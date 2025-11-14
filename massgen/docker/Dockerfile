# MassGen MCP Runtime Environment
# Provides isolated execution environment for command execution with Docker isolation
# Base image: Python 3.11 slim for balance of features and size

FROM python:3.11-slim

# Metadata
LABEL maintainer="MassGen Team"
LABEL description="Isolated runtime environment for MassGen command execution"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
# - git: Version control operations
# - curl: HTTP operations and downloads
# - build-essential: Compiling Python packages with C extensions
# - ripgrep: Fast text search (REQUIRED for filesystem-first mode)
# - unzip: For extracting ast-grep binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    build-essential \
    ripgrep \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x (LTS) for JavaScript execution
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep for structural code search (filesystem-first mode)
# Using pip (avoids conflict with system 'sg' command that npm version creates)
RUN pip install --no-cache-dir ast-grep-cli

# Install openskills CLI for skills management
# Anthropic skills are installed manually beforehand and added as a volume at runtime
RUN npm install -g openskills

# Install semtools for semantic search (optional semtools skills)
RUN npm install -g @llamaindex/semtools

# Install GitHub CLI for authenticated git operations
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Install Python dependencies
# Core requirements: pytest for testing
# Common tools: requests, pandas, numpy for typical data science tasks
RUN pip install --no-cache-dir \
    'pytest>=7.0.0' \
    'requests>=2.31.0' \
    'numpy>=1.24.0' \
    'pandas>=2.0.0'

# Create workspace and context directories
# These will be mounted as volumes at runtime
RUN mkdir -p /workspace /context /temp_workspaces

# Set workspace as default working directory
WORKDIR /workspace

# Setup non-root user for security
# Commands run as this user to prevent privilege escalation
RUN useradd -m -u 1000 -s /bin/bash massgen && \
    chown -R massgen:massgen /workspace /context /temp_workspaces /app

# Switch to non-root user
USER massgen

# Install uv (modern Python package installer for optional serena skill)
# Enables uvx for running tools like serena on-demand without permanent installation
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/massgen/.local/bin:${PATH}"

# Default command: Keep container running (overridden at runtime)
CMD ["tail", "-f", "/dev/null"]
