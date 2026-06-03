#!/usr/bin/env python3
"""Plan and spec resolution plus execution command runners.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    from ..plan_storage import PlanSession

from ..logger_config import logger

# --- cross-module references within the cli package ---
from .backends import create_agents_from_config
from .run import run_single_question


def resolve_plan_path(plan_path: str) -> "PlanSession":
    """Resolve a plan path/ID to a PlanSession object.

    Args:
        plan_path: Can be:
            - "latest" - most recent plan
            - Plan ID like "20260115_173113_836955"
            - Full path like ".massgen/plans/plan_20260115_173113_836955"

    Returns:
        PlanSession object

    Raises:
        FileNotFoundError: If plan not found
    """
    from ..plan_storage import PLANS_DIR, PlanSession, PlanStorage

    storage = PlanStorage()

    if plan_path == "latest":
        # Prefer latest resumable session for safer resume-by-default behavior.
        session = storage.get_latest_resumable_plan() or storage.get_latest_plan()
        if not session:
            raise FileNotFoundError("No plans found in .massgen/plans/")
        return session

    # Check if it's a full path
    plan_path_obj = Path(plan_path)
    if plan_path_obj.exists() and plan_path_obj.is_dir():
        # Extract plan_id from directory name
        plan_id = plan_path_obj.name.replace("plan_", "")
        session = PlanSession(plan_id)
        if not session.plan_dir.exists():
            raise FileNotFoundError(f"Plan directory not valid: {plan_path}")
        return session

    # Assume it's a plan ID
    session = PlanSession(plan_path)
    if not session.plan_dir.exists():
        # Try with plan_ prefix stripped if present
        if plan_path.startswith("plan_"):
            plan_id = plan_path[5:]  # Remove "plan_" prefix
            session = PlanSession(plan_id)

    if not session.plan_dir.exists():
        available_plans = list(PLANS_DIR.glob("plan_*")) if PLANS_DIR.exists() else []
        msg = f"Plan not found: {plan_path}"
        if available_plans:
            msg += "\n\nAvailable plans:"
            for plan_dir in sorted(available_plans, reverse=True)[:10]:
                msg += f"\n  - {plan_dir.name.replace('plan_', '')}"
        raise FileNotFoundError(msg)

    return session


async def _execute_plan_phase(
    config: dict[str, Any],
    plan_session: "PlanSession",
    question: str,
    automation: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Internal: Execute a plan (Phase 2) and collect results (Phase 3).

    This is the shared implementation used by both run_plan_and_execute
    and run_execute_plan.

    Args:
        config: Full config dict
        plan_session: PlanSession with frozen plan
        question: Task description
        automation: Whether in automation mode

    Returns:
        Tuple of (final_answer, diff_dict)
    """
    import copy as _copy

    from rich.console import Console

    from ..logger_config import get_log_session_root
    from ..plan_execution import (
        PlanValidationError,
        _get_artifact_items,
        build_execution_prompt,
        build_spec_execution_prompt,
        evaluate_chunk_progress,
        get_next_pending_chunk,
        initialize_chunk_execution_state,
        load_frozen_plan,
        mark_session_resumable,
        prepare_plan_execution_config,
        prepare_spec_execution_config,
        record_chunk_checkpoint,
        setup_agent_workspaces_for_execution,
        validate_chunked_plan,
    )

    console = Console()

    # Detect artifact type (spec vs plan) from session metadata
    metadata = plan_session.load_metadata()
    _artifact_type = getattr(metadata, "artifact_type", None)
    is_spec = _artifact_type == "spec"
    items_key = "requirements" if is_spec else "tasks"
    items_label = "requirements" if is_spec else "tasks"
    artifact_word = "spec" if is_spec else "plan"

    console.print("\n[bold blue]═══ EXECUTION ═══[/bold blue]")
    console.print(f"Executing {artifact_word} with agents...")

    # Update metadata
    metadata.status = "executing"
    plan_session.save_metadata(metadata)
    plan_session.log_event("execution_started", {"question": question})

    # Use shared helper to prepare config (adds context paths, enables planning tools, injects guidance)
    if is_spec:
        exec_config = prepare_spec_execution_config(config, plan_session)
    else:
        exec_config = prepare_plan_execution_config(config, plan_session)
    orchestrator_cfg = exec_config.get("orchestrator", {})

    # Create agents with plan context
    agents = create_agents_from_config(
        exec_config,
        orchestrator_cfg,
        memory_session_id=f"plan_exec_{plan_session.plan_id}",
    )

    # Validate + initialize chunk state
    try:
        chunk_metadata = initialize_chunk_execution_state(plan_session)
        frozen_plan_data = load_frozen_plan(plan_session)
        chunk_order, _ = validate_chunked_plan(frozen_plan_data)
    except (FileNotFoundError, PlanValidationError) as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print(f"[red]Cannot execute {artifact_word} without valid chunk metadata.[/red]")
        raise SystemExit(1)

    _, all_items = _get_artifact_items(frozen_plan_data)
    total_items = len(all_items)
    if total_items == 0:
        console.print(f"[bold red]Error: Frozen {artifact_word} has no {items_label}[/bold red]")
        raise SystemExit(1)
    if not chunk_order:
        console.print(f"[bold red]Error: Frozen {artifact_word} has no chunk order[/bold red]")
        raise SystemExit(1)

    console.print(
        f"[dim]Loaded {total_items} {items_label} across {len(chunk_order)} chunks from frozen {artifact_word}[/dim]",
    )
    if chunk_metadata.status == "resumable" and chunk_metadata.current_chunk:
        console.print(
            f"[yellow]Resuming from chunk: {chunk_metadata.current_chunk}[/yellow]",
        )

    # Build UI config
    requested_display_type = None
    if isinstance(config, dict):
        requested_display_type = (config.get("ui") or {}).get("display_type")
    execution_display_type = "silent" if automation else (requested_display_type or "rich_terminal")
    ui_config = {
        "display_type": execution_display_type,
        "logging_enabled": True,
        "automation_mode": automation,
    }

    # Maintain a full-artifact projection that gets updated chunk by chunk.
    working_plan_data = _copy.deepcopy(frozen_plan_data)
    plan_session.workspace_dir.mkdir(parents=True, exist_ok=True)
    artifact_filename = "spec.json" if is_spec else "plan.json"
    working_plan_file = plan_session.workspace_dir / artifact_filename
    working_plan_file.write_text(json.dumps(working_plan_data, indent=2))

    def _read_chunk_plan_from_agent(agent_obj: Any) -> dict[str, Any] | None:
        """Read the operational artifact produced by an execution turn."""
        if not (hasattr(agent_obj.backend, "filesystem_manager") and agent_obj.backend.filesystem_manager):
            return None
        workspace = Path(agent_obj.backend.filesystem_manager.cwd)
        # Check for both plan.json and spec.json in tasks/ and workspace root
        candidate_files = [
            workspace / "tasks" / artifact_filename,
            workspace / artifact_filename,
            workspace / "tasks" / "plan.json",
            workspace / "plan.json",
        ]
        for candidate in candidate_files:
            if not candidate.exists():
                continue
            try:
                payload = json.loads(candidate.read_text())
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and (isinstance(payload.get("tasks"), list) or isinstance(payload.get("requirements"), list)):
                return payload
        return None

    def _merge_chunk_updates(full_plan: dict[str, Any], chunk_items: list[dict[str, Any]]) -> None:
        """Merge chunk item updates into the full working artifact by id."""
        by_id = {str(item.get("id", "")).strip(): item for item in full_plan.get(items_key, []) if isinstance(item, dict)}
        for updated_item in chunk_items:
            if not isinstance(updated_item, dict):
                continue
            item_id = str(updated_item.get("id", "")).strip()
            if not item_id or item_id not in by_id:
                continue
            by_id[item_id].update(updated_item)

    retry_budget_per_chunk = 2
    retry_counts: dict[str, int] = {}
    if isinstance(chunk_metadata.resumable_state, dict):
        saved_retry_counts = chunk_metadata.resumable_state.get("retry_counts", {})
        if isinstance(saved_retry_counts, dict):
            for chunk_name, retry_value in saved_retry_counts.items():
                try:
                    retry_counts[str(chunk_name)] = int(retry_value)
                except (TypeError, ValueError):
                    continue

    final_answer = ""
    coordination_result: dict[str, Any] = {}

    try:
        while True:
            current_metadata = plan_session.load_metadata()
            active_chunk = current_metadata.current_chunk or get_next_pending_chunk(
                current_metadata,
            )
            if not active_chunk:
                break

            attempt = retry_counts.get(active_chunk, 0) + 1

            current_metadata.status = "executing"
            current_metadata.current_chunk = active_chunk
            current_metadata.resumable_state = {
                "marked_at": datetime.now().isoformat(),
                "current_chunk": active_chunk,
                "reason": "in_progress",
                "retry_counts": dict(retry_counts),
            }
            plan_session.save_metadata(current_metadata)
            plan_session.log_event(
                "chunk_started",
                {"chunk": active_chunk, "attempt": attempt},
            )

            task_count = setup_agent_workspaces_for_execution(
                agents,
                plan_session,
                active_chunk=active_chunk,
            )
            if task_count == 0:
                raise RuntimeError(
                    f"No executable {items_label} found for chunk '{active_chunk}'",
                )

            console.print(
                f"[bold cyan]Chunk {active_chunk}[/bold cyan] " f"[dim](attempt {attempt}, {task_count} {items_label})[/dim]",
            )

            if is_spec:
                execution_prompt = build_spec_execution_prompt(
                    question,
                    plan_session=plan_session,
                    active_chunk=active_chunk,
                    chunk_order=chunk_order,
                )
            else:
                execution_prompt = build_execution_prompt(
                    question,
                    active_chunk=active_chunk,
                    chunk_order=chunk_order,
                )

            result = await run_single_question(
                execution_prompt,
                agents,
                ui_config,
                return_metadata=True,
                orchestrator=orchestrator_cfg,
            )

            if result.get("answer"):
                final_answer = result["answer"]
            coordination_result = result.get("coordination_result", {}) or {}

            winner_id = coordination_result.get("selected_agent")
            chunk_plan_data: dict[str, Any] | None = None
            if winner_id and winner_id in agents:
                chunk_plan_data = _read_chunk_plan_from_agent(agents[winner_id])
            if chunk_plan_data is None:
                # Fallback: use the first readable agent plan.
                for agent in agents.values():
                    chunk_plan_data = _read_chunk_plan_from_agent(agent)
                    if chunk_plan_data:
                        break

            chunk_items = chunk_plan_data.get(items_key, []) or chunk_plan_data.get("tasks", []) if chunk_plan_data else []
            progress = evaluate_chunk_progress(chunk_items)
            if chunk_items:
                _merge_chunk_updates(working_plan_data, chunk_items)
                working_plan_file.write_text(json.dumps(working_plan_data, indent=2))

            if bool(coordination_result.get("is_orchestrator_timeout")):
                timeout_reason = str(
                    coordination_result.get("timeout_reason") or "Time limit exceeded",
                ).strip()
                timeout_msg = f"Chunk '{active_chunk}' timed out: {timeout_reason}"
                updated_metadata = record_chunk_checkpoint(
                    plan_session,
                    chunk=active_chunk,
                    status="timed_out",
                    attempt=attempt,
                    progress=progress,
                    error_message=timeout_msg,
                )
                updated_metadata.completed_chunks = updated_metadata.completed_chunks or []
                if active_chunk not in updated_metadata.completed_chunks:
                    # Treat timeout as skipped for chunk-to-chunk progression.
                    updated_metadata.completed_chunks.append(active_chunk)
                updated_metadata.current_chunk = get_next_pending_chunk(updated_metadata)
                if updated_metadata.current_chunk is None:
                    updated_metadata.status = "completed"
                    updated_metadata.resumable_state = None
                    console.print(
                        f"[yellow]Chunk {active_chunk} timed out and was skipped[/yellow] " "[dim](no remaining chunks)[/dim]",
                    )
                else:
                    updated_metadata.status = "executing"
                    updated_metadata.resumable_state = {
                        "marked_at": datetime.now().isoformat(),
                        "current_chunk": updated_metadata.current_chunk,
                        "reason": f"chunk_timeout_skipped: {active_chunk}",
                        "retry_counts": dict(retry_counts),
                    }
                    console.print(
                        f"[yellow]Chunk {active_chunk} timed out and was skipped[/yellow] " f"[dim]→ next: {updated_metadata.current_chunk}[/dim]",
                    )
                plan_session.save_metadata(updated_metadata)
                retry_counts[active_chunk] = 0
                continue

            if progress["is_complete"]:
                retry_counts[active_chunk] = 0
                updated_metadata = record_chunk_checkpoint(
                    plan_session,
                    chunk=active_chunk,
                    status="completed",
                    attempt=attempt,
                    progress=progress,
                )
                next_chunk = updated_metadata.current_chunk
                if next_chunk:
                    console.print(
                        f"[green]✓ Completed chunk {active_chunk}[/green] " f"[dim]→ next: {next_chunk}[/dim]",
                    )
                else:
                    console.print(
                        f"[green]✓ Completed final chunk {active_chunk}[/green]",
                    )
            else:
                retry_counts[active_chunk] = retry_counts.get(active_chunk, 0) + 1
                exhausted = not progress["made_progress"] and retry_counts[active_chunk] > retry_budget_per_chunk
                if exhausted:
                    error_msg = f"Chunk '{active_chunk}' exhausted retry budget " f"({retry_budget_per_chunk}) without progress"
                    record_chunk_checkpoint(
                        plan_session,
                        chunk=active_chunk,
                        status="failed",
                        attempt=attempt,
                        progress=progress,
                        error_message=error_msg,
                    )
                    raise RuntimeError(error_msg)

                record_chunk_checkpoint(
                    plan_session,
                    chunk=active_chunk,
                    status="incomplete",
                    attempt=attempt,
                    progress=progress,
                )
                console.print(
                    f"[yellow]Chunk {active_chunk} incomplete[/yellow] "
                    f"[dim](completed {progress['completed_count']}/{progress['total_tasks']}, "
                    f"retry {retry_counts[active_chunk]}/{retry_budget_per_chunk})[/dim]",
                )
    except KeyboardInterrupt:
        current_metadata = plan_session.load_metadata()
        mark_session_resumable(
            plan_session,
            current_chunk=current_metadata.current_chunk,
            reason="interrupted_by_user",
            retry_counts=retry_counts,
        )
        raise
    except Exception as e:
        current_metadata = plan_session.load_metadata()
        if current_metadata.status not in {"failed", "completed"}:
            mark_session_resumable(
                plan_session,
                current_chunk=current_metadata.current_chunk,
                reason=f"execution_error: {e}",
                retry_counts=retry_counts,
            )
        raise

    # ========== Collection & Reporting ==========
    console.print("\n[bold blue]═══ COLLECTION ═══[/bold blue]")

    # Compute plan diff
    diff = plan_session.compute_plan_diff()
    plan_session.diff_file.write_text(json.dumps(diff, indent=2))
    plan_session.log_event("diff_computed", diff)

    # Update metadata
    metadata = plan_session.load_metadata()
    if metadata.current_chunk is None:
        metadata.status = "completed"
        metadata.resumable_state = None
    metadata.execution_session_id = coordination_result.get("session_id") if coordination_result else None
    try:
        metadata.execution_log_dir = str(get_log_session_root())
    except Exception:
        metadata.execution_log_dir = None
    plan_session.save_metadata(metadata)

    # Print adherence summary
    adherence = 100 - diff.get("divergence_score", 0) * 100
    console.print(f"\n[green]Plan Adherence: {adherence:.1f}%[/green]")
    console.print(f"Plan stored at: {plan_session.plan_dir}")

    if diff.get("tasks_added"):
        console.print(f"[yellow]Tasks added: {len(diff['tasks_added'])}[/yellow]")
    if diff.get("tasks_removed"):
        console.print(f"[yellow]Tasks removed: {len(diff['tasks_removed'])}[/yellow]")
    if diff.get("tasks_modified"):
        console.print(f"[yellow]Tasks modified: {len(diff['tasks_modified'])}[/yellow]")

    return final_answer, diff


