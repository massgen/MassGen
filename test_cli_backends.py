#!/usr/bin/env python3
"""
Test script for CLI backends - Claude Code CLI and Gemini CLI integration.

This script tests the basic functionality of CLI backends without requiring
the actual CLI tools to be installed (mocked for testing).
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from massgen.backend.claude_code_cli import ClaudeCodeCLIBackend
    from massgen.backend.gemini_cli import GeminiCLIBackend
    from massgen.backend.cli_base import CLIBackend
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


class MockCLIBackend(CLIBackend):
    """Mock CLI backend for testing purposes."""
    
    def __init__(self, cli_command: str, mock_output: str = "Mock response", **kwargs):
        self.mock_output = mock_output
        # Skip the actual CLI tool check
        self.cli_command = cli_command
        self.working_dir = kwargs.get("working_dir", Path.cwd())
        self.timeout = kwargs.get("timeout", 300)
        self.config = kwargs
        from massgen.backend.base import TokenUsage
        self.token_usage = TokenUsage()
    
    def _build_command(self, messages, tools, **kwargs):
        return ["echo", "mock command"]
    
    def _parse_output(self, output):
        return {
            "content": self.mock_output,
            "tool_calls": [],
            "raw_response": output
        }
    
    async def _execute_cli_command(self, command):
        """Mock command execution."""
        await asyncio.sleep(0.1)  # Simulate some delay
        return self.mock_output
    
    def get_cost_per_token(self):
        """Mock cost per token."""
        return {"input": 0.001, "output": 0.002}


async def test_cli_base_functionality():
    """Test the CLI base class functionality."""
    print("🧪 Testing CLI base functionality...")
    
    backend = MockCLIBackend("mock-cli", "Hello from mock CLI!")
    
    messages = [{"role": "user", "content": "Test message"}]
    tools = []
    
    chunks = []
    async for chunk in backend.stream_with_tools(messages, tools):
        chunks.append(chunk)
    
    assert len(chunks) > 0, "Should produce at least one chunk"
    assert any(chunk.type == "content" for chunk in chunks), "Should have content chunk"
    assert any(chunk.type == "done" for chunk in chunks), "Should have done chunk"
    
    print("✅ CLI base functionality test passed")


def test_claude_code_cli_command_building():
    """Test Claude Code CLI command building (without executing)."""
    print("🧪 Testing Claude Code CLI command building...")
    
    # Mock the shutil.which check
    import massgen.backend.claude_code_cli
    original_which = massgen.backend.claude_code_cli.shutil.which
    massgen.backend.claude_code_cli.shutil.which = lambda x: "/usr/bin/claude"
    
    try:
        backend = ClaudeCodeCLIBackend(model="sonnet")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is 2+2?"}
        ]
        tools = [{"function": {"name": "test_tool", "description": "A test tool"}}]
        
        command = backend._build_command(messages, tools)
        
        assert "claude" in command[0], "Should use claude CLI"
        assert "-p" in command, "Should use print mode"
        assert "--output-format" in command, "Should request JSON output"
        assert "json" in command, "Should specify JSON format"
        
        print("✅ Claude Code CLI command building test passed")
        
    finally:
        # Restore original function
        massgen.backend.claude_code_cli.shutil.which = original_which


def test_gemini_cli_command_building():
    """Test Gemini CLI command building (without executing)."""
    print("🧪 Testing Gemini CLI command building...")
    
    # Mock the shutil.which check
    import massgen.backend.gemini_cli
    original_which = massgen.backend.gemini_cli.shutil.which
    massgen.backend.gemini_cli.shutil.which = lambda x: "/usr/bin/gemini"
    
    try:
        backend = GeminiCLIBackend(model="gemini-2.5-pro")
        
        messages = [
            {"role": "user", "content": "What is the capital of France?"}
        ]
        tools = []
        
        command = backend._build_command(messages, tools)
        
        assert "timeout" in command[0], "Should use timeout command"
        assert "gemini" in command, "Should use gemini CLI"
        
        print("✅ Gemini CLI command building test passed")
        
    finally:
        # Restore original function
        massgen.backend.gemini_cli.shutil.which = original_which


def test_configuration_files():
    """Test that configuration files are valid."""
    print("🧪 Testing configuration files...")
    
    import yaml
    
    config_files = [
        "massgen/configs/claude_code_cli.yaml",
        "massgen/configs/gemini_cli.yaml", 
        "massgen/configs/cli_backends_mixed.yaml"
    ]
    
    for config_file in config_files:
        if Path(config_file).exists():
            try:
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                assert config is not None, f"Config {config_file} should not be empty"
                print(f"✅ {config_file} is valid")
            except Exception as e:
                print(f"❌ {config_file} is invalid: {e}")
                raise
        else:
            print(f"⚠️  {config_file} not found, skipping")


async def test_end_to_end_mock():
    """Test end-to-end functionality with mocked CLI execution."""
    print("🧪 Testing end-to-end with mock execution...")
    
    # Test Claude Code CLI mock
    claude_backend = MockCLIBackend(
        "claude", 
        '{"response": "4", "reasoning": "2+2 equals 4"}'
    )
    
    messages = [{"role": "user", "content": "What is 2+2?"}]
    tools = []
    
    chunks = []
    async for chunk in claude_backend.stream_with_tools(messages, tools):
        chunks.append(chunk)
        print(f"  📝 Chunk: {chunk.type} - {chunk.content}")
    
    assert len(chunks) >= 3, "Should have content, complete_message, and done chunks"
    
    print("✅ End-to-end mock test passed")


async def main():
    """Run all tests."""
    print("🚀 Starting CLI backend tests...\n")
    
    try:
        # Test basic functionality
        await test_cli_base_functionality()
        print()
        
        # Test command building
        test_claude_code_cli_command_building()
        print()
        
        test_gemini_cli_command_building()
        print()
        
        # Test configuration files
        test_configuration_files()
        print()
        
        # Test end-to-end mock
        await test_end_to_end_mock()
        print()
        
        print("🎉 All CLI backend tests passed!")
        
        # Show usage information
        print("\n📋 Usage Information:")
        print("CLI backends are now available in MassGen!")
        print()
        print("Prerequisites:")
        print("  • Claude Code CLI: npm install -g @anthropic-ai/claude-code")
        print("  • Gemini CLI: npm install -g @google/gemini-cli")
        print()
        print("Usage examples:")
        print("  # Claude Code CLI")
        print("  uv run python -m massgen.cli --backend claude-code-cli --model sonnet 'What is 2+2?'")
        print("  uv run python -m massgen.cli --config massgen/configs/claude_code_cli.yaml 'Debug this code'")
        print()
        print("  # Gemini CLI")
        print("  uv run python -m massgen.cli --backend gemini-cli --model gemini-2.5-pro 'Explain quantum computing'")
        print("  uv run python -m massgen.cli --config massgen/configs/gemini_cli.yaml 'Analyze this data'")
        print()
        print("  # Mixed CLI backends")
        print("  uv run python -m massgen.cli --config massgen/configs/cli_backends_mixed.yaml 'Complex question'")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())