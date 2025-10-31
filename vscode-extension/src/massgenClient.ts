/**
 * MassGen Client - Manages communication with Python backend
 */

import * as vscode from 'vscode';
import { ChildProcess, spawn } from 'child_process';
import * as path from 'path';

export interface MassGenEvent {
    type: string;
    [key: string]: any;
}

export interface MassGenResponse {
    success: boolean;
    result?: any;
    error?: string;
}

export class MassGenClient {
    private pythonProcess?: ChildProcess;
    private requestId = 0;
    private pendingRequests = new Map<number, {
        resolve: (value: any) => void;
        reject: (reason: any) => void;
    }>();
    private eventListeners: ((event: MassGenEvent) => void)[] = [];
    private outputChannel: vscode.OutputChannel;
    private pythonPath: string;

    constructor(private context: vscode.ExtensionContext) {
        this.outputChannel = vscode.window.createOutputChannel('MassGen');

        // Get Python path from configuration
        const config = vscode.workspace.getConfiguration('massgen');
        this.pythonPath = config.get('pythonPath', 'python');
    }

    /**
     * Start the MassGen Python server
     */
    async start(): Promise<void> {
        if (this.pythonProcess) {
            this.log('Server already running');
            return;
        }

        this.log('Starting MassGen server...');

        try {
            // Find the massgen package directory
            const massgenPath = await this.findMassGenPath();

            // Start Python process
            this.pythonProcess = spawn(this.pythonPath, [
                '-m', 'massgen.vscode_adapter.server'
            ], {
                cwd: massgenPath
            });

            // Set up stdio communication
            this.setupCommunication();

            // Test connection
            const result = await this.sendRequest('test_connection', {});
            if (result.success) {
                this.log('MassGen server started successfully');
                vscode.window.showInformationMessage('MassGen: Server connected');
            } else {
                throw new Error('Connection test failed');
            }

        } catch (error) {
            const message = `Failed to start MassGen server: ${error}`;
            this.log(message, 'error');
            vscode.window.showErrorMessage(message);
            throw error;
        }
    }

    /**
     * Stop the server
     */
    stop(): void {
        if (this.pythonProcess) {
            this.log('Stopping MassGen server...');
            this.pythonProcess.kill();
            this.pythonProcess = undefined;
        }
    }

    /**
     * Send a JSON-RPC request to the Python server
     */
    async sendRequest(method: string, params: any): Promise<any> {
        if (!this.pythonProcess) {
            throw new Error('MassGen server not started');
        }

        const id = this.requestId++;
        const request = {
            jsonrpc: '2.0',
            id,
            method,
            params
        };

        return new Promise((resolve, reject) => {
            // Store pending request
            this.pendingRequests.set(id, { resolve, reject });

            // Send request
            const requestStr = JSON.stringify(request) + '\n';
            this.pythonProcess!.stdin?.write(requestStr);

            this.log(`Sent request: ${method}`, 'debug');

            // Set timeout
            setTimeout(() => {
                if (this.pendingRequests.has(id)) {
                    this.pendingRequests.delete(id);
                    reject(new Error(`Request timeout: ${method}`));
                }
            }, 30000); // 30 second timeout
        });
    }

    /**
     * Query MassGen with a question
     */
    async query(text: string, config?: string, models?: string[]): Promise<any> {
        return this.sendRequest('query', { text, config, models });
    }

    /**
     * Analyze code
     */
    async analyzeCode(code: string, language?: string): Promise<any> {
        return this.sendRequest('analyze', { code, language });
    }

    /**
     * List available configurations
     */
    async listConfigs(): Promise<any> {
        return this.sendRequest('list_configs', {});
    }

    /**
     * Get available models
     */
    async getAvailableModels(): Promise<any> {
        return this.sendRequest('get_available_models', {});
    }

    /**
     * Register event listener
     */
    onEvent(listener: (event: MassGenEvent) => void): vscode.Disposable {
        this.eventListeners.push(listener);
        return new vscode.Disposable(() => {
            const index = this.eventListeners.indexOf(listener);
            if (index >= 0) {
                this.eventListeners.splice(index, 1);
            }
        });
    }

