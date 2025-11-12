# -*- coding: utf-8 -*-
"""Data models for memory MCP server."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Literal


@dataclass
class Memory:
    """Represents a memory stored in the filesystem."""

    name: str
    description: str
    content: str
    tier: Literal["short_term", "long_term"]
    agent_id: str
    created: datetime = field(default_factory=datetime.now)
    updated: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Convert to markdown with YAML frontmatter.

        Returns:
            Markdown string with YAML frontmatter followed by content.
        """
        frontmatter = f"""---
name: {self.name}
description: {self.description}
tier: {self.tier}
agent_id: {self.agent_id}
created: {self.created.isoformat()}
updated: {self.updated.isoformat()}
---

{self.content}"""
        return frontmatter

    @classmethod
    def from_markdown(cls, content: str, filename: str = None) -> "Memory":
        """Parse markdown with YAML frontmatter.

        Args:
            content: Markdown string with YAML frontmatter
            filename: Optional filename (used to extract name if not in frontmatter)

        Returns:
            Memory instance parsed from markdown

        Raises:
            ValueError: If frontmatter is missing or malformed
        """
        # Split frontmatter from content
        if not content.startswith("---"):
            raise ValueError("Memory file must start with YAML frontmatter (---)")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Malformed YAML frontmatter - missing closing ---")

        frontmatter_text = parts[1].strip()
        memory_content = parts[2].strip()

        # Parse frontmatter (simple key: value parser)
        metadata = {}
        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

        # Extract name from filename if not in frontmatter
        name = metadata.get("name")
        if not name and filename:
            # Remove .md extension if present
            name = filename.replace(".md", "")
        if not name:
            raise ValueError("Memory name not found in frontmatter or filename")

        # Parse required fields
        description = metadata.get("description", "")
        tier = metadata.get("tier", "short_term")
        agent_id = metadata.get("agent_id", "unknown")

        # Parse timestamps
        created_str = metadata.get("created")
        updated_str = metadata.get("updated")

        try:
            created = datetime.fromisoformat(created_str) if created_str else datetime.now()
        except (ValueError, TypeError):
            created = datetime.now()

        try:
            updated = datetime.fromisoformat(updated_str) if updated_str else datetime.now()
        except (ValueError, TypeError):
            updated = datetime.now()

        # Validate tier
        if tier not in ["short_term", "long_term"]:
            tier = "short_term"

        return cls(
            name=name,
            description=description,
            content=memory_content,
            tier=tier,
            agent_id=agent_id,
            created=created,
            updated=updated,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the memory
        """
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "tier": self.tier,
            "agent_id": self.agent_id,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """Create Memory instance from dictionary.

        Args:
            data: Dictionary with memory fields

        Returns:
            Memory instance
        """
        # Parse timestamps
        created = data.get("created")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        elif created is None:
            created = datetime.now()

        updated = data.get("updated")
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        elif updated is None:
            updated = datetime.now()

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            content=data.get("content", ""),
            tier=data.get("tier", "short_term"),
            agent_id=data.get("agent_id", "unknown"),
            created=created,
            updated=updated,
        )
