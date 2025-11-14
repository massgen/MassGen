# Computer Use Agent Visualization Guide

This guide explains how to visualize the behavior of Claude Computer Use and Gemini Computer Use agents in real-time.

## Table of Contents
1. [Docker/Linux Agent (Claude) - VNC Viewer](#docker-vnc-viewer)
2. [Browser Agent (Gemini) - Non-Headless Mode](#browser-non-headless)
3. [Screenshot Logging](#screenshot-logging)
4. [Terminal Output Monitoring](#terminal-monitoring)
5. [Comparison Table](#comparison)

---

## 1. Docker/Linux Agent (Claude) - VNC Viewer

### Quick Setup
```bash
# 1. Enable VNC on the Docker container
./scripts/enable_vnc_viewer.sh

# 2. Install a VNC viewer (one-time setup)
# Ubuntu/Debian:
sudo apt-get install tigervnc-viewer
# Or:
sudo snap install remmina

# 3. Connect to the container
# Get container IP:
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cua-container
# Connect with: <container-ip>:5900
```

### Detailed Steps

#### Option A: Direct VNC Connection (Local Machine)
```bash
# 1. Start VNC server in container
./scripts/enable_vnc_viewer.sh cua-container

# 2. Get container IP
CONTAINER_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cua-container)
echo "Container IP: $CONTAINER_IP"

# 3. Connect with VNC viewer
vncviewer $CONTAINER_IP:5900
# or
remmina -c vnc://$CONTAINER_IP:5900
```

#### Option B: Port Forwarding (Remote Machine)
```bash
# On remote server:
./scripts/enable_vnc_viewer.sh cua-container
docker port-forward cua-container 5900:5900

# From local machine:
ssh -L 5900:localhost:5900 user@remote-server
# Then connect VNC viewer to localhost:5900
```

#### Option C: Docker Port Mapping (Recommended)
```bash
# Recreate container with port mapping
docker stop cua-container
docker rm cua-container

# Run with VNC port exposed
docker run -d --name cua-container -p 5900:5900 cua-ubuntu

# Start VNC inside
docker exec -d cua-container x11vnc -display :99 -forever -shared -rfbport 5900 -nopw

# Connect to localhost:5900
vncviewer localhost:5900
```

### What You'll See
- Real-time desktop with Xfce window manager
- Mouse movements and clicks as the agent executes actions
- Terminal windows opening for bash commands
- Applications launching (Firefox, text editors, etc.)
- File browser operations
- All desktop interactions in real-time

---

## 2. Browser Agent (Gemini/Claude) - Non-Headless Mode

For Gemini and Claude browser automation, you can watch the browser by disabling headless mode.

### Update Configuration

Edit your YAML config to use `preset_args` (not `default_params`):
```yaml
# For Gemini Computer Use
custom_tools:
  - name: ["gemini_computer_use"]
    category: "automation"
    path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
    function: ["gemini_computer_use"]
    preset_args:
      environment: "browser"
      display_width: 1440
      display_height: 900
      max_iterations: 25
      include_thoughts: true
      environment_config:
        headless: false  # Set to false for visible browser
        browser_type: "chromium"  # chromium, firefox, or webkit

# For Claude Computer Use (browser mode)
custom_tools:
  - name: ["claude_computer_use"]
    category: "automation"
    path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
    function: ["claude_computer_use"]
    preset_args:
      environment: "browser"
      headless: false  # Set to false for visible browser
```

### Running with Visible Browser

**Important**: You must set the `DISPLAY` environment variable when running:

```bash
# Check your available displays
ls /tmp/.X11-unix/
# Shows: X0, X20, etc.

# Run MassGen with DISPLAY variable (example using :20)
DISPLAY=:20 massgen --config massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml

# For Claude browser
DISPLAY=:20 massgen --config massgen/configs/tools/custom_tools/claude_computer_use_browser_example.yaml

# Or for multi-agent
DISPLAY=:20 massgen --config massgen/configs/tools/custom_tools/multi_agent_computer_use_example.yaml
```

### What You'll See
- Actual browser window opens on your desktop
- For Claude: Browser opens with Google homepage loaded
- For Gemini: Browser opens at specified URL or blank page
- Pages loading and navigation
- Form filling and clicking in real-time
- Scrolling and text entry
- Mouse movements and interactions
- Full browser automation visible in real-time

### Requirements
- X11 display server running (check with `echo $DISPLAY`)
- Desktop environment (GUI) or X server available
- DISPLAY environment variable set (e.g., `:0`, `:20`)
- Cannot run on headless servers without X forwarding or Xvfb

### X11 Forwarding (For Remote Servers)
```bash
# On remote server with X11 forwarding:
ssh -X user@remote-server

# Verify DISPLAY is set:
echo $DISPLAY
# Should show something like: localhost:10.0

# Run with DISPLAY and headless: false
DISPLAY=$DISPLAY massgen --config config.yaml
```

### Using Xvfb (Virtual Display on Headless Servers)
```bash
# Install Xvfb
sudo apt-get install xvfb

# Start virtual display
Xvfb :20 -screen 0 1440x900x24 &

# Run with visible browser on virtual display
DISPLAY=:20 massgen --config config.yaml

# To see it, use VNC or x11vnc
x11vnc -display :20 -forever -shared -rfbport 5900 -nopw &
vncviewer localhost:5900
```

---

## 3. Screenshot Logging

Both agents capture screenshots during execution. You can save these for analysis.

### Enable Screenshot Saving

Create a custom tool wrapper:

```python
# massgen/tool/_computer_use/computer_use_with_screenshots.py
import os
from datetime import datetime
from pathlib import Path

async def claude_computer_use_with_logging(query: str, **kwargs):
    """Wrapper that saves screenshots during execution."""

    # Create screenshots directory
    log_dir = Path("computer_use_logs") / datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Original function with logging
    from massgen.tool._claude_computer_use import claude_computer_use

    # You can modify the tool to save screenshots
    result = await claude_computer_use(query, **kwargs)

    return result
```

### View Logs
```bash
# MassGen logs are in:
ls massgen_logs/

# Each log directory contains:
# - agent_chat.log (conversation)
# - tool_calls.log (tool invocations)
# - errors.log (if any errors)
```

---

## 4. Terminal Output Monitoring

### Real-time Logs
```bash
# Watch MassGen logs in real-time
tail -f massgen_logs/log_*/agent_chat.log

# Watch Claude tool execution
tail -f massgen_logs/log_*/tool_calls.log

# In another terminal, run your agent:
uv run python3 -m massgen.cli --config multi_agent_computer_use_example.yaml
```

### Verbose Mode
```bash
# Enable debug logging
export MASSGEN_LOG_LEVEL=DEBUG
uv run python3 -m massgen.cli --config config.yaml
```

### What You'll See
```
[2025-11-08 10:30:45] Starting Claude Computer Use with query: Search for Python docs
[2025-11-08 10:30:45] Environment: linux, Display: 1024x768, Max iterations: 30
[2025-11-08 10:30:46] === Iteration 1/30 ===
[2025-11-08 10:30:46] Claude response stop_reason: tool_use
[2025-11-08 10:30:46]   -> Executing Claude tool: computer
[2025-11-08 10:30:46]      Screenshot captured
[2025-11-08 10:30:48] === Iteration 2/30 ===
[2025-11-08 10:30:48]   -> Executing Claude tool: computer
[2025-11-08 10:30:48]      Left click at (640, 100)
...
```

---

## 5. Comparison Table

| Visualization Method | Claude Docker | Claude Browser | Gemini Browser | Setup Difficulty | Real-time | Best For |
|---------------------|---------------|----------------|----------------|------------------|-----------|----------|
| **VNC Viewer** | ✅ Yes | ❌ No | ❌ No | Medium | ✅ Yes | Watching desktop automation |
| **Non-Headless Browser** | ❌ No | ✅ Yes | ✅ Yes | Easy | ✅ Yes | Watching web automation |
| **Screenshot Logs** | ✅ Yes | ✅ Yes | ✅ Yes | Easy | ❌ No | Post-execution analysis |
| **Terminal Logs** | ✅ Yes | ✅ Yes | ✅ Yes | Very Easy | ✅ Yes | Understanding agent decisions |
| **X11 Forwarding** | ✅ Yes | ✅ Yes | ✅ Yes | Hard | ✅ Yes | Remote server visualization |

---

## Quick Start Commands

### For Multi-Agent Visualization (Both Agents)

#### Terminal 1: Enable VNC for Claude
```bash
./scripts/enable_vnc_viewer.sh cua-container
vncviewer $(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cua-container):5900
```

#### Terminal 2: Verify DISPLAY for Gemini Browser
```bash
# Check available displays
ls /tmp/.X11-unix/
# Example output: X0  X20

# Check your current DISPLAY
echo $DISPLAY
# Example: :0 or :20

# If no DISPLAY, you can use Xvfb (virtual display)
Xvfb :20 -screen 0 1440x900x24 &
export DISPLAY=:20
```

#### Terminal 3: Update Config for Visible Gemini Browser
```bash
# Edit multi_agent_computer_use_example.yaml
# Ensure Gemini's configuration uses:
#   preset_args:
#     environment_config:
#       headless: false
```

#### Terminal 4: Run Agents with Logging
```bash
export MASSGEN_LOG_LEVEL=DEBUG
# IMPORTANT: Set DISPLAY environment variable
DISPLAY=:20 uv run python3 -m massgen.cli --config massgen/configs/tools/custom_tools/multi_agent_computer_use_example.yaml
```

#### Terminal 5: Watch Logs
```bash
tail -f .massgen/massgen_logs/log_*/turn_*/massgen.log
```

Now you can see:
- **VNC window** showing Claude's desktop actions in Docker
- **Browser window** showing Gemini's web automation on your display
- **Terminal logs** showing agent reasoning and tool calls
- **Real-time coordination** between agents

---

## Troubleshooting

### Common Configuration Mistake

**Issue**: Browser always runs in headless mode even with `headless: false`

**Solution**: MassGen's custom tools use `preset_args`, NOT `default_params`:

```yaml
# ❌ WRONG - Will not work
custom_tools:
  - name: ["gemini_computer_use"]
    default_params:
      environment_config:
        headless: false

# ✅ CORRECT - Use preset_args
custom_tools:
  - name: ["gemini_computer_use"]
    preset_args:
      environment: "browser"
      display_width: 1440
      display_height: 900
      environment_config:
        headless: false
        browser_type: "chromium"
```

### VNC Issues
```bash
# Check if VNC is running
docker exec cua-container ps aux | grep x11vnc

# Restart VNC
docker exec cua-container pkill x11vnc
./scripts/enable_vnc_viewer.sh

# Check firewall
sudo ufw allow 5900/tcp
```

### Browser Not Showing
```bash
# 1. Check DISPLAY variable is set
echo $DISPLAY
# Should show something like: :0 or :20

# 2. List available displays
ls /tmp/.X11-unix/
# Shows: X0, X20, etc.

# 3. Test with simple X app
DISPLAY=:20 xeyes  # Should open a window

# 4. If no DISPLAY, create virtual display
Xvfb :20 -screen 0 1440x900x24 &
export DISPLAY=:20

# 5. Verify Playwright can launch browser
python3 -c "
from playwright.sync_api import sync_playwright
import os
print(f'DISPLAY={os.environ.get(\"DISPLAY\")}')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    print('Browser launched successfully!')
    browser.close()
"

# 6. Check config uses preset_args (not default_params)
grep -A5 "preset_args" your_config.yaml

# 7. Ensure headless: false in environment_config
grep "headless" your_config.yaml

# If on remote server
ssh -X user@server  # With X forwarding
```

### Performance Issues
- VNC can be slow over network - use lower resolution
- Headless mode is much faster if visualization not needed
- Consider recording with `scrot` screenshots instead of live VNC

---

## Advanced: Recording Sessions

### Record VNC Session
```bash
# Install ffmpeg
sudo apt-get install ffmpeg vnc2flv

# Record VNC
vnc2flv -o output.flv localhost:5900

# Convert to MP4
ffmpeg -i output.flv -c:v libx264 computer_use_session.mp4
```

### Record Browser (Non-Headless)
```bash
# Use OBS Studio or SimpleScreenRecorder
sudo apt-get install simplescreenrecorder
# Record the browser window area
```

---

## Best Practices

1. **Development**: Use VNC + non-headless browser for debugging
2. **Testing**: Use terminal logs with occasional screenshots
3. **Production**: Use headless mode with comprehensive logging
4. **Demos**: Record sessions with VNC/browser recording
5. **Remote Work**: Use X11 forwarding or VNC over SSH tunnel

---

## See Also
- [Computer Use Tools Guide](../massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md)
- [MassGen Documentation](../README.md)
