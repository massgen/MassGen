#!/usr/bin/env python3
"""Question execution and interactive-mode run loops.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..agent_config import AgentConfig
from ..chat_agent import SingleAgent
from ..logger_config import is_debug_mode as _is_debug_mode
from ..logger_config import logger, save_execution_metadata, setup_logging
from ..orchestrator import Orchestrator

# --- cross-module references within the cli package ---
from ._constants import (
    BRIGHT_BLUE,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_RED,
    BRIGHT_WHITE,
    BRIGHT_YELLOW,
    RESET,
    SESSION_STORAGE,
)
from .backends import create_agents_from_config
from .config_loading import _scope_agent_temporary_workspace, _scope_snapshot_storage
from .config_parsing import (
    _apply_orchestrator_runtime_params,
    _parse_coordination_config,
)
from .env import _automation_print
from .input import (
    _restore_terminal_for_input,
    prompt_for_context_paths,
    read_multiline_input_async,
)
from .inspection import _list_all_turns, _show_turn_inspection
from .planning import (
    _disable_evaluation_criteria_generation_for_planning,
    _is_planning_turn,
    _set_planning_checklist_criteria_defaults,
)
from .prompts import (
    build_plan_review_refinement_appendix,
    get_log_analysis_prompt_prefix,
    get_skill_organization_prompt_prefix,
    get_spec_creation_prompt_prefix,
    get_task_planning_prompt_prefix,
    should_include_quick_edit_hint,
)
from .streaming import _build_coordination_ui


def _has_evolving_skills_enabled(agents: dict[str, Any] | None) -> bool:
    """Return True when any active agent has evolving skills enabled."""
    if not agents:
        return False

    for agent in agents.values():
        backend = getattr(agent, "backend", None)
        backend_config = getattr(backend, "config", None)
        if isinstance(backend_config, dict) and backend_config.get(
            "auto_discover_custom_tools",
            False,
        ):
            return True
    return False


def _should_use_conversation_history_for_turn(
    conversation_history: list[dict[str, Any]],
    mode_state: Any,
    agents: dict[str, Any] | None,
) -> bool:
    """Determine whether prior conversation history should be injected this turn."""
    if not conversation_history:
        return False

    if not (mode_state and getattr(mode_state, "plan_mode", None) == "execute"):
        return True

    # Execute turns normally run from task artifacts only. Keep history only when
    # evolving skills are enabled so iterative workflow refinement can use prior context.
    return _has_evolving_skills_enabled(agents)


def _persist_generated_personas_and_criteria(orchestrator, session_info: dict[str, Any]) -> None:
    """Store generated personas and evaluation criteria into ``session_info``.

    Lets subsequent turns reuse personas/criteria instead of regenerating them.
    Shared by the Rich and Textual interactive turn handlers.
    """
    if orchestrator.get_generated_personas():
        session_info["generated_personas"] = orchestrator.get_generated_personas()
    if orchestrator.get_generated_evaluation_criteria():
        session_info["generated_evaluation_criteria"] = [{"id": c.id, "text": c.text, "category": c.category} for c in orchestrator.get_generated_evaluation_criteria()]


def _extract_models_for_session(agents: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    """Collect per-agent model names for session metadata.

    Returns ``(models_dict, model_name_for_registry)`` where the registry name
    is a comma-separated list of unique models (preserving order), or ``None``
    when no agent exposes a model.
    """
    models_dict: dict[str, str] = {}
    for agent_id, agent in agents.items():
        if hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
            model = agent.config.backend_params.get("model")
            if model:
                models_dict[agent_id] = model
    model_name_for_registry = None
    if models_dict:
        unique_models = list(dict.fromkeys(models_dict.values()))
        model_name_for_registry = ", ".join(unique_models)
    return models_dict, model_name_for_registry


def _build_agent_display_info(
    agents: dict[str, Any] | None,
    original_config: dict[str, Any] | None,
) -> tuple[list[str], dict[str, str]]:
    """Derive ``(agent_ids, agent_models)`` for the interactive welcome screen.

    Handles both the already-created case (read from agent backends/config) and
    the deferred-creation case (read ids/models from the raw config so the
    welcome screen can render before agents exist).
    """
    agent_models: dict[str, str] = {}
    if agents is not None:
        agent_ids = list(agents.keys())
        for agent_id, agent in agents.items():
            if hasattr(agent, "backend") and hasattr(agent.backend, "model"):
                agent_models[agent_id] = agent.backend.model
            elif hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
                agent_models[agent_id] = agent.config.backend_params.get("model", "")
        return agent_ids, agent_models

    if original_config:
        agent_configs = original_config.get("agents", [])
        if not agent_configs and "agent" in original_config:
            agent_configs = [original_config["agent"]]
    else:
        agent_configs = []
    agent_ids = [ac.get("id", f"agent_{i}") for i, ac in enumerate(agent_configs)]
    for i, ac in enumerate(agent_configs):
        agent_id = ac.get("id", f"agent_{i}")
        # Model can be at top level or nested in backend.
        model = ac.get("model") or ac.get("backend", {}).get("model", "")
        if model:
            agent_models[agent_id] = model
    return agent_ids, agent_models


def _merge_readonly_context_path(config_dict: dict[str, Any], path_str: str, description: str) -> bool:
    """Add a read-only orchestrator context path if missing.

    Returns True if a new path was appended, False if it was already present
    (or *path_str* is empty). Mutates ``config_dict`` in place.
    """
    if not path_str:
        return False

    orchestrator_section = config_dict.setdefault("orchestrator", {})
    existing = orchestrator_section.get("context_paths", [])
    if not isinstance(existing, list):
        existing = []

    normalized_target = str(Path(path_str).resolve())
    normalized_existing = set()
    for item in existing:
        item_path = item.get("path") if isinstance(item, dict) else item
        if not item_path:
            continue
        try:
            normalized_existing.add(str(Path(item_path).resolve()))
        except Exception:
            normalized_existing.add(str(item_path))

    if normalized_target in normalized_existing:
        orchestrator_section["context_paths"] = existing
        return False

    existing.append(
        {
            "path": normalized_target,
            "permission": "read",
            "description": description,
        },
    )
    orchestrator_section["context_paths"] = existing
    return True


def _agents_have_context_path(current_agents: dict[str, Any] | None, path_str: str) -> bool:
    """Check whether all active agents already have a specific context path."""
    if not current_agents:
        return False

    target = str(Path(path_str).resolve())
    for agent in current_agents.values():
        backend = getattr(agent, "backend", None)
        fm = getattr(backend, "filesystem_manager", None)
        ppm = getattr(fm, "path_permission_manager", None)
        if ppm is None:
            return False

        found = False
        for ctx in ppm.get_context_paths():
            ctx_path = ctx.get("path") if isinstance(ctx, dict) else None
            if not ctx_path:
                continue
            try:
                normalized_ctx = str(Path(ctx_path).resolve())
            except Exception:
                normalized_ctx = str(ctx_path)
            if normalized_ctx == target:
                found = True
                break
        if not found:
            return False
    return True


def _load_persisted_personas_and_criteria(orchestrator_config, session_info):
    """Reload personas / evaluation criteria persisted from a prior turn.

    Values are returned only when the corresponding generator has
    ``persist_across_turns`` enabled. Returns ``(personas, criteria)`` where each
    element is ``None`` when not applicable. Inverse of
    :func:`_persist_generated_personas_and_criteria`.
    """
    cc = getattr(orchestrator_config, "coordination_config", None)

    generated_personas = None
    if cc and getattr(cc, "persona_generator", None) and cc.persona_generator.persist_across_turns:
        generated_personas = session_info.get("generated_personas")
        if generated_personas:
            logger.info("[Session] Reusing persisted personas from previous turn")

    generated_evaluation_criteria = None
    ecg = getattr(cc, "evaluation_criteria_generator", None) if cc else None
    if ecg and ecg.persist_across_turns:
        raw_criteria = session_info.get("generated_evaluation_criteria")
        if raw_criteria:
            from ..evaluation_criteria_generator import GeneratedCriterion

            generated_evaluation_criteria = [
                GeneratedCriterion(
                    id=c.get("id", f"E{i + 1}"),
                    text=c.get("text") or c.get("description") or c.get("name", ""),
                    category=c.get("category", "standard"),
                )
                for i, c in enumerate(raw_criteria)
                if c.get("text") or c.get("description") or c.get("name")
            ]
            logger.info("[Session] Reusing persisted evaluation criteria from previous turn")

    return generated_personas, generated_evaluation_criteria


def _reload_turn_history(session_info, session_id):
    """Return ``(previous_turns, winning_agents_history)`` for multi-turn memory.

    Prefers values already present in ``session_info``; otherwise restores them
    from session storage. Shared by the Rich and Textual turn handlers.
    """
    previous_turns = session_info.get("previous_turns", [])
    winning_agents_history = session_info.get("winning_agents_history", [])

    if not previous_turns and not winning_agents_history and session_id:
        from massgen.session import restore_session

        try:
            session_state = restore_session(session_id, SESSION_STORAGE)
            if session_state:
                previous_turns = session_state.previous_turns
                winning_agents_history = session_state.winning_agents_history
        except Exception as e:
            # Session doesn't exist yet or has no turns - fine for new sessions.
            logger.debug(f"Could not restore session for previous turns: {e}")

    return previous_turns, winning_agents_history


async def handle_session_persistence(
    orchestrator,
    question: str,
    session_info: dict[str, Any],
    config_path: str | None = None,
    model: str | None = None,
    log_directory: str | None = None,
    models_dict: dict[str, str] | None = None,
) -> tuple[str | None, int, str | None]:
    """
    Handle session persistence after orchestrator completes.

    Also registers session in registry on first successful turn.

    Returns:
        tuple: (session_id, updated_turn_number, normalized_answer)
    """
    # Get final result from orchestrator
    final_result = orchestrator.get_final_result()
    if not final_result:
        # No filesystem work to persist
        return (
            session_info.get("session_id"),
            session_info.get("current_turn", 0),
            None,
        )

    # Initialize or reuse session ID
    session_id = session_info.get("session_id")
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Increment turn
    current_turn = session_info.get("current_turn", 0) + 1

    # Create turn directory
    session_dir = Path(SESSION_STORAGE) / session_id
    turn_dir = session_dir / f"turn_{current_turn}"
    turn_dir.mkdir(parents=True, exist_ok=True)

    # Normalize answer paths
    final_answer = final_result["final_answer"]
    workspace_path = final_result.get("workspace_path")
    turn_workspace_path = (turn_dir / "workspace").resolve()  # Make absolute

    if workspace_path:
        # Replace workspace paths in answer with absolute path
        normalized_answer = final_answer.replace(
            workspace_path,
            str(turn_workspace_path),
        )
    else:
        normalized_answer = final_answer

    # Save normalized answer
    answer_file = turn_dir / "answer.txt"
    answer_file.write_text(normalized_answer, encoding="utf-8")

    # Save metadata
    metadata = {
        "turn": current_turn,
        "timestamp": datetime.now().isoformat(),
        "winning_agent": final_result["winning_agent_id"],
        "task": question,
        "session_id": session_id,
    }

    # Add model information if available
    if models_dict:
        metadata["models"] = models_dict
        # Also add winning agent's model for quick reference
        winning_agent_id = final_result["winning_agent_id"]
        if winning_agent_id in models_dict:
            metadata["winning_model"] = models_dict[winning_agent_id]

    metadata_file = turn_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Save winning agents history for memory sharing across turns
    # This allows the orchestrator to restore winner tracking when recreated
    if final_result.get("winning_agents_history"):
        winning_agents_file = session_dir / "winning_agents_history.json"
        winning_agents_file.write_text(
            json.dumps(final_result["winning_agents_history"], indent=2),
            encoding="utf-8",
        )
        logger.info(
            f"📚 Saved {len(final_result['winning_agents_history'])} winning agent(s) to session storage",
        )

    # Create/update session summary for easy viewing
    session_summary_file = session_dir / "SESSION_SUMMARY.txt"
    summary_lines = []

    if session_summary_file.exists():
        summary_lines = session_summary_file.read_text(encoding="utf-8").splitlines()
    else:
        summary_lines.append("=" * 80)
        summary_lines.append(f"Multi-Turn Session: {session_id}")
        summary_lines.append("=" * 80)
        summary_lines.append("")

    # Add turn separator and info
    summary_lines.append("")
    summary_lines.append("=" * 80)
    summary_lines.append(f"TURN {current_turn}")
    summary_lines.append("=" * 80)
    summary_lines.append(f"Timestamp: {metadata['timestamp']}")
    summary_lines.append(f"Winning Agent: {metadata['winning_agent']}")
    summary_lines.append(f"Task: {question}")
    summary_lines.append(f"Workspace: {turn_workspace_path}")
    summary_lines.append(f"Answer: See {(turn_dir / 'answer.txt').resolve()}")
    summary_lines.append("")

    session_summary_file.write_text("\n".join(summary_lines), encoding="utf-8")

    # Copy workspace if it exists
    if workspace_path and Path(workspace_path).exists():
        shutil.copytree(
            workspace_path,
            turn_workspace_path,
            dirs_exist_ok=True,
            symlinks=True,
            ignore_dangling_symlinks=True,
        )

    # Note: Session is already registered when created (before first turn runs)
    # No need to register here

    return (session_id, current_turn, normalized_answer)


async def run_question_with_history(
    question: str,
    agents: dict[str, SingleAgent],
    ui_config: dict[str, Any],
    history: list[dict[str, Any]],
    session_info: dict[str, Any],
    **kwargs,
) -> tuple[str, str | None, int, bool]:
    """Run MassGen with a question and conversation history.

    Returns:
        tuple: (response_text, session_id, turn_number, was_cancelled)
            - was_cancelled: True if user cancelled with Ctrl+C (partial progress may be saved)
    """
    # Build messages including history
    messages = history.copy()
    messages.append({"role": "user", "content": question})

    # In multiturn mode with session persistence, ALWAYS use orchestrator for proper final/ directory creation
    # Single agents in multiturn mode need the orchestrator to create session artifacts (final/, workspace/, etc.)
    # The orchestrator handles single agents efficiently by skipping unnecessary coordination

    # Create orchestrator config with timeout settings
    timeout_config = kwargs.get("timeout_config")
    orchestrator_config = AgentConfig()
    if timeout_config:
        orchestrator_config.timeout_config = timeout_config

    # Get orchestrator parameters from config
    orchestrator_cfg = kwargs.get("orchestrator", {})

    # Get orchestrator-level NLIP configuration
    orchestrator_enable_nlip = orchestrator_cfg.get("enable_nlip", False)
    orchestrator_nlip_config = orchestrator_cfg.get("nlip_config", {})

    if orchestrator_enable_nlip:
        logger.info(
            "[CLI] Orchestrator-level NLIP enabled (will propagate to capable agents)",
        )

    _apply_orchestrator_runtime_params(orchestrator_config, orchestrator_cfg)

    # Get context sharing parameters
    snapshot_storage = _scope_snapshot_storage(orchestrator_cfg.get("snapshot_storage"))
    agent_temporary_workspace = _scope_agent_temporary_workspace(
        orchestrator_cfg.get("agent_temporary_workspace"),
    )

    # Parse coordination config if present
    if "coordination" in orchestrator_cfg:
        coord_cfg = orchestrator_cfg["coordination"]
        logger.info(f"[CLI] coord_cfg keys: {list(coord_cfg.keys())}")
        orchestrator_config.coordination_config = _parse_coordination_config(coord_cfg)

    # Get session_id from session_info (will be generated in save_final_state if not exists)
    session_id = session_info.get("session_id")

    # Restore multi-turn memory (prefers session_info, else session storage).
    previous_turns, winning_agents_history = _reload_turn_history(session_info, session_id)

    # Reload personas/criteria persisted from a prior turn (when enabled).
    generated_personas, generated_evaluation_criteria = _load_persisted_personas_and_criteria(
        orchestrator_config,
        session_info,
    )

    orchestrator = Orchestrator(
        agents=agents,
        config=orchestrator_config,
        session_id=session_id,  # Pass CLI session_id for memory archiving
        snapshot_storage=snapshot_storage,
        agent_temporary_workspace=agent_temporary_workspace,
        previous_turns=previous_turns,
        winning_agents_history=winning_agents_history,  # Restore for memory sharing
        dspy_paraphraser=kwargs.get("dspy_paraphraser"),
        enable_rate_limit=kwargs.get("enable_rate_limit", False),
        enable_nlip=orchestrator_enable_nlip,
        nlip_config=orchestrator_nlip_config,
        generated_personas=generated_personas,  # Only if persist_across_turns=True
        generated_evaluation_criteria=generated_evaluation_criteria,
        raw_config=kwargs.get("raw_config"),
    )

    # Apply pre-populated workspaces from incomplete turns (passed from interactive mode)
    pre_populated_workspaces = kwargs.pop("pre_populated_workspaces", None)
    if pre_populated_workspaces:
        orchestrator._pre_populated_workspaces = pre_populated_workspaces

    # Detect main_agent for checkpoint coordination mode
    # MCP injection is handled by orchestrator._init_checkpoint_tool() in __init__
    _ckpt_main_agent_id = None
    raw_agents_for_checkpoint = kwargs.get("agents_config", [])
    if isinstance(raw_agents_for_checkpoint, list):
        for agent_data in raw_agents_for_checkpoint:
            if isinstance(agent_data, dict) and agent_data.get("main_agent") is True:
                _ckpt_main_agent_id = agent_data.get("id")
                break

    # Fallback: if checkpoint is enabled but no main_agent is set,
    # default to the first agent
    if not _ckpt_main_agent_id:
        if getattr(orchestrator_config, "coordination_config", None) and getattr(
            orchestrator_config.coordination_config,
            "checkpoint_enabled",
            False,
        ):
            _ckpt_main_agent_id = sorted(agents.keys())[0] if agents else None

    if _ckpt_main_agent_id and _ckpt_main_agent_id in agents:
        orchestrator.set_main_agent(_ckpt_main_agent_id)

    # Parse per-agent subtask assignments for decomposition mode
    if orchestrator_config.coordination_mode == "decomposition":
        raw_agents = kwargs.get("agents_config", [])
        if isinstance(raw_agents, list):
            for agent_data in raw_agents:
                if isinstance(agent_data, dict):
                    aid = agent_data.get("id", "")
                    subtask = agent_data.get("subtask")
                    if subtask:
                        orchestrator._agent_subtasks[aid] = subtask

    # Create a fresh UI instance for each question to ensure clean state
    ui = _build_coordination_ui(ui_config)

    # Determine display mode text
    if len(agents) == 1:
        mode_text = "Single Agent (Orchestrator)"
    else:
        mode_text = "Multi-Agent"

        # Get coordination config from YAML (if present)
        orchestrator_kwargs = kwargs.get("orchestrator", {})
        coordination_settings = orchestrator_kwargs.get("coordination", {})
        if coordination_settings:
            orchestrator_config.coordination_config = _parse_coordination_config(coordination_settings)

    print(f"\n🤖 {BRIGHT_CYAN}{mode_text}{RESET}", flush=True)
    print(f"Agents: {', '.join(agents.keys())}", flush=True)
    if history:
        print(f"History: {len(history) // 2} previous exchanges", flush=True)
    print(f"Question: {question}", flush=True)
    print("\n" + "=" * 60, flush=True)

    # For multi-agent with history, we need to use a different approach
    # that maintains coordination UI display while supporting conversation context

    # Setup graceful cancellation handling
    from massgen.cancellation import CancellationManager, CancellationRequested
    from massgen.session import save_partial_turn

    cancellation_mgr = CancellationManager()

    # Determine session ID for partial saves (may not exist yet for first turn)
    partial_session_id = session_info.get("session_id") or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    partial_turn_number = session_info.get("current_turn", 0) + 1

    # Check if we're in multi-turn mode (passed from caller)
    multi_turn_mode = session_info.get("multi_turn", False)

    def save_partial_progress(partial_result):
        """Callback to save partial progress when cancelled."""
        try:
            save_partial_turn(
                session_id=partial_session_id,
                turn_number=partial_turn_number,
                question=question,
                partial_result=partial_result,
                session_storage=SESSION_STORAGE,
            )
        except Exception as e:
            logger.warning(f"Failed to save partial progress: {e}")

    # Register cancellation handler (multi_turn mode returns to prompt instead of exiting)
    cancellation_mgr.register(
        orchestrator,
        save_partial_progress,
        multi_turn=multi_turn_mode,
    )

    # Restart loop (similar to multiturn pattern) - continues until no restart pending
    response_content = None
    was_cancelled = False
    try:
        while True:
            if history and len(history) > 0:
                # Use coordination UI with conversation context
                # Extract current question from messages
                current_question = messages[-1].get("content", question) if messages else question

                # Pass the full message context to the UI coordination
                response_content = await ui.coordinate_with_context(
                    orchestrator,
                    current_question,
                    messages,
                )
            else:
                # Standard coordination for new conversations
                response_content = await ui.coordinate(orchestrator, question)

            # Check if restart is needed
            if hasattr(orchestrator, "restart_pending") and orchestrator.restart_pending:
                # Restart needed - create fresh UI for next attempt
                print(f"\n{'=' * 80}")
                print(
                    f"🔄 Restarting coordination - Attempt {orchestrator.current_attempt + 1}/{orchestrator.max_attempts}",
                )
                print(f"{'=' * 80}\n")

                # Reset all agent backends to ensure clean state for next attempt
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent.backend, "reset_state"):
                        try:
                            import inspect

                            result = agent.backend.reset_state()
                            # Handle both sync and async reset_state
                            if inspect.iscoroutine(result):
                                await result
                            logger.info(f"Reset backend state for {agent_id}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to reset backend for {agent_id}: {e}",
                            )

                # Reuse existing UI if it supports restart, otherwise recreate
                try:
                    ui.prepare_for_restart(
                        orchestrator,
                        orchestrator.current_attempt + 1,
                        orchestrator.max_attempts,
                    )
                except Exception:
                    logger.warning("prepare_for_restart failed, recreating UI")
                    ui = _build_coordination_ui(ui_config)

                # Reset cancellation state for new attempt
                cancellation_mgr.reset()

                # Continue to next attempt
                continue
            else:
                # Coordination complete - exit loop
                break
    except CancellationRequested as cancel_exc:
        # In multi-turn mode, CancellationRequested is raised instead of KeyboardInterrupt
        # This allows us to return to the prompt instead of exiting
        was_cancelled = True

        if cancel_exc.partial_saved:
            print(
                f"\n{BRIGHT_YELLOW}⏸️  Turn cancelled. Partial progress saved.{RESET}",
                flush=True,
            )
        else:
            print(f"\n{BRIGHT_YELLOW}⏸️  Turn cancelled.{RESET}", flush=True)

        # Build cancelled turn history entry based on current phase
        # Import the helper function
        from massgen.session._state import _build_cancelled_turn_history_entry

        # Build partial result dict from orchestrator state
        answers = {}
        for agent_id, state in orchestrator.agent_states.items():
            if state.answer:
                answers[agent_id] = {
                    "answer": state.answer,
                    "has_voted": state.has_voted,
                    "votes": state.votes if state.has_voted else None,
                }

        active_agents = [state for state in orchestrator.agent_states.values() if not state.is_killed]
        voting_complete = all(state.has_voted for state in active_agents) if active_agents else False

        partial_result = {
            "phase": orchestrator.workflow_phase,
            "selected_agent": orchestrator._selected_agent,
            "answers": answers,
            "voting_complete": voting_complete,
        }

        # Build the history entry
        response_content = _build_cancelled_turn_history_entry(partial_result, question)

        # If cancelled during final presentation and we have a selected winner, show their answer
        if orchestrator._selected_agent and orchestrator.workflow_phase == "presenting":
            selected_agent_id = orchestrator._selected_agent
            agent_state = orchestrator.agent_states.get(selected_agent_id)
            if agent_state and agent_state.answer:
                print(f"\n{BRIGHT_CYAN}📋 Selected winner: {selected_agent_id}{RESET}")
                print(f"{BRIGHT_WHITE}{'-' * 60}{RESET}")
                print(agent_state.answer)
                print(f"{BRIGHT_WHITE}{'-' * 60}{RESET}")

        logger.info("Turn cancelled by user in multi-turn mode")
    finally:
        # Always unregister the cancellation handler
        cancellation_mgr.unregister()

    # Copy final results from attempt to turn root (turn_N/final/)
    # Only copy if we're in an attempt subdirectory
    try:
        import shutil

        from massgen.logger_config import get_log_session_dir, get_log_session_dir_base

        # Get the current attempt's final directory (e.g., turn_1/attempt_2/final/)
        attempt_final_dir = get_log_session_dir() / "final"

        # Get the turn-level directory (e.g., turn_1/)
        turn_dir = get_log_session_dir_base()
        turn_final_dir = turn_dir / "final"

        # Only copy if we're in an attempt subdirectory and final exists
        if attempt_final_dir.exists() and attempt_final_dir != turn_final_dir:
            # Remove turn final dir if it already exists
            if turn_final_dir.exists():
                shutil.rmtree(turn_final_dir)

            # Copy attempt's final to turn root
            shutil.copytree(
                attempt_final_dir,
                turn_final_dir,
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
            logger.info(
                f"Copied final results from {attempt_final_dir} to {turn_final_dir}",
            )
    except Exception as e:
        logger.warning(f"Failed to copy final results to turn root: {e}")

    # Handle session persistence if applicable
    # Get metadata for session registration (on first turn)
    from massgen.logger_config import get_log_session_root

    config_path = kwargs.get("config_path")
    model_name = kwargs.get("model_name")
    log_dir = get_log_session_root()
    log_dir_name = log_dir.name  # Get log_YYYYMMDD_HHMMSS from path

    (
        session_id_to_use,
        updated_turn,
        normalized_response,
    ) = await handle_session_persistence(
        orchestrator,
        question,
        session_info,
        config_path=config_path,
        model=model_name,
        log_directory=log_dir_name,
    )

    # Store generated personas/criteria for reuse across turns.
    _persist_generated_personas_and_criteria(orchestrator, session_info)

    # Return normalized response so conversation history has correct paths
    return (
        normalized_response or response_content,
        session_id_to_use,
        updated_turn,
        was_cancelled,
    )


async def run_single_question(
    question: str,
    agents: dict[str, SingleAgent],
    ui_config: dict[str, Any],
    session_id: str | None = None,
    restore_session_if_exists: bool = False,
    return_metadata: bool = False,
    **kwargs,
):
    """Run MassGen with a single question.

    Args:
        question: The question to ask
        agents: Dictionary of agents
        ui_config: UI configuration
        session_id: Optional session ID for persistence
        restore_session_if_exists: If True, attempt to restore previous session data
        return_metadata: If True, return dict with answer and orchestrator data
        **kwargs: Additional arguments

    Returns:
        str: The final response text (when return_metadata=False)
        dict: Dict with 'answer' and 'coordination_result' (when return_metadata=True)
    """
    # Generate session_id if not provided (needed for memory archiving)
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Restore previous session ONLY if explicitly requested (not for new sessions)
    conversation_history = []
    previous_turns = []
    winning_agents_history = []
    current_turn = 0

    if restore_session_if_exists:
        from massgen.logger_config import set_log_turn
        from massgen.session import restore_session

        try:
            session_state = restore_session(session_id, SESSION_STORAGE)
            conversation_history = session_state.conversation_history
            previous_turns = session_state.previous_turns
            winning_agents_history = session_state.winning_agents_history
            current_turn = session_state.current_turn

            # Set turn number for logger (next turn after last completed)
            next_turn = current_turn + 1
            set_log_turn(next_turn)

            print(
                f"📚 Restored {current_turn} previous turn(s) ({len(conversation_history)} messages) from session '{session_id}'",
                flush=True,
            )
            print(f"   Starting turn {next_turn}", flush=True)

            # Use run_question_with_history to include conversation context
            session_info = {
                "session_id": session_id,
                "current_turn": current_turn,
                "previous_turns": previous_turns,
                "winning_agents_history": winning_agents_history,
            }
            response_text, _, _ = await run_question_with_history(
                question,
                agents,
                ui_config,
                conversation_history,
                session_info,
                **kwargs,
            )
            if return_metadata:
                # Session restore doesn't provide full coordination metadata
                return {"answer": response_text, "coordination_result": None}
            return response_text

        except ValueError as e:
            # restore_session failed - no turns found
            print(f"❌ Session error: {e}", flush=True)
            print("Run 'massgen --list-sessions' to see available sessions", flush=True)
            sys.exit(1)

    # Check if we should use orchestrator for single agents (default: False for backward compatibility)
    use_orchestrator_for_single = ui_config.get(
        "use_orchestrator_for_single_agent",
        True,
    )

    if len(agents) == 1 and not use_orchestrator_for_single:
        # Single agent mode with existing SimpleDisplay frontend
        agent = next(iter(agents.values()))

        print(f"\n🤖 {BRIGHT_CYAN}Single Agent Mode{RESET}", flush=True)
        print(f"Agent: {agent.agent_id}", flush=True)
        print(f"Question: {question}", flush=True)
        print("\n" + "=" * 60, flush=True)

        messages = [{"role": "user", "content": question}]
        response_content = ""

        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "builtin_tool_results":
                # Skip builtin_tool_results to avoid duplication with real-time streaming
                continue
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}", flush=True)
                if return_metadata:
                    return {"answer": "", "coordination_result": None}
                return ""

        print("\n" + "=" * 60, flush=True)
        if return_metadata:
            return {"answer": response_content, "coordination_result": None}
        return response_content

    else:
        # Multi-agent mode
        # Create orchestrator config with timeout settings
        timeout_config = kwargs.get("timeout_config")
        orchestrator_config = AgentConfig()
        if timeout_config:
            orchestrator_config.timeout_config = timeout_config

        # Get coordination config from YAML (if present)
        orchestrator_kwargs = kwargs.get("orchestrator", {})
        coordination_settings = orchestrator_kwargs.get("coordination", {})
        if coordination_settings:
            orchestrator_config.coordination_config = _parse_coordination_config(coordination_settings)

        # Get orchestrator parameters from config
        orchestrator_cfg = kwargs.get("orchestrator", {})

        # Get orchestrator-level NLIP configuration
        orchestrator_enable_nlip = orchestrator_cfg.get("enable_nlip", False)
        orchestrator_nlip_config = orchestrator_cfg.get("nlip_config", {})

        if orchestrator_enable_nlip:
            logger.info(
                "[CLI] Orchestrator-level NLIP enabled (will propagate to capable agents)",
            )

        _apply_orchestrator_runtime_params(orchestrator_config, orchestrator_cfg)

        # Get context sharing parameters
        snapshot_storage = _scope_snapshot_storage(orchestrator_cfg.get("snapshot_storage"))
        agent_temporary_workspace = _scope_agent_temporary_workspace(
            orchestrator_cfg.get("agent_temporary_workspace"),
        )

        # Parse coordination config if present
        if "coordination" in orchestrator_cfg:
            coord_cfg = orchestrator_cfg["coordination"]
            orchestrator_config.coordination_config = _parse_coordination_config(coord_cfg)

        orchestrator = Orchestrator(
            agents=agents,
            config=orchestrator_config,
            session_id=session_id,  # Pass CLI session_id for memory archiving
            snapshot_storage=snapshot_storage,
            agent_temporary_workspace=agent_temporary_workspace,
            dspy_paraphraser=kwargs.get("dspy_paraphraser"),
            enable_rate_limit=kwargs.get("enable_rate_limit", False),
            enable_nlip=orchestrator_enable_nlip,
            nlip_config=orchestrator_nlip_config,
            raw_config=kwargs.get("raw_config"),
        )

        # Parse per-agent subtask assignments for decomposition mode
        if orchestrator_config.coordination_mode == "decomposition":
            raw_agents = kwargs.get("agents_config", [])
            if isinstance(raw_agents, list):
                for agent_data in raw_agents:
                    if isinstance(agent_data, dict):
                        aid = agent_data.get("id", "")
                        subtask = agent_data.get("subtask")
                        if subtask:
                            orchestrator._agent_subtasks[aid] = subtask

        # Create a fresh UI instance for each question to ensure clean state
        ui = _build_coordination_ui(ui_config)

        # Only print status if not in quiet mode
        display_type = ui_config.get("display_type", "textual_terminal")
        if display_type not in ("none", "silent"):
            print(f"\n🤖 {BRIGHT_CYAN}Multi-Agent Mode{RESET}", flush=True)
            print(f"Agents: {', '.join(agents.keys())}", flush=True)
            print(f"Question: {question}", flush=True)
            print("\n" + "=" * 60, flush=True)

        # Restart loop (similar to multiturn pattern)
        # Continues calling coordinate() until no restart is pending
        final_response = None
        while True:
            # Call coordinate with current orchestrator state
            final_response = await ui.coordinate(orchestrator, question)

            # Check if restart is needed
            if hasattr(orchestrator, "restart_pending") and orchestrator.restart_pending:
                # Restart needed - create fresh UI for next attempt
                if display_type not in ("none", "silent"):
                    print(f"\n{'=' * 80}")
                    print(
                        f"🔄 Restarting coordination - Attempt {orchestrator.current_attempt + 1}/{orchestrator.max_attempts}",
                    )
                    print(f"{'=' * 80}\n")

                # Set log attempt BEFORE creating new UI so display gets correct path
                # orchestrator.current_attempt was already incremented by _reset_for_restart()
                from massgen.logger_config import set_log_attempt

                set_log_attempt(orchestrator.current_attempt + 1)

                # Save execution metadata for this attempt
                save_execution_metadata(
                    query=question,
                    config_path=None,  # Not available in this scope
                    config_content=None,  # Not available in this scope
                    cli_args={
                        "mode": "coordination_restart",
                        "attempt": orchestrator.current_attempt + 1,
                        "session_id": session_id,
                        "restart_reason": orchestrator.restart_reason,
                    },
                )

                # Reset all agent backends to ensure clean state for next attempt
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent.backend, "reset_state"):
                        try:
                            import inspect

                            result = agent.backend.reset_state()
                            # Handle both sync and async reset_state
                            if inspect.iscoroutine(result):
                                await result
                            logger.info(f"Reset backend state for {agent_id}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to reset backend for {agent_id}: {e}",
                            )

                # Reuse existing UI if it supports restart, otherwise recreate
                try:
                    ui.prepare_for_restart(
                        orchestrator,
                        orchestrator.current_attempt + 1,
                        orchestrator.max_attempts,
                    )
                except Exception:
                    logger.warning("prepare_for_restart failed, recreating UI")
                    ui = _build_coordination_ui(ui_config)

                # Continue to next attempt
                continue
            else:
                # Coordination complete - exit loop
                break

        # Copy final results from attempt to turn root (turn_N/final/)
        # Only copy if we're in an attempt subdirectory
        try:
            import shutil

            from massgen.logger_config import (
                get_log_session_dir,
                get_log_session_dir_base,
            )

            # Get the current attempt's final directory (e.g., turn_1/attempt_2/final/)
            attempt_final_dir = get_log_session_dir() / "final"

            # Get the turn-level directory (e.g., turn_1/)
            turn_dir = get_log_session_dir_base()
            turn_final_dir = turn_dir / "final"

            # Only copy if we're in an attempt subdirectory and final exists
            if attempt_final_dir.exists() and attempt_final_dir != turn_final_dir:
                # Remove turn final dir if it already exists
                if turn_final_dir.exists():
                    shutil.rmtree(turn_final_dir)

                # Copy attempt's final to turn root
                shutil.copytree(
                    attempt_final_dir,
                    turn_final_dir,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                )
                logger.info(
                    f"Copied final results from {attempt_final_dir} to {turn_final_dir}",
                )
        except Exception as e:
            logger.warning(f"Failed to copy final results to turn root: {e}")

        # Print ANSWER: path in automation mode for easy result discovery
        if ui_config.get("automation_mode"):
            try:
                from massgen.logger_config import get_log_session_dir as _get_lsd
                from massgen.logger_config import (
                    get_log_session_dir_base as _get_lsd_base,
                )

                _answer_final_dir = _get_lsd_base() / "final"
                # Also check attempt-level if turn-level doesn't exist
                if not _answer_final_dir.exists():
                    _answer_final_dir = _get_lsd() / "final"
                winning_agent = getattr(orchestrator, "_selected_agent", None)
                if winning_agent and _answer_final_dir.exists():
                    answer_file = _answer_final_dir / winning_agent / "answer.txt"
                    if answer_file.exists():
                        _automation_print(f"ANSWER: {answer_file.resolve()}")
                    else:
                        # Fallback: find any answer.txt in the final dir
                        for agent_dir in sorted(_answer_final_dir.iterdir()):
                            if agent_dir.is_dir():
                                fallback = agent_dir / "answer.txt"
                                if fallback.exists():
                                    _automation_print(f"ANSWER: {fallback.resolve()}")
                                    break
            except Exception:
                pass  # Graceful: don't fail the run if answer path can't be determined

        # Handle session persistence for single-question runs
        if session_id:
            try:
                from massgen.logger_config import get_log_session_root

                # Get metadata for session registration
                config_path_for_session = kwargs.get("config_path")
                model_for_session = kwargs.get("model_name")
                log_dir = get_log_session_root()
                log_dir_name = log_dir.name

                session_info = {
                    "session_id": session_id,
                    "current_turn": 0,  # First turn
                }
                await handle_session_persistence(
                    orchestrator,
                    question,
                    session_info,
                    config_path=config_path_for_session,
                    model=model_for_session,
                    log_directory=log_dir_name,
                )
                logger.info(f"Saved session data for single-question run: {session_id}")
            except Exception as e:
                logger.warning(f"Failed to save session persistence: {e}")

        # Write to output file if specified
        output_file = kwargs.get("output_file")
        if output_file and final_response:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(final_response)
            logger.info(f"Wrote final answer to: {output_file}")
            # Print in automation mode for easy parsing
            _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

        if return_metadata:
            # Get comprehensive coordination result from orchestrator
            coordination_result = orchestrator.get_coordination_result()
            return {
                "answer": final_response,
                "coordination_result": coordination_result,
            }
        return final_response


def print_help_messages():
    """Display help messages using Rich for better formatting."""
    rich_console = Console()

    help_content = """[dim]💬  Type your questions below
