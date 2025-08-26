"""
Test script for Claude Code Context Sharing functionality.

This script tests the context sharing capabilities between multiple Claude Code agents,
ensuring that:
1. Workspace snapshots are saved correctly
2. Snapshots are restored with anonymization
3. Agents can access each other's work through shared context
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from massgen.orchestrator import Orchestrator
from massgen.chat_agent import ChatAgent
from massgen.agent_config import AgentConfig


class MockClaudeCodeBackend:
    """Mock Claude Code backend for testing."""
    
    def __init__(self, cwd: str = None):
        self._cwd = cwd or "test_workspace"
        
    def get_provider_name(self) -> str:
        return "claude_code"


class MockClaudeCodeAgent(ChatAgent):
    """Mock Claude Code agent for testing."""
    
    def __init__(self, agent_id: str, cwd: str = None):
        super().__init__(session_id=f"session_{agent_id}")
        self.agent_id = agent_id
        self.backend = MockClaudeCodeBackend(cwd)
        
    async def chat(self, messages, tools=None, reset_chat=False, clear_history=False):
        """Mock chat implementation."""
        for _ in range(3):
            yield {"type": "content", "content": f"Working on task from {self.agent_id}"}
        yield {"type": "result", "data": ("answer", f"Solution from {self.agent_id}")}


@pytest.fixture
def test_workspace(tmp_path):
    """Create temporary test workspace."""
    workspace = tmp_path / "test_context_sharing"
    workspace.mkdir(exist_ok=True)
    
    # Create test directories
    snapshot_storage = workspace / "snapshots"
    temp_workspace = workspace / "temp_workspaces"
    
    snapshot_storage.mkdir(exist_ok=True)
    temp_workspace.mkdir(exist_ok=True)
    
    yield {
        "workspace": workspace,
        "snapshot_storage": str(snapshot_storage),
        "temp_workspace": str(temp_workspace)
    }
    
    # Cleanup
    if workspace.exists():
        shutil.rmtree(workspace)


@pytest.fixture
def mock_agents():
    """Create mock Claude Code agents."""
    agents = {}
    for i in range(1, 4):
        agent_id = f"claude_code_{i}"
        cwd = f"test_workspace/agent_{i}"
        agents[agent_id] = MockClaudeCodeAgent(agent_id, cwd)
    return agents


def test_orchestrator_initialization_with_context_sharing(test_workspace, mock_agents):
    """Test orchestrator initializes with context sharing parameters."""
    
    orchestrator = Orchestrator(
        agents=mock_agents,
        snapshot_storage=test_workspace["snapshot_storage"],
        agent_temporary_workspace=test_workspace["temp_workspace"]
    )
    
    # Check that parameters are set
    assert orchestrator._snapshot_storage == test_workspace["snapshot_storage"]
    assert orchestrator._agent_temporary_workspace == test_workspace["temp_workspace"]
    
    # Check that agent ID mappings are created
    assert len(orchestrator._agent_id_mapping) == 3
    assert "claude_code_1" in orchestrator._agent_id_mapping
    assert "claude_code_2" in orchestrator._agent_id_mapping
    assert "claude_code_3" in orchestrator._agent_id_mapping
    
    # Check anonymized IDs
    assert orchestrator._agent_id_mapping["claude_code_1"] == "agent_1"
    assert orchestrator._agent_id_mapping["claude_code_2"] == "agent_2"
    assert orchestrator._agent_id_mapping["claude_code_3"] == "agent_3"
    
    # Check directories are created
    assert Path(test_workspace["snapshot_storage"]).exists()
    assert Path(test_workspace["temp_workspace"]).exists()
    
    for agent_id in mock_agents.keys():
        snapshot_dir = Path(test_workspace["snapshot_storage"]) / agent_id
        temp_dir = Path(test_workspace["temp_workspace"]) / agent_id
        assert snapshot_dir.exists()
        assert temp_dir.exists()


@pytest.mark.asyncio
async def test_snapshot_saving(test_workspace, mock_agents):
    """Test that snapshots are saved correctly when agents complete tasks."""
    
    orchestrator = Orchestrator(
        agents=mock_agents,
        snapshot_storage=test_workspace["snapshot_storage"],
        agent_temporary_workspace=test_workspace["temp_workspace"]
    )
    
    # Create some test files in agent workspaces
    for agent_id, agent in mock_agents.items():
        workspace = Path(agent.backend._cwd)
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Create test files
        (workspace / f"code_{agent_id}.py").write_text(f"# Code from {agent_id}")
        (workspace / f"test_{agent_id}.txt").write_text(f"Test data from {agent_id}")
    
    # Save snapshot for one agent
    await orchestrator._save_claude_code_snapshot("claude_code_1")
    
    # Check snapshot was saved
    snapshot_dir = Path(test_workspace["snapshot_storage"]) / "claude_code_1"
    assert (snapshot_dir / "code_claude_code_1.py").exists()
    assert (snapshot_dir / "test_claude_code_1.txt").exists()


@pytest.mark.asyncio
async def test_workspace_restoration_with_anonymization(test_workspace, mock_agents):
    """Test that workspaces are restored with anonymized agent IDs."""
    
    orchestrator = Orchestrator(
        agents=mock_agents,
        snapshot_storage=test_workspace["snapshot_storage"],
        agent_temporary_workspace=test_workspace["temp_workspace"]
    )
    
    # Create snapshots for all agents
    for agent_id, agent in mock_agents.items():
        workspace = Path(agent.backend._cwd)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / f"work_{agent_id}.txt").write_text(f"Work from {agent_id}")
        
        # Save to snapshot
        await orchestrator._save_claude_code_snapshot(agent_id)
    
    # Restore workspace for agent 2
    workspace_path = await orchestrator._restore_snapshots_to_workspace("claude_code_2")
    
    assert workspace_path is not None
    workspace_dir = Path(workspace_path)
    
    # Check that all snapshots are restored with anonymized names
    assert (workspace_dir / "agent_1" / "work_claude_code_1.txt").exists()
    assert (workspace_dir / "agent_2" / "work_claude_code_2.txt").exists()
    assert (workspace_dir / "agent_3" / "work_claude_code_3.txt").exists()
    
    # Verify content
    content1 = (workspace_dir / "agent_1" / "work_claude_code_1.txt").read_text()
    assert content1 == "Work from claude_code_1"


@pytest.mark.asyncio
async def test_save_all_snapshots(test_workspace, mock_agents):
    """Test saving all Claude Code agent snapshots at once."""
    
    orchestrator = Orchestrator(
        agents=mock_agents,
        snapshot_storage=test_workspace["snapshot_storage"],
        agent_temporary_workspace=test_workspace["temp_workspace"]
    )
    
    # Create test files in all agent workspaces
    for agent_id, agent in mock_agents.items():
        workspace = Path(agent.backend._cwd)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "shared.py").write_text(f"# Shared code from {agent_id}")
    
    # Save all snapshots
    await orchestrator._save_all_claude_code_snapshots()
    
    # Verify all snapshots were saved
    for agent_id in mock_agents.keys():
        snapshot_dir = Path(test_workspace["snapshot_storage"]) / agent_id
        assert (snapshot_dir / "shared.py").exists()
        content = (snapshot_dir / "shared.py").read_text()
        assert agent_id in content


def test_non_claude_code_agents_ignored(test_workspace):
    """Test that non-Claude Code agents are ignored for context sharing."""
    
    # Create mixed agents (some Claude Code, some not)
    agents = {
        "claude_code_1": MockClaudeCodeAgent("claude_code_1"),
        "regular_agent": MagicMock(backend=MagicMock(get_provider_name=lambda: "openai"))
    }
    
    orchestrator = Orchestrator(
        agents=agents,
        snapshot_storage=test_workspace["snapshot_storage"],
        agent_temporary_workspace=test_workspace["temp_workspace"]
    )
    
    # Only Claude Code agents should have mappings
    assert "claude_code_1" in orchestrator._agent_id_mapping
    assert "regular_agent" not in orchestrator._agent_id_mapping
    assert len(orchestrator._agent_id_mapping) == 1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])