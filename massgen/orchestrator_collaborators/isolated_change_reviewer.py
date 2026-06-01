"""Isolated-change review flow, extracted from Orchestrator.

Owns the review/apply pipeline for changes accumulated in an
``IsolationContextManager``. The collaborator holds a back-ref to the
orchestrator because several helpers (``_resolve_final_workspace_path``,
``_get_vote_results``, ``_sync_applied_context_files_into_final_artifacts``,
``_show_workspace_modal_if_needed``) remain on the orchestrator. The
``_pending_review_rework`` attribute is written via the back-ref because the
final-presentation restart loop reads it from the orchestrator.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from massgen.backend.base import StreamChunk
from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.chat_agent import ChatAgent
    from massgen.filesystem_manager import IsolationContextManager
    from massgen.orchestrator import Orchestrator


class IsolatedChangeReviewer:
    """Review/apply changes from an isolated write context."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def _count_diff_files(diff_text: str) -> int:
        if not diff_text:
            return 0
        return sum(1 for line in diff_text.splitlines() if line.startswith("diff --git "))

    @staticmethod
    def _normalize_approved_files_by_context(metadata: Any) -> dict[str, list[str]]:
        if not isinstance(metadata, dict):
            return {}
        raw_mapping = metadata.get("approved_files_by_context")
        if not isinstance(raw_mapping, dict):
            return {}

        normalized: dict[str, list[str]] = {}
        for context_path, approved_paths in raw_mapping.items():
            if not isinstance(context_path, str):
                continue
            if not isinstance(approved_paths, list):
                continue
            normalized[os.path.abspath(context_path)] = [path for path in approved_paths if isinstance(path, str)]
        return normalized

    @staticmethod
    def _normalize_approved_hunks_by_context(
        metadata: Any,
    ) -> dict[str, dict[str, list[int]]]:
        if not isinstance(metadata, dict):
            return {}
        raw_mapping = metadata.get("approved_hunks_by_context")
        if not isinstance(raw_mapping, dict):
            return {}

        normalized: dict[str, dict[str, list[int]]] = {}
        for context_path, hunks_by_file in raw_mapping.items():
            if not isinstance(context_path, str):
                continue
            if not isinstance(hunks_by_file, dict):
                continue
            context_hunks: dict[str, list[int]] = {}
            for file_path, hunk_indexes in hunks_by_file.items():
                if not isinstance(file_path, str):
                    continue
                if not isinstance(hunk_indexes, list):
                    continue
                normalized_indexes: list[int] = []
                for hunk_idx in hunk_indexes:
                    try:
                        hunk_idx_int = int(hunk_idx)
                    except (TypeError, ValueError):
                        continue
                    if hunk_idx_int >= 0:
                        normalized_indexes.append(hunk_idx_int)
                context_hunks[file_path] = sorted(set(normalized_indexes))
            normalized[os.path.abspath(context_path)] = context_hunks
        return normalized

    @staticmethod
    def _is_in_context_prefix(rel_path: str, context_prefix: str) -> bool:
        normalized_rel = rel_path.replace("\\", "/").strip("/")
        normalized_prefix = context_prefix.replace("\\", "/").strip("/")
        if normalized_prefix in ("", "."):
            return True
        return normalized_rel == normalized_prefix or normalized_rel.startswith(f"{normalized_prefix}/")

    @staticmethod
    def _format_file_list(file_paths: list[str], max_items: int = 10) -> str:
        deduped = sorted({path for path in file_paths if isinstance(path, str) and path.strip()})
        if len(deduped) <= max_items:
            return ", ".join(deduped)
        remaining = len(deduped) - max_items
        return f"{', '.join(deduped[:max_items])}, +{remaining} more"

    async def review(
        self,
        agent: ChatAgent,
        isolation_manager: IsolationContextManager,
        selected_agent_id: str,
    ) -> AsyncGenerator[StreamChunk]:
        """Review and apply changes from isolated write context."""
        from massgen.filesystem_manager import ChangeApplier, ReviewResult

        orch = self._orchestrator

        logger.info(f"[Orchestrator] Starting _review_isolated_changes for {selected_agent_id}")

        # 1. Collect all changes from isolated contexts
        all_changes = []
        for ctx_info in isolation_manager.list_contexts():
            if not ctx_info:
                continue
            original_path = ctx_info.get("original_path")
            if not original_path:
                continue

            changes = isolation_manager.get_changes(
                original_path,
                include_committed_since_base=True,
            )
            diff = isolation_manager.get_diff(
                original_path,
                include_committed_since_base=True,
            )

            if changes or diff:
                repo_root = os.path.abspath(ctx_info.get("repo_root") or original_path)
                original_abs = os.path.abspath(original_path)
                context_prefix = "."
                try:
                    if os.path.commonpath([original_abs, repo_root]) == repo_root:
                        context_prefix = os.path.relpath(original_abs, repo_root)
                    else:
                        context_prefix = "__massgen_out_of_scope__"
                        logger.warning(
                            "[Orchestrator] Context path is outside repo_root; " "writes will be blocked for this context: " f"context={original_abs}, repo_root={repo_root}",
                        )
                except ValueError:
                    context_prefix = "__massgen_out_of_scope__"
                    logger.warning(
                        "[Orchestrator] Could not compare context path and repo_root; " "writes will be blocked for this context: " f"context={original_abs}, repo_root={repo_root}",
                    )

                filtered_changes = [change for change in changes if isinstance(change, dict) and isinstance(change.get("path"), str) and self._is_in_context_prefix(change["path"], context_prefix)]

                has_relevant_changes = bool(filtered_changes) or (not changes and bool(diff))
                if not has_relevant_changes:
                    continue

                all_changes.append(
                    {
                        "original_path": original_abs,
                        "isolated_path": ctx_info.get("isolated_path"),
                        "repo_root": repo_root,
                        "base_ref": ctx_info.get("base_ref"),
                        "context_prefix": context_prefix,
                        "changes": filtered_changes,
                        "diff": diff,
                    },
                )

        # 2. If no changes, skip review and cleanup
        if not all_changes:
            logger.info("[Orchestrator] No isolated changes to review")
            for ctx_info in isolation_manager.list_contexts():
                ctx_path = ctx_info.get("original_path") if ctx_info else None
                if ctx_path:
                    isolation_manager.move_scratch_to_workspace(ctx_path)
            isolation_manager.cleanup_session()
            await orch._show_workspace_modal_if_needed()
            return

        # 3. Yield status chunk
        total_changes = sum(len(c.get("changes", [])) or self._count_diff_files(c.get("diff", "")) for c in all_changes)
        yield StreamChunk(
            type="status",
            content=f"Reviewing {total_changes} file change(s) from isolated context...",
            source=selected_agent_id,
        )

        # 4. Show review modal or auto-approve
        review_result = ReviewResult(approved=True, approved_files=None)

        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)

        logger.info(
            f"[Orchestrator] Review phase: display={display}, " f"has_final_answer_modal={hasattr(display, 'show_final_answer_modal') if display else False}",
        )

        if display and hasattr(display, "show_final_answer_modal"):
            try:
                logger.info("[Orchestrator] Showing final answer modal...")
                context_paths_summary: dict[str, list[str]] | None = None
                new_files: list[str] = []
                modified_files: list[str] = []
                for ctx in all_changes:
                    for change in ctx.get("changes", []):
                        path = change.get("path", "")
                        status = change.get("status", "")
                        if status == "A":
                            new_files.append(path)
                        elif status in ("M", "D", "R"):
                            modified_files.append(path)
                if new_files or modified_files:
                    context_paths_summary = {"new": new_files, "modified": modified_files}

                model_name = ""
                if agent and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                    model_name = agent.backend.config.get("model", "")

                workspace_path = orch._resolve_final_workspace_path(selected_agent_id)
                if not workspace_path and agent and hasattr(agent, "backend"):
                    fm = getattr(agent.backend, "filesystem_manager", None)
                    if fm is not None:
                        try:
                            workspace_path = str(fm.get_current_workspace())
                        except Exception:
                            pass

                review_result = await display.show_final_answer_modal(
                    changes=all_changes,
                    answer_content=orch._final_presentation_content or "",
                    vote_results=orch._get_vote_results(),
                    agent_id=selected_agent_id,
                    model_name=model_name,
                    context_paths=context_paths_summary,
                    workspace_path=workspace_path,
                )
                logger.info(f"[Orchestrator] Final answer modal returned: approved={review_result.approved}")
            except Exception as e:
                logger.warning(f"[Orchestrator] Final answer modal failed: {e}, rejecting for safety")
                review_result = ReviewResult(approved=False, metadata={"error": str(e)})
        elif display and hasattr(display, "show_change_review_modal"):
            try:
                logger.info("[Orchestrator] Showing review modal (fallback)...")
                review_result = await display.show_change_review_modal(all_changes)
                logger.info(f"[Orchestrator] Review modal returned: approved={review_result.approved}")
            except Exception as e:
                logger.warning(f"[Orchestrator] Review modal failed: {e}, rejecting for safety")
                review_result = ReviewResult(approved=False, metadata={"error": str(e)})
        else:
            logger.info("[Orchestrator] Non-TUI mode: auto-approving isolated changes")

        # 5. Handle rework/quick_fix
        if getattr(review_result, "action", None) in ("rework", "quick_fix"):
            # SHARED single-writer here; FinalPresentationRunner reads via orchestrator.
            orch._pending_review_rework = {
                "action": review_result.action,
                "feedback": getattr(review_result, "feedback", None),
                "agent_id": selected_agent_id,
            }
            yield StreamChunk(
                type="status",
                content="Rework requested — isolation preserved for re-presentation...",
                source=selected_agent_id,
            )
            return

        # 6. Apply approved changes
        if review_result.approved:
            applier = ChangeApplier()
            applied_files: list[str] = []
            drifted_files_all: list[str] = []
            approved_files_by_context = self._normalize_approved_files_by_context(review_result.metadata)
            approved_hunks_by_context = self._normalize_approved_hunks_by_context(review_result.metadata)
            drift_conflict_policy = (
                getattr(
                    getattr(orch.config, "coordination_config", None),
                    "drift_conflict_policy",
                    "skip",
                )
                or "skip"
            )
            if drift_conflict_policy not in {"skip", "prefer_presenter", "fail"}:
                logger.warning(
                    "[Orchestrator] Invalid drift_conflict_policy=%s; defaulting to 'skip'",
                    drift_conflict_policy,
                )
                drift_conflict_policy = "skip"

            logger.info(
                "[Orchestrator] Applying approved changes: " f"approved_files={review_result.approved_files}, " f"contexts={len(all_changes)}, " f"drift_conflict_policy={drift_conflict_policy}",
            )

            apply_plan: list[dict[str, Any]] = []
            for ctx in all_changes:
                try:
                    context_path = os.path.abspath(ctx["original_path"])
                    target = context_path
                    context_prefix = ctx.get("context_prefix")
                    approved_files_for_context: list[str] | None
                    approved_hunks_for_context: dict[str, list[int]] | None = approved_hunks_by_context.get(
                        context_path,
                    )

                    if review_result.approved_files is None:
                        approved_files_for_context = None
                    elif context_path in approved_files_by_context:
                        approved_files_for_context = approved_files_by_context[context_path]
                    else:
                        approved_files_for_context = []
                        for approved_entry in review_result.approved_files:
                            if not isinstance(approved_entry, str):
                                continue
                            if "::" in approved_entry:
                                approved_context, approved_path = approved_entry.split("::", 1)
                                if os.path.abspath(approved_context) == context_path and approved_path:
                                    approved_files_for_context.append(approved_path)
                            else:
                                approved_files_for_context.append(approved_entry)

                    logger.info(
                        "[Orchestrator] ChangeApplier: " f"source={ctx['isolated_path']}, " f"target={target}, " f"context_prefix={context_prefix}",
                    )
                    drifted_files = applier.detect_target_drift(
                        source_path=ctx["isolated_path"],
                        target_path=target,
                        base_ref=ctx.get("base_ref"),
                        approved_files=approved_files_for_context,
                        context_prefix=context_prefix,
                    )
                    if drifted_files:
                        drifted_files_all.extend(drifted_files)
                        logger.warning(
                            "[Orchestrator] Detected drifted files for context " f"{context_path}: {drifted_files}",
                        )

                    apply_plan.append(
                        {
                            "source_path": ctx["isolated_path"],
                            "target_path": target,
                            "approved_files_for_context": approved_files_for_context,
                            "approved_hunks_for_context": approved_hunks_for_context,
                            "context_prefix": context_prefix,
                            "base_ref": ctx.get("base_ref"),
                            "drifted_files": drifted_files,
                            "combined_diff": ctx.get("diff"),
                        },
                    )
                except Exception as e:
                    logger.error(f"[Orchestrator] Failed to apply changes to {ctx['original_path']}: {e}")
                    yield StreamChunk(
                        type="error",
                        error=f"Failed to apply some changes: {e}",
                        source=selected_agent_id,
                    )

            drifted_files_unique = sorted(set(drifted_files_all))
            drifted_files_total = len(drifted_files_unique)
            drifted_file_list = self._format_file_list(drifted_files_unique) if drifted_files_unique else ""

            if drifted_files_total and drift_conflict_policy == "fail":
                yield StreamChunk(
                    type="status",
                    content=(f"Detected {drifted_files_total} drifted file(s) (policy=fail): {drifted_file_list}"),
                    source=selected_agent_id,
                )
                yield StreamChunk(
                    type="error",
                    error=("Drift conflict policy is 'fail'; no changes were applied. " "Resolve drift or use coordination.drift_conflict_policy " "set to 'skip' or 'prefer_presenter'."),
                    source=selected_agent_id,
                )
            else:
                if drifted_files_total and drift_conflict_policy == "prefer_presenter":
                    yield StreamChunk(
                        type="status",
                        content=(f"Detected {drifted_files_total} drifted file(s) " f"(policy=prefer_presenter): {drifted_file_list}"),
                        source=selected_agent_id,
                    )

                for plan_entry in apply_plan:
                    blocked_files = plan_entry["drifted_files"] if drift_conflict_policy == "skip" else None
                    files = applier.apply_changes(
                        source_path=plan_entry["source_path"],
                        target_path=plan_entry["target_path"],
                        approved_files=plan_entry["approved_files_for_context"],
                        approved_hunks=plan_entry["approved_hunks_for_context"],
                        context_prefix=plan_entry["context_prefix"],
                        base_ref=plan_entry["base_ref"],
                        blocked_files=blocked_files,
                        combined_diff=plan_entry["combined_diff"],
                    )
                    if files:
                        orch._sync_applied_context_files_into_final_artifacts(
                            agent_id=selected_agent_id,
                            target_path=plan_entry["target_path"],
                            relative_paths=files,
                        )
                    applied_files.extend(files)

            if applied_files:
                yield StreamChunk(
                    type="status",
                    content=f"Applied {len(applied_files)} file change(s): {self._format_file_list(applied_files)}",
                    source=selected_agent_id,
                )

                if drifted_files_total and drift_conflict_policy == "skip":
                    yield StreamChunk(
                        type="status",
                        content=(f"Skipped {drifted_files_total} drifted file(s) " f"(policy=skip): {drifted_file_list}"),
                        source=selected_agent_id,
                    )

                if review_result.approved_files is not None:
                    total_available = sum(len(ctx.get("changes", [])) for ctx in all_changes)
                    rejected_count = total_available - len(review_result.approved_files)
                    if rejected_count > 0:
                        yield StreamChunk(
                            type="status",
                            content=f"User excluded {rejected_count} file(s) from apply",
                            source=selected_agent_id,
                        )

                logger.info(f"[Orchestrator] Applied isolated changes: {applied_files}")
            else:
                logger.warning("[Orchestrator] Review approved but no files were applied (empty change set)")
                yield StreamChunk(
                    type="status",
                    content="Review approved but no changed files were found to apply",
                    source=selected_agent_id,
                )
                if drifted_files_total and drift_conflict_policy == "skip":
                    yield StreamChunk(
                        type="status",
                        content=(f"Skipped {drifted_files_total} drifted file(s) " f"(policy=skip): {drifted_file_list}"),
                        source=selected_agent_id,
                    )
        else:
            yield StreamChunk(
                type="status",
                content="Changes rejected - no files were modified",
                source=selected_agent_id,
            )
            logger.info("[Orchestrator] User rejected isolated changes")

        # 6. Move scratch to archive and cleanup
        for ctx_info in isolation_manager.list_contexts():
            ctx_path = ctx_info.get("original_path") if ctx_info else None
            if ctx_path:
                isolation_manager.move_scratch_to_workspace(ctx_path)
        isolation_manager.cleanup_session()