💡  Use slash commands: [cyan]/help[/cyan], [cyan]/quit[/cyan], [cyan]/reset[/cyan], [cyan]/status[/cyan], [cyan]/config[/cyan], [cyan]/context[/cyan], [cyan]/inspect[/cyan]
📝  For multi-line input: start with [cyan]\"\"\"[/cyan] or [cyan]\'\'\'[/cyan]
⌨️   Press [cyan]Ctrl+C[/cyan] to exit[/dim]"""

    help_panel = Panel(
        help_content,
        border_style="dim",
        padding=(0, 2),
        width=80,
    )
    rich_console.print(help_panel)


async def _run_textual_turn(
    question: str,
    agents: dict[str, Any],
    ui_config: dict[str, Any],
    conversation_history: list,
    session_info: dict,
    *,
    display,
    adapter,
    context,
    agent_ids,
    config_path,
    original_config,
    orchestrator_cfg,
    debug,
    parse_at_references,
    outer_kwargs,
    **turn_kwargs,
):
    """Run a single turn through the orchestration engine."""
    from massgen.cancellation import CancellationRequested
    from massgen.frontend.coordination_ui import CoordinationUI
    from massgen.frontend.interactive_controller import TurnResult

    try:
        current_turn_num = session_info.get("current_turn", 0)
        sess_id = session_info.get("session_id")
        mode_state = display.get_mode_state()

        analysis_context_path: str | None = None
        if mode_state and mode_state.plan_mode == "analysis" and getattr(mode_state.analysis_config, "target", "log") == "log":
            selected_log_dir = getattr(mode_state.analysis_config, "selected_log_dir", None)
            if selected_log_dir:
                resolved_log_dir = Path(selected_log_dir).resolve()
                if resolved_log_dir.exists():
                    analysis_context_path = str(resolved_log_dir)
                    if original_config:
                        _merge_readonly_context_path(
                            original_config,
                            analysis_context_path,
                            "Analysis target log session",
                        )
                    if isinstance(orchestrator_cfg, dict):
                        _merge_readonly_context_path(
                            {"orchestrator": orchestrator_cfg},
                            analysis_context_path,
                            "Analysis target log session",
                        )
                else:
                    logger.warning(
                        f"[Textual] Analysis target log directory does not exist: {resolved_log_dir}",
                    )

        # Handle deferred agent creation (agents may be None on first turn)
        if agents is None:
            logger.info("[Textual] Creating agents on first prompt...")
            adapter.update_loading_status("🚀 Creating agents...")

            modified_config = original_config.copy()
            if analysis_context_path:
                _merge_readonly_context_path(
                    modified_config,
                    analysis_context_path,
                    "Analysis target log session",
                )
            if parse_at_references:
                # Parse @references from question and inject into config
                from ..path_handling import (
                    PromptParserError,
                    parse_prompt_for_context,
                )

                try:
                    parsed = parse_prompt_for_context(question)
                    if parsed.context_paths:
                        # Inject context paths into orchestrator config
                        orch_cfg = modified_config.get("orchestrator", {})
                        existing_paths = orch_cfg.get("context_paths", [])
                        orch_cfg["context_paths"] = existing_paths + parsed.context_paths
                        modified_config["orchestrator"] = orch_cfg
                        # Update the question to remove @references
                        question = parsed.cleaned_prompt
                except PromptParserError as e:
                    logger.warning(f"[Textual] Path parsing error: {e}")

            # Get orchestrator config for agent creation
            orch_cfg = modified_config.get("orchestrator", {})

            # Apply execute mode config modifications BEFORE agent creation
            # This injects plan execution guidance into agent system messages
            mode_state = display.get_mode_state()
            if mode_state and mode_state.plan_mode == "execute" and mode_state.plan_session:
                # Check artifact type to route to plan or spec execution
                try:
                    _exec_metadata = mode_state.plan_session.load_metadata()
                    _artifact_type = getattr(_exec_metadata, "artifact_type", "plan")
                except Exception:
                    _artifact_type = "plan"

                if _artifact_type == "spec":
                    from ..plan_execution import prepare_spec_execution_config

                    logger.info("[Textual] Execute mode - applying spec execution config")
                    modified_config = prepare_spec_execution_config(
                        modified_config,
                        mode_state.plan_session,
                    )
                else:
                    from ..plan_execution import prepare_plan_execution_config

                    logger.info("[Textual] Execute mode - applying plan execution config")
                    modified_config = prepare_plan_execution_config(
                        modified_config,
                        mode_state.plan_session,
                    )
                # Update orchestrator_cfg reference for later use
                orch_cfg = modified_config.get("orchestrator", {})

            # Progress callback for agent creation status
            def progress_callback(status: str, detail: str) -> None:
                adapter.update_loading_status(status)

            enable_rate_limit = outer_kwargs.get("enable_rate_limit", False)
            new_agents = create_agents_from_config(
                modified_config,
                orch_cfg,
                enable_rate_limit=enable_rate_limit,
                config_path=config_path,
                memory_session_id=sess_id,
                debug=debug,
                filesystem_session_id=sess_id,
                session_storage_base=SESSION_STORAGE,
                progress_callback=progress_callback,
            )
            if not new_agents:
                return TurnResult(
                    error=Exception("Failed to create agents"),
                    was_cancelled=False,
                )
            # Update context and use new agents
            context.agents = new_agents
            agents = new_agents
            logger.info(f"[Textual] Created {len(agents)} agent(s)")
            adapter.update_loading_status("✅ Agents created")

        # Ensure analysis target logs are mounted as read-only context paths.
        # Without this, agents in Docker cannot read host log artifacts.
        if agents is not None and analysis_context_path and not _agents_have_context_path(agents, analysis_context_path):
            logger.info(
                f"[Textual] Recreating agents with analysis log context path: {analysis_context_path}",
            )

            # Cleanup existing agents before recreating to avoid leaked containers.
            for aid, ag in agents.items():
                if hasattr(ag, "backend") and hasattr(ag.backend, "filesystem_manager") and ag.backend.filesystem_manager:
                    try:
                        ag.backend.filesystem_manager.cleanup()
                    except Exception as e:
                        logger.warning(f"[Textual] Cleanup failed for {aid}: {e}")
                if hasattr(ag.backend, "__aexit__"):
                    await ag.backend.__aexit__(None, None, None)

            modified_config = original_config.copy()
            _merge_readonly_context_path(
                modified_config,
                analysis_context_path,
                "Analysis target log session",
            )
            orch_cfg = modified_config.get("orchestrator", {})
            enable_rate_limit = outer_kwargs.get("enable_rate_limit", False)
            new_agents = create_agents_from_config(
                modified_config,
                orch_cfg,
                debug=debug,
                enable_rate_limit=enable_rate_limit,
                config_path=config_path,
                memory_session_id=sess_id,
                filesystem_session_id=sess_id,
                session_storage_base=SESSION_STORAGE,
            )
            context.agents = new_agents
            agents = new_agents
            logger.info(
                f"[Textual] Recreated {len(agents)} agent(s) with analysis log context path",
            )

        # Track workspaces from incomplete turns (applied to orchestrator after creation)
        pending_pre_populated_workspaces = {}

        # Inject previous turn workspace as read-only context (same as Rich mode)
        if current_turn_num > 0 and original_config and orchestrator_cfg:
            session_dir = Path(SESSION_STORAGE) / sess_id
            latest_turn_dir = session_dir / f"turn_{current_turn_num}"
            latest_turn_workspace = latest_turn_dir / "workspace"

            # Determine which workspaces to add as context paths
            context_workspaces_to_add = []
            incomplete_ws = getattr(context, "incomplete_turn_workspaces", {})

            if incomplete_ws:
                # Incomplete turn — store for orchestrator per-agent
                # writable copy (not read-only context). Applied after
                # orchestrator is created below.
                pending_pre_populated_workspaces = {ws_agent_id: Path(ws_path).resolve() for ws_agent_id, ws_path in incomplete_ws.items() if ws_path and Path(ws_path).exists()}
                logger.info(
                    f"[Textual] Prepared {len(pending_pre_populated_workspaces)} " f"per-agent workspace(s) from incomplete turn for writable copy",
                )
                # Clear after first use
                context.incomplete_turn_workspaces = {}
            elif latest_turn_workspace.exists():
                # Complete turn - single winning agent workspace
                context_workspaces_to_add.append(
                    {
                        "path": str(latest_turn_workspace.resolve()),
                        "permission": "read",
                    },
                )

            if context_workspaces_to_add:
                # Check for session pre-mount (no container restart needed)
                agents_with_session_mount = [
                    (aid, ag)
                    for aid, ag in agents.items()
                    if hasattr(ag, "backend") and hasattr(ag.backend, "filesystem_manager") and ag.backend.filesystem_manager and ag.backend.filesystem_manager.has_session_mount()
                ]

                persist_containers = orchestrator_cfg.get("docker", {}).get(
                    "persist_containers_between_turns",
                    True,
                )

                if agents_with_session_mount and persist_containers:
                    # Just update permission manager - no container restart
                    logger.info(
                        "[Textual] Session pre-mounted: adding turn path(s) without container restart",
                    )
                    for aid, ag in agents.items():
                        if hasattr(ag, "backend") and hasattr(ag.backend, "filesystem_manager") and ag.backend.filesystem_manager:
                            for ctx_ws in context_workspaces_to_add:
                                ag.backend.filesystem_manager.add_turn_context_path(
                                    Path(ctx_ws["path"]),
                                )
                else:
                    # Fall back: cleanup and recreate agents
                    logger.info(
                        f"[Textual] Recreating agents with turn {current_turn_num} workspace(s) as context",
                    )

                    # Cleanup existing agents
                    for aid, ag in agents.items():
                        if hasattr(ag, "backend") and hasattr(ag.backend, "filesystem_manager") and ag.backend.filesystem_manager:
                            try:
                                ag.backend.filesystem_manager.cleanup()
                            except Exception as e:
                                logger.warning(
                                    f"[Textual] Cleanup failed for {aid}: {e}",
                                )
                        if hasattr(ag.backend, "__aexit__"):
                            await ag.backend.__aexit__(None, None, None)

                    # Inject context paths into config
                    modified_config = original_config.copy()
                    agent_entries = [modified_config["agent"]] if "agent" in modified_config else modified_config.get("agents", [])
                    for agent_data in agent_entries:
                        backend_config = agent_data.get("backend", {})
                        if "cwd" in backend_config:
                            existing_context_paths = backend_config.get(
                                "context_paths",
                                [],
                            )
                            backend_config["context_paths"] = existing_context_paths + context_workspaces_to_add

                    # Recreate agents
                    enable_rate_limit = outer_kwargs.get("enable_rate_limit", False)
                    new_agents = create_agents_from_config(
                        modified_config,
                        orchestrator_cfg,
                        debug=debug,
                        enable_rate_limit=enable_rate_limit,
                        config_path=config_path,
                        memory_session_id=sess_id,
                        filesystem_session_id=sess_id,
                        session_storage_base=SESSION_STORAGE,
                    )
                    # Update context and local reference
                    context.agents = new_agents
                    agents = new_agents
                    logger.info(
                        f"[Textual] Recreated {len(agents)} agents with context paths",
                    )

        # Restore multi-turn memory (prefers session_info, else session storage).
        previous_turns, winning_agents_history = _reload_turn_history(session_info, sess_id)

        # Build orchestrator config (matching Rich terminal path setup)
        orchestrator_config = AgentConfig()
        # Get context sharing parameters (must be extracted before orchestrator creation)
        snapshot_storage = _scope_snapshot_storage(orchestrator_cfg.get("snapshot_storage") if orchestrator_cfg else None)
        agent_temporary_workspace = _scope_agent_temporary_workspace(
            orchestrator_cfg.get("agent_temporary_workspace") if orchestrator_cfg else None,
        )
        # Get NLIP config (matching Rich terminal path)
        orchestrator_enable_nlip = orchestrator_cfg.get("enable_nlip", False) if orchestrator_cfg else False
        orchestrator_nlip_config = orchestrator_cfg.get("nlip_config", {}) if orchestrator_cfg else {}
        if orchestrator_enable_nlip:
            logger.info("[Textual] NLIP enabled for orchestrator")
        if orchestrator_cfg:
            _apply_orchestrator_runtime_params(orchestrator_config, orchestrator_cfg)

            if "coordination" in orchestrator_cfg:
                coord_cfg = orchestrator_cfg["coordination"]
                orchestrator_config.coordination_config = _parse_coordination_config(coord_cfg)

        # Set timeout config if provided
        timeout_config = outer_kwargs.get("timeout_config")
        if timeout_config:
            orchestrator_config.timeout_config = timeout_config

        # Apply TUI mode state overrides (single-agent mode, refinement mode, etc.)
        mode_state = display.get_mode_state()
        if mode_state:
            # Respect config-provided coordination mode until user explicitly changes it in the mode bar.
            if not mode_state.coordination_mode_user_set:
                configured_coordination_mode = getattr(orchestrator_config, "coordination_mode", "voting")
                synced_mode = "decomposition" if configured_coordination_mode == "decomposition" else "parallel"
                if mode_state.coordination_mode != synced_mode:
                    mode_state.coordination_mode = synced_mode
                    logger.info(f"[Textual] Synced coordination mode from config: {synced_mode}")
                    if display._app:
                        display._call_app_method("_sync_coordination_mode_toggle", synced_mode)

            mode_overrides = mode_state.get_orchestrator_overrides()
            execute_refinement_mode = getattr(
                mode_state.plan_config,
                "execute_refinement_mode",
                "inherit",
            )
            if mode_state.plan_mode == "execute" and execute_refinement_mode in {"on", "off"}:
                if execute_refinement_mode == "on":
                    # Ensure refinement behavior is active for execute turns.
                    for key in (
                        "max_new_answers_per_agent",
                        "skip_final_presentation",
                        "skip_voting",
                        "disable_injection",
                        "defer_voting_until_all_answered",
                    ):
                        mode_overrides.pop(key, None)
                else:
                    # Force quick-mode behavior for execute turns.
                    mode_overrides["max_new_answers_per_agent"] = 1
                    mode_overrides["skip_final_presentation"] = True
                    if mode_state.agent_mode == "single":
                        mode_overrides["skip_voting"] = True
                        mode_overrides.pop("disable_injection", None)
                        mode_overrides.pop("defer_voting_until_all_answered", None)
                    else:
                        mode_overrides["disable_injection"] = True
                        mode_overrides["defer_voting_until_all_answered"] = True
                        mode_overrides.pop("skip_voting", None)
            if mode_overrides:
                logger.info(f"[Textual] Applying TUI mode overrides: {mode_overrides}")
                for key, value in mode_overrides.items():
                    if hasattr(orchestrator_config, key):
                        setattr(orchestrator_config, key, value)

            # Apply persona-generation toggle for parallel mode.
            # This is intentionally OFF by default in Textual mode unless the
            # mode-bar toggle is enabled.
            persona_enabled = mode_state.parallel_personas_enabled and mode_state.coordination_mode == "parallel"
            if orchestrator_config.coordination_config is None:
                from ..agent_config import CoordinationConfig

                orchestrator_config.coordination_config = CoordinationConfig()
            persona_cfg = getattr(orchestrator_config.coordination_config, "persona_generator", None)
            if persona_cfg is not None:
                persona_cfg.enabled = persona_enabled
                if persona_enabled:
                    persona_cfg.diversity_mode = mode_state.persona_diversity_mode
                logger.info(
                    f"[Textual] Parallel persona generation: {'enabled' if persona_enabled else 'disabled'} "
                    f"(toggle={mode_state.parallel_personas_enabled}, mode={mode_state.persona_diversity_mode}, "
                    f"coordination={mode_state.coordination_mode})",
                )

            # Apply plan mode coordination overrides
            coord_overrides = mode_state.get_coordination_overrides()
            if coord_overrides:
                logger.info(f"[Textual] Plan mode active - applying coordination overrides: {coord_overrides}")
                # Ensure coordination_config exists
                if orchestrator_config.coordination_config is None:
                    from ..agent_config import CoordinationConfig

                    orchestrator_config.coordination_config = CoordinationConfig()

                # Apply coordination overrides
                for key, value in coord_overrides.items():
                    if hasattr(orchestrator_config.coordination_config, key):
                        setattr(orchestrator_config.coordination_config, key, value)

            if _is_planning_turn(mode_state):
                if _disable_evaluation_criteria_generation_for_planning(orchestrator_config.coordination_config):
                    logger.info("[Textual] Plan mode: disabled evaluation criteria generation for planning turn")
                if _set_planning_checklist_criteria_defaults(orchestrator_config.coordination_config):
                    logger.info("[Textual] Plan mode: defaulted checklist_criteria_preset=planning")

            planning_turn_mode: str | None = None
            if mode_state.plan_mode == "plan" and mode_state.pending_planning_mode in {"multi", "single"}:
                planning_turn_mode = mode_state.pending_planning_mode
                # One-shot override set by planning review modal.
                mode_state.pending_planning_mode = None

            # In single-agent mode, filter agents to selected agent only
            if planning_turn_mode == "single":
                selected_for_quick_edit = mode_state.selected_single_agent or next(
                    iter(agents.keys()),
                    None,
                )
                if selected_for_quick_edit and selected_for_quick_edit in agents:
                    logger.info(
                        f"[Textual] Plan quick-edit mode: using single agent {selected_for_quick_edit}",
                    )
                    agents = {selected_for_quick_edit: agents[selected_for_quick_edit]}
            elif mode_state.is_single_agent_mode() and mode_state.selected_single_agent:
                effective_agents = mode_state.get_effective_agents(agents)
                if effective_agents:
                    logger.info(f"[Textual] Single-agent mode: using {list(effective_agents.keys())}")
                    agents = effective_agents

            enabled_skill_names = mode_state.analysis_config.get_enabled_skill_names()
            include_previous_session_skills = bool(
                mode_state.analysis_config.include_previous_session_skills,
            )
            skill_lifecycle_mode = str(
                getattr(mode_state.analysis_config, "skill_lifecycle_mode", "create_or_update"),
            )
            skills_runtime_enabled = bool(
                (orchestrator_config.coordination_config and orchestrator_config.coordination_config.use_skills) or mode_state.plan_mode == "analysis",
            )
            if skills_runtime_enabled:
                if orchestrator_config.coordination_config is None:
                    from ..agent_config import CoordinationConfig

                    orchestrator_config.coordination_config = CoordinationConfig()

                # Analysis mode always requires skills to be on.
                if mode_state.plan_mode == "analysis":
                    orchestrator_config.coordination_config.use_skills = True

                setattr(
                    orchestrator_config.coordination_config,
                    "enabled_skill_names",
                    enabled_skill_names,
                )
                setattr(
                    orchestrator_config.coordination_config,
                    "load_previous_session_skills",
                    include_previous_session_skills,
                )
                setattr(
                    orchestrator_config.coordination_config,
                    "skill_lifecycle_mode",
                    skill_lifecycle_mode,
                )

            # Prepend task planning prompt prefix when TUI plan mode is "plan" (not "execute")
            # Execute mode has its own execution prompt with plan context
            if mode_state.plan_mode == "plan":
                # Get subagents setting from coordination config
                coord_cfg = orchestrator_cfg.get("coordination", {}) if orchestrator_cfg else {}
                enable_subagents = coord_cfg.get("enable_subagents", False)
                # Also check if it was set via coordination overrides
                if orchestrator_config.coordination_config and orchestrator_config.coordination_config.enable_subagents:
                    enable_subagents = True

                planning_prefix = get_task_planning_prompt_prefix(
                    plan_depth=mode_state.plan_config.depth,
                    target_steps=mode_state.plan_config.target_steps,
                    target_chunks=mode_state.plan_config.target_chunks,
                    enable_subagents=enable_subagents,
                    broadcast_mode=mode_state.plan_config.broadcast,
                    thoroughness=mode_state.plan_config.thoroughness,
                )

                planning_feedback = (mode_state.pending_planning_feedback or "").strip()
                mode_state.pending_planning_feedback = None
                effective_planning_mode = planning_turn_mode or ("single" if len(agents) == 1 else "multi")
                mode_state.last_planning_mode = effective_planning_mode

                question = planning_prefix + question
                planning_refinement_appendix = build_plan_review_refinement_appendix(
                    question=question,
                    planning_feedback=planning_feedback,
                    include_quick_edit_hint=should_include_quick_edit_hint(planning_turn_mode),
                )
                if planning_refinement_appendix:
                    question += "\n\n" + planning_refinement_appendix
                logger.info(
                    f"[Textual] Plan mode: Prepended task planning instructions "
                    f"(depth={mode_state.plan_config.depth}, subagents={enable_subagents}, "
                    f"broadcast={mode_state.plan_config.broadcast}, target_steps={mode_state.plan_config.target_steps}, "
                    f"target_chunks={mode_state.plan_config.target_chunks}, planning_turn_mode={effective_planning_mode})",
                )

                # Capture context paths for use during execution
                # These will be stored in plan metadata when plan is finalized
                if orchestrator_cfg:
                    mode_state.planning_context_paths = orchestrator_cfg.get("context_paths", [])
                    if mode_state.planning_context_paths:
                        logger.info(
                            f"[Textual] Plan mode: Captured {len(mode_state.planning_context_paths)} context paths for execution",
                        )
            elif mode_state.plan_mode == "spec":
                spec_prefix = get_spec_creation_prompt_prefix(
                    broadcast_mode=mode_state.spec_config.broadcast,
                )

                planning_feedback = (mode_state.pending_planning_feedback or "").strip()
                mode_state.pending_planning_feedback = None
                effective_planning_mode = planning_turn_mode or ("single" if len(agents) == 1 else "multi")
                mode_state.last_planning_mode = effective_planning_mode

                question = spec_prefix + question
                planning_refinement_appendix = build_plan_review_refinement_appendix(
                    question=question,
                    planning_feedback=planning_feedback,
                    include_quick_edit_hint=should_include_quick_edit_hint(planning_turn_mode),
                )
                if planning_refinement_appendix:
                    question += "\n\n" + planning_refinement_appendix
                logger.info(
                    "[Textual] Spec mode: Prepended spec creation instructions " "(broadcast=%s, planning_turn_mode=%s)",
                    mode_state.spec_config.broadcast,
                    effective_planning_mode,
                )

                # Capture context paths for use during execution
                if orchestrator_cfg:
                    mode_state.planning_context_paths = orchestrator_cfg.get("context_paths", [])
                    if mode_state.planning_context_paths:
                        logger.info(
                            "[Textual] Spec mode: Captured %d context paths for execution",
                            len(mode_state.planning_context_paths),
                        )
            elif mode_state.plan_mode == "analysis":
                analysis_target = getattr(mode_state.analysis_config, "target", "log")
                if analysis_target == "skills":
                    question = get_skill_organization_prompt_prefix() + question
                    logger.info("[Textual] Analysis mode: skill organization (prepended organization instructions)")
                else:
                    analysis_profile = mode_state.analysis_config.profile
                    analysis_log_dir = mode_state.analysis_config.selected_log_dir
                    analysis_turn = mode_state.analysis_config.selected_turn
                    question = (
                        get_log_analysis_prompt_prefix(
                            log_dir=analysis_log_dir,
                            turn=analysis_turn,
                            profile=analysis_profile,
                            skill_lifecycle_mode=skill_lifecycle_mode,
                        )
                        + question
                    )
                    logger.info(
                        "[Textual] Analysis mode: prepended analysis instructions "
                        f"(profile={analysis_profile}, log_dir={analysis_log_dir}, turn={analysis_turn}, "
                        f"skills_filter={'all' if enabled_skill_names is None else len(enabled_skill_names)}, "
                        f"evolving={'on' if include_previous_session_skills else 'off'}, "
                        f"lifecycle={skill_lifecycle_mode})",
                    )

        # Reload personas/criteria persisted from a prior turn (matching Rich path).
        generated_personas, generated_evaluation_criteria = _load_persisted_personas_and_criteria(
            orchestrator_config,
            session_info,
        )

        # Create orchestrator with multi-turn state
        adapter.update_loading_status("🔧 Setting up workspace...")

        # Get plan session ID if in execute mode
        plan_session_id = None
        mode_state = display.get_mode_state()
        if mode_state and mode_state.plan_mode == "execute" and mode_state.plan_session:
            plan_session_id = mode_state.plan_session.plan_id
            logger.info(f"[Textual] Execute mode - passing plan_session_id to orchestrator: {plan_session_id}")

        orchestrator = Orchestrator(
            agents=agents,
            config=orchestrator_config,
            session_id=sess_id,
            snapshot_storage=snapshot_storage,
            agent_temporary_workspace=agent_temporary_workspace,
            previous_turns=previous_turns,
            winning_agents_history=winning_agents_history,
            dspy_paraphraser=outer_kwargs.get("dspy_paraphraser"),
            enable_rate_limit=outer_kwargs.get("enable_rate_limit", False),
            enable_nlip=orchestrator_enable_nlip,
            nlip_config=orchestrator_nlip_config,
            generated_personas=generated_personas,
            generated_evaluation_criteria=generated_evaluation_criteria,
            plan_session_id=plan_session_id,
            raw_config=original_config or outer_kwargs.get("raw_config"),
        )

        # Parse per-agent subtask assignments for decomposition mode
        if orchestrator_config.coordination_mode == "decomposition":
            raw_agents = []
            if original_config:
                raw_agents = original_config.get("agents", [])
                if not raw_agents and "agent" in original_config:
                    raw_agents = [original_config["agent"]]
            if isinstance(raw_agents, list):
                for agent_data in raw_agents:
                    if isinstance(agent_data, dict):
                        aid = agent_data.get("id", "")
                        subtask = agent_data.get("subtask")
                        if subtask:
                            orchestrator._agent_subtasks[aid] = subtask

            # Apply TUI-provided subtasks (takes precedence over config values)
            mode_state = display.get_mode_state()
            if mode_state and mode_state.decomposition_subtasks:
                for aid, subtask in mode_state.decomposition_subtasks.items():
                    if aid in agents and subtask:
                        orchestrator._agent_subtasks[aid] = subtask

        # Apply deferred pre-populated workspaces from incomplete turns
        if pending_pre_populated_workspaces:
            orchestrator._pre_populated_workspaces = pending_pre_populated_workspaces
            pending_pre_populated_workspaces = {}

        adapter.update_loading_status("🔌 Connecting to tools...")

        # Create coordination UI with preserve_display and interactive_mode
        coord_ui = CoordinationUI(
            display_type="textual_terminal",
            preserve_display=True,  # Don't cleanup display between turns
            interactive_mode=True,  # External driver owns the TUI loop
            **ui_config.get("display_kwargs", {}),
        )
        coord_ui.display = display
        coord_ui.agent_ids = agent_ids

        # Use begin_turn to update display state
        turn_num = session_info.get("current_turn", 0) + 1
        display.begin_turn(turn_num, question)

        # Reconfigure logging for the turn (same as Rich mode)
        setup_logging(debug=_is_debug_mode(), turn=turn_num)

        # Save execution metadata for this turn (same as Rich mode)
        save_execution_metadata(
            query=question,
            config_path=config_path,
            config_content=original_config,
            cli_args={
                "mode": "textual_interactive",
                "turn": turn_num,
                "session_id": sess_id,
            },
        )

        # Run orchestration with restart loop
        # (won't call display.run_async due to interactive_mode)
        use_conversation_history = _should_use_conversation_history_for_turn(
            conversation_history=conversation_history,
            mode_state=mode_state,
            agents=agents,
        )
        if mode_state and mode_state.plan_mode == "execute" and conversation_history:
            if use_conversation_history:
                logger.info(
                    "[Textual] Execute mode - keeping conversation history " "injection because evolving skills are enabled",
                )
            else:
                logger.info(
                    "[Textual] Execute mode - skipping conversation history " "injection for orchestration prompt assembly",
                )

        while True:
            # Use coordinate_with_context if we have conversation history for multi-turn
            if use_conversation_history:
                # Build messages list with history + current question
                messages = conversation_history + [
                    {"role": "user", "content": question},
                ]
                answer = await coord_ui.coordinate_with_context(
                    orchestrator=orchestrator,
                    question=question,
                    messages=messages,
                    agent_ids=agent_ids,
                )
            else:
                answer = await coord_ui.coordinate(
                    orchestrator=orchestrator,
                    question=question,
                    agent_ids=agent_ids,
                )

            # Check if restart is needed
            if hasattr(orchestrator, "restart_pending") and orchestrator.restart_pending:
                from massgen.logger_config import set_log_attempt

                set_log_attempt(orchestrator.current_attempt + 1)

                save_execution_metadata(
                    query=question,
                    config_path=config_path,
                    config_content=original_config,
                    cli_args={
                        "mode": "textual_interactive_restart",
                        "attempt": orchestrator.current_attempt + 1,
                        "turn": turn_num,
                        "session_id": sess_id,
                        "restart_reason": orchestrator.restart_reason,
                    },
                )

                # Reset all agent backends for clean state
                for agent_id, agent in orchestrator.agents.items():
                    if hasattr(agent.backend, "reset_state"):
                        try:
                            import inspect

                            result = agent.backend.reset_state()
                            if inspect.iscoroutine(result):
                                await result
                            logger.info(f"Reset backend state for {agent_id}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to reset backend for {agent_id}: {e}",
                            )

                # Reuse existing UI for restart (never recreate in Textual
                # mode — the Textual app owns the display and a fresh
                # CoordinationUI would not have it)
                try:
                    coord_ui.prepare_for_restart(
                        orchestrator,
                        orchestrator.current_attempt + 1,
                        orchestrator.max_attempts,
                    )
                except Exception as e:
                    logger.warning(f"prepare_for_restart failed: {e}", exc_info=True)

                continue
            else:
                break

        # Handle session persistence (same as Rich mode)
        session_id_to_use = session_info.get("session_id")
        updated_turn = turn_num
        normalized_answer = answer
        # Extract models from all agents for session metadata.
        models_dict, model_name_for_registry = _extract_models_for_session(agents)
        try:
            from massgen.logger_config import get_log_session_root

            log_dir = get_log_session_root()
            log_dir_name = log_dir.name if log_dir else None
            (
                session_id_to_use,
                updated_turn,
                normalized_answer,
            ) = await handle_session_persistence(
                orchestrator,
                question,
                session_info,
                config_path=config_path,
                model=model_name_for_registry,
                log_directory=log_dir_name,
                models_dict=models_dict,
            )
            if normalized_answer:
                answer = normalized_answer
            logger.info(
                f"[Textual] Persisted turn {updated_turn} to session {session_id_to_use}",
            )
        except Exception as persist_err:
            logger.warning(f"[Textual] Failed to persist session: {persist_err}")

        # Store generated personas/criteria for reuse across turns.
        _persist_generated_personas_and_criteria(orchestrator, session_info)

        # End turn
        display.end_turn(turn_num, answer=answer)

        return TurnResult(
            answer_text=answer,
            was_cancelled=False,
            updated_session_id=session_id_to_use,
            updated_turn=updated_turn,
        )

    except CancellationRequested as cancel_exc:
        # User cancelled the turn - save partial progress if available
        logger.info("[Textual] Turn cancelled by user")
        partial_saved = getattr(cancel_exc, "partial_saved", False)

        # Try to save partial result if orchestrator has one
        if not partial_saved and orchestrator:
            try:
                from massgen.session import save_partial_turn

                partial_result = orchestrator.get_partial_result()
                if partial_result:
                    save_partial_turn(
                        session_id=session_info.get("session_id"),
                        turn_number=turn_num,
                        question=question,
                        partial_result=partial_result,
                        session_storage=SESSION_STORAGE,
                    )
                    partial_saved = True
                    logger.info(f"[Textual] Saved partial turn {turn_num}")
            except Exception as save_err:
                logger.warning(f"[Textual] Failed to save partial turn: {save_err}")

        display.end_turn(turn_num, was_cancelled=True)

        return TurnResult(
            was_cancelled=True,
            partial_saved=partial_saved,
            updated_session_id=session_info.get("session_id"),
            updated_turn=session_info.get(
                "current_turn",
                0,
            ),  # Don't increment on cancel
        )

    except Exception as e:
        logger.exception(f"Error in turn: {e}")
        return TurnResult(
            error=e,
            was_cancelled=False,
            updated_session_id=session_info.get("session_id"),
            updated_turn=session_info.get("current_turn", 0),
        )


async def run_textual_interactive_mode(
    agents: dict[str, SingleAgent],
    ui_config: dict[str, Any],
    original_config: dict[str, Any] = None,
    orchestrator_cfg: dict[str, Any] = None,
    config_path: str | None = None,
    memory_session_id: str | None = None,
    initial_question: str | None = None,
    restore_session_if_exists: bool = False,
    debug: bool = False,
    **kwargs,
):
    """Run MassGen in Textual TUI interactive mode.

    This launches the Textual TUI immediately, displaying the ASCII art,
    session configuration, and input box within the TUI itself.
    All interaction happens inside the TUI without Rich terminal output.

    Uses the unified InteractiveSessionController for multi-turn orchestration.
    """
    import asyncio
    import contextvars
    import threading

    from massgen.frontend.displays.textual_terminal_display import (
        TEXTUAL_AVAILABLE,
        TextualTerminalDisplay,
    )
    from massgen.frontend.interactive_controller import (
        InteractiveSessionController,
        SessionContext,
        TextualInteractiveAdapter,
        TextualThreadQueueQuestionSource,
        TurnResult,
    )

    parse_at_references = kwargs.get("parse_at_references", True)

    if not TEXTUAL_AVAILABLE:
        print("⚠️ Textual library not available. Install with: pip install textual")
        print("   Falling back to Rich terminal mode...")
        ui_config["display_type"] = "rich_terminal"
        return await run_interactive_mode(
            agents=agents,
            ui_config=ui_config,
            original_config=original_config,
            orchestrator_cfg=orchestrator_cfg,
            config_path=config_path,
            memory_session_id=memory_session_id,
            initial_question=initial_question,
            restore_session_if_exists=restore_session_if_exists,
            debug=debug,
            **kwargs,
        )

    # Build agent info for display (handle deferred agent creation)
    agent_ids, agent_models = _build_agent_display_info(agents, original_config)

    # Session state
    session_id = memory_session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Restore session state if requested (same as Rich mode)
    current_turn = 0
    conversation_history = []
    previous_turns = []
    winning_agents_history = []
    incomplete_turn_workspaces = {}
    restore_notification = None  # Message to show in TUI after startup

    if memory_session_id and restore_session_if_exists:
        from massgen.logger_config import set_log_turn
        from massgen.session import restore_session

        try:
            session_state = restore_session(memory_session_id, SESSION_STORAGE)
            conversation_history = session_state.conversation_history
            current_turn = session_state.current_turn
            previous_turns = session_state.previous_turns
            winning_agents_history = session_state.winning_agents_history

            # Set turn number for logger (next turn after last completed)
            next_turn = current_turn + 1
            set_log_turn(next_turn)

            restore_notification = f"Restored session with {current_turn} previous turn(s) " f"({len(conversation_history)} messages). Starting turn {next_turn}"

            # Check for incomplete turn
            if session_state.incomplete_turn:
                incomplete = session_state.incomplete_turn
                restore_notification += f"\n⚠️ Previous turn was incomplete (cancelled during {incomplete.get('phase', 'unknown')} phase)"
                if incomplete.get("agents_with_answers"):
                    restore_notification += f"\nPartial answers from: {', '.join(incomplete['agents_with_answers'])}"

            # Store incomplete turn workspaces for context path injection
            incomplete_turn_workspaces = session_state.incomplete_turn_workspaces
        except ValueError as e:
            # restore_session failed - no turns found
            logger.error(f"Session restore error: {e}")
            restore_notification = f"Session error: {e}. Starting fresh session."
            # Reset to fresh session instead of exiting (TUI is more forgiving)
            current_turn = 0
            conversation_history = []

    # Create the Textual display with agent model info for welcome screen
    display_kwargs = ui_config.get("display_kwargs", {})
    display_kwargs["agent_models"] = agent_models
    cwd_context_mode = kwargs.get("cwd_context_mode")
    if cwd_context_mode:
        normalized_mode = str(cwd_context_mode).strip().lower()
        if normalized_mode in {"rw", "write"}:
            display_kwargs["default_cwd_context_mode"] = "write"
        elif normalized_mode in {"ro", "read"}:
            display_kwargs["default_cwd_context_mode"] = "read"
    configured_coordination_mode = orchestrator_cfg.get("coordination_mode", "voting") if orchestrator_cfg else "voting"
    display_kwargs["default_coordination_mode"] = "decomposition" if configured_coordination_mode == "decomposition" else "parallel"
    coordination_settings = orchestrator_cfg.get("coordination", {}) if orchestrator_cfg else {}
    display_kwargs["default_load_previous_session_skills"] = bool(
        coordination_settings.get("load_previous_session_skills", False),
    )
    display_kwargs["default_skill_lifecycle_mode"] = str(
        coordination_settings.get("skill_lifecycle_mode", "create_or_update"),
    )

    # Apply CLI mode defaults (override config-derived defaults)
    cli_mode_defaults = kwargs.pop("cli_mode_defaults", {})
    if cli_mode_defaults.get("agent_mode") == "single":
        display_kwargs["default_agent_mode"] = "single"
        if "selected_agent" in cli_mode_defaults:
            display_kwargs["default_selected_agent"] = cli_mode_defaults["selected_agent"]
    if "coordination_mode" in cli_mode_defaults:
        display_kwargs["default_coordination_mode"] = cli_mode_defaults["coordination_mode"]
    if "plan_mode" in cli_mode_defaults:
        display_kwargs["default_plan_mode"] = cli_mode_defaults["plan_mode"]
    if "refinement_enabled" in cli_mode_defaults:
        display_kwargs["default_refinement_enabled"] = cli_mode_defaults["refinement_enabled"]
    if "personas" in cli_mode_defaults:
        p = cli_mode_defaults["personas"]
        if p == "off":
            display_kwargs["default_personas_enabled"] = False
        else:
            display_kwargs["default_personas_enabled"] = True
            display_kwargs["default_persona_diversity_mode"] = p

    display = TextualTerminalDisplay(agent_ids, **display_kwargs)

    # Start background MCP registry cache warmup (non-blocking)
    # This pre-fetches MCP server descriptions while user types their first question
    if original_config:
        from massgen.mcp_tools.registry_client import warmup_mcp_registry_cache

        warmup_thread = threading.Thread(
            target=warmup_mcp_registry_cache,
            args=(original_config,),
            daemon=True,
            name="mcp-cache-warmup",
        )
        warmup_thread.start()
        logger.info("[Textual] Started background MCP registry cache warmup")

    # Create question source (thread-safe queue)
    question_source = TextualThreadQueueQuestionSource()

    # Create session context with restored values
    context = SessionContext(
        session_id=session_id,
        current_turn=current_turn,
        conversation_history=conversation_history,
        previous_turns=previous_turns,
        winning_agents_history=winning_agents_history,
        agents=agents,
        config_path=config_path,
        original_config=original_config,
        orchestrator_cfg=orchestrator_cfg,
    )

    # Store incomplete workspaces in context for workspace injection
    context.incomplete_turn_workspaces = incomplete_turn_workspaces

    # Create adapter for Textual UI updates
    adapter = TextualInteractiveAdapter(display)

    # Define turn runner that uses CoordinationUI
    outer_kwargs_capture = kwargs

    # Per-turn handler. Delegates to the module-level _run_textual_turn so the
    # ~870-line turn body is importable and testable; the closure only binds
    # the collaborators it captures.
    async def run_turn(
        question: str,
        agents: dict[str, Any],
        ui_config: dict[str, Any],
        conversation_history: list,
        session_info: dict,
        **turn_kwargs,
    ) -> TurnResult:
        return await _run_textual_turn(
            question,
            agents,
            ui_config,
            conversation_history,
            session_info,
            display=display,
            adapter=adapter,
            context=context,
            agent_ids=agent_ids,
            config_path=config_path,
            original_config=original_config,
            orchestrator_cfg=orchestrator_cfg,
            debug=debug,
            parse_at_references=parse_at_references,
            outer_kwargs=outer_kwargs_capture,
            **turn_kwargs,
        )

    # Create the controller
    controller = InteractiveSessionController(
        question_source=question_source,
        adapter=adapter,
        context=context,
        turn_runner=run_turn,
        ui_config=ui_config,
        debug=debug,
    )

    # Wire up the TUI input to the question source using set_input_handler
    # This delegates all input (questions and slash commands) to the controller
    display.set_input_handler(question_source.submit)

    # Start session (creates app once)
    display.start_session(
        initial_question=initial_question or "Welcome! Type your question below...",
        log_filename=None,
        session_id=session_id,
    )

    # Ensure the app also has the input handler set (in case app was created before set_input_handler)
    if display._app:
        display._app.set_input_handler(question_source.submit)

    # Run orchestration in background thread
    # Capture the current context on the MAIN thread so the orchestration thread
    # inherits the per-run LoggingSession ContextVar (MAS-274) instead of falling
    # back to the process-global session. Threads do NOT inherit ContextVars, so
    # without this concurrent in-process runs would cross-contaminate logs and
    # snapshot paths.
    orchestration_ctx = contextvars.copy_context()

    def orchestration_thread_fn():
        """Background thread that runs the controller."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run inside the copied context so get_log_session_dir / set_log_turn
            # resolve to this run's session, not the global fallback.
            orchestration_ctx.run(loop.run_until_complete, controller.run())
        except Exception as e:
            logger.exception(f"Controller error: {e}")
        finally:
            loop.close()

    orch_thread = threading.Thread(target=orchestration_thread_fn, daemon=True)
    orch_thread.start()

    # If initial question provided, submit it only after app is mounted
    async def submit_initial_question_when_ready():
        """Wait for app to be mounted before submitting initial question or showing restore notification."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, display._app_ready.wait)

        # Show restore notification if we restored a session
        if restore_notification:
            await asyncio.sleep(0.3)  # Brief delay for UI to settle
            adapter.notify(restore_notification, "info")

        # Submit initial question if provided
        if initial_question:
            question_source.submit(initial_question)

    # Schedule the initial question submission task
    initial_question_task = asyncio.create_task(submit_initial_question_when_ready())

    # Run the Textual TUI (blocks until user quits)
    try:
        await display.run_async()
    finally:
        # Cancel initial question task if still pending
        if not initial_question_task.done():
            initial_question_task.cancel()
        # Signal shutdown
        controller.stop()
        orch_thread.join(timeout=5)
        # Restore terminal to canonical mode (echo + line editing)
        _restore_terminal_for_input()

    print("✅ Textual session ended")


async def run_interactive_mode(
    agents: dict[str, SingleAgent] | None,
    ui_config: dict[str, Any],
    original_config: dict[str, Any] = None,
    orchestrator_cfg: dict[str, Any] = None,
    config_path: str | None = None,
    memory_session_id: str | None = None,
    initial_question: str | None = None,
    restore_session_if_exists: bool = False,
    debug: bool = False,
    raw_config_for_metadata: dict[str, Any] = None,
    # Parameters for deferred agent creation
    enable_rate_limit: bool = True,
    session_storage_base: str | None = None,
    **kwargs,
):
    """Run MassGen in interactive mode with conversation history.

    Args:
        agents: Dict of agents. If None, agents will be created after first prompt
            (allows @path references in first prompt to be included in Docker mounts).
        initial_question: Optional first question to auto-submit when entering interactive mode
        raw_config_for_metadata: Raw config (unexpanded env vars) for safe logging to metadata files
        enable_rate_limit: Whether to enable rate limiting for agent creation
        session_storage_base: Base directory for session storage (for Docker mounts)
    """

    # Textual-first mode: Launch TUI immediately without Rich terminal output
    # The TUI will handle ASCII art, session config, input, and multi-turn loop
    display_type = ui_config.get("display_type", "textual_terminal")
    parse_at_references = kwargs.get("parse_at_references", True)
    if display_type == "textual_terminal":
        return await run_textual_interactive_mode(
            agents=agents,
            ui_config=ui_config,
            original_config=original_config,
            orchestrator_cfg=orchestrator_cfg,
            config_path=config_path,
            memory_session_id=memory_session_id,
            initial_question=initial_question,
            restore_session_if_exists=restore_session_if_exists,
            debug=debug,
            **kwargs,
        )

    # Use Rich console for better display
    rich_console = Console()

    # Clear screen
    rich_console.clear()

    # ASCII art for interactive multi-agent mode
    ascii_art = """[bold #4A90E2]
     ███╗   ███╗ █████╗ ███████╗███████╗ ██████╗ ███████╗███╗   ██╗
     ████╗ ████║██╔══██╗██╔════╝██╔════╝██╔════╝ ██╔════╝████╗  ██║
     ██╔████╔██║███████║███████╗███████╗██║  ███╗█████╗  ██╔██╗ ██║
     ██║╚██╔╝██║██╔══██║╚════██║╚════██║██║   ██║██╔══╝  ██║╚██╗██║
     ██║ ╚═╝ ██║██║  ██║███████║███████║╚██████╔╝███████╗██║ ╚████║
     ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝[/bold #4A90E2]

     [dim]     🤖 🤖 🤖  →  💬 collaborate  →  🎯 winner  →  📢 final[/dim]
"""

    # Wrap ASCII art in a panel
    ascii_panel = Panel(
        ascii_art,
        border_style="bold #4A90E2",
        padding=(0, 2),
        width=80,
    )
    rich_console.print(ascii_panel)
    print()

    # Create configuration table
    config_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        show_edge=False,
    )
    config_table.add_column("Label", style="bold cyan", no_wrap=True)
    config_table.add_column("Value", style="white")

    # Determine mode (agents may be None if deferred creation)
    ui_config.get("use_orchestrator_for_single_agent", True)
    if agents is None:
        # Deferred agent creation - show config-based info
        agent_configs = original_config.get("agents", [])
        if not agent_configs and "agent" in original_config:
            agent_configs = [original_config["agent"]]
        num_agents = len(agent_configs)
        if num_agents == 1:
            mode = "Single Agent"
            mode_icon = "🤖"
        else:
            mode = f"Multi-Agent ({num_agents} agents)"
            mode_icon = "🤝"
        config_table.add_row(f"{mode_icon} Mode:", f"[bold]{mode}[/bold]")
        config_table.add_row(
            "  └─ Status:",
            "[dim]Agents will be created after first prompt[/dim]",
        )
    elif len(agents) == 1:
        mode = "Single Agent"
        mode_icon = "🤖"
        config_table.add_row(f"{mode_icon} Mode:", f"[bold]{mode}[/bold]")
        # Add agents info
        for agent_id, agent in agents.items():
            model = agent.config.backend_params.get("model", "unknown")
            backend_name = agent.backend.__class__.__name__.replace("Backend", "")
            display = f"{model} [dim]({backend_name})[/dim]"
            config_table.add_row(f"  ├─ {agent_id}:", display)
    else:
        mode = f"Multi-Agent ({len(agents)} agents)"
        mode_icon = "🤝"
        config_table.add_row(f"{mode_icon} Mode:", f"[bold]{mode}[/bold]")
        # Add agents info
        if len(agents) <= 3:
            # Show all agents if 3 or fewer
            for agent_id, agent in agents.items():
                model = agent.config.backend_params.get("model", "unknown")
                backend_name = agent.backend.__class__.__name__.replace("Backend", "")
                display = f"{model} [dim]({backend_name})[/dim]"
                config_table.add_row(f"  ├─ {agent_id}:", display)
        else:
            # Show count and first 2 agents
            agent_list = list(agents.items())
            for i, (agent_id, agent) in enumerate(agent_list[:2]):
                model = agent.config.backend_params.get("model", "unknown")
                backend_name = agent.backend.__class__.__name__.replace("Backend", "")
                display = f"{model} [dim]({backend_name})[/dim]"
                config_table.add_row(f"  ├─ {agent_id}:", display)
            config_table.add_row("  └─ ...", f"[dim]and {len(agents) - 2} more[/dim]")

    # Create main panel with configuration
    config_panel = Panel(
        config_table,
        title="[bold bright_yellow]⚙️  Session Configuration[/bold bright_yellow]",
        border_style="yellow",
        padding=(0, 2),
        width=80,
    )
    rich_console.print(config_panel)
    print()

    print_help_messages()

    # In multi-turn mode, skip the automatic agent selector menu after each turn.
    # Users can view outputs on demand via /inspect command.
    ui_config["skip_agent_selector"] = True

    # Session management for multi-turn filesystem support
    # Use memory_session_id (unified with memory system) if provided, otherwise create later
    session_id = memory_session_id
    current_turn = 0

    # Restore session state ONLY if explicitly requested (not for new sessions)
    conversation_history = []
    previous_turns = []
    winning_agents_history = []
    incomplete_turn_workspaces = {}  # Dict of agent_id -> workspace path for incomplete turns
    if memory_session_id and restore_session_if_exists:
        from massgen.logger_config import set_log_turn
        from massgen.session import restore_session

        try:
            session_state = restore_session(memory_session_id, SESSION_STORAGE)
            conversation_history = session_state.conversation_history
            current_turn = session_state.current_turn
            previous_turns = session_state.previous_turns
            winning_agents_history = session_state.winning_agents_history

            # Set turn number for logger (next turn after last completed)
            next_turn = current_turn + 1
            set_log_turn(next_turn)

            print(
                f"📚 Restored session with {current_turn} previous turn(s) " f"({len(conversation_history)} messages) from {SESSION_STORAGE}",
                flush=True,
            )
            print(f"   Starting turn {next_turn}", flush=True)

            # Notify user about incomplete turn if present
            if session_state.incomplete_turn:
                incomplete = session_state.incomplete_turn
                print(
                    f"\n{BRIGHT_YELLOW}⚠️  Previous turn was incomplete (cancelled during {incomplete.get('phase', 'unknown')} phase){RESET}",
                    flush=True,
                )
                print(f"   Task: {incomplete.get('task', 'N/A')}", flush=True)
                if incomplete.get("agents_with_answers"):
                    print(
                        f"   Partial answers saved from: {', '.join(incomplete['agents_with_answers'])}",
                        flush=True,
                    )
                if session_state.incomplete_turn_workspaces:
                    print(
                        f"   Workspaces available: {', '.join(session_state.incomplete_turn_workspaces.keys())}",
                        flush=True,
                    )
                print("", flush=True)

            # Store incomplete turn workspaces for context path injection
            incomplete_turn_workspaces = session_state.incomplete_turn_workspaces
        except ValueError as e:
            # restore_session failed - no turns found
            print(f"❌ Session error: {e}", flush=True)
            print("Run 'massgen --list-sessions' to see available sessions", flush=True)
            sys.exit(1)

    try:
        while True:
            try:
                # Recreate agents with previous turn as read-only context path.
                # This provides agents with BOTH:
                # 1. Read-only context path (original turn n-1 results) - for reference/comparison
                # 2. Writable workspace (copy of turn n-1 results, pre-populated by orchestrator) - for modification
                # This allows agents to compare "what I changed" vs "what was originally there".
                # TODO: We may want to avoid full recreation if possible in the future, conditioned on being able to easily reset MCPs.
                if current_turn > 0 and original_config and orchestrator_cfg:
                    # Get the most recent turn path (the one just completed)
                    session_dir = Path(SESSION_STORAGE) / session_id
                    latest_turn_dir = session_dir / f"turn_{current_turn}"
                    latest_turn_workspace = latest_turn_dir / "workspace"

                    # Determine which workspaces to add as context paths
                    # For complete turns: single workspace from winning agent
                    # For incomplete turns: all agent workspaces (no info lost)
                    context_workspaces_to_add = []

                    if incomplete_turn_workspaces:
                        # Incomplete turn — store for orchestrator per-agent
                        # writable copy (not read-only context). Passed via
                        # kwargs to run_question_with_history which applies
                        # them after orchestrator creation.
                        pre_pop = {ws_agent_id: Path(ws_path).resolve() for ws_agent_id, ws_path in incomplete_turn_workspaces.items() if ws_path and Path(ws_path).exists()}
                        kwargs["pre_populated_workspaces"] = pre_pop
                        logger.info(
                            f"[CLI] Prepared {len(pre_pop)} " f"per-agent workspace(s) from incomplete turn for writable copy",
                        )
                        # Clear after use (only needed for first turn after resume)
                        incomplete_turn_workspaces = {}
                    elif latest_turn_workspace.exists():
                        # Complete turn - single winning agent workspace
                        context_workspaces_to_add.append(
                            {
                                "path": str(latest_turn_workspace.resolve()),
                                "permission": "read",
                            },
                        )

                    if context_workspaces_to_add and agents is not None:
                        # Check if any agents have session pre-mount enabled
                        # Session pre-mount allows us to skip container recreation
                        agents_with_session_mount = [
                            (agent_id, agent)
                            for agent_id, agent in agents.items()
                            if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager and agent.backend.filesystem_manager.has_session_mount()
                        ]

                        # Get persist_containers_between_turns config (default: True)
                        persist_containers = (
                            orchestrator_cfg.get("docker", {}).get(
                                "persist_containers_between_turns",
                                True,
                            )
                            if orchestrator_cfg
                            else True
                        )

                        if agents_with_session_mount and persist_containers:
                            # Session dir is pre-mounted - just update permission manager
                            # No need to restart Docker containers!
                            logger.info(
                                f"[CLI] Session pre-mounted: adding {len(context_workspaces_to_add)} turn path(s) without container restart",
                            )

                            for agent_id, agent in agents.items():
                                if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                                    for ctx_ws in context_workspaces_to_add:
                                        agent.backend.filesystem_manager.add_turn_context_path(
                                            Path(ctx_ws["path"]),
                                        )

                            logger.info(
                                f"[CLI] Turn {current_turn} context paths registered (containers kept alive)",
                            )
                        else:
                            # Fall back to original behavior: cleanup and recreate agents
                            logger.info(
                                f"[CLI] Recreating agents with turn {current_turn} workspace(s) as read-only context path(s)",
                            )

                            # Check if any agents have Docker containers to clean up
                            agents_with_docker = [
                                (agent_id, agent)
                                for agent_id, agent in agents.items()
                                if hasattr(agent, "backend")
                                and hasattr(agent.backend, "filesystem_manager")
                                and agent.backend.filesystem_manager
                                and hasattr(
                                    agent.backend.filesystem_manager,
                                    "docker_manager",
                                )
                                and agent.backend.filesystem_manager.docker_manager
                            ]

                            # Clean up existing agents' backends and filesystem managers
                            if agents_with_docker:
                                from concurrent.futures import (
                                    ThreadPoolExecutor,
                                    as_completed,
                                )

                                from rich.status import Status

                                def cleanup_agent_fs(
                                    agent_id: str,
                                    agent,
                                ) -> tuple[str, Exception | None]:
                                    """Cleanup a single agent's filesystem manager (Docker container)."""
                                    try:
                                        agent.backend.filesystem_manager.cleanup()
                                        return (agent_id, None)
                                    except Exception as e:
                                        return (agent_id, e)

                                # Parallel Docker cleanup with spinner
                                with Status(
                                    f"[bold cyan]Preparing next turn ({len(agents_with_docker)} container(s))...",
                                    spinner="dots",
                                ):
                                    with ThreadPoolExecutor(
                                        max_workers=len(agents_with_docker),
                                    ) as executor:
                                        futures = {
                                            executor.submit(
                                                cleanup_agent_fs,
                                                agent_id,
                                                agent,
                                            ): agent_id
                                            for agent_id, agent in agents_with_docker
                                        }
                                        for future in as_completed(futures):
                                            agent_id, error = future.result()
                                            if error:
                                                logger.warning(
                                                    f"[CLI] Cleanup failed for agent {agent_id}: {error}",
                                                )

                                # Cleanup backends (must be sequential/async)
                                for agent_id, agent in agents.items():
                                    if hasattr(agent.backend, "__aexit__"):
                                        await agent.backend.__aexit__(None, None, None)
                            else:
                                # No Docker - quick cleanup without spinner
                                for agent_id, agent in agents.items():
                                    if hasattr(agent, "backend") and hasattr(
                                        agent.backend,
                                        "filesystem_manager",
                                    ):
                                        if agent.backend.filesystem_manager:
                                            try:
                                                agent.backend.filesystem_manager.cleanup()
                                            except Exception as e:
                                                logger.warning(
                                                    f"[CLI] Cleanup failed for agent {agent_id}: {e}",
                                                )

                                    if hasattr(agent.backend, "__aexit__"):
                                        await agent.backend.__aexit__(None, None, None)

                            # Inject previous turn path(s) as read-only context
                            modified_config = original_config.copy()
                            agent_entries = [modified_config["agent"]] if "agent" in modified_config else modified_config.get("agents", [])

                            for agent_data in agent_entries:
                                backend_config = agent_data.get("backend", {})
                                if "cwd" in backend_config:  # Only inject if agent has filesystem support
                                    existing_context_paths = backend_config.get(
                                        "context_paths",
                                        [],
                                    )
                                    backend_config["context_paths"] = existing_context_paths + context_workspaces_to_add

                            # Recreate agents from modified config (use same session)
                            enable_rate_limit = kwargs.get("enable_rate_limit", False)
                            agents = create_agents_from_config(
                                modified_config,
                                orchestrator_cfg,
                                debug=debug,
                                enable_rate_limit=enable_rate_limit,
                                config_path=config_path,
                                memory_session_id=session_id,
                                # Pass session params for the new agents too
                                filesystem_session_id=session_id,
                                session_storage_base=SESSION_STORAGE,
                            )
                            logger.info(
                                f"[CLI] Successfully recreated {len(agents)} agents with turn {current_turn} workspace(s) as read-only context",
                            )

                # Use initial_question for first turn if provided, otherwise prompt
                if initial_question and current_turn == 0:
                    question = initial_question
                    rich_console.print(f"\n[bold blue]👤 User:[/bold blue] {question}")
                    initial_question = None  # Clear so we prompt on subsequent turns
                else:
                    # Use async version since we're in an async context
                    # Pass ANSI-formatted prompt to prompt_toolkit
                    question = await read_multiline_input_async(
                        f"\n{BRIGHT_BLUE}👤 User:{RESET} ",
                        use_ansi_prompt=True,
                    )

                # Handle slash commands
                if question.startswith("/"):
                    command = question.lower()

                    if command in ["/quit", "/exit", "/q"]:
                        print("👋 Goodbye!", flush=True)
                        break
                    elif command in ["/reset", "/clear"]:
                        conversation_history = []
                        # Reset all agents (if they've been created)
                        if agents is not None:
                            for agent in agents.values():
                                agent.reset()
                        print(
                            f"{BRIGHT_YELLOW}🔄 Conversation history cleared!{RESET}",
                            flush=True,
                        )
                        continue
                    elif command in ["/help", "/h"]:
                        print(
                            f"\n{BRIGHT_CYAN}📚 Available Commands:{RESET}",
                            flush=True,
                        )
                        print("   /quit, /exit, /q     - Exit the program", flush=True)
                        print(
                            "   /reset, /clear       - Clear conversation history",
                            flush=True,
                        )
                        print(
                            "   /help, /h            - Show this help message",
                            flush=True,
                        )
                        print(
                            "   /status              - Show current status",
                            flush=True,
                        )
                        print(
                            "   /config              - Open config file in editor",
                            flush=True,
                        )
                        print(
                            "   /context             - Add/modify context paths for file access",
                            flush=True,
                        )
                        print(
                            "   /inspect, /i         - View agent outputs",
                            flush=True,
                        )
                        print(
                            "     /inspect           - Current turn outputs",
                            flush=True,
                        )
                        print(
                            "     /inspect <N>       - View turn N outputs",
                            flush=True,
                        )
                        print(
                            "     /inspect all       - List all session turns",
                            flush=True,
                        )
                        print(f"\n{BRIGHT_CYAN}💡 Multi-line Input:{RESET}", flush=True)
                        print(
                            "   Start with \"\"\" or ''' and end with the same delimiter",
                            flush=True,
                        )
                        print('   Example: """', flush=True)
                        print("            Your multi-line", flush=True)
                        print("            input here", flush=True)
                        print('            """', flush=True)
                        print(f"\n{BRIGHT_CYAN}📂 @Path Syntax:{RESET}", flush=True)
                        print(
                            "   Use @path to include files as context:",
                            flush=True,
                        )
                        print("   @path/to/file     - Read-only access", flush=True)
                        print("   @path/to/file:w   - Write access", flush=True)
                        print("   @path/to/dir/     - Directory access", flush=True)
                        continue
                    elif command == "/status":
                        print(f"\n{BRIGHT_CYAN}📊 Current Status:{RESET}", flush=True)
                        if agents is not None:
                            print(
                                f"   Agents: {len(agents)} ({', '.join(agents.keys())})",
                                flush=True,
                            )
                            use_orch_single = ui_config.get(
                                "use_orchestrator_for_single_agent",
                                True,
                            )
                            if len(agents) == 1:
                                mode_display = "Single Agent (Orchestrator)" if use_orch_single else "Single Agent (Direct)"
                            else:
                                mode_display = "Multi-Agent"
                            print(f"   Mode: {mode_display}", flush=True)
                        else:
                            # Agents not yet created (deferred creation)
                            agent_configs = original_config.get("agents", [])
                            if not agent_configs and "agent" in original_config:
                                agent_configs = [original_config["agent"]]
                            print(
                                f"   Agents: {len(agent_configs)} (pending creation after first prompt)",
                                flush=True,
                            )
                            print("   Mode: Deferred creation", flush=True)
                        print(
                            f"   History: {len(conversation_history) // 2} exchanges",
                            flush=True,
                        )
                        if config_path:
                            print(f"   Config: {config_path}", flush=True)
                        continue
                    elif command == "/config":
                        if config_path:
                            import platform
                            import subprocess

                            try:
                                system = platform.system()
                                if system == "Darwin":  # macOS
                                    subprocess.run(["open", config_path])
                                elif system == "Windows":
                                    subprocess.run(["start", config_path], shell=True)
                                else:  # Linux and others
                                    subprocess.run(["xdg-open", config_path])
                                print(
                                    f"\n📝 Opening config file: {config_path}",
                                    flush=True,
                                )
                            except Exception as e:
                                print(
                                    f"\n❌ Error opening config file: {e}",
                                    flush=True,
                                )
                                print(f"   Config location: {config_path}", flush=True)
                        else:
                            print(
                                "\n❌ No config file available (using CLI arguments)",
                                flush=True,
                            )
                        continue
                    elif command == "/inspect" or command.startswith("/inspect ") or command == "/i":
                        # Parse: /inspect, /inspect <N>, /inspect all
                        parts = question.split()

                        if len(parts) == 1:
                            # /inspect or /i - show current turn
                            target_turn = current_turn
                        elif parts[1].lower() == "all":
                            # /inspect all - list all turns
                            _list_all_turns(session_id, current_turn, rich_console)
                            continue
                        else:
                            # /inspect <N> - specific turn
                            try:
                                target_turn = int(parts[1])
                                if target_turn < 1 or target_turn > current_turn:
                                    print(
                                        f"{BRIGHT_RED}Turn {target_turn} not found. Available: 1-{current_turn}{RESET}",
                                        flush=True,
                                    )
                                    continue
                            except ValueError:
                                print(
                                    f"{BRIGHT_RED}Invalid turn number. Usage: /inspect [turn_number|all]{RESET}",
                                    flush=True,
                                )
                                continue

                        # Show inspection for target turn
                        if target_turn == 0:
                            print(
                                f"{BRIGHT_YELLOW}No turns completed yet. Complete a turn first.{RESET}",
                                flush=True,
                            )
                        else:
                            _show_turn_inspection(session_id, target_turn, agents)
                        continue
                    elif command == "/context":
                        # Add/modify context paths interactively
                        if original_config and orchestrator_cfg:
                            config_modified = prompt_for_context_paths(
                                original_config,
                                orchestrator_cfg,
                            )
                            if config_modified:
                                # Recreate agents with updated context paths
                                enable_rate_limit = kwargs.get(
                                    "enable_rate_limit",
                                    False,
                                )
                                agents = create_agents_from_config(
                                    original_config,
                                    orchestrator_cfg,
                                    debug=debug,
                                    enable_rate_limit=enable_rate_limit,
                                    config_path=config_path,
                                    memory_session_id=session_id,
                                )
                                print(
                                    f"   {BRIGHT_GREEN}✓ Agents reloaded with updated context paths{RESET}",
                                    flush=True,
                                )
                        else:
                            print(
                                f"{BRIGHT_YELLOW}Context paths require a config file with orchestrator settings.{RESET}",
                                flush=True,
                            )
                        continue
                    else:
                        print(f"❓ Unknown command: {command}", flush=True)
                        print("💡 Type /help for available commands", flush=True)
                        continue

                # Handle legacy plain text commands for backwards compatibility
                if question.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    break

                if question.lower() in ["reset", "clear"]:
                    conversation_history = []
                    if agents:
                        for agent in agents.values():
                            agent.reset()
                    print(f"{BRIGHT_YELLOW}🔄 Conversation history cleared!{RESET}")
                    continue

                if not question:
                    print(
                        "Please enter a question or type /help for commands.",
                        flush=True,
                    )
                    continue

                new_paths = []  # Track new paths for later use
                parsed_context_paths: list[dict[str, str]] = []
                if parse_at_references:
                    # Parse @references from question and inject as context paths
                    from ..path_handling import (
                        PromptParserError,
                        parse_prompt_for_context,
                    )

                    try:
                        parsed = parse_prompt_for_context(question)
                        parsed_context_paths = parsed.context_paths
                        if parsed_context_paths:
                            # Display extracted paths
                            print(f"\n{BRIGHT_CYAN}📂 Context paths from prompt:{RESET}")
                            for ctx in parsed_context_paths:
                                perm_icon = "📝" if ctx["permission"] == "write" else "📖"
                                print(f"   {perm_icon} {ctx['path']} ({ctx['permission']})")
                            for suggestion in parsed.suggestions:
                                print(f"   {BRIGHT_YELLOW}💡 {suggestion}{RESET}")

                            # Use cleaned question
                            question = parsed.cleaned_prompt

                            # Check for new paths that need agent recreation
                            existing_paths = set()
                            if orchestrator_cfg:
                                for p in orchestrator_cfg.get("context_paths", []):
                                    if isinstance(p, dict):
                                        existing_paths.add(p.get("path"))
                                    else:
                                        existing_paths.add(p)

                            new_paths = [ctx for ctx in parsed_context_paths if ctx["path"] not in existing_paths]

                            if new_paths:
                                # Update original_config with new paths
                                if "orchestrator" not in original_config:
                                    original_config["orchestrator"] = {}
                                if "context_paths" not in original_config["orchestrator"]:
                                    original_config["orchestrator"]["context_paths"] = []

                                for ctx in new_paths:
                                    original_config["orchestrator"]["context_paths"].append(
                                        ctx,
                                    )
                                    existing_paths.add(ctx["path"])

                                # Update orchestrator_cfg reference
                                orchestrator_cfg = original_config.get("orchestrator", {})
                    except PromptParserError as e:
                        print(f"\n{BRIGHT_RED}❌ {e}{RESET}", flush=True)
                        continue

                # If agents haven't been created yet (deferred creation), create them now
                if agents is None:
                    print(f"{BRIGHT_YELLOW}🚀 Creating agents...{RESET}")
                    agents = create_agents_from_config(
                        original_config,
                        orchestrator_cfg,
                        enable_rate_limit=enable_rate_limit,
                        config_path=config_path,
                        memory_session_id=memory_session_id,
                        debug=debug,
                        filesystem_session_id=memory_session_id,
                        session_storage_base=session_storage_base or SESSION_STORAGE,
                    )
                    if not agents:
                        print(
                            f"{BRIGHT_RED}❌ Failed to create agents{RESET}",
                            flush=True,
                        )
                        continue
                    print(f"{BRIGHT_GREEN}✅ Agents ready{RESET}")
                elif new_paths:
                    # Agents exist but we have new paths - need to recreate
                    print(
                        f"   {BRIGHT_YELLOW}🔄 Updating agents with new context paths...{RESET}",
                    )

                    # Clean up existing agents before recreating to avoid resource leaks
                    for agent_id, agent in agents.items():
                        if hasattr(agent, "backend"):
                            if hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                                try:
                                    agent.backend.filesystem_manager.cleanup()
                                except Exception as e:
                                    logger.warning(
                                        f"[CLI] Cleanup failed for agent {agent_id}: {e}",
                                    )
                            if hasattr(agent.backend, "__aexit__"):
                                await agent.backend.__aexit__(None, None, None)

                    agents = create_agents_from_config(
                        original_config,
                        orchestrator_cfg,
                        enable_rate_limit=enable_rate_limit,
                        config_path=config_path,
                        memory_session_id=memory_session_id,
                        debug=debug,
                        filesystem_session_id=memory_session_id,
                        session_storage_base=session_storage_base or SESSION_STORAGE,
                    )
                    print(
                        f"   {BRIGHT_GREEN}✅ Agents updated with new context paths{RESET}",
                    )
                if parsed_context_paths:
                    print()  # Add spacing after context path info

                print(f"\n🔄 {BRIGHT_YELLOW}Processing...{RESET}", flush=True)

                # Increment turn counter BEFORE processing so logs go to correct turn_N directory
                next_turn = current_turn + 1

                # Initialize session ID on first turn
                if session_id is None:
                    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Reconfigure logging for the turn we're about to process
                setup_logging(debug=_is_debug_mode(), turn=next_turn)
                logger.info(f"Starting turn {next_turn}")

                # Save execution metadata for this turn (use raw config to avoid logging secrets)
                save_execution_metadata(
                    query=question,
                    config_path=config_path,
                    config_content=raw_config_for_metadata or original_config,
                    cli_args={
                        "mode": "interactive",
                        "turn": next_turn,
                        "session_id": session_id,
                    },
                )

                # Pass session state for multi-turn filesystem support
                session_info = {
                    "session_id": session_id,
                    "current_turn": current_turn,  # Pass CURRENT turn (for looking up previous turns)
                    "previous_turns": previous_turns,
                    "winning_agents_history": winning_agents_history,
                    "multi_turn": True,  # Enable soft cancellation (return to prompt instead of exit)
                }
                (
                    response,
                    updated_session_id,
                    updated_turn,
                    was_cancelled,
                ) = await run_question_with_history(
                    question,
                    agents,
                    ui_config,
                    conversation_history,
                    session_info,
                    **kwargs,
                )

                # Update session state after completion
                session_id = updated_session_id
                current_turn = updated_turn

                if response:
                    # Add to conversation history
                    conversation_history.append({"role": "user", "content": question})
                    conversation_history.append(
                        {"role": "assistant", "content": response},
                    )

                    # Display the final answer in chat style
                    rich_console.print()
                    rich_console.print(
                        Panel(
                            response,
                            title="[bold green]🤖 MassGen[/bold green]",
                            border_style="green",
                            padding=(1, 2),
                        ),
                    )

                    rich_console.print(
                        f"\n[green]✅ Complete![/green] [cyan]💭 History: {len(conversation_history) // 2} exchanges[/cyan]",
                    )
                    rich_console.print(
                        "[dim]Tip: Use /inspect to view agent outputs[/dim]",
                    )

                elif was_cancelled:
                    # Turn was cancelled by user - add cancelled turn to conversation history
                    # so agents have context about what happened
                    if response:
                        conversation_history.append(
                            {"role": "user", "content": question},
                        )
                        conversation_history.append(
                            {"role": "assistant", "content": response},
                        )
                        logger.info(
                            f"Added cancelled turn to conversation history (phase: {response[:50]}...)",
                        )

                    # Ensure terminal is restored to a good state for next input
                    _restore_terminal_for_input()
                    # Just continue to next prompt (don't print "No response generated")
                    print(
                        f"{BRIGHT_CYAN}Enter your next question or /quit to exit.{RESET}",
                        flush=True,
                    )

                else:
                    print(f"\n{BRIGHT_RED}❌ No response generated{RESET}", flush=True)

            except KeyboardInterrupt:
                # User pressed Ctrl+C at the prompt - just clear line and continue
                print()  # Clean line after ^C
                continue
            except Exception as e:
                print(f"❌ Error: {e}", flush=True)
                print("Please try again or type /quit to exit.", flush=True)

    except KeyboardInterrupt:
        # Outer handler for any uncaught KeyboardInterrupt - just continue
        print()  # Clean line after ^C
