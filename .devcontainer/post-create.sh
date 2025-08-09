#!/bin/bash

# MassGen Development Environment Setup Script
# This script runs after the devcontainer is created

set -e

echo "🚀 Setting up MassGen development environment..."

# Update package lists
sudo apt-get update

# Install uv (Python package manager)
echo "📦 Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Add uv to PATH for current session
export PATH="$HOME/.cargo/bin:$PATH"

# Install project dependencies with uv
echo "📦 Installing Python dependencies..."
uv sync

# Install Node.js first (required for npm packages)
echo "🔧 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Claude Code CLI
echo "🤖 Installing Claude Code CLI..."
sudo npm install -g @anthropic-ai/claude-code

# Install Gemini CLI
echo "💎 Installing Gemini CLI..."
sudo npm install -g @google/gemini-cli

# Create .env file from .env.example if it doesn't exist
echo "🔑 Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env file from .env.example"
    echo "📝 Please edit .env file with your actual API keys"
else
    echo "ℹ️  .env file already exists, skipping creation"
fi

# Install additional development tools
echo "🛠️  Installing additional development tools..."
uv tool install black
uv tool install isort
uv tool install flake8

# Make sure all tools are in PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

echo "✅ Development environment setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Test the installation: python -m massgen.cli --help"
echo "3. Run MassGen: python -m massgen.cli --config configs/single_gpt5nano.yaml"
echo ""
echo "Available tools:"
echo "- uv (Python package manager)"
echo "- claude (Claude Code CLI)"
echo "- gemini (Gemini CLI)"
echo "- Standard Python dev tools (black, isort, flake8)"