async def run_execute_plan(
    config: dict[str, Any],
    plan_path: str,
    question: str | None = None,
    automation: bool = False,
) -> tuple[str, Any]:
    """
    Execute an existing plan (skips planning phase).

    Args:
        config: Full config dict
        plan_path: Path to plan directory, plan ID, or "latest"
        question: Optional task description override
        automation: Whether in automation mode

    Returns:
        Tuple of (final_answer, plan_session)
    """
    from rich.console import Console

    console = Console()

    # Resolve plan path to session
    plan_session = resolve_plan_path(plan_path)

    # Load plan metadata
    metadata = plan_session.load_metadata()
    console.print(f"\n[bold cyan]Executing plan: {plan_session.plan_id}[/bold cyan]")
    console.print(f"Created: {metadata.created_at}")
    console.print(f"Status: {metadata.status}")

    # Read frozen plan/spec to get task count - fail fast if missing or unreadable
    frozen_plan_file = plan_session.frozen_dir / "plan.json"
    frozen_spec_file = plan_session.frozen_dir / "spec.json"
    if frozen_plan_file.exists():
        artifact_file = frozen_plan_file
    elif frozen_spec_file.exists():
        artifact_file = frozen_spec_file
    else:
        console.print(f"[bold red]Error: Frozen plan/spec not found at {plan_session.frozen_dir}[/bold red]")
        console.print("[red]Cannot execute without a valid plan.json or spec.json[/red]")
        raise SystemExit(1)

    try:
        plan_data = json.loads(artifact_file.read_text())
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error: Failed to parse frozen artifact: {e}[/bold red]")
        console.print(f"[red]File: {artifact_file}[/red]")
        raise SystemExit(1)

    items = plan_data.get("tasks", []) or plan_data.get("requirements", [])
    items_label = "Requirements" if "requirements" in plan_data else "Tasks"
    console.print(f"{items_label}: {len(items)}")

    # Build question if not provided
    if question is None:
        question = "Execute the plan in tasks/plan.json."

    # Run execution phase
    final_answer, _ = await _execute_plan_phase(
        config=config,
        plan_session=plan_session,
        question=question,
        automation=automation,
    )

    return final_answer, plan_session


