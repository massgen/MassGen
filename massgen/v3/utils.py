from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union, Optional, Dict, List

MODEL_MAPPINGS = {
    "openai": [
        # GPT-4.1 variants
        "gpt-4.1",
        "gpt-4.1-mini",
        # GPT-4o variants
        "gpt-4o-mini",
        "gpt-4o",
        # o1
        "o1",  # -> o1-2024-12-17
        # o3
        "o3",
        "o3-low",
        "o3-medium",
        "o3-high",
        # o3 mini
        "o3-mini",
        "o3-mini-low",
        "o3-mini-medium",
        "o3-mini-high",
        # o4 mini
        "o4-mini",
        "o4-mini-low",
        "o4-mini-medium",
        "o4-mini-high",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "grok": [
        "grok-3-mini",
        "grok-3",
        "grok-4",
    ]
}

def get_backend_type_from_model(model: str) -> str:
    """
    Determine the agent type based on the model name.
        
    Args:
        model: The model name (e.g., "gpt-4", "gemini-pro", "grok-1")
            
    Returns:
        Agent type string ("openai", "gemini", "grok")
    """
    if not model:
        return "openai"  # Default to OpenAI
        
    model_lower = model.lower()
        
    for key, models in MODEL_MAPPINGS.items():
        if model_lower in models:
            return key
    raise ValueError(f"Unknown model: {model}")