"""
MassGen Configuration System

This module provides configuration management for the MassGen system,
supporting YAML file loading and programmatic configuration creation.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import asdict

from .types import (
    MassConfig, OrchestratorConfig, AgentConfig, ModelConfig, 
    StreamingDisplayConfig, LoggingConfig
)


class ConfigurationError(Exception):
    """Exception raised for configuration-related errors."""
    pass


def load_config_from_yaml(config_path: Union[str, Path]) -> MassConfig:
    """
    Load MassGen configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        MassConfig object with loaded configuration
        
    Raises:
        ConfigurationError: If configuration is invalid or file cannot be loaded
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML format: {e}")
    except Exception as e:
        raise ConfigurationError(f"Failed to read configuration file: {e}")
    
    if not yaml_data:
        raise ConfigurationError("Empty configuration file")
    
    return _dict_to_config(yaml_data)


def create_config_from_models(
    models: List[str],
    orchestrator_config: Optional[Dict[str, Any]] = None,
    streaming_config: Optional[Dict[str, Any]] = None,
    logging_config: Optional[Dict[str, Any]] = None
) -> MassConfig:
    """
    Create a MassGen configuration from a list of model names.
    
    Args:
        models: List of model names (e.g., ["gpt-4o", "gemini-2.5-flash"])
        orchestrator_config: Optional orchestrator configuration overrides
        streaming_config: Optional streaming display configuration overrides
        logging_config: Optional logging configuration overrides
        
    Returns:
        MassConfig object ready to use
    """
    from .utils import get_agent_type_from_model
    
    # Create agent configurations
    agents = []
    for i, model in enumerate(models):
        agent_type = get_agent_type_from_model(model)
        model_config = ModelConfig(
            model=model,
            tools=["live_search", "code_execution"],  # Default tools
            max_retries=10,
            max_rounds=10,
            temperature=None,
            inference_timeout=180
        )
        
        agent_config = AgentConfig(
            agent_id=i + 1,
            agent_type=agent_type,
            model_config=model_config
        )
        agents.append(agent_config)
    
    # Create configuration components
    orchestrator = OrchestratorConfig(**(orchestrator_config or {}))
    streaming_display = StreamingDisplayConfig(**(streaming_config or {}))
    logging = LoggingConfig(**(logging_config or {}))
    
    config = MassConfig(
        orchestrator=orchestrator,
        agents=agents,
        streaming_display=streaming_display,
        logging=logging
    )
    
    config.validate()
    return config


def _dict_to_config(data: Dict[str, Any]) -> MassConfig:
    """Convert dictionary data to MassConfig object."""
    try:
        # Parse orchestrator configuration
        orchestrator_data = data.get('orchestrator', {})
        orchestrator = OrchestratorConfig(**orchestrator_data)
        
        # Parse agents configuration
        agents_data = data.get('agents', [])
        if not agents_data:
            raise ConfigurationError("No agents specified in configuration")
        
        agents = []
        for agent_data in agents_data:
            # Parse model configuration
            model_data = agent_data.get('model_config', {})
            model_config = ModelConfig(**model_data)
            
            # Create agent configuration
            agent_config = AgentConfig(
                agent_id=agent_data['agent_id'],
                agent_type=agent_data['agent_type'],
                model_config=model_config
            )
            agents.append(agent_config)
        
        # Parse streaming display configuration
        streaming_data = data.get('streaming_display', {})
        streaming_display = StreamingDisplayConfig(**streaming_data)
        
        # Parse logging configuration
        logging_data = data.get('logging', {})
        logging = LoggingConfig(**logging_data)
        
        # Parse task configuration
        task = data.get('task')
        
        config = MassConfig(
            orchestrator=orchestrator,
            agents=agents,
            streaming_display=streaming_display,
            logging=logging,
            task=task
        )
        
        config.validate()
        return config
        
    except KeyError as e:
        raise ConfigurationError(f"Missing required configuration key: {e}")
    except TypeError as e:
        raise ConfigurationError(f"Invalid configuration value: {e}")
    except Exception as e:
        raise ConfigurationError(f"Configuration parsing error: {e}") 