# How to Test the MassGen VSCode Plugin

## ✅ What's Been Implemented

I've successfully created a VSCode plugin for MassGen with the following architecture:

```
┌─────────────────────────────┐
│   VSCode Extension (TS)     │
│   - Chat Panel UI           │
│   - Commands                │
│   - Status Bar              │
└──────────┬──────────────────┘
           │ JSON-RPC (stdio)
┌──────────▼──────────────────┐
│   Python Adapter            │
│   - JSON-RPC Server         │
│   - Event Streaming         │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│   MassGen Core              │
│   - Orchestrator            │
│   - Multi-Agent System      │
└─────────────────────────────┘
```

## 🚀 Quick Test (5 minutes)

### Step 1: Test Python Adapter

```bash
# In the MassGen root directory
python test_vscode_adapter.py
```

**Expected output:**
```
Creating VSCode server...

=== Testing initialize ===
Initialize result: {
  "success": true,
  "version": "0.1.0",
  "capabilities": {...}
}

=== Testing test_connection ===
Test connection result: {
  "success": true,
  "message": "Connection successful"
}

=== Testing list_configs ===
Found 100+ configuration files

✅ All tests passed!
```

### Step 2: Test in VSCode

```bash
# Open the extension folder in VSCode
cd vscode-extension
code .
```

**In VSCode:**
1. Press `F5` to launch Extension Development Host
2. A new VSCode window will open
3. Open Command Palette (`Cmd+Shift+P` or `Ctrl+Shift+P`)
4. Type and run: `MassGen: Test Connection`
5. You should see: **"✅ MassGen connection successful!"**

### Step 3: Try the Chat Interface

**In the Extension Development Host window:**
1. Run command: `MassGen: Start Chat`
2. A chat panel will open on the right side
3. Type any message and press Enter
4. Check the **Output** panel (View → Output → select "MassGen")

## 📁 Project Structure

```
MassGen/
├── massgen/
│   └── vscode_adapter/          # ✨ NEW: Python adapter
│       ├── __init__.py
│       └── server.py            # JSON-RPC server
│
├── vscode-extension/            # ✨ NEW: VSCode extension
│   ├── src/
│   │   ├── extension.ts         # Main entry point
│   │   ├── massgenClient.ts     # Python communication
│   │   └── views/
│   │       └── chatPanel.ts     # Chat UI
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
│
├── test_vscode_adapter.py       # ✨ NEW: Test script
├── VSCODE_PLUGIN_GUIDE.md       # ✨ NEW: Full documentation
└── HOW_TO_TEST_VSCODE_PLUGIN.md # ✨ This file
```

## 🎯 Available Features

| Feature | Status | How to Test |
|---------|--------|-------------|
| **Python-VSCode Communication** | ✅ Working | Run `test_vscode_adapter.py` |
| **Test Connection** | ✅ Working | Command: `MassGen: Test Connection` |
| **Chat Panel UI** | ✅ Working | Command: `MassGen: Start Chat` |
| **List Configurations** | ✅ Working | Opens automatically in chat |
| **Code Analysis** | ✅ Implemented | Select code → Right-click → "Analyze" |
| **Query Execution** | ⚠️ Placeholder | Returns mock response |
| **Event Streaming** | ⚠️ Partial | Events sent but not from agents |

## 🔧 Current Limitations

1. **Query execution is not fully integrated**
   - Currently returns placeholder results
   - Need to integrate with Orchestrator's async execution

2. **No real-time agent streaming yet**
   - Events are sent but not from actual agents
   - Need to modify Orchestrator to emit events

3. **Configuration UI not implemented**
   - Can only use existing config files
   - GUI editor coming soon

## 📝 Next Steps to Make It Fully Functional

### Priority 1: Integrate with Orchestrator

**File to modify:** `massgen/vscode_adapter/server.py`

The `_handle_query` method needs full Orchestrator integration:

```python
async def _handle_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
    # Current: Returns placeholder
    # TODO:
    # 1. Create orchestrator instance
    # 2. Hook into orchestrator events
    # 3. Stream events to VSCode
    # 4. Return actual results
```

### Priority 2: Add Event Streaming

**File to modify:** `massgen/orchestrator.py`

Add event callback support:

```python
class Orchestrator:
    def on_event(self, callback):
        """Register event listener"""
        self.event_callbacks.append(callback)

    def _emit_event(self, event):
        """Send events to listeners"""
        for callback in self.event_callbacks:
            callback(event)
```

### Priority 3: Enhance UI

- Multi-agent parallel display
- Voting visualization
- Progress indicators

## 🧪 Manual Testing Checklist

- [x] Python adapter starts
- [x] JSON-RPC communication works
- [x] VSCode extension loads
- [x] Test connection succeeds
- [x] Chat panel opens
- [x] Can list configurations
- [ ] Query executes with real agents
- [ ] Agent outputs stream to UI
- [ ] Code analysis works end-to-end

## 🐛 Troubleshooting

### Extension Won't Activate

**Error:** "Failed to activate MassGen"

**Solution:**
```bash
# Check if Python has massgen installed
python -m pip show massgen

# Check Python path in VSCode settings
# Settings → MassGen → Python Path
```

### Connection Test Fails

**Error:** "Connection test failed"

**Solution:**
```bash
# Test Python adapter directly
python test_vscode_adapter.py

# Check Output panel for errors
# View → Output → MassGen
```

### Chat Panel Shows Errors

**Check:**
1. Output panel (View → Output → MassGen)
2. Browser developer tools (Help → Toggle Developer Tools)
3. Extension Host logs (Help → Toggle Developer Tools → Console)

## 📚 Documentation

- **Development Guide:** `VSCODE_PLUGIN_GUIDE.md` - Comprehensive developer documentation
- **Extension README:** `vscode-extension/README.md` - User-facing documentation
- **Architecture:** See diagrams in `VSCODE_PLUGIN_GUIDE.md`

## 🎉 What's Working Great

1. ✅ **Clean Architecture:** TypeScript ↔ Python communication via JSON-RPC
2. ✅ **Extensible:** Easy to add new commands and features
3. ✅ **Type-Safe:** Full TypeScript typing
4. ✅ **Professional UI:** Native VSCode Webview with proper styling
5. ✅ **Good Foundation:** Ready for full Orchestrator integration

## 🚢 How to Use in Production

Once fully implemented, users will:

1. **Install from Marketplace:**
   ```bash
   # Search "MassGen" in VSCode Extensions
   ```

2. **Configure API Keys:**
   - Set up `.env` file with API keys
   - Or use VSCode settings

3. **Start Chatting:**
   - Click MassGen icon in status bar
   - Type question
   - Watch multiple agents collaborate!

---

**Current Branch:** `feature/vscode-plugin`

**Commit:** Ready to merge or continue development

**Status:** ✅ **Phase 1 Complete** - Basic architecture working, ready for Orchestrator integration

For full implementation details, see `VSCODE_PLUGIN_GUIDE.md`
