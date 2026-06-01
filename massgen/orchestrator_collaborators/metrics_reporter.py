"""Metrics reporting helpers, extracted from Orchestrator.

This collaborator owns the logic for persisting per-session metrics
(``metrics_events.json`` / ``metrics_summary.json``), aggregating
subagent costs from on-disk status files, and the public
``save_coordination_logs`` entry point that flushes coordination
state at end-of-run.

External callers
----------------
* ``massgen/frontend/coordination_ui.py`` calls
  ``orch.save_coordination_logs`` and ``orch.save_metrics``.
* ``massgen/frontend/displays/rich_terminal_display.py`` calls
  ``orch._collect_subagent_costs``.
* Tests (``test_answer_path_normalization.py``) monkeypatch
  ``orch.save_metrics`` and ``orch.coordination_tracker.save_coordination_logs``.

The orchestrator keeps thin delegators with identical signatures so all
of the above continue to work unchanged.  Inside this collaborator we
route any sibling-method calls through ``self._orchestrator.<method>``
so monkeypatches on the orchestrator instance stick.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import get_log_session_dir, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class MetricsReporter:
    """Persist per-session metrics and aggregate subagent costs."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def save_coordination_logs(self) -> None:
        """Public method to save coordination logs after final presentation is complete."""
        orch = self._orchestrator
        logger.info("[Orchestrator] save_coordination_logs called")
        # End the coordination session
        orch.coordination_tracker._end_session()

        # Save coordination logs using the coordination tracker
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            logger.info(f"[Orchestrator] Saving to {log_session_dir}")
            orch.coordination_tracker.save_coordination_logs(log_session_dir)
            # Also save final status.json with complete token/cost data
            orch.coordination_tracker.save_status_file(
                log_session_dir,
                orchestrator=orch,
            )
            # Save detailed metrics files (route through orchestrator so
            # monkeypatches on orch.save_metrics take effect).
            orch.save_metrics(log_session_dir)

    def save_metrics(self, log_dir: Path) -> None:
        """Save detailed metrics files for analysis.

        Outputs:
            - metrics_events.json: Detailed event log of all tool executions and round completions
            - metrics_summary.json: Aggregated summary with per-agent and global statistics
        """
        orch = self._orchestrator
        try:
            log_dir = Path(log_dir)

            # Collect all tool metrics and round history from agents
            all_tool_events = []
            all_round_events = []
            agent_metrics = {}

            for agent_id, agent in orch.agents.items():
                if hasattr(agent, "backend") and agent.backend:
                    backend = agent.backend

                    # Collect detailed tool execution events
                    if hasattr(backend, "get_tool_metrics"):
                        tool_events = backend.get_tool_metrics()
                        all_tool_events.extend(tool_events)

                    # Collect round token history
                    if hasattr(backend, "get_round_token_history"):
                        round_history = backend.get_round_token_history()
                        all_round_events.extend(round_history)

                    # Collect per-agent summaries
                    agent_metrics[agent_id] = {
                        "tool_metrics": backend.get_tool_metrics_summary() if hasattr(backend, "get_tool_metrics_summary") else None,
                        "round_history": backend.get_round_token_history() if hasattr(backend, "get_round_token_history") else None,
                        "token_usage": (
                            {
                                "input_tokens": backend.token_usage.input_tokens if backend.token_usage else 0,
                                "output_tokens": backend.token_usage.output_tokens if backend.token_usage else 0,
                                "reasoning_tokens": backend.token_usage.reasoning_tokens if backend.token_usage else 0,
                                "cached_input_tokens": backend.token_usage.cached_input_tokens if backend.token_usage else 0,
                                "estimated_cost": (
                                    round(
                                        backend.token_usage.estimated_cost,
                                        6,
                                    )
                                    if backend.token_usage
                                    else 0
                                ),
                            }
                            if hasattr(backend, "token_usage")
                            else None
                        ),
                    }

            # Save detailed events log
            events_file = log_dir / "metrics_events.json"
            events_data = {
                "meta": {
                    "generated_at": time.time(),
                    "session_id": log_dir.name,
                    "question": orch.current_task,
                },
                "tool_executions": all_tool_events,
                "round_completions": all_round_events,
            }
            with open(events_file, "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=2, default=str)

            # Build aggregated summary
            # Aggregate tool stats
            tools_summary = {
                "total_calls": 0,
                "total_failures": 0,
                "total_execution_time_ms": 0.0,
                "by_tool": {},
            }
            for event in all_tool_events:
                tools_summary["total_calls"] += 1
                if not event.get("success", True):
                    tools_summary["total_failures"] += 1
                tools_summary["total_execution_time_ms"] += event.get(
                    "execution_time_ms",
                    0,
                )

                tool_name = event.get("tool_name", "unknown")
                if tool_name not in tools_summary["by_tool"]:
                    tools_summary["by_tool"][tool_name] = {
                        "call_count": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "total_execution_time_ms": 0.0,
                        "total_input_chars": 0,
                        "total_output_chars": 0,
                        "tool_type": event.get("tool_type", "unknown"),
                    }
                tools_summary["by_tool"][tool_name]["call_count"] += 1
                if event.get("success", True):
                    tools_summary["by_tool"][tool_name]["success_count"] += 1
                else:
                    tools_summary["by_tool"][tool_name]["failure_count"] += 1
                tools_summary["by_tool"][tool_name]["total_execution_time_ms"] += event.get("execution_time_ms", 0)
                tools_summary["by_tool"][tool_name]["total_input_chars"] += event.get(
                    "input_chars",
                    0,
                )
                tools_summary["by_tool"][tool_name]["total_output_chars"] += event.get(
                    "output_chars",
                    0,
                )

            # Calculate tool averages and token estimates
            for tool_stats in tools_summary["by_tool"].values():
                count = tool_stats["call_count"]
                if count > 0:
                    tool_stats["avg_execution_time_ms"] = round(
                        tool_stats["total_execution_time_ms"] / count,
                        2,
                    )
                    tool_stats["input_tokens_est"] = tool_stats["total_input_chars"] // 4
                    tool_stats["output_tokens_est"] = tool_stats["total_output_chars"] // 4

            # Aggregate round stats
            rounds_summary = {
                "total_rounds": len(all_round_events),
                "by_outcome": {
                    "answer": 0,
                    "vote": 0,
                    "presentation": 0,
                    "post_evaluation": 0,
                    "restarted": 0,
                    "error": 0,
                    "timeout": 0,
                },
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_reasoning_tokens": 0,
                "total_estimated_cost": 0.0,
                "avg_context_usage_pct": 0.0,
            }
            total_context_pct = 0.0
            for r in all_round_events:
                outcome = r.get("outcome", "unknown")
                if outcome in rounds_summary["by_outcome"]:
                    rounds_summary["by_outcome"][outcome] += 1
                rounds_summary["total_input_tokens"] += r.get("input_tokens", 0)
                rounds_summary["total_output_tokens"] += r.get("output_tokens", 0)
                rounds_summary["total_reasoning_tokens"] += r.get("reasoning_tokens", 0)
                rounds_summary["total_estimated_cost"] += r.get("estimated_cost", 0.0)
                total_context_pct += r.get("context_usage_pct", 0.0)

            rounds_summary["total_estimated_cost"] = round(
                rounds_summary["total_estimated_cost"],
                6,
            )
            if len(all_round_events) > 0:
                rounds_summary["avg_context_usage_pct"] = round(
                    total_context_pct / len(all_round_events),
                    2,
                )

            # Calculate total costs across all agents
            total_cost = 0.0
            total_input_tokens = 0
            total_output_tokens = 0
            total_reasoning_tokens = 0
            for am in agent_metrics.values():
                tu = am.get("token_usage")
                if tu:
                    total_cost += tu.get("estimated_cost", 0)
                    total_input_tokens += tu.get("input_tokens", 0)
                    total_output_tokens += tu.get("output_tokens", 0)
                    total_reasoning_tokens += tu.get("reasoning_tokens", 0)

            # Collect subagent costs from status files (route through orchestrator
            # so monkeypatches on _collect_subagent_costs are respected).
            subagents_summary = orch._collect_subagent_costs(log_dir)
            subagent_total_cost = subagents_summary.get("total_estimated_cost", 0.0)

            # Aggregate API call timing metrics
            api_timing = {
                "total_calls": 0,
                "total_time_ms": 0.0,
                "avg_time_ms": 0.0,
                "avg_ttft_ms": 0.0,
                "by_round": {},
                "by_backend": {},
            }
            total_ttft_ms = 0.0

            for agent_id, agent in orch.agents.items():
                if hasattr(agent, "backend") and agent.backend:
                    backend = agent.backend
                    if hasattr(backend, "get_api_call_history"):
                        for metric in backend.get_api_call_history():
                            api_timing["total_calls"] += 1
                            api_timing["total_time_ms"] += metric.duration_ms
                            total_ttft_ms += metric.time_to_first_token_ms

                            # By round
                            round_key = f"round_{metric.round_number}"
                            if round_key not in api_timing["by_round"]:
                                api_timing["by_round"][round_key] = {
                                    "calls": 0,
                                    "time_ms": 0.0,
                                    "ttft_ms": 0.0,
                                }
                            api_timing["by_round"][round_key]["calls"] += 1
                            api_timing["by_round"][round_key]["time_ms"] += metric.duration_ms
                            api_timing["by_round"][round_key]["ttft_ms"] += metric.time_to_first_token_ms

                            # By backend
                            if metric.backend_name not in api_timing["by_backend"]:
                                api_timing["by_backend"][metric.backend_name] = {
                                    "calls": 0,
                                    "time_ms": 0.0,
                                    "ttft_ms": 0.0,
                                }
                            api_timing["by_backend"][metric.backend_name]["calls"] += 1
                            api_timing["by_backend"][metric.backend_name]["time_ms"] += metric.duration_ms
                            api_timing["by_backend"][metric.backend_name]["ttft_ms"] += metric.time_to_first_token_ms

            # Calculate averages
            if api_timing["total_calls"] > 0:
                api_timing["avg_time_ms"] = round(
                    api_timing["total_time_ms"] / api_timing["total_calls"],
                    2,
                )
                api_timing["avg_ttft_ms"] = round(
                    total_ttft_ms / api_timing["total_calls"],
                    2,
                )

            # Round timing values
            api_timing["total_time_ms"] = round(api_timing["total_time_ms"], 2)
            for round_data in api_timing["by_round"].values():
                round_data["time_ms"] = round(round_data["time_ms"], 2)
                round_data["ttft_ms"] = round(round_data["ttft_ms"], 2)
            for backend_data in api_timing["by_backend"].values():
                backend_data["time_ms"] = round(backend_data["time_ms"], 2)
                backend_data["ttft_ms"] = round(backend_data["ttft_ms"], 2)

            # Save summary file
            summary_file = log_dir / "metrics_summary.json"
            summary_data = {
                "meta": {
                    "generated_at": time.time(),
                    "session_id": log_dir.name,
                    "question": orch.current_task,
                    "num_agents": len(orch.agents),
                    "winner": orch.coordination_tracker.final_winner,
                },
                "totals": {
                    "estimated_cost": round(total_cost + subagent_total_cost, 6),
                    "agent_cost": round(total_cost, 6),
                    "subagent_cost": round(subagent_total_cost, 6),
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "reasoning_tokens": total_reasoning_tokens,
                },
                "tools": tools_summary,
                "rounds": rounds_summary,
                "api_timing": api_timing,
                "agents": agent_metrics,
                "subagents": subagents_summary,
            }
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, default=str)

            logger.info(f"[Orchestrator] Saved metrics files to {log_dir}")

        except Exception as e:
            logger.warning(f"Failed to save metrics files: {e}", exc_info=True)

    def collect_subagent_costs(self, log_dir: Path) -> dict[str, Any]:
        """Collect subagent costs and metrics from status.json and subprocess metrics.

        Args:
            log_dir: Path to the log directory (e.g., turn_1/attempt_1)

        Returns:
            Dictionary with total costs, timing data, and per-subagent breakdown
        """
        subagents_dir = log_dir / "subagents"
        if not subagents_dir.exists():
            return {
                "total_subagents": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_estimated_cost": 0.0,
                "total_api_time_ms": 0.0,
                "total_api_calls": 0,
                "subagents": [],
            }

        total_input_tokens = 0
        total_output_tokens = 0
        total_estimated_cost = 0.0
        total_api_time_ms = 0.0
        total_api_calls = 0
        subagent_details = []

        # Find all status.json files in subagent directories
        # Status file is at full_logs/status.json (written by subagent's Orchestrator)
        for subagent_path in subagents_dir.iterdir():
            if not subagent_path.is_dir():
                continue

            # Read from full_logs/status.json (the single source of truth)
            status_file = subagent_path / "full_logs" / "status.json"
            if not status_file.exists():
                continue

            try:
                # Read status.json for basic info
                with open(status_file, encoding="utf-8") as f:
                    status_data = json.load(f)

                # Extract costs from the new structure
                costs = status_data.get("costs", {})
                input_tokens = costs.get("total_input_tokens", 0)
                output_tokens = costs.get("total_output_tokens", 0)
                cost = costs.get("total_estimated_cost", 0.0)

                # Extract timing from meta
                meta = status_data.get("meta", {})
                elapsed_seconds = meta.get("elapsed_seconds", 0.0)

                # Extract coordination info
                coordination = status_data.get("coordination", {})
                phase = coordination.get("phase", "unknown")

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_estimated_cost += cost

                # Initialize subagent detail entry
                subagent_detail = {
                    "subagent_id": subagent_path.name,
                    "status": phase,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost": round(cost, 6),
                    "elapsed_seconds": elapsed_seconds,
                    "task": meta.get("question", "")[:100],
                }

                # Try to read subprocess metrics for API timing data
                subprocess_logs_file = subagent_path / "subprocess_logs.json"
                if subprocess_logs_file.exists():
                    try:
                        with open(subprocess_logs_file, encoding="utf-8") as f:
                            subprocess_logs = json.load(f)

                        subprocess_log_dir = subprocess_logs.get("subprocess_log_dir")
                        if subprocess_log_dir:
                            # Read the subprocess's metrics_summary.json
                            metrics_file = Path(subprocess_log_dir) / "metrics_summary.json"
                            if metrics_file.exists():
                                with open(metrics_file, encoding="utf-8") as f:
                                    metrics_data = json.load(f)

                                # Extract API timing data
                                api_timing = metrics_data.get("api_timing", {})
                                if api_timing:
                                    subagent_api_time = api_timing.get(
                                        "total_time_ms",
                                        0.0,
                                    )
                                    subagent_api_calls = api_timing.get(
                                        "total_calls",
                                        0,
                                    )

                                    total_api_time_ms += subagent_api_time
                                    total_api_calls += subagent_api_calls

                                    subagent_detail["api_timing"] = {
                                        "total_time_ms": round(subagent_api_time, 2),
                                        "total_calls": subagent_api_calls,
                                        "avg_time_ms": api_timing.get(
                                            "avg_time_ms",
                                            0.0,
                                        ),
                                        "avg_ttft_ms": api_timing.get(
                                            "avg_ttft_ms",
                                            0.0,
                                        ),
                                    }
                    except Exception as e:
                        logger.debug(
                            f"Failed to read subprocess metrics for {subagent_path.name}: {e}",
                        )

                subagent_details.append(subagent_detail)

            except Exception as e:
                logger.debug(f"Failed to read subagent status from {status_file}: {e}")

        return {
            "total_subagents": len(subagent_details),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_estimated_cost": round(total_estimated_cost, 6),
            "total_api_time_ms": round(total_api_time_ms, 2),
            "total_api_calls": total_api_calls,
            "subagents": subagent_details,
        }
