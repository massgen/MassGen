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
                await this.handleQuery(message.text, message.config, message.models);
                break;

            case 'analyzeCode':
                await this.handleAnalyzeCode(message.code, message.language);
                break;

            case 'listConfigs':
                await this.handleListConfigs();
                break;

            case 'getAvailableModels':
                await this.handleGetAvailableModels();
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
    private async handleQuery(text: string, config?: string, models?: string[]): Promise<void> {
        try {
            this.sendToWebview({
                type: 'queryStart',
                data: { text, models }
            });

            // Query is handled asynchronously, streaming will be handled via events
            const result = await this.client.query(text, config, models);

            // Only send queryComplete if we didn't already stream the result
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
     * Handle get available models request
     */
    private async handleGetAvailableModels(): Promise<void> {
        try {
            const result = await this.client.getAvailableModels();
            this.sendToWebview({
                type: 'availableModels',
                data: result
            });
        } catch (error) {
            vscode.window.showErrorMessage(`Failed to get available models: ${error}`);
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
            margin: 0 0 12px 0;
            font-size: 18px;
            font-weight: 600;
        }

        .model-selector {
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }

        .provider-section {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .provider-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--vscode-foreground);
            white-space: nowrap;
        }

        .provider-select {
            min-width: 150px;
            padding: 4px 8px;
            font-family: var(--vscode-font-family);
            font-size: 12px;
            color: var(--vscode-input-foreground);
            background-color: var(--vscode-input-background);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            cursor: pointer;
        }

        .provider-select:focus {
            outline: 1px solid var(--vscode-focusBorder);
        }

        .provider-select option {
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
        }

        .model-label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 8px;
        }

        .selected-models {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 8px;
        }

        .selected-model-tag {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            background-color: var(--vscode-inputOption-activeBackground);
            border: 1px solid var(--vscode-focusBorder);
            border-radius: 12px;
            font-size: 11px;
            color: var(--vscode-foreground);
        }

        .remove-model {
            cursor: pointer;
            color: var(--vscode-descriptionForeground);
            font-weight: bold;
            margin-left: 2px;
        }

        .remove-model:hover {
            color: var(--vscode-errorForeground);
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

        .message.progress {
            background-color: var(--vscode-editor-selectionBackground);
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

        .agent-progress {
            margin-top: 12px;
        }

        .agent-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 0;
            font-size: 12px;
        }

        .agent-icon {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .agent-icon.working {
            background-color: var(--vscode-charts-blue);
        }

        .agent-icon.complete {
            background-color: var(--vscode-charts-green);
        }

        .agent-icon.error {
            background-color: var(--vscode-charts-red);
        }

        .agent-name {
            font-weight: 500;
        }

        .agent-status {
            color: var(--vscode-descriptionForeground);
            font-size: 11px;
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

        .streaming-cursor {
            display: inline-block;
            color: var(--vscode-foreground);
            animation: blink 1s step-end infinite;
            margin-left: 2px;
        }

        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 MassGen - Multi-Agent AI Assistant</h1>
        <div class="model-label">Select Models:</div>
        <div class="model-selector" id="modelSelector">
            <!-- Models will be loaded dynamically -->
            <div style="color: var(--vscode-descriptionForeground); font-size: 12px;">Loading available models...</div>
        </div>
        <div class="selected-models" id="selectedModels"></div>
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
        let modelsByProvider = {};
        let selectedModels = [];
        let currentStreamingMessageId = null; // Track the current streaming message
        let agentStreamingMessages = {}; // Map source -> messageId for each agent's streaming message

        // Notify extension that webview is ready
        window.addEventListener('load', () => {
            vscode.postMessage({ type: 'ready' });
            // Request available models
            vscode.postMessage({ type: 'getAvailableModels' });
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

                case 'availableModels':
                    handleAvailableModels(message.data);
                    break;

                case 'queryStart':
                    isProcessing = true;
                    updateUI();
                    addMessage('user', 'You', message.data.text);
                    if (message.data.models && message.data.models.length > 0) {
                        addAgentProgress(message.data.models);
                    }
                    // Clear previous agent streaming messages
                    agentStreamingMessages = {};
                    // Note: We no longer create a single streaming message upfront
                    // Each agent will create its own message box when it first sends content
                    setStatus('Processing query...');
                    break;

                case 'queryComplete':
                    isProcessing = false;
                    updateUI();

                    // Finalize all agent streaming messages
                    for (const source in agentStreamingMessages) {
                        const messageId = agentStreamingMessages[source];
                        finalizeStreamingMessage(messageId);
                    }

                    // Clear the agent streaming messages map
                    agentStreamingMessages = {};
                    currentStreamingMessageId = null;

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

        function handleAvailableModels(data) {
            if (data && data.models_by_provider) {
                modelsByProvider = data.models_by_provider;
                renderModelSelector();
            }
        }

        function renderModelSelector() {
            const selector = document.getElementById('modelSelector');
            if (!selector) return;

            if (Object.keys(modelsByProvider).length === 0) {
                selector.innerHTML = '<div style="color: var(--vscode-descriptionForeground); font-size: 12px;">No models available</div>';
                return;
            }

            selector.innerHTML = '';

            Object.entries(modelsByProvider).forEach(([provider, data]) => {
                const section = document.createElement('div');
                section.className = 'provider-section';

                // Provider label
                const label = document.createElement('label');
                label.className = 'provider-label';
                label.textContent = provider + ':';
                label.setAttribute('for', \`select-\${provider}\`);
                section.appendChild(label);

                // Provider select dropdown
                const select = document.createElement('select');
                select.className = 'provider-select';
                select.id = \`select-\${provider}\`;
                select.multiple = true;
                select.size = 1; // Compact dropdown

                // Add a placeholder option
                const placeholderOption = document.createElement('option');
                placeholderOption.value = '';
                placeholderOption.textContent = '-- Select models --';
                placeholderOption.disabled = true;
                select.appendChild(placeholderOption);

                // Add popular models first (if they exist)
                if (data.popular && data.popular.length > 0) {
                    const popularGroup = document.createElement('optgroup');
                    popularGroup.label = 'Popular';
                    data.popular.forEach((model) => {
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        popularGroup.appendChild(option);
                    });
                    select.appendChild(popularGroup);
                }

                // Add all models
                const allModelsGroup = document.createElement('optgroup');
                allModelsGroup.label = 'All Models';
                data.models.forEach((model) => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    allModelsGroup.appendChild(option);
                });
                select.appendChild(allModelsGroup);

                // Handle selection
                select.onchange = () => handleModelSelection(provider, select);

                section.appendChild(select);
                selector.appendChild(section);
            });

            updateSelectedModelsDisplay();
        }

        function handleModelSelection(provider, selectElement) {
            const selectedOptions = Array.from(selectElement.selectedOptions);

            // Add newly selected models
            selectedOptions.forEach(option => {
                const model = option.value;
                if (model && !selectedModels.includes(model)) {
                    selectedModels.push(model);
                }
            });

            // Clear the selection in the dropdown
            selectElement.selectedIndex = -1;

            updateSelectedModelsDisplay();
        }

        function removeModel(model) {
            selectedModels = selectedModels.filter(m => m !== model);
            updateSelectedModelsDisplay();
        }

        function updateSelectedModelsDisplay() {
            const container = document.getElementById('selectedModels');
            if (!container) return;

            if (selectedModels.length === 0) {
                container.innerHTML = '';
                return;
            }

            container.innerHTML = '';

            selectedModels.forEach(model => {
                const tag = document.createElement('div');
                tag.className = 'selected-model-tag';

                const modelText = document.createElement('span');
                modelText.textContent = model;
                tag.appendChild(modelText);

                const removeBtn = document.createElement('span');
                removeBtn.className = 'remove-model';
                removeBtn.textContent = '×';
                removeBtn.onclick = () => removeModel(model);
                tag.appendChild(removeBtn);

                container.appendChild(tag);
            });
        }

        function addAgentProgress(models) {
            const container = document.getElementById('chatContainer');
            const progressDiv = document.createElement('div');
            progressDiv.className = 'message progress';
            progressDiv.id = 'agent-progress-message';

            let html = \`
                <div class="message-header">Multi-Agent Execution</div>
                <div class="message-content">
                    <div class="agent-progress">
            \`;

            models.forEach(model => {
                html += \`
                    <div class="agent-item" id="agent-\${model.replace(/[^a-zA-Z0-9]/g, '-')}">
                        <div class="agent-icon working">
                            <div class="loading" style="width: 8px; height: 8px; border-width: 1px;"></div>
                        </div>
                        <span class="agent-name">\${model}</span>
                        <span class="agent-status">Working...</span>
                    </div>
                \`;
            });

            html += \`
                    </div>
                </div>
            \`;

            progressDiv.innerHTML = html;
            container.appendChild(progressDiv);
            container.scrollTop = container.scrollHeight;
        }

        function updateAgentStatus(model, status, message) {
            const agentId = 'agent-' + model.replace(/[^a-zA-Z0-9]/g, '-');
            const agentDiv = document.getElementById(agentId);
            if (!agentDiv) return;

            const icon = agentDiv.querySelector('.agent-icon');
            const statusSpan = agentDiv.querySelector('.agent-status');

            icon.className = 'agent-icon ' + status;
            icon.innerHTML = status === 'complete' ? '✓' : (status === 'error' ? '✗' : '<div class="loading" style="width: 8px; height: 8px; border-width: 1px;"></div>');
            statusSpan.textContent = message || status;
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

                case 'agent_update':
                    if (event.agent && event.status) {
                        updateAgentStatus(event.agent, event.status, event.message);
                    }
                    break;

                case 'stream_chunk':
                    // Handle streaming content - create separate message box for each agent
                    if (event.content) {
                        const source = event.source || 'unknown';

                        // Check if this source already has a streaming message
                        if (!agentStreamingMessages[source]) {
                            // Create a new message box for this agent/source
                            let senderName = source;
                            if (source === 'orchestrator') {
                                senderName = '🎯 Orchestrator';
                            } else if (source === 'final_answer') {
                                senderName = '🏆 Final Answer';
                            } else if (source && source !== 'unknown') {
                                senderName = \`🤖 \${source}\`;
                            } else {
                                senderName = 'MassGen';
                            }

                            agentStreamingMessages[source] = addMessage('agent', senderName, '', true);
                        }

                        // Append content to this agent's message
                        appendToMessage(agentStreamingMessages[source], event.content);
                    }
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

            // Use selected models, or fall back to a default
            const modelsToUse = selectedModels.length > 0 ? selectedModels : null;

            vscode.postMessage({
                type: 'sendQuery',
                text: text,
                config: null,
                models: modelsToUse
            });

            input.value = '';
        }

        function addMessage(type, sender, content, isStreaming = false) {
            const container = document.getElementById('chatContainer');
            const messageDiv = document.createElement('div');
            const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            messageDiv.id = messageId;
            messageDiv.className = \`message \${type}\`;

            // For streaming messages, add a cursor indicator
            const cursorHtml = isStreaming ? '<span class="streaming-cursor">▋</span>' : '';

            messageDiv.innerHTML = \`
                <div class="message-header">\${sender}</div>
                <div class="message-content">\${escapeHtml(content)}\${cursorHtml}</div>
            \`;

            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;

            return messageId;
        }

        function appendToMessage(messageId, text) {
            const messageDiv = document.getElementById(messageId);
            if (!messageDiv) return;

            const contentDiv = messageDiv.querySelector('.message-content');
            if (!contentDiv) return;

            // Get existing content (without the cursor)
            const cursor = contentDiv.querySelector('.streaming-cursor');
            if (cursor) {
                cursor.remove();
            }

            // Append new text
            const textNode = document.createTextNode(text);
            contentDiv.appendChild(textNode);

            // Re-add cursor at the end
            const newCursor = document.createElement('span');
            newCursor.className = 'streaming-cursor';
            newCursor.textContent = '▋';
            contentDiv.appendChild(newCursor);

            // Scroll to bottom
            const container = document.getElementById('chatContainer');
            container.scrollTop = container.scrollHeight;
        }

        function finalizeStreamingMessage(messageId) {
            const messageDiv = document.getElementById(messageId);
            if (!messageDiv) return;

            const contentDiv = messageDiv.querySelector('.message-content');
            if (!contentDiv) return;

            // Remove cursor
            const cursor = contentDiv.querySelector('.streaming-cursor');
            if (cursor) {
                cursor.remove();
            }
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
