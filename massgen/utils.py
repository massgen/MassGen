MODEL_MAPPINGS = {
    "openai": [
        # GPT-5 variants
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        # GPT-4.1 variants
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        # GPT-4o variants
        "gpt-4o-mini",
        "gpt-4o",
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
    "claude": [
        # Claude 4 variants
        "claude-opus-4-1-20250805",
        "claude-opus-4-20250514", 
        "claude-sonnet-4-20250514",
        # Claude 3.5 variants
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-20250114",
        "claude-3-5-haiku-20250107",
        # Claude 3 variants
        "claude-3-opus-20240229",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "grok": [
        "grok-3-mini",
        "grok-3",
        "grok-4",
    ],
    "zai": [
        "glm-4.5",
        "glm-4.5-air",
    ],

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
