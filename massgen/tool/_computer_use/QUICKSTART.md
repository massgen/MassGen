# Computer Use Tool - Quick Start Guide

Get started with computer automation in 5 minutes!

## Prerequisites

1. Python 3.8 or higher
2. OpenAI API key
3. Choose your environment:
   - **Browser**: Playwright (easier, recommended for beginners)
   - **Desktop**: Docker (for OS-level tasks)

## Step 1: Install Dependencies

### For Browser Automation (Recommended)

```bash
# Install Playwright
pip install playwright python-dotenv openai

# Install browser binaries
playwright install
```

### For Docker Environment (Advanced)

```bash
# Install Docker from https://www.docker.com
# Then install Python dependencies
pip install python-dotenv openai
```

## Step 2: Set Up API Key

Create a `.env` file in your MassGen root directory:

```bash
echo "OPENAI_API_KEY=sk-your-api-key-here" > .env
```

Or set as environment variable:

```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

## Step 3: Run Your First Task

### Option A: Using the Command Line

```bash
# Browser automation example
massgen --config massgen/configs/tools/custom_tools/computer_use_browser_example.yaml "Search for Python tutorials on Google"
```

### Option B: Using Python

Create a file `test_computer_use.py`:

```python
import asyncio
from massgen.tool._computer_use import computer_use

async def main():
    result = await computer_use(
        task="Go to Google and search for 'Python tutorials'",
        environment="browser",
        display_width=1280,
        display_height=720,
        max_iterations=20,
        include_reasoning=True
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python test_computer_use.py
```

## Step 4: Try More Examples

### Example 1: Simple Web Search

```python
result = await computer_use(
    task="Search for 'OpenAI' on Bing",
    environment="browser"
)
```

### Example 2: Navigate to a Website

```python
result = await computer_use(
    task="Go to example.com and click the 'More information' link",
    environment="browser",
    max_iterations=15
)
```

### Example 3: Extract Information

```python
result = await computer_use(
    task="Go to Python.org and find the latest Python version number",
    environment="browser",
    include_reasoning=True
)
```

## Docker Setup (Optional)

If you want to use Docker for OS-level automation:

### 1. Create Dockerfile

Save this as `Dockerfile` in a new directory:

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    xfce4 x11vnc xvfb xdotool imagemagick \
    firefox-esr sudo \
 && apt-get clean

RUN useradd -ms /bin/bash myuser \
    && echo "myuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER myuser
WORKDIR /home/myuser

RUN x11vnc -storepasswd secret /home/myuser/.vncpass

EXPOSE 5900
CMD ["/bin/sh", "-c", " \
    Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 & \
    x11vnc -display :99 -forever -rfbauth /home/myuser/.vncpass -listen 0.0.0.0 -rfbport 5900 >/dev/null 2>&1 & \
    export DISPLAY=:99 && startxfce4 >/dev/null 2>&1 & \
    sleep 2 && tail -f /dev/null"]
```

### 2. Build and Run

```bash
# Build
docker build -t cua-image .

# Run
docker run --rm -d --name cua-container -p 5900:5900 -e DISPLAY=:99 cua-image
```

### 3. Test Docker Environment

```python
result = await computer_use(
    task="Open Firefox and go to example.com",
    environment="ubuntu",
    environment_config={
        "container_name": "cua-container",
        "display": ":99"
    }
)
```

### 4. View with VNC (Optional)

To see what's happening visually:

```bash
# Install VNC viewer, then connect to:
# localhost:5900
# Password: secret
```

## Common Issues

### Issue: "playwright not found"

**Solution:**
```bash
pip install playwright
playwright install
```

### Issue: "OpenAI API key not found"

**Solution:**
Create `.env` file with:
```
OPENAI_API_KEY=sk-...
```

### Issue: "Docker container not running"

**Solution:**
```bash
docker ps  # Check status
docker start cua-container  # If stopped
```

### Issue: "Task doesn't complete"

**Solutions:**
- Increase `max_iterations` (try 30-50 for complex tasks)
- Make task description more specific
- Check if website loaded (try simpler sites first)
- Enable `include_reasoning=True` to see what the AI is thinking

## Tips for Success

1. **Start Simple**: Begin with basic tasks like "Go to Google"
2. **Be Specific**: "Click the search button" is better than "search"
3. **Wait for Loading**: Complex pages may need higher iteration counts
4. **Check Reasoning**: Enable reasoning to understand AI decisions
5. **Iterate**: Refine your task descriptions based on results

## Next Steps

- Read the full [README.md](./README.md) for detailed documentation
- Explore example configurations in `massgen/configs/tools/custom_tools/`
- Check out [OpenAI's Computer Use Guide](https://platform.openai.com/docs/guides/tools-computer-use)
- Experiment with different environments and tasks

## Example Use Cases

- **Web Scraping**: "Go to news site and extract headlines"
- **Form Filling**: "Fill out contact form with test data"
- **Research**: "Search for information about X and summarize"
- **Testing**: "Navigate through app workflow and verify elements"
- **Automation**: "Download file from website"

## Getting Help

1. Check error messages in the returned result
2. Enable `include_reasoning=True` for insights
3. Review screenshots (returned as ImageContent)
4. Check logs for action history
5. Consult the main README.md

Happy automating! 🚀
