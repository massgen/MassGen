"""
AgentConfig Implementation - Issue #21: Implement Factory Functions and Configuration

This module provides comprehensive configuration management for agents and orchestrators,
including YAML/JSON support, validation, and hierarchical naming conventions.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable
import re
import json
import os
from pathlib import Path
from .backends import get_provider_from_model


@dataclass
class AgentConfig:
    """Comprehensive configuration class for agents and orchestrators."""
    
    # Core agent configuration
    agent_id: str
    model: str
    provider: Optional[str] = None
    api_key: Optional[str] = None
    system_message: Optional[str] = None
    
    # Agent behavior configuration
    max_retries: int = 3
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: int = 300
    
    # Tools and capabilities
    tools: List[Dict[str, Any]] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=list)
    
    # Session and logging
    session_id: Optional[str] = None
    log_level: str = "INFO"
    enable_logging: bool = True
    
    # Advanced configuration
    custom_config: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """Validate the agent configuration."""
        # Validate agent ID
        if not self.agent_id:
            raise ValueError("agent_id is required")
        
        if not self._is_valid_agent_id(self.agent_id):
            raise ValueError(f"Invalid agent_id format: {self.agent_id}")
        
        # Validate model
        if not self.model:
            raise ValueError("model is required")
        
        # Validate numeric values
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        
        # Auto-detect provider if not specified
        if not self.provider:
            self.provider = get_provider_from_model(self.model)
    
    def _is_valid_agent_id(self, agent_id: str) -> bool:
        """
        Validate agent ID with hierarchical naming conventions.
        
        Supported formats:
        - simple: "agent1", "researcher", "analyst"
        - hierarchical: "team.researcher", "org.team.analyst"
        - specialized: "research-team.senior-analyst", "dev_team.backend_engineer"
        
        Args:
            agent_id: Agent ID to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Pattern: alphanumeric, hyphens, underscores, dots for hierarchy
        pattern = r'^[a-zA-Z][a-zA-Z0-9_-]*(\.[a-zA-Z][a-zA-Z0-9_-]*)*$'
        
        if not re.match(pattern, agent_id):
            return False
        
        # Additional constraints
        parts = agent_id.split('.')
        
        # Max hierarchy depth of 5
        if len(parts) > 5:
            return False
        
        # Each part must be 1-50 characters
        for part in parts:
            if not (1 <= len(part) <= 50):
                return False
        
        return True
    
    
    def get_hierarchy_level(self) -> int:
        """Get the hierarchy level of the agent ID."""
        return len(self.agent_id.split('.'))
    
    def get_parent_id(self) -> Optional[str]:
        """Get the parent agent ID in the hierarchy."""
        parts = self.agent_id.split('.')
        if len(parts) <= 1:
            return None
        return '.'.join(parts[:-1])
    
    def get_root_id(self) -> str:
        """Get the root agent ID in the hierarchy."""
        return self.agent_id.split('.')[0]
    
    def is_child_of(self, parent_id: str) -> bool:
        """Check if this agent is a child of the given parent ID."""
        return self.agent_id.startswith(f"{parent_id}.")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "provider": self.provider,
            "api_key": self.api_key,
            "system_message": self.system_message,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "tools": self.tools,
            "allowed_actions": self.allowed_actions,
            "session_id": self.session_id,
            "log_level": self.log_level,
            "enable_logging": self.enable_logging,
            "custom_config": self.custom_config,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentConfig':
        """Create configuration from dictionary."""
        # Filter out None values and unknown keys
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() 
                        if k in known_fields and v is not None}
        
        return cls(**filtered_data)
    
    def merge(self, other: 'AgentConfig') -> 'AgentConfig':
        """Merge this configuration with another, with other taking precedence."""
        merged_data = self.to_dict()
        other_data = other.to_dict()
        
        # Merge dictionaries and lists appropriately
        for key, value in other_data.items():
            if value is not None:
                if key == "tools" and key in merged_data:
                    # Merge tool lists
                    merged_data[key] = merged_data[key] + value
                elif key == "custom_config" and key in merged_data:
                    # Merge custom config dictionaries
                    merged_data[key] = {**merged_data[key], **value}
                elif key == "tags" and key in merged_data:
                    # Merge tag lists (remove duplicates)
                    merged_data[key] = list(set(merged_data[key] + value))
                else:
                    merged_data[key] = value
        
        return AgentConfig.from_dict(merged_data)


@dataclass
class OrchestratorConfig:
    """Configuration for orchestrator-specific settings."""
    
    orchestrator_id: str = "orchestrator"
    max_duration: int = 600
    
    # Voting configuration
    voting_config: Dict[str, Any] = field(default_factory=lambda: {
        "include_vote_counts": False,
        "include_vote_reasons": False,
        "anonymous_voting": True,
        "voting_strategy": "simple_majority",
        "tie_breaking": "registration_order"
    })
    
    # Coordination settings
    enable_streaming: bool = True
    stream_coordination: bool = True
    graceful_restart: bool = True
    
    # Logging and monitoring
    log_manager: Optional[Any] = None
    enable_session_export: bool = True
    track_votes: bool = True
    
    # Advanced settings
    custom_orchestrator_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "orchestrator_id": self.orchestrator_id,
            "max_duration": self.max_duration,
            "voting_config": self.voting_config,
            "enable_streaming": self.enable_streaming,
            "stream_coordination": self.stream_coordination,
            "graceful_restart": self.graceful_restart,
            "enable_session_export": self.enable_session_export,
            "track_votes": self.track_votes,
            "custom_orchestrator_config": self.custom_orchestrator_config
        }


