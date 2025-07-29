"""
Factory functions for creating backend instances.
"""

from .base import AgentBackend
from .openai import OpenAIResponseBackend


def create_backend(provider: str, model: str, **kwargs) -> AgentBackend:
    """
    Create an agent backend based on provider.
    
    Args:
        provider: Provider name ("anthropic", "google", "openai", "xai", etc.)
        model: Model name
        **kwargs: Additional configuration
        
    Returns:
        AgentBackend: Initialized backend instance
    """
    if provider.lower() == "openai":
        return OpenAIResponseBackend(model=model, **kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def get_provider_from_model(model: str) -> str:
    """
    Detect provider from model name.
    
    Args:
        model: Model name
        
    Returns:
        str: Provider name
    """
    model_lower = model.lower()
    
    if any(prefix in model_lower for prefix in ["claude"]):
        return "anthropic"
    elif any(prefix in model_lower for prefix in ["gemini"]):
        return "google"
    elif any(prefix in model_lower for prefix in ["gpt", "o1", "o3"]):
        return "openai"
    elif any(prefix in model_lower for prefix in ["grok"]):
        return "xai"
    else:
        # Default to OpenAI for unknown models
        return "openai"