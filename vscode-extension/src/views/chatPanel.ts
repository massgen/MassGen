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
        * {
            box-sizing: border-box;
        }

        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: linear-gradient(135deg,
                var(--vscode-editor-background) 0%,
                color-mix(in srgb, var(--vscode-editor-background) 95%, var(--vscode-activityBar-background) 5%) 100%);
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }

        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-track {
            background: var(--vscode-editor-background);
        }

        ::-webkit-scrollbar-thumb {
            background: color-mix(in srgb, var(--vscode-scrollbarSlider-background) 70%, transparent 30%);
            border-radius: 5px;
            transition: background 0.3s ease;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--vscode-scrollbarSlider-hoverBackground);
        }

        .header {
            padding: 16px 24px;
            background: linear-gradient(135deg,
                color-mix(in srgb, var(--vscode-activityBar-background) 30%, transparent 70%),
                color-mix(in srgb, var(--vscode-sideBar-background) 20%, transparent 80%));
            border-bottom: 2px solid color-mix(in srgb, var(--vscode-panel-border) 50%, transparent 50%);
            backdrop-filter: blur(10px);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            margin: 0 0 12px 0;
            font-size: 20px;
            font-weight: 700;
            background: linear-gradient(135deg,
                var(--vscode-foreground) 0%,
                color-mix(in srgb, var(--vscode-foreground) 70%, var(--vscode-textLink-foreground) 30%) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.5px;
        }

        .model-selector-container {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .model-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--vscode-descriptionForeground);
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }

        .model-dropdown {
            position: relative;
            display: inline-block;
        }

        .dropdown-button {
            padding: 6px 12px;
            font-family: var(--vscode-font-family);
            font-size: 13px;
            font-weight: 500;
            color: var(--vscode-button-foreground);
            background: linear-gradient(135deg,
                var(--vscode-button-background),
                color-mix(in srgb, var(--vscode-button-background) 85%, var(--vscode-textLink-foreground) 15%));
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .dropdown-button:hover {
            background: linear-gradient(135deg,
                var(--vscode-button-hoverBackground),
                color-mix(in srgb, var(--vscode-button-hoverBackground) 85%, var(--vscode-textLink-foreground) 15%));
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .dropdown-arrow {
            font-size: 10px;
            transition: transform 0.3s ease;
        }

        .dropdown-arrow.open {
            transform: rotate(180deg);
        }

        .dropdown-menu {
            display: none;
            position: absolute;
            top: calc(100% + 8px);
            left: 0;
            min-width: 300px;
            max-height: 400px;
            background-color: var(--vscode-dropdown-background);
            border: 1.5px solid var(--vscode-dropdown-border);
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            z-index: 1000;
            overflow: hidden;
            animation: dropdownSlide 0.2s ease;
        }

        @keyframes dropdownSlide {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .dropdown-menu.show {
            display: flex;
            flex-direction: column;
        }

        .dropdown-search {
            padding: 8px;
            border-bottom: 1px solid var(--vscode-dropdown-border);
        }

        .dropdown-search input {
            width: 100%;
            padding: 6px 10px;
            font-family: var(--vscode-font-family);
            font-size: 12px;
            color: var(--vscode-input-foreground);
            background-color: var(--vscode-input-background);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            outline: none;
        }

        .dropdown-search input:focus {
            border-color: var(--vscode-focusBorder);
        }

        .dropdown-content {
            overflow-y: auto;
            max-height: 350px;
        }

        .provider-group {
            border-bottom: 1px solid color-mix(in srgb, var(--vscode-dropdown-border) 50%, transparent 50%);
        }

        .provider-group:last-child {
            border-bottom: none;
        }

        .provider-header {
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 700;
            color: var(--vscode-descriptionForeground);
            background-color: color-mix(in srgb, var(--vscode-dropdown-background) 90%, var(--vscode-foreground) 10%);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
            z-index: 1;
        }

        .model-option {
            padding: 8px 12px;
            font-size: 13px;
            color: var(--vscode-dropdown-foreground);
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .model-option:hover {
            background-color: var(--vscode-list-hoverBackground);
        }

        .model-option.popular {
            font-weight: 500;
        }

        .model-option.popular::before {
            content: "⭐";
            font-size: 11px;
        }

        .model-option.selected {
            background-color: var(--vscode-list-activeSelectionBackground);
            color: var(--vscode-list-activeSelectionForeground);
            font-weight: 600;
        }

        .selected-models {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
            animation: fadeIn 0.4s ease;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-5px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .selected-model-tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: linear-gradient(135deg,
                var(--vscode-inputOption-activeBackground),
                color-mix(in srgb, var(--vscode-inputOption-activeBackground) 80%, var(--vscode-button-background) 20%));
            border: 1.5px solid var(--vscode-focusBorder);
            border-radius: 16px;
            font-size: 12px;
            font-weight: 500;
            color: var(--vscode-foreground);
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: scale(0.8);
            }
            to {
                opacity: 1;
                transform: scale(1);
            }
        }

        .selected-model-tag:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .remove-model {
            cursor: pointer;
            color: var(--vscode-descriptionForeground);
            font-weight: bold;
            font-size: 16px;
            line-height: 1;
            margin-left: 4px;
            transition: all 0.2s ease;
            padding: 2px;
            border-radius: 50%;
        }

        .remove-model:hover {
            color: var(--vscode-errorForeground);
            background: color-mix(in srgb, var(--vscode-errorForeground) 20%, transparent 80%);
            transform: rotate(90deg);
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            scroll-behavior: smooth;
        }

        .message {
            margin-bottom: 20px;
            padding: 16px 20px;
            border-radius: 12px;
            background-color: var(--vscode-input-background);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            transition: all 0.3s ease;
            animation: messageSlideIn 0.4s ease;
            border: 1px solid color-mix(in srgb, var(--vscode-panel-border) 30%, transparent 70%);
        }

        @keyframes messageSlideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        }

        .message.user {
            background: linear-gradient(135deg,
                var(--vscode-inputOption-activeBackground),
                color-mix(in srgb, var(--vscode-inputOption-activeBackground) 90%, var(--vscode-button-background) 10%));
            border-left: 4px solid var(--vscode-textLink-foreground);
        }

        .message.agent {
            background: linear-gradient(135deg,
                var(--vscode-editor-inactiveSelectionBackground),
                color-mix(in srgb, var(--vscode-editor-inactiveSelectionBackground) 90%, var(--vscode-editor-selectionBackground) 10%));
            border-left: 4px solid var(--vscode-charts-blue);
        }

        .message.error {
            background: linear-gradient(135deg,
                var(--vscode-inputValidation-errorBackground),
                color-mix(in srgb, var(--vscode-inputValidation-errorBackground) 90%, var(--vscode-errorForeground) 10%));
            border: 1.5px solid var(--vscode-inputValidation-errorBorder);
            border-left: 4px solid var(--vscode-errorForeground);
        }

        .message.progress {
            background: linear-gradient(135deg,
                var(--vscode-editor-selectionBackground),
                color-mix(in srgb, var(--vscode-editor-selectionBackground) 90%, var(--vscode-charts-blue) 10%));
            border-left: 4px solid var(--vscode-charts-yellow);
        }

        .message-header {
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            opacity: 0.95;
            letter-spacing: 0.3px;
        }

        .message-content {
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.6;
            font-size: 14px;
        }

        .agent-progress {
            margin-top: 16px;
        }

        .agent-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            font-size: 13px;
            transition: all 0.3s ease;
        }

        .agent-item:hover {
            transform: translateX(4px);
        }

        .agent-icon {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
        }

        .agent-icon.working {
            background: linear-gradient(135deg, var(--vscode-charts-blue), color-mix(in srgb, var(--vscode-charts-blue) 70%, var(--vscode-charts-purple) 30%));
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% {
                transform: scale(1);
                opacity: 1;
            }
            50% {
                transform: scale(1.1);
                opacity: 0.8;
            }
        }

        .agent-icon.complete {
            background: linear-gradient(135deg, var(--vscode-charts-green), color-mix(in srgb, var(--vscode-charts-green) 70%, var(--vscode-charts-blue) 30%));
            color: white;
            font-size: 11px;
        }

        .agent-icon.error {
            background: linear-gradient(135deg, var(--vscode-charts-red), color-mix(in srgb, var(--vscode-charts-red) 70%, var(--vscode-charts-orange) 30%));
            color: white;
            font-size: 11px;
        }

        .agent-name {
            font-weight: 600;
            flex: 1;
        }

        .agent-status {
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
            font-style: italic;
        }

        .status {
            padding: 10px 24px;
            background: linear-gradient(90deg,
                var(--vscode-statusBar-background),
                color-mix(in srgb, var(--vscode-statusBar-background) 95%, var(--vscode-activityBar-background) 5%));
            color: var(--vscode-statusBar-foreground);
            font-size: 13px;
            font-weight: 500;
            box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
        }

        .input-area {
            padding: 20px 24px;
            background: linear-gradient(180deg,
                color-mix(in srgb, var(--vscode-editor-background) 95%, var(--vscode-activityBar-background) 5%),
                var(--vscode-editor-background));
            border-top: 2px solid color-mix(in srgb, var(--vscode-panel-border) 50%, transparent 50%);
            box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.08);
        }

        .input-wrapper {
            display: flex;
            gap: 12px;
            align-items: flex-end;
        }

        textarea {
            flex: 1;
            min-height: 70px;
            max-height: 200px;
            padding: 12px 16px;
            font-family: var(--vscode-font-family);
            font-size: 14px;
            line-height: 1.5;
            color: var(--vscode-input-foreground);
            background-color: var(--vscode-input-background);
            border: 2px solid color-mix(in srgb, var(--vscode-input-border) 50%, transparent 50%);
            border-radius: 10px;
            resize: vertical;
            transition: all 0.3s ease;
        }

        textarea:hover {
            border-color: color-mix(in srgb, var(--vscode-focusBorder) 60%, transparent 40%);
        }

        textarea:focus {
            outline: none;
            border-color: var(--vscode-focusBorder);
            box-shadow: 0 0 0 3px color-mix(in srgb, var(--vscode-focusBorder) 20%, transparent 80%),
                        0 4px 12px rgba(0, 0, 0, 0.1);
        }

        button {
            padding: 12px 24px;
            font-family: var(--vscode-font-family);
            font-size: 14px;
            font-weight: 600;
            color: var(--vscode-button-foreground);
            background: linear-gradient(135deg,
                var(--vscode-button-background),
                color-mix(in srgb, var(--vscode-button-background) 85%, var(--vscode-textLink-foreground) 15%));
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        button:hover:not(:disabled) {
            background: linear-gradient(135deg,
                var(--vscode-button-hoverBackground),
                color-mix(in srgb, var(--vscode-button-hoverBackground) 85%, var(--vscode-textLink-foreground) 15%));
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
        }

        button:active:not(:disabled) {
            transform: translateY(0);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .loading {
            display: inline-block;
            width: 10px;
            height: 10px;
            border: 2px solid currentColor;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .streaming-cursor {
            display: inline-block;
            color: var(--vscode-foreground);
            animation: blink 1s step-end infinite;
            margin-left: 3px;
            font-weight: bold;
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
        <div class="model-selector-container">
            <span class="model-label">Models:</span>
            <div class="model-dropdown">
                <button class="dropdown-button" id="dropdownButton" onclick="toggleDropdown()">
                    <span id="dropdownButtonText">Select Models</span>
                    <span class="dropdown-arrow" id="dropdownArrow">▼</span>
                </button>
                <div class="dropdown-menu" id="dropdownMenu">
                    <div class="dropdown-search">
                        <input type="text" id="modelSearch" placeholder="Search models..." oninput="filterModels()">
                    </div>
                    <div class="dropdown-content" id="dropdownContent">
                        <!-- Models will be loaded dynamically -->
                        <div style="padding: 12px; color: var(--vscode-descriptionForeground); font-size: 12px;">Loading models...</div>
                    </div>
                </div>
            </div>
            <div class="selected-models" id="selectedModels"></div>
        </div>
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

        function toggleDropdown() {
            const menu = document.getElementById('dropdownMenu');
            const arrow = document.getElementById('dropdownArrow');

            if (menu.classList.contains('show')) {
                menu.classList.remove('show');
                arrow.classList.remove('open');
            } else {
                menu.classList.add('show');
                arrow.classList.add('open');
                // Focus search input
                setTimeout(() => {
                    const searchInput = document.getElementById('modelSearch');
                    if (searchInput) searchInput.focus();
                }, 100);
            }
        }

        function closeDropdown() {
            const menu = document.getElementById('dropdownMenu');
            const arrow = document.getElementById('dropdownArrow');
            menu.classList.remove('show');
            arrow.classList.remove('open');
        }

        function filterModels() {
            const searchTerm = document.getElementById('modelSearch').value.toLowerCase();
            const providerGroups = document.querySelectorAll('.provider-group');

            providerGroups.forEach(group => {
                const models = group.querySelectorAll('.model-option');
                let hasVisibleModels = false;

                models.forEach(model => {
                    const modelName = model.textContent.toLowerCase();
                    if (modelName.includes(searchTerm)) {
                        model.style.display = 'flex';
                        hasVisibleModels = true;
                    } else {
                        model.style.display = 'none';
                    }
                });

                // Hide provider group if no models match
                group.style.display = hasVisibleModels ? 'block' : 'none';
            });
        }

        function renderModelSelector() {
            const content = document.getElementById('dropdownContent');
            if (!content) return;

            if (Object.keys(modelsByProvider).length === 0) {
                content.innerHTML = '<div style="padding: 12px; color: var(--vscode-descriptionForeground); font-size: 12px;">No models available</div>';
                return;
            }

            content.innerHTML = '';

            Object.entries(modelsByProvider).forEach(([provider, data]) => {
                const providerGroup = document.createElement('div');
                providerGroup.className = 'provider-group';

                // Provider header
                const header = document.createElement('div');
                header.className = 'provider-header';
                header.textContent = provider;
                providerGroup.appendChild(header);

                // Add popular models first
                if (data.popular && data.popular.length > 0) {
                    data.popular.forEach(model => {
                        const option = createModelOption(model, true);
                        providerGroup.appendChild(option);
                    });
                }

                // Add all other models (excluding duplicates)
                const popularSet = new Set(data.popular || []);
                data.models.forEach(model => {
                    if (!popularSet.has(model)) {
                        const option = createModelOption(model, false);
                        providerGroup.appendChild(option);
                    }
                });

                content.appendChild(providerGroup);
            });

            updateSelectedModelsDisplay();
            updateDropdownButtonText();
        }

        function createModelOption(model, isPopular) {
            const option = document.createElement('div');
            option.className = 'model-option' + (isPopular ? ' popular' : '');
            option.textContent = model;
            option.dataset.model = model;

            if (selectedModels.includes(model)) {
                option.classList.add('selected');
            }

            option.onclick = () => {
                if (selectedModels.includes(model)) {
                    // Deselect
                    selectedModels = selectedModels.filter(m => m !== model);
                    option.classList.remove('selected');
                } else {
                    // Select
                    selectedModels.push(model);
                    option.classList.add('selected');
                }
                updateSelectedModelsDisplay();
                updateDropdownButtonText();
            };

            return option;
        }

        function updateDropdownButtonText() {
            const buttonText = document.getElementById('dropdownButtonText');
            if (!buttonText) return;

            if (selectedModels.length === 0) {
                buttonText.textContent = 'Select Models';
            } else if (selectedModels.length === 1) {
                buttonText.textContent = selectedModels[0].substring(0, 20) + (selectedModels[0].length > 20 ? '...' : '');
            } else {
                buttonText.textContent = \`\${selectedModels.length} Models Selected\`;
            }
        }

        function removeModel(model) {
            selectedModels = selectedModels.filter(m => m !== model);

            // Update the model option in the dropdown
            const modelOptions = document.querySelectorAll('.model-option');
            modelOptions.forEach(option => {
                if (option.dataset.model === model) {
                    option.classList.remove('selected');
                }
            });

            updateSelectedModelsDisplay();
            updateDropdownButtonText();
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            const dropdown = document.querySelector('.model-dropdown');
            const menu = document.getElementById('dropdownMenu');

            if (dropdown && !dropdown.contains(event.target) && menu.classList.contains('show')) {
                closeDropdown();
            }
        });

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
