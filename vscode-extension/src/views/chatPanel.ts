/**
 * Chat Panel - Webview for MassGen chat interface
 */

import * as vscode from 'vscode';
import { MassGenClient, MassGenEvent } from '../massgenClient';

export class ChatPanel {
    public static currentPanel: ChatPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];

    private constructor(
        panel: vscode.WebviewPanel,
        private readonly context: vscode.ExtensionContext,
        private readonly client: MassGenClient
    ) {
        this.panel = panel;

        // Set up event handlers
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
        this.panel.webview.onDidReceiveMessage(
            message => this.handleWebviewMessage(message),
            null,
            this.disposables
        );

        // Listen to MassGen events
        this.client.onEvent(event => this.handleMassGenEvent(event));

        // Set initial HTML content
        this.panel.webview.html = this.getHtmlContent();
    }

    /**
     * Create or show the chat panel
     */
    public static createOrShow(context: vscode.ExtensionContext, client: MassGenClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        // If we already have a panel, show it
        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel.panel.reveal(column);
            return;
        }

        // Otherwise, create a new panel
        const panel = vscode.window.createWebviewPanel(
            'massgenChat',
            'MassGen Chat',
            column || vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(context.extensionUri, 'media')
                ]
            }
        );

        ChatPanel.currentPanel = new ChatPanel(panel, context, client);
    }

    /**
     * Handle messages from the webview
     */
    private async handleWebviewMessage(message: any): Promise<void> {
        switch (message.type) {
            case 'sendQuery':
                await this.handleQuery(message.text, message.config);
                break;

            case 'analyzeCode':
                await this.handleAnalyzeCode(message.code, message.language);
                break;

            case 'listConfigs':
                await this.handleListConfigs();
                break;

            case 'ready':
                // Webview is ready
                this.sendToWebview({ type: 'init', data: {} });
                break;
        }
    }

    /**
     * Handle query from user
     */
    private async handleQuery(text: string, config?: string): Promise<void> {
        try {
            this.sendToWebview({
                type: 'queryStart',
                data: { text }
            });

            const result = await this.client.query(text, config);

            this.sendToWebview({
                type: 'queryComplete',
                data: result
            });

        } catch (error) {
            this.sendToWebview({
                type: 'error',
                data: { message: String(error) }
            });
            vscode.window.showErrorMessage(`Query failed: ${error}`);
        }
    }

    /**
     * Handle code analysis
     */
    private async handleAnalyzeCode(code: string, language?: string): Promise<void> {
        try {
            const result = await this.client.analyzeCode(code, language);
            this.sendToWebview({
                type: 'analysisResult',
                data: result
            });
        } catch (error) {
            vscode.window.showErrorMessage(`Analysis failed: ${error}`);
        }
    }

    /**
     * Handle list configs request
     */
    private async handleListConfigs(): Promise<void> {
        try {
            const result = await this.client.listConfigs();
            this.sendToWebview({
                type: 'configList',
                data: result
            });
        } catch (error) {
            vscode.window.showErrorMessage(`Failed to list configs: ${error}`);
        }
    }

    /**
     * Handle events from MassGen
     */
    private handleMassGenEvent(event: MassGenEvent): void {
        // Forward event to webview
        this.sendToWebview({
            type: 'massgenEvent',
            data: event
        });
    }

    /**
     * Send message to webview
     */
    private sendToWebview(message: any): void {
        this.panel.webview.postMessage(message);
    }

    /**
     * Get HTML content for the webview
     */
    private getHtmlContent(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MassGen Chat</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        .header {
            padding: 16px;
            background-color: var(--vscode-editor-background);
            border-bottom: 1px solid var(--vscode-panel-border);
        }

        .header h1 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }

        .message {
            margin-bottom: 16px;
            padding: 12px;
            border-radius: 4px;
            background-color: var(--vscode-input-background);
        }

        .message.user {
            background-color: var(--vscode-inputOption-activeBackground);
        }

        .message.agent {
            background-color: var(--vscode-editor-inactiveSelectionBackground);
        }

        .message.error {
            background-color: var(--vscode-inputValidation-errorBackground);
            border: 1px solid var(--vscode-inputValidation-errorBorder);
        }

        .message-header {
            font-weight: 600;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .message-content {
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .status {
            padding: 8px 16px;
            background-color: var(--vscode-statusBar-background);
            color: var(--vscode-statusBar-foreground);
            font-size: 12px;
        }

        .input-area {
            padding: 16px;
            background-color: var(--vscode-editor-background);
            border-top: 1px solid var(--vscode-panel-border);
        }

        .input-wrapper {
            display: flex;
            gap: 8px;
        }

        textarea {
            flex: 1;
            min-height: 60px;
            padding: 8px;
            font-family: var(--vscode-font-family);
            font-size: 14px;
            color: var(--vscode-input-foreground);
            background-color: var(--vscode-input-background);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            resize: vertical;
        }

        textarea:focus {
            outline: 1px solid var(--vscode-focusBorder);
        }

        button {
            padding: 8px 16px;
            font-family: var(--vscode-font-family);
            font-size: 14px;
            color: var(--vscode-button-foreground);
            background-color: var(--vscode-button-background);
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }

        button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .loading {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid var(--vscode-foreground);
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 MassGen - Multi-Agent AI Assistant</h1>
    </div>

    <div class="status" id="status">Ready</div>

    <div class="chat-container" id="chatContainer">
        <div class="message agent">
            <div class="message-header">MassGen</div>
            <div class="message-content">Welcome! I'm MassGen, a multi-agent AI system. Ask me anything, and multiple AI agents will collaborate to give you the best answer.</div>
        </div>
    </div>

    <div class="input-area">
        <div class="input-wrapper">
            <textarea id="queryInput" placeholder="Ask anything... (e.g., 'Explain quantum computing', 'Analyze this code', etc.)"></textarea>
            <button id="sendButton" onclick="sendQuery()">Send</button>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        let isProcessing = false;

        // Notify extension that webview is ready
        window.addEventListener('load', () => {
            vscode.postMessage({ type: 'ready' });
        });

        // Handle messages from extension
        window.addEventListener('message', event => {
            const message = event.data;
            handleMessage(message);
        });

        function handleMessage(message) {
            switch (message.type) {
                case 'init':
                    setStatus('Ready');
                    break;

                case 'queryStart':
                    isProcessing = true;
                    updateUI();
                    addMessage('user', 'You', message.data.text);
                    setStatus('Processing query...');
                    break;

                case 'queryComplete':
                    isProcessing = false;
                    updateUI();
                    addMessage('agent', 'MassGen', JSON.stringify(message.data.result, null, 2));
                    setStatus('Ready');
                    break;

                case 'massgenEvent':
                    handleMassGenEvent(message.data);
                    break;

                case 'error':
                    isProcessing = false;
                    updateUI();
                    addMessage('error', 'Error', message.data.message);
                    setStatus('Error');
                    break;
            }
        }

        function handleMassGenEvent(event) {
            console.log('MassGen event:', event);

            switch (event.type) {
                case 'execution_start':
                    setStatus('🔄 Agents working...');
                    break;

                case 'execution_complete':
                    setStatus('✅ Complete');
                    break;

                case 'log':
                    console.log(\`[MassGen \${event.level}]\`, event.message);
                    break;
            }
        }

        function sendQuery() {
            const input = document.getElementById('queryInput');
            const text = input.value.trim();

            if (!text || isProcessing) {
                return;
            }

            vscode.postMessage({
                type: 'sendQuery',
                text: text,
                config: null
            });

            input.value = '';
        }

        function addMessage(type, sender, content) {
            const container = document.getElementById('chatContainer');
            const messageDiv = document.createElement('div');
            messageDiv.className = \`message \${type}\`;

            messageDiv.innerHTML = \`
                <div class="message-header">\${sender}</div>
                <div class="message-content">\${escapeHtml(content)}</div>
            \`;

            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }

        function setStatus(text) {
            document.getElementById('status').textContent = text;
        }

        function updateUI() {
            const sendButton = document.getElementById('sendButton');
            sendButton.disabled = isProcessing;
            sendButton.textContent = isProcessing ? 'Processing...' : 'Send';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Allow Enter to send (Shift+Enter for new line)
        document.getElementById('queryInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendQuery();
            }
        });
    </script>
</body>
</html>`;
    }

    /**
     * Dispose of resources
     */
    public dispose(): void {
        ChatPanel.currentPanel = undefined;

        this.panel.dispose();

        while (this.disposables.length) {
            const disposable = this.disposables.pop();
            if (disposable) {
                disposable.dispose();
            }
        }
    }
}