async def run_execute_spec(
    config: dict[str, Any],
    spec_path: str,
    question: str | None = None,
    automation: bool = False,
) -> tuple[str, Any]:
    """
    Execute against an existing spec (skips spec creation phase).

    Args:
        config: Full config dict
        spec_path: Path to spec directory, spec/plan ID, or "latest"
        question: Optional task description override
        automation: Whether in automation mode

    Returns:
        Tuple of (final_answer, plan_session)
    """
    from rich.console import Console

    console = Console()

    # Resolve spec path to session (reuses plan path resolution)
    plan_session = resolve_plan_path(spec_path)

    # Load metadata
    metadata = plan_session.load_metadata()
    console.print(f"\n[bold cyan]Executing spec: {plan_session.plan_id}[/bold cyan]")
    console.print(f"Created: {metadata.created_at}")
    console.print(f"Status: {metadata.status}")

    # Read frozen spec to get requirement count - fail fast if missing
    frozen_spec_file = plan_session.frozen_dir / "spec.json"
    if not frozen_spec_file.exists():
        console.print(f"[bold red]Error: Frozen spec not found at {frozen_spec_file}[/bold red]")
        console.print("[red]Cannot execute spec without a valid frozen spec.json[/red]")
        raise SystemExit(1)

    try:
        spec_data = json.loads(frozen_spec_file.read_text())
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error: Failed to parse frozen spec: {e}[/bold red]")
        console.print(f"[red]File: {frozen_spec_file}[/red]")
        raise SystemExit(1)

    req_count = len(spec_data.get("requirements", []))
    console.print(f"Requirements: {req_count}")

    # Build question if not provided
    if question is None:
        question = "Execute the spec in tasks/spec.json. Implement all requirements."

    # Run execution phase
    final_answer, _ = await _execute_plan_phase(
        config=config,
        plan_session=plan_session,
        question=question,
        automation=automation,
    )

    return final_answer, plan_session


