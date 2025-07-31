"""
Gemini backend implementation - DEFERRED

DECISION: Deferred until Gemini API supports combining builtin tools (code_execution, grounding) 
with user-defined function_declarations in the same request.

CURRENT API LIMITATIONS (2025):
- Regular API: Can only use (code_execution + grounding) OR function_declarations, not both
- Live API: Supports all tools together but is experimental/preview with session limits
- MassGen v3 architecture requires both builtin tools AND user functions simultaneously

RATIONALE FOR DEFERRING:
- v0.0.1 used workarounds/hacks that we want to avoid in v3
- API limitations would force architectural compromises
- Google likely to add multi-tool support to regular API in future
- Better to wait for proper API support than implement suboptimal solution

STATUS: Monitoring Gemini API updates for multi-tool support in regular API
WHEN TO REVISIT: When Gemini regular API supports (builtin tools + function_declarations)

For now, MassGen v3 focuses on OpenAI (full tool support) and Grok (web search support).
"""

# Implementation deferred - see rationale above
# class GeminiBackend(LLMBackend):
#     """Google Gemini backend - deferred due to API tool limitations."""
#     pass