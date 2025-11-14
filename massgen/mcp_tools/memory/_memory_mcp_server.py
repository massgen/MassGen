# -*- coding: utf-8 -*-
"""FastMCP server for agent memory management with filesystem persistence.

This MCP server provides tools for creating, updating, and loading memories
with automatic filesystem persistence. Memories are stored in the agent's
workspace under memory/short_term/ and memory/long_term/.

Inspired by Letta's context hierarchy: https://docs.letta.com/guides/agents/context-hierarchy
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import fastmcp
except ImportError:
    raise ImportError("fastmcp is required for memory MCP server. Install with: uv pip install fastmcp")

from massgen.mcp_tools.memory._memory_models import Memory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
_memories: Dict[str, Memory] = {}  # In-memory cache: name -> Memory
_workspace_path: Optional[Path] = None  # Agent workspace path


def _save_memory_to_filesystem(memory: Memory) -> None:
    """Save memory to filesystem if workspace path is configured.

    Memories are saved to workspace/memory/{tier}/{name}.md

    Args:
        memory: Memory instance to save
    """
    if _workspace_path is None:
        return

    memory_dir = _workspace_path / "memory" / memory.tier
    memory_dir.mkdir(parents=True, exist_ok=True)

    memory_file = memory_dir / f"{memory.name}.md"
    memory_file.write_text(memory.to_markdown())
    logger.info(f"Saved memory '{memory.name}' to {memory_file}")


def _delete_memory_from_filesystem(memory: Memory) -> None:
    """Delete memory from filesystem if it exists.

    Args:
        memory: Memory instance to delete
    """
    if _workspace_path is None:
        return

    memory_file = _workspace_path / "memory" / memory.tier / f"{memory.name}.md"
    if memory_file.exists():
        memory_file.unlink()
        logger.info(f"Deleted memory '{memory.name}' from {memory_file}")


def _load_memories_from_filesystem() -> None:
    """Load all memories from filesystem on startup.

    Scans memory/short_term/ and memory/long_term/ directories and loads
    all .md files into the in-memory cache.
    """
    if _workspace_path is None:
        return

    memory_base = _workspace_path / "memory"
    if not memory_base.exists():
        logger.info("No memory directory found, starting with empty memory")
        return

    loaded_count = 0
    for tier in ["short_term", "long_term"]:
        tier_dir = memory_base / tier
        if not tier_dir.exists():
            continue

        for memory_file in tier_dir.glob("*.md"):
            try:
                content = memory_file.read_text()
                memory = Memory.from_markdown(content, filename=memory_file.stem)
                _memories[memory.name] = memory
                loaded_count += 1
                logger.info(f"Loaded memory '{memory.name}' from {memory_file}")
            except Exception as e:
                logger.error(f"Failed to load memory from {memory_file}: {e}")

    logger.info(f"Loaded {loaded_count} memories from filesystem")


async def create_server() -> fastmcp.FastMCP:
    """Create and configure the memory MCP server.

    Returns:
        Configured FastMCP server instance
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--orchestrator-id", required=True, help="Orchestrator ID")
    parser.add_argument("--workspace-path", required=False, help="Agent workspace path for filesystem persistence")
    args = parser.parse_args()

    # Set workspace path if provided
    global _workspace_path
    if args.workspace_path:
        _workspace_path = Path(args.workspace_path)
        logger.info(f"Memory filesystem mode enabled: {_workspace_path}")
        _load_memories_from_filesystem()
    else:
        logger.info("Memory filesystem mode disabled (no workspace path)")

    # Create MCP server
    mcp = fastmcp.FastMCP("Agent Memory")
    mcp.agent_id = args.agent_id
    mcp.orchestrator_id = args.orchestrator_id

    @mcp.tool()
    def create_memory(
        name: str,
        description: str,
        content: str,
        tier: str = "short_term",
    ) -> Dict[str, Any]:
        """Create a new memory in short-term or long-term storage.

        Memories are automatically saved to the filesystem if workspace path is configured.
        Short-term memories are auto-injected into all agents' system prompts.
        Long-term memories require explicit loading via load_memory().

        Args:
            name: Unique identifier for the memory (must be filesystem-safe)
            description: Short summary of the memory (shown in tables/overviews)
            content: Full content of the memory (markdown supported)
            tier: Either "short_term" (always in-context) or "long_term" (load on-demand)

        Returns:
            Dictionary with operation result

        Example:
            create_memory(
                name="user_preferences",
                description="User's coding style preferences",
                content="# Preferences\\n- Uses tabs\\n- Prefers functional style",
                tier="short_term"
            )
        """
        try:
            # Validate tier
            if tier not in ["short_term", "long_term"]:
                return {
                    "success": False,
                    "error": f"Invalid tier '{tier}'. Must be 'short_term' or 'long_term'",
                }

            # Check if memory already exists
            if name in _memories:
                return {
                    "success": False,
                    "error": f"Memory '{name}' already exists. Use update_memory to modify it.",
                }

            # Create memory
            memory = Memory(
                name=name,
                description=description,
                content=content,
                tier=tier,
                agent_id=mcp.agent_id,
                created=datetime.now(),
                updated=datetime.now(),
            )

            # Store in memory cache
            _memories[name] = memory

            # Save to filesystem
            _save_memory_to_filesystem(memory)

            return {
                "success": True,
                "operation": "create_memory",
                "memory": memory.to_dict(),
            }

        except Exception as e:
            logger.error(f"Error creating memory: {e}")
            return {
                "success": False,
                "operation": "create_memory",
                "error": str(e),
            }

    @mcp.tool()
    def update_memory(
        name: str,
        content: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update existing memory content and/or description.

        Args:
            name: Name of the memory to update
            content: New content for the memory
            description: Optional new description (if None, keeps existing)

        Returns:
            Dictionary with operation result

        Example:
            update_memory(
                name="user_preferences",
                content="# Updated Preferences\\n- Uses spaces (changed from tabs)",
                description="Updated user coding style preferences"
            )
        """
        try:
            # Check if memory exists
            if name not in _memories:
                return {
                    "success": False,
                    "error": f"Memory '{name}' not found. Use create_memory to create it.",
                }

            # Update memory
            memory = _memories[name]
            memory.content = content
            if description is not None:
                memory.description = description
            memory.updated = datetime.now()

            # Save to filesystem
            _save_memory_to_filesystem(memory)

            return {
                "success": True,
                "operation": "update_memory",
                "memory": memory.to_dict(),
            }

        except Exception as e:
            logger.error(f"Error updating memory: {e}")
            return {
                "success": False,
                "operation": "update_memory",
                "error": str(e),
            }

    @mcp.tool()
    def remove_memory(name: str) -> Dict[str, Any]:
        """Delete a memory from storage.

        Args:
            name: Name of the memory to remove

        Returns:
            Dictionary with operation result

        Example:
            remove_memory(name="old_preferences")
        """
        try:
            # Check if memory exists
            if name not in _memories:
                return {
                    "success": False,
                    "error": f"Memory '{name}' not found.",
                }

            # Get memory before deletion
            memory = _memories[name]

            # Remove from cache
            del _memories[name]

            # Delete from filesystem
            _delete_memory_from_filesystem(memory)

            return {
                "success": True,
                "operation": "remove_memory",
                "name": name,
            }

        except Exception as e:
            logger.error(f"Error removing memory: {e}")
            return {
                "success": False,
                "operation": "remove_memory",
                "error": str(e),
            }

    @mcp.tool()
    def load_memory(name: str) -> Dict[str, Any]:
        """Load a long-term memory into context.

        This tool retrieves the full content of a long-term memory, making it
        available in the current conversation context. Short-term memories are
        already in-context and don't need to be loaded.

        Args:
            name: Name of the memory to load

        Returns:
            Dictionary with memory content and metadata

        Example:
            load_memory(name="project_history")
        """
        try:
            # Check if memory exists
            if name not in _memories:
                return {
                    "success": False,
                    "error": f"Memory '{name}' not found.",
                }

            memory = _memories[name]

            return {
                "success": True,
                "operation": "load_memory",
                "memory": memory.to_dict(),
                "content": memory.content,
            }

        except Exception as e:
            logger.error(f"Error loading memory: {e}")
            return {
                "success": False,
                "operation": "load_memory",
                "error": str(e),
            }

    return mcp


if __name__ == "__main__":
    import asyncio

    import fastmcp

    asyncio.run(fastmcp.run(create_server))