async def run_plan_and_execute(
    config: dict[str, Any],
    question: str,
    plan_depth: str = "dynamic",
    plan_thoroughness: str = "standard",
    plan_target_steps: int | None = None,
    plan_target_chunks: int | None = None,
    broadcast_mode: str | bool = "false",
    automation: bool = False,
    debug: bool = False,
    config_path: str | None = None,
) -> tuple[str, Any]:
    """
    Run full plan-and-execute workflow:
    1. Phase 1: Run planning subprocess to create task plan
    2. Phase 2: Execute the plan with plan context injected

    Args:
        config: Full config dict
        question: User's task/question
        plan_depth: dynamic/shallow/medium/deep
        plan_thoroughness: standard/thorough
        plan_target_steps: Optional explicit target number of tasks.
        plan_target_chunks: Optional explicit target number of chunks (defaults to 1).
        broadcast_mode: human/agents/false
        automation: Whether in automation mode
        debug: Debug mode flag
        config_path: Path to config file (for subprocess)

    Returns:
        Tuple of (final_answer, plan_session)
    """
    import os
    import subprocess
    import tempfile

    import yaml
    from rich.console import Console

    from ..plan_storage import PlanStorage

    console = Console()

    # ========== PHASE 1: Planning ==========
    console.print("\n[bold blue]═══ PHASE 1: PLANNING ═══[/bold blue]")
    effective_plan_target_chunks = plan_target_chunks if isinstance(plan_target_chunks, int) and plan_target_chunks > 0 else 1
    planning_controls = [f"depth={plan_depth}"]
    if plan_target_steps is not None:
        planning_controls.append(f"target_steps={plan_target_steps}")
    planning_controls.append(f"target_chunks={effective_plan_target_chunks}")
    console.print(f"Running agents to create task plan ({', '.join(planning_controls)})...")

    # Create plan storage
    storage = PlanStorage()

    # Normalize broadcast mode to a CLI-safe string.
    normalized_broadcast_mode = "false" if broadcast_mode is False else str(broadcast_mode)
    if normalized_broadcast_mode not in {"human", "agents", "false"}:
        normalized_broadcast_mode = "false"

    # Handle broadcast mode for automation
    # In automation mode, "human" broadcast doesn't work (no human to respond)
    # Auto-switch to "false" for fully autonomous planning
    effective_broadcast_mode = normalized_broadcast_mode
    if automation and normalized_broadcast_mode == "human":
        console.print(
            "[yellow]Note: Switching broadcast mode from 'human' to 'false' for automation mode[/yellow]",
        )
        effective_broadcast_mode = "false"

    # For non-automation runs, enable full Textual planning when the config explicitly asks for it.
    ui_cfg = config.get("ui", {}) if isinstance(config, dict) else {}
    planning_display_type = ui_cfg.get("display_type")
    use_interactive_planning_subprocess = not automation and planning_display_type == "textual_terminal"

    # Build planning subprocess command
    # Write config to temp file if not provided
    temp_config_path = None
    if not config_path:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_config_path = f.name
            config_path = temp_config_path

    cmd = [
        "uv",
        "run",
        "massgen",
    ]
    if use_interactive_planning_subprocess:
        cmd.extend(["--display", "textual"])
    else:
        cmd.append("--automation")
    cmd.extend(
        [
            "--plan",
            "--plan-depth",
            plan_depth,
            "--plan-thoroughness",
            plan_thoroughness,
            "--broadcast",
            effective_broadcast_mode,
            "--config",
            config_path,
        ],
    )
    if plan_target_steps is not None:
        cmd.extend(["--plan-steps", str(plan_target_steps)])
    cmd.extend(["--plan-chunks", str(effective_plan_target_chunks)])

    if debug:
        cmd.append("--debug")

    # Add end-of-options marker and question last, so question starting with '-' is treated as data
    cmd.extend(["--", question])

    # Run planning subprocess
    logger.info(f"[PlanAndExecute] Starting planning subprocess: {' '.join(cmd)}")

    try:
        log_dir = None
        final_dir = None

        if use_interactive_planning_subprocess:
            # Interactive planning (Textual) needs direct terminal ownership.
            log_base_dir = Path(os.getenv("MASSGEN_LOG_BASE_DIR", ".massgen/massgen_logs"))
            existing_log_dirs = {p.name for p in log_base_dir.glob("log_*")} if log_base_dir.exists() else set()

            result = subprocess.run(cmd)
            if result.returncode != 0:
                raise RuntimeError(f"Planning subprocess failed with exit code {result.returncode}")

            if not log_base_dir.exists():
                raise RuntimeError("Planning completed but no log directory base was found")

            created_logs = [p for p in log_base_dir.glob("log_*") if p.name not in existing_log_dirs]
            if created_logs:
                log_root = max(created_logs, key=lambda p: p.stat().st_mtime)
            else:
                all_logs = list(log_base_dir.glob("log_*"))
                if not all_logs:
                    raise RuntimeError("Planning completed but no log session directory was found")
                log_root = max(all_logs, key=lambda p: p.stat().st_mtime)

            log_dir = str(log_root)

            final_candidates = [
                log_root / "turn_1" / "final",
                log_root / "final",
            ]
            if not any(path.exists() for path in final_candidates):
                turn_dirs = sorted(log_root.glob("turn_*"))
                final_candidates.extend(turn_dir / "final" for turn_dir in turn_dirs)
            for candidate in final_candidates:
                if candidate.exists():
                    final_dir = candidate
                    break
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout to avoid deadlock
                text=True,
                bufsize=1,  # Line buffered
            )

            # Parse LOG_DIR, STATUS, and FINAL_DIR from stdout
            stdout_lines = []
            for line in process.stdout:
                stdout_lines.append(line)
                if line.startswith("LOG_DIR:"):
                    log_dir = line.split(":", 1)[1].strip()
                elif line.startswith("FINAL_DIR:"):
                    final_dir = Path(line.split(":", 1)[1].strip())
                # Print output in non-automation mode for visibility
                if not automation:
                    print(line, end="")

            # Wait for process to complete
            process.wait()

            if process.returncode != 0:
                # stderr is merged into stdout, so show captured output
                output = "".join(stdout_lines)
                raise RuntimeError(f"Planning subprocess failed:\n{output}")

            if not log_dir:
                raise RuntimeError("Planning subprocess did not provide LOG_DIR")

        logger.info(f"[PlanAndExecute] Planning complete. Log dir: {log_dir}")

    except Exception as e:
        console.print(f"[red]Planning failed: {e}[/red]")
        raise
    finally:
        # Clean up temp config file
        if temp_config_path:
            try:
                Path(temp_config_path).unlink()
            except Exception:
                pass

    # Create plan session and copy workspace
    planning_session_id = Path(log_dir).name
    plan_session = storage.create_plan(planning_session_id, log_dir)

    # Use FINAL_DIR from subprocess output, or fall back to log_dir/final/
    if not final_dir:
        final_dir = Path(log_dir) / "final"

    if final_dir.exists():
        # Find the actual workspace directory within final/
        # Structure is: final/agent_*/workspace/ (we want only workspace content)
        workspace_source = None

        # Look for agent workspace directories
        agent_dirs = list(final_dir.glob("agent_*/workspace"))
        if agent_dirs:
            # Use first agent's workspace (in planning mode, typically one agent or winner)
            workspace_source = agent_dirs[0]

            # Check if two-tier workspace is enabled (deliverable/ exists)
            # If so, only copy the deliverable part
            deliverable_dir = workspace_source / "deliverable"
            if deliverable_dir.exists():
                console.print("[dim]Two-tier workspace detected, copying deliverable/ only[/dim]")
                workspace_source = deliverable_dir

            logger.info(f"[PlanAndExecute] Using workspace source: {workspace_source}")
        else:
            # Fallback to final_dir if no agent workspace structure found
            # This handles legacy or non-standard setups
            workspace_source = final_dir
            logger.warning(f"[PlanAndExecute] No agent workspace found in {final_dir}, using full directory")

        # Copy only workspace artifacts to plan storage
        # Extract context paths from config to preserve for execution
        orchestrator_cfg = config.get("orchestrator", {})
        context_paths = orchestrator_cfg.get("context_paths", [])
        storage.finalize_planning_phase(plan_session, workspace_source, context_paths=context_paths)

        # Verify a valid artifact was created - if not, clean up and fail
        frozen_plan = plan_session.frozen_dir / "plan.json"
        frozen_spec = plan_session.frozen_dir / "spec.json"
        if not frozen_plan.exists() and not frozen_spec.exists():
            console.print("[bold red]Error: Planning phase did not produce a valid plan.json or spec.json[/bold red]")
            console.print("[red]The planning agent may have ended early or failed to create an artifact.[/red]")
            # Clean up the empty plan session directory
            if plan_session.plan_dir.exists():
                shutil.rmtree(plan_session.plan_dir)
                logger.info(f"[PlanAndExecute] Cleaned up empty plan session: {plan_session.plan_dir}")
            raise SystemExit(1)

        console.print(f"[green]Plan created and frozen: {plan_session.plan_dir}[/green]")
    else:
        console.print("[bold red]Error: No final/ directory found in planning logs[/bold red]")
        console.print("[red]Planning phase did not complete successfully.[/red]")
        # Clean up the empty plan session directory
        if plan_session.plan_dir.exists():
            shutil.rmtree(plan_session.plan_dir)
            logger.info(f"[PlanAndExecute] Cleaned up empty plan session: {plan_session.plan_dir}")
        raise SystemExit(1)

    # ========== PHASE 2: Execution ==========
    console.print("\n[bold blue]═══ PHASE 2: EXECUTION ═══[/bold blue]")

    # Use shared execution phase implementation
    final_answer, _ = await _execute_plan_phase(
        config=config,
        plan_session=plan_session,
        question=question,
        automation=automation,
    )

    return final_answer, plan_session
