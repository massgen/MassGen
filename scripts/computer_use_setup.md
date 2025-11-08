# Setup Scripts

## Docker Computer Use Setup

To use the Docker-based computer use environment:

```bash
# Run the setup script
./scripts/setup_docker_cua.sh
```

This will:
1. Create a Dockerfile with Ubuntu 22.04 + desktop environment
2. Build the Docker image named `cua-ubuntu`
3. Start a container named `cua-container`
4. Test the X11 display is working

After setup, you can use the Docker example:

```bash
uv run python3 -m massgen.cli \
  --config massgen/configs/tools/custom_tools/computer_use_docker_example.yaml
```

## Browser-Based Computer Use (Recommended)

For browser automation (easier setup):

```bash
# Install Playwright
pip install playwright
playwright install chromium

# Use browser example
uv run python3 -m massgen.cli \
  --config massgen/configs/tools/custom_tools/computer_use_browser_example.yaml
```

## Troubleshooting

### Docker container not found
Run the setup script: `./scripts/setup_docker_cua.sh`

### Container exists but not working
```bash
# Restart container
docker restart cua-container

# Check logs
docker logs cua-container

# Test X11
docker exec -e DISPLAY=:99 cua-container xdotool getmouselocation
```

### Playwright not installed
```bash
pip install playwright
playwright install
```
