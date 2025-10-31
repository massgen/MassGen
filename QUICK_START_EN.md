# MassGen VSCode Plugin Quick Start Guide

## 🎯 Try the Plugin Now

### Method 1: Development Mode Testing (Easiest)

#### 1. Open the Plugin Project

```bash
cd vscode-extension
code .
```

#### 2. Launch the Plugin (Press F5)

In VSCode:
- Press **F5**
- Or click menu: **Run → Start Debugging**
- A new VSCode window will open automatically (with title `[Extension Development Host]`)

#### 3. Test Features

**In the newly opened window:**

##### ✅ Test 1: Check Connection

```
1. Press Cmd+Shift+P (Mac) or Ctrl+Shift+P (Windows/Linux)
2. Type: MassGen: Test Connection
3. Click to execute
4. You should see: ✅ MassGen connection successful!
```

<img src="https://via.placeholder.com/800x100/4CAF50/FFFFFF?text=✅+MassGen+connection+successful!" alt="Success" width="400"/>

##### 💬 Test 2: Open Chat Interface

```
1. Press Cmd+Shift+P (Mac) or Ctrl+Shift+P (Windows/Linux)
2. Type: MassGen: Start Chat
3. Click to execute
4. A chat panel will open on the right side
```

**Chat Interface Preview:**
```
┌──────────────────────────────────────┐
│ 🚀 MassGen - Multi-Agent AI Assistant│
├──────────────────────────────────────┤
│ Ready                                 │
├──────────────────────────────────────┤
│                                       │
│  ┌────────────────────────────────┐  │
│  │ MassGen                        │  │
│  │ Welcome! I'm MassGen, a        │  │
│  │ multi-agent AI system...       │  │
│  └────────────────────────────────┘  │
│                                       │
├──────────────────────────────────────┤
│ Ask anything...                       │
│ [                              ] Send │
└──────────────────────────────────────┘
```

Type in the input box: **"Hello, test message"**, then press Enter.

##### 🔍 Test 3: Code Analysis

```
1. Open any code file in the Extension Development Host window
2. Select a piece of code
3. Right-click → Select "MassGen: Analyze Code Selection"
4. The chat panel will open automatically and send an analysis request
```

##### 📊 View Logs

```
1. Click menu: View → Output
2. Select "MassGen" from the dropdown
3. You can see all communication logs
```

Example logs:
```
2025-10-18 22:53:37 [INFO] MassGen server started successfully
2025-10-18 22:53:38 [DEBUG] Sent request: test_connection
2025-10-18 22:53:38 [INFO] ✅ Connection successful
```

#### 4. Check Status Bar

At the bottom of the window, you'll see:
```
💬 MassGen  (Click to quickly open chat)
```

---

### Method 2: Command Line Testing (Verify Python Backend)

In the project root directory:

```bash
# Test Python adapter
python test_vscode_adapter.py
```

**Expected output:**
```
Creating VSCode server...

=== Testing initialize ===
Initialize result: {
  "success": true,
  "version": "0.1.0",
  "capabilities": {
    "query": true,
    "configure": true,
    "analyze": true,
    "streaming": true
  }
}

=== Testing test_connection ===
Test connection result: {
  "success": true,
  "message": "Connection successful"
}

=== Testing list_configs ===
List configs result: {...}
Found 100+ configuration files
  - ag2_coder.yaml: ag2/ag2_coder.yaml
  - gemini_4o_claude.yaml: basic/multi/gemini_4o_claude.yaml
  - three_agents_default.yaml: basic/multi/three_agents_default.yaml

✅ All tests passed!
```

---

## 🎨 Interface Preview

### 1. Command Palette

When you press `Cmd+Shift+P`, you'll see:

```
> MassGen: Start Chat
> MassGen: Analyze Code Selection
> MassGen: Configure Agents
> MassGen: Test Connection
```

### 2. Chat Panel

The chat interface uses native VSCode styles and supports:
- ✅ Automatic dark/light theme adaptation
- ✅ Message bubble display
- ✅ Real-time status updates
- ✅ Scrollable message history

### 3. Context Menu

After selecting code, right-click:
```
Cut
Copy
Paste
-----------------
MassGen: Analyze Code Selection  ← New feature
-----------------
...
```

---

## 🔍 Debugging Tips

### View Communication Process

1. **Python-side logs:**
   In VSCode Output panel → Select "MassGen"

2. **TypeScript-side logs:**
   Help → Toggle Developer Tools → Console tab

3. **Webview logs:**
   In the chat panel, Help → Toggle Developer Tools

### Common Troubleshooting

#### ❌ Issue 1: Plugin Won't Start

**Error message:**
```
Failed to activate MassGen: ...
```

**Solution:**
```bash
# Check if Python and massgen are installed
python -m pip show massgen

# If not installed
pip install -e .
```

#### ❌ Issue 2: Connection Test Failed

**Solution:**
```bash
# First test the Python adapter
python test_vscode_adapter.py

# View detailed errors
# View → Output → MassGen
```

#### ❌ Issue 3: Chat Panel is Blank

**Solution:**
1. Open Developer Tools (Help → Toggle Developer Tools)
2. Check for errors in the Console
3. Verify that webview loaded successfully

---

## 📸 Complete Test Flow (5 Minutes)

### ⏱️ Minute 1: Launch Plugin

```bash
cd vscode-extension
code .
# Press F5
```

### ⏱️ Minute 2: Test Connection

```
Cmd+Shift+P → "MassGen: Test Connection"
✅ See success message
```

### ⏱️ Minute 3: Open Chat

```
Cmd+Shift+P → "MassGen: Start Chat"
✅ See chat panel
```

### ⏱️ Minute 4: Send Message

```
Type in chat: Hello
Press Enter
✅ See message displayed
```

### ⏱️ Minute 5: View Logs

```
View → Output → Select "MassGen"
✅ See communication logs
```

---

## 🎯 Current Feature Status

| Feature | Status | Test Method |
|---------|--------|-------------|
| Plugin Loading | ✅ Working | Press F5 to start |
| Python Communication | ✅ Working | Test Connection |
| Chat Interface | ✅ Working | Start Chat |
| Status Bar Icon | ✅ Working | Check bottom status bar |
| Code Analysis | ✅ Working | Right-click menu |
| List Configs | ✅ Working | Auto-load |
| **Actual Query** | ⚠️ Placeholder | Returns mock data |
| **Agent Streaming** | ⚠️ Partial | Event system ready |

---

## 💡 Next Steps

### Currently Available:
1. ✅ Interface fully functional
2. ✅ Communication mechanism working
3. ✅ All commands executable
4. ⚠️ Queries return placeholder data (needs Orchestrator integration)

### To Use Real Multi-Agent Features:

Orchestrator integration is needed (approx. 2-3 hours development). After integration:
- 🚀 Real multi-agent parallel execution
- 🚀 See each agent's thinking process in real-time
- 🚀 Voting and consensus visualization
- 🚀 Complete query results

---

## 📚 More Resources

- **Detailed Development Docs:** `VSCODE_PLUGIN_GUIDE.md`
- **Architecture Description:** See Architecture section in the above document
- **Issue Reporting:** Check logs and refer to Troubleshooting section

---

**Try it now! Press F5 to launch the plugin and see it in action!** 🚀

Feel free to ask if you have any questions!
