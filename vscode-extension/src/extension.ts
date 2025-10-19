/**
 * MassGen VSCode Extension
 * Main entry point
 */

import * as vscode from 'vscode';
import { MassGenClient } from './massgenClient';
import { ChatPanel } from './views/chatPanel';

let client: MassGenClient | undefined;

/**
 * Extension activation
 */
export async function activate(context: vscode.ExtensionContext) {
    console.log('MassGen extension is activating...');

    // Initialize MassGen client
    client = new MassGenClient(context);

    // Register commands first (so they're always available)
    registerCommands(context);

    // Try to start the server in the background
    try {
        await client.start();
        console.log('MassGen extension activated successfully');
        vscode.window.showInformationMessage('MassGen is ready! Use "MassGen: Start Chat" to begin.');
    } catch (error) {
        console.error('Failed to start MassGen server:', error);
        vscode.window.showWarningMessage(
            `MassGen extension loaded, but server failed to start: ${error}\n\n` +
            'Make sure MassGen is installed: pip install massgen'
        );
    }
}

/**
 * Register all extension commands
 */
function registerCommands(context: vscode.ExtensionContext) {
    // Command: Start Chat
    context.subscriptions.push(
        vscode.commands.registerCommand('massgen.chat', () => {
            if (client) {
                ChatPanel.createOrShow(context, client);
            }
        })
    );

    // Command: Analyze Code Selection
    context.subscriptions.push(
        vscode.commands.registerCommand('massgen.analyzeCode', async () => {
            if (!client) {
                return;
            }

            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }

            const selection = editor.document.getText(editor.selection);
            if (!selection) {
                vscode.window.showWarningMessage('No code selected');
                return;
            }

            const language = editor.document.languageId;

            try {
                // Show chat panel
                ChatPanel.createOrShow(context, client);

                // Send analysis request
                vscode.window.showInformationMessage('Analyzing code...');
                await client.analyzeCode(selection, language);

            } catch (error) {
                vscode.window.showErrorMessage(`Analysis failed: ${error}`);
            }
        })
    );

    // Command: Configure Agents
    context.subscriptions.push(
        vscode.commands.registerCommand('massgen.configure', async () => {
            vscode.window.showInformationMessage(
                'Configuration UI coming soon! For now, edit your config files directly.'
            );

            // TODO: Implement configuration UI
        })
    );

    // Command: Test Connection
    context.subscriptions.push(
        vscode.commands.registerCommand('massgen.testConnection', async () => {
            if (!client) {
                vscode.window.showErrorMessage('MassGen client not initialized');
                return;
            }

            try {
                const result = await client.sendRequest('test_connection', {});
                if (result.success) {
                    vscode.window.showInformationMessage('✅ MassGen connection successful!');
                    client.showOutput();
                } else {
                    vscode.window.showErrorMessage('❌ Connection test failed');
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Connection test failed: ${error}`);
            }
        })
    );

    // Status bar item
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    statusBarItem.text = '$(comment-discussion) MassGen';
    statusBarItem.tooltip = 'Click to open MassGen chat';
    statusBarItem.command = 'massgen.chat';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
}

/**
 * Extension deactivation
 */
export function deactivate() {
    if (client) {
        client.stop();
        client = undefined;
    }
}