class ConfigManager:
    """Manager for loading and saving agent configurations."""
    
    @staticmethod
    def load_from_file(file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load configuration from YAML or JSON file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Dict containing configuration data
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is unsupported or invalid
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        suffix = file_path.suffix.lower()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if suffix in ['.yaml', '.yml']:
                    try:
                        import yaml
                        return yaml.safe_load(f)
                    except ImportError:
                        raise ValueError("PyYAML not installed. Install with: pip install pyyaml")
                elif suffix == '.json':
                    return json.load(f)
                else:
                    raise ValueError(f"Unsupported file format: {suffix}")
        except Exception as e:
            raise ValueError(f"Error parsing configuration file: {e}")
    
    @staticmethod
    def save_to_file(config_data: Dict[str, Any], file_path: Union[str, Path]) -> None:
        """
        Save configuration to YAML or JSON file.
        
        Args:
            config_data: Configuration data to save
            file_path: Path where to save the file
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        
        # Create directory if it doesn't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if suffix in ['.yaml', '.yml']:
                    try:
                        import yaml
                        yaml.safe_dump(config_data, f, default_flow_style=False, indent=2)
                    except ImportError:
                        raise ValueError("PyYAML not installed. Install with: pip install pyyaml")
                elif suffix == '.json':
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"Unsupported file format: {suffix}")
        except Exception as e:
            raise ValueError(f"Error saving configuration file: {e}")
    
    @staticmethod
    def load_agent_config(file_path: Union[str, Path]) -> AgentConfig:
        """Load AgentConfig from file."""
        data = ConfigManager.load_from_file(file_path)
        return AgentConfig.from_dict(data)
    
    @staticmethod
    def save_agent_config(config: AgentConfig, file_path: Union[str, Path]) -> None:
        """Save AgentConfig to file."""
        ConfigManager.save_to_file(config.to_dict(), file_path)
    
    @staticmethod
    def load_team_config(file_path: Union[str, Path]) -> List[AgentConfig]:
        """
        Load team configuration from file.
        
        Expected format:
        {
            "team": [
                {"agent_id": "agent1", "model": "gpt-4o", ...},
                {"agent_id": "agent2", "model": "claude-3-sonnet", ...}
            ]
        }
        """
        data = ConfigManager.load_from_file(file_path)
        
        if "team" not in data:
            raise ValueError("Configuration file must contain 'team' key with list of agent configs")
        
        return [AgentConfig.from_dict(agent_data) for agent_data in data["team"]]
    
    @staticmethod
    def get_config_from_env(agent_id: str, model: str) -> AgentConfig:
        """
        Create AgentConfig from environment variables.
        
        Environment variables:
        - MASSGEN_API_KEY or {PROVIDER}_API_KEY
        - MASSGEN_LOG_LEVEL
        - MASSGEN_TIMEOUT
        - etc.
        """
        from .agent_backend import get_provider_from_model
        
        provider = get_provider_from_model(model)
        
        # Get API key from environment
        api_key = None
        env_keys = [
            f"MASSGEN_API_KEY",
            f"{provider.upper()}_API_KEY",
            "OPENAI_API_KEY",  # Common fallback
            "ANTHROPIC_API_KEY"
        ]
        
        for key in env_keys:
            api_key = os.getenv(key)
            if api_key:
                break
        
        return AgentConfig(
            agent_id=agent_id,
            model=model,
            provider=provider,
            api_key=api_key,
            log_level=os.getenv("MASSGEN_LOG_LEVEL", "INFO"),
            timeout=int(os.getenv("MASSGEN_TIMEOUT", "300")),
            max_retries=int(os.getenv("MASSGEN_MAX_RETRIES", "3")),
            enable_logging=os.getenv("MASSGEN_ENABLE_LOGGING", "true").lower() == "true"
        )


# Validation functions
def validate_agent_id(agent_id: str) -> bool:
    """Validate agent ID format."""
    try:
        config = AgentConfig(agent_id=agent_id, model="dummy")
        return True
    except ValueError:
        return False


def validate_config_file(file_path: Union[str, Path]) -> List[str]:
    """
    Validate configuration file and return list of validation errors.
    
    Args:
        file_path: Path to configuration file
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    try:
        data = ConfigManager.load_from_file(file_path)
    except Exception as e:
        return [f"Failed to load file: {e}"]
    
    # Validate structure
    if "team" in data:
        # Team configuration
        if not isinstance(data["team"], list):
            errors.append("'team' must be a list")
        else:
            for i, agent_data in enumerate(data["team"]):
                try:
                    AgentConfig.from_dict(agent_data)
                except Exception as e:
                    errors.append(f"Agent {i}: {e}")
    else:
        # Single agent configuration
        try:
            AgentConfig.from_dict(data)
        except Exception as e:
            errors.append(f"Agent configuration error: {e}")
    
    return errors