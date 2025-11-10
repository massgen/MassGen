# Docker Credential Management Examples

This directory now ships with three canonical configurations. Use them as-is or treat them as templates when tailoring Docker code execution for your own workflows.

| Config | Purpose | When to use it |
|--------|---------|----------------|
| `docker_full_dev_setup.yaml` | Comprehensive environment with credentials and preinstalls | Default starting point for real development work |
| `docker_github_readonly.yaml` | Read-only GitHub operations with command blocking | Safe exploration when you do not want push/create access |
| `docker_custom_image.yaml` | Bring your own Docker image | You maintain a bespoke runtime image |

All other scenarios (token-only auth, SSH without preinstalls, etc.) can be reproduced by trimming the full template rather than maintaining many near-duplicate config files.

## Prerequisites

1. Docker daemon running
2. MassGen Docker image built:
   ```bash
   bash massgen/docker/build.sh          # base image
   bash massgen/docker/build.sh --sudo   # required for sudo-enabled runs
   ```

## Config Details

### Full Development Setup (`docker_full_dev_setup.yaml`)

Everything enabled by default: `.env` loading, SSH/git mounts, and package preinstalls.

```bash
bash massgen/docker/build.sh --sudo
echo "GITHUB_TOKEN=ghp_your_token" > .env

uv run massgen --config massgen/configs/tools/code-execution/docker_full_dev_setup.yaml \
  "Demonstrate full dev environment: check gh auth, verify pre-installed packages, create Flask app with requirements.txt, show git config"
```

**Toggle features by editing the file:**

```yaml
command_line_docker_credentials:
  env_file: ".env"          # remove to skip .env loading
  env_vars:
    - "GITHUB_TOKEN"        # uncomment to pass select env vars directly
  mount:
    - "ssh_keys"            # drop entries you do not need
    - "git_config"

command_line_docker_packages:
  preinstall:               # delete block to skip base installs
    python:
      - "massgen"
    npm:
      - "typescript"
```

Keep this file in version control as your single source of truth, and adjust it per environment rather than relying on multiple standalone configs.

### GitHub Read-Only (`docker_github_readonly.yaml`)

Mounts the same credentials as the full template but blocks destructive commands (`git push`, `gh pr create`, etc.).

```bash
uv run massgen --config massgen/configs/tools/code-execution/docker_github_readonly.yaml \
  "Clone the MassGen repo, inspect recent commits, and summarize changes"
```

Use this when you want the agent to explore private repositories without any ability to mutate them.

### Custom Docker Image (`docker_custom_image.yaml`)

Points MassGen at a Docker image you manage.

```bash
cat > Dockerfile.custom <<'EOF'
FROM massgen/mcp-runtime:latest
RUN pip install --no-cache-dir tensorflow scikit-learn jupyter
RUN apt-get update && apt-get install -y vim htop && rm -rf /var/lib/apt/lists/*
EOF

docker build -t my-massgen-ml:v1 -f Dockerfile.custom .

uv run massgen --config massgen/configs/tools/code-execution/docker_custom_image.yaml \
  "Verify custom image packages: check for tensorflow, scikit-learn, jupyter, vim, and htop"
```

Swap in your own Dockerfile to bake shared tooling directly into the image.

## Re-creating Previous Scenarios

The deleted sample configs mapped one-to-one with sections of the full template. Use these snippets to replicate them without additional files:

- **Token-only GitHub auth:** comment out the `mount:` block and keep `env_vars: ["GITHUB_TOKEN"]`.
- **SSH + git config only:** drop `env_file`, keep `mount: ["ssh_keys", "git_config"]`.
- **.env only:** remove everything but `env_file: ".env"`.
- **No preinstalls:** remove the entire `preinstall` mapping or individual lists under it.

Because every knob is opt-in, removing a key from the YAML immediately disables that behavior.


## Troubleshooting & Tips

- **SSH permissions:** run `chmod 700 ~/.ssh` and `chmod 600 ~/.ssh/id_rsa` if mounts fail.
- **GitHub CLI scopes:** ensure `GITHUB_TOKEN` includes `repo` and `workflow` if you rely on token auth.
- **Custom images:** `docker images | grep massgen` confirms that your custom tag exists before launching.

## Additional Documentation

- User Guide: `docs/source/user_guide/docker_authentication.rst`
- Design Doc: `docs/dev_notes/CODE_EXECUTION_DESIGN.md`
- PR Draft: `PR_DRAFT_436.md`
