# Docker Credential Management Examples

This directory contains practical examples for using Docker code execution with credential management, dependency installation, and environment setup.

## Quick Start

All examples require:
1. **Docker daemon running**
2. **MassGen Docker image built**: `bash massgen/docker/build.sh`
   - For sudo examples: `bash massgen/docker/build.sh --sudo`

## Examples Overview

### 1. GitHub CLI Authentication (`docker_github_cli_auth.yaml`)

Test GitHub CLI with token authentication.

**Setup**:
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_github_cli_auth.yaml
```

**What it does**: Runs `gh auth status` and `gh api user` to verify GitHub CLI authentication.

---

### 2. Pre-Install Packages (`docker_preinstall_packages.yaml`)

Install base packages that are always available in containers.

**Setup**: Build with sudo support
```bash
bash massgen/docker/build.sh --sudo
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_preinstall_packages.yaml
```

**What it does**: Pre-installs Python (requests, numpy, pytest), npm (typescript), and system packages (curl, vim), then verifies they're available.

**Key feature**: Packages install BEFORE workspace scanning, giving you a consistent base environment.

---

### 3. Private Repository Clone (`docker_private_repo_clone.yaml`)

Clone private GitHub repos using SSH keys.

**Setup**:
```bash
# Ensure SSH keys exist and have correct permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa

# Add SSH key to GitHub account (if not already done)
# https://github.com/settings/keys
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_private_repo_clone.yaml
```

**What it does**: Mounts your SSH keys and git config, tests SSH connection, attempts to clone a private repo.

**Note**: Edit the config to replace `yourorg/private-repo` with a real private repo you have access to.

---

### 4. Auto-Dependency Installation (`docker_autodeps_install.yaml`)

Automatically detect and install dependencies from `requirements.txt`, `package.json`, etc.

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_autodeps_install.yaml
```

**What it does**: Agent creates dependency files, auto-install detects and installs them, then verifies installation.

**Key feature**: Dependencies in workspace are automatically detected and installed on container creation.

---

### 5. Environment File (.env) (`docker_env_file.yaml`)

Pass credentials via .env file (recommended for multiple secrets).

**Setup**:
```bash
cat > .env <<EOF
GITHUB_TOKEN=ghp_your_token
ANTHROPIC_API_KEY=sk-ant-your_key
CUSTOM_VAR=test_value
EOF
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_env_file.yaml
```

**What it does**: Loads environment variables from .env file and verifies they're available in the container.

**Best practice**: Use .env files for managing multiple credentials. Add `.env` to `.gitignore`.

---

### 6. Full Development Setup (`docker_full_dev_setup.yaml`)

Comprehensive example combining all features - use this as a production template.

**Setup**:
```bash
# Build with sudo
bash massgen/docker/build.sh --sudo

# Create .env file
echo "GITHUB_TOKEN=ghp_your_token" > .env

# Ensure SSH keys and git config exist
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_full_dev_setup.yaml
```

**What it does**: Combines GitHub CLI, pre-install packages, auto-dependencies, SSH keys, git config, and .env file into a complete development environment.

**Features**:
- GitHub CLI authentication
- Pre-installed base packages (pytest, requests, numpy, typescript)
- Auto-dependency detection and installation
- SSH keys for private repos
- Git config for commits
- Resource limits (4GB RAM, 2 CPUs)

---

### 7. Custom Docker Image (`docker_custom_image.yaml`)

Use your own Docker image with custom tools and libraries.

**Setup**:
```bash
# Create Dockerfile.custom
cat > Dockerfile.custom <<EOF
FROM massgen/mcp-runtime:latest
RUN pip install --no-cache-dir tensorflow scikit-learn jupyter
RUN apt-get update && apt-get install -y vim htop && rm -rf /var/lib/apt/lists/*
EOF

# Build your custom image
docker build -t my-massgen-ml:v1 -f Dockerfile.custom .
```

**Run**:
```bash
uv run massgen massgen/configs/tools/code-execution/docker_custom_image.yaml
```

**What it does**: Uses your custom Docker image instead of the default MassGen image.

**When to use**: When you need the same packages across all runs, or have complex system dependencies.

---

## Common Patterns

### Pattern 1: GitHub Development
Combine GitHub CLI + SSH keys + git config:
```yaml
command_line_docker_network_mode: "bridge"
command_line_docker_pass_env_vars: ["GITHUB_TOKEN"]
command_line_docker_mount_ssh_keys: true
command_line_docker_mount_git_config: true
```

### Pattern 2: Private Package Development
For npm/PyPI private packages:
```yaml
command_line_docker_network_mode: "bridge"
command_line_docker_mount_npm_config: true
command_line_docker_mount_pypi_config: true
command_line_docker_pass_env_vars: ["NPM_TOKEN"]
```

### Pattern 3: Consistent Environment
Pre-install + auto-detect:
```yaml
command_line_docker_preinstall_python: ["pytest", "requests"]
command_line_docker_auto_install_deps: true
```

### Pattern 4: Multiple Secrets
Use .env file:
```yaml
command_line_docker_env_file_path: ".env"
```

## Troubleshooting

### SSH Keys Not Working
```bash
# Check permissions
ls -la ~/.ssh/
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa

# Test SSH connection
ssh -T git@github.com
```

### GitHub CLI Not Authenticating
```bash
# Check token is set
echo $GITHUB_TOKEN

# Verify token has correct scopes (repo, workflow)
```

### Dependencies Not Installing
```bash
# Check logs in .massgen/massgen_logs/
# Look for installation errors

# Try manual install in container
docker exec -it massgen-agent_a /bin/bash
pip install <package>
```

### Custom Image Not Found
```bash
# Verify image exists
docker images | grep my-massgen

# Build if needed
docker build -t my-massgen-ml:v1 .
```

## Security Best Practices

1. **Use .env files** for credentials, never hardcode in configs
2. **Add .env to .gitignore** to prevent committing secrets
3. **Use read-only mounts** for credential files (default behavior)
4. **Enable only needed credentials** - opt-in by default
5. **Use network isolation** (`network_mode: none`) unless network is required
6. **Review logs** for any credential leakage before sharing

## Documentation

For complete documentation, see:
- User Guide: `docs/source/user_guide/docker_authentication.rst`
- Design Doc: `docs/dev_notes/CODE_EXECUTION_DESIGN.md`
- PR Draft: `PR_DRAFT_436.md`

## Feature Summary

| Feature | Config Parameter | Example |
|---------|-----------------|---------|
| GitHub CLI | `pass_env_vars: ["GITHUB_TOKEN"]` | docker_github_cli_auth.yaml |
| SSH Keys | `mount_ssh_keys: true` | docker_private_repo_clone.yaml |
| Git Config | `mount_git_config: true` | docker_private_repo_clone.yaml |
| .env File | `env_file_path: ".env"` | docker_env_file.yaml |
| Pre-install | `preinstall_python: [...]` | docker_preinstall_packages.yaml |
| Auto-deps | `auto_install_deps: true` | docker_autodeps_install.yaml |
| Custom Image | `docker_image: "your-image"` | docker_custom_image.yaml |
| Full Setup | (all combined) | docker_full_dev_setup.yaml |
