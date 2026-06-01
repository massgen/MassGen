"""Question irreversibility analysis, extracted from Orchestrator.

The analyzer asks one of the orchestrator's agents to decide whether the
user's question involves MCP tools with irreversible outcomes, and which
specific MCP tools (if any) should be blocked. The orchestrator keeps a
thin async delegator so existing call sites and tests (which call
``orchestrator._analyze_question_irreversibility(...)``) keep working.

All cross-cutting helpers (``log_orchestrator_activity``,
``_format_planning_mode_ui``) are accessed through the orchestrator
back-reference so test monkeypatches on the orchestrator instance keep
applying. ``log_orchestrator_activity`` itself is resolved lazily via
``massgen.orchestrator`` so any test that patches the symbol at the
module level continues to win.
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class QuestionIrreversibilityAnalyzer:
    """Analyze whether a user's question requires irreversible MCP tools."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def _log_activity(*args: Any, **kwargs: Any) -> None:
        """Route to ``log_orchestrator_activity`` via the orchestrator module.

        Using a lazy import here (instead of a module-level import) preserves
        the ability for tests to ``patch('massgen.orchestrator.log_orchestrator_activity', ...)``
        and have the patch take effect even when this code runs from the
        collaborator module.
        """
        from massgen import orchestrator as _orch_mod

        _orch_mod.log_orchestrator_activity(*args, **kwargs)

    async def analyze(
        self,
        user_question: str,
        conversation_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze if the user's question involves irreversible MCP operations.

        Args:
            user_question: The user's question/request.
            conversation_context: Full conversation context including history.

        Returns:
            Dict with ``has_irreversible`` (bool) and ``blocked_tools`` (set).
        """
        orchestrator = self._orchestrator

        print("=" * 80, flush=True)
        print(
            "🔍 [INTELLIGENT PLANNING MODE] Analyzing question for irreversibility...",
            flush=True,
        )
        print(
            f"📝 Question: {user_question[:100]}{'...' if len(user_question) > 100 else ''}",
            flush=True,
        )
        print("=" * 80, flush=True)

        # Select a random agent for analysis
        available_agents = [aid for aid, agent in orchestrator.agents.items() if agent.backend is not None]
        if not available_agents:
            # No agents available, default to safe mode (planning enabled, block ALL)
            self._log_activity(
                orchestrator.orchestrator_id,
                "No agents available for irreversibility analysis, defaulting to planning mode",
                {},
            )
            return {"has_irreversible": True, "blocked_tools": set()}

        analyzer_agent_id = random.choice(available_agents)
        analyzer_agent = orchestrator.agents[analyzer_agent_id]

        print(f"🤖 Selected analyzer agent: {analyzer_agent_id}", flush=True)

        # Check if agents have isolated workspaces
        has_isolated_workspaces = False
        workspace_info = []
        for agent_id, agent in orchestrator.agents.items():
            if agent.backend and agent.backend.filesystem_manager:
                cwd = agent.backend.filesystem_manager.cwd
                if cwd and "workspace" in os.path.basename(cwd).lower():
                    has_isolated_workspaces = True
                    workspace_info.append(f"{agent_id}: {cwd}")

        if has_isolated_workspaces:
            print(
                "🔒 Detected isolated agent workspaces - filesystem ops will be allowed",
                flush=True,
            )

        self._log_activity(
            orchestrator.orchestrator_id,
            "Analyzing question irreversibility",
            {
                "analyzer_agent": analyzer_agent_id,
                "question_preview": user_question[:100] + "..." if len(user_question) > 100 else user_question,
                "has_isolated_workspaces": has_isolated_workspaces,
            },
        )

        # Build analysis prompt - now asking for specific tool names
        workspace_context = ""
        if has_isolated_workspaces:
            workspace_context = """
IMPORTANT - ISOLATED WORKSPACES:
The agents are working in isolated temporary workspaces (directories containing "workspace" in their name).
Filesystem operations (read_file, write_file, delete_file, list_files, etc.) within these isolated workspaces are SAFE and REVERSIBLE.
They should NOT be blocked because:
- These are temporary directories specific to this coordination session
- Files created/modified are isolated from external systems
- Changes are contained within the agent's sandbox
- The workspace can be cleared after coordination

Only block filesystem operations if they explicitly target paths OUTSIDE the isolated workspace.
"""

        analysis_prompt = f"""You are analyzing whether a user's request involves operations with irreversible outcomes.

USER REQUEST:
{user_question}
{workspace_context}
CONTEXT:
Your task is to determine if executing this request would involve MCP (Model Context Protocol) tools that have irreversible outcomes, and if so, identify which specific tools should be blocked.

MCP tools follow the naming convention: mcp__<server>__<tool_name>
Examples:
- mcp__discord__discord_send (irreversible - sends messages)
- mcp__discord__discord_read_channel (reversible - reads messages)
- mcp__twitter__post_tweet (irreversible - posts publicly)
- mcp__twitter__search_tweets (reversible - searches)
- mcp__filesystem__write_file (SAFE in isolated workspace - writes to temporary files)
- mcp__filesystem__read_file (reversible - reads files)

IRREVERSIBLE OPERATIONS:
- Sending messages (discord_send, slack_send, etc.)
- Posting content publicly (post_tweet, create_post, etc.)
- Deleting files or data OUTSIDE isolated workspace (delete_file on external paths, remove_data, etc.)
- Modifying external systems (write_file to external paths, update_record, etc.)
- Creating permanent records (create_issue, add_comment, etc.)
- Executing commands that change state (run_command, execute_script, etc.)

REVERSIBLE OPERATIONS (DO NOT BLOCK):
- Reading messages or data (read_channel, get_messages, etc.)
- Searching or querying information (search_tweets, query_data, etc.)
- Listing files or resources (list_files, list_channels, etc.)
- Fetching data from APIs (get_user, fetch_data, etc.)
- Viewing information (view_channel, get_info, etc.)
- Filesystem operations IN ISOLATED WORKSPACE (write_file, read_file, delete_file, list_files when in workspace*)

Respond in this EXACT format:
IRREVERSIBLE: YES/NO
BLOCKED_TOOLS: tool1, tool2, tool3

If IRREVERSIBLE is NO, leave BLOCKED_TOOLS empty.
If IRREVERSIBLE is YES, list the specific MCP tool names that should be blocked (e.g., mcp__discord__discord_send).

Your answer:"""

        # Create messages for the analyzer
        analysis_messages = [
            {"role": "user", "content": analysis_prompt},
        ]

        try:
            # Stream response from analyzer agent (but don't show to user)
            response_text = ""
            async for chunk in analyzer_agent.backend.stream_with_tools(
                messages=analysis_messages,
                tools=[],  # No tools needed for simple analysis
                agent_id=analyzer_agent_id,
            ):
                if chunk.type == "content" and chunk.content:
                    response_text += chunk.content

            # Parse response
            response_clean = response_text.strip()
            has_irreversible = False
            blocked_tools = set()

            # Parse IRREVERSIBLE line
            found_irreversible_line = False
            for line in response_clean.split("\n"):
                line = line.strip()
                if line.startswith("IRREVERSIBLE:"):
                    found_irreversible_line = True
                    # Extract the value after the colon
                    value = line.split(":", 1)[1].strip().upper()
                    # Check if the first word is YES
                    has_irreversible = value.startswith("YES")
                elif line.startswith("BLOCKED_TOOLS:"):
                    # Extract tool names after the colon
                    tools_part = line.split(":", 1)[1].strip()
                    if tools_part:
                        # Split by comma and clean up whitespace
                        blocked_tools = {tool.strip() for tool in tools_part.split(",") if tool.strip()}

            # Fallback: If no structured format found, look for YES/NO in the response
            if not found_irreversible_line:
                print(
                    "⚠️  [WARNING] No 'IRREVERSIBLE:' line found, using fallback parsing",
                    flush=True,
                )
                response_upper = response_clean.upper()
                # Look for clear YES/NO indicators
                if "YES" in response_upper and "NO" not in response_upper:
                    has_irreversible = True
                elif "NO" in response_upper:
                    has_irreversible = False
                else:
                    # Default to safe mode if unclear
                    has_irreversible = True

            self._log_activity(
                orchestrator.orchestrator_id,
                "Irreversibility analysis complete",
                {
                    "analyzer_agent": analyzer_agent_id,
                    "response": response_clean[:100],
                    "has_irreversible": has_irreversible,
                    "blocked_tools_count": len(blocked_tools),
                },
            )

            # Display nice UI box for planning mode status. Route through the
            # orchestrator so tests that monkeypatch the formatter still win.
            ui_box = orchestrator._format_planning_mode_ui(
                has_irreversible=has_irreversible,
                blocked_tools=blocked_tools,
                has_isolated_workspaces=has_isolated_workspaces,
                user_question=user_question,
            )
            print(ui_box, flush=True)

            return {
                "has_irreversible": has_irreversible,
                "blocked_tools": blocked_tools,
            }

        except Exception as e:
            # On error, default to safe mode (planning enabled, block ALL)
            self._log_activity(
                orchestrator.orchestrator_id,
                "Irreversibility analysis failed, defaulting to planning mode",
                {"error": str(e)},
            )
            return {"has_irreversible": True, "blocked_tools": set()}
