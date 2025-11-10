# Docker Credential Examples - Quick Start Commands

Copy and paste these commands to exercise the Docker credential features that ship with MassGen. All other scenarios can be reproduced by editing the full template.

## Prerequisites

```bash
# Build the Docker image (one-time setup)
bash massgen/docker/build.sh

# For sudo-enabled runs (required by the full template)
bash massgen/docker/build.sh --sudo
```

## Example Commands

### 1. Full Development Setup ⭐ RECOMMENDED START

Comprehensive workflow with credential mounts, .env loading, and package preinstalls.

```bash
# Setup
bash massgen/docker/build.sh --sudo
echo "GITHUB_TOKEN=ghp_your_token" > .env

# Run everything at once
uv run massgen --config massgen/configs/tools/code-execution/docker_full_dev_setup.yaml \
  "Demonstrate full dev environment: check gh auth, verify pre-installed packages, create Flask app with requirements.txt, show git config"
```

**Customize it**:
- Remove `command_line_docker_packages.preinstall` to skip preinstalled packages.
- Drop entries from `command_line_docker_credentials.mount` if you do not need SSH or git config.
- Delete `env_file: ".env"` if you prefer to export tokens directly before launching MassGen.
- Add `auto_install_deps: true` under `command_line_docker_packages` if you explicitly want automatic installs (see note below).

The template is designed so you can comment out or delete the sections you do not need and keep a single source of truth.

---

### 2. GitHub Read-Only ⭐ EXISTING WORKFLOW

Safe mode that mounts credentials but blocks push/create/merge commands.

```bash
uv run massgen --config massgen/configs/tools/code-execution/docker_github_readonly.yaml \
  "Clone the MassGen repo, inspect recent commits, and summarize changes"
```

Use this when you want assurance that the agent cannot mutate your repositories.

---

### 3. Custom Docker Image ⭐ BRING YOUR OWN ENV

Point MassGen at a prebuilt image with your preferred tooling.

```bash
# Example custom image build
cat > Dockerfile.custom <<'EOF'
FROM massgen/mcp-runtime:latest
RUN pip install --no-cache-dir tensorflow scikit-learn jupyter
RUN apt-get update && apt-get install -y vim htop && rm -rf /var/lib/apt/lists/*
EOF

docker build -t my-massgen-ml:v1 -f Dockerfile.custom .

# Run with the custom image
uv run massgen --config massgen/configs/tools/code-execution/docker_custom_image.yaml \
  "Verify custom image packages: check for tensorflow, scikit-learn, jupyter, vim, and htop"
```

Adjust the Dockerfile to bake in whatever tools your teams rely on.

---

## Re-creating Other Scenarios

The previous individual configs (token-based gh auth, SSH-only, .env, etc.) can all be expressed by trimming the `docker_full_dev_setup.yaml` template. A few common toggles:

```yaml
command_line_docker_credentials:
  env_file: ".env"        # load .env, remove line to skip
  env_vars:
    - "GITHUB_TOKEN"      # pass selected env vars directly
  mount:
    - "ssh_keys"          # comment out to avoid mounting
    - "git_config"

command_line_docker_packages:
  preinstall:
    python:
      - "pytest"
```

Use these snippets to tailor the full template for lightweight runs without needing separate files.

## Troubleshooting

### Docker daemon not running
```bash
# macOS
open -a Docker

# Linux
sudo systemctl start docker
```

### Docker image not found
```bash
# Build the base image
bash massgen/docker/build.sh

# Or with sudo support
bash massgen/docker/build.sh --sudo

# Verify images exist
docker images | grep massgen
```

### GitHub token not working
```bash
# Check token is set
echo $GITHUB_TOKEN

# Re-export if needed
export GITHUB_TOKEN=ghp_your_token_here
```

### Permission denied for SSH
```bash
# Fix SSH key permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub
```

---
