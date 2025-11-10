# Docker Credential Examples - Quick Start Commands

Copy and paste these commands to test the new Docker credential features.

## Prerequisites

```bash
# Build the Docker image (one-time setup)
bash massgen/docker/build.sh

# For examples with sudo support
bash massgen/docker/build.sh --sudo
```

## Example Commands

### 1. GitHub CLI Authentication ⭐ START HERE

**Option A: Already logged in via `gh auth login`** (EASIEST - no token needed!)

```bash
# Check you're logged in
gh auth status

# Run - uses your existing authentication
uv run massgen massgen/configs/tools/code-execution/docker_github_cli_existing_auth.yaml \
  "Use gh CLI to check auth status and show my GitHub user info"
```

**Option B: Using GITHUB_TOKEN**

```bash
# Setup
export GITHUB_TOKEN=ghp_your_token_here

# Run
uv run massgen massgen/configs/tools/code-execution/docker_github_cli_auth.yaml \
  "Use gh CLI to check auth status and show my GitHub user info"
```

**Option C: Read-Only GitHub Access** (SAFE - blocks push, create, merge, delete)

```bash
# Check you're logged in
gh auth status

# Run - can read/clone but not write/push
uv run massgen massgen/configs/tools/code-execution/docker_github_readonly.yaml \
  "Clone the MassGen repo and examine recent commits"
```

**Recommendation**: Use Option A for full access, Option C for safe read-only browsing.

---

### 2. Pre-Install Packages ⭐ NEW FEATURE

Install base packages specified in YAML config.

```bash
# One-time: Build with sudo
bash massgen/docker/build.sh --sudo

# Run
uv run massgen massgen/configs/tools/code-execution/docker_preinstall_packages.yaml \
  "Verify pre-installed packages: check for requests, numpy, pytest (Python), typescript (npm), and curl/vim (system)"
```

**This config pre-installs**: requests, numpy, pytest, typescript, curl, vim

---

### 3. Private Repository Clone

Clone private repos using SSH keys.

```bash
# Ensure SSH keys have correct permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa

# Run
uv run massgen massgen/configs/tools/code-execution/docker_private_repo_clone.yaml \
  "Test SSH setup and clone a private repo if you have one"
```

**Note**: Edit the task to specify an actual private repo you have access to.

---

### 4. Auto-Dependency Installation ⭐ NEW FEATURE

Automatically detect and install from requirements.txt, package.json, etc.

```bash
uv run massgen massgen/configs/tools/code-execution/docker_autodeps_install.yaml \
  "Create requirements.txt with requests and flask, create package.json with express, then verify they install automatically"
```

---

### 5. Environment File (.env)

Pass multiple credentials via .env file.

```bash
# Create .env file
cat > .env <<EOF
GITHUB_TOKEN=ghp_your_token
ANTHROPIC_API_KEY=sk-ant-your_key
CUSTOM_VAR=test_value
EOF

# Run
uv run massgen massgen/configs/tools/code-execution/docker_env_file.yaml \
  "Check that environment variables from .env file are available (without printing secrets)"
```

---

### 6. Full Development Setup ⭐ RECOMMENDED

Complete development environment with all features.

```bash
# Setup
bash massgen/docker/build.sh --sudo
echo "GITHUB_TOKEN=ghp_your_token" > .env

# Run
uv run massgen massgen/configs/tools/code-execution/docker_full_dev_setup.yaml \
  "Demonstrate full dev environment: check gh auth, verify pre-installed pytest, create Flask app with requirements.txt, show git config"
```

**This is the best example to start with for real development work.**

Features included:
- GitHub CLI auth
- SSH keys + git config
- Pre-install: pytest, requests, numpy, typescript
- Auto-dependency detection
- Resource limits (4GB RAM, 2 CPUs)

---

### 7. Custom Docker Image ⭐ BYOI (Bring Your Own Image)

Use your own Docker image.

```bash
# Create custom Dockerfile
cat > Dockerfile.custom <<EOF
FROM massgen/mcp-runtime:latest
RUN pip install --no-cache-dir tensorflow scikit-learn jupyter
RUN apt-get update && apt-get install -y vim htop && rm -rf /var/lib/apt/lists/*
EOF

# Build custom image
docker build -t my-massgen-ml:v1 -f Dockerfile.custom .

# Run
uv run massgen massgen/configs/tools/code-execution/docker_custom_image.yaml \
  "Verify custom image packages: check for tensorflow, scikit-learn, jupyter, vim, and htop"
```

---

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

## What Each Example Demonstrates

| Example | New Features | Command |
|---------|-------------|---------|
| 1a. GitHub CLI (token) | Env var passing | `docker_github_cli_auth.yaml` |
| 1b. GitHub CLI (existing) | Mount gh_config | `docker_github_cli_existing_auth.yaml` |
| 1c. GitHub (read-only) | **Command filtering for safety** | `docker_github_readonly.yaml` |
| 2. Pre-Install | **Pre-install packages** | `docker_preinstall_packages.yaml` |
| 3. Private Repo | SSH keys, git config | `docker_private_repo_clone.yaml` |
| 4. Auto-Deps | **Auto-detect dependencies** | `docker_autodeps_install.yaml` |
| 5. Env File | .env file loading | `docker_env_file.yaml` |
| 6. Full Setup | All features combined | `docker_full_dev_setup.yaml` |
| 7. Custom Image | **Bring your own image** | `docker_custom_image.yaml` |

---

## Next Steps

1. **Start with #1 (GitHub CLI)** - simplest to verify Docker is working
2. **Try #2 (Pre-Install)** - see the new pre-install feature in action
3. **Try #6 (Full Dev Setup)** - comprehensive example for real work
4. **Read full docs** - see `DOCKER_CREDENTIALS_README.md` for details