    /**
     * Set up stdio communication
     */
    private setupCommunication(): void {
        if (!this.pythonProcess) {
            return;
        }

        let buffer = '';

        // Handle stdout (responses and events)
        this.pythonProcess.stdout?.on('data', (data: Buffer) => {
            buffer += data.toString();

            // Process complete lines
            let lineEnd;
            while ((lineEnd = buffer.indexOf('\n')) >= 0) {
                const line = buffer.slice(0, lineEnd).trim();
                buffer = buffer.slice(lineEnd + 1);

                if (line) {
                    try {
                        const message = JSON.parse(line);
                        this.handleMessage(message);
                    } catch (error) {
                        this.log(`Failed to parse message: ${line}`, 'error');
                    }
                }
            }
        });

        // Handle stderr (logs)
        this.pythonProcess.stderr?.on('data', (data: Buffer) => {
            const message = data.toString();
            this.log(`Python: ${message}`, 'debug');
        });

        // Handle process exit
        this.pythonProcess.on('exit', (code) => {
            this.log(`MassGen server exited with code ${code}`);
            this.pythonProcess = undefined;

            // Reject all pending requests
            for (const [id, { reject }] of this.pendingRequests) {
                reject(new Error('Server disconnected'));
            }
            this.pendingRequests.clear();
        });

        // Handle errors
        this.pythonProcess.on('error', (error) => {
            this.log(`Process error: ${error}`, 'error');
            vscode.window.showErrorMessage(`MassGen error: ${error.message}`);
        });
    }

    /**
     * Handle incoming message from Python
     */
    private handleMessage(message: any): void {
        if (message.method === 'event') {
            // This is an event notification
            const event = message.params as MassGenEvent;
            this.handleEvent(event);
        } else if (message.id !== undefined) {
            // This is a response to a request
            const pending = this.pendingRequests.get(message.id);
            if (pending) {
                this.pendingRequests.delete(message.id);

                if (message.error) {
                    pending.reject(new Error(message.error.message));
                } else {
                    pending.resolve(message.result);
                }
            }
        }
    }

    /**
     * Handle event from Python
     */
    private handleEvent(event: MassGenEvent): void {
        this.log(`Event: ${event.type}`, 'debug');

        // Special handling for log events
        if (event.type === 'log') {
            this.log(`[Python] ${event.message}`, event.level || 'info');
        }

        // Notify all listeners
        for (const listener of this.eventListeners) {
            try {
                listener(event);
            } catch (error) {
                this.log(`Event listener error: ${error}`, 'error');
            }
        }
    }

    /**
     * Find MassGen installation path
     */
    private async findMassGenPath(): Promise<string> {
        // Try to find massgen package
        // First, check if we're in development mode (running from source)
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (workspaceFolder) {
            const devPath = path.join(workspaceFolder.uri.fsPath, 'massgen');
            // Check if massgen directory exists
            try {
                const fs = require('fs').promises;
                await fs.access(devPath);
                this.log(`Using development MassGen at: ${devPath}`);
                return workspaceFolder.uri.fsPath;
            } catch {
                // Not in dev mode
            }
        }

        // Otherwise, assume massgen is installed via pip
        this.log('Using installed MassGen package');
        return process.cwd();
    }

    /**
     * Log message to output channel
     */
    private log(message: string, level: 'info' | 'error' | 'debug' = 'info'): void {
        const config = vscode.workspace.getConfiguration('massgen');
        const enableLogging = config.get('enableLogging', true);

        if (!enableLogging && level === 'debug') {
            return;
        }

        const timestamp = new Date().toISOString();
        const prefix = level === 'error' ? '[ERROR]' : level === 'debug' ? '[DEBUG]' : '[INFO]';
        this.outputChannel.appendLine(`${timestamp} ${prefix} ${message}`);
    }

    /**
     * Show output channel
     */
    showOutput(): void {
        this.outputChannel.show();
    }
}
