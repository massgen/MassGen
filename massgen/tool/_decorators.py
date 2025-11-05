# -*- coding: utf-8 -*-
"""Decorators for custom tool functions."""

from typing import Callable


def context_params(*param_names: str) -> Callable[[Callable], Callable]:
    """Mark parameters for auto-injection from ExecutionContext.

    Parameters marked with this decorator will be:
    1. Excluded from the LLM schema (not visible to the model)
    2. Automatically injected from execution_context at runtime

    This is useful for parameters that should come from the backend runtime
    context rather than from the LLM, such as:
    - messages: Conversation history
    - agent_id: Current agent identifier
    - backend_name: Backend provider name
    - current_stage: Current coordination stage

    Args:
        *param_names: Names of parameters to mark as context parameters

    Returns:
        Decorator function that marks the parameters

    Example:
        >>> from massgen.tool import context_params, ExecutionResult
        >>> from typing import List, Dict, Any
        >>>
        >>> @context_params("messages", "agent_id")
        >>> async def analyze_conversation(
        ...     query: str,  # LLM provides this
        ...     messages: List[Dict[str, Any]],  # Auto-injected from context
        ...     agent_id: str,  # Auto-injected from context
        ... ) -> ExecutionResult:
        ...     '''Analyze conversation with full context.'''
        ...     # messages and agent_id are automatically filled from execution_context
        ...     system_msg = next((m for m in messages if m.get("role") == "system"), None)
        ...     return ExecutionResult(...)

    Note:
        The execution_context is provided by the backend when executing tools.
        Only parameters marked by this decorator will be injected from the context.
    """

    def decorator(func: Callable) -> Callable:
        """Store context parameter names in function metadata."""
        func.__context_params__ = set(param_names)
        return func

    return decorator
