"""
Hook manager for MCP function calls.

Manages registration and retrieval of hooks for MCP tool execution.
"""

from typing import Dict, List
try:
    from .hooks import HookType, FunctionHook
except ImportError:
    from hooks import HookType, FunctionHook


class FunctionHookManager:
    """Global hook manager for MCP functions."""

    def __init__(self):
        self.global_hooks: Dict[HookType, List[FunctionHook]] = {
            hook_type: [] for hook_type in HookType
        }
        self.function_specific_hooks: Dict[str, Dict[HookType, List[FunctionHook]]] = {}

    def register_global_hook(self, hook_type: HookType, hook: FunctionHook) -> None:
        """Register a hook that applies to all functions."""
        self.global_hooks[hook_type].append(hook)

    def register_function_hook(self, function_name: str, hook_type: HookType, hook: FunctionHook) -> None:
        """Register a hook for a specific function."""
        if function_name not in self.function_specific_hooks:
            self.function_specific_hooks[function_name] = {ht: [] for ht in HookType}
        self.function_specific_hooks[function_name][hook_type].append(hook)

    def get_hooks_for_function(self, function_name: str) -> Dict[HookType, List[FunctionHook]]:
        """Get all applicable hooks for a function (global + specific)."""
        all_hooks = {hook_type: [] for hook_type in HookType}

        # Add global hooks
        for hook_type, hooks in self.global_hooks.items():
            all_hooks[hook_type].extend(hooks)

        # Add function-specific hooks
        if function_name in self.function_specific_hooks:
            for hook_type, hooks in self.function_specific_hooks[function_name].items():
                all_hooks[hook_type].extend(hooks)

        return all_hooks

    def clear_hooks(self) -> None:
        """Clear all registered hooks."""
        for hook_type in HookType:
            self.global_hooks[hook_type].clear()
        self.function_specific_hooks.clear()


# Global instance
function_hook_manager = FunctionHookManager()