# -*- coding: utf-8 -*-
"""
Rate limit configuration loader for MassGen.

Loads rate limit settings from YAML configuration file and provides
easy access to provider-specific limits.
"""

import os
from pathlib import Path
from typing import Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class RateLimitConfig:
    """
    Rate limit configuration loader and accessor.
    
    Loads rate limits from YAML configuration file and provides
    methods to retrieve limits for specific providers and models.
    
    Example:
        config = RateLimitConfig()
        limits = config.get_limits('gemini', 'gemini-2.5-flash')
        # Returns: {'rpm': 9, 'tpm': 240000, 'rpd': 245}
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize rate limit config loader.
        
        Args:
            config_path: Path to YAML config file. If None, uses default location.
        """
        if config_path is None:
            # Default to rate_limits.yaml in the same directory as this file
            # This file is in massgen/configs/rate_limits/rate_limit_config.py
            config_dir = Path(__file__).parent
            config_path = config_dir / "rate_limits.yaml"
        
        self.config_path = Path(config_path)
        self._config: Dict = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from YAML file."""
        if yaml is None:
            from ...logger_config import logger
            logger.warning(
                "[RateLimitConfig] PyYAML not installed. "
                "Rate limit configuration will not be loaded. "
                "Install with: pip install pyyaml"
            )
            return
        
        if not self.config_path.exists():
            from ...logger_config import logger
            logger.warning(
                f"[RateLimitConfig] Configuration file not found: {self.config_path}. "
                "Using default rate limits."
            )
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
                
            from ...logger_config import logger
            logger.info(
                f"[RateLimitConfig] Loaded rate limits from {self.config_path}"
            )
        except Exception as e:
            from ...logger_config import logger
            logger.error(
                f"[RateLimitConfig] Failed to load config from {self.config_path}: {e}. "
                "Using default rate limits."
            )
    
    def get_limits(
        self, 
        provider: str, 
        model: str,
        use_defaults: bool = True
    ) -> Dict[str, Optional[int]]:
        """
        Get rate limits for a specific provider and model.
        
        Args:
            provider: Provider name (e.g., 'gemini', 'openai', 'claude')
            model: Model name (e.g., 'gemini-2.5-flash', 'gpt-4', 'claude-3-5-sonnet')
            use_defaults: If True, falls back to provider's default config if model not found
            
        Returns:
            Dictionary with 'rpm', 'tpm', 'rpd' keys. Values are None if not configured.
        """
        # Default values
        result = {
            'rpm': None,
            'tpm': None,
            'rpd': None
        }
        
        if not self._config:
            return result
        
        # Get provider config
        provider_config = self._config.get(provider, {})
        if not provider_config:
            return result
        
        # Try to find exact model match
        model_config = None
        
        # First: Try exact match
        if model in provider_config:
            model_config = provider_config[model]
        else:
            # Second: Try partial match (e.g., "gemini-2.5-flash" contains "2.5-flash")
            for config_model, config in provider_config.items():
                if config_model != 'default' and config_model in model:
                    model_config = config
                    break
        
        # Third: Fall back to default if enabled
        if model_config is None and use_defaults:
            model_config = provider_config.get('default', {})
        
        # Extract limits from config
        if model_config:
            result['rpm'] = model_config.get('rpm')
            result['tpm'] = model_config.get('tpm')
            result['rpd'] = model_config.get('rpd')
        
        return result
    
    def get_provider_models(self, provider: str) -> list:
        """
        Get list of configured models for a provider.
        
        Args:
            provider: Provider name (e.g., 'gemini', 'openai', 'claude')
            
        Returns:
            List of model names configured for the provider
        """
        if not self._config:
            return []
        
        provider_config = self._config.get(provider, {})
        return [k for k in provider_config.keys() if k != 'default']
    
    def has_config(self) -> bool:
        """Check if configuration was successfully loaded."""
        return bool(self._config)


# Global singleton instance
_global_config: Optional[RateLimitConfig] = None


def get_rate_limit_config(reload: bool = False) -> RateLimitConfig:
    """
    Get global rate limit configuration instance.
    
    Args:
        reload: If True, reloads the configuration from file
        
    Returns:
        RateLimitConfig instance
    """
    global _global_config
    
    if _global_config is None or reload:
        _global_config = RateLimitConfig()
    
    return _global_config
