# MassGen VSCode Plugin Development Guide

This document explains how to use and test the MassGen VSCode extension.

## 📁 Project Structure

```
MassGen/
├── massgen/
│   └── vscode_adapter/          # Python adapter module
│       ├── __init__.py
│       └── server.py            # JSON-RPC server
├── vscode-extension/            # VSCode extension
│   ├── src/
│   │   ├── extension.ts         # Main entry point
│   │   ├── massgenClient.ts     # Python communication client
│   │   └── views/
│   │       └── chatPanel.ts     # Chat panel Webview
│   ├── package.json
│   └── tsconfig.json
└── test_vscode_adapter.py       # Python adapter test script
```

## 🚀 Quick Start

### 1. Test Python Adapter

```bash
# Test the Python JSON-RPC server
python test_vscode_adapter.py
```

Expected output:
```
✅ All tests passed!
```

### 2. Test Extension in VSCode

#### Method 1: Using VSCode Extension Development Host

1. Open the `vscode-extension` folder in VSCode:
   ```bash
   cd vscode-extension
   code .
   ```

2. Press `F5` to launch Extension Development Host

3. In the new window:
   - Open Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`)
   - Run `MassGen: Test Connection`
   - If successful, you'll see "✅ MassGen connection successful!"

4. Test chat functionality:
   - Run `MassGen: Start Chat`
   - Type a question in the chat panel
   - Check the Output panel → "MassGen" channel for logs

#### Method 2: Manual Installation

```bash
cd vscode-extension

# Compile TypeScript
npm run compile

# Package (optional)
npm install -g @vscode/vsce
vsce package

# Install the generated .vsix file
code --install-extension massgen-vscode-0.1.0.vsix
```

## 🎯 Available Commands

| Command | Description |
|---------|-------------|
| `MassGen: Start Chat` | Open interactive chat panel |
| `MassGen: Analyze Code Selection` | Analyze selected code |
| `MassGen: Configure Agents` | Configure agents (WIP) |
| `MassGen: Test Connection` | Test Python backend connection |

## 🔧 Development Details

### Python Side (Adapter)

**Core file**: `massgen/vscode_adapter/server.py`

Key features:
- JSON-RPC server (stdio communication)
- Handles requests from VSCode
- Event streaming
- Integration with MassGen Orchestrator

Supported requests:
```python
{
    "initialize": Initialize server,
    "query": Execute query,
    "analyze": Analyze code,
    "configure": Configuration management,
    "list_configs": List available configurations,
    "test_connection": Test connection
}
```

### TypeScript Side (VSCode Extension)

**Core files**:
- `src/extension.ts` - Extension activation and command registration
- `src/massgenClient.ts` - Python process management and communication
- `src/views/chatPanel.ts` - Webview chat interface

Communication flow:
```
VSCode Extension
    ↓ (JSON-RPC request via stdin)
Python Server
    ↓ (execute query)
MassGen Orchestrator
    ↓ (events via stdout)
VSCode Extension (update UI)
```

## 🧪 Testing Checklist

- [x] Python adapter starts
- [x] JSON-RPC communication
- [x] Initialize connection
- [x] List configuration files
- [ ] Execute actual queries (requires API keys)
- [ ] Chat panel UI
- [ ] Code analysis feature
- [ ] Real-time event streaming

## 📝 Next Steps

### Short-term (1-2 weeks)

1. **Complete Query Execution**
   - Integrate Orchestrator's async execution
   - Real-time event streaming
   - Error handling and recovery

2. **Enhance UI**
   - Multi-agent parallel display
   - Voting and consensus visualization
   - Progress indicators

3. **Configuration Management**
   - GUI configuration editor
   - Configuration template selection
   - Secure API key storage

### Mid-term (3-4 weeks)

4. **Editor Integration**
   - Inline code suggestions
   - Quick actions
   - Code diff display

5. **History and Sessions**
   - Session save and restore
   - History browsing
   - Export results

### Long-term

6. **Advanced Features**
   - Custom agent templates
   - Marketplace publishing
   - Multi-workspace support

## 🐛 Known Issues

1. **Query Execution Not Fully Integrated**
   - Currently returns placeholder results only
   - Need to implement full Orchestrator integration

2. **Event Streaming Not Implemented**
   - Agent output events need to be captured from Orchestrator
   - Orchestrator needs modification to support event callbacks

3. **Configuration UI Not Developed**
   - Currently only supports file path configuration

## 💡 Implementation Notes

### How to Add a New JSON-RPC Method

1. Register in `server.py`'s `_setup_handlers`:
   ```python
   self.handlers["new_method"] = self._handle_new_method
   ```

2. Implement the handler:
   ```python
   async def _handle_new_method(self, params: Dict[str, Any]) -> Dict[str, Any]:
       # Handler logic
       return {"success": True, "data": result}
   ```

3. Add method in TypeScript:
   ```typescript
   async newMethod(params: any): Promise<any> {
       return this.sendRequest('new_method', params);
   }
   ```

### How to Send Events to VSCode

Python side:
```python
self._send_event({
    "type": "custom_event",
    "data": {"message": "Hello from Python"}
})
```

TypeScript side (listening):
```typescript
client.onEvent(event => {
    if (event.type === 'custom_event') {
        console.log(event.data.message);
    }
});
```

## 🏗️ Architecture Design

### Communication Protocol

The extension uses JSON-RPC 2.0 over stdio:

```typescript
// Request format
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "query",
    "params": {"text": "What is AI?"}
}

// Response format
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"success": true, "data": "..."}
}

// Event notification (no id)
{
    "jsonrpc": "2.0",
    "method": "event",
    "params": {"type": "agent_update", "data": {...}}
}
```

### Key Design Decisions

1. **stdio over WebSocket**: Simpler, no port conflicts
2. **JSON-RPC**: Standard protocol, easier debugging
3. **Async execution**: Non-blocking UI
4. **Event streaming**: Real-time agent updates

## 📚 References

- [VSCode Extension API](https://code.visualstudio.com/api)
- [JSON-RPC Specification](https://www.jsonrpc.org/specification)
- [MassGen Documentation](https://docs.massgen.io)

## 🧪 Testing the Extension

### Test Connection

```bash
# In Extension Development Host
1. Open Command Palette (Cmd+Shift+P)
2. Type "MassGen: Test Connection"
3. Should see success message
```

### Test Chat (Basic)

```bash
# In Extension Development Host
1. Run "MassGen: Start Chat"
2. Type: "Hello, test message"
3. Press Enter or click Send
4. Check Output panel for logs
```

### Test Code Analysis

```bash
# In Extension Development Host
1. Open any code file
2. Select some code
3. Right-click → "MassGen: Analyze Code Selection"
4. Chat panel should open with analysis query
```

## 🚢 Deployment

### Publishing to VSCode Marketplace

```bash
cd vscode-extension

# 1. Update version in package.json
# 2. Compile and test
npm run compile

# 3. Package
vsce package

# 4. Publish (requires publisher account)
vsce publish
```

### Installing Locally

```bash
# Build .vsix file
vsce package

# Install in VSCode
code --install-extension massgen-vscode-X.X.X.vsix
```

## 🤝 Contributing

Contributions welcome! Main development branch: `feature/vscode-plugin`

### Development Workflow

1. **Branch**: `git checkout feature/vscode-plugin`
2. **Install**: `cd vscode-extension && npm install`
3. **Develop**: Make changes
4. **Compile**: `npm run compile`
5. **Test**: Press `F5` in VSCode
6. **Commit**: Follow conventional commits

---

**Current Status**: ✅ Basic architecture complete, core communication working

**Next Milestone**: Full query execution and event streaming
