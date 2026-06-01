"""Provider/model slug resolution for the Textual terminal display.

Extracted collaborator (step 2 of the textual_terminal_display refactor).

``ProviderModelResolver`` is a set of pure, stateless functions over three
module-level mapping tables. There is NO back-reference to the display/app and
nothing from Textual is imported, so this module is import-safe even when
Textual is unavailable.

The ``TextualApp`` keeps thin methods that delegate here.
``build_welcome_agents_info`` takes the already-extracted ``agent_models`` map,
the ordered ``agent_ids``, and per-agent ``provider_hints`` so the App method
only needs to read those off its coordination display / orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_BACKEND_PROVIDER_SLUGS: dict[str, str] = {
    "openai": "openai",
    "codex": "openai",
    "claude": "anthropic",
    "claude_code": "anthropic",
    "gemini": "google",
    "grok": "xai",
    "chatcompletion": "openai",
    "azure_openai": "azure",
    "openrouter": "openrouter",
    "groq": "groq",
    "together": "together",
    "fireworks": "fireworks",
    "cerebras": "cerebras",
    "moonshot": "moonshot",
    "qwen": "alibaba",
    "nebius": "nebius",
    "poe": "poe",
    "lmstudio": "lmstudio",
    "zai": "zai",
    "vllm": "vllm",
    "sglang": "sglang",
    "inference": "inference",
    "ag2": "ag2",
    "uitars": "bytedance",
}

_PROVIDER_NAME_SLUGS: dict[str, str] = {
    "openai": "openai",
    "azure openai": "azure",
    "claude": "anthropic",
    "claude code": "anthropic",
    "anthropic": "anthropic",
    "gemini": "google",
    "google": "google",
    "grok": "xai",
    "xai": "xai",
    "openrouter": "openrouter",
    "chat completions (generic)": "openai",
    "groq": "groq",
    "together ai": "together",
    "fireworks ai": "fireworks",
    "cerebras ai": "cerebras",
    "kimi (moonshot ai)": "moonshot",
    "nebius ai studio": "nebius",
    "qwen (alibaba cloud)": "alibaba",
}

_MODEL_PREFIX_PROVIDER_SLUGS: tuple[tuple[str, str], ...] = (
    ("gpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("o4-", "openai"),
    ("claude-", "anthropic"),
    ("gemini-", "google"),
    ("grok-", "xai"),
    ("qwen-", "alibaba"),
    ("llama-", "meta"),
    ("mistral-", "mistral"),
    ("deepseek-", "deepseek"),
)


def normalize_provider_slug(provider_hint: str | None) -> str | None:
    """Normalize a backend/provider hint into a canonical slug."""
    if not provider_hint:
        return None
    value = str(provider_hint).strip().lower()
    if not value:
        return None
    if "/" in value:
        value = value.split("/", 1)[0]

    backend_key = value.replace(" ", "_").replace("-", "_")
    if backend_key in _BACKEND_PROVIDER_SLUGS:
        return _BACKEND_PROVIDER_SLUGS[backend_key]

    name_key = value.replace("_", " ")
    if name_key in _PROVIDER_NAME_SLUGS:
        return _PROVIDER_NAME_SLUGS[name_key]

    if value in _PROVIDER_NAME_SLUGS:
        return _PROVIDER_NAME_SLUGS[value]

    return None


def infer_provider_slug_from_model(model_name: str) -> str | None:
    """Infer provider slug from common model naming prefixes."""
    lowered_model = model_name.strip().lower()
    if not lowered_model:
        return None
    for prefix, provider_slug in _MODEL_PREFIX_PROVIDER_SLUGS:
        if lowered_model.startswith(prefix):
            return provider_slug
    return None


def to_provider_model(model_name: str, provider_hint: str | None) -> str:
    """Format model names as ``provider/model`` for startup display."""
    model = (model_name or "").strip()
    if not model:
        return ""

    if "/" in model:
        raw_provider, raw_model = model.split("/", 1)
        provider_slug = normalize_provider_slug(raw_provider) or raw_provider.strip().lower()
        normalized_model = raw_model.strip()
        return f"{provider_slug}/{normalized_model}" if normalized_model else provider_slug

    provider_slug = normalize_provider_slug(provider_hint) or infer_provider_slug_from_model(model)
    if not provider_slug:
        return model
    return f"{provider_slug}/{model}"


def build_welcome_agents_info(
    agent_ids: Sequence[str],
    agent_models: Mapping[str, str],
    provider_hints: Mapping[str, str],
) -> list[dict[str, str]]:
    """Build welcome-screen agent metadata with provider/model display names."""
    agents_info_list: list[dict[str, str]] = []
    for agent_id in agent_ids:
        raw_model = str(agent_models.get(agent_id, "") or "").strip()
        provider_model = to_provider_model(raw_model, provider_hints.get(agent_id))
        agents_info_list.append(
            {
                "id": agent_id,
                "model": provider_model,
            },
        )
    return agents_info_list
