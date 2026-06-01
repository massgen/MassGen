"""
Textual Terminal Display for MassGen Coordination

"""

import ast
import functools
import json
import os
import re
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Optional

if TYPE_CHECKING:
    from massgen.filesystem_manager import ReviewResult
    from massgen.frontend.displays.textual_widgets.plan_approval_modal import (
        PlanApprovalResult,
    )

from massgen.logger_config import get_event_emitter, get_log_session_dir, logger
from massgen.subagent.models import SubagentDisplayData
from massgen.user_settings import get_user_settings

from .terminal_display import TerminalDisplay

try:
    from rich.text import Text
    from textual import events, on
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, VerticalScroll
    from textual.message import Message
    from textual.reactive import reactive
    from textual.screen import ModalScreen
    from textual.theme import Theme
    from textual.widget import Widget
    from textual.widgets import Button, Footer, Input, Label, RichLog, Static, TextArea

    from .base_tui_layout import BaseTUILayoutMixin
    from .content_handlers import ToolBatchTracker

    # Import extracted modals from the new textual/ package
    from .textual import (  # Browser modals; Status modals; Coordination modals; Content modals; Input modals; Shortcuts modal; Workspace modals; Agent output modal
        AgentOutputModal,
        AgentSelectorModal,
        AnswerBrowserModal,
        BroadcastPromptModal,
        BrowserTabsModal,
        ChunkAdvanceModal,
        ContextModal,
        ConversationHistoryModal,
        CoordinationTableModal,
        CostBreakdownModal,
        DecompositionGenerationModal,
        DecompositionSubtasksModal,
        EvaluationCriteriaModal,
        FileInspectionModal,
        KeyboardShortcutsModal,
        MCPStatusModal,
        MetricsModal,
        OrchestratorEventsModal,
        SkillsModal,
        StructuredBroadcastPromptModal,
        SystemStatusModal,
        TextContentModal,
        TimelineModal,
        VoteResultsModal,
        WorkspaceBrowserModal,
    )
    from .textual_widgets import (
        AgentStatusRibbon,
        AgentTabBar,
        AgentTabChanged,
        AnalysisProfileChanged,
        AnalysisSkillLifecycleChanged,
        AnalysisTargetChanged,
        AnalysisTargetTypeChanged,
        AnswerNowClicked,
        BackgroundTasksClicked,
        BackgroundTasksModal,
        BroadcastModeChanged,
        CompletionFooter,
        ConsensusMap,
        ConsensusMapState,
        ContextPathsClicked,
        CopyModeBanner,
        ExecuteAutoContinueChanged,
        ExecutePrefillRequested,
        ExecuteRefinementModeChanged,
        ExecutionStatusLine,
        FinalPresentationCard,
        ModeBar,
        ModeChanged,
        ModeHelpClicked,
        MultiLineInput,
        OverrideRequested,
        PathSuggestionDropdown,
        PlanChunkTargetChanged,
        PlanDepthChanged,
        PlanOptionsPopover,
        PlanSelected,
        PlanSettingsClicked,
        PlanStepTargetChanged,
        QueuedInputBanner,
        SessionInfoClicked,
        SkillsClicked,
        SubagentCard,
        SubagentScreen,
        SubtasksClicked,
        TaskPlanCard,
        TaskPlanModal,
        TasksClicked,
        TimelineSection,
        ToolBatchCard,
        ToolCallCard,
        ToolDetailModal,
        ToolSection,
        ViewAnalysisRequested,
        ViewPlanRequested,
        ViewSelected,
    )
    from .textual_widgets.copy_mode_banner import (
        COPY_MODE_BINDING,
        set_terminal_mouse_capture,
    )
    from .tui_event_pipeline import TimelineEventAdapter
    from .tui_modes import TuiModeState

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

# TUI Debug logger - use shared implementation
from .shared.tui_debug import tui_debug_enabled, tui_log  # noqa: E402


def _process_line_buffer(
    buffer: str,
    content: str,
    log_writer: Callable[[str], None],
) -> str:
    """Process content with line buffering, return updated buffer.

    Args:
        buffer: Current line buffer content.
        content: New content to append.
        log_writer: Callable to write complete lines.

    Returns:
        Updated buffer containing incomplete line.
    """
    buffer += content
    if "\n" in buffer:
        lines = buffer.split("\n")
        for line in lines[:-1]:
            if line.strip():
                log_writer(line)
        return lines[-1]
    return buffer


# File preview utilities imported from shared module


from . import _textual_provider_model as _provider_model  # noqa: E402
from . import _textual_widget_debug as _widget_debug  # noqa: E402

# Emoji fallback mapping for terminals without Unicode support.
# Extracted to _textual_terminal_capabilities; re-exported here for back-compat.
from ._textual_terminal_capabilities import (  # noqa: E402, F401
    EMOJI_FALLBACKS,
    TerminalCapabilityProbe,
)

CRITICAL_PATTERNS = {
    "vote": "✅ Vote recorded",
    "status": ["📊 Status changed", "Status: "],
    "tool": "🔧",
    "presentation": "🎤 Final Presentation",
}

CRITICAL_CONTENT_TYPES = {"status", "presentation", "tool", "vote", "error"}


def _parse_spawn_subagents_result(result_text: Any) -> dict[str, Any] | None:
    """Parse spawn_subagents result payloads across JSON and repr encodings.

    Spawn tool results frequently arrive as:
    - raw JSON dict
    - Python repr dict
    - list-wrapped Claude/Codex content blocks containing JSON/repr text
    - wrappers with a top-level ``structured_content`` dict
    """
    if not isinstance(result_text, str) or not result_text.strip():
        return None

    try:
        from .content_processor import ContentProcessor

        parsed = ContentProcessor._parse_result_dict(result_text)
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return None

    structured = parsed.get("structured_content")
    if isinstance(structured, dict):
        parsed = structured

    return parsed


def _parse_spawn_subagents_args(args_payload: Any) -> dict[str, Any] | None:
    """Parse spawn_subagents args payloads across JSON/repr encodings."""
    if isinstance(args_payload, dict):
        return args_payload
    if not isinstance(args_payload, str):
        return None

    raw = args_payload.strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    return None


def _is_start_background_tool_name(tool_name: Any) -> bool:
    """Return True when tool_name is the background start lifecycle tool."""
    return str(tool_name or "").lower().endswith("start_background_tool")


def _extract_spawn_subagents_args_for_tool(
    tool_name: Any,
    args_payload: Any,
) -> dict[str, Any] | None:
    """Extract subagent-tool arguments from direct or wrapper tool payloads."""
    parsed = _parse_spawn_subagents_args(args_payload)
    if not isinstance(parsed, dict):
        return None

    if isinstance(parsed.get("tasks"), list):
        return parsed

    if not _is_start_background_tool_name(tool_name):
        return parsed

    target_tool = str(parsed.get("tool_name") or parsed.get("tool") or "").strip().lower()
    if "spawn_subagent" not in target_tool and "continue_subagent" not in target_tool:
        return parsed

    nested_raw = parsed.get("arguments", parsed.get("args"))
    nested = _parse_spawn_subagents_args(nested_raw)
    if isinstance(nested, dict):
        return nested

    merged = {key: value for key, value in parsed.items() if key not in {"tool_name", "tool", "arguments", "args"}}
    if isinstance(merged.get("tasks"), list) or merged.get("subagent_id"):
        return merged
    return parsed


def _extract_spawned_subagents(result_text: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return normalized subagent payload plus extracted subagent entries."""
    result_data = _parse_spawn_subagents_result(result_text)
    if not isinstance(result_data, dict):
        return None, []

    spawned_raw = result_data.get(
        "results",
        result_data.get("spawned_subagents", result_data.get("subagents", [])),
    )
    if isinstance(spawned_raw, list):
        spawned = [entry for entry in spawned_raw if isinstance(entry, dict)]
        if spawned:
            return result_data, spawned

    # continue_subagent returns a single subagent payload rather than a list.
    single_subagent_id = result_data.get("subagent_id") or result_data.get("id")
    if single_subagent_id and result_data.get("status"):
        return result_data, [result_data]

    return result_data, []


# Pre-collab subagent IDs that get dedicated full-screen treatment
# instead of appearing as inline cards in the agent timeline.
_PRECOLLAB_SUBAGENT_IDS = frozenset(
    {
        "persona_generation",
        "task_decomposition",
        "criteria_generation",
        "prompt_improvement",
    },
)


_PRECOLLAB_DISPLAY_NAMES: dict[str, str] = {
    "persona_generation": "Personas",
    "criteria_generation": "Eval Criteria",
    "prompt_improvement": "Prompt",
    "task_decomposition": "Decomposition",
}

# Parallel pre-collab IDs — all except task_decomposition which runs separately.
_PARALLEL_PRECOLLAB_IDS = _PRECOLLAB_SUBAGENT_IDS - {"task_decomposition"}


class _PrecollabSubagentState:
    """Mutable state for a single pre-collab subagent's TUI tracking."""

    __slots__ = ("call_id", "agent_id", "data", "status_callback", "auto_opened")

    def __init__(self) -> None:
        self.call_id: str | None = None
        self.agent_id: str | None = None
        self.data: Any | None = None  # SubagentDisplayData
        self.status_callback: Callable | None = None
        self.auto_opened: bool = False


def _subagent_card_dom_id(call_id: Any) -> str:
    """Build a safe, deterministic DOM id for subagent cards."""
    safe_call_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(call_id or "subagent"))
    return f"subagent_{safe_call_id}"


def _map_subagent_status(raw_status: Any, completion_percentage: int | None = None) -> tuple[str, int]:
    """Map raw subagent status values to display status/progress."""
    status = str(raw_status or "").lower().strip()
    if status == "completed":
        return "completed", 100
    if status in {"completed_but_timeout", "partial", "timeout"}:
        progress = completion_percentage if completion_percentage is not None else 100
        return "timeout", max(0, min(int(progress), 100))
    if status in {"failed", "error"}:
        return "failed", 0
    if status in {"cancelled", "canceled", "stopped"}:
        return "canceled", 0
    if status in {"pending"}:
        return "pending", 0
    return "running", 0


def _count_workspace_files(workspace_path: str) -> int:
    if not workspace_path:
        return 0
    workspace = Path(workspace_path)
    if not workspace.exists():
        return 0
    try:
        return sum(1 for path in workspace.rglob("*") if path.is_file())
    except Exception:
        return 0


def _read_subagent_reference_error(log_path: Any) -> str | None:
    """Read terminal error details from subagent subprocess reference logs."""
    if not log_path:
        return None

    try:
        base = Path(str(log_path))
    except Exception:
        return None

    if base.is_file():
        base = base.parent

    ref_file = base / "subprocess_logs.json"
    if not ref_file.exists() or not ref_file.is_file():
        return None

    try:
        payload = json.loads(ref_file.read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return None

    error = payload.get("error")
    if isinstance(error, str):
        error = error.strip()
        if error:
            return error
    return None


def _normalize_subagent_context_paths(raw_paths: Any) -> list[str]:
    """Normalize context path payloads to a stable list[str]."""
    if raw_paths is None:
        return []

    if isinstance(raw_paths, dict):
        raw_paths = raw_paths.get("paths", [])

    if not isinstance(raw_paths, list):
        raw_paths = [raw_paths]

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in raw_paths:
        path_value = ""
        if isinstance(entry, str):
            path_value = entry.strip()
        elif isinstance(entry, dict):
            candidate = entry.get("path")
            if candidate is not None:
                path_value = str(candidate).strip()
        elif entry is not None:
            path_value = str(entry).strip()

        if not path_value or path_value in seen:
            continue
        seen.add(path_value)
        normalized.append(path_value)

    return normalized


def _normalize_subagent_type(raw_type: Any) -> str | None:
    """Normalize specialized subagent type labels for display."""
    if raw_type is None:
        return None
    value = str(raw_type).strip()
    if not value:
        return None
    return value.lower()


def _build_context_paths_labeled(
    context_paths: list[str],
    workspace_path: str,
    sa_data: dict[str, Any],
    existing: SubagentDisplayData | None,
) -> list[dict[str, str]]:
    """Build labeled context paths for the SubagentContextModal."""
    if existing and existing.context_paths_labeled and not context_paths:
        return existing.context_paths_labeled
    if not context_paths:
        return []

    labeled: list[dict[str, str]] = []
    for p in context_paths:
        # Determine label based on path characteristics
        if workspace_path and p == workspace_path:
            label = "Parent CWD"
        elif "temp_workspace" in p or "temp_ws" in p:
            label = "Temp Workspace"
        else:
            label = Path(p).name or p
        labeled.append({"path": p, "label": label, "permission": "read"})
    return labeled


def _build_subagent_display_data(
    sa_data: dict[str, Any],
    existing: SubagentDisplayData | None = None,
) -> SubagentDisplayData:
    """Build SubagentDisplayData from spawn result/status records."""
    subagent_id = str(
        sa_data.get("subagent_id") or sa_data.get("id") or (existing.id if existing else "unknown"),
    )
    completion_percentage = sa_data.get("completion_percentage")
    if completion_percentage is not None:
        try:
            completion_percentage = int(completion_percentage)
        except Exception:
            completion_percentage = None
    display_status, progress = _map_subagent_status(sa_data.get("status"), completion_percentage)

    task = str(sa_data.get("task") or (existing.task if existing else ""))
    workspace_path = str(sa_data.get("workspace") or (existing.workspace_path if existing else ""))
    timeout_seconds = float(sa_data.get("timeout_seconds") or (existing.timeout_seconds if existing else 300))
    elapsed_seconds = float(sa_data.get("execution_time_seconds") or (existing.elapsed_seconds if existing else 0.0))
    log_path = sa_data.get("log_path") or (existing.log_path if existing else None)

    # Recalculate log_path when the server assigned a different ID than the
    # placeholder used at card creation (e.g. "subagent_0" → "subagent_1").
    # The stale log_path still points to the old ID's directory.
    if log_path and existing and subagent_id != existing.id and not sa_data.get("log_path"):
        try:
            from massgen.logger_config import get_log_session_dir

            session_dir = get_log_session_dir()
            if session_dir:
                log_path = str(session_dir / "subagents" / subagent_id)
        except Exception:
            pass

    error = sa_data.get("error")
    if not error and existing:
        error = existing.error
    if not error:
        raw_status = str(sa_data.get("status") or "").lower().strip()
        terminal_raw_statuses = {
            "failed",
            "error",
            "timeout",
            "completed_but_timeout",
            "partial",
            "cancelled",
            "canceled",
            "stopped",
        }
        if display_status in {"failed", "timeout", "canceled"} or raw_status in terminal_raw_statuses:
            error = _read_subagent_reference_error(log_path)

    answer = sa_data.get("answer")
    answer_preview = ((answer or "")[:200] if answer else None) or (existing.answer_preview if existing else None)
    raw_context_paths = sa_data.get("context_paths")
    if raw_context_paths is None and existing is not None:
        raw_context_paths = getattr(existing, "context_paths", [])
    context_paths = _normalize_subagent_context_paths(raw_context_paths)
    raw_subagent_type = sa_data.get("subagent_type")
    if raw_subagent_type is None and existing is not None:
        raw_subagent_type = getattr(existing, "subagent_type", None)
    subagent_type = _normalize_subagent_type(raw_subagent_type)

    workspace_file_count = _count_workspace_files(workspace_path)
    if workspace_file_count == 0 and existing and existing.workspace_file_count > 0:
        workspace_file_count = existing.workspace_file_count

    # Build labeled context paths for the SubagentContextModal
    context_paths_labeled = _build_context_paths_labeled(
        context_paths,
        workspace_path,
        sa_data,
        existing,
    )

    return SubagentDisplayData(
        id=subagent_id,
        task=task,
        status=display_status,
        progress_percent=progress,
        elapsed_seconds=elapsed_seconds,
        timeout_seconds=timeout_seconds,
        workspace_path=workspace_path,
        workspace_file_count=workspace_file_count,
        last_log_line=str(error or ""),
        error=error,
        answer_preview=answer_preview,
        log_path=str(log_path) if log_path else None,
        context_paths=context_paths,
        context_paths_labeled=context_paths_labeled,
        subagent_type=subagent_type,
    )


class ProgressIndicator(Static):
    """Animated spinner with optional progress bar for loading states.

    Provides visual feedback during async operations with configurable
    spinner styles and optional progress percentage display.
    """

    SPINNERS = {
        "unicode": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "ascii": ["|", "/", "-", "\\"],
        "dots": [".", "..", "...", ""],
    }

    progress = reactive(0.0)
    message = reactive("Loading...")
    is_spinning = reactive(False)

    def __init__(
        self,
        message: str = "Loading...",
        spinner_type: str = "unicode",
        show_progress: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._message = message
        self._spinner_type = spinner_type
        self._show_progress = show_progress
        self._spinner_index = 0
        self._spinner_timer = None
        self._frames = self.SPINNERS.get(spinner_type, self.SPINNERS["unicode"])

    def render(self) -> str:
        """Render the spinner with message."""
        if not self.is_spinning:
            return ""

        spinner_char = self._frames[self._spinner_index % len(self._frames)]

        if self._show_progress and self.progress > 0:
            return f"{spinner_char} {self.message} ({int(self.progress * 100)}%)"
        return f"{spinner_char} {self.message}"

    def start_spinner(self, message: str = None) -> None:
        """Start the spinner animation."""
        if message:
            self.message = message
        self.is_spinning = True
        self._spinner_index = 0
        self._start_animation()

    def stop_spinner(self) -> None:
        """Stop the spinner animation."""
        self.is_spinning = False
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.refresh()

    def set_progress(self, value: float, message: str = None) -> None:
        """Update progress value (0.0 to 1.0) and optional message."""
        self.progress = max(0.0, min(1.0, value))
        if message:
            self.message = message
        self.refresh()

    def _start_animation(self) -> None:
        """Start the spinner animation timer."""
        if self._spinner_timer:
            self._spinner_timer.stop()

        def advance_spinner():
            if self.is_spinning:
                self._spinner_index = (self._spinner_index + 1) % len(self._frames)
                self.refresh()

        self._spinner_timer = self.set_interval(0.1, advance_spinner)

    def on_unmount(self) -> None:
        """Clean up timer when widget is removed."""
        self.stop_spinner()


class TextualTerminalDisplay(TerminalDisplay):
    """Textual-based terminal display with feature parity to Rich."""

    def __init__(self, agent_ids: list[str], **kwargs: Any):
        super().__init__(agent_ids, **kwargs)
        self._validate_agent_ids()
        self._dom_id_mapping: dict[str, str] = {}

        # Agent models mapping (agent_id -> model name) for display
        self.agent_models: dict[str, str] = kwargs.get("agent_models", {})

        # Load theme from user settings if not explicitly provided
        self.theme = kwargs.get("theme") or get_user_settings().theme
        self.refresh_rate = kwargs.get("refresh_rate")
        self.enable_syntax_highlighting = kwargs.get("enable_syntax_highlighting", True)
        self.show_timestamps = kwargs.get("show_timestamps", True)
        self.max_line_length = kwargs.get("max_line_length", 100)
        self.max_web_search_lines = kwargs.get("max_web_search_lines", 4)
        self.truncate_web_on_status_change = kwargs.get("truncate_web_on_status_change", True)
        self.max_web_lines_on_status_change = kwargs.get("max_web_lines_on_status_change", 3)
        self.default_coordination_mode = kwargs.get("default_coordination_mode", "parallel")
        self.default_load_previous_session_skills = bool(
            kwargs.get("default_load_previous_session_skills", False),
        )
        self.default_skill_lifecycle_mode = str(
            kwargs.get("default_skill_lifecycle_mode", "create_or_update"),
        )
        default_cwd_context_mode = str(kwargs.get("default_cwd_context_mode", "off")).strip().lower()
        if default_cwd_context_mode in {"rw", "write"}:
            self.default_cwd_context_mode = "write"
        elif default_cwd_context_mode in {"ro", "read"}:
            self.default_cwd_context_mode = "read"
        else:
            self.default_cwd_context_mode = "off"
        # CLI mode defaults (set by --single-agent, --quick, --personas, --coordination-mode)
        self.default_agent_mode = kwargs.get("default_agent_mode", "multi")
        self.default_selected_agent = kwargs.get("default_selected_agent", None)
        default_plan_mode = str(kwargs.get("default_plan_mode", "normal")).strip().lower()
        if default_plan_mode not in {"normal", "plan", "spec", "execute", "analysis"}:
            default_plan_mode = "normal"
        self.default_plan_mode = default_plan_mode
        self.default_refinement_enabled = kwargs.get("default_refinement_enabled", True)
        self.default_personas_enabled = kwargs.get("default_personas_enabled", False)
        self.default_persona_diversity_mode = kwargs.get("default_persona_diversity_mode", "perspective")

        # Runtime toggle to ignore hotkeys/key handling when enabled
        self.safe_keyboard_mode = kwargs.get("safe_keyboard_mode", False)
        self.max_buffer_batch = kwargs.get("max_buffer_batch", 50)
        self.max_buffer_size = kwargs.get("max_buffer_size", 200)  # Max items per agent buffer
        self._keyboard_interactive_mode = kwargs.get("keyboard_interactive_mode", True)

        # File output
        default_output_dir = kwargs.get("output_dir")
        if default_output_dir is None:
            try:
                default_output_dir = get_log_session_dir() / "agent_outputs"
            except Exception:
                default_output_dir = Path("output") / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(default_output_dir)
        self.agent_files = {}
        self.system_status_file = None
        self.final_presentation_file = None
        self.final_presentation_latest = None

        # Textual app
        self._app = None

        # Display state
        self.question = ""
        self.log_filename = None
        self.restart_reason = None
        self.restart_instructions = None
        self._final_answer_cache: str | None = None
        self._final_answer_metadata: dict[str, Any] = {}
        self._post_evaluation_lines: Deque[str] = deque(maxlen=20)
        self._final_stream_active = False
        self._final_stream_buffer: str = ""
        self._final_presentation_agent: str | None = None
        self._final_presentation_card = None
        self._routing_to_post_eval_card = False  # Bug 2 fix: prevent timeline routing during post-eval
        self._in_final_presentation = False  # Prevent duplicate timeline content during final presentation
        self._pending_final_review_status: str | None = None

        self._app_ready = threading.Event()
        self._input_handler: Callable[[str], None] | None = None
        self.orchestrator = None
        self._user_quit_requested = False
        self.session_id = None
        self.current_turn = 1

        probe = TerminalCapabilityProbe.detect(
            env=os.environ,
            on_error=lambda e: tui_log(f"[TextualDisplay] {e}"),
        )
        self.emoji_support = probe.emoji_support
        self._terminal_type = probe.terminal_type

        if self.refresh_rate is None:
            self.refresh_rate = probe.refresh_rate
        else:
            self.refresh_rate = int(self.refresh_rate)

        if self.enable_syntax_highlighting is None:
            self.enable_syntax_highlighting = True

        default_buffer_flush = kwargs.get("buffer_flush_interval")
        if default_buffer_flush is None:
            # Faster flush for smoother streaming - 20 FPS (0.05s) provides
            # good balance between smooth appearance and performance
            if self._terminal_type in ("vscode", "windows_terminal"):
                default_buffer_flush = 0.1  # Faster than before (was 0.3s)
            else:
                # 0.05s (20 FPS) for smooth streaming, capped at refresh rate
                adaptive_flush = max(0.05, 1 / max(self.refresh_rate, 1))
                default_buffer_flush = min(adaptive_flush, 0.05)
        self.buffer_flush_interval = default_buffer_flush
        self._buffers = {agent_id: [] for agent_id in self.agent_ids}
        self._buffer_lock = threading.Lock()
        self._recent_web_chunks: dict[str, Deque[str]] = {agent_id: deque(maxlen=self.max_web_search_lines) for agent_id in self.agent_ids}

        self._event_listener_registered = False

        # Viewer mode: read-only TUI driven by EventFeeder from disk
        self.viewer_mode = kwargs.get("viewer_mode", False)
        self._viewer_event_feeder = None  # Set externally before run

    def _validate_agent_ids(self):
        """Validate agent IDs for security and robustness."""
        if not self.agent_ids:
            raise ValueError("At least one agent ID is required")

        MAX_AGENT_ID_LENGTH = 100

        for agent_id in self.agent_ids:
            if len(agent_id) > MAX_AGENT_ID_LENGTH:
                truncated_preview = agent_id[:50] + "..."
                raise ValueError(f"Agent ID exceeds maximum length of {MAX_AGENT_ID_LENGTH} characters: {truncated_preview}")

            if not agent_id or not agent_id.strip():
                raise ValueError("Agent ID cannot be empty or whitespace-only")

        if len(self.agent_ids) != len(set(self.agent_ids)):
            raise ValueError("Duplicate agent IDs detected")

    def reset_turn_state(self) -> None:
        """Reset turn-level state in the display for a new turn.

        Clears final answer state, content buffers, and other state
        that should not persist between turns.
        """
        # Final answer/presentation state - clear for new turn
        self._final_answer_cache = None
        self._final_answer_metadata.clear()
        self._final_stream_buffer = ""
        self._final_presentation_agent = None
        self._final_presentation_card = None
        self._final_stream_active = False
        self._routing_to_post_eval_card = False
        self._in_final_presentation = False
        self._pending_final_review_status = None

        # Post-evaluation content - clear for new turn
        self._post_evaluation_lines.clear()

        # Content buffers - clear for new turn
        with self._buffer_lock:
            for agent_id in self._buffers:
                self._buffers[agent_id].clear()

        # Web search chunks - reset for new turn
        for agent_id in self._recent_web_chunks:
            self._recent_web_chunks[agent_id].clear()

        # Reset app state if app exists
        if self._app:
            try:
                self._app.reset_turn_state()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

    def _detect_emoji_support(self) -> bool:
        """Detect if terminal supports emoji (delegates to TerminalCapabilityProbe)."""
        from ._textual_terminal_capabilities import detect_emoji_support

        return detect_emoji_support(os.environ, on_error=lambda e: tui_log(f"[TextualDisplay] {e}"))

    def _get_icon(self, emoji: str) -> str:
        """Get emoji or fallback based on terminal support."""
        from ._textual_terminal_capabilities import get_icon

        return get_icon(emoji, emoji_support=self.emoji_support)

    def _is_critical_content(self, content: str, content_type: str) -> bool:
        """Identify content that should flush immediately."""
        if content_type in CRITICAL_CONTENT_TYPES:
            return True

        lowered = content.lower()
        if "vote recorded" in lowered:
            return True

        for value in CRITICAL_PATTERNS.values():
            if isinstance(value, list):
                if any(pattern in content for pattern in value):
                    return True
            else:
                if value in content:
                    return True
        return False

    def _detect_terminal_type(self) -> str:
        """Detect terminal type (delegates to TerminalCapabilityProbe)."""
        from ._textual_terminal_capabilities import detect_terminal_type

        return detect_terminal_type(os.environ)

    def _get_adaptive_refresh_rate(self, terminal_type: str) -> int:
        """Get optimal refresh rate based on terminal (delegates to probe)."""
        from ._textual_terminal_capabilities import get_adaptive_refresh_rate

        return get_adaptive_refresh_rate(terminal_type)

    def _write_to_agent_file(self, agent_id: str, content: str):
        """Write content to agent's output file."""
        if agent_id not in self.agent_files:
            return

        file_path = self.agent_files[agent_id]
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                suffix = "" if content.endswith("\n") else "\n"
                f.write(content + suffix)
                f.flush()
        except OSError as exc:
            logger.warning(f"Failed to append to agent log {file_path} for {agent_id}: {exc}")

    def _write_to_system_file(self, content: str):
        """Write content to system status file."""
        if not self.system_status_file:
            return

        try:
            with open(self.system_status_file, "a", encoding="utf-8") as f:
                if self.show_timestamps:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    f.write(f"[{timestamp}] {content}\n")
                else:
                    f.write(f"{content}\n")
                f.flush()
        except OSError as exc:
            logger.warning(f"Failed to append to system status log {self.system_status_file}: {exc}")

    def _call_app_method(self, method_name: str, *args: Any, **kwargs: Any):
        """Invoke a Textual app method safely regardless of calling thread."""
        if not self._app:
            return

        callback = getattr(self._app, method_name, None)
        if not callback:
            return

        app_thread_id = getattr(self._app, "_thread_id", None)
        try:
            if app_thread_id is not None and app_thread_id == threading.get_ident():
                callback(*args, **kwargs)
            else:
                self._app.call_from_thread(callback, *args, **kwargs)
        except RuntimeError:
            # App is no longer running (e.g., early cancellation)
            pass

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit web-style display events into Textual app handlers.

        CoordinationUI uses this hook for preparation status events. Textual
        consumes those to keep progress UI in sync with orchestrator setup.
        """
        if event_type == "preparation_status":
            status = data.get("status", "") if isinstance(data, dict) else ""
            detail = data.get("detail", "") if isinstance(data, dict) else ""
            self._call_app_method("handle_preparation_status", status, detail)

    def set_input_handler(self, handler: Callable[[str], None]) -> None:
        """Set the callback for user-submitted input (questions or commands)"""
        self._input_handler = handler
        if self._app:
            try:
                self._app.set_input_handler(handler)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

    def set_human_input_hook(self, hook) -> None:
        """Set the human input hook for injecting user input during execution.

        Args:
            hook: HumanInputHook instance from orchestrator
        """
        logger.info(f"[Display] set_human_input_hook called, _app={self._app is not None}, hook={hook}")
        if self._app and hasattr(self._app, "set_human_input_hook"):
            try:
                self._app.set_human_input_hook(hook)
                logger.info("[Display] Successfully forwarded hook to app")
            except Exception as e:
                logger.warning(f"Failed to set human input hook on app: {e}")
        else:
            logger.warning(f"[Display] Cannot forward hook: _app={self._app}, has method={hasattr(self._app, 'set_human_input_hook') if self._app else 'N/A'}")

    def set_subagent_message_callback(self, callback) -> None:
        """Set the callback for sending messages to running subagents."""
        if self._app and hasattr(self._app, "set_subagent_message_callback"):
            self._app.set_subagent_message_callback(callback)

    def set_subagent_continue_callback(self, callback) -> None:
        """Set the callback for continuing terminal subagents from TUI."""
        if self._app and hasattr(self._app, "set_subagent_continue_callback"):
            self._app.set_subagent_continue_callback(callback)

    def set_answer_now_callback(self, callback) -> None:
        """Set the callback for the status-bar Answer Now control."""
        if self._app and hasattr(self._app, "set_answer_now_callback"):
            self._app.set_answer_now_callback(callback)

    def initialize(self, question: str, log_filename: str | None = None):
        """Initialize display with file output."""
        self.question = question
        self.log_filename = log_filename

        if self._app is not None:
            return
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        for agent_id in self.agent_ids:
            file_path = self.output_dir / f"{agent_id}.txt"
            self.agent_files[agent_id] = file_path
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"=== {agent_id.upper()} OUTPUT LOG ===\n\n")

        self.system_status_file = self.output_dir / "system_status.txt"
        with open(self.system_status_file, "w", encoding="utf-8") as f:
            f.write("=== SYSTEM STATUS LOG ===\n")
            f.write(f"Question: {question}\n\n")

        self.final_presentation_file = None
        self.final_presentation_latest = None

        # Suppress console logging to prevent interference with Textual display
        from massgen.logger_config import suppress_console_logging

        suppress_console_logging()

        if TEXTUAL_AVAILABLE:
            self._app = TextualApp(
                self,
                question,
                buffers=self._buffers,
                buffer_lock=self._buffer_lock,
                buffer_flush_interval=self.buffer_flush_interval,
            )

    def update_agent_content(
        self,
        agent_id: str,
        content: str,
        content_type: str = "thinking",
        tool_call_id: str | None = None,
    ):
        """Update agent content with appropriate formatting.

        Args:
            agent_id: Agent identifier
            content: Content to display
            content_type: Type of content - "thinking", "tool", "status", "presentation"
            tool_call_id: Optional unique ID for tool calls (enables tracking across events)
        """
        # Bug 2 fix: Skip timeline updates if content is being routed to post-eval card
        # But allow tool content through - tools should be displayed during post-evaluation
        if hasattr(self, "_routing_to_post_eval_card") and self._routing_to_post_eval_card:
            if content_type != "tool":
                return

        # Skip timeline updates during final presentation - content goes to FinalPresentationCard
        # Allow tools through since they should still be displayed
        if hasattr(self, "_in_final_presentation") and self._in_final_presentation:
            if content_type not in ("tool", "thinking"):
                return

        if not content:
            return

        tui_log(f"[update_agent_content] agent={agent_id} type={content_type} len={len(content)} content={content[:80]}")

        # Auto-set status to streaming when content arrives and agent is idle/waiting
        # This ensures the status indicator updates immediately when streaming starts
        current_status = self.agent_status.get(agent_id, "idle")
        if current_status in ("idle", "waiting"):
            self.agent_status[agent_id] = "streaming"  # Update local dict first
            self._call_app_method("update_agent_status", agent_id, "streaming")

        display_type = "status" if content_type == "thinking" and self._is_critical_content(content, content_type) else content_type

        prepared = self._prepare_agent_content(agent_id, content, display_type)

        self.agent_outputs[agent_id].append(content)
        self._write_to_agent_file(agent_id, content)

        if not prepared:
            return

        is_critical = self._is_critical_content(content, display_type)

        with self._buffer_lock:
            self._buffers[agent_id].append(
                {
                    "content": prepared,
                    "type": display_type,
                    "timestamp": datetime.now(),
                    "force_jump": False,
                    "tool_call_id": tool_call_id,
                },
            )
            buffered_len = len(self._buffers[agent_id])
            # Trim buffer if it exceeds max size to prevent memory issues
            if buffered_len > self.max_buffer_size:
                # Keep critical items and the most recent half
                keep_count = self.max_buffer_size // 2
                critical = [e for e in self._buffers[agent_id][:-keep_count] if self._is_critical_content(e.get("content", ""), e.get("type", ""))]
                self._buffers[agent_id] = critical + self._buffers[agent_id][-keep_count:]
                buffered_len = len(self._buffers[agent_id])

        if self._app and (is_critical or buffered_len >= self.max_buffer_batch):
            self._app.request_flush()

    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent."""
        self.agent_status[agent_id] = status
        self._reset_web_cache(agent_id, truncate_history=self.truncate_web_on_status_change)

        if self._app:
            self._app.request_flush()
        with self._buffer_lock:
            existing = self._buffers.get(agent_id, [])
            preserved: list[dict[str, Any]] = []
            for entry in existing:
                entry_content = entry.get("content", "")
                entry_type = entry.get("type", "thinking")
                if self._is_critical_content(entry_content, entry_type):
                    preserved.append(entry)
            self._buffers[agent_id] = preserved
            self._buffers[agent_id].append(
                {
                    "content": f"📊 Status changed to {status}",
                    "type": "status",
                    "timestamp": datetime.now(),
                    "force_jump": True,
                },
            )

        if self._app:
            self._call_app_method("update_agent_status", agent_id, status)

        status_msg = f"\n[Status Changed: {status.upper()}]\n"
        self._write_to_agent_file(agent_id, status_msg)

    def update_timeout_status(self, agent_id: str, timeout_state: dict[str, Any]) -> None:
        """Update timeout display for an agent.

        Args:
            agent_id: The agent whose timeout status to update
            timeout_state: Timeout state from orchestrator.get_agent_timeout_state()
        """
        if self._app:
            self._call_app_method("update_agent_timeout", agent_id, timeout_state)

    def notify_subagent_spawn_started(
        self,
        agent_id: str,
        tool_name: str,
        args: dict[str, Any],
        call_id: str,
    ) -> None:
        """Notify the TUI that subagent spawning has started.

        This is called from a background thread when spawn_subagents is invoked,
        BEFORE the blocking execution begins. This allows showing the SubagentCard
        immediately rather than waiting for the tool to complete.

        Args:
            agent_id: ID of the agent spawning subagents
            tool_name: Name of the spawn tool (e.g., spawn_subagents)
            args: Tool arguments containing tasks list
            call_id: Tool call ID
        """
        if self._app:
            self._call_app_method("show_subagent_card_from_spawn", agent_id, args, call_id)

    def notify_runtime_subagent_started(
        self,
        agent_id: str,
        subagent_id: str,
        task: str,
        timeout_seconds: int = 300,
        call_id: str | None = None,
        status_callback: Callable[[str], Any | None] | None = None,
        log_path: str | None = None,
    ) -> None:
        """Show a subagent card for orchestrator-owned runtime subagents.

        Used for decomposition/persona generation style subagents that are
        spawned directly by orchestrator code (not via tool cards).
        """
        if not self._app:
            return
        self._call_app_method(
            "show_runtime_subagent_card",
            agent_id,
            subagent_id,
            task,
            timeout_seconds,
            call_id or subagent_id,
            status_callback,
            log_path,
        )

    def notify_runtime_subagent_completed(
        self,
        agent_id: str,
        subagent_id: str,
        call_id: str,
        status: str = "completed",
        answer_preview: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update a runtime subagent card when orchestration completes."""
        if not self._app:
            return
        self._call_app_method(
            "update_runtime_subagent_card",
            agent_id,
            subagent_id,
            call_id,
            status,
            answer_preview,
            error,
        )

    def notify_prompt_improved(self, improved_prompt: str) -> None:
        """Notify the TUI that the task prompt was improved/evolved."""
        if not self._app:
            return
        self._call_app_method("update_improved_prompt", improved_prompt)

    def update_hook_execution(
        self,
        agent_id: str,
        tool_call_id: str | None,
        hook_info: dict[str, Any],
    ) -> None:
        """Update display with hook execution information.

        Args:
            agent_id: The agent whose tool call has hooks
            tool_call_id: Optional ID of the tool call this hook is attached to
            hook_info: Hook execution info dict
        """
        if self._app:
            self._call_app_method("update_hook_execution", agent_id, tool_call_id, hook_info)

    def update_token_usage(self, agent_id: str, usage: dict[str, Any]) -> None:
        """Update token usage display for an agent.

        Phase 13.1: Wire token/cost updates from backend to status ribbon.

        Args:
            agent_id: The agent whose token usage to update
            usage: Token usage dict with input_tokens, output_tokens, estimated_cost
        """
        if self._app:
            self._call_app_method("update_token_usage", agent_id, usage)

    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event."""
        self.orchestrator_events.append(event)
        self._write_to_system_file(event)

        if self._app:
            self._app.request_flush()
            self._call_app_method("add_orchestrator_event", event)
            # Also increment status bar event counter
            self._call_app_method("add_status_bar_event")

    # === Status Bar Notification Bridge Methods ===

    def notify_vote(self, voter: str, voted_for: str, reason: str = "", submission_round: int = 1):
        """Notify the TUI of a vote cast - updates status bar, shows toast, and adds tool card.

        Args:
            submission_round: Round the vote was cast in (1-indexed display round)
        """
        if self._app:
            self._call_app_method("notify_vote", voter, voted_for, reason, submission_round)

    def highlight_winner_quick(
        self,
        winner_id: str,
        vote_results: dict[str, Any] | None = None,
    ) -> None:
        """Highlight the winning agent in no-refinement mode (skip_final_presentation).

        This marks the winner's tab with a trophy and adds a banner indicating
        the existing answer was used, without streaming a new final presentation.

        Args:
            winner_id: The winning agent's ID
            vote_results: Vote results dict with vote_counts, winner, is_tie, etc.
        """
        if self._app:
            self._call_app_method("highlight_winner_quick", winner_id, vote_results or {})

    def send_new_answer(
        self,
        agent_id: str,
        content: str,
        answer_id: str | None = None,
        answer_number: int = 1,
        answer_label: str | None = None,
        workspace_path: str | None = None,
        submission_round: int = 1,
    ) -> None:
        """Notify the TUI of a new answer - shows enhanced toast and tracks for browser.

        Args:
            agent_id: Agent that submitted the answer
            content: The answer content
            answer_id: Optional unique answer ID
            answer_number: The answer number for this agent (1, 2, etc.)
            answer_label: Label for this answer (e.g., "agent1.1")
            workspace_path: Absolute path to the workspace snapshot for this answer
            submission_round: Round the answer was submitted in (1-indexed display round)
        """
        if self._app:
            self._call_app_method(
                "notify_new_answer",
                agent_id,
                content,
                answer_id,
                answer_number,
                answer_label,
                workspace_path,
                submission_round,
            )

    def record_answer_with_context(
        self,
        agent_id: str,
        answer_label: str,
        context_sources: list[str],
        round_num: int,
    ) -> None:
        """Record an answer node with its context sources for timeline visualization.

        Args:
            agent_id: Agent who submitted the answer
            answer_label: Label like "agent1.1"
            context_sources: List of answer labels this agent saw (e.g., ["agent2.1"])
            round_num: Round number for this answer
        """
        if self._app:
            self._call_app_method(
                "record_answer_context",
                agent_id,
                answer_label,
                context_sources,
                round_num,
            )

    def notify_context_received(self, agent_id: str, context_sources: list[str]) -> None:
        """Notify the TUI when an agent receives context from other agents.

        Args:
            agent_id: Agent receiving context
            context_sources: List of answer labels this agent can now see
        """
        if self._app:
            self._call_app_method("update_agent_context", agent_id, context_sources)

    def notify_phase(self, phase: str):
        """Notify the TUI of a phase change - updates status bar."""
        tui_log(f"TextualTerminalDisplay.notify_phase called with phase='{phase}', _app={self._app is not None}")
        if self._app:
            self._call_app_method("notify_phase", phase)
        else:
            tui_log("  WARNING: _app is None, cannot forward notify_phase")

    def notify_completion(self, agent_id: str):
        """Notify the TUI of agent completion - shows toast."""
        if self._app:
            self._call_app_method("notify_completion", agent_id)

    def notify_error(self, agent_id: str, error: str):
        """Notify the TUI of an error - shows error toast."""
        if self._app:
            self._call_app_method("notify_error", agent_id, error)

    def update_loading_status(self, message: str):
        """Update the loading status text on all agent panels.

        Use this during initialization to show progress like:
        - "Creating agents..."
        - "Starting Docker containers..."
        - "Connecting to MCP servers..."
        """
        if self._app:
            self._call_app_method("_update_all_loading_text", message)

    def update_status_bar_votes(self, vote_counts: dict[str, int]):
        """Update vote counts in the status bar."""
        if self._app:
            self._call_app_method("update_status_bar_votes", vote_counts)

    def _get_context_path_writes_footer(self) -> str:
        """Generate footer text for context path writes.

        Returns:
            Footer text if files were written, empty string otherwise.
        """
        if not self.orchestrator:
            return ""

        writes = self.orchestrator.get_context_path_writes() if hasattr(self.orchestrator, "get_context_path_writes") else []
        if not writes:
            return ""

        # Get categorized writes if available
        categorized = {}
        if hasattr(self.orchestrator, "get_context_path_writes_categorized"):
            categorized = self.orchestrator.get_context_path_writes_categorized()
        new_files = categorized.get("new", [])
        modified_files = categorized.get("modified", [])

        INLINE_THRESHOLD = 5  # Show inline if <= this many files

        # Create visually distinct section
        header = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        if len(writes) <= INLINE_THRESHOLD:
            # Show files inline, split by category
            footer_lines = [
                header,
                "📂 **Context Path Changes**",
                "",
            ]
            if new_files:
                footer_lines.append("  **New files:**")
                for path in sorted(new_files):
                    footer_lines.append(f"    ✚ `{path}`")
            if modified_files:
                if new_files:
                    footer_lines.append("")  # Blank line between sections
                footer_lines.append("  **Modified files:**")
                for path in sorted(modified_files):
                    footer_lines.append(f"    ✎ `{path}`")
            return "\n".join(footer_lines)
        else:
            # Many files - write to log file and show summary
            log_file_path = self._write_context_path_log(writes, new_files, modified_files)
            summary = f"{len(new_files)} new, {len(modified_files)} modified"
            return f"{header}\n📂 **{len(writes)} Context Path Changes** ({summary})\n\n  See full list: `{log_file_path}`"

    def _write_context_path_log(
        self,
        writes: list[str],
        new_files: list[str] | None = None,
        modified_files: list[str] | None = None,
    ) -> str:
        """Write full context path write list to log directory.

        Args:
            writes: List of all file paths written to context paths.
            new_files: List of new file paths (optional, for categorized output).
            modified_files: List of modified file paths (optional, for categorized output).

        Returns:
            Path to the log file.
        """
        log_file = self.output_dir / "context_path_writes.txt"
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"Context Path Changes - {len(writes)} files\n")
                f.write("=" * 50 + "\n\n")

                if new_files or modified_files:
                    # Categorized output
                    if new_files:
                        f.write(f"New files ({len(new_files)}):\n")
                        for path in sorted(new_files):
                            f.write(f"  + {path}\n")
                        f.write("\n")
                    if modified_files:
                        f.write(f"Modified files ({len(modified_files)}):\n")
                        for path in sorted(modified_files):
                            f.write(f"  ~ {path}\n")
                else:
                    # Flat output (fallback)
                    for path in sorted(writes):
                        f.write(f"{path}\n")

            return str(log_file)
        except OSError as exc:
            logger.error(f"Failed to write context path log: {exc}")
            return ""

    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Show final answer completion card.

        Note: With the "final presentation as round N+1" approach, content has already
        been displayed through the normal pipeline (thinking, tools, response).
        This method adds the completion card and persists the final answer.
        """
        if not selected_agent:
            return

        display_answer = answer or ""
        try:
            logger.info(
                f"[FinalAnswer] show_final_answer: selected_agent={selected_agent} " f"answer_len={len(display_answer)} vote_keys={list((vote_results or {}).keys())}",
            )
        except Exception as e:
            tui_log(f"[TextualDisplay] {e}")

        # Add context path writes footer if any files were written
        context_writes_footer = self._get_context_path_writes_footer()
        if context_writes_footer:
            display_answer = display_answer.rstrip() + "\n" + context_writes_footer

        self._final_answer_metadata = {
            "selected_agent": selected_agent,
            "vote_results": vote_results or {},
        }
        self._final_presentation_agent = selected_agent

        # Write to final presentation file(s)
        persist_needed = self._final_answer_cache is None or self._final_answer_cache != display_answer
        if persist_needed:
            self._persist_final_presentation(display_answer, selected_agent, vote_results)
            self._final_answer_cache = display_answer

        self._write_to_system_file("Final presentation ready.")

        # Add completion card (post-evaluation section + action buttons)
        if self._app:
            self._call_app_method(
                "show_final_presentation",
                display_answer,
                vote_results,
                selected_agent,
            )

    def show_post_evaluation_content(self, content: str, agent_id: str):
        """Display post-evaluation streaming content.

        Bug 2 fix: _routing_to_post_eval_card flag is set at coordination level
        when post-eval starts, preventing duplicate routing to timeline.
        """
        eval_msg = f"\n[POST-EVALUATION]\n{content}"
        self._write_to_agent_file(agent_id, eval_msg)
        for line in content.splitlines() or [content]:
            clean = line.strip()
            if clean:
                self._post_evaluation_lines.append(clean)

        if self._app:
            self._call_app_method("show_post_evaluation", content, agent_id)

    def end_post_evaluation_content(self, agent_id: str):
        """Called when post-evaluation is complete to show footer with buttons."""
        # Bug 2 fix: Clear flag when post-eval ends
        self._routing_to_post_eval_card = False

        if self._app:
            self._call_app_method("end_post_evaluation", agent_id)

    def show_post_evaluation_tool_content(self, tool_name: str, args: dict, agent_id: str):
        """Called when a post-evaluation tool call (submit/restart) is detected."""
        if self._app:
            self._call_app_method("show_post_evaluation_tool", tool_name, args, agent_id)

    def show_restart_banner(self, reason: str, instructions: str, attempt: int, max_attempts: int):
        """Display restart decision banner."""
        banner_msg = f"\n{'=' * 60}\n" f"RESTART TRIGGERED (Attempt {attempt}/{max_attempts})\n" f"Reason: {reason}\n" f"Instructions: {instructions}\n" f"{'=' * 60}\n"

        self._write_to_system_file(banner_msg)

        if self._app:
            self._call_app_method("show_restart_banner", reason, instructions, attempt, max_attempts)

    def show_restart_context_panel(self, reason: str, instructions: str):
        """Display restart context panel at top of UI (for attempt 2+)."""
        self.restart_reason = reason
        self.restart_instructions = instructions

        if self._app:
            self._call_app_method("show_restart_context", reason, instructions)

    def show_agent_restart(self, agent_id: str, round_num: int):
        """Notify that a specific agent is starting a new round.

        This is called when an agent restarts due to new context from other agents.
        The TUI should show a fresh timeline for this agent.

        Args:
            agent_id: The agent that is restarting
            round_num: The new round number for this agent
        """
        if self._app:
            self._call_app_method("show_agent_restart", agent_id, round_num)

    def show_final_presentation_start(self, agent_id: str, vote_counts: dict[str, int] | None = None, answer_labels: dict[str, str] | None = None):
        """Notify that the final presentation phase is starting for the winning agent.

        This shows a fresh view with a distinct "Final Presentation" banner
        in green to indicate this is the winning agent presenting.

        Args:
            agent_id: The winning agent presenting the final answer
            vote_counts: Optional dict of {agent_id: vote_count} for vote summary display
            answer_labels: Optional dict of {agent_id: label} for display (e.g., {"agent1": "A1.1"})
        """
        # Skip direct content updates during final presentation - event pipeline handles it
        self._in_final_presentation = True
        if self._app:
            self._call_app_method("show_final_presentation_start", agent_id, vote_counts, answer_labels)

    def cleanup(self):
        """Cleanup and exit Textual app."""
        if self._app:
            self._app.exit()
            self._app = None
        self._post_evaluation_lines.clear()
        self._final_stream_active = False
        self._final_stream_buffer = ""
        self._final_answer_cache = None
        self._final_answer_metadata = {}
        self._final_presentation_agent = None

        # Restore console logging after Textual display is done
        from massgen.logger_config import restore_console_logging

        restore_console_logging()

    def reset_quit_request(self) -> None:
        """Reset the quit request flag at the start of each turn."""
        self._user_quit_requested = False

    def request_cancellation(self) -> None:
        """Request cancellation of the current turn."""
        self._user_quit_requested = True
        # Update execution status to show cancelled state
        if self._app and hasattr(self._app, "_show_cancelled_status"):
            self._call_app_method("_show_cancelled_status")

    # =========================================================================
    # Multi-turn Lifecycle Methods
    # =========================================================================

    def start_session(
        self,
        initial_question: str,
        log_filename: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Start a new interactive session - creates the app ONCE."""
        self.session_id = session_id
        self.current_turn = 1

        # Only initialize if app doesn't exist
        if self._app is None:
            self.initialize(initial_question, log_filename)

    def begin_turn(self, turn: int, question: str, previous_answer: str | None = None) -> None:
        """Begin a new turn within an existing session.

        Updates the header and resets the UI for the new turn.
        Does NOT recreate the app.

        Args:
            turn: The turn number (1-indexed).
            question: The user's question for this turn.
            previous_answer: Optional summary of the previous turn's answer.
        """
        self.current_turn = turn
        self.question = question

        self.reset_quit_request()

        self._final_answer_cache = None
        self._final_answer_metadata = {}
        self._final_stream_active = False
        self._final_stream_buffer = ""
        self._final_presentation_agent = None

        # Fully reset UI for new turn (clears timelines, adds turn separator)
        if self._app:
            from massgen.logger_config import logger

            logger.info(f"[TUI] Calling prepare_for_new_turn(turn={turn})")
            self._call_app_method("prepare_for_new_turn", turn, previous_answer)
            logger.info("[TUI] prepare_for_new_turn complete, now calling update_turn_header")
            self._call_app_method("update_turn_header", turn, question)
            logger.info("[TUI] update_turn_header complete")

        for agent_id in self.agent_ids:
            separator = f"\n{'='*60}\n=== TURN {turn} ===\n{'='*60}\n"
            self._write_to_agent_file(agent_id, separator)

        self._write_to_system_file(f"\n=== TURN {turn} ===\nQuestion: {question}\n")

    def set_agent_subtasks(self, subtasks: dict[str, str]) -> None:
        """Pass agent subtask assignments to the TUI for display in the tab bar.

        Args:
            subtasks: Mapping of agent_id to subtask description.
        """
        if self._app:
            self._call_app_method("set_agent_subtasks", subtasks)

    def set_agent_personas(self, personas: dict[str, str]) -> None:
        """Pass agent persona assignments to the TUI for display in the tab bar.

        Args:
            personas: Mapping of agent_id to persona summary/description.
        """
        if self._app:
            self._call_app_method("set_agent_personas", personas)

    def set_evaluation_criteria(
        self,
        criteria: list[dict],
        source: str = "default",
    ) -> None:
        """Pass active evaluation criteria to the TUI for display via Ctrl+E.

        Args:
            criteria: List of dicts with keys: id, text, category, verify_by.
            source: Where the criteria came from (generated, inline, preset name, default).
        """
        if self._app:
            self._call_app_method("set_evaluation_criteria", criteria, source)

    def begin_restart(
        self,
        attempt: int,
        max_attempts: int,
        reason: str = "",
        instructions: str = "",
    ) -> None:
        """Prepare the TUI for a restart attempt without recreating the app.

        Resets internal state and delegates to the app's prepare_for_restart_attempt.

        Args:
            attempt: The new attempt number (1-indexed).
            max_attempts: Total allowed attempts.
            reason: Why the restart was triggered.
            instructions: Instructions for the next attempt.
        """
        self.reset_quit_request()
        self._final_answer_cache = None
        self._final_answer_metadata = {}
        self._final_stream_active = False
        self._final_stream_buffer = ""
        self._final_presentation_agent = None

        if self._app:
            self._call_app_method(
                "prepare_for_restart_attempt",
                attempt,
                max_attempts,
                reason,
                instructions,
            )

        for agent_id in self.agent_ids:
            separator = f"\n{'='*60}\n=== ATTEMPT {attempt}/{max_attempts} ===\n{'='*60}\n"
            self._write_to_agent_file(agent_id, separator)
        self._write_to_system_file(
            f"\n=== ATTEMPT {attempt}/{max_attempts} ===\nReason: {reason}\n",
        )

    def end_turn(
        self,
        turn: int,
        answer: str | None = None,
        error: Exception | None = None,
        was_cancelled: bool = False,
    ) -> None:
        """End the current turn"""
        if self._app:
            self._call_app_method("set_input_enabled", True)

        if was_cancelled:
            self._write_to_system_file(f"Turn {turn} cancelled by user.")
        elif error:
            self._write_to_system_file(f"Turn {turn} failed: {error}")
        else:
            self._write_to_system_file(f"Turn {turn} completed successfully.")

    def is_session_active(self) -> bool:
        """Check if a session is currently active (app is running)"""
        return self._app is not None

    def run(self):
        """Run Textual app in main thread."""
        if self._app and TEXTUAL_AVAILABLE:
            self._app.run()

    async def run_async(self):
        """Run Textual app within an existing asyncio event loop."""
        if self._app and TEXTUAL_AVAILABLE:
            await self._app.run_async()

    # Rich parity methods (not in BaseDisplay, but needed for feature parity)
    def display_vote_results(self, vote_results: dict[str, Any]):
        """Display vote results in formatted table."""
        formatted = self._format_vote_results(vote_results)
        self._call_app_method("display_vote_results", formatted)
        self._write_to_system_file(f"Vote Results: {vote_results}")

    def display_coordination_table(self):
        """Display coordination table using existing builder."""
        table_text = self._format_coordination_table_from_orchestrator()
        self._call_app_method("display_coordination_table", table_text)

    def update_system_status(self, status: str) -> None:
        """Display system-level status updates (initialization, cancellation, etc.)"""
        self._write_to_system_file(f"System status: {status}")

        if self._app:
            self._call_app_method("add_orchestrator_event", status)

    def _format_coordination_table_from_orchestrator(self) -> str:
        """Build coordination table text with best effort."""
        table_text = "Coordination data is not available yet."
        try:
            from massgen.frontend.displays.create_coordination_table import (
                CoordinationTableBuilder,
            )

            tracker = getattr(self.orchestrator, "coordination_tracker", None)
            if tracker:
                events_data = [event.to_dict() for event in getattr(tracker, "events", [])]
                session_data = {
                    "session_metadata": {
                        "user_prompt": getattr(tracker, "user_prompt", ""),
                        "agent_ids": getattr(tracker, "agent_ids", []),
                        "start_time": getattr(tracker, "start_time", None),
                        "end_time": getattr(tracker, "end_time", None),
                        "final_winner": getattr(tracker, "final_winner", None),
                    },
                    "events": events_data,
                }
                builder = CoordinationTableBuilder(session_data)
                table_text = self._format_coordination_table(builder)
        except Exception as exc:
            table_text = f"Unable to build coordination table: {exc}"

        return table_text

    def show_agent_selector(self):
        """Show interactive agent selector modal."""
        self._call_app_method("show_agent_selector")

    async def prompt_for_broadcast_response(self, broadcast_request: Any) -> Any | None:
        """Prompt human for response to a broadcast question.

        Args:
            broadcast_request: BroadcastRequest object with question details

        Returns:
            For simple questions: Human's response string, or None if skipped/timeout
            For structured questions: List of response dicts, or None if skipped/timeout
        """
        import asyncio

        if not self._app:
            return None

        # Extract details from broadcast request
        sender_agent_id = getattr(broadcast_request, "sender_agent_id", "Unknown Agent")
        base_timeout = getattr(broadcast_request, "timeout", 60)

        # Check if this is a structured question
        is_structured = getattr(broadcast_request, "is_structured", False)

        # For structured questions, use longer timeout (5 min) to give user time to answer all
        timeout = 300 if is_structured else base_timeout

        # Create a future to wait for the modal result
        response_future: asyncio.Future = asyncio.Future()

        # Track the modal we push so we only pop our own modal on timeout
        modal_ref = {"modal": None}

        def show_modal():
            """Show the appropriate broadcast modal and handle response."""
            if is_structured:
                # Use structured modal for questions with options
                structured_questions = getattr(broadcast_request, "structured_questions", [])
                modal = StructuredBroadcastPromptModal(
                    sender_agent_id,
                    structured_questions,
                    timeout,
                    self._app,
                )
            else:
                # Use simple modal for text questions
                question = getattr(broadcast_request, "question", "No question provided")
                if isinstance(question, str):
                    question_text = question
                else:
                    question_text = getattr(broadcast_request, "question_text", "No question provided")
                modal = BroadcastPromptModal(sender_agent_id, question_text, timeout, self._app)

            # Store reference to this specific modal
            modal_ref["modal"] = modal

            async def handle_dismiss(result):
                if not response_future.done():
                    response_future.set_result(result)

            self._app.push_screen(modal, handle_dismiss)

        # Call from the app thread
        self._app.call_from_thread(show_modal)

        try:
            # Wait for response with timeout
            result = await asyncio.wait_for(response_future, timeout=timeout)
            return result
        except TimeoutError:
            # Only dismiss if the current top screen is OUR modal (not a different one)
            def safe_pop():
                if self._app.screen_stack and modal_ref["modal"]:
                    current_screen = self._app.screen_stack[-1]
                    if current_screen is modal_ref["modal"]:
                        self._app.pop_screen()

            self._app.call_from_thread(safe_pop)
            return None

    def stream_final_answer_chunk(self, chunk: str, selected_agent: str | None, vote_results: dict[str, Any] | None = None):
        """DEPRECATED: Final presentation content now flows through update_agent_content().

        This method is kept for backwards compatibility but is no longer called.
        Content routing in coordination_ui.py sends all content through the normal
        pipeline, and final presentation is treated as round N+1.
        """
        # No-op - content now flows through update_agent_content()

    def _prepare_agent_content(self, agent_id: str, content: str, content_type: str) -> str | None:
        """Normalize agent content, apply filters, and truncate noisy sections."""
        if not content:
            return None

        if agent_id not in self._recent_web_chunks:
            self._recent_web_chunks[agent_id] = deque(maxlen=self.max_web_search_lines)

        if self._should_filter_content(content, content_type):
            return None

        if content_type in {"status", "presentation", "tool"}:
            self._reset_web_cache(agent_id)

        if self._is_web_search_content(content):
            truncated = self._truncate_web_content(content)
            history = self._recent_web_chunks.get(agent_id)
            if history is not None:
                history.append(truncated)
            return truncated

        return content

    def _truncate_web_content(self, content: str) -> str:
        """Trim verbose web search snippets while keeping the useful prefix."""
        max_len = min(60, self.max_line_length // 2)
        if len(content) <= max_len:
            return content

        truncated = content[:max_len]
        for token in [". ", "! ", "? ", ", "]:
            idx = truncated.rfind(token)
            if idx > max_len // 2:
                truncated = truncated[: idx + 1]
                break
        return truncated.rstrip() + "..."

    def _should_filter_content(self, content: str, content_type: str) -> bool:
        """Drop metadata-only lines and ultra-long noise blocks."""
        if content_type in {"status", "presentation", "error", "tool"}:
            return False

        stripped = content.strip()
        if stripped.startswith("...") and stripped.endswith("..."):
            return True

        if len(stripped) > 1500 and self._is_web_search_content(stripped):
            return True

        return False

    def _is_web_search_content(self, content: str) -> bool:
        """Heuristic detection for web-search/tool snippets."""
        lowered = content.lower()
        markers = [
            "search query",
            "search result",
            "web search",
            "url:",
            "source:",
        ]
        return any(marker in lowered for marker in markers) or lowered.startswith("http")

    def _reset_web_cache(self, agent_id: str, truncate_history: bool = False):
        """Reset stored web search snippets after a status change."""
        if agent_id in self._recent_web_chunks:
            self._recent_web_chunks[agent_id].clear()

        if truncate_history:
            with self._buffer_lock:
                buf = self._buffers.get(agent_id, [])
                if buf:
                    trimmed: list[dict[str, Any]] = []
                    web_count = 0
                    for entry in reversed(buf):
                        if self._is_web_search_content(entry.get("content", "")):
                            web_count += 1
                            if web_count > self.max_web_lines_on_status_change:
                                continue
                        trimmed.append(entry)
                    trimmed.reverse()
                    self._buffers[agent_id] = trimmed

    def _format_vote_results(self, vote_results: dict[str, Any]) -> str:
        """Turn vote results dict into a readable multiline string for Textual modal."""
        if not vote_results:
            return "No vote data is available yet."

        lines = ["🗳️ Vote Results", "=" * 40]
        vote_counts = vote_results.get("vote_counts", {})
        winner = vote_results.get("winner")
        is_tie = vote_results.get("is_tie", False)

        if vote_counts:
            lines.append("\n📊 Vote Count:")
            for agent_id, count in sorted(vote_counts.items(), key=lambda item: item[1], reverse=True):
                prefix = "🏆 " if agent_id == winner else "   "
                tie_note = " (tie-broken)" if is_tie and agent_id == winner else ""
                lines.append(f"{prefix}{agent_id}: {count} vote{'s' if count != 1 else ''}{tie_note}")

        voter_details = vote_results.get("voter_details", {})
        if voter_details:
            lines.append("\n🔍 Rationale:")
            for voted_for, voters in voter_details.items():
                lines.append(f"→ {voted_for}")
                for detail in voters:
                    reason = detail.get("reason", "").strip()
                    voter = detail.get("voter", "unknown")
                    lines.append(f'   • {voter}: "{reason}"')

        total_votes = vote_results.get("total_votes", 0)
        agents_voted = vote_results.get("agents_voted", 0)
        lines.append(f"\n📈 Participation: {agents_voted}/{total_votes} agents voted")
        if is_tie:
            lines.append("⚖️  Tie broken by coordinator ordering")

        mapping = vote_results.get("agent_mapping", {})
        if mapping:
            lines.append("\n🔀 Agent Mapping:")
            for anon_id, real_id in mapping.items():
                lines.append(f"   {anon_id} → {real_id}")

        return "\n".join(lines)

    def _format_coordination_table(self, builder: Any) -> str:
        """Compose summary metadata plus plain-text table for Textual modal."""
        table_text = builder.generate_event_table()
        metadata = builder.session_metadata if hasattr(builder, "session_metadata") else {}
        lines = ["📋 Coordination Session", "=" * 40]
        if metadata:
            question = metadata.get("user_prompt") or ""
            if question:
                lines.append(f"💡 Question: {question}")
            final_winner = metadata.get("final_winner")
            if final_winner:
                lines.append(f"🏆 Winner: {final_winner}")
            start = metadata.get("start_time")
            end = metadata.get("end_time")
            if start and end:
                lines.append(f"⏱️  Duration: {start} → {end}")
        lines.append("\n" + table_text)
        lines.append("\nTip: Use the mouse wheel or drag the scrollbar to explore this view.")
        return "\n".join(lines)

    def _persist_final_presentation(self, content: str, selected_agent: str | None, vote_results: dict[str, Any] | None):
        """Persist final presentation to files with latest pointer."""
        header = ["=== FINAL PRESENTATION ==="]
        if selected_agent:
            header.append(f"Selected Agent: {selected_agent}")
        if vote_results:
            header.append(f"Vote Results: {vote_results}")
        header.append("")  # blank line
        final_text = "\n".join(header) + f"{content}\n"

        targets: list[Path] = []
        if selected_agent:
            agent_file = self.output_dir / f"final_presentation_{selected_agent}.txt"
            self.final_presentation_file = agent_file
            self.final_presentation_latest = self.output_dir / f"final_presentation_{selected_agent}_latest.txt"
            targets.append(agent_file)
        else:
            if self.final_presentation_file is None:
                self.final_presentation_file = self.output_dir / "final_presentation.txt"
            if self.final_presentation_latest is None:
                self.final_presentation_latest = self.output_dir / "final_presentation_latest.txt"
            targets.append(self.final_presentation_file)

        for path in targets:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(final_text)
            except OSError as exc:
                logger.error(f"Failed to persist final presentation to {path}: {exc}")

        if self.final_presentation_latest:
            try:
                if self.final_presentation_latest.exists() or self.final_presentation_latest.is_symlink():
                    self.final_presentation_latest.unlink()
                self.final_presentation_latest.symlink_to(targets[-1].name)
            except (OSError, NotImplementedError) as exc:
                logger.warning(f"Failed to create final presentation symlink at {self.final_presentation_latest}: {exc}")

    def get_mode_state(self) -> Optional["TuiModeState"]:
        """Get the current TUI mode state for orchestrator configuration.

        Returns:
            TuiModeState instance if the TextualApp is running, None otherwise.
        """
        if self._app and hasattr(self._app, "_mode_state"):
            return self._app._mode_state
        return None

    def _persist_planning_revision_snapshot(
        self,
        plan_path: Path,
        plan_data: dict[str, Any],
        mode_state: "TuiModeState",
    ) -> None:
        """Persist the latest planning revision immediately.

        This creates/reuses a plan session at review time so iterative modal edits
        and refinements survive even before final execution is triggered.
        """
        from massgen.logger_config import get_log_session_root
        from massgen.plan_storage import PlanStorage

        storage = PlanStorage()
        session = mode_state.plan_session

        if session is None:
            log_dir = get_log_session_root()
            planning_turn = mode_state.planning_started_turn
            if planning_turn is None:
                planning_turn = getattr(self, "_current_turn", 0) or 0
                mode_state.planning_started_turn = planning_turn
            session = storage.create_plan(
                log_dir.name,
                str(log_dir),
                planning_prompt=mode_state.last_planning_question,
                planning_turn=planning_turn,
            )
            mode_state.plan_session = session
            mode_state.selected_plan_id = session.plan_id

        try:
            plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
        except Exception as write_err:
            logger.warning(f"[PlanApproval] Failed to persist plan file before snapshot: {write_err}")

        storage.finalize_planning_phase(
            session,
            plan_path.parent,
            context_paths=mode_state.planning_context_paths or [],
        )

        metadata = session.load_metadata()
        metadata.plan_revision = mode_state.plan_revision or metadata.plan_revision
        metadata.planning_iteration_count = mode_state.planning_iteration_count or metadata.planning_iteration_count
        if mode_state.planning_feedback_history:
            metadata.planning_feedback_history = list(mode_state.planning_feedback_history)
        metadata.last_planning_mode = mode_state.last_planning_mode
        metadata.execution_mode = metadata.execution_mode or "chunked_by_planner_v1"
        session.save_metadata(metadata)

    def show_plan_approval_modal(
        self,
        tasks: list[dict[str, Any]],
        plan_path: Path,
        plan_data: dict[str, Any],
        mode_state: "TuiModeState",
    ) -> None:
        """Show the plan approval modal and handle the result.

        Called from TextualInteractiveAdapter when planning completes.

        Args:
            tasks: List of tasks from the plan
            plan_path: Path to the plan file
            plan_data: Full plan data dictionary
            mode_state: TuiModeState instance to update
        """
        if not self._app:
            logger.warning("[PlanApproval] Cannot show modal - no app instance")
            mode_state.reset_plan_state()
            return

        try:
            self._persist_planning_revision_snapshot(plan_path, plan_data, mode_state)
        except Exception as e:
            logger.warning(f"[PlanApproval] Failed to persist planning snapshot: {e}")

        from massgen.frontend.displays.textual_widgets.plan_approval_modal import (
            PlanApprovalModal,
            PlanApprovalResult,
        )

        def show_modal():
            try:
                # If quick-edit temporarily forced single-agent visuals, restore
                # the user's prior agent-mode selection before showing review.
                if getattr(mode_state, "quick_edit_restore_pending", False):
                    restore_mode = mode_state.quick_edit_prev_agent_mode or "multi"
                    restore_selected = mode_state.quick_edit_prev_selected_agent
                    mode_state.agent_mode = restore_mode
                    mode_state.selected_single_agent = restore_selected
                    mode_state.quick_edit_prev_agent_mode = None
                    mode_state.quick_edit_prev_selected_agent = None
                    mode_state.quick_edit_restore_pending = False

                    if hasattr(self._app, "_set_agent_mode_visual_state"):
                        self._app._set_agent_mode_visual_state(restore_mode, restore_selected)

                revision = getattr(mode_state, "plan_revision", 0) or None
                modal = PlanApprovalModal(tasks, plan_path, plan_data, revision=revision)

                def handle_result(result: PlanApprovalResult) -> None:
                    try:
                        action = getattr(result, "action", "cancel") if result else "cancel"
                        if action == "finalize":
                            self._execute_approved_plan(result, mode_state)
                        elif action == "finalize_manual":
                            self._execute_approved_plan(
                                result,
                                mode_state,
                                auto_submit=False,
                            )
                        elif action in {"continue", "quick_edit"}:
                            self._continue_planning_refinement(result, mode_state)
                        else:
                            # Cancelled - reset to normal mode
                            mode_state.reset_plan_state()
                            self._app.notify("Plan cancelled", severity="information")
                            if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                                self._app._mode_bar.set_plan_mode("normal")
                    except Exception as e:
                        logger.exception(f"[PlanApproval] Error handling modal result: {e}")
                        mode_state.reset_plan_state()
                        self._app.notify(f"Plan error: {e}", severity="error")
                        if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                            self._app._mode_bar.set_plan_mode("normal")

                self._app.push_screen(modal, handle_result)
            except Exception as e:
                logger.exception(f"[PlanApproval] Error showing modal: {e}")
                mode_state.reset_plan_state()
                self._app.notify(f"Failed to show plan approval: {e}", severity="error")
                if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                    self._app._mode_bar.set_plan_mode("normal")

        try:
            self._app.call_from_thread(show_modal)
        except Exception as e:
            logger.exception(f"[PlanApproval] call_from_thread failed: {e}")
            mode_state.reset_plan_state()
            # Can't notify via app if call_from_thread failed
            logger.error("[PlanApproval] Failed to dispatch modal to main thread")

    def _continue_planning_refinement(
        self,
        result: "PlanApprovalResult",
        mode_state: "TuiModeState",
    ) -> None:
        """Queue another planning turn from the plan review modal."""
        if not self._app:
            mode_state.reset_plan_state()
            return

        action = getattr(result, "action", "continue")
        planning_mode = "single" if action == "quick_edit" else "multi"
        feedback = (getattr(result, "feedback", None) or "").strip()
        if not feedback:
            self._app.notify(
                "Cannot continue planning with an empty prompt. Enter feedback in the review modal.",
                severity="warning",
                timeout=4,
            )
            return

        mode_state.pending_planning_mode = planning_mode
        mode_state.last_planning_mode = planning_mode
        mode_state.pending_planning_feedback = feedback
        mode_state.planning_feedback_history.append(feedback)

        # Keep planning mode active and submit refinement prompt.
        mode_state.plan_mode = "plan"
        if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
            self._app._mode_bar.set_plan_mode("plan")

        if planning_mode == "single":
            # Temporarily reflect quick-edit single-agent mode in the mode bar.
            # We'll restore these visuals after the turn completes.
            mode_state.quick_edit_prev_agent_mode = mode_state.agent_mode
            mode_state.quick_edit_prev_selected_agent = mode_state.selected_single_agent
            mode_state.quick_edit_restore_pending = True

            selected = mode_state.selected_single_agent or getattr(self._app, "_active_agent_id", None)
            if not selected and getattr(self.coordination_display, "agent_ids", None):
                selected = self.coordination_display.agent_ids[0]
            mode_state.agent_mode = "single"
            mode_state.selected_single_agent = selected
            if hasattr(self._app, "_set_agent_mode_visual_state"):
                self._app._set_agent_mode_visual_state("single", selected)
        else:
            mode_state.quick_edit_prev_agent_mode = None
            mode_state.quick_edit_prev_selected_agent = None
            mode_state.quick_edit_restore_pending = False

        refinement_prompt = "Refine `project_plan.json` using the latest plan review." " Keep chunk labels deterministic and update any affected dependencies."
        refinement_prompt += f"\n\nPlan review feedback:\n{feedback}"

        refinement_prompt = refinement_prompt.strip()
        if not refinement_prompt:
            self._app.notify(
                "Cannot submit an empty planning refinement prompt.",
                severity="warning",
                timeout=3,
            )
            return

        self._app.notify(
            ("Quick Edit: running single-agent planning refinement..." if planning_mode == "single" else "Continuing planning refinement..."),
            severity="information",
            timeout=3,
        )

        question_input = getattr(self._app, "question_input", None)
        if question_input:
            question_input.disabled = True
            question_input.value = refinement_prompt

            def submit_and_reenable() -> None:
                try:
                    submit_value = refinement_prompt.strip()
                    if not submit_value:
                        self._app.notify(
                            "Cannot submit an empty planning refinement prompt.",
                            severity="warning",
                            timeout=3,
                        )
                        return
                    self._app._submit_question(submit_value)
                finally:
                    question_input.disabled = False

            self._app.call_later(submit_and_reenable)
        else:
            self._app.call_later(lambda: self._app._submit_question(refinement_prompt.strip()))

    async def show_change_review_modal(
        self,
        changes: list[dict[str, Any]],
    ) -> "ReviewResult":
        """Show modal for reviewing changes before applying.

        This method displays a modal that shows git diffs from isolated write
        contexts and allows the user to approve or reject changes before they
        are applied to the original context paths.

        Args:
            changes: List of context change dicts with keys:
                - original_path: Original context path
                - isolated_path: Isolated context path
                - changes: List of file changes [{status, path}, ...]
                - diff: Git diff output string

        Returns:
            ReviewResult with approval status and selected files
        """
        import asyncio

        from massgen.filesystem_manager import ReviewResult

        if not self._app:
            logger.warning("[ChangeReview] Cannot show modal - no app instance")
            return ReviewResult(approved=False, metadata={"error": "no_app"})

        from .textual.widgets.modals.review_modal import GitDiffReviewModal

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[ReviewResult] = loop.create_future()

        def show_modal():
            try:
                modal = GitDiffReviewModal(changes=changes)

                def handle_result(result: ReviewResult) -> None:
                    # Must use call_soon_threadsafe because this callback runs
                    # on the Textual thread, not the asyncio event loop thread.
                    if not result_future.done():
                        loop.call_soon_threadsafe(result_future.set_result, result)

                self._app.push_screen(modal, handle_result)
            except Exception as e:
                logger.exception(f"[ChangeReview] Error showing modal: {e}")
                if not result_future.done():
                    loop.call_soon_threadsafe(
                        result_future.set_result,
                        ReviewResult(approved=False, metadata={"error": str(e)}),
                    )

        try:
            self._app.call_from_thread(show_modal)
        except Exception as e:
            logger.exception(f"[ChangeReview] call_from_thread failed: {e}")
            return ReviewResult(approved=False, metadata={"error": str(e)})

        try:
            # Wait for user decision with 5 minute timeout
            return await asyncio.wait_for(result_future, timeout=300)
        except TimeoutError:
            logger.warning("[ChangeReview] Modal timed out after 5 minutes")
            # Try to dismiss the modal on timeout
            try:
                self._app.call_from_thread(self._app.pop_screen)
            except Exception:
                pass
            return ReviewResult(approved=False, metadata={"error": "timeout"})

    async def show_final_answer_modal(
        self,
        changes: list[dict[str, Any]],
        answer_content: str,
        vote_results: dict[str, Any],
        agent_id: str,
        model_name: str = "",
        post_eval_content: str | None = None,
        post_eval_status: str = "none",
        context_paths: dict | None = None,
        workspace_path: str | None = None,
    ) -> "ReviewResult":
        """Show the tabbed Final Answer modal with optional Review Changes tab.

        Combines the final answer presentation with diff review into a single
        modal. The Answer tab shows vote info and the winning answer. The
        Review Changes tab (shown only when changes exist) provides the full
        diff review UI. When no changes exist but workspace_path is set,
        a Workspace browser tab is shown instead.

        Args:
            changes: List of context change dicts (same format as show_change_review_modal)
            answer_content: The final answer markdown text
            vote_results: Vote results dict with winner, vote_counts, is_tie
            agent_id: ID of the winning agent
            model_name: Model name used by the agent
            post_eval_content: Optional post-evaluation text
            post_eval_status: "none" or "verified"
            context_paths: Optional dict with "new" and "modified" path lists
            workspace_path: Optional path to agent workspace dir (no-git mode)

        Returns:
            ReviewResult with approval status and selected files
        """
        import asyncio

        from massgen.filesystem_manager import ReviewResult

        if not self._app:
            logger.warning("[FinalAnswer] Cannot show modal - no app instance")
            return ReviewResult(approved=False, metadata={"error": "no_app"})

        from .textual.widgets.modals.final_answer_modal import (
            FinalAnswerModal,
            FinalAnswerModalData,
        )

        data = FinalAnswerModalData(
            answer_content=answer_content,
            vote_results=vote_results,
            agent_id=agent_id,
            model_name=model_name,
            post_eval_content=post_eval_content,
            post_eval_status=post_eval_status,
            changes=changes,
            context_paths=context_paths,
            workspace_path=workspace_path,
        )
        # Store for re-opening from the card's "View Full Answer" button
        self._last_final_answer_modal_data = data

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[ReviewResult] = loop.create_future()

        def show_modal():
            try:
                modal = FinalAnswerModal(data=data)

                def handle_result(result: ReviewResult) -> None:
                    # Only update review status when there were actual
                    # reviewed changes. Workspace-only and answer-only modal
                    # paths should not surface "changes approved/rejected".
                    if data.changes:
                        # This callback runs inside Textual's event loop, so
                        # we can safely access widgets here.
                        self._update_card_review_status(result)
                    try:
                        card = self._get_active_final_card()
                        if card is not None:
                            card.scroll_visible(animate=True, top=False)
                    except Exception:
                        logger.exception("[FinalAnswer] Failed to scroll final card into view")
                    if not result_future.done():
                        loop.call_soon_threadsafe(result_future.set_result, result)

                self._app.push_screen(modal, handle_result)
            except Exception as e:
                logger.exception(f"[FinalAnswer] Error showing modal: {e}")
                if not result_future.done():
                    loop.call_soon_threadsafe(
                        result_future.set_result,
                        ReviewResult(approved=False, metadata={"error": str(e)}),
                    )

        try:
            self._app.call_from_thread(show_modal)
        except Exception as e:
            logger.exception(f"[FinalAnswer] call_from_thread failed: {e}")
            return ReviewResult(approved=False, metadata={"error": str(e)})

        try:
            result = await asyncio.wait_for(result_future, timeout=300)
        except TimeoutError:
            logger.warning("[FinalAnswer] Modal timed out after 5 minutes")
            try:
                self._app.call_from_thread(self._app.pop_screen)
            except Exception:
                pass
            result = ReviewResult(approved=False, metadata={"error": "timeout"})

        # Store the result so re-opening from "View Full Answer" knows the action taken
        self._last_final_answer_result = result

        return result

    def _get_active_final_card(self) -> Optional["FinalPresentationCard"]:
        """Return the most relevant final card currently mounted."""
        card = getattr(self, "_final_presentation_card", None)
        if card is not None:
            return card

        if self._app is None:
            return None

        app_card = getattr(self._app, "_final_presentation_card", None)
        if app_card is not None:
            return app_card

        from .textual_widgets.content_sections import FinalPresentationCard

        try:
            cards = list(self._app.query(FinalPresentationCard))
            return cards[-1] if cards else None
        except Exception:
            return None

    def _apply_pending_review_status(self, card: Optional["FinalPresentationCard"]) -> None:
        """Apply a cached review status to the card and clear cache."""
        pending_status = getattr(self, "_pending_final_review_status", None)
        if card is None or not pending_status:
            return
        try:
            card.set_review_status(pending_status)
            self._pending_final_review_status = None
        except Exception:
            logger.exception("[FinalAnswer] Failed to apply pending review status")

    def _update_card_review_status(self, result: Optional["ReviewResult"] = None) -> None:
        """Update the FinalPresentationCard's review status indicator.

        Must be called from within Textual's event loop (e.g. from a
        push_screen callback or event handler).
        """
        if result is None:
            return

        status = "approved" if result.approved else "rejected"
        if getattr(self, "_pending_final_review_status", None) != status:
            self._pending_final_review_status = status

        card = self._get_active_final_card()
        if card is None:
            tui_log("[FinalAnswer] No final card available yet; caching review status")
            return

        self._apply_pending_review_status(card)

    def _dispatch_review_rework(self, rework_info: dict[str, Any]) -> None:
        """Dispatch a review rework by submitting feedback as a new question.

        Called after the orchestrator signals that the user wants to rework
        changes from the review modal instead of applying or rejecting them.
        Mirrors the _continue_planning_refinement pattern.

        Args:
            rework_info: Dict with keys: action, feedback, agent_id
        """
        if not self._app:
            return

        action = rework_info.get("action", "rework")
        feedback = (rework_info.get("feedback") or "").strip()

        if not feedback:
            try:
                self._app.call_from_thread(
                    lambda: self._app.notify(
                        "Cannot rework without feedback.",
                        severity="warning",
                        timeout=4,
                    ),
                )
            except Exception:
                pass
            return

        # Build rework prompt
        if action == "quick_fix":
            rework_prompt = f"Quick fix requested for the presented changes. " f"Apply the following feedback and re-present:\n\n{feedback}"
        else:
            rework_prompt = f"Rework requested for the presented changes. " f"Apply the following feedback and re-present:\n\n{feedback}"

        def submit_rework():
            try:
                mode_label = "Quick Fix" if action == "quick_fix" else "Rework"
                self._app.notify(
                    f"{mode_label}: re-running with feedback...",
                    severity="information",
                    timeout=3,
                )

                question_input = getattr(self._app, "question_input", None)
                if question_input:
                    question_input.disabled = True
                    question_input.value = rework_prompt

                    def do_submit():
                        try:
                            self._app._submit_question(rework_prompt)
                        finally:
                            if question_input:
                                question_input.disabled = False

                    self._app.call_later(do_submit)
                else:
                    self._app.call_later(lambda: self._app._submit_question(rework_prompt))
            except Exception as e:
                logger.exception(f"[ReviewRework] Error dispatching rework: {e}")

        try:
            self._app.call_from_thread(submit_rework)
        except Exception as e:
            logger.exception(f"[ReviewRework] call_from_thread failed: {e}")

    def _execute_approved_plan(
        self,
        approval: "PlanApprovalResult",
        mode_state: "TuiModeState",
        auto_submit: bool = True,
    ) -> None:
        """Finalize an approved plan and optionally auto-submit the first execute turn.

        Args:
            approval: PlanApprovalResult with plan data and path
            mode_state: TuiModeState instance to update
            auto_submit: When True, immediately starts first chunk execution.
        """
        from massgen.logger_config import get_log_session_root
        from massgen.plan_execution import (
            PlanValidationError,
            build_execution_prompt,
            initialize_chunk_execution_state,
        )
        from massgen.plan_storage import PlanStorage

        try:
            # Validate planning_started_turn is set
            if mode_state.planning_started_turn is None:
                # Recover by using current turn or defaulting to 0
                current_turn = 0
                if hasattr(self, "_current_turn"):
                    current_turn = self._current_turn or 0
                elif hasattr(self._app, "coordination_display"):
                    current_turn = getattr(self._app.coordination_display, "current_turn", 0)
                mode_state.planning_started_turn = current_turn
                logger.warning(
                    f"[PlanExecution] planning_started_turn was None, defaulting to {current_turn}",
                )

            storage = PlanStorage()
            session = mode_state.plan_session
            if session is None:
                log_dir = get_log_session_root()
                session = storage.create_plan(
                    log_dir.name,
                    str(log_dir),
                    planning_prompt=mode_state.last_planning_question,
                    planning_turn=mode_state.planning_started_turn,
                )
                mode_state.plan_session = session

            # Copy workspace to frozen - use the parent of plan_path as workspace source
            workspace_source = approval.plan_path.parent
            if approval.plan_data and approval.plan_path:
                try:
                    approval.plan_path.write_text(
                        json.dumps(approval.plan_data, indent=2),
                        encoding="utf-8",
                    )
                except Exception as write_err:
                    logger.warning(f"[PlanExecution] Failed to persist edited plan before finalize: {write_err}")
            # Use context paths captured during planning phase
            context_paths = mode_state.planning_context_paths or []
            storage.finalize_planning_phase(session, workspace_source, context_paths=context_paths)

            # Persist planning review metadata from iterative modal workflow.
            session_metadata = session.load_metadata()
            session_metadata.plan_revision = mode_state.plan_revision or 1
            session_metadata.planning_iteration_count = mode_state.planning_iteration_count or session_metadata.plan_revision
            session_metadata.planning_feedback_history = list(
                mode_state.planning_feedback_history or [],
            )
            session_metadata.last_planning_mode = mode_state.last_planning_mode
            session_metadata.execution_mode = "chunked_by_planner_v1"
            session.save_metadata(session_metadata)

            # Update mode state for execution
            mode_state.plan_mode = "execute"
            mode_state.plan_session = session
            mode_state.selected_plan_id = session.plan_id
            mode_state.pending_planning_feedback = None
            mode_state.pending_planning_mode = None

            # Validate chunk contract and initialize current chunk pointer.
            try:
                chunk_metadata = initialize_chunk_execution_state(session)
            except PlanValidationError as e:
                self._app.notify(
                    f"Plan validation failed: {e}",
                    severity="error",
                    timeout=6,
                )
                mode_state.reset_plan_state()
                if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                    self._app._mode_bar.set_plan_mode("normal")
                return

            # Update mode bar
            if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                self._app._mode_bar.set_plan_mode("execute")

            # Build execution prompt from original question
            original_question = mode_state.last_planning_question or "Execute the plan"
            execution_prompt = build_execution_prompt(
                original_question,
                active_chunk=chunk_metadata.current_chunk,
                chunk_order=chunk_metadata.chunk_order or [],
            )

            if hasattr(self, "question_input") and self.question_input:
                self.question_input.placeholder = "Press Enter to execute selected plan • or type instructions"

            if not auto_submit:
                self._app.notify(
                    "Plan finalized. Adjust mode bar options, then press Enter to execute.",
                    severity="information",
                    timeout=4,
                )
                return

            self._app.notify("Executing plan...", severity="information", timeout=3)

            # Submit execution prompt directly using _submit_question
            if hasattr(self._app, "_submit_question"):
                # Prevent duplicate submission by disabling input during auto-submit
                question_input = getattr(self._app, "question_input", None)
                if question_input:
                    # Disable to prevent user accidentally triggering duplicate submit
                    question_input.disabled = True
                    question_input.value = execution_prompt

                    def submit_and_reenable():
                        try:
                            self._app._submit_question(execution_prompt)
                        finally:
                            # Re-enable input after submission starts
                            # (actual processing lock handled by set_input_enabled)
                            if question_input:
                                question_input.disabled = False

                    self._app.call_later(submit_and_reenable)
                else:
                    # No input widget, just submit directly
                    self._app.call_later(lambda: self._app._submit_question(execution_prompt))
            else:
                logger.error("[PlanExecution] No _submit_question method found to execute plan")
                mode_state.reset_plan_state()

        except Exception as e:
            logger.exception(f"[PlanExecution] Failed to execute approved plan: {e}")
            self._app.notify(f"Failed to execute plan: {e}", severity="error")
            mode_state.reset_plan_state()
            if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                self._app._mode_bar.set_plan_mode("normal")

    def set_override_available(self, available: bool) -> None:
        """Set whether human override is available.

        Called by orchestrator after voting completes, before final presentation.

        Args:
            available: True if override is available, False otherwise.
        """
        if self._app and hasattr(self._app, "_mode_state"):
            self._app._mode_state.override_available = available
            if hasattr(self._app, "_mode_bar") and self._app._mode_bar:
                self._app._mode_bar.override_available = available


# Textual App Implementation
if TEXTUAL_AVAILABLE:
    from textual.binding import Binding

    def keyboard_action(func):
        """Decorator to skip action when keyboard is locked."""

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if self._keyboard_locked():
                return
            return func(self, *args, **kwargs)

        return wrapper

    class StatusBarEventsClicked(Message):
        """Message emitted when the events counter in StatusBar is clicked."""

    class StatusBarCancelClicked(Message):
        """Message emitted when the cancel button in StatusBar is clicked."""

    class StatusBarAnswerNowClicked(Message):
        """Message emitted when the Answer Now button in StatusBar is clicked."""

    class StatusBarCwdClicked(Message):
        """Message emitted when the CWD display in StatusBar is clicked."""

        def __init__(self, cwd: str, mode: str = "off") -> None:
            super().__init__()
            self.cwd = cwd
            self.mode = mode  # "off", "read", or "write"

    class StatusBarThemeClicked(Message):
        """Message emitted when the theme indicator in StatusBar is clicked."""

    class StatusBarContextClicked(Message):
        """Message emitted when the context paths indicator in StatusBar is clicked."""

    class StatusBarToolsClicked(Message):
        """Message emitted when the running/background tools indicator is clicked."""

    class StatusBar(Widget):
        """Persistent status bar showing orchestration state at the bottom of the TUI."""

        # CSS is in external theme files (dark.tcss/light.tcss)

        # Spinner frames for activity indicator
        SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        def __init__(self, agent_ids: list[str] | None = None):
            super().__init__(id="status_bar")
            self._vote_counts: dict[str, int] = {}
            self._vote_history: list[tuple[str, str, float]] = []  # (voter, voted_for, timestamp)
            self._current_phase = "idle"
            self._event_count = 0
            self._start_time: float | None = None
            self._timer_interval = None
            self._agent_ids = agent_ids or []
            self._last_leader: str | None = None
            # Activity indicator state
            self._working_agents: set[str] = set()
            self._spinner_frame = 0
            self._spinner_interval = None
            # Agent activity tracking for phase icons display
            self._agent_activities: dict[str, str] = {}  # agent_id -> activity type
            self._agent_letters: dict[str, str] = {}  # agent_id -> letter (A, B, C...)
            self._agent_order: list[str] = []  # ordered list of agent IDs
            # Per-agent answer and vote tracking
            self._agent_answer_counts: dict[str, int] = {}  # agent_id -> number of answers
            self._agent_votes_received: dict[str, int] = {}  # agent_id -> votes received for their answers
            # CWD context mode: "off", "read", or "write"
            self._cwd_context_mode = "off"
            self._timeout_states: dict[str, dict[str, Any]] = {}
            # Initialize vote counts to 0 for all agents and register agents
            for idx, agent_id in enumerate(self._agent_ids):
                self._vote_counts[agent_id] = 0
                # Auto-register agents with letters A, B, C, etc.
                letter = chr(ord("A") + idx) if idx < 26 else str(idx + 1)
                self._agent_letters[agent_id] = letter
                self._agent_order.append(agent_id)
                self._agent_activities[agent_id] = "idle"
                self._agent_answer_counts[agent_id] = 0
                self._agent_votes_received[agent_id] = 0

        def compose(self) -> ComposeResult:
            """Create the status bar layout with phase, activity, progress, tools, votes, events, MCP, CWD, cancel hint, and timer.

            Layout: [phase] [activity] [progress] [tools] [votes] --- spacer --- [mcp] [cwd] [events] [hints] [timer] [cancel]
            """
            # Left-aligned items
            # Viewer mode indicator (hidden by default, shown in viewer mode)
            yield Static("👁 VIEWER", id="status_viewer_mode", classes="hidden")
            yield Static("⏳ Idle", id="status_phase")
            yield Static("", id="status_activity", classes="activity-indicator hidden")  # Pulsing activity indicator
            yield Static("", id="status_progress")  # Progress summary: "3 agents | 2 answers | 4/6 votes"
            yield Static("", id="status_tools", classes="hidden clickable")
            yield Static("", id="status_votes")
            # Spacer to push right-side elements to the edge
            yield Static("", id="status_spacer")
            # Right-aligned items
            yield Static("", id="status_mcp")
            # Theme toggle indicator - clickable to toggle light/dark theme
            yield Static("[dim]D[/]", id="status_theme", classes="clickable")
            # CWD display - clickable to toggle auto-include as context
            cwd = Path.cwd()
            cwd_short = f"~/{cwd.name}" if len(str(cwd)) > 30 else str(cwd)
            yield Static(f"[dim]📁[/] {cwd_short}", id="status_cwd", classes="clickable")
            # Context paths - clickable to open context paths modal
            yield Static("[dim]CTX[/]", id="status_context", classes="clickable")
            yield Static("📋 0 events", id="status_events", classes="clickable")
            yield Static("[dim]?:help[/]", id="status_hints")  # Always visible, shows q:cancel during coordination
            yield Static("⏱️ 0:00", id="status_timer")
            yield Static("", id="status_answer_now", classes="answer-now-button hidden")
            yield Static("", id="status_cancel", classes="cancel-button hidden")

        def on_click(self, event: events.Click) -> None:
            """Handle click on the events counter, cancel button, or CWD."""
            # Textual uses event.widget, not event.target
            widget = getattr(event, "widget", None)
            if widget and hasattr(widget, "id"):
                if widget.id == "status_events":
                    self.post_message(StatusBarEventsClicked())
                elif widget.id == "status_answer_now":
                    self.post_message(StatusBarAnswerNowClicked())
                elif widget.id == "status_cancel":
                    self.post_message(StatusBarCancelClicked())
                elif widget.id == "status_tools":
                    self.post_message(StatusBarToolsClicked())
                elif widget.id == "status_cwd":
                    self.toggle_cwd_auto_include()
                elif widget.id == "status_theme":
                    self.post_message(StatusBarThemeClicked())
                elif widget.id == "status_context":
                    self.post_message(StatusBarContextClicked())

        def toggle_cwd_auto_include(self) -> None:
            """Cycle CWD context mode and update display."""
            # Cycle through modes
            modes = ["off", "read", "write"]
            current_idx = modes.index(self._cwd_context_mode)
            self._cwd_context_mode = modes[(current_idx + 1) % len(modes)]

            cwd = Path.cwd()
            cwd_short = f"~/{cwd.name}" if len(str(cwd)) > 30 else str(cwd)
            try:
                cwd_widget = self.query_one("#status_cwd", Static)
                if self._cwd_context_mode == "read":
                    cwd_widget.update(f"[green]📁 {cwd_short} \\[read][/]")
                elif self._cwd_context_mode == "write":
                    cwd_widget.update(f"[green]📁 {cwd_short} \\[read+write][/]")
                else:
                    cwd_widget.update(f"[dim]📁[/] {cwd_short}")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
            # Post message to notify app of the toggle
            self.post_message(StatusBarCwdClicked(str(cwd), self._cwd_context_mode))

        def update_phase(self, phase: str) -> None:
            """Update the phase indicator."""
            self._current_phase = phase
            # Map workflow phases to display
            phase_icons = {
                "idle": "⏳ Idle",
                "coordinating": "🔄 Coordinating",
                "initial_answer": "✏️ Answering",
                "enforcement": "🗳️ Voting",
                "presenting": "🎯 Presenting",
                "presentation": "🎯 Presenting",
            }
            display_text = phase_icons.get(phase, f"📋 {phase.title()}")

            try:
                phase_widget = self.query_one("#status_phase", Static)
                phase_widget.update(display_text)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

            # Update hints based on phase - always show ?:help, add q:cancel during coordination
            try:
                hints_widget = self.query_one("#status_hints", Static)
                if phase in ("idle",):
                    hints_widget.update("[dim]?:help[/]")
                else:
                    hints_widget.update("[dim]q:cancel • ?:help[/]")
                hints_widget.remove_class("hidden")  # Always visible
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

            # Update phase-based styling
            self.remove_class("phase-idle")
            self.remove_class("phase-initial")
            self.remove_class("phase-enforcement")
            self.remove_class("phase-presentation")
            if phase in ("initial_answer", "coordinating"):
                self.add_class("phase-initial")
            elif phase == "enforcement":
                self.add_class("phase-enforcement")
            elif phase in ("presenting", "presentation"):
                self.add_class("phase-presentation")
            else:
                self.add_class("phase-idle")

            self._update_answer_now_display()

        def update_mcp_status(self, server_count: int, tool_count: int) -> None:
            """Update MCP indicator in status bar."""
            try:
                mcp_widget = self.query_one("#status_mcp", Static)
                if server_count > 0:
                    mcp_widget.update(f"🔌 {server_count}s/{tool_count}t")
                else:
                    mcp_widget.update("")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def update_running_tools(self, count: int, background_count: int = 0) -> None:
            """Update running/background tools counter in status bar."""
            try:
                tools_widget = self.query_one("#status_tools", Static)
                if count > 0:
                    parts = [f"🔧 {count} running"]
                    if background_count > 0:
                        parts.append(f"⚙️ {background_count} bg")
                    tools_widget.update(" | ".join(parts))
                    tools_widget.remove_class("hidden")
                else:
                    tools_widget.update("")
                    tools_widget.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def update_progress(
            self,
            agent_count: int,
            answer_count: int,
            vote_count: int,
            expected_votes: int = 0,
            winner: str = "",
        ) -> None:
            """Update progress summary in status bar.

            Args:
                agent_count: Number of agents in the session
                answer_count: Number of answers received
                vote_count: Number of votes cast
                expected_votes: Total expected votes (for X/Y display)
                winner: If set, display winner celebration instead
            """
            try:
                progress_widget = self.query_one("#status_progress", Static)

                if winner:
                    text = f"🏆 [bold yellow]{winner[:12]} wins![/]"
                else:
                    parts = []
                    if agent_count > 0:
                        parts.append(f"{agent_count} agents")
                    if answer_count > 0:
                        parts.append(f"{answer_count} answers")
                    if expected_votes > 0:
                        parts.append(f"{vote_count}/{expected_votes} votes")
                    elif vote_count > 0:
                        parts.append(f"{vote_count} votes")
                    text = " | ".join(parts) if parts else ""

                progress_widget.update(text)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def add_vote(self, voted_for: str, voter: str = "") -> None:
            """Increment vote count for an agent and track history."""
            import time

            if voted_for not in self._vote_counts:
                self._vote_counts[voted_for] = 0
            self._vote_counts[voted_for] += 1
            self._vote_history.append((voter, voted_for, time.time()))
            # Also update per-agent votes received tracking
            if voted_for in self._agent_votes_received:
                self._agent_votes_received[voted_for] = self._vote_counts[voted_for]
            self._update_votes_display(animate=True)

        def update_votes(self, vote_counts: dict[str, int]) -> None:
            """Update all vote counts at once."""
            self._vote_counts = vote_counts.copy()
            self._update_votes_display()

        def _update_votes_display(self, animate: bool = False) -> None:
            """Update the votes display widget with leader highlighting."""
            if not self._vote_counts or all(v == 0 for v in self._vote_counts.values()):
                display_text = ""
                current_leader = None
            else:
                # Find the leader (max votes)
                max_votes = max(self._vote_counts.values())
                leaders = [aid for aid, count in self._vote_counts.items() if count == max_votes]
                current_leader = leaders[0] if len(leaders) == 1 else None  # No leader if tie

                # Format as "A:2 B:1" with leader highlighted
                parts = []
                for agent_id, count in sorted(self._vote_counts.items()):
                    if count > 0:
                        # Use first character or first 3 chars if agent ID is long
                        short_id = agent_id[0].upper() if len(agent_id) <= 3 else agent_id[:3]
                        if agent_id == current_leader:
                            # Highlight leader with crown
                            parts.append(f"[bold yellow]👑{short_id}:{count}[/]")
                        else:
                            parts.append(f"{short_id}:{count}")
                display_text = "🗳️ " + " ".join(parts) if parts else ""

            # Check if leader changed
            leader_changed = current_leader != self._last_leader and current_leader is not None
            self._last_leader = current_leader

            try:
                votes_widget = self.query_one("#status_votes", Static)
                votes_widget.update(display_text)

                # Trigger animation on vote update
                if animate:
                    votes_widget.add_class("vote-updated")
                    if leader_changed:
                        votes_widget.add_class("leader-changed")
                    # Remove animation classes after delay
                    self.set_timer(0.5, lambda: self._remove_vote_animation(votes_widget))
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def _remove_vote_animation(self, widget: Static) -> None:
            """Remove animation classes from vote widget."""
            try:
                widget.remove_class("vote-updated")
                widget.remove_class("leader-changed")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def get_standings_text(self) -> str:
            """Get current vote standings as text."""
            if not self._vote_counts or all(v == 0 for v in self._vote_counts.values()):
                return ""
            sorted_votes = sorted(self._vote_counts.items(), key=lambda x: -x[1])
            parts = [f"{aid[:8]}:{count}" for aid, count in sorted_votes if count > 0]
            return " | ".join(parts)

        def get_vote_history(self) -> list[tuple[str, str, float]]:
            """Get the vote history list."""
            return self._vote_history.copy()

        def celebrate_winner(self, winner: str) -> None:
            """Highlight winner when consensus is reached."""
            self.add_class("consensus-reached")
            # Remove after animation
            self.set_timer(3.0, lambda: self.remove_class("consensus-reached"))

        def add_event(self) -> None:
            """Increment the event counter."""
            self._event_count += 1
            self._update_events_display()

        def _update_events_display(self) -> None:
            """Update the events counter display."""
            display_text = f"📋 {self._event_count} events"
            try:
                events_widget = self.query_one("#status_events", Static)
                events_widget.update(display_text)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def start_timer(self) -> None:
            """Start the elapsed timer."""
            self._start_time = time.time()
            self._schedule_timer_update()

        def _schedule_timer_update(self) -> None:
            """Schedule the next timer update."""
            if self._start_time is not None:
                self._timer_interval = self.set_interval(1.0, self._update_timer)

        def _update_timer(self) -> None:
            """Update the timer display."""
            if self._start_time is None:
                return
            elapsed = time.time() - self._start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            display_text = f"⏱️ {minutes}:{seconds:02d}"
            try:
                timer_widget = self.query_one("#status_timer", Static)
                timer_widget.update(display_text)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        @staticmethod
        def _format_compact_duration(seconds: float | int | None) -> str:
            """Format a compact duration for status-bar labels."""
            if seconds is None:
                return "--:--"
            total_seconds = max(0, int(seconds))
            return f"{total_seconds // 60}:{total_seconds % 60:02d}"

        def set_timeout_state(self, agent_id: str, timeout_state: dict[str, Any]) -> None:
            """Store timeout state for Answer Now and wrap-up display."""
            self._timeout_states[agent_id] = dict(timeout_state)
            self._update_answer_now_display()

        def _update_answer_now_display(self) -> None:
            """Update the Answer Now control based on wrap-up state."""
            try:
                answer_widget = self.query_one("#status_answer_now", Static)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
                return

            is_execution_phase = self._current_phase not in ("idle", "presenting", "presentation")
            for class_name in ("wrapping-up", "blocked"):
                answer_widget.remove_class(class_name)

            active_states = [timeout_state for timeout_state in self._timeout_states.values() if timeout_state.get("active_timeout")]

            # Only expose the Answer Now control when at least one agent has a
            # soft timeout configured — otherwise the click is a no-op because
            # the orchestrator has no wrap-up hook to trigger.
            if not is_execution_phase or not active_states:
                answer_widget.add_class("hidden")
                return

            answer_widget.remove_class("hidden")

            wrapping_states = [timeout_state for timeout_state in active_states if timeout_state.get("soft_timeout_fired")]
            pending_states = [timeout_state for timeout_state in active_states if timeout_state.get("wrap_up_requested") and not timeout_state.get("soft_timeout_fired")]

            if any(timeout_state.get("is_hard_blocked") for timeout_state in wrapping_states):
                answer_widget.update("🚫 Blocked")
                answer_widget.add_class("blocked")
                return

            if wrapping_states:
                remaining_values = [timeout_state.get("remaining_hard") for timeout_state in wrapping_states if timeout_state.get("remaining_hard") is not None]
                remaining_text = ""
                if remaining_values:
                    remaining_text = f" {self._format_compact_duration(min(remaining_values))}"
                answer_widget.update(f"⚠ Wrapping up{remaining_text}")
                answer_widget.add_class("wrapping-up")
                return

            if pending_states:
                answer_widget.update("⚠ Wrap-up pending")
                answer_widget.add_class("wrapping-up")
                return

            answer_widget.update("⚡ Answer Now")

        def stop_timer(self) -> None:
            """Stop the timer updates."""
            if self._timer_interval:
                self._timer_interval.stop()
                self._timer_interval = None

        def reset(self) -> None:
            """Reset the status bar to initial state."""
            self._vote_counts = {agent_id: 0 for agent_id in self._agent_ids}
            self._event_count = 0
            self._start_time = None
            self._timeout_states = {}
            self.stop_timer()
            self.update_phase("idle")
            self._update_votes_display()
            self._update_events_display()
            try:
                timer_widget = self.query_one("#status_timer", Static)
                timer_widget.update("⏱️ 0:00")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def show_cancel_button(self, show: bool = True) -> None:
            """Show or hide the cancel button."""
            try:
                cancel_widget = self.query_one("#status_cancel", Static)
                if show:
                    cancel_widget.update("❌ Cancel")
                    cancel_widget.remove_class("hidden")
                else:
                    cancel_widget.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def show_restart_count(self, attempt: int, max_attempts: int) -> None:
            """Show restart count in the phase indicator."""
            try:
                phase_widget = self.query_one("#status_phase", Static)
                phase_widget.update(f"🔄 Restart {attempt}/{max_attempts}")
                phase_widget.add_class("restart-active")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def clear_restart_indicator(self) -> None:
            """Clear the restart indicator."""
            try:
                phase_widget = self.query_one("#status_phase", Static)
                phase_widget.remove_class("restart-active")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def set_agent_working(self, agent_id: str, working: bool = True) -> None:
            """Mark an agent as working or not working.

            Args:
                agent_id: The agent identifier
                working: True if agent is actively working, False if done
            """
            if working:
                self._working_agents.add(agent_id)
            else:
                self._working_agents.discard(agent_id)

            # Update activity indicator
            if self._working_agents:
                self._start_activity_spinner()
            else:
                self._stop_activity_spinner()

        def set_agent_activity(self, agent_id: str, activity: str) -> None:
            """Update agent activity type and refresh the activity display.

            Args:
                agent_id: The agent identifier
                activity: One of "idle", "thinking", "tool", "streaming", "voting", "waiting", "error"
            """
            if agent_id not in self._agent_letters:
                return  # Unknown agent

            self._agent_activities[agent_id] = activity

            # Start/stop spinner based on any active agents
            any_active = any(a != "idle" for a in self._agent_activities.values())
            if any_active and not self._spinner_interval:
                self._start_activity_spinner()
            elif not any_active and self._spinner_interval:
                self._stop_activity_spinner()
            else:
                # Just refresh the display without changing spinner state
                self._update_activity_display()

        def increment_agent_answer(self, agent_id: str) -> None:
            """Increment answer count for an agent."""
            if agent_id in self._agent_answer_counts:
                self._agent_answer_counts[agent_id] += 1

        def update_agent_votes_received(self, agent_id: str, votes: int) -> None:
            """Update the number of votes an agent has received."""
            if agent_id in self._agent_votes_received:
                self._agent_votes_received[agent_id] = votes

        def _start_activity_spinner(self) -> None:
            """Start the activity spinner animation."""
            if self._spinner_interval is not None:
                return  # Already running

            self._spinner_frame = 0
            self._update_activity_display()

            # Show the activity indicator
            try:
                activity_widget = self.query_one("#status_activity", Static)
                activity_widget.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Start animation interval (update every 100ms for smooth animation)
            self._spinner_interval = self.set_interval(0.1, self._animate_spinner)

        def _stop_activity_spinner(self) -> None:
            """Stop the activity spinner animation."""
            if self._spinner_interval:
                self._spinner_interval.stop()
                self._spinner_interval = None

            # Hide the activity indicator
            try:
                activity_widget = self.query_one("#status_activity", Static)
                activity_widget.add_class("hidden")
                activity_widget.update("")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _animate_spinner(self) -> None:
            """Animate the spinner to next frame."""
            self._spinner_frame = (self._spinner_frame + 1) % len(self.SPINNER_FRAMES)
            self._update_activity_display()

        def _update_activity_display(self) -> None:
            """Update the activity indicator display with phase icons per agent.

            Format: [A⠙💭] [B⠙🔧] [C ○]
            - Active agents show spinner + phase icon
            - Idle agents show hollow circle
            """
            # Activity icons mapping
            ACTIVITY_ICONS = {
                "idle": "○",
                "thinking": "💭",
                "tool": "🔧",
                "streaming": "✍️",
                "voting": "🗳️",
                "waiting": "⏳",
                "error": "⚠️",
            }

            parts = []
            spinner = self.SPINNER_FRAMES[self._spinner_frame]

            for agent_id in self._agent_order:
                letter = self._agent_letters.get(agent_id, "?")
                activity = self._agent_activities.get(agent_id, "idle")
                icon = ACTIVITY_ICONS.get(activity, "○")

                if activity == "idle":
                    parts.append(f"[{letter} {icon}]")
                else:
                    parts.append(f"[{letter}{spinner}{icon}]")

            display = " ".join(parts)

            # Check if any agent is active
            any_active = any(a != "idle" for a in self._agent_activities.values())

            try:
                activity_widget = self.query_one("#status_activity", Static)
                activity_widget.update(display)
                # Show/hide based on any activity
                if any_active:
                    activity_widget.remove_class("hidden")
                else:
                    activity_widget.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

    # BaseModal is now imported from .textual package

    class TextualApp(App):
        """Main Textual application for MassGen coordination."""

        THEMES_DIR = Path(__file__).parent / "textual_themes"
        PALETTES_DIR = THEMES_DIR / "palettes"
        CSS_PATH = str(THEMES_DIR / "dark.tcss")  # Legacy - now using combined CSS

        # Map theme names to palette files
        # Core themes cycle via Ctrl+Shift+T; others available via config only
        PALETTE_MAP = {
            "dark": "_dark.tcss",
            "light": "_light.tcss",
            "catppuccin_mocha": "_catppuccin_mocha.tcss",
            "catppuccin_latte": "_catppuccin_latte.tcss",
        }

        # Themes that cycle with Ctrl+Shift+T
        CORE_THEMES = ["dark", "light"]

        # Custom Textual themes with proper color palettes
        # These are registered at app startup and provide consistent styling
        CUSTOM_THEMES = {
            "dark": Theme(
                name="massgen-dark",
                primary="#58a6ff",  # Blue
                secondary="#a371f7",  # Purple
                accent="#f0883e",  # Orange
                foreground="#e6edf3",  # Light text
                background="#0d1117",  # Dark bg
                surface="#161b22",  # Elevated surface
                panel="#21262d",  # Panel bg
                success="#3fb950",
                warning="#d29922",
                error="#f85149",
                dark=True,
            ),
            "light": Theme(
                name="massgen-light",
                primary="#0969da",  # Strong blue
                secondary="#8250df",  # Purple
                accent="#bf8700",  # Amber
                foreground="#1f2328",  # Dark text (high contrast)
                background="#ffffff",  # White bg
                surface="#f6f8fa",  # Light gray surface
                panel="#ffffff",  # White panel
                success="#1a7f37",  # Dark green (readable)
                warning="#9a6700",  # Dark amber
                error="#cf222e",  # Dark red
                dark=False,
            ),
        }

        # Map internal theme names to Textual registered theme names
        THEME_NAME_MAP = {
            "dark": "massgen-dark",
            "light": "massgen-light",
        }

        # Cache for combined CSS files
        _combined_css_cache: dict[str, Path] = {}

        @classmethod
        def _get_combined_css_path(cls, theme: str) -> Path:
            """Get path to combined CSS (palette + base) for a theme.

            Textual CSS variables must be defined before they're used, so we
            concatenate the palette file (which defines variables like $bg-base)
            with the base file (which uses those variables).

            Args:
                theme: Theme name (e.g., "dark", "light")

            Returns:
                Path to the combined CSS file
            """
            # Get palette file for this theme
            palette_file = cls.PALETTE_MAP.get(theme, "_dark.tcss")
            palette_path = cls.PALETTES_DIR / palette_file
            base_path = cls.THEMES_DIR / "base.tcss"

            # Create combined CSS in a cache directory
            import hashlib
            import tempfile

            cache_dir = Path(tempfile.gettempdir()) / "massgen_themes"
            cache_dir.mkdir(exist_ok=True)

            # Read and concatenate files
            palette_css = palette_path.read_text() if palette_path.exists() else ""
            base_css = base_path.read_text() if base_path.exists() else ""

            # Import modal base CSS (shared styles for all modal dialogs)
            from .textual.widgets.modal_base import MODAL_BASE_CSS

            # Split palette into variables and component overrides
            # Variables must come first, but component overrides should come last
            palette_lines = palette_css.split("\n")
            palette_vars = []
            palette_overrides = []
            in_overrides = False
            for line in palette_lines:
                if "Component Overrides" in line:
                    in_overrides = True
                if in_overrides:
                    palette_overrides.append(line)
                else:
                    palette_vars.append(line)

            # Order: palette vars → modal base CSS → base.tcss → palette overrides
            combined_css = f"/* Combined theme: {theme} */\n"
            combined_css += f"/* Palette variables from: {palette_file} */\n\n"
            combined_css += "\n".join(palette_vars)
            combined_css += "\n\n/* Modal base styles */\n\n"
            combined_css += MODAL_BASE_CSS
            combined_css += "\n\n/* Base component styles */\n\n"
            combined_css += base_css
            if palette_overrides:
                combined_css += "\n\n/* Theme-specific component overrides */\n\n"
                combined_css += "\n".join(palette_overrides)

            # Use a content hash in the filename so stale cached files are never reused.
            # This avoids mismatches when the CSS assembly logic changes across runs.
            css_hash = hashlib.sha256(combined_css.encode("utf-8")).hexdigest()[:12]
            combined_path = cache_dir / f"{theme}_combined_{css_hash}.tcss"

            if not combined_path.exists():
                combined_path.write_text(combined_css)

            cls._combined_css_cache[theme] = combined_path

            # Best-effort cleanup of stale combined CSS files for this theme.
            for stale_path in cache_dir.glob(f"{theme}_combined*.tcss"):
                if stale_path != combined_path:
                    try:
                        stale_path.unlink()
                    except OSError:
                        pass

            return combined_path

        # Minimal bindings - most features accessed via /slash commands
        # Only canonical shortcuts that users expect
        BINDINGS = [
            # Agent navigation
            Binding("f", "go_to_winner", "Go to Winner", show=False),
            Binding("tab", "next_agent", "Next Agent"),
            Binding("left", "prev_agent", "Prev Agent", show=False),
            Binding("right", "next_agent", "Next Agent", show=False),
            # Quit - Ctrl+D quits directly
            Binding("ctrl+d", "quit", "Quit", show=False),
            # Ctrl+C - context-aware: clear input / cancel turn, double to quit
            Binding("ctrl+c", "handle_ctrl_c", "Cancel/Quit", show=False),
            # CWD context toggle - priority so it works even when input focused
            Binding("ctrl+p", "toggle_cwd", "Toggle CWD", priority=True, show=False),
            # Subagent quick access
            Binding("ctrl+u", "show_subagents", "Subagents", priority=True, show=False),
            Binding("b", "open_background_tools", "Background Jobs", show=False),
            # Help - Ctrl+G for guide/help
            Binding("ctrl+g", "show_help", "Help", priority=True, show=False),
            # Mode toggles
            Binding("shift+tab", "toggle_plan_mode", "Mode Cycle", priority=True),
            Binding("ctrl+o", "trigger_override", "Override", priority=True, show=False),
            # Task plan toggle
            Binding("ctrl+t", "toggle_task_plan", "Toggle Tasks", priority=True, show=False),
            # Runtime injection target toggle: all agents <-> current agent
            Binding("ctrl+shift+i", "toggle_human_input_target", "Inject Target", priority=True, show=False),
            # Theme toggle
            Binding("ctrl+shift+t", "toggle_theme", "Theme", priority=True, show=False),
            # Copy mode - releases the mouse so the user can drag-select text
            Binding(COPY_MODE_BINDING, "toggle_copy_mode", "Copy Mode", priority=True, show=False),
            # Evaluation criteria viewer
            Binding("ctrl+e", "show_evaluation_criteria", "Criteria", priority=True, show=False),
        ]

        def __init__(
            self,
            display: TextualTerminalDisplay,
            question: str,
            buffers: dict[str, list],
            buffer_lock: threading.Lock,
            buffer_flush_interval: float,
        ):
            # Build combined CSS from palette + base
            # Textual CSS variables must be defined before use, so we concatenate
            # the palette (variables) with the base (component styles)
            # Load user settings for theme preference
            user_settings = get_user_settings()
            theme = user_settings.theme
            if theme not in self.PALETTE_MAP:
                theme = "dark"
            combined_css_path = self._get_combined_css_path(theme)
            super().__init__(css_path=str(combined_css_path))
            self.coordination_display = display
            self.question = question
            self._buffers = buffers
            self._buffer_lock = buffer_lock
            self.buffer_flush_interval = buffer_flush_interval
            self._keyboard_interactive_mode = display._keyboard_interactive_mode
            self._timing_debug = tui_debug_enabled() and os.environ.get("MASSGEN_TUI_TIMING_DEBUG", "").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            self._heartbeat_timer = None
            self._last_heartbeat_at: float | None = None
            self._stall_watchdog_thread: threading.Thread | None = None
            self._stall_watchdog_stop = threading.Event()
            self._last_stall_dump_at: float = 0.0
            try:
                self._stall_watchdog_threshold_s = float(os.environ.get("MASSGEN_TUI_STALL_THRESHOLD_S", "0.8"))
            except ValueError:
                self._stall_watchdog_threshold_s = 0.8

            self.agent_widgets = {}
            self.header_widget = None
            self.footer_widget = None
            self.post_eval_panel = None
            self.final_stream_panel = None
            self.safe_indicator = None
            self._tab_bar: AgentTabBar | None = None
            self._status_ribbon: AgentStatusRibbon | None = None
            self._consensus_map: ConsensusMap | None = None
            self._consensus_map_state = ConsensusMapState(
                self.coordination_display.agent_ids,
                getattr(self.coordination_display, "agent_models", {}),
            )
            self._execution_status_line: ExecutionStatusLine | None = None
            # Side panel removed - using separate SubagentScreen
            # self._subagent_side_panel: Optional[Container] = None
            # self._subagent_view: Optional[SubagentView] = None
            self._active_agent_id: str | None = None
            self._winner_agent_id: str | None = None
            # Final presentation state (streams into winner's AgentPanel)
            self._final_presentation_agent: str | None = None
            self._final_presentation_card: FinalPresentationCard | None = None
            self._pending_final_review_status: str | None = None
            self._welcome_screen: Optional["WelcomeScreen"] = None
            self._status_bar: Optional["StatusBar"] = None
            # Show welcome if no real question (detect placeholder strings)
            # Viewer mode skips welcome — always go straight to agent panels
            self._viewer_mode = display.viewer_mode
            is_placeholder = not question or question.lower().startswith("welcome")
            self._showing_welcome = is_placeholder and not self._viewer_mode
            self.current_agent_index = 0
            self._pending_flush = False
            self._resize_debounce_handle = None
            self._thread_id: int | None = None
            self._orchestrator_events: list[str] = []
            self._input_handler: Callable[[str], None] | None = None

            # Event-driven pipeline state
            self._event_adapters: dict[str, TimelineEventAdapter] = {}
            # Event batching: accumulate events for ~16ms before marshaling
            self._event_batch: Deque = deque()
            self._event_batch_lock = threading.Lock()
            self._event_batch_timer: threading.Timer | None = None
            self._EVENT_BATCH_INTERVAL = 0.016  # 16ms (~60fps)

            # Answer tracking for browser modal
            self._answers: list[dict[str, Any]] = []  # All answers with metadata
            self._votes: list[dict[str, Any]] = []  # All votes with metadata
            self._winner_agent_id: str | None = None  # Winner when consensus reached

            # Conversation history tracking
            self._conversation_history: list[dict[str, Any]] = []  # {question, answer, turn, timestamp}
            self._current_question: str = ""  # Track the current question

            # Restart and context tracking
            self._restart_history: list[dict[str, Any]] = []  # Track all restarts
            self._current_restart: dict[str, Any] = {}  # Current restart info
            self._context_per_agent: dict[str, list[str]] = {}  # Which answers each agent has seen

            # CWD context mode: "off", "read", or "write"
            self._cwd_context_mode: str = self._normalize_cwd_context_mode(
                getattr(self.coordination_display, "default_cwd_context_mode", "off"),
            )

            # Timer for updating execution status bar with spinner animation
            self._execution_status_timer = None

            # Agent pulsing animation state
            self._pulsing_agents: set = set()  # Set of agent_ids currently pulsing
            self._pulse_frame: int = 0
            self._pulse_timer = None

            # Human input during execution state
            self._queued_human_input: str | None = None
            self._human_input_hook = None  # Set by orchestrator via set_human_input_hook()
            self._subagent_message_callback = None  # Set by orchestrator via set_subagent_message_callback()
            self._subagent_continue_callback = None  # Set by orchestrator via set_subagent_continue_callback()
            self._answer_now_callback = None
            self._queued_input_banner: QueuedInputBanner | None = None
            self._queued_input_region: Container | None = None
            self._queued_input_row: Horizontal | None = None
            self._queued_input_actions: Horizontal | None = None
            self._input_header: Vertical | None = None
            self._question_input_row: Container | None = None
            self._queue_cancel_latest_button: Button | None = None
            self._queue_clear_button: Button | None = None
            self._human_input_target_mode: str = "all"  # "all" | "current"
            self._queued_human_input_pending_by_agent: dict[str, int] = {}
            self._inject_target_button: Button | None = None
            self._skip_queued_fallback_once_after_restart: bool = False

            # TUI Mode State (plan mode, agent mode, refinement mode, override)
            self._mode_state = TuiModeState()
            requested_default_plan_mode = getattr(self.coordination_display, "default_plan_mode", "normal")
            if requested_default_plan_mode in {"plan", "spec"}:
                # Seed mode state immediately so first submitted turn uses
                # the requested planning/spec workflow even before first repaint.
                self._mode_state.plan_mode = requested_default_plan_mode
            self._mode_state.analysis_config.include_previous_session_skills = bool(
                self.coordination_display.default_load_previous_session_skills,
            )
            lifecycle_mode = str(self.coordination_display.default_skill_lifecycle_mode).strip().lower()
            if lifecycle_mode not in {"create_new", "create_or_update"}:
                lifecycle_mode = "create_or_update"
            self._mode_state.analysis_config.skill_lifecycle_mode = lifecycle_mode
            if self.coordination_display.default_coordination_mode == "decomposition":
                self._mode_state.coordination_mode = "decomposition"

            # Apply CLI mode defaults (--single-agent, --quick, --personas, --coordination-mode)
            if self.coordination_display.default_agent_mode == "single":
                self._mode_state.agent_mode = "single"
                if self.coordination_display.default_selected_agent:
                    self._mode_state.selected_single_agent = self.coordination_display.default_selected_agent
                elif self.coordination_display.agent_ids:
                    self._mode_state.selected_single_agent = self.coordination_display.agent_ids[0]
            if not self.coordination_display.default_refinement_enabled:
                self._mode_state.refinement_enabled = False
            if self.coordination_display.default_personas_enabled:
                self._mode_state.parallel_personas_enabled = True
                self._mode_state.persona_diversity_mode = self.coordination_display.default_persona_diversity_mode

            self._mode_bar: ModeBar | None = None

            # Runtime decomposition generation UI state
            self._decomposition_generation_modal: DecompositionGenerationModal | None = None
            self._runtime_decomposition_subtasks: dict[str, str] = {}
            self._runtime_parallel_personas: dict[str, str] = {}
            self._runtime_evaluation_criteria: list[dict] | None = None
            self._runtime_evaluation_criteria_source: str = "default"
            self._decomposition_completion_source: str = "subagent"
            self._precollab_subagents: dict[str, _PrecollabSubagentState] = {}
            self._parallel_precollab_expected: set[str] = set()
            self._parallel_precollab_screen_opened: bool = False
            # Workspace browser open-guard to prevent duplicate modal pushes from
            # repeated click/key events while the UI is busy.
            self._workspace_browser_open_pending: bool = False
            self._workspace_browser_last_request_at: float = 0.0
            # Performance guard: suppress expensive hover style updates while the
            # timeline is answer-locked (buttons remain clickable).
            self._hover_updates_suppressed: bool = False

            if not self._keyboard_interactive_mode:
                self.BINDINGS = []

        def _keyboard_locked(self) -> bool:
            """Return True when keyboard input should be ignored.

            Keyboard is locked when:
            - safe_keyboard_mode is True (during sensitive operations)
            - _keyboard_interactive_mode is False (non-interactive)
            - execution is in progress (mode_state.is_locked())
            """
            if self.coordination_display.safe_keyboard_mode:
                return True
            if not self._keyboard_interactive_mode:
                return True
            # Block mode-changing keyboard shortcuts during execution
            if hasattr(self, "_mode_state") and self._mode_state.is_locked():
                return True
            return False

        def reset_turn_state(self) -> None:
            """Reset turn-level state for a new turn.

            Clears answer/vote tracking, winner state, context tracking,
            and UI state that should not persist between turns.
            """
            # Answer/voting state - clear for new turn
            self._answers.clear()
            self._votes.clear()
            self._winner_agent_id = None
            self._current_question = ""

            # Restart tracking - keep history but clear current
            self._current_restart = {}

            # Context tracking - agents start fresh for new turn
            self._context_per_agent.clear()

            # Orchestrator events - clear event log for new turn
            self._orchestrator_events.clear()

            # Human input queue - clear any stale queued input
            self._queued_human_input = None
            self._queued_human_input_pending_by_agent = {}
            self._skip_queued_fallback_once_after_restart = False
            if self._queued_input_banner:
                self._queued_input_banner.clear()
            if self._queued_input_region:
                self._queued_input_region.remove_class("visible")
            if self._tab_bar:
                self._tab_bar.set_pending_injection_counts({})

            # Agent pulsing - stop all pulse animations
            self._pulsing_agents.clear()

            # Final presentation state - clear winner's presentation
            self._final_presentation_agent = None
            self._final_presentation_card = None
            self._pending_final_review_status = None

            # Decomposition generation modal/runtime state
            self._runtime_decomposition_subtasks = {}
            self._runtime_parallel_personas = {}
            self._dismiss_decomposition_generation_modal()
            self._precollab_subagents.clear()
            self._parallel_precollab_expected = set()
            self._parallel_precollab_screen_opened = False

            if self._tab_bar and self._mode_state.coordination_mode == "parallel":
                if self._mode_state.parallel_personas_enabled:
                    self._tab_bar.set_agent_personas({})
                else:
                    self._tab_bar.set_agent_subtasks({})

            # Ensure status-bar tool indicators reset between turns.
            self._update_running_tools_count()

            if hasattr(self, "_consensus_map_state"):
                self._consensus_map_state.reset_turn(
                    self.coordination_display.agent_ids,
                    getattr(self.coordination_display, "agent_models", {}),
                )
                self._refresh_consensus_map()

        def _refresh_consensus_map(self) -> None:
            """Refresh the compact consensus map from current state."""
            if not getattr(self, "_consensus_map", None):
                return
            try:
                self._consensus_map.set_state(self._consensus_map_state.snapshot())
                if self._showing_welcome:
                    self._consensus_map.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] consensus map refresh failed: {e}")

        def _apply_consensus_event(self, event) -> None:
            """Apply a structured event to the compact consensus map."""
            if not hasattr(self, "_consensus_map_state"):
                return
            try:
                self._consensus_map_state.apply_event(event)
                self._refresh_consensus_map()
            except Exception as e:
                tui_log(f"[TextualDisplay] consensus map event failed: {e}")

        def _record_consensus_tool_complete(self, agent_id: str, tool_data: Any, round_number: int = 1) -> None:
            """Fallback: update consensus state from completed workflow tool cards."""
            tool_name = str(getattr(tool_data, "tool_name", "") or "").lower()
            if "new_answer" not in tool_name and "vote" not in tool_name:
                return

            from massgen.events import EventType, MassGenEvent

            if "new_answer" in tool_name:
                self._apply_consensus_event(
                    MassGenEvent.create(
                        EventType.ANSWER_SUBMITTED,
                        agent_id=agent_id,
                        round_number=round_number,
                        answer_number=1,
                    ),
                )
                return

            target_id = ""
            args_full = getattr(tool_data, "args_full", None)
            if isinstance(args_full, str) and args_full.strip():
                import ast
                import json

                for parser in (json.loads, ast.literal_eval):
                    try:
                        parsed = parser(args_full)
                    except Exception:
                        continue
                    if isinstance(parsed, dict):
                        target_id = str(parsed.get("agent_id") or parsed.get("target_id") or "")
                        break
            if target_id:
                self._apply_consensus_event(
                    MassGenEvent.create(
                        EventType.VOTE,
                        agent_id=agent_id,
                        round_number=round_number,
                        target_id=target_id,
                    ),
                )

        # Provider/model slug tables extracted to _textual_provider_model.
        # Kept as class-level aliases for any external attribute reads.
        _BACKEND_PROVIDER_SLUGS = _provider_model._BACKEND_PROVIDER_SLUGS
        _PROVIDER_NAME_SLUGS = _provider_model._PROVIDER_NAME_SLUGS
        _MODEL_PREFIX_PROVIDER_SLUGS = _provider_model._MODEL_PREFIX_PROVIDER_SLUGS

        def _normalize_provider_slug(self, provider_hint: str | None) -> str | None:
            """Normalize a backend/provider hint into a canonical slug (delegates)."""
            return _provider_model.normalize_provider_slug(provider_hint)

        def _infer_provider_slug_from_model(self, model_name: str) -> str | None:
            """Infer provider slug from common model naming prefixes (delegates)."""
            return _provider_model.infer_provider_slug_from_model(model_name)

        def _to_provider_model(self, model_name: str, provider_hint: str | None) -> str:
            """Format model names as provider/model for startup display (delegates)."""
            return _provider_model.to_provider_model(model_name, provider_hint)

        def _build_welcome_agents_info(self) -> list[dict[str, str]]:
            """Build welcome-screen agent metadata with provider/model display names."""
            agent_models = getattr(self.coordination_display, "agent_models", {}) or {}
            provider_hints: dict[str, str] = {}

            orchestrator = getattr(self.coordination_display, "orchestrator", None)
            orchestrator_agents = getattr(orchestrator, "agents", {}) if orchestrator else {}
            for agent_id, agent in orchestrator_agents.items():
                backend = getattr(agent, "backend", None)
                if backend is None:
                    continue

                backend_type = getattr(backend, "backend_type", None)
                if isinstance(backend_type, str) and backend_type.strip():
                    provider_hints[agent_id] = backend_type
                    continue

                provider_name = None
                get_provider_name = getattr(backend, "get_provider_name", None)
                if callable(get_provider_name):
                    try:
                        provider_name = get_provider_name()
                    except Exception:
                        provider_name = None
                if provider_name:
                    provider_hints[agent_id] = str(provider_name)

            return _provider_model.build_welcome_agents_info(
                self.coordination_display.agent_ids,
                agent_models,
                provider_hints,
            )

        def compose(self) -> ComposeResult:
            """Compose the UI layout with adaptive agent arrangement."""
            len(self.coordination_display.agent_ids)
            agents_info_list = self._build_welcome_agents_info()

            turn = getattr(self.coordination_display, "current_turn", 1)
            agent_ids = self.coordination_display.agent_ids

            # Header removed - session info now in tab bar (right side)

            # === BOTTOM DOCKED WIDGETS (yield order: last yielded = very bottom) ===
            # Input area container - dock: bottom
            with Container(id="input_area"):
                # Copy mode banner (hidden by default; Ctrl+Shift+S toggles)
                yield CopyModeBanner(id="copy_mode_banner")
                # Runtime injection queue strip above mode/status rows.
                with Vertical(id="queued_input_region") as queued_input_region:
                    self._queued_input_region = queued_input_region
                    with Horizontal(id="queued_input_row") as queued_input_row:
                        self._queued_input_row = queued_input_row
                        self._queued_input_banner = QueuedInputBanner(id="queued_input_banner")
                        yield self._queued_input_banner
                        with Horizontal(id="queued_input_actions") as queued_input_actions:
                            self._queued_input_actions = queued_input_actions
                            self._queue_cancel_latest_button = Button("Cancel latest", id="queue_cancel_latest_button")
                            yield self._queue_cancel_latest_button
                            self._queue_clear_button = Button("Clear queue", id="queue_clear_button")
                            yield self._queue_clear_button

                # Input header with mode controls and compact vim/help hints.
                with Vertical(id="input_header") as input_header:
                    self._input_header = input_header
                    with Horizontal(id="input_modes_row"):
                        # Mode bar - toggles for plan/agent/refinement modes
                        self._mode_bar = ModeBar(id="mode_bar")
                        yield self._mode_bar

                        # Right-side status panel: Vim status + CWD/context line.
                        with Vertical(id="input_meta_panel"):
                            with Horizontal(id="input_meta_primary"):
                                self._vim_indicator = Static("", id="vim_indicator")
                                yield self._vim_indicator
                            self._input_hint = Static("", id="input_hint")
                            yield self._input_hint

                # Execution bar - shown ONLY during coordination, replaces input
                # Contains status text (left) and cancel button (right)
                with Horizontal(id="execution_bar"):
                    # Status text on left - shows agent activity icons
                    self._execution_status = Static("Working...", id="execution_status")
                    yield self._execution_status
                    # Spacer to push cancel button to right
                    yield Static("", id="execution_spacer")
                    # Cancel button - on right
                    self._cancel_button = Button("Cancel [q]", id="turn_cancel_button", variant="error")
                    yield self._cancel_button

                # Multi-line input: Enter to submit, Shift+Enter for new line
                # Type @ to trigger path autocomplete
                # Hint text is now part of placeholder (frees up space on input header row)
                with Container(id="question_input_row") as question_input_row:
                    self._question_input_row = question_input_row
                    self.question_input = MultiLineInput(
                        placeholder="Enter to submit • Shift+Enter for newline • @ for files • Ctrl+G help",
                        id="question_input",
                    )
                    yield self.question_input
                    self._inject_target_button = Button("Inject: all", id="inject_target_button")
                    yield self._inject_target_button

            # Footer - dock: bottom (Textual built-in)
            self.footer_widget = Footer()
            yield self.footer_widget

            # Status bar - dock: bottom, yielded LAST so it's at very bottom
            self._status_bar = StatusBar(agent_ids=agent_ids)
            yield self._status_bar

            # === CONTENT WIDGETS (fill remaining space, in visual order top-to-bottom) ===
            # Tab bar for agent switching (flows below header, hidden during welcome)
            # NOTE: No dock:top - just flows naturally after docked widgets
            agent_models = getattr(self.coordination_display, "agent_models", {})
            self._tab_bar = AgentTabBar(
                agent_ids,
                agent_models=agent_models,
                turn=turn,
                question=self.question,
                id="agent_tab_bar",
            )
            if self._showing_welcome:
                self._tab_bar.add_class("hidden")
            yield self._tab_bar

            # Agent status ribbon - shows round, activity, timeout, tasks, tokens, cost
            initial_agent = agent_ids[0] if agent_ids else ""
            self._status_ribbon = AgentStatusRibbon(agent_id=initial_agent, id="agent_status_ribbon")
            if self._showing_welcome:
                self._status_ribbon.add_class("hidden")
            yield self._status_ribbon

            self._consensus_map = ConsensusMap(id="consensus_map")
            self._refresh_consensus_map()
            if self._showing_welcome:
                self._consensus_map.add_class("hidden")
            yield self._consensus_map

            # Set initial active agent
            self._active_agent_id = agent_ids[0] if agent_ids else None

            # Welcome screen (shown initially, hidden when session starts)
            self._welcome_screen = WelcomeScreen(agents_info_list)
            if not self._showing_welcome:
                self._welcome_screen.add_class("hidden")
            yield self._welcome_screen

            # Main container with agent panels (hidden during welcome)
            with Container(id="main_container", classes="hidden" if self._showing_welcome else ""):
                with Horizontal(id="main_split"):
                    with Container(id="agents_container"):
                        for idx, agent_id in enumerate(agent_ids):
                            # Only first agent is visible, rest are hidden
                            is_hidden = idx > 0
                            agent_widget = AgentPanel(agent_id, self.coordination_display, idx + 1)
                            if is_hidden:
                                agent_widget.add_class("hidden")
                            self.agent_widgets[agent_id] = agent_widget
                            yield agent_widget

                    # Subagent side panel removed - now using separate SubagentScreen
                    # self._subagent_side_panel = Container(id="subagent_side_panel", classes="hidden")
                    # yield self._subagent_side_panel

                # Phase 13.2: Execution status line - shows all agents' states at a glance
                # Placed at bottom of main content area, above mode bar
                self._execution_status_line = ExecutionStatusLine(
                    agent_ids=agent_ids,
                    focused_agent=initial_agent,
                    id="execution_status_line",
                )
                yield self._execution_status_line

            self.post_eval_panel = PostEvaluationPanel()
            yield self.post_eval_panel

            # FinalStreamPanel is deprecated - final answer now streams into winner's AgentPanel
            # Keep the instance but don't yield it (hidden)
            self.final_stream_panel = FinalStreamPanel(coordination_display=self.coordination_display)
            # yield self.final_stream_panel  # Hidden - using FinalPresentationCard in AgentPanel instead

            self.safe_indicator = Label("", id="safe_indicator")
            yield self.safe_indicator

            # Path autocomplete dropdown (hidden by default, floats above input area)
            self._path_dropdown = PathSuggestionDropdown(id="path_dropdown")
            yield self._path_dropdown

            # Plan options popover (hidden by default, shows when settings button clicked)
            self._plan_options_popover = PlanOptionsPopover(id="plan_options_popover")
            yield self._plan_options_popover

        def _get_layout_class(self, num_agents: int) -> str:
            """Return CSS class for adaptive layout based on agent count."""
            if num_agents == 1:
                return "single-agent"
            elif num_agents == 2:
                return "two-agents"
            elif num_agents == 3:
                return "three-agents"
            else:
                return "many-agents"

        async def on_mount(self):
            """Set up periodic buffer flushing when app starts."""
            # Register custom themes for proper color palette support
            for theme in self.CUSTOM_THEMES.values():
                self.register_theme(theme)

            # Set initial theme based on coordination_display.theme
            initial_theme = self.coordination_display.theme
            if initial_theme in self.THEME_NAME_MAP:
                self.theme = self.THEME_NAME_MAP[initial_theme]
            # Set initial theme class for CSS-based theme switching
            if initial_theme == "light":
                self.add_class("theme-light")
            else:
                self.add_class("theme-dark")
            # Apply saved vim mode preference
            try:
                user_settings = get_user_settings()
                if self.question_input:
                    self.question_input.vim_mode = user_settings.vim_mode
                    self._update_vim_indicator(None if not user_settings.vim_mode else False)
            except Exception:
                pass
            self._update_human_input_target_button()

            self._thread_id = threading.get_ident()
            self.coordination_display._app_ready.set()

            # In viewer mode, start the EventFeeder instead of the in-process listener
            if self._viewer_mode and self.coordination_display._viewer_event_feeder:
                feeder = self.coordination_display._viewer_event_feeder
                feeder._event_callback = self._handle_event_from_emitter
                feeder.start()
            else:
                self._register_event_listener()
            self.set_interval(self.buffer_flush_interval, self._flush_buffers)
            if self._timing_debug:
                self._last_heartbeat_at = time.monotonic()
                self._heartbeat_timer = self.set_interval(0.05, self._heartbeat_tick)
                self._start_stall_watchdog()
            if self.coordination_display.restart_reason and self.header_widget:
                self.header_widget.show_restart_context(
                    self.coordination_display.restart_reason,
                    self.coordination_display.restart_instructions or "",
                )
            self._update_safe_indicator()
            self._update_theme_indicator()
            self._set_cwd_context_mode(self._cwd_context_mode, notify=False)
            self._refresh_welcome_context_hint()
            if self._mode_bar:
                self._mode_bar.set_agent_mode(self._mode_state.agent_mode)
                self._mode_bar.set_refinement_mode(self._mode_state.refinement_enabled)
                self._mode_bar.set_coordination_mode(self._mode_state.coordination_mode)
                self._mode_bar.set_coordination_enabled(self._mode_state.agent_mode != "single")
                self._mode_bar.set_parallel_personas_enabled(self._mode_state.parallel_personas_enabled, self._mode_state.persona_diversity_mode)
            default_plan_mode = getattr(self.coordination_display, "default_plan_mode", "normal")
            if default_plan_mode != "normal":
                self.call_after_refresh(
                    lambda mode=default_plan_mode: self._handle_plan_mode_change(mode),
                )
            self._refresh_skills_button_state()
            self._refresh_input_modes_row_layout()
            self._update_running_tools_count()
            # Re-run once after the first layout pass so width-dependent hint
            # truncation can use settled regions.
            self.call_after_refresh(lambda: (self._refresh_welcome_context_hint(), self._refresh_input_modes_row_layout()))
            # Viewer mode: hide input area, show viewer indicator
            if self._viewer_mode:
                input_area = self.query_one("#input_area", Container)
                if input_area:
                    input_area.add_class("hidden")
                viewer_label = self.query_one("#status_viewer_mode", Static)
                if viewer_label:
                    viewer_label.remove_class("hidden")
                # Set phase to indicate viewer mode
                feeder = self.coordination_display._viewer_event_feeder
                is_live = feeder._is_live if feeder else False
                phase_label = "👁 LIVE" if is_live else "👁 REPLAY"
                phase_widget = self.query_one("#status_phase", Static)
                if phase_widget:
                    phase_widget.update(phase_label)
            else:
                # Auto-focus input field on startup (not in viewer mode)
                if self.question_input:
                    self.question_input.focus()

            # DEBUG: Log widget state to file (opt-in)
            if os.environ.get("MASSGEN_TUI_LAYOUT_DEBUG", "").lower() in ("1", "true", "yes", "on"):
                import json

                debug_info = {
                    "header_widget": {
                        "exists": self.header_widget is not None,
                        "id": getattr(self.header_widget, "id", None) if self.header_widget else None,
                        "display": str(self.header_widget.display) if self.header_widget else None,
                        "visible": self.header_widget.visible if self.header_widget else None,
                        "classes": list(self.header_widget.classes) if self.header_widget else None,
                        "styles_dock": str(self.header_widget.styles.dock) if self.header_widget else None,
                        "styles_height": str(self.header_widget.styles.height) if self.header_widget else None,
                        "styles_display": str(self.header_widget.styles.display) if self.header_widget else None,
                    },
                    "status_bar": {
                        "exists": self._status_bar is not None,
                        "id": getattr(self._status_bar, "id", None) if self._status_bar else None,
                        "display": str(self._status_bar.display) if self._status_bar else None,
                        "visible": self._status_bar.visible if self._status_bar else None,
                        "classes": list(self._status_bar.classes) if self._status_bar else None,
                        "styles_dock": str(self._status_bar.styles.dock) if self._status_bar else None,
                        "styles_height": str(self._status_bar.styles.height) if self._status_bar else None,
                        "styles_display": str(self._status_bar.styles.display) if self._status_bar else None,
                    },
                    "tab_bar": {
                        "exists": self._tab_bar is not None,
                        "id": getattr(self._tab_bar, "id", None) if self._tab_bar else None,
                        "classes": list(self._tab_bar.classes) if self._tab_bar else None,
                        "styles_dock": str(self._tab_bar.styles.dock) if self._tab_bar else None,
                    },
                }
                # Add execution_bar and cancel_button info
                try:
                    execution_bar = self.query_one("#execution_bar")
                    debug_info["execution_bar"] = {
                        "exists": True,
                        "id": execution_bar.id,
                        "classes": list(execution_bar.classes),
                        "display": str(execution_bar.styles.display),
                        "visible": execution_bar.visible,
                    }
                except Exception as e:
                    debug_info["execution_bar"] = {"exists": False, "error": str(e)}

                try:
                    cancel_btn = self.query_one("#turn_cancel_button")
                    debug_info["cancel_button"] = {
                        "exists": True,
                        "id": cancel_btn.id,
                        "classes": list(cancel_btn.classes),
                        "display": str(cancel_btn.styles.display),
                        "visible": cancel_btn.visible,
                    }
                except Exception as e:
                    debug_info["cancel_button"] = {"exists": False, "error": str(e)}

                try:
                    input_area = self.query_one("#input_area")
                    debug_info["input_area"] = {
                        "exists": True,
                        "id": input_area.id,
                        "classes": list(input_area.classes),
                        "display": str(input_area.styles.display),
                    }
                except Exception as e:
                    debug_info["input_area"] = {"exists": False, "error": str(e)}

                _debug_path = os.path.join(tempfile.gettempdir(), "textual_debug.json")
                with open(_debug_path, "w") as f:
                    json.dump(debug_info, f, indent=2, default=str)
                self.log(f"DEBUG: Widget info written to {_debug_path}")
                tui_log(f"TUI mounted - debug info written to {_debug_path}")

        def on_unmount(self) -> None:
            """Clean up debug timers/threads when app exits."""
            try:
                if self._heartbeat_timer is not None:
                    self._heartbeat_timer.stop()
            except Exception:
                pass
            self._heartbeat_timer = None
            self._stop_stall_watchdog()
            # If the user exits while copy mode is on, the terminal is left without
            # mouse tracking. Restore it before the driver tears down.
            if getattr(self, "_copy_mode_active", False):
                try:
                    self._set_terminal_mouse_capture(True)
                except Exception:
                    pass
                self._copy_mode_active = False

        def set_hover_updates_suppressed(self, suppressed: bool, reason: str = "") -> None:
            """Enable/disable hover-style recalculation for responsiveness."""
            if self._hover_updates_suppressed == suppressed:
                return
            self._hover_updates_suppressed = suppressed
            if self._timing_debug:
                reason_suffix = f" reason={reason}" if reason else ""
                tui_log(f"[TIMING] TextualApp.hover_updates_suppressed {suppressed}{reason_suffix}")

        def _set_mouse_over(self, widget: Widget | None, hover_widget: Widget | None) -> None:
            """Skip hover style churn when suppression is enabled."""
            if self._hover_updates_suppressed:
                return
            super()._set_mouse_over(widget, hover_widget)

        def _start_stall_watchdog(self) -> None:
            """Start a background watchdog to capture main-thread stack on stalls."""
            _widget_debug.start_stall_watchdog(self)

        def _stop_stall_watchdog(self) -> None:
            """Stop stall watchdog thread."""
            _widget_debug.stop_stall_watchdog(self)

        def _stall_watchdog_loop(self) -> None:
            """Capture Python stack traces when main loop appears blocked."""
            _widget_debug.stall_watchdog_loop(self)

        def _heartbeat_tick(self) -> None:
            """Log event-loop stalls when timing debug is enabled."""
            _widget_debug.heartbeat_tick(self)

        def _dump_widget_sizes(self) -> None:
            """Dump full widget tree with sizes for debugging layout issues."""
            _widget_debug.dump_widget_sizes(self)

        def _update_safe_indicator(self):
            """Show/hide safe keyboard status in footer area."""
            if not self.safe_indicator:
                return
            if self.coordination_display.safe_keyboard_mode:
                self.safe_indicator.update("🔒 Safe keys: ON")
                self.safe_indicator.styles.display = "block"
            elif not self._keyboard_interactive_mode:
                self.safe_indicator.update("⌨ Keyboard input disabled")
                self.safe_indicator.styles.display = "block"
            else:
                self.safe_indicator.update("")
                self.safe_indicator.styles.display = "none"

        def _update_theme_indicator(self) -> None:
            """Update theme icon in status bar."""
            try:
                theme_widget = self.query_one("#status_theme", Static)
                theme = self.coordination_display.theme
                icon_map = {"dark": "D", "light": "L"}
                icon = f"[dim]{icon_map.get(theme, 'D')}[/]"
                theme_widget.update(icon)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Widget not mounted yet

        def set_input_handler(self, handler: Callable[[str], None]) -> None:
            """Set the input handler callback for controller integration."""
            self._input_handler = handler

        def _dismiss_welcome(self) -> None:
            """Dismiss the welcome screen and show the main UI."""
            if not self._showing_welcome:
                return
            self._showing_welcome = False

            # Hide welcome screen
            if self._welcome_screen:
                self._welcome_screen.add_class("hidden")

            # Show tab bar, status ribbon, execution status line, main container, and status bar
            if self._tab_bar:
                self._tab_bar.remove_class("hidden")
            if self._status_ribbon:
                self._status_ribbon.remove_class("hidden")
            self._refresh_consensus_map()
            if self._execution_status_line:
                self._execution_status_line.remove_class("hidden")
            if self._status_bar:
                self._status_bar.remove_class("hidden")
                self._status_bar.start_timer()
            try:
                main_container = self.query_one("#main_container", Container)
                main_container.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Refresh right-side hint now that welcome-only context is gone.
            if hasattr(self, "question_input") and self.question_input:
                vim_normal = None
                if self.question_input.vim_mode:
                    vim_normal = bool(getattr(self.question_input, "_vim_normal", False))
                self._update_vim_indicator(vim_normal)

        def on_key(self, event: events.Key) -> None:
            """Handle key events for agent shortcuts and @ autocomplete.

            Number keys 1-9 switch to specific agents (when not typing).
            All other shortcuts use Ctrl modifiers and are handled via BINDINGS.
            """
            # If @ autocomplete is showing, route keys to it first
            if hasattr(self, "_path_dropdown") and self._path_dropdown.is_showing:
                if self._path_dropdown.handle_key(event):
                    event.prevent_default()
                    event.stop()
                    return

            # Don't handle shortcuts when typing in input (supports both Input and MultiLineInput/TextArea)
            if isinstance(self.focused, (Input, TextArea)) and getattr(self.focused, "id", None) == "question_input":
                # But allow Escape to unfocus from input
                if event.key == "escape":
                    self.set_focus(None)
                    self.notify("Press any shortcut key (h for help)", severity="information", timeout=2)
                    event.stop()
                    return
                # Stop event propagation when input is focused to prevent shortcuts from triggering
                event.stop()
                # Note: Tab key when dropdown is showing is handled above
                return

            # Handle agent shortcuts
            self._handle_agent_shortcuts(event)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            """Handle Enter key in the single-line Input widget (fallback)."""
            if event.input.id == "question_input":
                self._submit_question()

        def on_multi_line_input_submitted(self, event: MultiLineInput.Submitted) -> None:
            """Handle Enter in the multi-line input."""
            if event.input.id == "question_input":
                # Pass the submitted value which has paste placeholders expanded
                self._submit_question(event.value)

        @on(TextArea.Changed, "#question_input")
        def handle_question_input_changed(self, event: TextArea.Changed) -> None:
            """Handle TextArea changes to trigger @ autocomplete check."""
            if hasattr(self, "question_input") and hasattr(self.question_input, "_check_at_trigger"):
                self.question_input._check_at_trigger()

        def on_multi_line_input_vim_mode_changed(self, event: MultiLineInput.VimModeChanged) -> None:
            """Handle vim mode changes to update the indicator."""
            if event.input.id == "question_input":
                self._update_vim_indicator(event.vim_normal)

        def on_multi_line_input_at_prefix_changed(self, event: MultiLineInput.AtPrefixChanged) -> None:
            """Handle @ prefix changes for path autocomplete."""
            if event.input.id == "question_input" and hasattr(self, "_path_dropdown"):
                self._path_dropdown.update_suggestions(event.prefix)
                self.question_input.autocomplete_active = self._path_dropdown.is_showing

        def on_multi_line_input_at_dismissed(self, event: MultiLineInput.AtDismissed) -> None:
            """Handle @ autocomplete dismissal."""
            if event.input.id == "question_input" and hasattr(self, "_path_dropdown"):
                self._path_dropdown.dismiss()
                self.question_input.autocomplete_active = False

        def on_multi_line_input_tab_pressed_with_autocomplete(self, event: MultiLineInput.TabPressedWithAutocomplete) -> None:
            """Handle Tab press while autocomplete is active - select current item."""
            if event.input.id == "question_input" and hasattr(self, "_path_dropdown") and self._path_dropdown.is_showing:
                self._path_dropdown._select_current()

        def on_multi_line_input_quit_requested(self, event: MultiLineInput.QuitRequested) -> None:
            """Handle Ctrl+C on empty input - quit the application."""
            if event.input.id == "question_input":
                self.exit()

        def on_multi_line_input_quit_pending(self, event: MultiLineInput.QuitPending) -> None:
            """Handle first Ctrl+C - show hint to press again to quit."""
            if event.input.id == "question_input":
                self.notify("Press Ctrl+C again to quit", severity="warning", timeout=3)

        def on_path_suggestion_dropdown_path_selected(self, event: PathSuggestionDropdown.PathSelected) -> None:
            """Handle path selection from autocomplete dropdown."""
            if hasattr(self, "question_input"):
                self.question_input.insert_completion(event.path, event.with_write)
                self.question_input.autocomplete_active = False

        def on_path_suggestion_dropdown_continue_browsing(self, event: PathSuggestionDropdown.ContinueBrowsing) -> None:
            """Handle directory selection to continue browsing."""
            if hasattr(self, "question_input"):
                self.question_input.update_at_prefix(event.prefix)

        def on_path_suggestion_dropdown_dismissed(self, event: PathSuggestionDropdown.Dismissed) -> None:
            """Handle dropdown dismissal."""
            if hasattr(self, "question_input"):
                self.question_input.autocomplete_active = False

        def _register_event_listener(self) -> None:
            """Register this TUI as a listener on the global EventEmitter.

            Events flow directly from the emitter to per-agent TimelineEventAdapters.
            """
            if self.coordination_display._event_listener_registered:
                tui_log("[_register_event_listener] SKIP: already registered")
                return

            emitter = get_event_emitter()
            if emitter is None:
                tui_log("[_register_event_listener] SKIP: emitter is None")
                return

            emitter.add_listener(self._handle_event_from_emitter)
            self.coordination_display._event_listener_registered = True
            tui_log("[_register_event_listener] SUCCESS: listener registered")

        # Event types that bypass the agent_id-in-widgets guard because they
        # fire before agent widgets exist or carry no agent_id.
        _AGENT_GUARD_BYPASS_EVENTS = frozenset(
            {
                "pre_collab_batch_announced",
                "pre_collab_started",
                "pre_collab_completed",
                "personas_set",
                "evaluation_criteria_set",
                "evaluation_criteria_evolved",
                "subtasks_set",
                "orchestrator_timeout",
                "phase_change",
            },
        )

        def _handle_event_from_emitter(self, event) -> None:
            """Handle an event from the global EventEmitter.

            Called from backend/orchestrator threads. Events are batched for
            ~16ms before being marshaled to the Textual main thread via a
            single call_from_thread(), reducing per-token thread sync overhead.
            """
            # Skip legacy stream_chunk events from old log files
            if event.event_type == "stream_chunk":
                return

            # Coordination events (answer_submitted, vote, winner_selected,
            # context_received) are now rendered through the event pipeline
            # instead of direct display callbacks.

            # Pre-collab and config events may fire before agent widgets
            # exist or have no agent_id. Let them through unconditionally.
            agent_id = event.agent_id
            if event.event_type not in self._AGENT_GUARD_BYPASS_EVENTS:
                if not agent_id or agent_id not in self.agent_widgets:
                    return

            with self._event_batch_lock:
                self._event_batch.append(event)
                # Start timer on first event in batch
                if self._event_batch_timer is None:
                    self._event_batch_timer = threading.Timer(
                        self._EVENT_BATCH_INTERVAL,
                        self._flush_event_batch,
                    )
                    self._event_batch_timer.daemon = True
                    self._event_batch_timer.start()

        def _flush_event_batch(self) -> None:
            """Flush accumulated events to the Textual main thread."""
            with self._event_batch_lock:
                if not self._event_batch:
                    self._event_batch_timer = None
                    return
                batch = list(self._event_batch)
                self._event_batch.clear()
                self._event_batch_timer = None

            try:
                self.call_from_thread(self._route_event_batch, batch)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Don't crash for display issues

        def _route_event_batch(self, events) -> None:
            """Route a batch of events to their agent TimelineEventAdapters.

            Runs on the Textual main thread (via call_from_thread).
            """
            for event in events:
                # Handle coordination event side effects first (some events like
                # orchestrator_timeout don't have an agent_id)
                self._handle_coordination_event_side_effects(event)

                agent_id = event.agent_id

                # Orchestrator-level events (no agent_id) go to all adapters
                if not agent_id and event.event_type == "orchestrator_timeout":
                    for aid, panel in self.agent_widgets.items():
                        adapter = self._event_adapters.get(aid)
                        if adapter is None:
                            adapter = TimelineEventAdapter(panel, agent_id=aid)
                            self._event_adapters[aid] = adapter
                        adapter.handle_event(event)
                    continue

                # Pre-collab and config events are handled entirely by
                # side effects above — skip adapter routing for them.
                if event.event_type in self._AGENT_GUARD_BYPASS_EVENTS:
                    continue

                if not agent_id or agent_id not in self.agent_widgets:
                    continue

                panel = self.agent_widgets[agent_id]
                adapter = self._event_adapters.get(agent_id)
                if adapter is None:
                    adapter = TimelineEventAdapter(panel, agent_id=agent_id)
                    self._event_adapters[agent_id] = adapter

                adapter.handle_event(event)

        def _handle_coordination_event_side_effects(self, event) -> None:
            """Handle status bar, toast, and browser tracking for coordination events.

            These side effects were previously in direct display methods
            (notify_vote, notify_new_answer, highlight_winner_quick).
            """
            import time

            self._apply_consensus_event(event)

            if event.event_type == "answer_submitted":
                agent_id = event.agent_id or ""
                content = event.data.get("content", "")
                answer_label = event.data.get("answer_label", "")
                answer_number = event.data.get("answer_number", 1)

                model_name = self.coordination_display.agent_models.get(agent_id, "")

                # Track for browser
                self._answers.append(
                    {
                        "agent_id": agent_id,
                        "model": model_name,
                        "content": content,
                        "answer_id": None,
                        "answer_number": answer_number,
                        "answer_label": answer_label,
                        "workspace_path": event.data.get("workspace_path"),
                        "timestamp": time.time(),
                        "is_final": False,
                        "is_winner": False,
                    },
                )

                # Update status bar
                if self._status_bar:
                    agent_count = len(self.coordination_display.agent_ids)
                    answer_count = len(self._answers)
                    vote_count = len(self._votes)
                    self._status_bar.update_progress(agent_count, answer_count, vote_count)
                    self._status_bar.increment_agent_answer(agent_id)

                # Show toast
                agent_display = f"{agent_id}" + (f" ({model_name})" if model_name else "")
                preview = content[:100].replace("\n", " ")
                if len(content) > 100:
                    preview += "..."
                self.notify(
                    f"📝 [bold green]New Answer[/] from [bold]{agent_display}[/]\n   Answer #{answer_number}: {preview}",
                    timeout=5,
                )

            elif event.event_type == "vote":
                voter = event.agent_id or ""
                target = event.data.get("target_id", "")
                reason = event.data.get("reason", "")

                voter_model = self.coordination_display.agent_models.get(voter, "")
                voted_for_model = self.coordination_display.agent_models.get(target, "")

                # Get voted-for answer label from coordination tracker
                voted_for_label = None
                tracker = None
                if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                    tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)
                if tracker:
                    voted_for_label = tracker.get_voted_for_label(voter, target)

                vote_count = len(self._votes) + 1
                self._votes.append(
                    {
                        "voter": voter,
                        "voter_model": voter_model,
                        "voted_for": target,
                        "voted_for_model": voted_for_model,
                        "voted_for_label": voted_for_label,
                        "reason": reason,
                        "timestamp": time.time(),
                    },
                )

                if self._status_bar:
                    self._status_bar.add_vote(target, voter)
                    agent_count = len(self.coordination_display.agent_ids)
                    answer_count = len(self._answers)
                    expected_votes = agent_count * (agent_count - 1) if agent_count > 1 else 0
                    self._status_bar.update_progress(agent_count, answer_count, vote_count, expected_votes)

                    standings = self._status_bar.get_standings_text()
                    voter_display = f"{voter}" + (f" ({voter_model})" if voter_model else "")
                    target_display = f"{target}" + (f" ({voted_for_model})" if voted_for_model else "")

                    if standings:
                        self.notify(
                            f"🗳️ [bold]{voter_display}[/] voted for [bold cyan]{target_display}[/]\n📊 {standings}",
                            timeout=4,
                        )
                    else:
                        self.notify(
                            f"🗳️ [bold]{voter_display}[/] voted for [bold cyan]{target_display}[/]",
                            timeout=3,
                        )
                else:
                    self.notify(f"🗳️ {voter} voted for {target}", timeout=3)

            elif event.event_type == "agent_stopped":
                # Decomposition mode: agent signaled stop (subtask complete)
                agent_id = event.agent_id or ""
                summary = event.data.get("summary", "")
                stop_status = event.data.get("status", "complete")

                model_name = self.coordination_display.agent_models.get(agent_id, "")
                agent_display = f"{agent_id}" + (f" ({model_name})" if model_name else "")

                status_emoji = "✅" if stop_status == "complete" else "⚠️"
                self.notify(
                    f"{status_emoji} [bold]{agent_display}[/] stopped ({stop_status})",
                    timeout=4,
                )
                # Tool card is created by content_processor (unified pipeline),
                # matching how vote tool cards work. No duplicate card here.

            elif event.event_type == "winner_selected":
                winner_id = event.agent_id or ""
                # Switch to winner tab and mark with trophy
                if self._tab_bar:
                    self._tab_bar.set_active(winner_id)
                    self._tab_bar.set_winner(winner_id)

                # Update ExecutionStatusLine: all agents to done
                if self._execution_status_line:
                    for aid in self._execution_status_line._agent_ids:
                        self._execution_status_line.set_agent_state(aid, "done")

                # Show winner panel, hide others
                self._winner_agent_id = winner_id
                self._update_winner_hints(winner_id)
                if winner_id in self.agent_widgets:
                    if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                        self.agent_widgets[self._active_agent_id].add_class("hidden")
                    self.agent_widgets[winner_id].remove_class("hidden")
                    self._active_agent_id = winner_id

            elif event.event_type == "final_presentation_start":
                agent_id = event.agent_id or ""
                self._winner_agent_id = agent_id
                self._update_winner_hints(agent_id)
                # Pause background UI timers to keep final answer responsive
                if hasattr(self, "_execution_status_timer") and self._execution_status_timer:
                    self._execution_status_timer.stop()
                    self._execution_status_timer = None
                self._stop_all_pulses()
                # Skip direct content updates during final presentation - event pipeline handles it
                if hasattr(self.coordination_display, "_in_final_presentation"):
                    self.coordination_display._in_final_presentation = True
                # Switch to winner tab if not already
                if self._tab_bar:
                    self._tab_bar.set_active(agent_id)
                    self._tab_bar.set_winner(agent_id)
                if self._execution_status_line:
                    for aid in self._execution_status_line._agent_ids:
                        self._execution_status_line.set_agent_state(aid, "done")

            elif event.event_type == "answer_locked":
                agent_id = event.agent_id or ""
                # Clear final presentation flag - content can now flow normally
                if hasattr(self.coordination_display, "_in_final_presentation"):
                    self.coordination_display._in_final_presentation = False
                # Update input placeholder
                if hasattr(self, "question_input"):
                    self.question_input.placeholder = "Type your follow-up question..."

            elif event.event_type == "orchestrator_timeout":
                # Show toast notification
                timeout_reason = event.data.get("timeout_reason", "")
                available = event.data.get("available_answers", 0)
                self.notify(
                    f"[bold yellow]Orchestration timed out[/bold yellow]\n{timeout_reason}\n{available} answer(s) available",
                    timeout=8,
                )

                # Update ExecutionStatusLine: mark unfinished agents as timed out
                if self._execution_status_line:
                    summary = event.data.get("agent_answer_summary", {})
                    for aid, info in summary.items():
                        if not info.get("has_answer"):
                            self._execution_status_line.set_agent_state(aid, "error")

            elif event.event_type == "context_received":
                agent_id = event.agent_id or ""
                context_labels = event.data.get("context_labels", [])
                if hasattr(self, "update_agent_context"):
                    try:
                        self.update_agent_context(agent_id, context_labels)
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

            elif event.event_type == "pre_collab_batch_announced":
                ids = event.data.get("pre_collab_ids", [])
                self._parallel_precollab_expected = set(ids)
                self._parallel_precollab_screen_opened = False

            elif event.event_type == "pre_collab_started":
                try:
                    self.show_runtime_subagent_card(
                        agent_id=event.data.get("agent_id") or event.agent_id or "",
                        subagent_id=event.data.get("subagent_id", ""),
                        task=event.data.get("task", ""),
                        timeout_seconds=event.data.get("timeout_seconds", 300),
                        call_id=event.data.get("call_id", event.data.get("subagent_id", "")),
                        status_callback=None,
                        log_path=event.data.get("log_path"),
                    )
                except Exception as e:
                    tui_log(f"[TextualDisplay] pre_collab_started: {e}")

            elif event.event_type == "pre_collab_completed":
                try:
                    self.update_runtime_subagent_card(
                        agent_id=event.data.get("agent_id") or event.agent_id or "",
                        subagent_id=event.data.get("subagent_id", ""),
                        call_id=event.data.get("call_id", event.data.get("subagent_id", "")),
                        status=event.data.get("status", "completed"),
                        answer_preview=event.data.get("answer_preview"),
                        error=event.data.get("error"),
                    )
                except Exception as e:
                    tui_log(f"[TextualDisplay] pre_collab_completed: {e}")

            elif event.event_type == "personas_set":
                try:
                    personas = event.data.get("personas", {})
                    self.set_agent_personas(personas)
                except Exception as e:
                    tui_log(f"[TextualDisplay] personas_set: {e}")

            elif event.event_type == "evaluation_criteria_set":
                try:
                    criteria = event.data.get("criteria", [])
                    source = event.data.get("source", "default")
                    self.set_evaluation_criteria(criteria, source=source)
                except Exception as e:
                    tui_log(f"[TextualDisplay] evaluation_criteria_set: {e}")

            elif event.event_type == "evaluation_criteria_evolved":
                try:
                    evo_num = event.data.get("evolution_number", "?")
                    evolved_count = event.data.get("evolved_count", 0)
                    total_count = event.data.get("total_count", 0)
                    summary = event.data.get("summary", "")
                    short_summary = (summary[:80] + "...") if len(summary) > 80 else summary
                    self.notify(
                        f"Criteria evolved (v{evo_num}): " f"{evolved_count}/{total_count} criteria raised\n" f"{short_summary}",
                        severity="information",
                        timeout=10,
                    )
                except Exception as e:
                    tui_log(f"[TextualDisplay] evaluation_criteria_evolved: {e}")

            elif event.event_type == "subtasks_set":
                try:
                    subtasks = event.data.get("subtasks", {})
                    self.set_agent_subtasks(subtasks)
                except Exception as e:
                    tui_log(f"[TextualDisplay] subtasks_set: {e}")

        def _is_execution_in_progress(self) -> bool:
            """Check if agents are currently executing.

            Returns:
                True if in an executing phase, False if idle/presentation.
            """
            if self._status_bar and hasattr(self._status_bar, "_current_phase"):
                phase = self._status_bar._current_phase
                # Idle and presentation phases mean execution is done
                return phase not in ("idle", "presentation", "presenting")
            return False

        def _resolve_human_input_targets(self) -> list[str]:
            """Resolve which agents should receive the next queued runtime message."""
            agent_ids = list(getattr(self.coordination_display, "agent_ids", []) or [])
            if not agent_ids:
                return []

            if self._human_input_target_mode == "current":
                selected = self._active_agent_id or agent_ids[0]
                return [selected] if selected else []

            return agent_ids

        def _describe_human_input_targets(self, targets: list[str]) -> str:
            """Return a compact human-readable target label for queue UI."""
            if not targets:
                return "none"
            if len(targets) == 1:
                return targets[0]
            return "all agents"

        def _build_human_input_target_button_label(self) -> str:
            """Build compact label for the runtime injection target button."""
            mode = self._human_input_target_mode
            if mode == "all":
                return "Inject: all"

            width = self.size.width or (self.app.size.width if self.app else 120)
            selected = self._active_agent_id or "current"
            if width >= 130:
                return f"Inject: {selected}"
            return "Inject: current"

        def _update_human_input_target_button(self) -> None:
            """Refresh runtime injection target button text/classes."""
            button = getattr(self, "_inject_target_button", None)
            if not button:
                return

            label = self._build_human_input_target_button_label()
            button.label = label
            try:
                button.remove_class("mode-all", "mode-current")
                button.add_class(f"mode-{self._human_input_target_mode}")
            except Exception:
                pass

        def _set_queued_input_region_visible(self, visible: bool) -> None:
            """Show/hide the queued-input strip above the mode bar."""
            region = getattr(self, "_queued_input_region", None)
            if not region:
                return
            if visible:
                region.add_class("visible")
            else:
                region.remove_class("visible")

            cancel_button = getattr(self, "_queue_cancel_latest_button", None)
            clear_button = getattr(self, "_queue_clear_button", None)
            for button in (cancel_button, clear_button):
                if button is not None:
                    button.disabled = not visible

        def _sync_queued_input_banner_from_hook(self) -> list[dict[str, Any]]:
            """Sync queue banner rows from HumanInputHook pending-message metadata."""
            if self._queued_input_banner is None:
                self._ensure_queued_input_banner_mounted()
            if self._queued_input_banner is None:
                return []

            hook = self._human_input_hook
            agent_ids = list(getattr(self.coordination_display, "agent_ids", []) or [])
            messages: list[dict[str, Any]] = []

            if hook and hasattr(hook, "get_pending_messages"):
                try:
                    messages = hook.get_pending_messages(agent_ids=agent_ids) or []  # type: ignore[assignment]
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to query pending messages: {e}")
                    messages = []

            try:
                if hasattr(self._queued_input_banner, "set_messages"):
                    self._queued_input_banner.set_messages(messages)
                elif messages:
                    latest = messages[-1]
                    self._queued_input_banner.add_message(
                        str(latest.get("content", "")),
                        target_label=str(latest.get("target_label", "all agents")),
                        source_label=str(latest.get("source_label", latest.get("source", "human"))),
                    )
                else:
                    self._queued_input_banner.clear()
            except Exception as e:
                tui_log(f"[HumanInput] Failed to update queue banner rows: {e}")

            self._set_queued_input_region_visible(bool(messages))
            return messages

        def _refresh_human_input_pending_state(self) -> dict[str, int]:
            """Sync per-agent pending runtime-input counts to tabs and banner."""
            agent_ids = list(getattr(self.coordination_display, "agent_ids", []) or [])
            counts: dict[str, int] = {aid: 0 for aid in agent_ids}

            hook = self._human_input_hook
            if hook and hasattr(hook, "get_pending_counts_for_agents"):
                try:
                    counts = hook.get_pending_counts_for_agents(agent_ids)  # type: ignore[assignment]
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to query pending counts: {e}")

            self._queued_human_input_pending_by_agent = counts

            if self._tab_bar:
                try:
                    self._tab_bar.set_pending_injection_counts(counts)
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to update tab pending counts: {e}")

            if self._queued_input_banner:
                try:
                    self._queued_input_banner.set_pending_counts(counts)
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to update queue banner counts: {e}")

            return counts

        def _compose_pending_human_input_for_new_turn(self) -> str | None:
            """Build fallback new-turn text from all queued pending runtime messages."""
            hook = self._human_input_hook
            if not hook or not hasattr(hook, "get_pending_messages"):
                return self._queued_human_input

            agent_ids = list(getattr(self.coordination_display, "agent_ids", []) or [])
            try:
                messages = hook.get_pending_messages(agent_ids=agent_ids) or []
            except Exception as e:
                tui_log(f"[HumanInput] Failed to query pending messages for fallback submit: {e}")
                return self._queued_human_input

            contents = [str(entry.get("content", "")).strip() for entry in messages if str(entry.get("content", "")).strip()]
            if not contents:
                return None
            return "\n".join(contents)

        def _queue_human_input(self, text: str) -> None:
            """Queue human input for injection during execution.

            Args:
                text: The human input text to queue
            """
            self._queued_human_input = text
            targets = self._resolve_human_input_targets()
            target_label = self._describe_human_input_targets(targets)

            # Send to hook if available
            queued_message_id: int | None = None
            if self._human_input_hook:
                queued_message_id = self._human_input_hook.set_pending_input(
                    text,
                    target_agents=targets if targets else None,
                    source="human",
                )

            # Show visual indicator - mount banner dynamically if not present
            try:
                messages = self._sync_queued_input_banner_from_hook()
                if not messages and self._queued_input_banner is not None:
                    # Fallback path for tests or legacy hooks without metadata.
                    self._queued_input_banner.add_message(text, target_label=target_label)
                    self._set_queued_input_region_visible(True)
            except Exception as e:
                tui_log(f"[HumanInput] Failed to show banner: {e}")

            counts = self._refresh_human_input_pending_state()
            preview = text[:40] + "..." if len(text) > 40 else text
            pending_on = [aid for aid, count in counts.items() if count > 0]
            pending_label = ", ".join(pending_on) if pending_on else target_label
            id_prefix = f"#{queued_message_id} " if queued_message_id is not None else ""
            self.notify(
                f'📝 Queued {id_prefix}for {pending_label}: "{preview}" (Ctrl+C to cancel and start new turn)',
                timeout=4,
            )
            tui_log(f"[HumanInput] Queued input: {text[:50]}...")

        def _ensure_queued_input_banner_mounted(self) -> None:
            """Ensure runtime-queue banner exists and is mounted above the mode row."""
            if self._queued_input_banner is None:
                self._queued_input_banner = QueuedInputBanner(id="queued_input_banner")

            banner = self._queued_input_banner
            if banner is None:
                return

            # Already mounted somewhere in the UI tree.
            if getattr(banner, "parent", None) is not None:
                return

            try:
                queue_row = self.query_one("#queued_input_row", Horizontal)
                if self._queued_input_actions is not None:
                    queue_row.mount(banner, before=self._queued_input_actions)
                else:
                    queue_row.mount(banner)
                return
            except Exception:
                pass

            try:
                queue_region = self.query_one("#queued_input_region", Container)
                queue_region.mount(banner)
                return
            except Exception:
                pass

            # Fallback for tests/legacy layout: mount above input_header.
            input_area = self.query_one("#input_area", Container)
            anchor = self._input_header if self._input_header is not None else self.question_input
            input_area.mount(banner, before=anchor)

        def _clear_queued_input(self) -> None:
            """Clear the queued human input after injection."""
            self._queued_human_input = None
            self._queued_human_input_pending_by_agent = {}

            # Clear visual indicator
            if self._queued_input_banner:
                self._queued_input_banner.clear()
            self._set_queued_input_region_visible(False)
            if self._tab_bar:
                self._tab_bar.set_pending_injection_counts({})

            tui_log("[HumanInput] Cleared queued input")

        def _add_runtime_injection_timeline_entry(
            self,
            agent_id: str,
            content: str,
            *,
            message_id: int | None = None,
            source_label: str | None = None,
        ) -> None:
            """Insert a dedicated timeline entry when runtime input is injected."""
            panel = self.agent_widgets.get(agent_id)
            if not panel:
                return

            try:
                timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                round_number = getattr(panel, "_current_round", 1)
                prefix = f"Runtime Injection #{message_id}" if message_id is not None else "Runtime Injection"
                if source_label:
                    prefix = f"{prefix} [{source_label}]"
                timeline.add_text(
                    f"{prefix} -> Delivered to {agent_id}: {content}",
                    text_class="status runtime-injection",
                    round_number=round_number,
                )
            except Exception as e:
                tui_log(f"[HumanInput] Failed to append runtime injection timeline entry: {e}")

        def _on_human_input_injected(
            self,
            content: str,
            agent_id: str,
            delivered_messages: list[dict[str, Any]] | None = None,
        ) -> None:
            """Called when human input is injected into tool result.

            Updates per-agent pending state, records a timeline entry, and
            clears queue UI once all targeted deliveries are complete.

            Args:
                content: The injected input content
                agent_id: Agent that received this runtime injection
            """
            if delivered_messages:
                for message in delivered_messages:
                    message_id = message.get("id")
                    try:
                        normalized_id = int(message_id) if message_id is not None else None
                    except Exception:
                        normalized_id = None
                    self._add_runtime_injection_timeline_entry(
                        agent_id,
                        str(message.get("content", "")),
                        message_id=normalized_id,
                        source_label=str(message.get("source_label") or message.get("source") or "").strip() or None,
                    )
            else:
                self._add_runtime_injection_timeline_entry(agent_id, content)
            counts = self._refresh_human_input_pending_state()
            self._sync_queued_input_banner_from_hook()
            if not any(count > 0 for count in counts.values()):
                self._clear_queued_input()

            preview = content[:40] + "..." if len(content) > 40 else content
            self.notify(
                f'💬 Injected into {agent_id}: "{preview}"',
                severity="information",
                timeout=3,
            )
            tui_log(f"[HumanInput] Input injected into {agent_id}: {content[:50]}...")

        def set_human_input_hook(self, hook) -> None:
            """Set the human input hook reference from orchestrator.

            Args:
                hook: HumanInputHook instance to use for injection
            """
            self._human_input_hook = hook
            # Set callback so we're notified when input is injected
            if hook:
                hook.set_inject_callback(
                    lambda content, agent_id, delivered_messages=None: self.call_from_thread(
                        self._on_human_input_injected,
                        content,
                        agent_id,
                        delivered_messages,
                    ),
                )
            self._refresh_human_input_pending_state()
            self._sync_queued_input_banner_from_hook()
            tui_log(f"[HumanInput] Set human input hook: {hook}")

        def set_subagent_message_callback(self, callback) -> None:
            """Set the callback for sending messages to running subagents."""
            self._subagent_message_callback = callback

        def set_subagent_continue_callback(self, callback) -> None:
            """Set callback for continuing terminal subagents from SubagentScreen."""
            self._subagent_continue_callback = callback

        def set_answer_now_callback(self, callback) -> None:
            """Set callback for the status-bar Answer Now action."""
            self._answer_now_callback = callback

        def _submit_question(
            self,
            submitted_text: str | None = None,
            *,
            bypass_execution_queue: bool = False,
        ) -> None:
            """Submit the current question text.

            During execution, input is queued for injection into the next tool result.
            Cancel execution first (Ctrl+C) if you want to start a new turn.

            Args:
                submitted_text: Pre-processed text from Submitted event (with paste
                    placeholders expanded). If None, reads from widget directly.
                bypass_execution_queue: Internal-only flag. When True, submit as a
                    new turn even if execution-phase status still reports in-progress.
            """
            text = submitted_text.strip() if submitted_text else self.question_input.text.strip()
            tui_log(f"_submit_question called with text: '{text[:50]}...' (len={len(text)})")

            # In execute/analysis mode, allow empty submission.
            # - Execute: Enter runs selected plan.
            # - Analysis: Enter runs default analysis request for selected log target.
            is_execute_mode = self._mode_state.plan_mode == "execute"
            is_analysis_mode = self._mode_state.plan_mode == "analysis"
            if not text and not (is_execute_mode or is_analysis_mode):
                tui_log("  Empty text and not execute/analysis mode, returning")
                return

            # Hide plan options popover on submission (especially for execute mode)
            if hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes:
                self._plan_options_popover.hide()

            # Clear any persistent cancelled state when user starts a new turn
            self._clear_cancelled_state()

            # CRITICAL: Check execution status FIRST before execute mode
            # During active execution, queue input (don't trigger new plan execution)
            is_executing = self._is_execution_in_progress()
            has_hook = self._human_input_hook is not None
            phase = self._status_bar._current_phase if self._status_bar else "unknown"
            tui_log(f"  is_executing={is_executing}, has_hook={has_hook}, phase={phase}")

            if not text.startswith("/") and is_executing and has_hook and not bypass_execution_queue:
                if not text:
                    tui_log("  -> Ignoring empty runtime input during execution")
                    self.question_input.clear()
                    return
                tui_log("  -> Queueing input for injection")
                self._queue_human_input(text)
                # Clear queued text immediately so repeated Enter presses don't requeue it.
                self.question_input.clear()
                return

            # In execute mode (and NOT currently executing), set up plan execution
            if is_execute_mode:
                text = self._setup_plan_execution(text)
                if text is None:
                    # Setup failed, error already shown
                    return
            elif is_analysis_mode:
                text = self._setup_analysis_submission(text)

            # Clear input after determining routing (queued input was already cleared)
            self.question_input.clear()

            tui_log("  -> Submitting as new turn")

            # Auto-include CWD as context based on mode
            if self._cwd_context_mode != "off" and not text.startswith("/"):
                cwd = str(Path.cwd())
                # Add @cwd with appropriate permission suffix
                suffix = ":w" if self._cwd_context_mode == "write" else ""
                cwd_ref = f"@{cwd}{suffix}"
                # Prepend if not already present
                if f"@{cwd}" not in text:
                    text = f"{cwd_ref} {text}"
                    tui_log(f"  Auto-prepended CWD context: {cwd_ref}")

            # Dismiss welcome screen on first real input
            if self._showing_welcome and not text.startswith("/"):
                self._dismiss_welcome()

            # Handle TUI-local slash commands first (like /vim)
            if text.startswith("/"):
                if self._handle_local_slash_command(text):
                    tui_log("  Handled as local slash command")
                    return  # Command was handled locally

            tui_log(f"  _input_handler is: {self._input_handler}")
            if self._input_handler:
                tui_log("  Calling _input_handler...")

                # Store question for plan execution if in plan mode
                # Only capture the FIRST user input - don't overwrite with subsequent/injected inputs
                if not text.startswith("/") and self._mode_state.plan_mode in ("plan", "spec"):
                    if self._mode_state.last_planning_question is None:
                        self._mode_state.last_planning_question = text
                        self._mode_state.planning_started_turn = self.coordination_display.current_turn
                        tui_log(f"  Stored planning question (turn {self._mode_state.planning_started_turn}): {text[:50]}...")
                    else:
                        tui_log(f"  Plan question already set, not overwriting with: {text[:50]}...")

                self._input_handler(text)
                if not text.startswith("/"):
                    # Track the current question for history
                    self._current_question = text
                    try:
                        main_container = self.query_one("#main_container", Container)
                        main_container.remove_class("hidden")
                        if self.header_widget:
                            self.header_widget.update_question(text)
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")
                return

            if text.startswith("/"):
                self._handle_slash_command(text)
                return

            # Track the current question for history
            self._current_question = text
            main_container = self.query_one("#main_container", Container)
            main_container.remove_class("hidden")

            if self.header_widget:
                self.header_widget.update_question(text)

        def _submit_followup_question(self, question: str) -> None:
            """Submit a follow-up question from the final answer panel."""
            if not question:
                return

            # Dismiss welcome screen if still showing
            if self._showing_welcome:
                self._dismiss_welcome()

            # Track the question for history
            self._current_question = question

            # Update header with new question
            if self.header_widget:
                self.header_widget.update_question(question)

            # Show main container
            try:
                main_container = self.query_one("#main_container", Container)
                main_container.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Submit through the input handler
            if self._input_handler:
                self._input_handler(question)

        def _handle_local_slash_command(self, command: str) -> bool:
            """Handle TUI-local slash commands that should not be passed to the orchestrator.

            Args:
                command: The slash command string.

            Returns:
                True if the command was handled locally, False otherwise.
            """
            cmd = command.split()[0].lower()
            parts = command.split()

            if cmd == "/vim":
                self._toggle_vim_mode()
                return True

            # /theme command enabled with user settings
            if cmd == "/theme":
                self.action_toggle_theme()
                return True

            if cmd in {"/inject-target", "/inject"}:
                requested = parts[1].strip().lower() if len(parts) > 1 else ""
                if requested in {"all", "current"}:
                    self._set_human_input_target_mode(requested)
                else:
                    self._toggle_human_input_target_mode()
                return True

            return False

        def _handle_slash_command(self, command: str) -> None:
            """Handle slash commands within the TUI using unified SlashCommandDispatcher."""
            try:
                from massgen.frontend.interactive_controller import (
                    SessionContext,
                    SlashCommandDispatcher,
                )

                context = SessionContext(
                    session_id=getattr(self.coordination_display, "session_id", None),
                    current_turn=getattr(self.coordination_display, "current_turn", 0),
                    agents={},
                )

                dispatcher = SlashCommandDispatcher(context=context, adapter=None)
                result = dispatcher.dispatch(command)

                if result.should_exit:
                    self.exit()
                    return

                if result.reset_ui_view:
                    self._reset_agent_panels()

                if result.ui_action == "show_help":
                    self._show_help_modal()
                elif result.ui_action == "show_status":
                    self._show_system_status_modal()
                elif result.ui_action == "show_events":
                    self._show_orchestrator_modal()
                elif result.ui_action == "show_vote":
                    self.action_open_vote_results()
                elif result.ui_action == "show_turn_inspection":
                    self.action_agent_selector()
                elif result.ui_action == "list_all_turns":
                    self.action_agent_selector()
                elif result.ui_action == "cancel_turn":
                    self.coordination_display.request_cancellation()
                elif result.ui_action == "prompt_context_paths":
                    self._show_context_modal()
                elif result.ui_action == "show_cost":
                    self._show_cost_breakdown_modal()
                elif result.ui_action == "show_workspace":
                    self._show_workspace_files_modal()
                elif result.ui_action == "show_metrics":
                    self._show_metrics_modal()
                elif result.ui_action == "show_mcp":
                    self.action_open_mcp_status()
                elif result.ui_action == "show_answers":
                    self.action_open_answer_browser()
                elif result.ui_action == "show_timeline":
                    self.action_open_timeline()
                elif result.ui_action == "show_files":
                    self.action_open_workspace_browser()
                elif result.ui_action == "show_browser":
                    self.action_open_unified_browser()
                elif result.ui_action == "show_skills":
                    self._show_skills_modal()
                elif result.ui_action == "toggle_vim":
                    self._toggle_vim_mode()
                elif result.ui_action == "toggle_theme":
                    self.action_toggle_theme()
                elif result.ui_action == "show_history":
                    self._show_history_modal()
                elif result.message and not result.ui_action:
                    self.notify(result.message, severity="information" if result.handled else "warning")

                if not result.handled:
                    self.notify(result.message or f"Unknown command: {command}", severity="warning")

            except ImportError:
                cmd = command.lower().strip()
                if cmd in ("/help", "/h", "/?"):
                    self._show_help_modal()
                elif cmd in ("/quit", "/q", "/exit"):
                    self.exit()
                elif cmd in ("/reset", "/clear"):
                    self._reset_agent_panels()
                elif cmd.startswith("/inspect"):
                    self.action_agent_selector()
                elif cmd in ("/status", "/s"):
                    self._show_system_status_modal()
                elif cmd in ("/events", "/o"):
                    self._show_orchestrator_modal()
                elif cmd in ("/vote", "/v"):
                    self.action_open_vote_results()
                elif cmd in ("/context",):
                    self._show_context_modal()
                elif cmd in ("/metrics", "/m"):
                    self._show_metrics_modal()
                elif cmd in ("/cost", "/c"):
                    self._show_cost_breakdown_modal()
                elif cmd in ("/workspace", "/w"):
                    self._show_workspace_files_modal()
                elif cmd in ("/mcp", "/p"):
                    self.action_open_mcp_status()
                elif cmd == "/vim":
                    self._toggle_vim_mode()
                elif cmd in ("/history", "/hist"):
                    self._show_history_modal()
                elif cmd in ("/timeline", "/t"):
                    self.action_open_timeline()
                elif cmd in ("/skills", "/k"):
                    self._show_skills_modal()
                else:
                    self.notify(f"Unknown command: {command}", severity="warning")

        def _toggle_vim_mode(self) -> None:
            """Toggle vim mode on the question input."""
            if not hasattr(self, "question_input") or self.question_input is None:
                return

            current = self.question_input.vim_mode
            self.question_input.vim_mode = not current

            if self.question_input.vim_mode:
                # Enter insert mode when enabling (more intuitive - user wants to type)
                self.question_input._vim_normal = False
                self.question_input.remove_class("vim-normal")
                self._update_vim_indicator(False)  # False = insert mode
            else:
                self.question_input._vim_normal = False
                self.question_input.remove_class("vim-normal")
                self._update_vim_indicator(None)  # None = vim mode off
            # Save vim mode preference
            try:
                user_settings = get_user_settings()
                user_settings.vim_mode = self.question_input.vim_mode
            except Exception:
                pass

        def _update_vim_indicator(self, vim_normal: bool | None) -> None:
            """Update the vim mode indicator.

            Args:
                vim_normal: True for normal mode, False for insert mode, None to hide.
            """
            if not hasattr(self, "_vim_indicator"):
                return

            path_context = self._build_welcome_context_hint_text()
            if hasattr(self, "_input_hint"):
                self._input_hint.update(path_context)
                self._input_hint.remove_class("hidden")

            indicator_text = self._build_vim_indicator_text(vim_normal)
            if vim_normal is None:
                # Vim mode off - keep explicit mode affordance.
                self._vim_indicator.update(indicator_text)
                self._vim_indicator.remove_class("vim-normal-indicator")
                self._vim_indicator.remove_class("vim-insert-indicator")
            elif vim_normal:
                # Normal mode line (top row in right panel).
                self._vim_indicator.update(indicator_text)
                self._vim_indicator.remove_class("vim-insert-indicator")
                self._vim_indicator.add_class("vim-normal-indicator")
            else:
                # Insert mode line (top row in right panel).
                self._vim_indicator.update(indicator_text)
                self._vim_indicator.remove_class("vim-normal-indicator")
                self._vim_indicator.add_class("vim-insert-indicator")

            self._refresh_input_modes_row_layout()

            # Force refresh to ensure visual update
            self._vim_indicator.refresh(layout=True)
            if hasattr(self, "_input_hint"):
                self._input_hint.refresh()

        def _refresh_input_modes_row_layout(self) -> None:
            """Stack meta hints below mode controls when horizontal space is tight."""
            try:
                input_modes_row = self.query_one("#input_modes_row", Horizontal)
            except Exception:
                return

            width = self.size.width or (self.app.size.width if self.app else 120)
            plan_mode = getattr(getattr(self, "_mode_state", None), "plan_mode", "normal")
            if self._mode_bar:
                try:
                    plan_mode = self._mode_bar.get_plan_mode()
                except Exception:
                    pass

            mode_required: int | None = None
            meta_required: int | None = None
            one_row_required: int | None = None
            decision_reason = ""
            forced_compact = False
            # Plan/execute/analysis modes expose longer run-control labels and
            # an extra settings affordance in the left bar; stack the right meta
            # panel earlier to keep run controls readable in standard terminals.
            if plan_mode in {"plan", "execute", "analysis"}:
                stack_meta = width <= 150
                decision_reason = "plan_mode_threshold"
            else:
                # In normal mode, keep one-row layout whenever the compacted
                # left controls and right meta panel actually fit.
                if self._mode_bar:
                    self._mode_bar._refresh_responsive_labels()

                mode_required = 72
                if self._mode_bar:
                    try:
                        mode_required = max(0, int(self._mode_bar._measure_control_width()))
                    except Exception:
                        mode_required = self._mode_bar.region.width or mode_required

                vim_required = 0
                hint_required = 0
                if hasattr(self, "_vim_indicator"):
                    vim_required = len(str(self._vim_indicator.render()).strip())
                if hasattr(self, "_input_hint"):
                    hint_required = len(str(self._input_hint.render()).strip())

                # Right panel width is driven by the wider of its two lines.
                meta_primary_required = vim_required
                meta_required = max(meta_primary_required, hint_required, 24)
                one_row_required = mode_required + meta_required + 6

                # If full labels cause stacking but compact labels would fit,
                # proactively compact the mode controls to preserve single-row
                # startup behavior in thin terminals.
                if self._mode_bar and one_row_required > width and not self._mode_bar._compact_labels_active:
                    try:
                        self._mode_bar._apply_compact_labels(True)
                        compact_mode_required = max(0, int(self._mode_bar._measure_control_width()))
                        compact_one_row_required = compact_mode_required + meta_required + 6
                        if compact_one_row_required <= width:
                            self._mode_bar._compact_labels_active = True
                            mode_required = compact_mode_required
                            one_row_required = compact_one_row_required
                            decision_reason = "forced_compact_for_fit"
                            forced_compact = True
                        else:
                            # Revert if compact labels still cannot satisfy the row budget.
                            self._mode_bar._apply_compact_labels(False)
                    except Exception:
                        pass

                if width >= 150 and "meta-stacked" not in input_modes_row.classes:
                    # Keep a small tolerance on the tested wide threshold so
                    # minor width deltas do not force a stacked layout.
                    stack_meta = one_row_required > width + 2
                    if not decision_reason:
                        decision_reason = "wide_threshold_with_tolerance"
                elif "meta-stacked" in input_modes_row.classes:
                    # Small hysteresis prevents stack/unstack oscillation.
                    stack_meta = one_row_required > max(0, width - 2)
                    if not decision_reason:
                        decision_reason = "stacked_hysteresis"
                else:
                    stack_meta = one_row_required > width
                    if not decision_reason:
                        decision_reason = "fit_comparison"

            if stack_meta:
                input_modes_row.add_class("meta-stacked")
            else:
                input_modes_row.remove_class("meta-stacked")

            mode_bar_compact = self._mode_bar.has_class("compact-layout") if self._mode_bar else None
            tui_log(
                "[INPUT_LAYOUT] "
                f"width={width} plan_mode={plan_mode} stack_meta={stack_meta} "
                f"reason={decision_reason} mode_required={mode_required} "
                f"meta_required={meta_required} one_row_required={one_row_required} "
                f"mode_bar_compact={mode_bar_compact} forced_compact={forced_compact} "
                f"classes={list(input_modes_row.classes)}",
            )

        def _build_vim_indicator_text(self, vim_normal: bool | None) -> str:
            """Build a width-aware vim status line for the input meta panel."""
            width = self.size.width or (self.app.size.width if self.app else 120)
            if vim_normal is None:
                return "Vim off • /vim on"

            if vim_normal:
                if width < 92:
                    return "Normal • i/a • hjkl"
                if width < 120:
                    return "Normal • i/a insert • /vim off"
                return "Normal • i/a insert • hjkl • /vim off"

            if width < 92:
                return "Insert • Esc normal"
            return "Insert • Esc normal • /vim off"

        def _show_help_modal(self) -> None:
            """Show help information in a modal."""
            try:
                from massgen.frontend.interactive_controller import (
                    SlashCommandDispatcher,
                )

                command_help = SlashCommandDispatcher.build_help_text()
            except ImportError:
                command_help = "Help unavailable."

            help_text = f"""MassGen Textual UI Commands

SLASH COMMANDS:
{command_help}

KEYBOARD SHORTCUTS:
  Tab/←/→         - Navigate between agents
  Ctrl+G          - Show this help
  Ctrl+T          - Toggle task plan (collapse/expand)
  Ctrl+Shift+T    - Toggle light/dark theme
  Ctrl+P          - Toggle CWD context auto-include
  Ctrl+U          - Show subagents panel
  Ctrl+C          - Cancel current turn (double to quit)
  Ctrl+D          - Quit immediately

MODAL SHORTCUTS (when not typing):
  s               - System status log
  o               - Orchestrator events
  i               - Agent selector
  c               - Coordination table
  v               - Vote results

MODE BAR:
  Plan            - Normal → Planning → Execute → Analysis
  Agents          - Multi-agent or single-agent runs
  Coordination    - Parallel (vote) or decomposition (independent subtasks)
  Personas        - Toggle parallel persona generation + convergence prep view
  Subtasks        - Define per-agent subtasks (decomposition mode)
  Skills          - Open skills manager (source groups, custom/evolving toggles)
  Refine          - Keep iterative refinement/voting on or off
  ⋮               - Plan/analysis settings (depth, selector, profile, target)
  ?               - Open mode bar help
  Override        - Manually pick final presenter (when available)

TOOL CARDS:
  Click           - Expand/collapse tool card
  Double-click    - Open full detail modal

Type your question and press Enter to ask the agents.
"""
            self._show_modal_async(TextContentModal("MassGen Help", help_text))

        def _reset_agent_panels(self) -> None:
            """Reset agent panels for new question."""
            for agent_id, widget in self.agent_widgets.items():
                widget.content_log.clear()
                widget.update_status("waiting")
                widget._line_buffer = ""
                widget.current_line_label.update("")
                if agent_id in self._event_adapters:
                    try:
                        self._event_adapters[agent_id].reset()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")
                # Reset round state when doing full reset
                if hasattr(widget, "reset_round_state"):
                    widget.reset_round_state()
            self.notify("Agent panels reset", severity="information")

        def _update_all_loading_text(self, message: str) -> None:
            """Update loading text on all agent panels."""
            for widget in self.agent_widgets.values():
                widget._update_loading_text(message)

        async def _flush_buffers(self):
            """Flush buffered content to widgets.

            Uses frame-aware batching to prevent UI blocking:
            - Limits items processed per flush to max_buffer_batch (default 5)
            - Remaining items stay in buffer for next flush cycle
            """
            self._pending_flush = False
            all_updates = []
            # Debug: log buffer sizes
            for _aid in self.coordination_display.agent_ids:
                with self._buffer_lock:
                    blen = len(self._buffers.get(_aid, []))
                if blen > 0:
                    tui_log(f"[_flush_buffers] agent={_aid} buffer_size={blen}")
            max_items_per_agent = 5  # Limit to prevent blocking

            for agent_id in self.coordination_display.agent_ids:
                with self._buffer_lock:
                    if not self._buffers[agent_id]:
                        continue
                    # Take only max_items_per_agent items per flush
                    items_to_process = self._buffers[agent_id][:max_items_per_agent]
                    self._buffers[agent_id] = self._buffers[agent_id][max_items_per_agent:]

                if items_to_process and agent_id in self.agent_widgets:
                    all_updates.append((agent_id, items_to_process))

            if all_updates:
                with self.batch_update():
                    for agent_id, buffer_copy in all_updates:
                        for item in buffer_copy:
                            await self.update_agent_widget(
                                agent_id,
                                item["content"],
                                item.get("type", "thinking"),
                                item.get("tool_call_id"),
                            )
                            if item.get("force_jump"):
                                widget = self.agent_widgets.get(agent_id)
                                if widget:
                                    widget.jump_to_latest()

        def request_flush(self):
            """Request a near-immediate flush (debounced)."""
            if self._pending_flush:
                return
            self._pending_flush = True
            try:
                if threading.get_ident() == getattr(self, "_thread_id", None):
                    self.call_later(self._flush_buffers)
                else:
                    self.call_from_thread(self._flush_buffers)
            except Exception:
                self._pending_flush = False

        def _show_modal_async(self, modal: ModalScreen) -> None:
            """Display a modal screen asynchronously."""

            async def _show():
                await self.push_screen(modal)

            self.call_later(lambda: self.run_worker(_show()))

        def _show_decomposition_generation_modal(self, status: str, detail: str = "") -> None:
            """Open (or update) runtime decomposition progress modal."""
            if self._decomposition_generation_modal:
                self._decomposition_generation_modal.update_progress(status, detail)
                return

            modal = DecompositionGenerationModal(status=status, detail=detail)
            self._decomposition_generation_modal = modal
            self._runtime_decomposition_subtasks = {}
            self._decomposition_completion_source = "subagent"

            def _on_dismiss(_result: Any = None) -> None:
                self._decomposition_generation_modal = None

            self.push_screen(modal, _on_dismiss)

        def _show_chunk_advance_modal(
            self,
            completed_chunk: str,
            next_chunk: str,
            auto_continue: bool = True,
        ) -> None:
            """Show chunk transition modal and optionally auto-continue execution."""
            if self._mode_state.plan_mode != "execute":
                return

            modal = ChunkAdvanceModal(
                completed_chunk=completed_chunk,
                next_chunk=next_chunk,
                auto_continue=auto_continue,
                countdown_seconds=2,
            )

            def _on_dismiss(should_continue: Any = None) -> None:
                if self._mode_state.plan_mode != "execute":
                    return
                if should_continue:
                    self.notify(
                        f"Continuing with next chunk: {next_chunk}",
                        severity="information",
                        timeout=2,
                    )
                    if hasattr(self, "question_input") and self.question_input:
                        self.question_input.value = next_chunk

                    def _submit_next() -> None:
                        if self._mode_state.plan_mode != "execute":
                            return
                        self._submit_question(
                            next_chunk,
                            bypass_execution_queue=True,
                        )

                    self.call_later(_submit_next)
                else:
                    self.notify(
                        f"Paused after chunk {completed_chunk}. Next ready: {next_chunk}",
                        severity="warning",
                        timeout=3,
                    )

            self.push_screen(modal, _on_dismiss)

        def _dismiss_decomposition_generation_modal(self) -> None:
            """Dismiss decomposition progress modal if present."""
            if not self._decomposition_generation_modal:
                return
            try:
                self._decomposition_generation_modal.dismiss()
            except Exception:
                pass

        def handle_preparation_status(self, status: str, detail: str = "") -> None:
            """Handle orchestrator preparation status updates in Textual mode."""
            message = status if not detail else f"{status} — {detail}"
            self._update_all_loading_text(message)

            lower_status = (status or "").lower()
            lower_detail = (detail or "").lower()
            is_decomposition = "decompos" in lower_status or "decompos" in lower_detail or "subtask" in lower_status or "subtask" in lower_detail
            if not is_decomposition:
                return

            if "decomposing task" in lower_status:
                # Decomposition now uses the dedicated subagent screen path.
                # Keep loading text in panels, but avoid showing the legacy modal.
                self._dismiss_decomposition_generation_modal()
                return

            if lower_status in ("decomposition ready", "decomposition fallback"):
                decomp_state = self._precollab_subagents.get("task_decomposition")
                if decomp_state and decomp_state.call_id:
                    self._dismiss_decomposition_generation_modal()
                    return
                self._decomposition_completion_source = "subagent" if "ready" in lower_status else "fallback"
                if self._decomposition_generation_modal:
                    self._decomposition_generation_modal.update_progress(status, detail)
                    # If subtasks already arrived, render and auto-dismiss.
                    if self._runtime_decomposition_subtasks:
                        self._decomposition_generation_modal.show_subtasks(
                            self._runtime_decomposition_subtasks,
                            source=self._decomposition_completion_source,
                        )
                        self.set_timer(2.5, self._dismiss_decomposition_generation_modal)
                    else:
                        # Guard against stale modals if no explicit subtasks are emitted.
                        self.set_timer(3.0, self._dismiss_decomposition_generation_modal)

        async def update_agent_widget(
            self,
            agent_id: str,
            content: str,
            content_type: str,
            tool_call_id: str | None = None,
        ):
            """Update agent widget with content."""
            if agent_id not in self.agent_widgets:
                tui_log(f"[update_agent_widget] SKIP agent={agent_id} not in agent_widgets")
                return

            # Tool content is handled via structured TOOL_START/TOOL_COMPLETE events
            # from _handle_event_from_emitter. Skip it here to avoid duplicates.
            if content_type == "tool":
                return

            # All TUI content is handled via structured events routed through
            # _handle_event_from_emitter. This method is a no-op for Textual TUI.
            # Non-Textual displays still use update_agent_content directly.
            return

        def update_agent_status(self, agent_id: str, status: str):
            """Update agent status."""
            if hasattr(self, "_consensus_map_state"):
                self._consensus_map_state.set_agent_status(agent_id, status)
                self._refresh_consensus_map()
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].update_status(status)
                # Only jump to latest if this is the active agent
                if agent_id == self._active_agent_id:
                    self.agent_widgets[agent_id].jump_to_latest()
            # Also update the tab bar status badge
            if self._tab_bar:
                self._tab_bar.update_agent_status(agent_id, status)
            # NOTE: Activity indicator removed from ribbon - see Phase 13.2 for ExecutionStatusLine
            # Update StatusBar activity indicator with granular phase icons
            if self._status_bar:
                # Map status strings to activity types for phase icons
                STATUS_TO_ACTIVITY = {
                    # Thinking states
                    "working": "thinking",
                    "thinking": "thinking",
                    "processing": "thinking",
                    # Streaming states
                    "streaming": "streaming",
                    # Tool execution states
                    "tool_call": "tool",
                    "mcp_tool_called": "tool",
                    "custom_tool_called": "tool",
                    "mcp_tool_response": "thinking",  # After tool, back to thinking
                    "custom_tool_response": "thinking",
                    "mcp_tool_error": "error",
                    "custom_tool_error": "error",
                    # Voting states
                    "voting": "voting",
                    "voted": "waiting",  # After voting, waiting for others
                    # Waiting states
                    "waiting": "waiting",
                    # Completion states - "completed" means agent finished one task,
                    # but may still be active in coordination (voting, restart, etc.)
                    # Only truly idle when coordination is done
                    "error": "error",
                    "complete": "waiting",  # Completed one task, waiting for coordination
                    "completed": "waiting",  # Same - waiting, not truly idle
                    "idle": "idle",
                    "done": "idle",
                    "finished": "idle",  # Only explicit "idle"/"done"/"finished" = truly idle
                }
                activity = STATUS_TO_ACTIVITY.get(status, "thinking")  # Default to thinking if unknown
                self._status_bar.set_agent_activity(agent_id, activity)
                # Also maintain backwards compatibility with set_agent_working
                is_working = activity not in ("idle",)
                self._status_bar.set_agent_working(agent_id, is_working)

                # Trigger pulsing animation for active agents
                from massgen.logger_config import logger

                logger.info(f"[PULSE] update_agent_status: agent={agent_id}, status={status}, activity={activity}")
                if activity in ("thinking", "tool", "streaming"):
                    self._start_agent_pulse(agent_id)
                else:
                    self._stop_agent_pulse(agent_id)

            # Phase 13.2: Update ExecutionStatusLine with agent state
            if self._execution_status_line:
                # Map to ExecutionStatusLine states
                # "voted" = green checkmark (waiting for consensus)
                # "done" = dim checkmark (final presentation in progress)
                STATE_MAP = {
                    "working": "working",
                    "thinking": "working",
                    "streaming": "working",
                    "processing": "working",
                    "tool_call": "working",
                    "mcp_tool_called": "working",
                    "custom_tool_called": "working",
                    "mcp_tool_response": "working",
                    "custom_tool_response": "working",
                    "voting": "working",
                    "voted": "voted",  # Green checkmark - agent voted
                    "stopped": "stopped",  # Green checkmark - agent stopped (decomposition)
                    "waiting": "voted",  # Waiting for others after voting
                    "complete": "voted",  # Finished, waiting for consensus
                    "completed": "voted",
                    "done": "done",  # Dim checkmark - final presentation happening
                    "error": "error",
                    "cancelled": "cancelled",
                    "idle": "idle",
                }
                mapped_state = STATE_MAP.get(status, "working")
                self._execution_status_line.set_agent_state(agent_id, mapped_state)
            # Update execution status bar with new agent icons
            self._update_execution_status()

        def update_agent_timeout(self, agent_id: str, timeout_state: dict[str, Any]):
            """Update agent timeout display.

            Args:
                agent_id: The agent whose timeout to update
                timeout_state: Timeout state from orchestrator
            """
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].update_timeout(timeout_state)

            if self._status_bar:
                self._status_bar.set_timeout_state(agent_id, timeout_state)

            # Also update the status ribbon timeout display
            if self._status_ribbon:
                remaining = timeout_state.get("remaining_soft")
                self._status_ribbon.set_timeout(agent_id, remaining)
                self._status_ribbon.set_timeout_state(agent_id, timeout_state)

        def update_hook_execution(
            self,
            agent_id: str,
            tool_call_id: str | None,
            hook_info: dict[str, Any],
        ):
            """Update display with hook execution information.

            Args:
                agent_id: The agent whose tool call has hooks
                tool_call_id: Optional ID of the tool call
                hook_info: Hook execution info
            """
            from massgen.logger_config import logger

            logger.info(
                f"[MassGenApp] update_hook_execution: agent={agent_id}, " f"tool_call_id={tool_call_id}, has_widget={agent_id in self.agent_widgets}",
            )
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].add_hook_to_tool(tool_call_id, hook_info)
            else:
                logger.warning(f"[MassGenApp] Agent {agent_id} not in agent_widgets")

        def update_token_usage(self, agent_id: str, usage: dict[str, Any]):
            """Update token usage display for an agent.

            Phase 13.1: Wire token/cost updates to status ribbon.

            Args:
                agent_id: The agent whose token usage to update
                usage: Token usage dict with input_tokens, output_tokens, estimated_cost
            """
            if self._status_ribbon:
                total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                self._status_ribbon.set_tokens(agent_id, total_tokens)
                self._status_ribbon.set_cost(agent_id, usage.get("estimated_cost", 0))

        def add_orchestrator_event(self, event: str):
            """Add orchestrator event to internal tracking."""
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._orchestrator_events.append(f"{timestamp} {event}")

        def _update_winner_hints(self, winner_id: str) -> None:
            """Update winner hints on all agent timelines.

            Args:
                winner_id: The ID of the winning agent. Non-winners will show
                    a hint directing users to the winner's timeline.
            """
            for agent_id, panel in self.agent_widgets.items():
                try:
                    timeline = panel._get_timeline()
                    if timeline:
                        # Show hint on non-winners, hide on winner
                        timeline.show_winner_hint(show=(agent_id != winner_id))
                except Exception as e:
                    tui_log(
                        f"_update_winner_hints failed for agent={agent_id}, winner={winner_id}: {e}",
                        level="debug",
                    )

        def _get_precollab_subagent(
            self,
            subagent_id: str,
        ) -> Any | None:
            """Return latest data for a pre-collab subagent, refreshing via callback."""
            state = self._precollab_subagents.get(subagent_id)
            if not state:
                return None

            current = state.data
            callback = state.status_callback

            if callback:
                try:
                    refreshed = callback(subagent_id)
                    if refreshed is not None:
                        state.data = refreshed
                        current = refreshed
                except Exception:
                    pass

            if current is not None and getattr(current, "id", None) == subagent_id:
                return current
            return None

        def _open_precollab_screen(
            self,
            subagent_id: str,
            auto_return_on_completion: bool = False,
        ) -> bool:
            """Open the SubagentScreen for a pre-collab subagent.

            Returns:
                True if a screen was opened, False otherwise.
            """
            subagent = self._get_precollab_subagent(subagent_id)
            if not subagent:
                return False

            screen = SubagentScreen(
                subagent=subagent,
                all_subagents=[subagent],
                status_callback=lambda sid=subagent_id: self._get_precollab_subagent(sid),
                auto_return_on_completion=auto_return_on_completion,
                send_message_callback=self._subagent_message_callback,
                continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
            )
            self.push_screen(screen)
            return True

        def _precollab_events_ready(self, subagent_id: str) -> bool:
            """Return True when a pre-collab subagent has enough event data for display.

            Readiness requires:
            - a readable events stream, and
            - detectable inner-agent identity data (metadata or event agent IDs/sources).
            """
            subagent = self._get_precollab_subagent(subagent_id)
            if not subagent:
                return False

            log_path_raw = getattr(subagent, "log_path", None)
            if not log_path_raw:
                return False

            try:
                from massgen.subagent.models import SubagentResult

                log_path = Path(log_path_raw)
                if not log_path.is_absolute():
                    log_path = (Path.cwd() / log_path).resolve()

                events_path: Path | None = None
                if log_path.is_file():
                    events_path = log_path
                elif log_path.is_dir():
                    resolved = SubagentResult.resolve_events_path(log_path)
                    if resolved:
                        events_path = Path(resolved)

                if not events_path or not events_path.exists():
                    return False
                if events_path.stat().st_size <= 0:
                    return False

                # Prefer explicit metadata signal (same source SubagentScreen uses).
                metadata_candidates = [events_path.parent / "execution_metadata.yaml"]
                if log_path.is_dir():
                    metadata_candidates.extend(
                        [
                            log_path / "full_logs" / "execution_metadata.yaml",
                            log_path / "execution_metadata.yaml",
                        ],
                    )
                else:
                    metadata_candidates.append(log_path.parent / "execution_metadata.yaml")

                for candidate in metadata_candidates:
                    if not candidate.exists():
                        continue
                    try:
                        import yaml

                        with open(candidate, encoding="utf-8") as f:
                            metadata = yaml.safe_load(f) or {}
                        agents_cfg = (metadata.get("config") or {}).get("agents") or []
                        if isinstance(agents_cfg, list):
                            agent_ids = [a.get("id") for a in agents_cfg if isinstance(a, dict) and isinstance(a.get("id"), str) and a.get("id")]
                            if agent_ids:
                                return True
                    except Exception:
                        continue

                # Fallback: scan recent event lines for inner-agent sources.
                # Exclude the subagent's own ID from the "seen agents" set.
                excluded_sources = {"mcp_setup", "mcp_session", "orchestrator", "system", subagent_id}

                def _is_agent_source(source: str | None) -> bool:
                    if not source:
                        return False
                    lowered = source.lower()
                    if lowered.startswith("mcp_") or lowered.startswith("mcp__") or "mcp__" in lowered:
                        return False
                    if lowered in excluded_sources:
                        return False
                    return True

                try:
                    import json

                    tail_lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-400:]
                    seen_agents: set[str] = set()
                    for raw in tail_lines:
                        if not raw.strip():
                            continue
                        try:
                            event = json.loads(raw)
                        except Exception:
                            continue

                        agent_id = event.get("agent_id")
                        if isinstance(agent_id, str) and _is_agent_source(agent_id):
                            seen_agents.add(agent_id)

                        data = event.get("data") if isinstance(event.get("data"), dict) else {}
                        source = data.get("source") if isinstance(data, dict) else None
                        if not source and isinstance(data, dict):
                            chunk = data.get("chunk")
                            if isinstance(chunk, dict):
                                source = chunk.get("source")
                        if isinstance(source, str) and _is_agent_source(source):
                            seen_agents.add(source)

                    if seen_agents:
                        return True
                except Exception:
                    return False

                return False
            except Exception:
                return False

        def _auto_open_precollab_screen(self, subagent_id: str, attempt: int = 0) -> None:
            """Auto-open a pre-collab subagent screen once event data is available."""
            if self._precollab_events_ready(subagent_id):
                self._open_precollab_screen(subagent_id, auto_return_on_completion=True)
                return

            # Retry for a short window; avoid forcing an early empty screen.
            if attempt >= 120:
                return

            self.set_timer(
                0.1,
                lambda sid=subagent_id, a=attempt: self._auto_open_precollab_screen(sid, a + 1),
            )

        def _try_open_unified_precollab_screen(self, attempt: int = 0) -> None:
            """Wait for all expected parallel pre-collabs to register, then open unified screen."""
            if self._parallel_precollab_screen_opened:
                return

            registered = set(self._precollab_subagents.keys()) & _PARALLEL_PRECOLLAB_IDS

            if self._parallel_precollab_expected:
                # Batch info available — wait for all expected
                target = self._parallel_precollab_expected
            elif attempt < 10:
                # Batch info not yet available — wait briefly for it
                self.set_timer(
                    0.1,
                    lambda a=attempt: self._try_open_unified_precollab_screen(a + 1),
                )
                return
            else:
                # Timeout waiting for batch info — use whatever registered
                target = registered

            if target.issubset(registered):
                self._open_unified_precollab_screen()
                return

            # Retry up to ~5s (50 * 100ms)
            if attempt >= 50:
                # Timeout — open with whatever is available
                self._open_unified_precollab_screen()
                return

            self.set_timer(
                0.1,
                lambda a=attempt: self._try_open_unified_precollab_screen(a + 1),
            )

        def _open_unified_precollab_screen(self) -> None:
            """Open a single SubagentScreen with tabs for all parallel pre-collab subagents."""
            if self._parallel_precollab_screen_opened:
                return
            self._parallel_precollab_screen_opened = True

            from massgen.subagent.models import SubagentDisplayData

            # Collect all parallel pre-collab SubagentDisplayData, preserving order.
            # Use _parallel_precollab_expected if available, else fall back to
            # whatever parallel IDs are registered (handles the race where the
            # batch event hasn't arrived yet).
            expected = self._parallel_precollab_expected or (set(self._precollab_subagents.keys()) & _PARALLEL_PRECOLLAB_IDS)
            subagents: list = []
            for sid in ("persona_generation", "criteria_generation", "prompt_improvement"):
                if sid not in expected:
                    continue
                state = self._precollab_subagents.get(sid)
                if state and state.data:
                    # Create a copy with a friendly display name as subagent_type
                    display_name = _PRECOLLAB_DISPLAY_NAMES.get(sid, sid)
                    data = state.data
                    subagent = SubagentDisplayData(
                        id=sid,
                        task=data.task,
                        status=data.status,
                        progress_percent=data.progress_percent,
                        elapsed_seconds=data.elapsed_seconds,
                        timeout_seconds=data.timeout_seconds,
                        workspace_path=data.workspace_path,
                        workspace_file_count=data.workspace_file_count,
                        last_log_line=data.last_log_line,
                        error=data.error,
                        answer_preview=data.answer_preview,
                        log_path=data.log_path,
                        subagent_type=display_name,
                    )
                    subagents.append(subagent)

            if not subagents:
                self._parallel_precollab_screen_opened = False
                return

            # Wait for at least one to have event data ready (up to ~12s)
            self._wait_and_open_unified_screen(subagents, attempt=0)

        def _wait_and_open_unified_screen(self, subagents: list, attempt: int = 0) -> None:
            """Wait for at least one pre-collab to have events, then push screen."""
            any_ready = any(self._precollab_events_ready(s.id) for s in subagents)

            if any_ready or attempt >= 120:
                screen = SubagentScreen(
                    subagent=subagents[0],
                    all_subagents=subagents,
                    status_callback=lambda sid: self._get_precollab_subagent(sid),
                    auto_return_on_completion=True,
                    send_message_callback=self._subagent_message_callback,
                    continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
                )
                self.push_screen(screen)
                return

            self.set_timer(
                0.1,
                lambda a=attempt: self._wait_and_open_unified_screen(subagents, a + 1),
            )

        def set_precollab_batch(self, pre_collab_ids: list[str]) -> None:
            """Set which parallel pre-collab subagents will run.

            Called by the orchestrator via direct display callback BEFORE
            any pre-collab subagent starts, ensuring the unified screen
            logic is ready before show_runtime_subagent_card fires.
            """
            self._parallel_precollab_expected = set(pre_collab_ids)
            self._parallel_precollab_screen_opened = False

        def show_runtime_subagent_card(
            self,
            agent_id: str,
            subagent_id: str,
            task: str,
            timeout_seconds: int,
            call_id: str,
            status_callback: Callable[[str], Any | None] | None = None,
            log_path: str | None = None,
            round_number: int | None = None,
            _retry_count: int = 0,
        ) -> None:
            """Render a subagent card for orchestrator-owned runtime subagents."""
            from massgen.subagent.models import SubagentDisplayData

            # Pre-collab subagents (persona, decomposition, criteria) should not
            # appear in the main timeline — they open directly in a full-screen view.
            if subagent_id in _PRECOLLAB_SUBAGENT_IDS:
                trimmed_task = (task or "").strip()
                if len(trimmed_task) > 300:
                    trimmed_task = trimmed_task[:297] + "..."

                resolved_log_path = log_path
                if not resolved_log_path:
                    try:
                        log_dir = get_log_session_dir()
                        if log_dir:
                            resolved_log_path = str(log_dir / "subagents" / subagent_id)
                    except Exception:
                        resolved_log_path = None

                state = self._precollab_subagents.get(subagent_id)
                if not state:
                    state = _PrecollabSubagentState()
                    self._precollab_subagents[subagent_id] = state

                state.call_id = call_id
                state.agent_id = agent_id
                state.status_callback = status_callback
                state.data = SubagentDisplayData(
                    id=subagent_id,
                    task=trimmed_task,
                    status="running",
                    progress_percent=0,
                    elapsed_seconds=0.0,
                    timeout_seconds=float(timeout_seconds or 300),
                    workspace_path="",
                    workspace_file_count=0,
                    last_log_line="Starting...",
                    error=None,
                    answer_preview=None,
                    log_path=resolved_log_path,
                )

                if subagent_id == "task_decomposition":
                    self._dismiss_decomposition_generation_modal()

                if not state.auto_opened:
                    state.auto_opened = True
                    if subagent_id == "task_decomposition":
                        # Decomposition always gets its own screen (runs after parallel batch)
                        self.set_timer(0.05, lambda sid=subagent_id: self._auto_open_precollab_screen(sid))
                    elif subagent_id in _PARALLEL_PRECOLLAB_IDS:
                        # Any parallel pre-collab uses the unified screen path,
                        # regardless of whether the batch event has arrived yet.
                        self._try_open_unified_precollab_screen()
                    else:
                        # Fallback for unknown pre-collab IDs
                        self.set_timer(0.05, lambda sid=subagent_id: self._auto_open_precollab_screen(sid))
                return

            target_agent = agent_id if agent_id in self.agent_widgets else None
            if not target_agent:
                if self._active_agent_id in self.agent_widgets:
                    target_agent = self._active_agent_id
                elif self.coordination_display.agent_ids:
                    candidate = self.coordination_display.agent_ids[0]
                    if candidate in self.agent_widgets:
                        target_agent = candidate

            if not target_agent:
                if _retry_count < 8:
                    self.set_timer(
                        0.1,
                        lambda: self.show_runtime_subagent_card(
                            agent_id=agent_id,
                            subagent_id=subagent_id,
                            task=task,
                            timeout_seconds=timeout_seconds,
                            call_id=call_id,
                            status_callback=status_callback,
                            log_path=log_path,
                            round_number=round_number,
                            _retry_count=_retry_count + 1,
                        ),
                    )
                return

            trimmed_task = (task or "").strip()
            if len(trimmed_task) > 300:
                trimmed_task = trimmed_task[:297] + "..."

            resolved_log_path = log_path
            if not resolved_log_path:
                try:
                    log_dir = get_log_session_dir()
                    if log_dir:
                        resolved_log_path = str(log_dir / "subagents" / subagent_id)
                except Exception:
                    resolved_log_path = None

            subagent = SubagentDisplayData(
                id=subagent_id,
                task=trimmed_task,
                status="running",
                progress_percent=0,
                elapsed_seconds=0.0,
                timeout_seconds=float(timeout_seconds or 300),
                workspace_path="",
                workspace_file_count=0,
                last_log_line="Starting...",
                error=None,
                answer_preview=None,
                log_path=resolved_log_path,
            )

            panel = self.agent_widgets.get(target_agent)
            if not panel:
                if _retry_count < 8:
                    self.set_timer(
                        0.1,
                        lambda: self.show_runtime_subagent_card(
                            agent_id=agent_id,
                            subagent_id=subagent_id,
                            task=task,
                            timeout_seconds=timeout_seconds,
                            call_id=call_id,
                            status_callback=status_callback,
                            log_path=log_path,
                            round_number=round_number,
                            _retry_count=_retry_count + 1,
                        ),
                    )
                return

            # Ensure timeline cards are visible during prep (not masked by loading panel).
            try:
                panel._hide_loading()
            except Exception:
                pass

            try:
                timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
            except Exception:
                if _retry_count < 8:
                    self.set_timer(
                        0.1,
                        lambda: self.show_runtime_subagent_card(
                            agent_id=agent_id,
                            subagent_id=subagent_id,
                            task=task,
                            timeout_seconds=timeout_seconds,
                            call_id=call_id,
                            status_callback=status_callback,
                            log_path=log_path,
                            round_number=round_number,
                            _retry_count=_retry_count + 1,
                        ),
                    )
                return

            card_id = _subagent_card_dom_id(call_id)
            card: SubagentCard | None = None
            try:
                card = timeline.query_one(f"#{card_id}", SubagentCard)
            except Exception:
                card = None

            if card:
                card.update_subagents([subagent])
                if status_callback:
                    card.set_status_callback(status_callback)
            else:
                card = SubagentCard(
                    subagents=[subagent],
                    tool_call_id=call_id,
                    status_callback=status_callback,
                    id=card_id,
                )
                effective_round = (
                    round_number
                    if round_number is not None
                    else max(
                        1,
                        int(getattr(panel, "_current_round", getattr(timeline, "_viewed_round", 1)) or 1),
                    )
                )
                timeline.add_widget(card, round_number=effective_round)

        def update_runtime_subagent_card(
            self,
            agent_id: str,
            subagent_id: str,
            call_id: str,
            status: str,
            answer_preview: str | None = None,
            error: str | None = None,
        ) -> None:
            """Update status/result info for an orchestrator-owned runtime subagent."""
            from massgen.subagent.models import SubagentDisplayData

            status_map = {
                "running": "running",
                "pending": "pending",
                "completed": "completed",
                "timeout": "timeout",
                "failed": "failed",
                "error": "error",
                "cancelled": "canceled",
                "canceled": "canceled",
                "stopped": "canceled",
            }
            normalized_status = status_map.get((status or "").lower(), "failed")

            # Pre-collab subagents are not rendered in the timeline — keep status
            # in memory so Ctrl+U and the dedicated subagent screen still work.
            if subagent_id in _PRECOLLAB_SUBAGENT_IDS:
                pc_state = self._precollab_subagents.get(subagent_id)
                if not pc_state:
                    return

                existing = self._get_precollab_subagent(subagent_id) or pc_state.data
                if existing is not None:
                    pc_state.data = SubagentDisplayData(
                        id=existing.id,
                        task=existing.task,
                        status=normalized_status,
                        progress_percent=100 if normalized_status in ("completed", "timeout", "failed", "error", "canceled") else existing.progress_percent,
                        elapsed_seconds=existing.elapsed_seconds,
                        timeout_seconds=existing.timeout_seconds,
                        workspace_path=existing.workspace_path,
                        workspace_file_count=existing.workspace_file_count,
                        last_log_line=existing.last_log_line,
                        error=error or existing.error,
                        answer_preview=answer_preview or existing.answer_preview,
                        log_path=existing.log_path,
                        context_paths=list(getattr(existing, "context_paths", []) or []),
                    )

                if call_id == pc_state.call_id and normalized_status in ("completed", "timeout", "failed", "error", "canceled"):
                    pc_state.call_id = None
                    pc_state.agent_id = None
                return

            # Resolve target agent — check pre-collab states for call_id ownership.
            target_agent = agent_id
            for pc_state in self._precollab_subagents.values():
                if call_id == pc_state.call_id and pc_state.agent_id:
                    target_agent = pc_state.agent_id
                    break

            panel = self.agent_widgets.get(target_agent)
            if not panel:
                return

            try:
                timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
            except Exception:
                return

            card_id = _subagent_card_dom_id(call_id)
            try:
                card = timeline.query_one(f"#{card_id}", SubagentCard)
            except Exception:
                return

            existing = None
            for sa in card.subagents:
                if sa.id == subagent_id:
                    existing = sa
                    break

            if existing is None:
                return

            final_progress = 100 if normalized_status in ("completed", "timeout", "failed", "error", "canceled") else existing.progress_percent
            updated = SubagentDisplayData(
                id=existing.id,
                task=existing.task,
                status=normalized_status,
                progress_percent=final_progress,
                elapsed_seconds=existing.elapsed_seconds,
                timeout_seconds=existing.timeout_seconds,
                workspace_path=existing.workspace_path,
                workspace_file_count=existing.workspace_file_count,
                last_log_line=existing.last_log_line,
                error=error or existing.error,
                answer_preview=answer_preview or existing.answer_preview,
                log_path=existing.log_path,
                context_paths=list(getattr(existing, "context_paths", []) or []),
            )
            card.update_subagent(subagent_id, updated)

            # Clear call ownership on terminal status for any pre-collab state.
            if normalized_status in ("completed", "timeout", "failed", "error", "canceled"):
                for pc_state in self._precollab_subagents.values():
                    if call_id == pc_state.call_id:
                        pc_state.call_id = None
                        pc_state.agent_id = None
                        break

        def show_subagent_card_from_spawn(
            self,
            agent_id: str,
            args: dict[str, Any],
            call_id: str,
        ):
            """Show SubagentCard immediately when spawn_subagents is called.

            This is called from a background thread via notify_subagent_spawn_started,
            BEFORE the blocking MCP tool execution begins. This allows showing the
            SubagentCard with pending subagents immediately rather than waiting
            for tool completion.

            Args:
                agent_id: ID of the agent spawning subagents
                args: Tool arguments containing tasks list
                call_id: Tool call ID for card identification
            """
            from massgen.subagent.models import SubagentDisplayData

            tui_log(f"show_subagent_card_from_spawn: agent_id={agent_id}, call_id={call_id}")

            # Validate we have tasks in args
            tasks = args.get("tasks", [])
            if not tasks:
                tui_log("show_subagent_card_from_spawn: no tasks in args")
                return

            tui_log(f"show_subagent_card_from_spawn: creating card for {len(tasks)} tasks")

            # Resolve base log directory for subagents in this session
            subagent_logs_base = None
            try:
                from massgen.logger_config import get_log_session_dir

                log_dir = get_log_session_dir()
                if log_dir:
                    subagent_logs_base = log_dir / "subagents"
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Create SubagentDisplayData for each task (all pending/running)
            subagents = []
            for i, task_data in enumerate(tasks):
                subagent_id = task_data.get("subagent_id", task_data.get("id", f"pending_{call_id}_{i}"))
                task_desc = task_data.get("task", "")
                log_path = str(subagent_logs_base / subagent_id) if subagent_logs_base else None
                context_paths = _normalize_subagent_context_paths(task_data.get("context_paths", []))
                subagent_type = _normalize_subagent_type(task_data.get("subagent_type"))

                subagents.append(
                    SubagentDisplayData(
                        id=subagent_id,
                        task=task_desc,
                        status="running",  # All start as running
                        progress_percent=0,
                        elapsed_seconds=0.0,
                        timeout_seconds=task_data.get("timeout_seconds", 300),
                        workspace_path="",  # Not yet assigned
                        workspace_file_count=0,
                        last_log_line="Starting...",
                        error=None,
                        answer_preview=None,
                        log_path=log_path,
                        context_paths=context_paths,
                        subagent_type=subagent_type,
                    ),
                )

            if not subagents:
                return

            # Get the agent's timeline and add the card
            if agent_id in self.agent_widgets:
                panel = self.agent_widgets[agent_id]
                try:
                    try:
                        panel._hide_loading()
                    except Exception:
                        pass
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)

                    # Flush any pending tool batch so the card appears
                    # after all preceding tools in chronological order
                    if hasattr(panel, "_batch_tracker") and panel._batch_tracker:
                        panel._batch_tracker.mark_content_arrived()
                        panel._batch_tracker.finalize_current_batch()

                    # Remove stale duplicate card for the same tool call only.
                    card_dom_id = _subagent_card_dom_id(call_id)
                    try:
                        for old_card in list(timeline.query(SubagentCard)):
                            old_id = getattr(old_card, "id", "")
                            old_tool_call_id = getattr(old_card, "tool_call_id", None) or getattr(old_card, "_tool_call_id", None)
                            if old_id == card_dom_id or str(old_tool_call_id) == str(call_id):
                                old_card.remove()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

                    round_number = max(
                        1,
                        int(getattr(panel, "_current_round", getattr(timeline, "_viewed_round", 1)) or 1),
                    )

                    # Create and add SubagentCard to timeline
                    card = SubagentCard(
                        subagents=subagents,
                        tool_call_id=call_id,
                        status_callback=None,
                        id=card_dom_id,
                    )

                    status_callback = None
                    try:
                        try:
                            status_callback = self._build_spawn_status_callback(
                                agent_id=agent_id,
                                seed_subagents=subagents,
                                card=card,
                            )
                        except TypeError:
                            # Backward compatibility for tests/overrides that still expose
                            # the older two-argument callback builder shape.
                            status_callback = self._build_spawn_status_callback(
                                agent_id=agent_id,
                                seed_subagents=subagents,
                            )
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

                    if status_callback is not None:
                        try:
                            card.set_status_callback(status_callback)
                        except Exception as e:
                            tui_log(f"[TextualDisplay] {e}")

                    timeline.add_widget(card, round_number=round_number)
                    tui_log(
                        f"show_subagent_card_from_spawn: added SubagentCard with {len(subagents)} pending subagents",
                    )
                except Exception as e:
                    tui_log(f"show_subagent_card_from_spawn: failed to add card: {e}")
            else:
                tui_log(f"show_subagent_card_from_spawn: agent {agent_id} not in agent_widgets")

        def show_final_presentation(
            self,
            answer: str,
            vote_results=None,
            selected_agent=None,
        ):
            """Display final answer modal with flush effect and winner celebration."""
            import time

            if not selected_agent:
                return

            # Track the winner
            self._winner_agent_id = selected_agent
            self._update_winner_hints(selected_agent)

            # Mark the winning answer(s) in tracked answers and extract workspace_path
            winner_workspace_path = None
            for ans in self._answers:
                if ans.get("agent_id") == selected_agent:
                    ans["is_winner"] = True
                    ans["is_final"] = True
                    # Get workspace_path from the most recent winning answer
                    if ans.get("workspace_path"):
                        winner_workspace_path = ans.get("workspace_path")

            # Add to conversation history
            if self._current_question and answer:
                model_name = self.coordination_display.agent_models.get(selected_agent, "")
                self._conversation_history.append(
                    {
                        "question": self._current_question,
                        "answer": answer,
                        "agent_id": selected_agent,
                        "model": model_name,
                        "turn": len(self._conversation_history) + 1,
                        "timestamp": time.time(),
                        "workspace_path": winner_workspace_path,
                    },
                )

            # Celebrate the winner
            self._celebrate_winner(selected_agent, answer)

            # Add completion card with the final answer
            self._add_final_completion_card(selected_agent, vote_results or {}, answer)

        def _add_final_completion_card(self, agent_id: str, vote_results: dict[str, Any], answer: str = ""):
            """Add completion card with the final answer at the end of final presentation.

            This card provides:
            - Final answer content
            - Vote summary
            - Action buttons (Copy, Workspace)
            - Continue conversation prompt
            """
            try:
                logger.info(
                    f"[FinalAnswer] _add_final_completion_card: agent_id={agent_id} " f"answer_len={len(answer)} vote_keys={list(vote_results.keys())}",
                )
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Prevent duplicate cards
            if hasattr(self, "_final_completion_added") and self._final_completion_added:
                return
            self._final_completion_added = True
            self._final_header_added = True  # Compat flag for other code paths

            # Track for post-evaluation routing
            self._final_presentation_agent = agent_id

            # 1. Auto-switch to winner's tab and mark with trophy
            if self._tab_bar:
                self._tab_bar.set_active(agent_id)
                self._tab_bar.set_winner(agent_id)

            # 2. Update ExecutionStatusLine: all agents to done
            if self._execution_status_line:
                for aid in self._execution_status_line._agent_ids:
                    self._execution_status_line.set_agent_state(aid, "done")

            # 3. Show the winner's panel (hide others)
            if agent_id in self.agent_widgets:
                if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                    self.agent_widgets[self._active_agent_id].add_class("hidden")
                self.agent_widgets[agent_id].remove_class("hidden")
                self._active_agent_id = agent_id

            if agent_id not in self.agent_widgets:
                return

            panel = self.agent_widgets[agent_id]

            try:
                timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)

                # Get coordination_tracker for answer label lookup
                tracker = None
                if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                    tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)

                # Build formatted vote results for the card
                vote_counts = vote_results.get("vote_counts", {})
                winner = vote_results.get("winner", agent_id)
                is_tie = vote_results.get("is_tie", False)

                def get_answer_label(aid):
                    """Convert agent ID to answer label (e.g., 'A1.1')."""
                    if tracker:
                        label = tracker.get_latest_answer_label(aid)
                        if label:
                            return label.replace("agent", "A")
                        num = tracker._get_agent_number(aid)
                        return f"A{num}" if num else aid
                    return aid

                # Build formatted vote results for the card
                formatted_vote_results = {
                    "vote_counts": {get_answer_label(aid): cnt for aid, cnt in vote_counts.items()},
                    "winner": get_answer_label(winner),
                    "is_tie": is_tie,
                }

                # Get context paths from orchestrator
                context_paths = {}
                if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                    orch = self.coordination_display.orchestrator
                    if hasattr(orch, "get_context_path_writes_categorized"):
                        context_paths = orch.get_context_path_writes_categorized()

                # Check if card already exists (may have been created by event pipeline)
                existing_cards = list(timeline.query("#final_presentation_card"))
                if existing_cards:
                    tui_log("[TextualDisplay] Final card already exists, reusing it")
                    card = existing_cards[0]
                    self._final_presentation_card = card
                    self.coordination_display._apply_pending_review_status(card)
                    if answer and not getattr(card, "_final_content", []):
                        card.append_chunk(answer)
                    card.complete()
                    return

                tui_log("[TextualDisplay] Creating new final presentation card")
                # Create the final answer card with content
                card = FinalPresentationCard(
                    agent_id=agent_id,
                    vote_results=formatted_vote_results,
                    context_paths=context_paths,
                    id="final_presentation_card",
                )

                # Tag with current round for CSS visibility switching
                current_round = getattr(panel, "_current_round", 1)
                card.add_class(f"round-{current_round}")

                # Use mount() directly to ensure card is always at the END of timeline
                # (add_widget uses round-based insertion which can place card before later content)
                timeline.mount(card)
                self._final_presentation_card = card
                self.coordination_display._apply_pending_review_status(card)

                # Stop the round timer - final presentation is the end state
                if self._status_ribbon:
                    self._status_ribbon.stop_all_round_timers()

                try:
                    logger.info(
                        f"[FinalAnswer] Timeline children after card add: {len(list(timeline.children))} " f"current_round={current_round}",
                    )
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

                # Set the answer content and mark as complete
                def set_content_and_complete():
                    # Only add content if card is empty (streaming may have already populated it)
                    if answer and not getattr(card, "_final_content", []):
                        card.append_chunk(answer)
                    card.complete()
                    try:
                        logger.info(
                            "[FinalAnswer] Card completed in timeline",
                        )
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")
                    # Auto-collapse task plan when final presentation shows
                    if hasattr(panel, "_task_plan_host"):
                        panel._task_plan_host.collapse()
                    # Update input placeholder to encourage follow-up
                    if hasattr(self, "question_input"):
                        self.question_input.placeholder = "Type your follow-up question..."

                self.set_timer(0.1, set_content_and_complete)

                # Scroll to show the card
                timeline.scroll_to_widget("final_presentation_card")

            except Exception as e:
                logger.debug(f"Failed to create final completion card: {e}")

        def show_post_evaluation(self, content: str, agent_id: str):
            """Show post-evaluation content in the FinalPresentationCard.

            Routes post-evaluation content to the unified card instead of
            using separate banners and timeline items.
            """
            import re

            # Route to the FinalPresentationCard if available
            if self._final_presentation_card:
                # Filter out JSON tool call content before passing to card
                if content:
                    stripped = content.strip()

                    # Skip JSON fragments and tool call content
                    json_indicators = [
                        '"action_type"',
                        '"submit_data"',
                        '"restart_data"',
                        '"action": "submit"',
                        '"confirmed": true',
                        '"confirmed":true',
                        '": "submit"',
                        '": "restart_orchestration"',
                    ]

                    is_json_fragment = any(ind in content for ind in json_indicators)

                    # Also skip lines that are just JSON syntax
                    is_json_syntax = stripped in ["{", "}", "```json", "```", '",', '",']
                    is_json_syntax = is_json_syntax or stripped.startswith('"action')
                    is_json_syntax = is_json_syntax or stripped.startswith('"confirmed')
                    is_json_syntax = is_json_syntax or stripped.startswith('"submit')
                    is_json_syntax = is_json_syntax or stripped.startswith('"restart')

                    if not is_json_fragment and not is_json_syntax:
                        # Filter out any remaining JSON blocks
                        clean_content = content

                        # Remove JSON code blocks
                        clean_content = re.sub(r"```json\s*\{[\s\S]*?\}\s*```", "", clean_content)

                        # Remove inline JSON objects with action_type
                        clean_content = re.sub(
                            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"action_type"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
                            "",
                            clean_content,
                            flags=re.DOTALL,
                        )

                        # Clean up any leftover JSON fragments
                        clean_content = re.sub(r"^\s*[\{\}]\s*$", "", clean_content, flags=re.MULTILINE)

                        clean_content = clean_content.strip()
                        if clean_content:
                            # Set status to evaluating and add content
                            self._final_presentation_card.set_post_eval_status("evaluating", clean_content)

            self.add_orchestrator_event(f"[POST-EVALUATION] {agent_id}: {content}")

        def show_post_evaluation_tool(self, tool_name: str, args: dict, agent_id: str):
            """Update FinalPresentationCard with post-evaluation tool decision.

            Args:
                tool_name: "submit" or "restart_orchestration"
                args: Tool arguments dict
                agent_id: The winner agent ID
            """
            # Update the FinalPresentationCard status based on tool decision
            if self._final_presentation_card:
                if tool_name == "submit":
                    self._final_presentation_card.set_post_eval_status("verified")
                elif tool_name == "restart_orchestration":
                    reason = args.get("reason", "No reason provided")
                    self._final_presentation_card.set_post_eval_status("restart", f"Reason: {reason}")

        def end_post_evaluation(self, agent_id: str):
            """Mark post-evaluation as complete via the FinalPresentationCard.

            This finalizes the card by:
            1. Marking post-eval as verified (if not already set to restart)
            2. Calling complete() to show footer with Copy/Workspace buttons
            3. Storing the final answer content for view-based navigation
            """
            # Finalize the FinalPresentationCard
            if self._final_presentation_card:
                # Mark as verified when post-eval completes (unless it's a restart request)
                if self._final_presentation_card._post_eval_status in ("none", "evaluating"):
                    self._final_presentation_card.set_post_eval_status("verified")

                # Auto-collapse task plan and update input when final answer shows
                if agent_id in self.agent_widgets:
                    panel = self.agent_widgets[agent_id]
                    try:
                        if hasattr(panel, "_task_plan_host"):
                            panel._task_plan_host.collapse()
                        if hasattr(self, "question_input"):
                            self.question_input.placeholder = "Type your follow-up question..."
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

                # Mark the card as complete (shows footer with buttons)
                self._final_presentation_card.complete()

                # Phase 12.4: Store final answer for view-based navigation
                if agent_id in self.agent_widgets:
                    panel = self.agent_widgets[agent_id]

                    # Get the final answer content from the card
                    final_content = getattr(self._final_presentation_card, "_answer_content", "")
                    vote_results = getattr(self._final_presentation_card, "_vote_results", {})

                    # Store for the FinalAnswerView
                    final_metadata = {
                        "winner": agent_id,
                        "vote_counts": vote_results.get("vote_counts", {}),
                        "total_rounds": panel.get_current_round(),
                        "agreement": sum(1 for v in vote_results.get("vote_counts", {}).values() if v > 0),
                        "total_agents": len(self.agent_widgets),
                    }
                    panel.set_final_answer(final_content, final_metadata)

                    # Mark all agents' ribbons as having final answer available
                    if self._status_ribbon:
                        for aid in self.agent_widgets:
                            self._status_ribbon.set_final_answer_available(aid, True)

                    try:
                        timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                        timeline._auto_scroll()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

        def begin_final_stream(self, agent_id: str, vote_results: dict[str, Any]):
            """DEPRECATED: Start final presentation streaming.

            This method is kept for backwards compatibility but is no longer the
            primary path. Use _add_final_completion_card() instead.

            Final presentation content now flows through the normal pipeline
            (update_agent_content), and a completion card is added at the end.
            """
            # Prevent duplicate cards - check if we've already started or if winner was quick-highlighted
            if hasattr(self, "_final_header_added") and self._final_header_added:
                return
            if hasattr(self, "_winner_quick_highlighted") and self._winner_quick_highlighted:
                # Winner already shown via highlight_winner_quick, skip adding another card
                # But still set up for streaming - the card was already created by highlight_winner_quick
                self._final_presentation_agent = agent_id
                self._final_header_added = True  # Prevent future duplicates
                if agent_id in self.agent_widgets:
                    panel = self.agent_widgets[agent_id]
                    try:
                        timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                        self._final_stream_timeline = timeline
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")
                return

            # Store the winner agent for routing chunks
            self._final_presentation_agent = agent_id
            self._final_presentation_card = None  # Will hold the FinalPresentationCard
            self._final_stream_timeline = None  # Track timeline for streaming
            self._final_header_added = True  # Track that card was added
            self._post_eval_header_added = False  # Reset post-eval tracking

            # 1. Auto-switch to winner's tab
            if self._tab_bar:
                self._tab_bar.set_active(agent_id)
                self._tab_bar.set_winner(agent_id)

            # 1.5. Update ExecutionStatusLine: dim checkmarks for non-presenting, dots for presenter
            if self._execution_status_line:
                for aid in self._execution_status_line._agent_ids:
                    if aid == agent_id:
                        # Presenting agent goes back to working dots
                        self._execution_status_line.set_agent_state(aid, "working")
                    else:
                        # Non-presenting agents get dim checkmark
                        self._execution_status_line.set_agent_state(aid, "done")

            # 2. Show the agent panel for the winner (remove hidden class)
            if agent_id in self.agent_widgets:
                if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                    self.agent_widgets[self._active_agent_id].add_class("hidden")
                self.agent_widgets[agent_id].remove_class("hidden")
                self._active_agent_id = agent_id

            # 3. Create FinalPresentationCard and add to timeline
            if agent_id in self.agent_widgets:
                panel = self.agent_widgets[agent_id]

                try:
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                    self._final_stream_timeline = timeline

                    # Check if card already exists (may have been created by event pipeline)
                    existing_cards = list(timeline.query("#final_presentation_card"))
                    if existing_cards:
                        tui_log("[TextualDisplay] begin_final_stream: card already exists, reusing")
                        self._final_presentation_card = existing_cards[0]
                        self.coordination_display._apply_pending_review_status(existing_cards[0])
                        timeline.scroll_to_widget("final_presentation_card")
                        return

                    # Get coordination_tracker for answer label lookup
                    tracker = None
                    if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                        tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)

                    # Build formatted vote results for the card
                    vote_counts = vote_results.get("vote_counts", {})
                    winner = vote_results.get("winner", agent_id)
                    is_tie = vote_results.get("is_tie", False)

                    def get_answer_label(aid):
                        """Convert agent ID to answer label (e.g., 'A1.1')."""
                        if tracker:
                            label = tracker.get_latest_answer_label(aid)
                            if label:
                                return label.replace("agent", "A")
                            # Fallback to agent number
                            num = tracker._get_agent_number(aid)
                            return f"A{num}" if num else aid
                        return aid

                    # Build formatted vote results for the card
                    formatted_vote_results = {
                        "vote_counts": {get_answer_label(aid): cnt for aid, cnt in vote_counts.items()},
                        "winner": get_answer_label(winner),
                        "is_tie": is_tie,
                    }

                    tui_log("[TextualDisplay] begin_final_stream: creating new card")
                    # Create the unified card
                    card = FinalPresentationCard(
                        agent_id=agent_id,
                        vote_results=formatted_vote_results,
                        id="final_presentation_card",
                    )
                    # Tag with current round for CSS visibility switching
                    current_round = getattr(panel, "_current_round", 1)
                    card.add_class(f"round-{current_round}")
                    # Note: Removed full-width-mode to allow tool cards to be visible
                    # during final presentation (was causing content cutoff issue)
                    # Use mount() directly to ensure card is always at the END of timeline
                    timeline.mount(card)
                    self._final_presentation_card = card
                    self.coordination_display._apply_pending_review_status(card)

                    # Scroll to show the card
                    timeline.scroll_to_widget("final_presentation_card")
                except Exception as e:
                    logger.debug(f"Failed to create final presentation card: {e}")

        def update_final_stream(self, chunk: str):
            """DEPRECATED: Append streaming chunks to the FinalPresentationCard.

            This method is kept for backwards compatibility but is no longer the
            primary path. Final presentation content now flows through the normal
            pipeline (update_agent_content).
            """
            if not chunk:
                return

            # Buffer chunks if card doesn't exist yet (race condition with highlight_winner_quick)
            if not self._final_presentation_card:
                if not hasattr(self, "_pending_final_chunks"):
                    self._pending_final_chunks = []
                self._pending_final_chunks.append(chunk)
                return

            # Flush any pending chunks first (from before card was created)
            if hasattr(self, "_pending_final_chunks") and self._pending_final_chunks:
                for pending_chunk in self._pending_final_chunks:
                    try:
                        self._final_presentation_card.append_chunk(pending_chunk)
                    except Exception as e:
                        logger.error(f"FinalPresentationCard.append_chunk (pending) failed: {e}")
                self._pending_final_chunks = []

            # Now append the current chunk
            try:
                self._final_presentation_card.append_chunk(chunk)
            except Exception as e:
                logger.error(f"FinalPresentationCard.append_chunk failed: {e}")

        def end_final_stream(self):
            """DEPRECATED: Mark the final presentation streaming as complete.

            This method is kept for backwards compatibility but is no longer the
            primary path. The completion card (with footer) is now added via
            _add_final_completion_card().
            """
            # Only end if we actually started
            if not getattr(self, "_final_header_added", False):
                return

            # Mark the card's streaming as complete (but don't show footer yet)
            # Footer will appear after post-evaluation via end_post_evaluation
            if self._final_presentation_card:
                # Don't call complete() yet - that shows footer
                # Just flush the buffer
                pass

            # Clear the streaming timeline reference (keep card for post-eval)
            self._final_stream_timeline = None

            if self.post_eval_panel and not self.coordination_display._post_evaluation_lines:
                self.post_eval_panel.hide()

        def highlight_winner_quick(self, winner_id: str, vote_results: dict[str, Any]) -> None:
            """Highlight the winner in no-refinement mode (skip_final_presentation).

            This is called when refinement is OFF, so we just mark the winner
            without streaming a new final presentation. The existing answer
            was already shown via new_answer tool cards.

            Args:
                winner_id: The winning agent's ID
                vote_results: Vote results dict with vote_counts, winner, is_tie, etc.
            """
            # Prevent duplicate highlighting or if final presentation already started
            if hasattr(self, "_winner_quick_highlighted") and self._winner_quick_highlighted:
                return
            if hasattr(self, "_final_header_added") and self._final_header_added:
                return  # Final presentation banner already added
            self._winner_quick_highlighted = True

            from massgen.events import EventType, MassGenEvent

            self._apply_consensus_event(
                MassGenEvent.create(
                    EventType.WINNER_SELECTED,
                    agent_id=winner_id,
                    vote_results=vote_results,
                ),
            )

            # 1. Auto-switch to winner's tab and mark with trophy
            if self._tab_bar:
                self._tab_bar.set_active(winner_id)
                self._tab_bar.set_winner(winner_id)

            # 1.5. Update ExecutionStatusLine: all agents to done (no streaming in quick mode)
            if self._execution_status_line:
                for aid in self._execution_status_line._agent_ids:
                    self._execution_status_line.set_agent_state(aid, "done")

            # 2. Show the winner's panel (hide others)
            if winner_id in self.agent_widgets:
                if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                    self.agent_widgets[self._active_agent_id].add_class("hidden")
                self.agent_widgets[winner_id].remove_class("hidden")
                self._active_agent_id = winner_id

            # 3. Add a "WINNER SELECTED" card to the winner's timeline using FinalPresentationCard
            if winner_id in self.agent_widgets:
                panel = self.agent_widgets[winner_id]
                try:
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)

                    # Get coordination_tracker for answer label lookup
                    tracker = None
                    if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                        tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)

                    # Build vote summary with answer labels (A1.1 format)
                    vote_counts = vote_results.get("vote_counts", {})
                    winner = vote_results.get("winner", winner_id)
                    is_tie = vote_results.get("is_tie", False)

                    def get_answer_label(aid):
                        """Convert agent ID to answer label (e.g., 'A1.1')."""
                        if tracker:
                            label = tracker.get_latest_answer_label(aid)
                            if label:
                                return label.replace("agent", "A")
                            # Fallback to agent number
                            num = tracker._get_agent_number(aid)
                            return f"A{num}" if num else aid
                        return aid

                    # Build formatted vote results for the card
                    formatted_vote_results = {
                        "vote_counts": {get_answer_label(aid): cnt for aid, cnt in vote_counts.items()},
                        "winner": get_answer_label(winner),
                        "is_tie": is_tie,
                    }

                    # Create the completion card (no streaming content - answer is already in timeline)
                    card = FinalPresentationCard(
                        agent_id=winner_id,
                        vote_results=formatted_vote_results,
                        id="winner_selected_card",
                    )
                    # Tag with current round for CSS visibility switching
                    card.add_class(f"round-{self._current_round}")
                    # Use completion-only mode - content already in timeline via normal pipeline
                    card.add_class("completion-only")
                    # Use mount() directly to ensure card is always at the END of timeline
                    timeline.mount(card)
                    self._final_presentation_card = card
                    self.coordination_display._apply_pending_review_status(card)

                    # Auto-collapse task plan and update input after card is added
                    def after_card_add():
                        try:
                            if hasattr(panel, "_task_plan_host"):
                                panel._task_plan_host.collapse()
                            if hasattr(self, "question_input"):
                                self.question_input.placeholder = "Type your follow-up question..."
                        except Exception as e:
                            tui_log(f"[TextualDisplay] {e}")

                    self.set_timer(0.1, after_card_add)

                    # Scroll to show the card
                    timeline.scroll_to_widget("winner_selected_card")

                    # Phase 12.4: Mark final answer as available for view-based navigation
                    # Note: Final answer content will be set via set_final_answer() when streaming completes
                    # For now, mark final answer as available in the ribbon
                    if self._status_ribbon:
                        self._status_ribbon.set_final_answer_available(winner_id, True)

                except Exception as e:
                    logger.debug(f"Failed to add winner selected card: {e}")

            # 4. Show toast notification
            self.notify(f"🏆 [bold]{winner_id}[/] selected as winner!", timeout=4)

        def clear_winner_state(self):
            """Reset winner highlighting and panel dimming for a new turn."""
            # Clear winner status from tab bar
            if self._tab_bar:
                self._tab_bar.clear_winner()

            # Undim all panels
            for panel in self.agent_widgets.values():
                panel.undim()

            # Reset final presentation tracking flags for the new turn
            self._final_header_added = False
            self._final_completion_added = False  # Reset completion card flag
            self._post_eval_header_added = False
            self._post_eval_footer_added = False
            self._final_stream_content = ""
            self._final_stream_timeline = None
            self._final_presentation_agent = None
            self._winner_quick_highlighted = False

        def prepare_for_new_turn(self, turn: int, previous_answer: str | None = None):
            """Fully reset the UI for a new turn while preserving conversation context.

            Args:
                turn: The new turn number (1-indexed)
                previous_answer: Optional summary of the previous turn's answer
            """
            from massgen.logger_config import logger

            logger.info(f"[TUI-App] prepare_for_new_turn() called: turn={turn}, has_previous_answer={previous_answer is not None}")
            # Clear winner state and flags
            self.clear_winner_state()
            logger.info("[TUI-App] Winner state cleared")

            # Reset status indicators so they animate for the new turn
            if self._status_bar:
                for agent_id in self._status_bar._agent_order:
                    self._status_bar.set_agent_activity(agent_id, "thinking")
            if self._execution_status_line:
                for agent_id in self._execution_status_line._agent_ids:
                    self._execution_status_line.set_agent_state(agent_id, "working")

            # Clear timeline content from all agent panels
            logger.info(f"[TUI-App] Clearing timelines for {len(self.agent_widgets)} agent panels")
            for agent_id, panel in self.agent_widgets.items():
                try:
                    logger.info(f"[TUI-App] Processing agent {agent_id}")
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                    logger.info(f"[TUI-App] Found timeline widget for {agent_id}")
                    # Clear the timeline content (add Round 1 only for turn 1)
                    timeline.clear(add_round_1=(turn == 1))
                    logger.info(f"[TUI-App] Timeline cleared for {agent_id}, add_round_1={turn == 1}")

                    # Add a turn separator banner if this is turn 2+
                    if turn > 1:
                        # Defer banner insertion until after clear() is fully processed.
                        # Textual removes children asynchronously, so immediate mounts can collide on IDs.
                        def _add_turn_banner(
                            agent_id: str = agent_id,
                            timeline: TimelineSection = timeline,
                            previous_answer: str | None = previous_answer,
                            turn: int = turn,
                        ) -> None:
                            logger.info(f"[TUI-App] Adding turn {turn} banner for {agent_id}")
                            from massgen.frontend.displays.textual_widgets.content_sections import (
                                RestartBanner,
                            )

                            # Create a turn separator that shows context from previous turn
                            separator_label = f"══════ Turn {turn} ══════"
                            turn_banner = RestartBanner(
                                label=separator_label,
                                id=f"turn_{turn}_separator",
                            )
                            turn_banner.add_class("turn-banner")
                            indicator = None
                            try:
                                from textual.widgets import Static

                                indicator = timeline.query_one("#scroll_mode_indicator", Static)
                            except Exception:
                                indicator = None
                            timeline.mount(turn_banner, after=indicator)
                            logger.info(f"[TUI-App] Turn banner added to timeline for {agent_id}")

                            # If we have a previous answer summary, show it collapsed
                            insert_after = turn_banner
                            if previous_answer:
                                logger.info(f"[TUI-App] Adding previous answer context for {agent_id}")
                                from textual.widgets import Static

                                summary = previous_answer[:200] + "..." if len(previous_answer) > 200 else previous_answer
                                context_widget = Static(
                                    f"[dim]Previous: {summary}[/]",
                                    id=f"turn_{turn}_context",
                                    markup=True,
                                )
                                context_widget.add_class("turn-context")
                                timeline.mount(context_widget, after=insert_after)
                                insert_after = context_widget

                            # CRITICAL: Add Round 1 separator BELOW the turn banner (and optional context)
                            # This ensures proper order: Turn X → [Context] → Round 1 → Content
                            logger.info(f"[TUI-App] Adding Round 1 separator for {agent_id}")
                            try:
                                if hasattr(timeline, "_pending_round_separators"):
                                    timeline._pending_round_separators.discard(1)
                                if hasattr(timeline, "_shown_round_banners"):
                                    timeline._shown_round_banners.discard(1)
                                if hasattr(timeline, "_round_1_shown"):
                                    timeline._round_1_shown = False
                            except Exception:
                                pass
                            try:
                                timeline.add_separator("Round 1", round_number=1, after=insert_after)
                                logger.info("[TUI-App] Round 1 separator added after turn banner/context")
                            except Exception as e:
                                logger.warning(f"[TUI-App] Failed to add Round 1 separator: {e}")
                                try:
                                    round_banner = RestartBanner(
                                        label="Round 1",
                                        id=f"turn_{turn}_round_1_separator",
                                    )
                                    round_banner.add_class("round-1")
                                    timeline.mount(round_banner, after=insert_after)
                                    if hasattr(timeline, "_shown_round_banners"):
                                        timeline._shown_round_banners.add(1)
                                    if hasattr(timeline, "_last_round_shown"):
                                        timeline._last_round_shown = max(timeline._last_round_shown, 1)
                                    if hasattr(timeline, "_round_1_shown"):
                                        timeline._round_1_shown = True
                                    logger.info("[TUI-App] Forced Round 1 separator mount (fallback)")
                                except Exception as e2:
                                    logger.warning(f"[TUI-App] Failed to force-mount Round 1 separator: {e2}")

                            # Scroll to the turn banner to show the new turn at the top
                            try:
                                turn_banner.scroll_visible()
                                logger.info(f"[TUI-App] Scrolled to turn banner for {agent_id}")
                            except Exception as e:
                                logger.warning(f"[TUI-App] Failed to scroll to turn banner for {agent_id}: {e}")

                        timeline.call_after_refresh(_add_turn_banner)

                except Exception as e:
                    logger.error(f"[TUI-App] Failed to prepare timeline for {agent_id}: {e}", exc_info=True)

            # Reset any modal state
            # (modals should auto-dismiss but just in case)

            # Scroll to top of timelines (only for turn 1, turn 2+ scrolls to turn banner)
            if turn == 1:
                logger.info("[TUI-App] Scrolling to top for turn 1")
                for panel in self.agent_widgets.values():
                    try:
                        timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)
                        timeline.scroll_home()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

            logger.info(f"[TUI-App] prepare_for_new_turn() complete for turn {turn}")

        def prepare_for_restart_attempt(
            self,
            attempt: int,
            max_attempts: int,
            reason: str = "",
            instructions: str = "",
        ):
            """Reset the UI for a restart attempt while keeping the app running.

            Unlike prepare_for_new_turn which clears timelines, this adds a restart
            separator to each agent panel so users see continuity between attempts.

            Args:
                attempt: The new attempt number (1-indexed).
                max_attempts: Total allowed attempts.
                reason: Why the restart was triggered.
                instructions: Instructions for the next attempt.
            """
            from massgen.logger_config import logger

            logger.info(
                f"[TUI-App] prepare_for_restart_attempt() called: " f"attempt={attempt}/{max_attempts}, reason={reason!r}",
            )
            self._skip_queued_fallback_once_after_restart = True

            # Clear winner state from previous attempt
            self.clear_winner_state()

            # Reset ribbon round state so rounds start fresh for this attempt
            if self._status_ribbon:
                self._status_ribbon.reset_round_state_all_agents()

            # Add restart separator to each agent panel
            for agent_id, panel in self.agent_widgets.items():
                try:
                    panel.show_restart_separator(attempt=attempt, reason=reason, instructions=instructions)
                    logger.info(f"[TUI-App] Restart separator added for {agent_id}")
                except Exception as e:
                    logger.warning(
                        f"[TUI-App] Failed to add restart separator for {agent_id}: {e}",
                    )

            # Show attempt counter in status bar
            if self._status_bar and hasattr(self._status_bar, "show_restart_count"):
                self._status_bar.show_restart_count(attempt, max_attempts)

            # Reset agent status indicators to thinking
            for agent_id in self.agent_widgets:
                self.set_agent_working(agent_id, working=True)

            # Preserve and re-render queued runtime injections so they still
            # inject in the restarted attempt instead of being treated as a new turn.
            self._refresh_human_input_pending_state()
            self._sync_queued_input_banner_from_hook()

            logger.info("[TUI-App] prepare_for_restart_attempt() complete")

        # =====================================================================
        # Multi-turn Lifecycle Methods
        # =====================================================================

        def update_turn_header(self, turn: int, question: str):
            """Update the header with new turn number and question.

            Args:
                turn: The turn number (1-indexed).
                question: The user's question for this turn.
            """
            try:
                main_container = self.query_one("#main_container", Container)
                main_container.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
            # Update tab bar session info (turn + question)
            if self._tab_bar:
                self._tab_bar.update_turn(turn)
                self._tab_bar.update_question(question)
            if turn > 1:
                from massgen.logger_config import logger

                logger.info(f"[TUI] update_turn_header called for turn {turn}")

                separator = f"\n{'='*50}\n   TURN {turn}\n{'='*50}\n"
                for agent_id, widget in self.agent_widgets.items():
                    if hasattr(widget, "content_log"):
                        widget.content_log.write(separator)

                # CRITICAL: Reset round state for all agents at the start of each new turn
                # This ensures rounds restart at R1 for the new turn
                logger.info(f"[TUI] Resetting round state for {len(self.agent_widgets)} agent panels")
                for agent_id, widget in self.agent_widgets.items():
                    if hasattr(widget, "reset_round_state"):
                        logger.info(f"[TUI] Calling reset_round_state() on panel for agent {agent_id}")
                        widget.reset_round_state()
                        logger.info(f"[TUI] After reset: panel._current_round={widget._current_round}, panel._viewed_round={widget._viewed_round}")

                # CRITICAL: Reset per-agent event adapters so new turn starts at Round 1
                if hasattr(self, "_event_adapters") and self._event_adapters:
                    logger.info(f"[TUI] Resetting {len(self._event_adapters)} TimelineEventAdapters for new turn")
                    for agent_id, adapter in self._event_adapters.items():
                        try:
                            adapter.reset()
                            adapter.set_round_number(1)
                        except Exception as e:
                            logger.warning(f"[TUI] Failed to reset adapter for {agent_id}: {e}")

                # CRITICAL: Reset status ribbon for all agents
                # The ribbon is at app level, not inside panels, so reset it directly
                if self._status_ribbon:
                    logger.info("[TUI] Resetting status ribbon for all agents")
                    self._status_ribbon.reset_round_state_all_agents()
                    logger.info("[TUI] Status ribbon reset complete")

                # CRITICAL: Reset turn-level state (answers, votes, buffers, etc.)
                # This ensures clean state for each new turn
                self.coordination_display.reset_turn_state()

        def update_improved_prompt(self, improved_prompt: str) -> None:
            """Store the improved/evolved prompt for display in the session info modal."""
            if self._tab_bar:
                self._tab_bar.update_improved_prompt(improved_prompt)

        def set_agent_subtasks(self, subtasks: dict[str, str]) -> None:
            """Pass agent subtask assignments to the tab bar for display.

            Args:
                subtasks: Mapping of agent_id to subtask description.
            """
            self._runtime_decomposition_subtasks = dict(subtasks or {})
            if self._tab_bar:
                self._tab_bar.set_agent_subtasks(subtasks)

            if self._decomposition_generation_modal:
                self._decomposition_generation_modal.show_subtasks(
                    self._runtime_decomposition_subtasks,
                    source=self._decomposition_completion_source,
                )
                self.set_timer(2.5, self._dismiss_decomposition_generation_modal)

        def set_agent_personas(self, personas: dict[str, str]) -> None:
            """Pass agent persona assignments to the tab bar for display."""
            self._runtime_parallel_personas = dict(personas or {})
            if self._tab_bar and self._mode_state.coordination_mode == "parallel" and self._mode_state.parallel_personas_enabled:
                self._tab_bar.set_agent_personas(self._runtime_parallel_personas)

        def set_evaluation_criteria(
            self,
            criteria: list[dict],
            source: str = "default",
        ) -> None:
            """Store the active evaluation criteria for display via Ctrl+E."""
            self._runtime_evaluation_criteria = list(criteria) if criteria else []
            self._runtime_evaluation_criteria_source = source

        def set_input_enabled(self, enabled: bool):
            """Enable or disable mode controls during execution.

            Note: The input field is NEVER disabled - users can always type.
            During execution, input is queued for injection via HumanInputHook.

            Args:
                enabled: True when idle (normal input), False during execution (input queued).
            """
            # NOTE: We intentionally do NOT disable question_input anymore.
            # Users can type during execution and input gets queued for injection.
            # The _submit_question method handles this queueing logic.

            # Lock/unlock mode controls during execution
            # Defensive: ensure lock is released even if error occurs
            try:
                if enabled:
                    self._mode_state.unlock()
                else:
                    self._mode_state.lock()
            except Exception as e:
                # Ensure lock is released even if error occurs
                logger.error(f"Error in set_input_enabled: {e}")
                try:
                    self._mode_state.unlock()
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")  # Best effort to recover
                raise

            # Update mode bar enabled state
            if self._mode_bar:
                self._mode_bar.set_enabled(enabled)

        def show_restart_banner(
            self,
            reason: str,
            instructions: str,
            attempt: int,
            max_attempts: int,
        ):
            """Show restart banner in header and all agent panels."""
            import time

            # Track the restart
            self._current_restart = {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "reason": reason,
                "instructions": instructions,
                "timestamp": time.time(),
                "answers_at_restart": [a["answer_label"] for a in self._answers],
            }
            self._restart_history.append(self._current_restart.copy())
            self._skip_queued_fallback_once_after_restart = True

            # Notify with toast so user knows restart is happening
            short_reason = reason[:50] + "..." if len(reason) > 50 else reason
            self.notify(
                f"🔄 [bold red]RESTART[/] — Attempt {attempt}/{max_attempts}\n   {short_reason}",
                severity="warning",
                timeout=8,
            )

            if self.header_widget:
                self.header_widget.show_restart_banner(
                    reason,
                    instructions,
                    attempt,
                    max_attempts,
                )

            # Update StatusBar to show restart count
            if self._status_bar:
                self._update_status_bar_restart_info()
                # Reset all agents to "thinking" state since they'll be working again
                for agent_id in self._status_bar._agent_order:
                    self._status_bar.set_agent_activity(agent_id, "thinking")

            # Show restart separator in ALL agent panels for within-turn restarts
            # (post-eval restarts are handled separately by prepare_for_restart_attempt)
            for agent_id, panel in self.agent_widgets.items():
                panel.show_restart_separator(attempt, reason)
                adapter = self._event_adapters.get(agent_id)
                if adapter:
                    try:
                        adapter.set_round_number(attempt)
                        adapter.flush()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

        def show_restart_context(self, reason: str, instructions: str):
            """Show restart context."""
            if self.header_widget:
                self.header_widget.show_restart_context(reason, instructions)

        def show_agent_restart(self, agent_id: str, round_num: int):
            """Show that a specific agent is starting a new round.

            This is called when an agent restarts due to new context from other agents.
            Only affects the specified agent's panel.

            Args:
                agent_id: The agent that is restarting
                round_num: The new round number for this agent
            """
            panel = self.agent_widgets.get(agent_id)
            if panel:
                # Use start_new_round which handles timeline visibility and ribbon update
                panel.start_new_round(round_num, is_context_reset=False)
                tui_log("DEBUG: MassGenApp.show_agent_restart called panel.start_new_round")
                adapter = self._event_adapters.get(agent_id)
                if adapter:
                    try:
                        adapter.set_round_number(round_num)
                        adapter.flush()
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

        def show_final_presentation_start(self, agent_id: str, vote_counts: dict[str, int] | None = None, answer_labels: dict[str, str] | None = None):
            """Show that the final presentation is starting for the winning agent.

            This shows a fresh view with a distinct "Final Presentation" banner.

            Args:
                agent_id: The winning agent presenting the final answer
                vote_counts: Optional dict of {agent_id: vote_count} for vote summary display
                answer_labels: Optional dict of {agent_id: label} for display (e.g., {"agent1": "A1.1"})
            """
            from massgen.events import EventType, MassGenEvent

            self._apply_consensus_event(
                MassGenEvent.create(
                    EventType.FINAL_PRESENTATION_START,
                    agent_id=agent_id,
                    vote_counts=vote_counts or {},
                    answer_labels=answer_labels or {},
                ),
            )
            panel = self.agent_widgets.get(agent_id)
            if panel:
                # Use start_final_presentation which shows distinct green banner
                panel.start_final_presentation(vote_counts=vote_counts, answer_labels=answer_labels)

        def display_vote_results(self, formatted_results: str):
            """Display vote results."""
            self.add_orchestrator_event("🗳️ Voting complete. Press 'v' to inspect details.")
            self._latest_vote_results_text = formatted_results
            self._show_modal_async(
                VoteResultsModal(
                    results_text=formatted_results,
                    vote_counts=self._vote_counts.copy() if hasattr(self, "_vote_counts") else None,
                    votes=self._votes.copy() if hasattr(self, "_votes") else None,
                ),
            )

        def display_coordination_table(self, table_text: str):
            """Display coordination table."""
            self._show_modal_async(CoordinationTableModal(table_text))

        def show_agent_selector(self):
            """Show agent selector modal."""
            modal = AgentSelectorModal(
                self.coordination_display.agent_ids,
                self.coordination_display,
                self,
            )
            self.push_screen(modal)

        def action_next_agent(self):
            """Switch to next agent tab, or select in dropdown if showing."""
            # If dropdown is showing, Tab selects the current item
            if hasattr(self, "_path_dropdown") and self._path_dropdown.is_showing:
                self._path_dropdown._select_current()
                return
            if self._tab_bar:
                next_agent = self._tab_bar.get_next_agent()
                if next_agent:
                    self._switch_to_agent(next_agent)

        def action_prev_agent(self):
            """Switch to previous agent tab."""
            if self._tab_bar:
                prev_agent = self._tab_bar.get_previous_agent()
                if prev_agent:
                    self._switch_to_agent(prev_agent)

        def action_go_to_winner(self):
            """Switch to the winner agent tab."""
            if self._winner_agent_id:
                self._switch_to_agent(self._winner_agent_id)

        def action_show_subagents(self):
            """Show subagent screen for first running subagent.

            Searches all agent panels for subagent cards and opens the screen
            for the first running subagent found (or first overall).
            """
            # Find subagent cards in all agent panels
            for panel in self.agent_widgets.values():
                try:
                    subagent_cards = panel.query(SubagentCard)
                    for card in subagent_cards:
                        if card.subagents:
                            # Find first running subagent
                            running = [sa for sa in card.subagents if sa.status == "running"]
                            if running:
                                screen = SubagentScreen(
                                    subagent=running[0],
                                    all_subagents=card.subagents,
                                    status_callback=self._build_subagent_status_callback(card),
                                    send_message_callback=self._subagent_message_callback,
                                    continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
                                )
                                self.push_screen(screen)
                                return
                            # Fallback to first subagent
                            screen = SubagentScreen(
                                subagent=card.subagents[0],
                                all_subagents=card.subagents,
                                status_callback=self._build_subagent_status_callback(card),
                                send_message_callback=self._subagent_message_callback,
                                continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
                            )
                            self.push_screen(screen)
                            return
                except Exception:
                    continue

            # Fallback: runtime preparation subagents (hidden from timeline by design)
            # Collect all available parallel pre-collab subagents for a unified screen.
            from massgen.subagent.models import SubagentDisplayData as _SDD

            parallel_subagents: list = []
            for sid in ("persona_generation", "criteria_generation", "prompt_improvement"):
                pc_state = self._precollab_subagents.get(sid)
                if pc_state and pc_state.data:
                    display_name = _PRECOLLAB_DISPLAY_NAMES.get(sid, sid)
                    data = pc_state.data
                    parallel_subagents.append(
                        _SDD(
                            id=sid,
                            task=data.task,
                            status=data.status,
                            progress_percent=data.progress_percent,
                            elapsed_seconds=data.elapsed_seconds,
                            timeout_seconds=data.timeout_seconds,
                            workspace_path=data.workspace_path,
                            workspace_file_count=data.workspace_file_count,
                            last_log_line=data.last_log_line,
                            error=data.error,
                            answer_preview=data.answer_preview,
                            log_path=data.log_path,
                            subagent_type=display_name,
                        ),
                    )

            if parallel_subagents:
                screen = SubagentScreen(
                    subagent=parallel_subagents[0],
                    all_subagents=parallel_subagents,
                    status_callback=lambda sid: self._get_precollab_subagent(sid),
                    send_message_callback=self._subagent_message_callback,
                    continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
                )
                self.push_screen(screen)
                return

            # task_decomposition gets its own screen
            if self._open_precollab_screen("task_decomposition"):
                return

            self.notify("No active subagents", severity="information", timeout=2)

        # Side panel methods removed - now using separate SubagentScreen
        # def _open_subagent_side_panel(
        #     self,
        #     subagent: SubagentDisplayData,
        #     all_subagents: List[SubagentDisplayData],
        # ) -> None:
        #     """Open the right-panel subagent view."""
        #     ...
        #
        # def _close_subagent_side_panel(self) -> None:
        #     """Close the right-panel subagent view."""
        #     ...

        def _switch_to_agent(self, agent_id: str) -> None:
            """Switch the visible agent tab.

            Args:
                agent_id: The agent ID to switch to.
            """
            tui_log(f"_switch_to_agent called: {agent_id}, current: {self._active_agent_id}")
            tui_log(f"  agent_widgets keys: {list(self.agent_widgets.keys())}")
            try:
                if agent_id == self._active_agent_id:
                    tui_log(f"  Already on {agent_id}, skipping")
                    return

                # Hide current panel
                if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                    tui_log(f"  Hiding panel: {self._active_agent_id}")
                    self.agent_widgets[self._active_agent_id].add_class("hidden")

                # Show new panel - only if agent exists
                if agent_id in self.agent_widgets:
                    tui_log(f"  Showing panel: {agent_id}")
                    new_panel = self.agent_widgets[agent_id]
                    new_panel.remove_class("hidden")
                    # Auto-scroll to bottom so user sees latest content
                    try:
                        timeline = new_panel.query_one(f"#{new_panel._timeline_section_id}", TimelineSection)
                        timeline._scroll_to_end(animate=False, force=True)
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")  # Timeline may not exist yet
                else:
                    tui_log(f"  Panel not found for: {agent_id}", level="warning")
                    # Agent panel doesn't exist yet, just update state

                # Update tab bar
                if self._tab_bar:
                    tui_log(f"  Updating tab bar active: {agent_id}")
                    self._tab_bar.set_active(agent_id)

                # Update status ribbon to show this agent's status
                if self._status_ribbon:
                    tui_log(f"  Updating status ribbon for: {agent_id}")
                    self._status_ribbon.set_agent(agent_id)

                # Phase 13.2: Update execution status line focused agent
                if self._execution_status_line:
                    self._execution_status_line.set_focused_agent(agent_id)

                self._active_agent_id = agent_id
                tui_log(f"  Switch complete to: {agent_id}")
                self._update_human_input_target_button()

                # Show winner hint separator on non-winner timelines
                if self._winner_agent_id and agent_id != self._winner_agent_id:
                    self._update_winner_hints(self._winner_agent_id)

                # Update current_agent_index for compatibility with existing methods
                try:
                    self.current_agent_index = self.coordination_display.agent_ids.index(agent_id)
                except ValueError:
                    pass
            except Exception as e:
                tui_log(f"  ERROR in _switch_to_agent: {e}", level="error")
                # Don't crash on tab switch errors

        def on_agent_tab_changed(self, event: AgentTabChanged) -> None:
            """Handle tab click from AgentTabBar."""
            tui_log(f"on_agent_tab_changed: {event.agent_id}")

            # In single-agent mode, clicking a different tab changes the selected agent
            if self._mode_state.is_single_agent_mode():
                # Block agent switching during execution
                if self._mode_state.is_locked():
                    tui_log("  Agent switch blocked - execution in progress")
                    self.notify("Cannot switch agents during execution", severity="warning", timeout=2)
                    event.stop()
                    return

                tui_log(f"  Single-agent mode: selecting {event.agent_id}")
                self._mode_state.selected_single_agent = event.agent_id
                if self._tab_bar:
                    self._tab_bar.set_single_agent_mode(True, event.agent_id)
                # Update agent panels with "in use" state
                self._update_agent_panels_in_use_state(event.agent_id)
                self.notify(f"Single agent: {event.agent_id}", severity="information", timeout=2)

            self._switch_to_agent(event.agent_id)
            event.stop()

        def on_view_selected(self, event: ViewSelected) -> None:
            """Handle view selection from AgentStatusRibbon dropdown.

            Switches the agent panel to show either a specific round or the final answer.
            """
            if event.agent_id not in self.agent_widgets:
                return

            panel = self.agent_widgets[event.agent_id]

            if event.view_type == "final_answer":
                panel.switch_to_final_answer()
            elif event.view_type == "round" and event.round_number is not None:
                # Check if we're currently viewing final answer BEFORE changing state
                was_viewing_final = panel._current_view == "final_answer"
                if was_viewing_final:
                    panel.switch_from_final_answer()
                panel.switch_to_round(event.round_number)

            event.stop()

        def on_session_info_clicked(self, event: SessionInfoClicked) -> None:
            """Handle click on session info to show full prompt."""
            tui_log(f"on_session_info_clicked: turn={event.turn}")
            # Build content with optional per-agent assignment (subtask/persona)
            content = ""
            if event.subtask:
                label = getattr(event, "assignment_kind", "Subtask")
                content += f"{label}: {event.subtask}\n\n"

            improved = getattr(event, "improved_prompt", None)
            if improved:
                content += "IMPROVED PROMPT (what agents see):\n"
                content += improved
                content += "\n\n---\n\n"
                content += "ORIGINAL PROMPT:\n"
                content += event.question or "(No prompt)"
            else:
                content += event.question or "(No prompt)"

            title = f"Turn {event.turn} • Prompt"
            if improved:
                title += " (improved)"
            # Show the full prompt in a text modal
            self.push_screen(
                TextContentModal(
                    title=title,
                    content=content,
                ),
            )
            event.stop()

        def _sync_coordination_mode_toggle(self, mode: str) -> None:
            """Sync coordination toggle UI state from external config/runtime.

            This is used by the CLI driver to align the mode bar with config defaults
            before the user explicitly changes the coordination toggle.
            """
            if self._mode_state.agent_mode == "single" and mode == "decomposition":
                mode = "parallel"
            self._mode_state.coordination_mode = mode
            if self._mode_bar:
                self._mode_bar.set_coordination_mode(mode)
                self._mode_bar.set_coordination_enabled(self._mode_state.agent_mode != "single")
                self._mode_bar.set_parallel_personas_enabled(self._mode_state.parallel_personas_enabled, self._mode_state.persona_diversity_mode)
            if self._tab_bar:
                if mode == "decomposition":
                    self._tab_bar.set_agent_subtasks(self._mode_state.decomposition_subtasks)
                else:
                    if self._mode_state.parallel_personas_enabled:
                        self._tab_bar.set_agent_personas(self._runtime_parallel_personas)
                    else:
                        self._tab_bar.set_agent_subtasks({})

        # ============================================================
        # Mode Change Handlers
        # ============================================================

        def on_mode_changed(self, event: ModeChanged) -> None:
            """Handle mode toggle changes from ModeBar."""
            tui_log(f"on_mode_changed: {event.mode_type}={event.value}")

            # Block mode changes during execution
            if self._mode_state.is_locked():
                tui_log("  -> BLOCKED: execution in progress")
                self.notify(
                    "Cannot change modes during execution. Wait for completion or cancel first.",
                    severity="warning",
                    timeout=3,
                )
                # Revert the toggle to its previous state
                if event.mode_type == "plan" and self._mode_bar:
                    self._mode_bar.set_plan_mode(self._mode_state.plan_mode)
                elif event.mode_type == "agent" and self._mode_bar:
                    self._mode_bar.set_agent_mode(self._mode_state.agent_mode)
                elif event.mode_type == "coordination" and self._mode_bar:
                    self._mode_bar.set_coordination_mode(self._mode_state.coordination_mode)
                elif event.mode_type == "refinement" and self._mode_bar:
                    self._mode_bar.set_refinement_mode(self._mode_state.refinement_enabled)
                elif event.mode_type == "personas" and self._mode_bar:
                    self._mode_bar.set_parallel_personas_enabled(
                        self._mode_state.parallel_personas_enabled,
                        self._mode_state.persona_diversity_mode,
                    )
                event.stop()
                return

            if event.mode_type == "plan":
                self._handle_plan_mode_change(event.value)
            elif event.mode_type == "agent":
                self._handle_agent_mode_change(event.value)
            elif event.mode_type == "coordination":
                self._handle_coordination_mode_change(event.value)
            elif event.mode_type == "refinement":
                self._handle_refinement_mode_change(event.value == "on")
            elif event.mode_type == "personas":
                enabled = event.value != "off"
                diversity_mode = event.value if enabled else "perspective"
                self._handle_parallel_persona_mode_change(enabled, diversity_mode)

            self._refresh_input_modes_row_layout()
            event.stop()

        def on_override_requested(self, event: OverrideRequested) -> None:
            """Handle override button press from ModeBar."""
            tui_log("on_override_requested")
            self.action_trigger_override()
            event.stop()

        def on_plan_settings_clicked(self, event: PlanSettingsClicked) -> None:
            """Handle plan settings button click - show/hide plan options popover."""
            tui_log("on_plan_settings_clicked - START")

            # Block during execution
            if self._mode_state.is_locked():
                tui_log("  -> BLOCKED: execution in progress")
                self.notify(
                    "Cannot change plan settings during execution.",
                    severity="warning",
                    timeout=2,
                )
                event.stop()
                return

            if hasattr(self, "_plan_options_popover"):
                popover = self._plan_options_popover
                tui_log(f"  popover exists, visible={'visible' in popover.classes}, classes={list(popover.classes)}")
                if "visible" in popover.classes:
                    # Already visible - just hide it
                    tui_log("  -> hiding popover")
                    popover.hide()
                else:
                    # Not visible - update state and recompose to show plans, then show
                    tui_log("  -> updating state and showing")
                    self._update_plan_options_popover_state()
                    tui_log(f"  -> after state update, plans count: {len(popover._available_plans)}")
                    # Reset initialized flag before recompose to ignore spurious events
                    popover._initialized = False
                    tui_log("  -> set _initialized=False")
                    popover.refresh(recompose=True)
                    tui_log("  -> after refresh(recompose=True)")
                    # Use call_later to show after recompose completes (show() sets _initialized=True)
                    tui_log("  -> calling call_later(popover.show)")
                    self.call_later(popover.show)
            else:
                tui_log("  popover does not exist!")
            tui_log("on_plan_settings_clicked - END")
            event.stop()

        def on_mode_help_clicked(self, event: ModeHelpClicked) -> None:
            """Handle mode bar help button click."""
            self.action_show_shortcuts()
            event.stop()

        def on_subtasks_clicked(self, event: SubtasksClicked) -> None:
            """Handle subtasks editor button click."""
            if self._mode_state.is_locked():
                self.notify("Cannot edit subtasks during execution.", severity="warning", timeout=2)
                event.stop()
                return
            self._show_subtasks_editor_modal()
            event.stop()

        def on_skills_clicked(self, event: SkillsClicked) -> None:
            """Handle global skills manager button click."""
            if self._mode_state.is_locked():
                self.notify("Cannot change skill settings during execution.", severity="warning", timeout=2)
                event.stop()
                return
            self._show_skills_modal()
            event.stop()

        def _show_subtasks_editor_modal(self) -> None:
            """Open decomposition subtasks editor modal."""
            modal = DecompositionSubtasksModal(
                agent_ids=self.coordination_display.agent_ids,
                current_subtasks=self._mode_state.decomposition_subtasks,
            )

            def _on_subtasks_dismiss(result: dict[str, str] | None) -> None:
                # None means cancelled/closed
                if result is None:
                    return
                self._mode_state.decomposition_subtasks = result
                if self._tab_bar:
                    self._tab_bar.set_agent_subtasks(result if self._mode_state.coordination_mode == "decomposition" else {})
                if result:
                    self.notify(
                        f"Saved {len(result)} decomposition subtask assignment(s).",
                        severity="information",
                        timeout=3,
                    )
                else:
                    self.notify(
                        "Cleared explicit subtasks. A decomposition subagent will auto-generate them at runtime.",
                        severity="warning",
                        timeout=3,
                    )

            self.push_screen(modal, _on_subtasks_dismiss)

        def on_plan_selected(self, event: PlanSelected) -> None:
            """Handle plan selection from popover."""
            tui_log(f"on_plan_selected: plan_id={event.plan_id}, is_new={event.is_new}")

            requested_plan_id = None if event.plan_id in (None, "", "latest") else event.plan_id
            current_plan_id = None if self._mode_state.selected_plan_id in (None, "", "latest") else self._mode_state.selected_plan_id

            # Ignore no-op selections emitted during recompose/initialization.
            if not event.is_new and requested_plan_id == current_plan_id:
                tui_log("  -> no-op plan selection, ignoring")
                event.stop()
                return

            # Block during execution
            if self._mode_state.is_locked():
                tui_log("  -> BLOCKED: execution in progress")
                self.notify("Cannot change plan selection during execution.", severity="warning", timeout=2)
                event.stop()
                return

            if event.is_new:
                # User wants to create a new plan
                self._mode_state.selected_plan_id = None
                self.notify("Will create new plan on next query", severity="information", timeout=2)
            elif requested_plan_id:
                # Specific plan selected
                self._mode_state.selected_plan_id = requested_plan_id
                self.notify(f"Selected plan: {requested_plan_id[:15]}...", severity="information", timeout=2)
            else:
                # Latest plan (auto) - don't notify on initial load
                self._mode_state.selected_plan_id = None
                # Only notify if popover is visible (user actually selected)
                if hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes:
                    pass  # Don't notify for "latest" - it's the default

            # Don't auto-hide - let user close with Close button or click settings again
            event.stop()

        def on_plan_depth_changed(self, event: PlanDepthChanged) -> None:
            """Handle plan depth change from popover."""
            tui_log(f"on_plan_depth_changed: depth={event.depth}")

            # Block during execution
            if self._mode_state.is_locked():
                tui_log("  -> BLOCKED: execution in progress")
                self.notify("Cannot change plan depth during execution.", severity="warning", timeout=2)
                event.stop()
                return

            self._mode_state.plan_config.depth = event.depth
            if event.depth == "dynamic":
                self.notify("Plan depth: dynamic (scope-adaptive)", severity="information", timeout=2)
            else:
                self.notify(f"Plan depth: {event.depth}", severity="information", timeout=2)
            event.stop()

        def on_plan_step_target_changed(self, event: PlanStepTargetChanged) -> None:
            """Handle explicit planning task-count target change from popover."""
            tui_log(f"on_plan_step_target_changed: target_steps={event.target_steps}")

            if self._mode_state.is_locked():
                self.notify("Cannot change plan step target during execution.", severity="warning", timeout=2)
                event.stop()
                return

            self._mode_state.plan_config.target_steps = event.target_steps
            if event.target_steps is None:
                self.notify("Task count target: dynamic", severity="information", timeout=2)
            else:
                self.notify(f"Task count target: {event.target_steps}", severity="information", timeout=2)
            event.stop()

        def on_plan_chunk_target_changed(self, event: PlanChunkTargetChanged) -> None:
            """Handle explicit planning chunk-count target change from popover."""
            tui_log(f"on_plan_chunk_target_changed: target_chunks={event.target_chunks}")

            if self._mode_state.is_locked():
                self.notify("Cannot change chunk target during execution.", severity="warning", timeout=2)
                event.stop()
                return

            self._mode_state.plan_config.target_chunks = event.target_chunks
            if event.target_chunks is None:
                self.notify("Chunk target: dynamic", severity="information", timeout=2)
            else:
                self.notify(f"Chunk target: {event.target_chunks}", severity="information", timeout=2)
            event.stop()

        def on_broadcast_mode_changed(self, event: BroadcastModeChanged) -> None:
            """Handle broadcast mode change from popover."""
            tui_log(f"on_broadcast_mode_changed: broadcast={event.broadcast}")

            # Block during execution
            if self._mode_state.is_locked():
                tui_log("  -> BLOCKED: execution in progress")
                self.notify("Cannot change broadcast mode during execution.", severity="warning", timeout=2)
                event.stop()
                return

            if self._mode_state.plan_mode == "spec":
                self._mode_state.spec_config.broadcast = event.broadcast
            else:
                self._mode_state.plan_config.broadcast = event.broadcast

            if event.broadcast == "human":
                self.notify("Broadcast: Agents can ask human questions", severity="information", timeout=2)
            elif event.broadcast == "agents":
                self.notify("Broadcast: Agents debate without human", severity="information", timeout=2)
            else:
                self.notify("Broadcast: Fully autonomous (no questions)", severity="warning", timeout=2)
            event.stop()

        def on_view_plan_requested(self, event: ViewPlanRequested) -> None:
            """Handle request to view full plan details in a modal."""
            tui_log(f"on_view_plan_requested: plan_id={event.plan_id}, tasks={len(event.tasks)}")

            if not event.tasks:
                self.notify("No tasks in this plan", severity="warning", timeout=2)
                event.stop()
                return

            # Open TaskPlanModal with the plan's tasks
            modal = TaskPlanModal(tasks=event.tasks)
            self.push_screen(modal)
            event.stop()

        def on_execute_prefill_requested(self, event: ExecutePrefillRequested) -> None:
            """Handle execute popover prefill requests from chunk controls."""
            prefill_value = (event.value or "").strip()
            if not prefill_value:
                event.stop()
                return
            if hasattr(self, "question_input") and self.question_input:
                self.question_input.value = prefill_value
                self.question_input.focus()
                self.notify(
                    f"Prefilled execute input: {prefill_value}",
                    severity="information",
                    timeout=2,
                )
            event.stop()

        def on_analysis_target_type_changed(self, event: AnalysisTargetTypeChanged) -> None:
            """Handle analysis target type changes (log vs skills) from the popover."""
            tui_log(f"on_analysis_target_type_changed: target={event.target}")

            if self._mode_state.is_locked():
                self.notify("Cannot change analysis target during execution.", severity="warning", timeout=2)
                event.stop()
                return

            target = "skills" if event.target == "skills" else "log"
            self._mode_state.analysis_config.target = target

            # Update input placeholder to match the new target
            if hasattr(self, "question_input"):
                from massgen.frontend.displays.tui_modes import (
                    get_analysis_placeholder_text,
                )

                self.question_input.placeholder = get_analysis_placeholder_text(target)

            popover_visible = hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes
            if not popover_visible:
                label = "Organize Skills" if target == "skills" else "Log Session"
                self.notify(
                    f"Analysis target: {label}",
                    severity="information",
                    timeout=2,
                )
            event.stop()

        def on_execute_auto_continue_changed(self, event: ExecuteAutoContinueChanged) -> None:
            """Handle execute auto-continue setting change from popover."""
            if self._mode_state.is_locked():
                self.notify("Cannot change execute flow during execution.", severity="warning", timeout=2)
                event.stop()
                return
            self._mode_state.plan_config.execute_auto_continue_chunks = bool(event.enabled)
            if event.enabled:
                self.notify("Execute flow: auto-continue enabled", severity="information", timeout=2)
            else:
                self.notify("Execute flow: pause after each chunk", severity="information", timeout=2)
            event.stop()

        def on_execute_refinement_mode_changed(self, event: ExecuteRefinementModeChanged) -> None:
            """Handle execute refinement override mode change from popover."""
            if self._mode_state.is_locked():
                self.notify("Cannot change execute refinement during execution.", severity="warning", timeout=2)
                event.stop()
                return
            mode = event.mode if event.mode in {"inherit", "on", "off"} else "inherit"
            self._mode_state.plan_config.execute_refinement_mode = mode
            labels = {
                "inherit": "Execute refinement: inherit mode bar setting",
                "on": "Execute refinement: forced ON",
                "off": "Execute refinement: forced OFF",
            }
            self.notify(labels[mode], severity="information", timeout=2)
            event.stop()

        def on_analysis_profile_changed(self, event: AnalysisProfileChanged) -> None:
            """Handle analysis profile changes from the popover."""
            tui_log(f"on_analysis_profile_changed: profile={event.profile}")

            if self._mode_state.is_locked():
                self.notify("Cannot change analysis profile during execution.", severity="warning", timeout=2)
                event.stop()
                return

            profile = "user" if event.profile == "user" else "dev"
            self._mode_state.analysis_config.profile = profile

            popover_visible = hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes
            if not popover_visible:
                self.notify(
                    f"Analysis profile: {'User (skills)' if profile == 'user' else 'Dev (internals)'}",
                    severity="information",
                    timeout=2,
                )
            event.stop()

        def on_analysis_skill_lifecycle_changed(self, event: AnalysisSkillLifecycleChanged) -> None:
            """Handle analysis skill lifecycle mode changes from the popover."""
            tui_log(f"on_analysis_skill_lifecycle_changed: mode={event.mode}")

            if self._mode_state.is_locked():
                self.notify("Cannot change analysis skill lifecycle during execution.", severity="warning", timeout=2)
                event.stop()
                return

            mode = str(event.mode or "").strip().lower()
            if mode not in {"create_new", "create_or_update"}:
                mode = "create_or_update"

            self._mode_state.analysis_config.skill_lifecycle_mode = mode

            popover_visible = hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes
            if not popover_visible:
                labels = {
                    "create_new": "Create New",
                    "create_or_update": "Create or Update",
                }
                self.notify(
                    f"Analysis skill lifecycle: {labels.get(mode, mode)}",
                    severity="information",
                    timeout=2,
                )
            event.stop()

        def on_analysis_target_changed(self, event: AnalysisTargetChanged) -> None:
            """Handle analysis target changes from the popover."""
            tui_log(f"on_analysis_target_changed: log_dir={event.log_dir}, turn={event.turn}")

            if self._mode_state.is_locked():
                self.notify("Cannot change analysis target during execution.", severity="warning", timeout=2)
                event.stop()
                return

            cfg = self._mode_state.analysis_config
            prev_log_dir = cfg.selected_log_dir
            prev_turn = cfg.selected_turn
            cfg.selected_log_dir = event.log_dir

            if event.log_dir:
                turns = self._get_turn_numbers(Path(event.log_dir))
                if event.turn in turns:
                    cfg.selected_turn = event.turn
                elif turns:
                    cfg.selected_turn = turns[-1]
                else:
                    cfg.selected_turn = None
            else:
                cfg.selected_turn = None

            if cfg.selected_log_dir == prev_log_dir and cfg.selected_turn == prev_turn:
                event.stop()
                return

            self._refresh_analysis_popover_if_visible()

            popover_visible = hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes
            if not popover_visible:
                if cfg.selected_log_dir and cfg.selected_turn is not None:
                    self.notify(
                        f"Analysis target: {Path(cfg.selected_log_dir).name} / turn_{cfg.selected_turn}",
                        severity="information",
                        timeout=2,
                    )
                elif cfg.selected_log_dir:
                    self.notify(
                        f"Analysis target: {Path(cfg.selected_log_dir).name} (no turns found)",
                        severity="warning",
                        timeout=2,
                    )
                else:
                    self.notify("Analysis target cleared", severity="warning", timeout=2)
            event.stop()

        def on_view_analysis_requested(self, event: ViewAnalysisRequested) -> None:
            """Handle request to open the selected analysis report."""
            report_path = self._get_analysis_report_path(event.log_dir, event.turn)
            if not report_path.exists():
                self.notify(
                    f"Analysis report not found at {report_path}. Run analysis first.",
                    severity="warning",
                    timeout=3,
                )
                event.stop()
                return

            self._show_text_modal(report_path, f"Analysis Report • {Path(event.log_dir).name} • turn_{event.turn}")
            event.stop()

        def _update_plan_options_popover_state(self) -> None:
            """Update the plan options popover internal state (without recompose)."""
            if not hasattr(self, "_plan_options_popover"):
                return

            try:
                from massgen.plan_storage import PlanStorage

                storage = PlanStorage()
                plans = storage.get_all_plans(limit=5)
                self._ensure_analysis_defaults()
                analysis_log_options = self._build_analysis_log_options()
                analysis_turn_options = self._build_analysis_turn_options()

                # Update popover internal state
                popover = self._plan_options_popover
                popover._plan_mode = self._mode_state.plan_mode
                popover._available_plans = plans
                popover._current_plan_id = self._mode_state.selected_plan_id
                popover._current_depth = self._mode_state.plan_config.depth
                popover._current_step_target = self._mode_state.plan_config.target_steps
                popover._current_chunk_target = self._mode_state.plan_config.target_chunks
                popover._current_execute_auto_continue = self._mode_state.plan_config.execute_auto_continue_chunks
                popover._current_execute_refinement_mode = self._mode_state.plan_config.execute_refinement_mode
                if self._mode_state.plan_mode == "spec":
                    popover._current_broadcast = self._mode_state.spec_config.broadcast
                else:
                    popover._current_broadcast = self._mode_state.plan_config.broadcast
                popover._analysis_target_type = getattr(self._mode_state.analysis_config, "target", "log")
                popover._analysis_profile = self._mode_state.analysis_config.profile
                popover._analysis_log_options = analysis_log_options
                popover._analysis_selected_log_dir = self._mode_state.analysis_config.selected_log_dir
                popover._analysis_turn_options = analysis_turn_options
                popover._analysis_selected_turn = self._mode_state.analysis_config.selected_turn
                popover._analysis_preview_text = self._build_analysis_preview_text(
                    self._mode_state.analysis_config.selected_log_dir,
                    self._mode_state.analysis_config.selected_turn,
                )
                popover._analysis_skill_lifecycle_mode = self._mode_state.analysis_config.skill_lifecycle_mode
                # Don't recompose - let the popover show with updated state
            except Exception as e:
                tui_log(f"_update_plan_options_popover_state error: {e}")

        def _get_available_log_sessions(self) -> list[Path]:
            """Return available log session directories, excluding the current session.

            The current running session's log dir is excluded because it's
            actively being written to and not useful as an analysis target.
            """
            log_dirs: list[Path] = []
            try:
                from massgen.logger_config import get_log_session_root
                from massgen.logs_analyzer import get_logs_dir

                logs_base = get_logs_dir()
                if logs_base.exists():
                    log_dirs.extend([p.resolve() for p in logs_base.glob("log_*") if p.is_dir()])
                    # Timestamp-based directory names sort correctly lexicographically.
                    log_dirs.sort(key=lambda p: p.name, reverse=True)

                # Exclude the current running session — it's still being
                # written to and isn't a meaningful analysis target.
                current_root = get_log_session_root().resolve()
                if current_root.exists() and current_root.is_dir():
                    log_dirs = [p for p in log_dirs if p != current_root]

                # Exclude sessions that never completed an attempt (no status.json).
                log_dirs = [p for p in log_dirs if any(p.glob("turn_*/attempt_*/status.json"))]
            except Exception as e:
                tui_log(f"_get_available_log_sessions error: {e}")
            return log_dirs

        @staticmethod
        def _get_turn_numbers(log_dir: Path) -> list[int]:
            """Extract sorted turn numbers from a log session directory."""
            turns: list[int] = []
            if not log_dir.exists():
                return turns
            for turn_dir in log_dir.glob("turn_*"):
                if not turn_dir.is_dir():
                    continue
                try:
                    turns.append(int(turn_dir.name.split("_", 1)[1]))
                except (IndexError, ValueError):
                    continue
            return sorted(set(turns))

        def _ensure_analysis_defaults(self) -> None:
            """Ensure analysis target defaults are set to valid log/turn values."""
            logs = self._get_available_log_sessions()
            cfg = self._mode_state.analysis_config

            if not logs:
                cfg.selected_log_dir = None
                cfg.selected_turn = None
                return

            log_paths = {str(p): p for p in logs}
            selected_log = cfg.selected_log_dir
            if not selected_log or selected_log not in log_paths:
                selected_log = str(logs[0])

            turns = self._get_turn_numbers(log_paths[selected_log])
            selected_turn = cfg.selected_turn
            if not turns:
                selected_turn = None
            elif selected_turn not in turns:
                selected_turn = turns[-1]

            cfg.selected_log_dir = selected_log
            cfg.selected_turn = selected_turn

        def _build_analysis_log_options(self) -> list[tuple[str, str]]:
            """Build `(label, value)` options for analysis log selection."""
            options: list[tuple[str, str]] = []
            logs = self._get_available_log_sessions()
            selected = self._mode_state.analysis_config.selected_log_dir
            for path in logs:
                query = self._get_log_session_query(path)
                # Extract timestamp portion from dir name (e.g. "20260207_143026")
                ts = path.name.removeprefix("log_").rsplit("_", 1)[0]
                if query:
                    label = f"{ts} — {query[:50]}"
                else:
                    label = path.name
                if str(path) == selected:
                    label += " (selected)"
                options.append((label, str(path)))
            return options

        @staticmethod
        def _get_log_session_query(log_dir: Path) -> str | None:
            """Extract the user query from the first status.json in a log session."""
            import json

            for status_path in sorted(log_dir.glob("turn_*/attempt_*/status.json")):
                try:
                    data = json.loads(status_path.read_text())
                    question = data.get("meta", {}).get("question", "")
                    if question:
                        return question.strip()
                except Exception:
                    continue
            return None

        def _build_analysis_turn_options(self) -> list[tuple[str, str]]:
            """Build `(label, value)` options for analysis turn selection."""
            options: list[tuple[str, str]] = []
            selected_log = self._mode_state.analysis_config.selected_log_dir
            if not selected_log:
                return options
            turns = self._get_turn_numbers(Path(selected_log))
            for turn in turns:
                options.append((f"turn_{turn}", str(turn)))
            return options

        def _refresh_analysis_popover_if_visible(self) -> None:
            """Recompose the analysis popover when it is currently visible."""
            if not hasattr(self, "_plan_options_popover"):
                return
            popover = self._plan_options_popover
            if "visible" not in popover.classes:
                return
            self._update_plan_options_popover_state()
            popover._initialized = False
            popover.refresh(recompose=True)
            self.call_later(popover.show)

        @staticmethod
        def _get_analysis_report_path(log_dir: str, turn: int) -> Path:
            """Return the expected ANALYSIS_REPORT.md path for a log session turn."""
            return Path(log_dir) / f"turn_{turn}" / "ANALYSIS_REPORT.md"

        @staticmethod
        def _extract_user_query_fragment(question: str) -> str:
            """Extract the user-facing part of a structured analysis prompt."""
            if not question:
                return ""

            text = question.strip()
            # Analysis prompts often wrap user input as "USER'S ANALYSIS REQUEST: ..."
            patterns = [
                r"USER'?S\s+ANALYSIS\s+REQUEST:\s*(.+)",
                r"USER'?S\s+REQUEST:\s*(.+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    candidate = match.group(1).strip()
                    if candidate:
                        return candidate
            return text

        @staticmethod
        def _condense_preview(text: str, max_chars: int = 260) -> str:
            """Condense multiline text into a short single-line preview."""
            if not text:
                return ""
            single_line = re.sub(r"\s+", " ", text).strip()
            if len(single_line) <= max_chars:
                return single_line
            return single_line[: max_chars - 3].rstrip() + "..."

        @staticmethod
        def _read_yaml_file(path: Path) -> dict[str, Any]:
            """Read a YAML file into a dictionary, returning {} on errors."""
            if not path.exists():
                return {}
            try:
                import yaml

                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        @staticmethod
        def _get_latest_attempt_dir(turn_dir: Path) -> Path | None:
            """Return latest attempt dir under a turn, or the turn dir for legacy layouts."""
            if not turn_dir.exists() or not turn_dir.is_dir():
                return None

            attempts = [p for p in turn_dir.glob("attempt_*") if p.is_dir()]
            if not attempts:
                return turn_dir

            def attempt_key(path: Path) -> int:
                match = re.match(r"attempt_(\d+)$", path.name)
                return int(match.group(1)) if match else -1

            attempts.sort(key=attempt_key)
            return attempts[-1]

        def _extract_query_preview_from_attempt(self, attempt_dir: Path) -> str | None:
            """Extract query preview from status/metadata/system logs."""
            if not attempt_dir.exists():
                return None

            status_candidates = [attempt_dir / "status.json"]
            metadata_candidates = [attempt_dir / "execution_metadata.yaml"]
            system_status_candidates = [attempt_dir / "agent_outputs" / "system_status.txt"]

            if attempt_dir.name.startswith("attempt_"):
                status_candidates.append(attempt_dir.parent / "status.json")
                metadata_candidates.append(attempt_dir.parent / "execution_metadata.yaml")
                system_status_candidates.append(attempt_dir.parent / "agent_outputs" / "system_status.txt")

            # 1) status.json -> meta.question (preferred during active/attempt-based runs)
            for status_path in status_candidates:
                if not status_path.exists():
                    continue
                try:
                    status_data = json.loads(status_path.read_text(encoding="utf-8"))
                    question = status_data.get("meta", {}).get("question")
                    if isinstance(question, str) and question.strip():
                        question = self._extract_user_query_fragment(question)
                        return self._condense_preview(question)
                except Exception:
                    continue

            # 2) execution_metadata.yaml -> query
            for metadata_path in metadata_candidates:
                metadata = self._read_yaml_file(metadata_path)
                query = metadata.get("query")
                if isinstance(query, str) and query.strip():
                    query = self._extract_user_query_fragment(query)
                    return self._condense_preview(query)

            # 3) system_status.txt fallback (legacy logs may only have this)
            for system_status_path in system_status_candidates:
                if not system_status_path.exists():
                    continue
                try:
                    content = system_status_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                match = re.search(r"^\s*(?:Question|Query)\s*:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
                if match:
                    query = self._extract_user_query_fragment(match.group(1))
                    if query:
                        return self._condense_preview(query)

            return None

        @staticmethod
        def _extract_winner_from_status(status_data: dict[str, Any]) -> str | None:
            """Extract winner agent id from status payload."""
            if not status_data:
                return None

            results = status_data.get("results", {})
            winner = results.get("winner")
            if isinstance(winner, str) and winner.strip():
                return winner.strip()

            details = status_data.get("finish_reason_details")
            if isinstance(details, str):
                match = re.search(r"Winner:\s*([A-Za-z0-9_.-]+)", details)
                if match:
                    return match.group(1)
            return None

        def _extract_final_answer_preview_from_attempt(self, attempt_dir: Path) -> str | None:
            """Extract final answer preview if final/ exists for the selected target."""
            if not attempt_dir.exists():
                return None

            final_dir_candidates = [attempt_dir / "final"]
            status_candidates = [attempt_dir / "status.json"]

            if attempt_dir.name.startswith("attempt_"):
                final_dir_candidates.append(attempt_dir.parent / "final")
                status_candidates.append(attempt_dir.parent / "status.json")

            final_dir: Path | None = None
            for candidate in final_dir_candidates:
                if candidate.exists() and candidate.is_dir():
                    final_dir = candidate
                    break

            # User requested: skip final preview when there is no final/
            if not final_dir:
                return None

            status_data: dict[str, Any] = {}
            for status_path in status_candidates:
                if not status_path.exists():
                    continue
                try:
                    status_data = json.loads(status_path.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue

            candidates: list[Path] = []
            winner = self._extract_winner_from_status(status_data)
            if winner:
                candidates.append(final_dir / winner / "answer.txt")
            candidates.extend(sorted(final_dir.glob("*/answer.txt")))

            seen: set[Path] = set()
            for answer_path in candidates:
                if answer_path in seen:
                    continue
                seen.add(answer_path)
                if not answer_path.exists():
                    continue
                try:
                    answer = answer_path.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if answer:
                    return self._condense_preview(answer)

            return "unavailable"

        def _build_analysis_preview_text(self, log_dir: str | None, turn: int | None) -> str:
            """Build query/final preview text for analysis popover."""
            if not log_dir or turn is None:
                return ""

            turn_dir = Path(log_dir) / f"turn_{turn}"
            attempt_dir = self._get_latest_attempt_dir(turn_dir)
            if not attempt_dir:
                return ""

            parts: list[str] = []
            query_preview = self._extract_query_preview_from_attempt(attempt_dir)
            if query_preview:
                parts.append(f"Query: {query_preview}")

            final_preview = self._extract_final_answer_preview_from_attempt(attempt_dir)
            if final_preview:
                parts.append(f"Final: {final_preview}")

            return "\n".join(parts)

        def _enter_execute_mode(self) -> None:
            """Enter execute mode and show plan selector if plans exist.

            Called from action_toggle_plan_mode when transitioning from plan → execute.
            If no plans exist, skips to analysis mode so the user isn't stuck.
            """
            tui_log("_enter_execute_mode - START")

            try:
                from massgen.plan_storage import PlanStorage

                storage = PlanStorage()
                plans = storage.get_all_plans(limit=10)
                tui_log(f"  -> found {len(plans)} plans")

                if not plans:
                    # No plans available - skip execute and go straight to analysis
                    tui_log("  -> no plans, skipping to analysis mode")
                    self._enter_analysis_mode()
                    return

                # Default selection prefers resumable plan sessions.
                if not self._mode_state.selected_plan_id:
                    resumable_plan = storage.get_latest_resumable_plan()
                    if resumable_plan:
                        self._mode_state.selected_plan_id = resumable_plan.plan_id

                # Set execute mode
                self._mode_state.plan_mode = "execute"
                if self._mode_bar:
                    self._mode_bar.set_plan_mode("execute")

                # Update input placeholder for execute mode
                if hasattr(self, "question_input"):
                    self.question_input.placeholder = "Press Enter to execute selected plan • or type instructions"

                # Show the plan selector popover
                self._show_plan_selector_popover(plans)

                self.notify("Execute Mode: Select a plan to run", severity="information", timeout=3)
                tui_log("_enter_execute_mode - END (success)")

            except Exception as e:
                tui_log(f"_enter_execute_mode error: {e}")
                self.notify(f"Error loading plans: {e}", severity="error", timeout=3)

        def _show_plan_selector_popover(self, plans: list) -> None:
            """Show the plan options popover configured for execute mode.

            Args:
                plans: List of available PlanSession objects.
            """
            tui_log(f"_show_plan_selector_popover: {len(plans)} plans")

            if not hasattr(self, "_plan_options_popover"):
                tui_log("  -> popover does not exist!")
                return

            popover = self._plan_options_popover

            # Update popover state for execute mode
            popover._plan_mode = "execute"
            popover._available_plans = plans
            popover._current_plan_id = self._mode_state.selected_plan_id
            popover._current_execute_auto_continue = self._mode_state.plan_config.execute_auto_continue_chunks
            popover._current_execute_refinement_mode = self._mode_state.plan_config.execute_refinement_mode

            # Reset initialized flag before recompose to ignore spurious events
            popover._initialized = False
            tui_log("  -> set _initialized=False, calling refresh(recompose=True)")

            # Recompose to show execute mode UI (plan selector)
            popover.refresh(recompose=True)

            # Show popover after recompose completes
            self.call_later(popover.show)
            tui_log("  -> called call_later(popover.show)")

        def _setup_plan_execution(self, user_text: str) -> str | None:
            """Set up plan execution and return the execution prompt.

            Called from _submit_question when in execute mode.

            Args:
                user_text: User's input text (may be empty or contain instructions).

            Returns:
                The execution prompt to submit, or None if setup failed.
            """
            tui_log(f"_setup_plan_execution: user_text='{user_text[:50] if user_text else '(empty)'}'")

            try:
                from massgen.plan_execution import (
                    PlanValidationError,
                    build_execution_prompt,
                    build_spec_execution_prompt,
                    resolve_active_chunk,
                )
                from massgen.plan_storage import PlanStorage

                # Get the selected plan
                plan_id = self._mode_state.selected_plan_id
                storage = PlanStorage()
                plans = storage.get_all_plans(limit=10)

                if not plans:
                    self.notify("No plans available to execute", severity="error", timeout=3)
                    tui_log("  -> no plans available")
                    return None

                # Find the plan to execute
                if plan_id and plan_id != "latest":
                    # Find specific plan
                    plan = None
                    for p in plans:
                        if p.plan_id == plan_id:
                            plan = p
                            break
                    if not plan:
                        self.notify(f"Plan '{plan_id}' not found", severity="error", timeout=3)
                        tui_log(f"  -> plan not found: {plan_id}")
                        return None
                else:
                    # Default resume target to latest resumable, otherwise latest plan.
                    plan = storage.get_latest_resumable_plan() or plans[0]

                tui_log(f"  -> using plan: {plan.plan_id}")

                # Set the plan session on mode state (needed for workspace setup)
                self._mode_state.plan_session = plan
                self._mode_state.selected_plan_id = plan.plan_id

                # Load metadata to get the original planning prompt and artifact type
                _artifact_type = None
                try:
                    metadata = plan.load_metadata()
                    original_question = getattr(metadata, "planning_prompt", None) or user_text or "Execute the plan"
                    _artifact_type = getattr(metadata, "artifact_type", None)
                except Exception:
                    original_question = user_text or "Execute the plan"

                cleaned_input = (user_text or "").strip()
                requested_chunk: str | None = None
                range_selection: tuple[str, str] | None = None
                additional_instructions: str | None = None

                try:
                    chunk_metadata, chunk_order = resolve_active_chunk(
                        plan,
                        requested_chunk=None,
                    )
                except PlanValidationError as e:
                    self.notify(f"Plan validation failed: {e}", severity="error", timeout=6)
                    tui_log(f"  -> chunk validation error: {e}")
                    return None

                # Parse optional chunk/range selection from execute input.
                if cleaned_input:
                    if cleaned_input in set(chunk_order):
                        requested_chunk = cleaned_input
                    else:
                        range_match = re.match(
                            r"^\s*([^\s-]+)\s*-\s*([^\s-]+)\s*$",
                            cleaned_input,
                        )
                        if range_match:
                            start_chunk = range_match.group(1).strip()
                            end_chunk = range_match.group(2).strip()
                            if start_chunk in set(chunk_order) and end_chunk in set(chunk_order):
                                range_selection = (start_chunk, end_chunk)
                                requested_chunk = start_chunk
                            else:
                                additional_instructions = cleaned_input
                        else:
                            additional_instructions = cleaned_input

                if requested_chunk:
                    try:
                        chunk_metadata, chunk_order = resolve_active_chunk(
                            plan,
                            requested_chunk=requested_chunk,
                        )
                    except PlanValidationError as e:
                        self.notify(f"Plan validation failed: {e}", severity="error", timeout=6)
                        tui_log(f"  -> chunk selection validation error: {e}")
                        return None

                if not chunk_metadata.current_chunk:
                    # No pending chunk selected. Fall back to first chunk only if explicit range was requested.
                    if chunk_order and requested_chunk and requested_chunk in set(chunk_order):
                        chunk_metadata.current_chunk = requested_chunk
                    else:
                        self.notify("Selected plan has no pending chunks to execute", severity="warning", timeout=3)
                        tui_log("  -> no pending chunks")
                        return None

                if cleaned_input and not requested_chunk and not additional_instructions:
                    additional_instructions = cleaned_input
                elif cleaned_input and requested_chunk and cleaned_input != requested_chunk and not range_selection and not additional_instructions:
                    # Input was not a plain chunk selection (e.g., text containing chunk names).
                    additional_instructions = cleaned_input

                prompt_question = original_question
                if additional_instructions:
                    prompt_question = f"{original_question}\n\nAdditional instructions: {additional_instructions}"

                if _artifact_type == "spec":
                    execution_prompt = build_spec_execution_prompt(
                        prompt_question,
                        plan_session=plan,
                        active_chunk=chunk_metadata.current_chunk,
                        chunk_order=chunk_order,
                    )
                else:
                    execution_prompt = build_execution_prompt(
                        prompt_question,
                        active_chunk=chunk_metadata.current_chunk,
                        chunk_order=chunk_order,
                    )

                if range_selection:
                    execution_prompt += (
                        f"\n\nOperator range request: {range_selection[0]}-{range_selection[1]}."
                        " Start at the first chunk now, then continue sequentially toward the range end"
                        " as chunks are completed in subsequent runs."
                    )

                tui_log(f"  -> execution_prompt: {execution_prompt[:100]}...")

                # Reset placeholder since we're leaving execute mode conceptually
                if hasattr(self, "question_input"):
                    self.question_input.placeholder = "Enter to submit • Shift+Enter for newline • @ for files • Ctrl+G help"

                self.notify(
                    f"Executing chunk: {chunk_metadata.current_chunk}",
                    severity="information",
                    timeout=3,
                )
                return execution_prompt

            except Exception as e:
                tui_log(f"_setup_plan_execution error: {e}")
                self.notify(f"Failed to set up plan execution: {e}", severity="error", timeout=3)
                return None

        def _setup_analysis_submission(self, user_text: str) -> str:
            """Prepare analysis request text for submission.

            Empty analysis submissions use a default request so users can press Enter
            (matching execute mode ergonomics).

            Args:
                user_text: User-provided analysis request text (may be empty).

            Returns:
                Analysis request text to submit.
            """
            cleaned = (user_text or "").strip()
            target = self._mode_state.analysis_config.target

            # Snapshot skill directories before analysis for new-skill detection (log target only).
            if target == "log" and self._mode_state.analysis_config.profile == "user":
                self._mode_state.analysis_config._pre_analysis_skill_dirs = self._snapshot_skill_dirs()

            if cleaned:
                return cleaned

            # Keep defaults in sync before submission.
            if target == "log":
                self._ensure_analysis_defaults()

            if target == "skills":
                default_request = "Organize all installed skills: merge overlapping ones and generate a SKILL_REGISTRY.md routing guide."
            elif self._mode_state.analysis_config.profile == "user":
                default_request = "Read the logs from this run, understand the workflow that was executed, and create a single reusable skill capturing that workflow."
            else:
                default_request = "Analyze this run in depth. Explain what happened, identify likely " "root causes, and recommend concrete MassGen internal improvements."

            label = "Skill Organization" if target == "skills" else "Analysis Mode"
            self.notify(
                f"{label}: running default request",
                severity="information",
                timeout=3,
            )
            return default_request

        def _handle_plan_mode_change(self, mode: str) -> None:
            """Handle plan mode toggle.

            Args:
                mode: "normal", "plan", "spec", "execute", or "analysis".
            """
            tui_log(f"_handle_plan_mode_change: {mode}")

            if mode == "plan":
                self._mode_state.plan_mode = mode
                if self._mode_bar:
                    self._mode_bar.set_plan_mode(mode)
                self.notify("Plan Mode: ON - Submit query to create plan", severity="information", timeout=3)
            elif mode == "spec":
                self._mode_state.plan_mode = mode
                if self._mode_bar:
                    self._mode_bar.set_plan_mode(mode)
                self.notify("Spec Mode: ON - Submit query to create requirements spec", severity="information", timeout=3)
            elif mode == "execute":
                # Entering execute mode - use helper which handles plan loading and popover
                # Note: The mode bar already shows "execute", but _enter_execute_mode
                # may revert to "plan" if no plans exist
                self._enter_execute_mode()
            elif mode == "analysis":
                self._enter_analysis_mode()
            elif mode == "normal":
                self._mode_state.reset_plan_state()
                if self._mode_bar:
                    self._mode_bar.set_plan_mode(mode)
                # Hide popover if visible
                if hasattr(self, "_plan_options_popover") and "visible" in self._plan_options_popover.classes:
                    self._plan_options_popover.hide()
                # Reset input placeholder
                if hasattr(self, "question_input"):
                    self.question_input.placeholder = "Enter to submit • Shift+Enter for newline • @ for files • Ctrl+G help"
                self.notify("Plan Mode: OFF", severity="information", timeout=2)

        def _enter_analysis_mode(self) -> None:
            """Enter log analysis mode."""
            from massgen.frontend.displays.tui_modes import (
                get_analysis_placeholder_text,
            )

            self._mode_state.plan_mode = "analysis"
            if self._mode_bar:
                self._mode_bar.set_plan_mode("analysis")
            if hasattr(self, "question_input"):
                target = self._mode_state.analysis_config.target
                self.question_input.placeholder = get_analysis_placeholder_text(target)
            # Ensure default analysis target/profile are populated.
            self._ensure_analysis_defaults()
            # Always show the analysis options popover so the user can
            # pick profile/log/turn immediately.
            if hasattr(self, "_plan_options_popover"):
                self._update_plan_options_popover_state()
                self._plan_options_popover._initialized = False
                self._plan_options_popover.refresh(recompose=True)
                self.call_later(self._plan_options_popover.show)
            self.notify(
                "Analysis Mode: ON - Dev/User profile and log target in settings menu",
                severity="information",
                timeout=3,
            )

        def _handle_agent_mode_change(self, mode: str) -> None:
            """Handle agent mode toggle.

            Args:
                mode: "multi" or "single".
            """
            tui_log(f"_handle_agent_mode_change: {mode}")
            self._mode_state.agent_mode = mode

            if mode == "single":
                switched_from_decomposition = self._mode_state.coordination_mode == "decomposition"
                if switched_from_decomposition:
                    self._mode_state.coordination_mode = "parallel"
                    self._mode_state.coordination_mode_user_set = False
                # Select the currently active agent as the single agent
                selected = self._active_agent_id or (self.coordination_display.agent_ids[0] if self.coordination_display.agent_ids else None)
                self._mode_state.selected_single_agent = selected
                if self._mode_bar:
                    self._mode_bar.set_coordination_mode("parallel")
                    self._mode_bar.set_coordination_enabled(False)
                if self._tab_bar and selected:
                    self._tab_bar.set_single_agent_mode(True, selected)
                    if self._mode_state.parallel_personas_enabled:
                        self._tab_bar.set_agent_personas(self._runtime_parallel_personas)
                    else:
                        self._tab_bar.set_agent_subtasks({})
                # Update agent panels with "in use" state
                self._update_agent_panels_in_use_state(selected)
                if switched_from_decomposition:
                    self.notify(
                        f"Single-Agent Mode: {selected} (decomposition disabled; using parallel)",
                        severity="warning",
                        timeout=3,
                    )
                else:
                    self.notify(f"Single-Agent Mode: {selected}", severity="information", timeout=3)
            else:
                # Multi-agent mode
                self._mode_state.selected_single_agent = None
                if self._mode_bar:
                    self._mode_bar.set_coordination_enabled(True)
                if self._tab_bar:
                    self._tab_bar.set_single_agent_mode(False)
                # All panels are in use in multi-agent mode
                self._update_agent_panels_in_use_state(None)
                self.notify("Multi-Agent Mode", severity="information", timeout=2)

        def _set_agent_mode_visual_state(self, mode: str, selected_agent: str | None = None) -> None:
            """Update agent-mode UI state without changing orchestration logic."""
            if self._mode_bar:
                self._mode_bar.set_agent_mode(mode)

            if mode == "single":
                selected = selected_agent or self._active_agent_id
                if not selected and self.coordination_display.agent_ids:
                    selected = self.coordination_display.agent_ids[0]
                if self._tab_bar and selected:
                    self._tab_bar.set_single_agent_mode(True, selected)
                self._update_agent_panels_in_use_state(selected)
            else:
                if self._tab_bar:
                    self._tab_bar.set_single_agent_mode(False)
                self._update_agent_panels_in_use_state(None)

        def _handle_coordination_mode_change(self, mode: str) -> None:
            """Handle coordination mode toggle.

            Args:
                mode: "parallel" or "decomposition".
            """
            tui_log(f"_handle_coordination_mode_change: {mode}")
            if mode == "decomposition" and self._mode_state.agent_mode == "single":
                self._mode_state.coordination_mode = "parallel"
                self._mode_state.coordination_mode_user_set = False
                if self._mode_bar:
                    self._mode_bar.set_coordination_mode("parallel")
                    self._mode_bar.set_coordination_enabled(False)
                if self._tab_bar:
                    if self._mode_state.parallel_personas_enabled:
                        self._tab_bar.set_agent_personas(self._runtime_parallel_personas)
                    else:
                        self._tab_bar.set_agent_subtasks({})
                self.notify(
                    "Decomposition requires Multi-Agent mode.",
                    severity="warning",
                    timeout=3,
                )
                return

            self._mode_state.coordination_mode = mode
            self._mode_state.coordination_mode_user_set = True
            if self._mode_bar:
                self._mode_bar.set_coordination_mode(mode)
                self._mode_bar.set_coordination_enabled(self._mode_state.agent_mode != "single")

            if mode == "decomposition":
                if self._tab_bar:
                    self._tab_bar.set_agent_subtasks(self._mode_state.decomposition_subtasks)
                self.notify(
                    "Coordination: Decomposition (independent subtasks). Use 'Subtasks' to assign manually.",
                    severity="warning",
                    timeout=3,
                )
            else:
                if self._tab_bar:
                    if self._mode_state.parallel_personas_enabled:
                        self._tab_bar.set_agent_personas(self._runtime_parallel_personas)
                    else:
                        self._tab_bar.set_agent_subtasks({})
                self.notify(
                    "Coordination: Parallel (agents solve the same task and vote)",
                    severity="information",
                    timeout=3,
                )

        def _handle_parallel_persona_mode_change(self, enabled: bool, diversity_mode: str = "perspective") -> None:
            """Handle parallel persona generation toggle."""
            tui_log(f"_handle_parallel_persona_mode_change: enabled={enabled}, mode={diversity_mode}")
            self._mode_state.parallel_personas_enabled = enabled
            self._mode_state.persona_diversity_mode = diversity_mode

            if self._tab_bar and self._mode_state.coordination_mode == "parallel":
                if enabled:
                    self._tab_bar.set_agent_personas(self._runtime_parallel_personas)
                else:
                    self._tab_bar.set_agent_subtasks({})

            if enabled:
                mode_label = diversity_mode.title()
                if self._mode_state.coordination_mode == "parallel":
                    self.notify(
                        f"Personas: {mode_label} (agents get different {diversity_mode}s)",
                        severity="information",
                        timeout=3,
                    )
                else:
                    self.notify(
                        f"Personas: {mode_label} (will apply when coordination mode is Parallel)",
                        severity="information",
                        timeout=3,
                    )
            else:
                self.notify(
                    "Personas: OFF",
                    severity="warning",
                    timeout=2,
                )

        def _update_agent_panels_in_use_state(self, selected_agent: str | None) -> None:
            """Update the 'in use' state for all agent panels.

            Args:
                selected_agent: The selected agent ID in single-agent mode, or None for multi-agent mode.
            """
            if not hasattr(self, "agent_widgets"):
                return

            for agent_id, panel in self.agent_widgets.items():
                if hasattr(panel, "set_in_use"):
                    if selected_agent is None:
                        # Multi-agent mode: all panels in use
                        panel.set_in_use(True)
                    else:
                        # Single-agent mode: only selected panel in use
                        panel.set_in_use(agent_id == selected_agent)

        def _handle_refinement_mode_change(self, enabled: bool) -> None:
            """Handle refinement mode toggle.

            Args:
                enabled: True for refinement on, False for off.
            """
            tui_log(f"_handle_refinement_mode_change: {enabled}")
            self._mode_state.refinement_enabled = enabled

            if enabled:
                self.notify("Refinement: ON (normal voting)", severity="information", timeout=2)
            else:
                if self._mode_state.agent_mode == "single":
                    self.notify("Refinement: OFF (direct answer, no voting)", severity="warning", timeout=3)
                else:
                    self.notify("Refinement: OFF (vote after first answer)", severity="warning", timeout=3)

        @keyboard_action
        def action_toggle_plan_mode(self) -> None:
            """Toggle mode: normal -> plan -> spec -> execute -> analysis -> normal (Shift+Tab)."""
            tui_log("action_toggle_plan_mode")

            # Block during execution (keyboard_action decorator handles this,
            # but add explicit check with user message for clarity)
            if self._mode_state.is_locked():
                self.notify(
                    "Cannot change plan mode during execution. Wait for completion or cancel first.",
                    severity="warning",
                    timeout=3,
                )
                return

            if self._mode_state.plan_mode == "normal":
                # normal → plan
                self._handle_plan_mode_change("plan")
            elif self._mode_state.plan_mode == "plan":
                # plan → spec
                self._handle_plan_mode_change("spec")
            elif self._mode_state.plan_mode == "spec":
                # spec → execute (show plan/spec selector if sessions exist)
                self._handle_plan_mode_change("execute")
            elif self._mode_state.plan_mode == "execute":
                # execute -> analysis
                self._handle_plan_mode_change("analysis")
            elif self._mode_state.plan_mode == "analysis":
                # analysis -> normal
                self._handle_plan_mode_change("normal")

        @keyboard_action
        def action_trigger_override(self) -> None:
            """Trigger human override of final answer selection (Ctrl+O shortcut)."""
            tui_log("action_trigger_override")

            if not self._mode_state.override_available:
                self.notify("Override not available (voting not complete)", severity="warning", timeout=2)
                return

            if not self._answers:
                self.notify("No answers to override", severity="warning", timeout=2)
                return

            # Show the answer browser modal for override selection
            # TODO: Create dedicated OverrideModal or enhance AnswerBrowserModal
            self.action_open_answer_browser()

        def on_tool_call_card_tool_card_clicked(self, event: ToolCallCard.ToolCardClicked) -> None:
            """Handle tool card click - show detail modal."""
            card = event.card
            modal = ToolDetailModal(
                tool_name=card.display_name,
                icon=card.icon,
                status=card.status,
                elapsed=card.elapsed_str,
                args=card.params,
                result=card.result,
                error=card.error,
            )
            self.push_screen(modal)
            event.stop()

        def on_tool_batch_card_tool_in_batch_clicked(
            self,
            event: ToolBatchCard.ToolInBatchClicked,
        ) -> None:
            """Handle tool-in-batch click - show detail modal."""
            tool = event.tool_item
            modal = ToolDetailModal(
                tool_name=tool.display_name,
                icon="🔧",  # Generic tool icon
                status=tool.status,
                elapsed=f"{tool.elapsed_seconds:.1f}s" if tool.elapsed_seconds else None,
                args=tool.args_full,
                result=tool.result_full,
                error=tool.error,
            )
            self.push_screen(modal)
            event.stop()

        def on_task_plan_card_open_modal(self, event: TaskPlanCard.OpenModal) -> None:
            """Handle task plan card click - show task plan modal."""
            modal = TaskPlanModal(
                tasks=event.tasks,
                focused_task_id=event.focused_task_id,
            )
            self.push_screen(modal)
            event.stop()

        def _build_subagent_status_callback(
            self,
            card: Any | None = None,
            fallback_subagents: list[Any] | None = None,
        ) -> Callable[[str], Any | None]:
            """Return a callback that always pulls the latest subagent data."""

            def _status_callback(subagent_id: str) -> Any | None:
                # Fast path: known source card from the click target.
                try:
                    if card is not None:
                        for subagent in card.subagents:
                            if getattr(subagent, "id", None) == subagent_id:
                                return subagent
                except Exception:
                    pass

                # Fallback: scan all currently rendered subagent cards.
                try:
                    for panel in self.agent_widgets.values():
                        try:
                            subagent_cards = panel.query(SubagentCard)
                        except Exception:
                            continue
                        for candidate_card in subagent_cards:
                            for subagent in getattr(candidate_card, "subagents", []):
                                if getattr(subagent, "id", None) == subagent_id:
                                    return subagent
                except Exception:
                    pass

                # Final fallback: use snapshot payload carried by event.
                if fallback_subagents:
                    for subagent in fallback_subagents:
                        if getattr(subagent, "id", None) == subagent_id:
                            return subagent
                return None

            return _status_callback

        def _build_spawn_status_callback(
            self,
            agent_id: str,
            seed_subagents: list[SubagentDisplayData] | None = None,
            card: Any | None = None,
        ) -> Callable[[str], SubagentDisplayData | None]:
            """Build a resilient status callback for spawn_subagents cards.

            Primary source: live card snapshots from `_build_subagent_status_callback`.
            Fallback source: `<workspace>/subagents/_spawn_status.json`.
            """
            fallback_subagents = list(seed_subagents or [])
            by_id: dict[str, SubagentDisplayData] = {sa.id: sa for sa in fallback_subagents if getattr(sa, "id", None)}
            live_callback = self._build_subagent_status_callback(
                card=card,
                fallback_subagents=fallback_subagents,
            )

            status_file: Path | None = None
            try:
                orchestrator = getattr(self.coordination_display, "orchestrator", None)
                agent = getattr(orchestrator, "agents", {}).get(agent_id) if orchestrator else None
                filesystem_manager = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
                workspace = getattr(filesystem_manager, "get_current_workspace", lambda: None)() if filesystem_manager else None
                if workspace:
                    status_file = Path(workspace) / "subagents" / "_spawn_status.json"
            except Exception:
                status_file = None

            cache: dict[str, Any] = {
                "mtime": None,
                "entries": {},
            }

            def _load_entries() -> dict[str, dict[str, Any]]:
                if status_file is None or not status_file.exists():
                    return {}
                try:
                    mtime = status_file.stat().st_mtime
                except OSError:
                    return {}
                if cache["mtime"] == mtime:
                    return cache["entries"]
                try:
                    payload = json.loads(status_file.read_text())
                except (OSError, json.JSONDecodeError):
                    return {}
                entries: dict[str, dict[str, Any]] = {}
                for entry in payload.get("subagents", []):
                    if not isinstance(entry, dict):
                        continue
                    subagent_id = entry.get("subagent_id") or entry.get("id")
                    if subagent_id:
                        entries[str(subagent_id)] = entry
                cache["mtime"] = mtime
                cache["entries"] = entries
                return entries

            def _lookup_known_background_status(subagent_id: str) -> str | None:
                panel = self.agent_widgets.get(agent_id)
                if panel is None:
                    return None

                timeline = None
                get_timeline = getattr(panel, "_get_timeline", None)
                if callable(get_timeline):
                    try:
                        timeline = get_timeline()
                    except Exception:
                        timeline = None
                if timeline is None:
                    return None

                collect_known = getattr(timeline, "_collect_known_background_statuses", None)
                if not callable(collect_known):
                    return None

                try:
                    statuses = collect_known() or {}
                except Exception:
                    return None
                if not isinstance(statuses, dict):
                    return None

                status = statuses.get(subagent_id)
                if status is None:
                    status = statuses.get(str(subagent_id))
                if status is None:
                    return None

                normalized = str(status).lower().strip()
                return normalized or None

            def _lookup_background_history_entry(subagent_id: str) -> dict[str, Any] | None:
                panel = self.agent_widgets.get(agent_id)
                if panel is None:
                    return None
                history_fn = getattr(panel, "_get_background_tool_history", None)
                if not callable(history_fn):
                    return None
                try:
                    history_items = history_fn() or []
                except Exception:
                    return None
                for item in history_items:
                    if not isinstance(item, dict):
                        continue
                    candidate_id = str(item.get("async_id") or item.get("job_id") or item.get("subagent_id") or "").strip()
                    if not candidate_id:
                        continue
                    if candidate_id == subagent_id:
                        return item
                return None

            def _status_callback(subagent_id: str) -> SubagentDisplayData | None:
                latest = live_callback(subagent_id)
                if latest and latest.status not in {"running", "pending"}:
                    return latest

                entry = _load_entries().get(subagent_id)
                if not entry:
                    known_status = _lookup_known_background_status(subagent_id)
                    if known_status and known_status not in {"running", "pending", "background", "queued"}:
                        baseline = latest or by_id.get(subagent_id)
                        merged = _build_subagent_display_data(
                            {
                                "subagent_id": subagent_id,
                                "status": known_status,
                            },
                            baseline,
                        )
                        by_id[subagent_id] = merged
                        return merged

                    history_entry = _lookup_background_history_entry(subagent_id)
                    if not history_entry:
                        return latest

                    history_status = str(history_entry.get("latest_status") or history_entry.get("status") or "").lower().strip()
                    if history_status in {"running", "pending", "background", "queued"} or not history_status:
                        return latest
                    if history_status in {"cancelled", "canceled", "stopped"}:
                        history_status = "canceled"

                    history_payload: dict[str, Any] = {
                        "subagent_id": subagent_id,
                        "status": history_status,
                    }
                    result_payload = history_entry.get("result")
                    if isinstance(result_payload, str) and result_payload:
                        if history_status in {"failed", "error", "timeout", "canceled"}:
                            history_payload["error"] = result_payload
                        else:
                            history_payload["answer"] = result_payload
                    error_payload = history_entry.get("error")
                    if isinstance(error_payload, str) and error_payload:
                        history_payload["error"] = error_payload

                    baseline = latest or by_id.get(subagent_id)
                    merged = _build_subagent_display_data(history_payload, baseline)
                    by_id[subagent_id] = merged
                    return merged

                # Merge running file entries too: the spawn status file can carry
                # authoritative timeout metadata before terminal results arrive.
                baseline = latest or by_id.get(subagent_id)
                merged = _build_subagent_display_data(entry, baseline)
                by_id[subagent_id] = merged
                return merged

            return _status_callback

        def on_subagent_card_open_modal(self, event: SubagentCard.OpenModal) -> None:
            """Handle subagent card click - open separate screen."""
            # Track timeline child count before entering subagent view
            timeline_count_before = 0
            try:
                active_agent = self.coordination_display.agent_ids[0] if self.coordination_display.agent_ids else None
                if active_agent and active_agent in self.agent_widgets:
                    panel = self.agent_widgets[active_agent]
                    tl = panel._get_timeline()
                    if tl:
                        timeline_count_before = len(tl.children)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            def _on_screen_dismiss(result: object = None) -> None:
                """Show badge if new timeline items appeared while in subagent view."""
                try:
                    active_agent = self.coordination_display.agent_ids[0] if self.coordination_display.agent_ids else None
                    if active_agent and active_agent in self.agent_widgets:
                        panel = self.agent_widgets[active_agent]
                        tl = panel._get_timeline()
                        if tl:
                            new_count = len(tl.children) - timeline_count_before
                            if new_count > 0:
                                self.notify(
                                    f"\u2193 {new_count} new item{'s' if new_count != 1 else ''} added",
                                    severity="information",
                                    timeout=5,
                                )
                                # Scroll to bottom to show new content
                                tl.scroll_end(animate=True)
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

            card = getattr(event, "card", None)
            status_callback = self._build_subagent_status_callback(
                card=card,
                fallback_subagents=event.all_subagents,
            )
            screen = SubagentScreen(
                subagent=event.subagent,
                all_subagents=event.all_subagents,
                status_callback=status_callback,
                send_message_callback=self._subagent_message_callback,
                continue_subagent_callback=getattr(self, "_subagent_continue_callback", None),
                subagent_index=getattr(event, "subagent_index", None),
            )
            self.push_screen(screen, _on_screen_dismiss)
            event.stop()

        # Close handler removed - SubagentScreen handles its own closing
        # def on_subagent_view_close_requested(self, event: SubagentView.CloseRequested) -> None:
        #     """Handle close request from the right-panel subagent view."""
        #     ...

        def on_tasks_clicked(self, event: TasksClicked) -> None:
            """Handle tasks label click in ribbon - show task plan modal."""
            if event.agent_id in self.agent_widgets:
                panel = self.agent_widgets[event.agent_id]
                tasks = panel.get_task_plan_tasks()
                if tasks:
                    modal = TaskPlanModal(tasks=tasks)
                    self.push_screen(modal)
            event.stop()

        def on_background_tasks_clicked(self, event: BackgroundTasksClicked) -> None:
            """Handle background tasks label click in ribbon."""
            background_tasks, recent_tasks = self._collect_background_tools_for_agent(event.agent_id)
            if background_tasks or recent_tasks:
                self._show_modal_async(
                    BackgroundTasksModal(
                        background_tasks,
                        recent_tasks=recent_tasks,
                        agent_id=event.agent_id,
                    ),
                )
            else:
                self.notify("No background jobs running", severity="warning", timeout=3)
            event.stop()

        def on_context_paths_clicked(self, event: ContextPathsClicked) -> None:
            """Handle context paths icon click in ribbon - open context paths modal."""
            self._show_context_modal()
            event.stop()

        def on_final_presentation_card_view_final_answer(
            self,
            event: FinalPresentationCard.ViewFinalAnswer,
        ) -> None:
            """Re-open FinalAnswerModal from the card's View button.

            Reuses the stored modal data (with changes) so the Review
            Changes tab is still available, but marked as already approved.
            """
            from .textual.widgets.modals.final_answer_modal import (
                FinalAnswerModal,
                FinalAnswerModalData,
            )

            card = event.card
            display = self.coordination_display

            # Reuse stored data if available (includes changes for review tab)
            stored = getattr(display, "_last_final_answer_modal_data", None)
            # Determine prior action from stored result
            stored_result = getattr(display, "_last_final_answer_result", None)
            if stored_result is not None:
                prior_action = "approved" if stored_result.approved else "rejected"
            else:
                prior_action = None  # No decision was made yet

            # Resolve workspace_path: prefer stored data, then final workspace from logs
            workspace_path = None
            orchestrator = getattr(display, "orchestrator", None)
            if orchestrator is not None:
                try:
                    resolve_fn = getattr(orchestrator, "_resolve_final_workspace_path", None)
                    agent_id = card.agent_id if hasattr(card, "agent_id") else None
                    if resolve_fn and agent_id:
                        workspace_path = resolve_fn(agent_id)
                except Exception:
                    pass

            if stored is not None:
                data = FinalAnswerModalData(
                    answer_content=stored.answer_content,
                    vote_results=stored.vote_results,
                    agent_id=stored.agent_id,
                    model_name=stored.model_name,
                    post_eval_content=stored.post_eval_content,
                    post_eval_status=stored.post_eval_status,
                    changes=stored.changes,
                    context_paths=stored.context_paths,
                    prior_action=prior_action,
                    workspace_path=stored.workspace_path or workspace_path,
                )
            else:
                data = FinalAnswerModalData(
                    answer_content=card.get_content(),
                    vote_results=card.vote_results,
                    agent_id=card.agent_id,
                    model_name=card.model_name,
                    context_paths=card.context_paths,
                    prior_action=prior_action,
                    workspace_path=workspace_path,
                )
            modal = FinalAnswerModal(data=data)

            def _on_modal_dismissed(_result=None):
                # Update card review status if a new decision was made
                # Only set review status when there are actual changes to review;
                # workspace-only or answer-only modals don't need a status badge.
                has_real_changes = bool(data.changes)
                if _result is not None and display is not None and has_real_changes:
                    # Prefer updating the card that launched the modal so the
                    # indicator is guaranteed to reflect the same decision.
                    try:
                        status = "approved" if _result.approved else "rejected"
                        card.set_review_status(status)
                    except Exception:
                        logger.exception(
                            "[TextualDisplay] Failed to update clicked final card review status",
                        )

                    display._update_card_review_status(_result)
                    display._last_final_answer_result = _result
                # Scroll the final card into view after modal closes
                try:
                    card.scroll_visible(animate=True, top=False)
                except Exception:
                    pass

            self.push_screen(modal, _on_modal_dismissed)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle button clicks in main app."""
            if event.button.id == "turn_cancel_button":
                # Trigger cancellation (same as Ctrl+C)
                self.coordination_display.request_cancellation()
                self.notify("Cancelling turn...", severity="warning", timeout=2)
                event.stop()
            elif event.button.id == "inject_target_button":
                self.action_toggle_human_input_target()
                event.stop()
            elif event.button.id == "queue_cancel_latest_button":
                self._cancel_latest_queued_human_input()
                event.stop()
            elif event.button.id == "queue_clear_button":
                self._clear_all_queued_human_input()
                event.stop()

        def _cancel_latest_queued_human_input(self) -> None:
            """Cancel the newest queued runtime-injection message."""
            hook = self._human_input_hook
            removed = None
            if hook and hasattr(hook, "pop_latest_pending_input"):
                try:
                    removed = hook.pop_latest_pending_input()
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to cancel latest queued message: {e}")

            self._refresh_human_input_pending_state()
            self._sync_queued_input_banner_from_hook()

            if removed:
                preview = str(removed.get("content", ""))
                if len(preview) > 40:
                    preview = preview[:37] + "..."
                self.notify(
                    f'Cancelled latest queued injection: "{preview}"',
                    severity="information",
                    timeout=2,
                )
            else:
                self.notify("No queued injections to cancel.", severity="information", timeout=2)

        def _clear_all_queued_human_input(self) -> None:
            """Clear all queued runtime-injection messages."""
            hook = self._human_input_hook
            if hook and hasattr(hook, "clear_pending_input"):
                try:
                    hook.clear_pending_input()
                except Exception as e:
                    tui_log(f"[HumanInput] Failed to clear queued injections: {e}")

            self._clear_queued_input()
            self.notify("Cleared queued runtime injections.", severity="information", timeout=2)

        def _handle_cancel(self) -> None:
            """Handle cancel action from button or 'q' key."""
            if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                # Request cancellation from orchestrator
                self.notify("Cancellation requested...", severity="warning")
                # Set cancel flag if orchestrator supports it
                if hasattr(self.coordination_display.orchestrator, "cancel_requested"):
                    self.coordination_display.orchestrator.cancel_requested = True
            else:
                self.notify("Nothing to cancel", severity="information")

        def action_toggle_safe_keyboard(self):
            """Toggle safe keyboard mode to ignore hotkeys."""
            self.coordination_display.safe_keyboard_mode = not self.coordination_display.safe_keyboard_mode
            status = "ON" if self.coordination_display.safe_keyboard_mode else "OFF"
            self.add_orchestrator_event(f"Keyboard safe mode {status}")
            self._update_safe_indicator()

        def action_agent_selector(self):
            """Show agent selector."""
            self.show_agent_selector()

        def action_coordination_table(self):
            """Show coordination table."""
            self._show_coordination_table_modal()

        def action_quit(self):
            """Quit the application."""
            self.exit()

        def action_handle_ctrl_c(self) -> None:
            """Handle Ctrl+C: clear input / cancel turn, or quit if nothing to do."""
            # Check if input is focused and has content
            if hasattr(self, "question_input") and self.question_input.has_focus:
                if self.question_input.value:
                    # Clear input
                    self.question_input.value = ""
                    self.notify("Input cleared", timeout=1)
                    return

            # Check if there's an active turn to cancel
            has_active_turn = (
                hasattr(self.coordination_display, "_user_quit_requested")
                and not self.coordination_display._user_quit_requested
                and hasattr(self.coordination_display, "orchestrator")
                and self.coordination_display.orchestrator is not None
            )

            if has_active_turn:
                # Cancel the turn
                self.coordination_display.request_cancellation()
                self.notify("Cancelling turn...", severity="warning", timeout=2)
            else:
                # Nothing to cancel, input empty - quit
                self.exit()

        def action_toggle_cwd(self) -> None:
            """Toggle CWD auto-include (Ctrl+P binding)."""
            self._toggle_cwd_auto_include()

        def _set_human_input_target_mode(self, mode: str) -> None:
            """Set runtime human-input target mode and notify user."""
            normalized = str(mode or "all").strip().lower()
            if normalized not in {"all", "current"}:
                normalized = "all"
            self._human_input_target_mode = normalized
            self._update_human_input_target_button()
            label = "all agents" if normalized == "all" else "current agent tab"
            self.notify(f"Runtime injection target: {label}", severity="information", timeout=2)

        def _toggle_human_input_target_mode(self) -> None:
            """Toggle runtime human-input target mode between all/current."""
            next_mode = "current" if self._human_input_target_mode == "all" else "all"
            self._set_human_input_target_mode(next_mode)

        def action_toggle_human_input_target(self) -> None:
            """Toggle runtime human-input target mode (Ctrl+Shift+I)."""
            self._toggle_human_input_target_mode()

        def action_toggle_task_plan(self) -> None:
            """Toggle task plan visibility (Ctrl+T binding)."""
            if self._active_agent_id and self._active_agent_id in self.agent_widgets:
                self.agent_widgets[self._active_agent_id].toggle_task_plan()

        def action_toggle_theme(self) -> None:
            """Toggle between dark and light themes (Ctrl+Shift+T binding)."""
            current = self.coordination_display.theme
            # Cycle through core themes only: dark -> light -> dark
            try:
                current_idx = self.CORE_THEMES.index(current)
                next_idx = (current_idx + 1) % len(self.CORE_THEMES)
                new_theme = self.CORE_THEMES[next_idx]
            except ValueError:
                # Current theme not in core themes, reset to dark
                new_theme = "dark"

            try:
                # Use our custom registered themes for proper color palette support
                textual_theme_name = self.THEME_NAME_MAP.get(new_theme, "massgen-dark")
                self.theme = textual_theme_name

                # Update the theme state
                self.coordination_display.theme = new_theme

                # Toggle theme classes on the app for CSS-based theme switching
                # This allows theme-specific styles to update dynamically
                if new_theme == "light":
                    self.add_class("theme-light")
                    self.remove_class("theme-dark")
                else:
                    self.add_class("theme-dark")
                    self.remove_class("theme-light")

                # Save the new theme to user preferences
                try:
                    user_settings = get_user_settings()
                    user_settings.theme = new_theme
                except Exception:
                    pass
            except Exception as e:
                self.notify(f"Theme error: {e}", severity="error", timeout=3)
                logger.exception(f"Failed to toggle theme: {e}")
                return

            # Update status bar indicator
            self._update_theme_indicator()
            self.notify(f"Theme: {new_theme.title()}", timeout=1.5)

        def action_toggle_copy_mode(self) -> None:
            """Toggle copy mode (Ctrl+Shift+S).

            Releases the terminal mouse so the user can drag-select text natively
            and copy with the terminal's built-in shortcut. Press again to restore
            Textual's normal mouse behavior.
            """
            try:
                banner = self.query_one(CopyModeBanner)
            except Exception:
                logger.warning("[copy_mode] banner not mounted; cannot toggle")
                return
            new_state = not banner.active
            banner.set_active(new_state)
            self._set_terminal_mouse_capture(not new_state)
            self._copy_mode_active = new_state
            self.notify(
                "Copy mode ON — drag to select, then Cmd/Ctrl+C in your terminal" if new_state else "Copy mode OFF",
                timeout=2.0,
            )

        def _set_terminal_mouse_capture(self, enabled: bool) -> None:
            """Toggle terminal mouse-tracking escape codes via the Textual driver."""
            set_terminal_mouse_capture(getattr(self, "_driver", None), enabled)

        def action_show_help(self) -> None:
            """Show help modal (Ctrl+/ binding)."""
            self._show_help_modal()

        def action_show_evaluation_criteria(self) -> None:
            """Show the active evaluation criteria modal (Ctrl+E binding)."""
            criteria = getattr(self, "_runtime_evaluation_criteria", None) or []
            source = getattr(self, "_runtime_evaluation_criteria_source", "default")
            self._show_modal_async(
                EvaluationCriteriaModal(criteria=criteria, source=source),
            )

        def action_open_vote_results(self):
            """Open vote results modal."""
            text = getattr(self, "_latest_vote_results_text", "")
            if not text:
                status = getattr(self.coordination_display, "_final_answer_metadata", {}) or {}
                text = self.coordination_display._format_vote_results(status.get("vote_results", {})) if hasattr(self.coordination_display, "_format_vote_results") else ""
            if not text.strip():
                text = ""
            self._show_modal_async(
                VoteResultsModal(
                    results_text=text,
                    vote_counts=self._vote_counts.copy() if hasattr(self, "_vote_counts") else None,
                    votes=self._votes.copy() if hasattr(self, "_votes") else None,
                ),
            )

        def action_open_system_status(self):
            """Open system status log."""
            self._show_system_status_modal()

        def action_open_orchestrator(self):
            """Open orchestrator events modal."""
            self._show_orchestrator_modal()

        def action_open_agent_output(self):
            """Open full agent output modal for currently active agent."""
            agent_id = self._active_agent_id
            if not agent_id:
                # Fall back to first agent
                agent_id = self.coordination_display.agent_ids[0] if self.coordination_display.agent_ids else None
            if agent_id:
                self._show_agent_output_modal(agent_id)
            else:
                self.notify("No agent selected", severity="warning")

        def _collect_background_tools(self) -> list[dict[str, Any]]:
            """Collect active background jobs across all agent panels."""
            active, _recent = self._collect_background_activity()
            return active

        @staticmethod
        def _sort_background_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Sort background task records chronologically by start time."""
            return sorted(tasks, key=lambda item: item.get("start_time") or datetime.min)

        def _collect_background_activity(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            """Collect active + recent background jobs across all agent panels."""
            active_tasks: list[dict[str, Any]] = []
            recent_tasks: list[dict[str, Any]] = []
            for agent_id, panel in self.agent_widgets.items():
                panel_active, panel_recent = self._collect_background_tools_for_agent(agent_id)
                active_tasks.extend(panel_active)
                recent_tasks.extend(panel_recent)
            return self._sort_background_tasks(active_tasks), self._sort_background_tasks(recent_tasks)

        def _collect_background_tools_for_agent(self, agent_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            """Collect active + recent background jobs from a single agent panel."""
            panel = self.agent_widgets.get(agent_id)
            if panel is None:
                return [], []

            get_history = getattr(panel, "_get_background_tool_history", None)
            if callable(get_history):
                try:
                    history_items = get_history() or []
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")
                    history_items = []
                active: list[dict[str, Any]] = []
                recent: list[dict[str, Any]] = []
                for task in history_items:
                    if not isinstance(task, dict):
                        continue
                    merged_task = dict(task)
                    merged_task.setdefault("agent_id", agent_id)
                    is_active = bool(merged_task.get("is_active", True))
                    if is_active:
                        active.append(merged_task)
                    else:
                        recent.append(merged_task)
                if active or recent:
                    return self._sort_background_tasks(active), self._sort_background_tasks(recent)

            get_tools = getattr(panel, "_get_background_tools", None)
            if not callable(get_tools):
                return [], []

            try:
                panel_tasks = get_tools() or []
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
                return [], []

            tasks: list[dict[str, Any]] = []
            for task in panel_tasks:
                if not isinstance(task, dict):
                    continue
                merged_task = dict(task)
                merged_task.setdefault("agent_id", agent_id)
                tasks.append(merged_task)
            return self._sort_background_tasks(tasks), []

        def _update_running_tools_count(self) -> None:
            """Refresh status-bar tool counters across all agent panels."""
            if not self._status_bar and not self._status_ribbon:
                return

            running_count = 0
            background_count = 0
            per_agent_background: dict[str, int] = {}

            for agent_id, panel in self.agent_widgets.items():
                get_running = getattr(panel, "_get_running_tools_count", None)
                if callable(get_running):
                    try:
                        running_count += int(get_running())
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

                agent_background_count = 0
                get_background = getattr(panel, "_get_background_tools", None)
                if callable(get_background):
                    try:
                        agent_background_count = len(get_background() or [])
                        background_count += agent_background_count
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")
                per_agent_background[agent_id] = agent_background_count

            if self._status_bar:
                self._status_bar.update_running_tools(
                    running_count,
                    background_count=background_count,
                )
            if self._status_ribbon:
                for agent_id, count in per_agent_background.items():
                    self._status_ribbon.set_background_jobs(agent_id, count)

        def action_open_background_tools(self) -> None:
            """Open modal showing active background tool jobs."""
            background_tasks, recent_tasks = self._collect_background_activity()
            if not background_tasks and not recent_tasks:
                self.notify("No background jobs running", severity="warning", timeout=3)
                return
            self._show_modal_async(
                BackgroundTasksModal(
                    background_tasks,
                    recent_tasks=recent_tasks,
                ),
            )

        def action_open_cost_breakdown(self):
            """Open cost breakdown modal."""
            self._show_cost_breakdown_modal()

        def action_open_metrics(self):
            """Open metrics modal."""
            self._show_metrics_modal()

        def action_show_shortcuts(self):
            """Show keyboard shortcuts modal."""
            self._show_modal_async(KeyboardShortcutsModal())

        def action_open_mcp_status(self):
            """Open MCP server status modal."""
            mcp_status = self._get_mcp_status()
            if not mcp_status["servers"]:
                self.notify("No MCP servers connected", severity="warning", timeout=3)
                return
            self._show_modal_async(MCPStatusModal(mcp_status))

        def action_open_answer_browser(self):
            """Open answer browser modal."""
            if not self._answers:
                self.notify("No answers yet", severity="warning", timeout=3)
                return
            self._show_modal_async(
                AnswerBrowserModal(
                    answers=self._answers,
                    votes=self._votes,
                    agent_ids=self.coordination_display.agent_ids,
                    winner_agent_id=self._winner_agent_id,
                ),
            )

        def action_open_timeline(self):
            """Open timeline visualization modal."""
            if not self._answers and not self._votes:
                self.notify("No activity yet", severity="warning", timeout=3)
                return
            self._show_modal_async(
                TimelineModal(
                    answers=self._answers,
                    votes=self._votes,
                    agent_ids=self.coordination_display.agent_ids,
                    winner_agent_id=self._winner_agent_id,
                    restart_history=self._restart_history,
                ),
            )

        def action_open_workspace_browser(self):
            """Open workspace browser modal to view answer snapshots."""
            from pathlib import Path

            # Get current workspace paths for ALL agents
            agent_workspace_paths: dict[str, str] = {}
            agent_final_paths: dict[str, str] = {}
            orchestrator = getattr(self.coordination_display, "orchestrator", None)

            logger.info(f"[WorkspaceBrowser] orchestrator: {orchestrator is not None}")

            if orchestrator:
                # Get current workspaces
                for agent_id, agent in getattr(orchestrator, "agents", {}).items():
                    fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
                    if fm:
                        workspace = getattr(fm, "get_current_workspace", lambda: None)()
                        if workspace:
                            agent_workspace_paths[agent_id] = str(workspace)

                # Scan for final workspaces in log directory
                log_dir = getattr(orchestrator, "log_session_dir", None)
                logger.info(f"[WorkspaceBrowser] log_dir: {log_dir}")

                if log_dir:
                    log_path = Path(log_dir)

                    def scan_for_final(base_dir: Path) -> dict[str, str]:
                        found = {}
                        final_dir = base_dir / "final"
                        logger.info(f"[WorkspaceBrowser] Checking final_dir: {final_dir}, exists: {final_dir.exists()}")
                        if final_dir.exists() and final_dir.is_dir():
                            for agent_dir in final_dir.iterdir():
                                logger.info(f"[WorkspaceBrowser] Found agent_dir: {agent_dir.name}")
                                if agent_dir.is_dir() and agent_dir.name.startswith("agent_"):
                                    ws_path = agent_dir / "workspace"
                                    logger.info(f"[WorkspaceBrowser] ws_path: {ws_path}, exists: {ws_path.exists()}")
                                    if ws_path.exists():
                                        found[agent_dir.name] = str(ws_path)
                        return found

                    # Try direct final/ directory
                    agent_final_paths = scan_for_final(log_path)
                    logger.info(f"[WorkspaceBrowser] Direct scan result: {agent_final_paths}")

                    # If not found, try turn_*/attempt_* subdirectories
                    if not agent_final_paths:
                        for turn_dir in sorted(log_path.glob("turn_*"), reverse=True):
                            for attempt_dir in sorted(turn_dir.glob("attempt_*"), reverse=True):
                                logger.info(f"[WorkspaceBrowser] Checking attempt_dir: {attempt_dir}")
                                agent_final_paths = scan_for_final(attempt_dir)
                                if agent_final_paths:
                                    break
                            if agent_final_paths:
                                break

            logger.info(f"[WorkspaceBrowser] Final agent_final_paths: {agent_final_paths}")
            logger.info(f"[WorkspaceBrowser] agent_workspace_paths: {agent_workspace_paths}")

            # Allow opening even without answers if we have current or final workspace
            if not self._answers and not agent_workspace_paths and not agent_final_paths:
                self.notify("No answers yet - workspaces available after agents submit", severity="warning", timeout=3)
                return

            self._present_workspace_browser_modal(
                WorkspaceBrowserModal(
                    answers=self._answers,
                    agent_ids=self.coordination_display.agent_ids,
                    agent_workspace_paths=agent_workspace_paths,
                    agent_final_paths=agent_final_paths,
                ),
            )

        def _show_workspace_browser_for_agent(
            self,
            agent_id: str,
            preferred_final_workspace: str | None = None,
        ):
            """Open workspace browser focused on the winning agent's final workspace.

            Args:
                agent_id: The agent ID to show workspace for (typically the winner)
                preferred_final_workspace: Optional already-resolved final workspace path
                    for the agent. When provided, avoids rescanning log directories.
            """
            from pathlib import Path

            started_total = time.perf_counter()
            # Get current workspace paths for ALL agents
            agent_workspace_paths: dict[str, str] = {}
            final_workspace_paths: dict[str, str] = {}
            orchestrator = getattr(self.coordination_display, "orchestrator", None)

            if preferred_final_workspace:
                preferred_path = Path(preferred_final_workspace)
                if preferred_path.exists():
                    final_workspace_paths[agent_id] = str(preferred_path)
                    if self._timing_debug:
                        tui_log(
                            "[TIMING] WorkspaceBrowser.reuse_preferred_final_workspace " f"0.0ms agent={agent_id}",
                        )

            if orchestrator:
                started_collect = time.perf_counter()
                # Get current workspaces
                for aid, agent in getattr(orchestrator, "agents", {}).items():
                    fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
                    if fm:
                        workspace = getattr(fm, "get_current_workspace", lambda: None)()
                        if workspace:
                            agent_workspace_paths[aid] = str(workspace)
                if self._timing_debug:
                    tui_log(
                        "[TIMING] WorkspaceBrowser.collect_current_workspaces " f"{(time.perf_counter() - started_collect) * 1000.0:.1f}ms " f"count={len(agent_workspace_paths)}",
                    )

                # Scan for final workspaces in log directory (unless we already
                # received a resolved path from the final-answer card).
                log_dir = getattr(orchestrator, "log_session_dir", None)
                if log_dir and not final_workspace_paths:
                    started_scan = time.perf_counter()
                    log_path = Path(log_dir)

                    def scan_for_final(base_dir: Path) -> dict[str, str]:
                        found = {}
                        final_dir = base_dir / "final"
                        if final_dir.exists() and final_dir.is_dir():
                            for agent_dir in final_dir.iterdir():
                                if agent_dir.is_dir() and agent_dir.name.startswith("agent_"):
                                    ws_path = agent_dir / "workspace"
                                    if ws_path.exists():
                                        found[agent_dir.name] = str(ws_path)
                        return found

                    # Try direct final/ directory
                    final_workspace_paths = scan_for_final(log_path)

                    # If not found, try turn_*/attempt_* subdirectories
                    if not final_workspace_paths:
                        for turn_dir in sorted(log_path.glob("turn_*"), reverse=True):
                            for attempt_dir in sorted(turn_dir.glob("attempt_*"), reverse=True):
                                final_workspace_paths = scan_for_final(attempt_dir)
                                if final_workspace_paths:
                                    break
                            if final_workspace_paths:
                                break
                    if self._timing_debug:
                        tui_log(
                            "[TIMING] WorkspaceBrowser.scan_final_workspaces " f"{(time.perf_counter() - started_scan) * 1000.0:.1f}ms " f"count={len(final_workspace_paths)}",
                        )

            # Merge final workspaces into agent_workspace_paths with special key
            # The modal will detect keys ending with "-final" as final workspaces
            agent_final_paths: dict[str, str] = {}
            for aid, path in final_workspace_paths.items():
                agent_final_paths[aid] = path

            if not self._answers and not agent_workspace_paths and not agent_final_paths:
                self.notify("No workspace available yet", severity="warning", timeout=3)
                if self._timing_debug:
                    tui_log(
                        "[TIMING] WorkspaceBrowser.open " f"{(time.perf_counter() - started_total) * 1000.0:.1f}ms result=no_workspace",
                    )
                return

            self._present_workspace_browser_modal(
                WorkspaceBrowserModal(
                    answers=self._answers,
                    agent_ids=self.coordination_display.agent_ids,
                    agent_workspace_paths=agent_workspace_paths,
                    agent_final_paths=agent_final_paths,
                    default_agent=agent_id,
                    default_to_final=True,
                ),
            )
            if self._timing_debug:
                tui_log(
                    "[TIMING] WorkspaceBrowser.open "
                    f"{(time.perf_counter() - started_total) * 1000.0:.1f}ms "
                    f"answers={len(self._answers)} current={len(agent_workspace_paths)} final={len(agent_final_paths)}",
                )

        def _present_workspace_browser_modal(self, modal: WorkspaceBrowserModal) -> bool:
            """Open workspace browser once, suppressing duplicate open bursts."""
            now = time.monotonic()
            # Ignore rapid repeated requests before the first modal appears.
            if now - self._workspace_browser_last_request_at < 0.4:
                if self._timing_debug:
                    tui_log("[TIMING] WorkspaceBrowser.open suppressed=throttled")
                return False
            if self._workspace_browser_open_pending:
                if self._timing_debug:
                    tui_log("[TIMING] WorkspaceBrowser.open suppressed=pending")
                return False

            # If a workspace modal is already on stack, don't push another.
            try:
                if any(isinstance(screen, WorkspaceBrowserModal) for screen in self.screen_stack):
                    if self._timing_debug:
                        tui_log("[TIMING] WorkspaceBrowser.open suppressed=already_open")
                    return False
            except Exception:
                pass

            self._workspace_browser_open_pending = True
            self._workspace_browser_last_request_at = now

            def _on_dismiss(_result: Any = None) -> None:
                self._workspace_browser_open_pending = False

            try:
                self.push_screen(modal, _on_dismiss)
                return True
            except Exception:
                self._workspace_browser_open_pending = False
                raise

        def action_open_unified_browser(self):
            """Open unified browser modal with tabs for Answers, Votes, Workspace, Timeline."""
            if not self._answers and not self._votes:
                self.notify("No activity yet", severity="warning", timeout=3)
                return
            self._show_modal_async(
                BrowserTabsModal(
                    answers=self._answers,
                    votes=self._votes,
                    vote_counts=self._vote_counts.copy() if hasattr(self, "_vote_counts") else {},
                    agent_ids=self.coordination_display.agent_ids,
                    winner_agent_id=self._winner_agent_id,
                ),
            )

        def _get_mcp_status(self) -> dict[str, Any]:
            """Gather MCP server status from orchestrator."""
            orchestrator = getattr(self.coordination_display, "orchestrator", None)
            if not orchestrator:
                return {"servers": [], "total_tools": 0}

            servers = []
            total_tools = 0

            # MCP client is typically shared across agents, check the first one with a backend
            agents = getattr(orchestrator, "agents", {})
            for agent_id, agent in agents.items():
                backend = getattr(agent, "backend", None)
                if not backend:
                    continue
                mcp_client = getattr(backend, "_mcp_client", None)
                if not mcp_client:
                    continue

                # Get server names
                server_names = []
                if hasattr(mcp_client, "get_server_names"):
                    server_names = mcp_client.get_server_names()
                elif hasattr(mcp_client, "_server_clients"):
                    server_names = list(mcp_client._server_clients.keys())

                # Get available tools
                all_tools = []
                if hasattr(mcp_client, "get_available_tools"):
                    all_tools = mcp_client.get_available_tools()

                for name in server_names:
                    # Filter tools for this server (MCP tools are prefixed with mcp__{server}__{tool})
                    server_tools = [t for t in all_tools if f"mcp__{name}__" in str(t)]
                    servers.append(
                        {
                            "name": name,
                            "connected": True,
                            "state": "connected",
                            "tools": server_tools,
                            "agent": agent_id,
                        },
                    )
                    total_tools += len(server_tools)

                # Only need to check one agent since MCP client is shared
                break

            return {"servers": servers, "total_tools": total_tools}

        def _show_orchestrator_modal(self):
            """Display orchestrator events in a modal."""
            events_text = "\n".join(self._orchestrator_events) if self._orchestrator_events else "No events yet."
            self._show_modal_async(OrchestratorEventsModal(events_text))

        def on_status_bar_events_clicked(self, event: StatusBarEventsClicked) -> None:
            """Handle click on status bar events counter - opens orchestrator events modal."""
            self._show_orchestrator_modal()

        def on_status_bar_tools_clicked(self, event: StatusBarToolsClicked) -> None:
            """Handle click on status bar running/background tools indicator."""
            self.action_open_background_tools()

        def on_status_bar_answer_now_clicked(self, event: StatusBarAnswerNowClicked) -> None:
            """Handle click on status bar Answer Now control."""
            self._trigger_answer_now()

        def on_answer_now_clicked(self, event: AnswerNowClicked) -> None:
            """Handle click on ribbon Answer Now control."""
            self._trigger_answer_now()

        def _trigger_answer_now(self) -> None:
            """Trigger the shared Answer Now callback and show user feedback."""
            callback = getattr(self, "_answer_now_callback", None)
            if not callable(callback):
                self.notify("Answer Now is unavailable for this run.", severity="warning", timeout=2)
                return

            result = callback() or {}
            requested_agents = list(result.get("requested_agents") or [])
            already_requested_agents = list(result.get("already_requested_agents") or [])
            skipped_agents = list(result.get("skipped_agents") or [])

            if requested_agents:
                self.add_orchestrator_event(
                    f"Answer Now requested for: {', '.join(requested_agents)}",
                )
                self.notify(
                    f"Asked {len(requested_agents)} agent(s) to wrap up and answer now.",
                    severity="warning",
                    timeout=3,
                )
                return

            if already_requested_agents:
                self.notify(
                    "Wrap-up is already in progress for the active agents.",
                    severity="information",
                    timeout=2,
                )
                return

            if skipped_agents:
                self.notify(
                    "No active agents are available to wrap up.",
                    severity="information",
                    timeout=2,
                )
                return

            self.notify("Nothing is currently running.", severity="information", timeout=2)

        def on_status_bar_cwd_clicked(self, event: StatusBarCwdClicked) -> None:
            """Handle CWD mode change from status bar click."""
            if self._is_cwd_context_toggle_blocked():
                self._set_cwd_context_mode(self._cwd_context_mode, notify=False)
                self.notify(
                    self._cwd_context_toggle_blocked_message(),
                    severity="warning",
                    timeout=2,
                )
                return

            self._set_cwd_context_mode(event.mode, notify=True, cwd=event.cwd)

        def on_status_bar_theme_clicked(self, event: StatusBarThemeClicked) -> None:
            """Handle theme toggle from status bar click."""
            self.action_toggle_theme()

        def on_status_bar_context_clicked(self, event: StatusBarContextClicked) -> None:
            """Handle click on status bar context indicator - opens context paths modal."""
            self._show_context_modal()

        @staticmethod
        def _normalize_cwd_context_mode(mode: str | None) -> str:
            """Normalize mode aliases to off/read/write."""
            normalized = str(mode or "off").strip().lower()
            if normalized in {"rw", "write"}:
                return "write"
            if normalized in {"ro", "read"}:
                return "read"
            return "off"

        def _cwd_context_toggle_blocked_message(self) -> str:
            """Return user-facing reason why CWD context toggle is blocked."""
            if self._mode_state.plan_mode == "execute":
                return "Cannot change CWD context in execute mode."
            return "Cannot change CWD context during execution."

        def _is_cwd_context_toggle_blocked(self) -> bool:
            """Return True when Ctrl+P/status-bar CWD toggles should be blocked."""
            return self._mode_state.plan_mode == "execute" or self._mode_state.is_locked()

        def _set_cwd_context_mode(
            self,
            mode: str,
            *,
            notify: bool,
            cwd: str | None = None,
        ) -> None:
            """Apply CWD context mode and sync status bar + hint UI."""
            self._cwd_context_mode = self._normalize_cwd_context_mode(mode)
            cwd_value = str(Path(cwd).resolve()) if cwd else str(Path.cwd())
            cwd_short = f"~/{Path(cwd_value).name}" if len(cwd_value) > 30 else cwd_value

            if self._status_bar:
                self._status_bar._cwd_context_mode = self._cwd_context_mode
                try:
                    cwd_widget = self._status_bar.query_one("#status_cwd", Static)
                    if self._cwd_context_mode == "read":
                        cwd_widget.update(f"[green]📁 {cwd_short} \\[read][/]")
                    elif self._cwd_context_mode == "write":
                        cwd_widget.update(f"[green]📁 {cwd_short} \\[read+write][/]")
                    else:
                        cwd_widget.update(f"[dim]📁[/] {cwd_short}")
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

            self._update_cwd_hint()
            if notify:
                self._notify_cwd_context_change(self._cwd_context_mode, cwd_value)

        def _toggle_cwd_auto_include(self) -> None:
            """Cycle CWD context mode: off → read → write → off (Ctrl+P)."""
            if self._is_cwd_context_toggle_blocked():
                self.notify(
                    self._cwd_context_toggle_blocked_message(),
                    severity="warning",
                    timeout=2,
                )
                return

            # Cycle through modes
            modes = ["off", "read", "write"]
            current_idx = modes.index(self._cwd_context_mode)
            self._set_cwd_context_mode(modes[(current_idx + 1) % len(modes)], notify=True)

        def _notify_cwd_context_change(self, mode: str, cwd: str) -> None:
            """Show a toast when CWD context visibility/mode changes."""
            mode_label = {
                "off": "hidden",
                "read": "read-only",
                "write": "read+write",
            }.get(mode, mode)

            if mode == "off":
                message = f"Ctrl+P: CWD context {mode_label} ({cwd})"
            else:
                message = f"Ctrl+P: CWD context {mode_label} ({cwd})"

            self.notify(message, severity="information", timeout=3)

        def _format_cwd_for_hint(self, max_len: int) -> str:
            """Return cwd text compacted for the right-side hint panel."""
            cwd = Path.cwd()
            cwd_text = str(cwd)

            home = str(Path.home())
            if cwd_text.startswith(home):
                remainder = cwd_text[len(home) :].lstrip("/\\")
                cwd_text = "~" if not remainder else f"~/{remainder}"

            if len(cwd_text) <= max_len:
                return cwd_text

            leaf = cwd.name or cwd_text
            compact = f".../{leaf}"
            if len(compact) <= max_len:
                return compact
            return leaf if len(leaf) <= max_len else leaf[-max_len:]

        def _build_welcome_context_hint_text(self) -> str:
            """Build compact Ctrl+P context hint for the right-side status panel."""
            mode_token = {
                "off": "off",
                "read": "[bold]ro[/]",
                "write": "[bold]rw[/]",
            }.get(self._cwd_context_mode, "off")

            width = self.size.width or (self.app.size.width if self.app else 120)
            cwd_name = Path.cwd().name or str(Path.cwd())
            cwd_medium = self._format_cwd_for_hint(24)
            cwd_long = self._format_cwd_for_hint(36)

            if width >= 150:
                return f"Ctrl+P: CWD {mode_token} ({cwd_long})"
            if width >= 120:
                return f"Ctrl+P: CWD {mode_token} ({cwd_medium})"
            if width >= 90:
                return f"Ctrl+P: CWD {mode_token} ({cwd_name})"
            return f"Ctrl+P: CWD {mode_token} ({cwd_name})"

        def _refresh_welcome_context_hint(self) -> None:
            """Refresh right-side vim/path panel when layout or mode changes."""
            if not hasattr(self, "question_input") or not self.question_input:
                return
            vim_normal: bool | None = None
            if self.question_input.vim_mode:
                vim_normal = bool(getattr(self.question_input, "_vim_normal", False))
            self._update_vim_indicator(vim_normal)

        def _update_cwd_hint(self) -> None:
            """Update compact path/help hint display."""
            self._refresh_welcome_context_hint()

        def _update_status_bar_restart_info(self) -> None:
            """Update StatusBar to show restart count."""
            if not self._status_bar or not self._current_restart:
                return
            try:
                # Show restart info in the progress area
                attempt = self._current_restart.get("attempt", 1)
                max_attempts = self._current_restart.get("max_attempts", 3)
                self._status_bar.show_restart_count(attempt, max_attempts)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        # === Status Bar Notification Methods ===

        def notify_vote(self, voter: str, voted_for: str, reason: str = "", submission_round: int = 1) -> None:
            """Called when a vote is cast. Updates status bar, shows toast, and adds tool card.

            Args:
                submission_round: Round the vote was cast in (1-indexed).
                    This ensures the vote card appears in the correct round
                    even if panel._current_round has advanced due to restart.
            """
            import time
            from datetime import datetime

            from massgen.events import EventType, MassGenEvent

            from .content_handlers import ToolDisplayData

            self._apply_consensus_event(
                MassGenEvent.create(
                    EventType.VOTE,
                    agent_id=voter,
                    round_number=submission_round,
                    target_id=voted_for,
                    reason=reason,
                ),
            )

            # Get model names for richer display
            voter_model = self.coordination_display.agent_models.get(voter, "")
            voted_for_model = self.coordination_display.agent_models.get(voted_for, "")

            # Get voted-for answer label from coordination tracker (for swimlane display)
            voted_for_label = None
            tracker = None
            if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)
            if tracker:
                voted_for_label = tracker.get_voted_for_label(voter, voted_for)

            # Track the vote for browser
            vote_count = len(self._votes) + 1
            self._votes.append(
                {
                    "voter": voter,
                    "voter_model": voter_model,
                    "voted_for": voted_for,
                    "voted_for_model": voted_for_model,
                    "voted_for_label": voted_for_label,  # Answer label like "1.2" for swimlane display
                    "reason": reason,
                    "timestamp": time.time(),
                },
            )

            if self._status_bar:
                self._status_bar.add_vote(voted_for, voter)
                standings = self._status_bar.get_standings_text()

                # Update progress summary
                agent_count = len(self.coordination_display.agent_ids)
                answer_count = len(self._answers)
                # Expected votes = agents * (agents - 1) in typical voting round
                expected_votes = agent_count * (agent_count - 1) if agent_count > 1 else 0
                self._status_bar.update_progress(agent_count, answer_count, vote_count, expected_votes)

                # Enhanced toast with model info - explicitly say "voted for"
                voter_display = f"{voter}" + (f" ({voter_model})" if voter_model else "")
                target_display = f"{voted_for}" + (f" ({voted_for_model})" if voted_for_model else "")

                if standings:
                    self.notify(
                        f"🗳️ [bold]{voter_display}[/] voted for [bold cyan]{target_display}[/]\n📊 {standings}",
                        timeout=4,
                    )
                else:
                    self.notify(
                        f"🗳️ [bold]{voter_display}[/] voted for [bold cyan]{target_display}[/]",
                        timeout=3,
                    )
            else:
                self.notify(f"🗳️ {voter} voted for {voted_for}", timeout=3)

            # Add vote tool card to the voter's timeline
            if voter in self.agent_widgets:
                panel = self.agent_widgets[voter]
                try:
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)

                    # Truncate reason for card display
                    reason_preview = reason[:80] + "..." if len(reason) > 80 else reason
                    reason_preview = reason_preview.replace("\n", " ")

                    now = datetime.now()
                    tool_id = f"vote_{voter}_{vote_count}"
                    tool_data = ToolDisplayData(
                        tool_id=tool_id,
                        tool_name="workspace/vote",
                        display_name="Workspace/Vote",
                        tool_type="workspace",
                        category="workspace",
                        icon="🗳️",
                        color="#a371f7",  # Purple for voting
                        status="success",
                        start_time=now,
                        end_time=now,
                        args_summary=f'voted_for="{voted_for}"',
                        args_full=f'voted_for="{voted_for}", reason="{reason}"',
                        result_summary=f"Voted for {voted_for}",
                        result_full=f"Voted for {voted_for}\nReason: {reason}" if reason else f"Voted for {voted_for}",
                        elapsed_seconds=0.0,
                    )

                    # Add tool card to timeline and mark as success immediately
                    # Use submission_round (not panel._current_round) to ensure
                    # chronological correctness: vote appears before round restart
                    timeline.add_tool(tool_data, round_number=submission_round)
                    tool_data.status = "success"
                    timeline.update_tool(tool_id, tool_data)

                    # Add "VOTED" separator banner with answer labels
                    # Get coordination_tracker to resolve answer labels
                    tracker = None
                    if hasattr(self.coordination_display, "orchestrator") and self.coordination_display.orchestrator:
                        tracker = getattr(self.coordination_display.orchestrator, "coordination_tracker", None)

                    if tracker:
                        # Get voted-for answer label from voter's context
                        target_label = tracker.get_voted_for_label(voter, voted_for)

                        if target_label:
                            # Convert from "agent1.1" format to "A1.1" format
                            target_label.replace("agent", "A")
                        else:
                            # Fallback to agent number if label not available
                            target_num = tracker._get_agent_number(voted_for)
                            f"A{target_num}" if target_num else voted_for

                        # NOTE: Vote separator banner disabled - clutters UI
                        # sep_label = f"🗳️ VOTED → {target_short}"
                        # timeline.add_separator(sep_label, round_number=current_round)
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")  # Silently ignore if panel not found

        def notify_new_answer(
            self,
            agent_id: str,
            content: str,
            answer_id: str | None,
            answer_number: int,
            answer_label: str | None,
            workspace_path: str | None,
            submission_round: int = 1,
        ) -> None:
            """Called when an agent submits an answer. Shows enhanced toast, tool card, and tracks for browser.

            Args:
                submission_round: Round the answer was submitted in (1-indexed).
                    This ensures the answer card appears in the correct round
                    even if panel._current_round has advanced due to restart.
            """
            import time

            from massgen.events import EventType, MassGenEvent

            self._apply_consensus_event(
                MassGenEvent.create(
                    EventType.ANSWER_SUBMITTED,
                    agent_id=agent_id,
                    round_number=submission_round,
                    answer_label=answer_label or f"{agent_id}.{answer_number}",
                    answer_number=answer_number,
                    content=content,
                    workspace_path=workspace_path,
                ),
            )

            # Get model name for richer display
            model_name = self.coordination_display.agent_models.get(agent_id, "")

            # Track the answer for browser
            self._answers.append(
                {
                    "agent_id": agent_id,
                    "model": model_name,
                    "content": content,
                    "answer_id": answer_id,
                    "answer_number": answer_number,
                    "answer_label": answer_label or f"{agent_id}.{answer_number}",
                    "workspace_path": workspace_path,
                    "timestamp": time.time(),
                    "is_final": False,
                    "is_winner": False,
                },
            )

            # Update progress summary in StatusBar
            if self._status_bar:
                agent_count = len(self.coordination_display.agent_ids)
                answer_count = len(self._answers)
                vote_count = len(self._votes)
                self._status_bar.update_progress(agent_count, answer_count, vote_count)
                # Increment per-agent answer count
                self._status_bar.increment_agent_answer(agent_id)

            # Enhanced toast with model info
            agent_display = f"{agent_id}" + (f" ({model_name})" if model_name else "")
            answer_count = len([a for a in self._answers if a["agent_id"] == agent_id])

            # Truncate content preview
            preview = content[:100] + "..." if len(content) > 100 else content
            preview = preview.replace("\n", " ")

            self.notify(
                f"📝 [bold green]New Answer[/] from [bold]{agent_display}[/]\n" f"   Answer #{answer_count}: {preview}",
                timeout=5,
            )

            # Also add a tool card for the new_answer action in the agent's panel
            # This provides visual feedback in the timeline view
            if agent_id in self.agent_widgets:
                panel = self.agent_widgets[agent_id]

                try:
                    timeline = panel.query_one(f"#{panel._timeline_section_id}", TimelineSection)

                    # Create tool display data with FULL content for the modal
                    from datetime import datetime

                    from .content_handlers import ToolDisplayData

                    tool_id = f"new_answer_{agent_id}_{answer_count}"

                    # Create truncated preview for card display
                    card_preview = content[:100].replace("\n", " ")
                    if len(content) > 100:
                        card_preview += "..."

                    now = datetime.now()
                    tool_data = ToolDisplayData(
                        tool_id=tool_id,
                        tool_name="workspace/new_answer",
                        display_name="Workspace/New Answer",
                        tool_type="workspace",
                        category="workspace",
                        icon="📝",
                        color="#4fc1ff",
                        status="success",
                        start_time=now,
                        end_time=now,
                        args_summary=f'content="{card_preview}"',
                        args_full=f'content="{content}"',  # Full content for modal
                        result_summary=f"Answer #{answer_count} submitted successfully",
                        result_full=content,  # Full answer content in result
                        elapsed_seconds=0.0,
                    )

                    # Add tool card directly to timeline
                    # Use submission_round (not panel._current_round) to ensure
                    # chronological correctness: answer appears before round restart
                    timeline.add_tool(tool_data, round_number=submission_round)
                    # Mark as success immediately
                    tool_data.status = "success"
                    timeline.update_tool(tool_id, tool_data)

                    # Phase 12: No inline separator - view dropdown handles round navigation
                    # The round will change when orchestrator calls _add_restart_content

                    # Reset per-round state (badges) now that answer is submitted
                    # The background shells will be killed by orchestrator when new round starts
                    panel._reset_round_state()
                except Exception as e:
                    import sys
                    import traceback

                    print(f"[ERROR] Failed to add workspace/new_answer card: {e}", file=sys.stderr)
                    traceback.print_exc()

        def update_agent_context(self, agent_id: str, context_sources: list[str]) -> None:
            """Update agent panel to show what context this agent has received.

            Called when an agent receives context from other agents' answers.

            Args:
                agent_id: Agent receiving context
                context_sources: List of answer labels this agent can see
            """
            # Store context for this agent
            self._context_per_agent[agent_id] = context_sources.copy()

            # Update agent panel header to show context
            if agent_id in self.agent_widgets:
                panel = self.agent_widgets[agent_id]
                panel.update_context_display(context_sources)

        def record_answer_context(
            self,
            agent_id: str,
            answer_label: str,
            context_sources: list[str],
            round_num: int,
        ) -> None:
            """Record context sources for an answer and update agent panel display.

            Args:
                agent_id: Agent who submitted the answer
                answer_label: Label like "agent1.1"
                context_sources: List of answer labels this agent saw (e.g., ["agent2.1"])
                round_num: Round number for this answer
            """
            # Store context for this agent (already done by update_agent_context, but ensure consistency)
            self._context_per_agent[agent_id] = context_sources.copy()

            # Update the answer record if it exists
            for ans in self._answers:
                if ans.get("answer_label") == answer_label:
                    ans["context_sources"] = context_sources.copy()
                    break

            # Update agent panel header to show context
            if agent_id in self.agent_widgets:
                panel = self.agent_widgets[agent_id]
                panel.update_context_display(context_sources)

                # If this is a new round for this panel, start the new round
                if round_num > panel._current_round:
                    panel.start_new_round(round_num, is_context_reset=False)

            # Update status ribbon with round number
            if self._status_ribbon:
                self._status_ribbon.set_round(agent_id, round_num)

        def _celebrate_winner(self, winner_id: str, answer_preview: str) -> None:
            """Display prominent winner celebration effects.

            Args:
                winner_id: The winning agent's ID
                answer_preview: Preview of the winning answer
            """
            # 1. Update StatusBar with winner announcement
            if self._status_bar:
                agent_count = len(self.coordination_display.agent_ids)
                answer_count = len(self._answers)
                vote_count = len(self._votes)
                self._status_bar.update_progress(
                    agent_count,
                    answer_count,
                    vote_count,
                    0,
                    winner=winner_id,
                )
                self._status_bar.celebrate_winner(winner_id)

            # 2. Add winner CSS class to the winning agent's tab
            try:
                tab_bar = self.query_one(AgentTabBar)
                for tab in tab_bar.query(".agent-tab"):
                    if getattr(tab, "agent_id", "") == winner_id:
                        tab.add_class("winner")
                        break
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Tab bar might not be available

            # 3. Add orchestrator event
            self.add_orchestrator_event(f"🏆 Winner: {winner_id} selected by consensus")

        def notify_phase(self, phase: str) -> None:
            """Called on phase change. Updates status bar phase indicator and input area mode."""
            tui_log(f"notify_phase called with phase='{phase}'")
            if self._status_bar:
                self._status_bar.update_phase(phase)

            # Toggle execution mode on input area based on phase
            try:
                input_area = self.query_one("#input_area")
                if phase in ("idle", "presentation", "presenting"):
                    # Not executing - show normal input
                    tui_log(f"  Phase '{phase}' -> removing execution-mode class")
                    input_area.remove_class("execution-mode")
                    self._dismiss_decomposition_generation_modal()
                    # Stop execution status update timer
                    if hasattr(self, "_execution_status_timer") and self._execution_status_timer:
                        self._execution_status_timer.stop()
                        self._execution_status_timer = None

                    # If queued runtime input wasn't injected, submit ALL pending
                    # queue entries as a new turn.
                    pending_input = self._compose_pending_human_input_for_new_turn()
                    if pending_input:
                        if self._skip_queued_fallback_once_after_restart:
                            tui_log("[HumanInput] Preserving queued runtime input across restart boundary")
                            self._skip_queued_fallback_once_after_restart = False
                            self._refresh_human_input_pending_state()
                            self._sync_queued_input_banner_from_hook()
                        else:
                            self._clear_queued_input()
                            # Clear hook queue after we've captured pending payload.
                            if self._human_input_hook and hasattr(self._human_input_hook, "clear_pending_input"):
                                self._human_input_hook.clear_pending_input()
                            tui_log(f"[HumanInput] Turn ended with queued input, submitting as new turn: {pending_input[:50]}...")
                            # Submit as new question (use set_timer to avoid recursion issues)
                            self.set_timer(0.1, lambda: self._submit_question(pending_input))
                else:
                    # Executing (initial_answer, enforcement, coordinating) - show status
                    tui_log(f"  Phase '{phase}' -> adding execution-mode class")
                    input_area.add_class("execution-mode")
                    # Start timer to periodically update execution status (for spinner animation)
                    if not hasattr(self, "_execution_status_timer") or not self._execution_status_timer:
                        self._execution_status_timer = self.set_interval(0.1, self._update_execution_status)
                tui_log(f"  input_area classes after: {input_area.classes}")
            except Exception as e:
                tui_log(f"  Exception toggling execution-mode: {e}")

        def notify_completion(self, agent_id: str) -> None:
            """Called when an agent completes their work."""
            self.notify(f"✅ {agent_id} completed", severity="information", timeout=3)

        def notify_error(self, agent_id: str, error: str) -> None:
            """Called on agent error."""
            self.notify(f"❌ {agent_id}: {error}", severity="error", timeout=5)

        def add_status_bar_event(self) -> None:
            """Increment the event counter in the status bar."""
            if self._status_bar:
                self._status_bar.add_event()

        def update_status_bar_votes(self, vote_counts: dict[str, int]) -> None:
            """Update all vote counts in the status bar at once."""
            if self._status_bar:
                self._status_bar.update_votes(vote_counts)

            # Also update execution status line with vote info
            self._update_execution_status(vote_counts=vote_counts)

        def _update_execution_status(self, vote_counts: dict[str, int] | None = None) -> None:
            """Update the execution status line with per-agent progress and activity.

            Format: A: 2 ans, 3 votes 💭  |  B: 1 ans, 2 votes 🔧  |  ⏱ 16s
            """
            try:
                # Keep runtime-injection queue UI in sync even when hook callbacks
                # are suppressed (e.g., Codex _flush path).
                queue_counts = getattr(self, "_queued_human_input_pending_by_agent", {}) or {}
                queue_has_pending = any((count or 0) > 0 for count in queue_counts.values())
                queue_region = getattr(self, "_queued_input_region", None)
                queue_visible = bool(queue_region and "visible" in getattr(queue_region, "classes", set()))
                if getattr(self, "_human_input_hook", None) and (queue_has_pending or queue_visible):
                    self._refresh_human_input_pending_state()
                    self._sync_queued_input_banner_from_hook()

                if hasattr(self, "_execution_status"):
                    # Build status text
                    parts = []

                    # Add per-agent stats from status bar
                    if hasattr(self, "_status_bar") and self._status_bar:
                        ACTIVITY_ICONS = {
                            "idle": "○",
                            "thinking": "💭",
                            "tool": "🔧",
                            "streaming": "✍️",
                            "voting": "🗳️",
                            "waiting": "⏳",
                            "error": "⚠️",
                        }
                        SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                        spinner = SPINNER_FRAMES[self._status_bar._spinner_frame]

                        agent_parts = []
                        for agent_id in self._status_bar._agent_order:
                            letter = self._status_bar._agent_letters.get(agent_id, "?")
                            activity = self._status_bar._agent_activities.get(agent_id, "idle")
                            icon = ACTIVITY_ICONS.get(activity, "○")
                            answers = self._status_bar._agent_answer_counts.get(agent_id, 0)
                            votes = self._status_bar._agent_votes_received.get(agent_id, 0)

                            # Build agent status string with spaces
                            stats_parts = []
                            if answers > 0:
                                stats_parts.append(f"{answers} ans")
                            if votes > 0:
                                stats_parts.append(f"{votes} votes")
                            stats = ", ".join(stats_parts) if stats_parts else ""

                            # Format: "A: 2 ans, 3 votes 💭" or "A: 💭" if no stats yet
                            if activity == "idle":
                                if stats:
                                    agent_parts.append(f"{letter}: {stats}  {icon}")
                                else:
                                    agent_parts.append(f"{letter}: {icon}")
                            else:
                                if stats:
                                    agent_parts.append(f"{letter}: {stats}  {spinner} {icon}")
                                else:
                                    agent_parts.append(f"{letter}: {spinner} {icon}")

                        if agent_parts:
                            parts.append("  |  ".join(agent_parts))
                        else:
                            parts.append("Working...")
                    else:
                        parts.append("Working...")

                    # Add elapsed time
                    if hasattr(self, "_status_bar") and self._status_bar and hasattr(self._status_bar, "_start_time"):
                        start_time = self._status_bar._start_time
                        if start_time:
                            elapsed = time.time() - start_time
                            mins = int(elapsed // 60)
                            secs = int(elapsed % 60)
                            if mins > 0:
                                parts.append(f"⏱ {mins}m {secs}s")
                            else:
                                parts.append(f"⏱ {secs}s")

                    self._execution_status.update("  |  ".join(parts))
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _show_cancelled_status(self) -> None:
            """Stop execution status updates and show cancelled state with PERSISTENT visual feedback.

            The cancelled state persists until the user submits a new question, making it
            clear that the system is waiting for input rather than auto-dismissing.
            """
            try:
                # Stop the execution status timer
                if hasattr(self, "_execution_status_timer") and self._execution_status_timer:
                    self._execution_status_timer.stop()
                    self._execution_status_timer = None

                # Set all agents to idle in status bar
                if hasattr(self, "_status_bar") and self._status_bar:
                    for agent_id in self._status_bar._agent_order:
                        self._status_bar.set_agent_activity(agent_id, "idle")

                # Update ExecutionStatusLine to show cancelled state
                if hasattr(self, "_execution_status_line") and self._execution_status_line:
                    for agent_id in self._execution_status_line._agent_ids:
                        self._execution_status_line.set_agent_state(agent_id, "cancelled")

                # Stop all pulsing animations
                self._stop_all_pulses()

                # Stop round timers in ribbon
                if hasattr(self, "_status_ribbon") and self._status_ribbon:
                    self._status_ribbon.stop_all_round_timers()

                # Mark cancelled state in mode tracker (persists until new input)
                if hasattr(self.coordination_display, "_mode_state"):
                    self.coordination_display._mode_state.was_cancelled = True

                # Update execution status to show cancelled
                if hasattr(self, "_execution_status"):
                    # Get elapsed time for final display
                    elapsed_text = ""
                    if hasattr(self, "_status_bar") and self._status_bar and hasattr(self._status_bar, "_start_time"):
                        start_time = self._status_bar._start_time
                        if start_time:
                            elapsed = time.time() - start_time
                            mins = int(elapsed // 60)
                            secs = int(elapsed % 60)
                            if mins > 0:
                                elapsed_text = f"  |  ⏱ {mins}m {secs}s"
                            else:
                                elapsed_text = f"  |  ⏱ {secs}s"

                    self._execution_status.update(f"❌ Cancelled{elapsed_text}")

                # Add PERSISTENT visual state change - red tint on main container
                # This persists until user submits a new question
                try:
                    main = self.query_one("#main_container")
                    main.add_class("cancelled-state")

                    # Update placeholder to indicate waiting for input
                    if hasattr(self, "question_input"):
                        self.question_input.placeholder = "Type to continue • Previous turn was cancelled"

                    # Show notification (brief)
                    self.notify("Execution cancelled - type to continue", severity="warning", timeout=3)

                    # NO auto-dismiss timer - state persists until user provides new input
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _clear_cancelled_state(self) -> None:
            """Clear the persistent cancelled state when user starts a new turn."""
            try:
                # Clear mode state flag
                if hasattr(self.coordination_display, "_mode_state"):
                    self.coordination_display._mode_state.reset_cancelled_state()

                # Remove visual cancelled state
                try:
                    main = self.query_one("#main_container")
                    main.remove_class("cancelled-state")
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

                # Restore default placeholder
                if hasattr(self, "question_input"):
                    self.question_input.placeholder = "Enter to submit • Shift+Enter for newline • @ for files • Ctrl+G help"
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        # =====================================================================
        # Agent Pulsing Animation
        # =====================================================================

        _PULSE_FRAMES = ["pulse-bright", "pulse-bright", "pulse-normal", "pulse-normal"]

        def _start_agent_pulse(self, agent_id: str) -> None:
            """Start pulsing animation for an active agent.

            NOTE: Pulsing animation disabled - was too distracting.
            Left as no-op to avoid breaking callers.
            """
            return  # Pulsing disabled

            self._pulsing_agents.add(agent_id)
            logger.info(f"[PULSE] Added {agent_id} to pulsing_agents: {self._pulsing_agents}")

            # Start the timer if not already running
            if not self._pulse_timer:
                self._pulse_frame = 0
                self._pulse_timer = self.set_interval(0.25, self._animate_agent_pulse)
                logger.info("[PULSE] Started pulse timer")

        def _stop_agent_pulse(self, agent_id: str) -> None:
            """Stop pulsing animation for an agent."""
            if agent_id not in self._pulsing_agents:
                return

            self._pulsing_agents.discard(agent_id)

            # Remove pulse classes from the panel
            try:
                panel = self.agent_widgets.get(agent_id)
                if panel:
                    panel.remove_class("pulse-bright", "pulse-normal")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Stop the timer if no agents are pulsing
            if not self._pulsing_agents and self._pulse_timer:
                self._pulse_timer.stop()
                self._pulse_timer = None

        def _stop_all_pulses(self) -> None:
            """Stop all agent pulsing animations."""
            for agent_id in list(self._pulsing_agents):
                self._stop_agent_pulse(agent_id)

        def _animate_agent_pulse(self) -> None:
            """Animate the pulsing effect on active agent panels."""
            from massgen.logger_config import logger

            if not self._pulsing_agents:
                return

            # Advance frame
            self._pulse_frame = (self._pulse_frame + 1) % len(self._PULSE_FRAMES)
            frame_class = self._PULSE_FRAMES[self._pulse_frame]
            prev_frame_class = self._PULSE_FRAMES[(self._pulse_frame - 1) % len(self._PULSE_FRAMES)]

            for agent_id in self._pulsing_agents:
                try:
                    panel = self.agent_widgets.get(agent_id)
                    if panel:
                        # Remove previous frame class, add current
                        if prev_frame_class != frame_class:
                            panel.remove_class(prev_frame_class)
                        panel.add_class(frame_class)
                        logger.debug(f"[PULSE] Applied {frame_class} to {agent_id}, classes={panel.classes}")
                    else:
                        logger.warning(f"[PULSE] Panel not found for {agent_id}, available: {list(self.agent_widgets.keys())}")
                except Exception as e:
                    logger.error(f"[PULSE] Error animating {agent_id}: {e}")

        def _handle_agent_shortcuts(self, event: events.Key) -> bool:
            """Handle agent shortcuts. Returns True if event was handled.

            Single-key shortcuts (when not typing in input):
            - 1-9: Switch to agent by number
            - q: Cancel/stop current execution
            - s: System status
            - o: Orchestrator events
            - v: Vote results
            - w: Workspace browser
            - f: Final presentation / files
            - c: Cost breakdown
            - m: MCP status / metrics
            - k: Skills manager
            - a: Answer browser
            - t: Timeline
            - h or ?: Help/shortcuts

            Note: Info shortcuts always work - they're read-only views.
            No need to check keyboard lock since none of these change modes.
            """
            key = event.character
            if not key:
                return False

            # Number keys for agent switching
            if key.isdigit() and key != "0":
                idx = int(key) - 1
                if 0 <= idx < len(self.coordination_display.agent_ids):
                    agent_id = self.coordination_display.agent_ids[idx]
                    self._switch_to_agent(agent_id)
                    event.stop()
                    return True

            key_lower = key.lower()

            # q - Exit scroll mode and go to bottom
            if key_lower == "q":
                self._exit_scroll_mode()
                event.stop()
                return True

            # s - System status
            if key_lower == "s":
                self.action_open_system_status()
                event.stop()
                return True

            # o - Full agent output (repurposed from orchestrator events)
            if key_lower == "o":
                self.action_open_agent_output()
                event.stop()
                return True

            # v - Vote results
            if key_lower == "v":
                self.action_open_vote_results()
                event.stop()
                return True

            # w - Workspace browser
            if key_lower == "w":
                self.action_open_workspace_browser()
                event.stop()
                return True

            # f - Removed (merged into 'w' workspace browser)

            # c - Cost breakdown
            if key_lower == "c":
                self.action_open_cost_breakdown()
                event.stop()
                return True

            # m - MCP status or metrics
            if key_lower == "m":
                self.action_open_mcp_status()
                event.stop()
                return True

            # k - Skills manager
            if key_lower == "k":
                self._show_skills_modal()
                event.stop()
                return True

            # a - Answer browser
            if key_lower == "a":
                self.action_open_answer_browser()
                event.stop()
                return True

            # t - Timeline/Browser (unified tabbed view)
            if key_lower == "t":
                self.action_open_unified_browser()
                event.stop()
                return True

            # ? - Help/shortcuts
            if key == "?":
                self.action_show_shortcuts()
                event.stop()
                return True

            # D - Dump widget sizes for debugging
            if key == "D":
                self._dump_widget_sizes()
                self.notify(f"Widget sizes dumped to {os.path.join(tempfile.gettempdir(), 'widget_sizes.json')}", severity="information")
                event.stop()
                return True

            # h - History
            if key_lower == "h":
                self._show_history_modal()
                event.stop()
                return True

            # i or / - Focus input (vim-like insert mode or search)
            if key_lower == "i" or key == "/":
                if hasattr(self, "question_input") and self.question_input:
                    self.question_input.focus()
                    event.stop()
                    return True

            # Escape when not in input - show hint or exit scroll mode
            if event.key == "escape":
                # If in scroll mode, exit it
                if self._in_scroll_mode():
                    self._exit_scroll_mode()
                    event.stop()
                    return True
                self.notify("Already in command mode. Press i or / to type.", severity="information", timeout=2)
                event.stop()
                return True

            return False

        def _in_scroll_mode(self) -> bool:
            """Check if any timeline is in scroll mode."""
            try:
                for timeline in self.query(TimelineSection):
                    if timeline.in_scroll_mode:
                        return True
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
            return False

        def _exit_scroll_mode(self) -> None:
            """Exit scroll mode on all timelines and scroll to bottom."""
            exited = False
            try:
                for timeline in self.query(TimelineSection):
                    if timeline.in_scroll_mode:
                        timeline.exit_scroll_mode()
                        exited = True
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
            if exited:
                self.notify("Resumed auto-scroll", severity="information", timeout=1)

        def _show_coordination_table_modal(self):
            """Display coordination table in a modal."""
            table_text = self.coordination_display._format_coordination_table_from_orchestrator()
            self._show_modal_async(CoordinationTableModal(table_text))

        def _show_text_modal(self, path: Path, title: str):
            """Display file content in a modal."""
            content = ""
            try:
                if path.exists():
                    content = path.read_text(encoding="utf-8")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")
            if not content:
                content = "Content unavailable."
            self._show_modal_async(TextContentModal(title, content))

        def _show_system_status_modal(self):
            """Display system status log in a modal."""
            content = ""
            status_path = self.coordination_display.system_status_file
            if status_path and Path(status_path).exists():
                try:
                    content = Path(status_path).read_text(encoding="utf-8")
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")
            if not content:
                content = "System status log is empty or unavailable."
            self._show_modal_async(SystemStatusModal(content))

        def _show_cost_breakdown_modal(self):
            """Display cost breakdown in a modal."""
            self._show_modal_async(CostBreakdownModal(self.coordination_display))

        def _show_workspace_files_modal(self):
            """Display workspace files in a modal (uses WorkspaceBrowserModal)."""
            self._show_workspace_browser()

        def _show_context_modal(self):
            """Display context paths modal."""
            self._show_modal_async(ContextModal(self.coordination_display, self))

        def _show_metrics_modal(self):
            """Display tool metrics in a modal."""
            self._show_modal_async(MetricsModal(self.coordination_display))

        def _show_history_modal(self):
            """Display conversation history in a modal."""
            self._show_modal_async(
                ConversationHistoryModal(
                    self._conversation_history,
                    self._current_question,
                    self.coordination_display.agent_ids,
                ),
            )

        @staticmethod
        def _normalize_skill_name_list(skill_names: list[str]) -> list[str]:
            """Normalize and deduplicate skill names while preserving order."""
            seen: set[str] = set()
            normalized: list[str] = []
            for name in skill_names:
                cleaned = (name or "").strip()
                if not cleaned:
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                normalized.append(cleaned)
            return normalized

        def _collect_skill_inventory(
            self,
            include_previous_session_skills: bool = True,
        ) -> dict[str, list[dict[str, Any]]]:
            """Collect available skills grouped by source location."""
            from massgen.filesystem_manager.skills_manager import scan_skills
            from massgen.logs_analyzer import get_logs_dir

            skills_dir = Path(".agent/skills")
            logs_dir = get_logs_dir()
            logs_source = logs_dir if include_previous_session_skills and logs_dir.exists() else None
            all_skills = scan_skills(skills_dir, logs_dir=logs_source)

            grouped: dict[str, list[dict[str, Any]]] = {
                "builtin": [],
                "project": [],
                "user": [],
                "previous_session": [],
            }
            for skill in all_skills:
                location = str(skill.get("location", "project"))
                if location not in grouped:
                    grouped[location] = []
                grouped[location].append(skill)

            for location in grouped:
                grouped[location] = sorted(
                    grouped[location],
                    key=lambda s: str(s.get("name", "")).lower(),
                )
            return grouped

        @staticmethod
        def _flatten_skill_inventory(
            skills_by_location: dict[str, list[dict[str, Any]]],
            include_previous_session_skills: bool,
        ) -> list[dict[str, Any]]:
            """Flatten grouped skills into a single list with optional evolving exclusion."""
            flattened: list[dict[str, Any]] = []
            for location, skills in skills_by_location.items():
                if location == "previous_session" and not include_previous_session_skills:
                    continue
                flattened.extend(skills)
            return flattened

        def _refresh_skills_button_state(self) -> None:
            """Compatibility hook retained after removing skills from the mode bar."""
            if self._mode_bar:
                self._mode_bar.set_skills_available(False)

        def _show_skills_modal(self) -> None:
            """Show session skill manager modal."""
            include_previous = bool(
                self._mode_state.analysis_config.include_previous_session_skills,
            )
            skills_by_location = self._collect_skill_inventory(
                include_previous_session_skills=True,
            )
            current_enabled = self._mode_state.analysis_config.get_enabled_skill_names()

            # Load registry content if SKILL_REGISTRY.md exists
            registry_content = None
            try:
                registry_path = Path(".agent/skills/SKILL_REGISTRY.md")
                if registry_path.is_file():
                    registry_content = registry_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass

            modal = SkillsModal(
                skills_by_location=skills_by_location,
                enabled_skill_names=current_enabled,
                include_previous_session_skills=include_previous,
                registry_content=registry_content if registry_content else None,
            )

            def _on_skills_dismiss(result: dict[str, Any] | None) -> None:
                if result is None:
                    return

                selected = self._normalize_skill_name_list(
                    result.get("enabled_skill_names", []),
                )
                include_previous_session_skills = bool(
                    result.get("include_previous_session_skills", include_previous),
                )
                self._mode_state.analysis_config.include_previous_session_skills = include_previous_session_skills
                discovered = self._normalize_skill_name_list(
                    [
                        str(s.get("name", ""))
                        for s in self._flatten_skill_inventory(
                            skills_by_location,
                            include_previous_session_skills=include_previous_session_skills,
                        )
                    ],
                )

                selected_set = {name.lower() for name in selected}
                discovered_set = {name.lower() for name in discovered}

                if discovered and selected_set == discovered_set:
                    # None = unfiltered; automatically includes newly discovered skills.
                    self._mode_state.analysis_config.enabled_skill_names = None
                    enabled_count = len(discovered)
                    self.notify(f"Skills enabled: all {enabled_count} discovered", severity="information", timeout=3)
                else:
                    self._mode_state.analysis_config.enabled_skill_names = selected
                    self.notify(f"Skills enabled: {len(selected)}", severity="information", timeout=3)
                self._refresh_skills_button_state()

            self.push_screen(modal, _on_skills_dismiss)

        @staticmethod
        def _snapshot_skill_dirs() -> set:
            """Return set of directory names in .agent/skills/ that contain a SKILL.md."""
            skills_root = Path(".agent") / "skills"
            if not skills_root.is_dir():
                return set()
            return {d.name for d in skills_root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()}

        def _detect_new_skills_from_analysis(self) -> None:
            """Harvest skills from agent workspaces and copy to project .agent/skills/.

            After an analysis run with the "user" profile, agents may have created
            SKILL.md files inside their workspace (e.g. final/agent_*/workspace/.agent/skills/*/).
            This method copies those to the project-root skills directory so they
            are discoverable by future runs.
            """
            if self._mode_state.plan_mode != "analysis":
                return
            if self._mode_state.analysis_config.profile != "user":
                return

            try:
                self._harvest_skills_from_workspace()
            finally:
                # Clear snapshot after detection.
                self._mode_state.analysis_config._pre_analysis_skill_dirs = None

        def _harvest_skills_from_workspace(self) -> None:
            """Apply skill lifecycle updates from analysis outputs into .agent/skills/."""

            from massgen.filesystem_manager.skills_manager import (
                apply_analysis_skill_lifecycle,
                normalize_skill_lifecycle_mode,
            )
            from massgen.logger_config import get_log_session_dir

            project_skills_root = Path(".agent") / "skills"
            pre_snapshot = self._mode_state.analysis_config._pre_analysis_skill_dirs or set()
            lifecycle_mode = normalize_skill_lifecycle_mode(
                self._mode_state.analysis_config.skill_lifecycle_mode,
            )

            # Find SKILL.md files in agent workspaces
            log_dir = get_log_session_dir()
            final_dir = log_dir / "final"
            if not final_dir.exists():
                tui_log("[SkillHarvest] No final/ directory found")
                return

            actions: list[dict[str, Any]] = []
            for skill_md in sorted(final_dir.glob("agent_*/workspace/.agent/skills/*/SKILL.md")):
                skill_dir = skill_md.parent

                try:
                    result = apply_analysis_skill_lifecycle(
                        skill_dir,
                        project_skills_root,
                        lifecycle_mode=lifecycle_mode,
                        preexisting_skill_dirs=pre_snapshot,
                    )
                    actions.append(result)
                    tui_log(f"[SkillHarvest] lifecycle={lifecycle_mode} result={result}")
                except Exception as e:
                    tui_log(f"[SkillHarvest] Failed lifecycle apply for {skill_dir.name}: {e}")

            created_names = []
            updated_names = []
            for item in actions:
                name = str(item.get("name", "") or "").strip()
                if not name:
                    continue
                if item.get("action") == "created":
                    created_names.append(name)
                elif item.get("action") == "updated":
                    updated_names.append(name)

            created_names = self._normalize_skill_name_list(created_names)
            updated_names = self._normalize_skill_name_list(updated_names)

            if not created_names and not updated_names:
                return

            summary_parts = []
            if created_names:
                summary_parts.append(f"created {len(created_names)}")
            if updated_names:
                summary_parts.append(f"updated {len(updated_names)}")

            summary_text = ", ".join(summary_parts)
            self.notify(f"Skills lifecycle applied: {summary_text}", severity="information", timeout=5)

            # Suggest git tracking if skills aren't version-controlled
            try:
                from massgen.filesystem_manager.skills_manager import (
                    check_skills_git_tracking,
                )

                tracking = check_skills_git_tracking(Path.cwd())
                if tracking == "untracked":
                    self.notify(
                        "Tip: Track skills in git — add !.agent/skills/ and !.agent/skills/** to .gitignore",
                        severity="information",
                        timeout=8,
                    )
            except Exception:
                pass  # Non-critical — don't break harvest on gitignore check failure

            # Auto-add to enabled filter if one is active.
            enabled = self._mode_state.analysis_config.get_enabled_skill_names()
            if enabled is not None:
                self._mode_state.analysis_config.enabled_skill_names = self._normalize_skill_name_list(enabled + created_names + updated_names)
            self._refresh_skills_button_state()

        def _show_file_inspection_modal(self):
            """Display file inspection modal with tree view."""
            orchestrator = getattr(self.coordination_display, "orchestrator", None)
            workspace_path = None
            if orchestrator:
                workspace_dir = getattr(orchestrator, "workspace_dir", None)
                if workspace_dir:
                    workspace_path = Path(workspace_dir)
            if not workspace_path or not workspace_path.exists():
                self.notify("No workspace available", severity="warning")
                return
            self._show_modal_async(FileInspectionModal(workspace_path, self))

        def _show_agent_output_modal(self, agent_id: str):
            """Display full agent output in a modal."""
            # Get the agent outputs from the display
            agent_outputs = self.coordination_display.get_agent_content(agent_id)
            # Get model name from orchestrator if available
            model_name = None
            orchestrator = getattr(self.coordination_display, "orchestrator", None)
            if orchestrator:
                agents = getattr(orchestrator, "agents", {})
                if agent_id in agents:
                    agent = agents[agent_id]
                    # Model is stored on backend.model, not directly on agent
                    backend = getattr(agent, "backend", None)
                    if backend:
                        model_name = getattr(backend, "model", None)
                    # Fallback to agent-level attributes
                    if not model_name:
                        model_name = getattr(agent, "model", None) or getattr(agent, "model_name", None)
            # Get all agents for toggle functionality
            all_agents = {}
            if orchestrator:
                for aid, agent in getattr(orchestrator, "agents", {}).items():
                    agent_model = None
                    backend = getattr(agent, "backend", None)
                    if backend:
                        agent_model = getattr(backend, "model", None)
                    all_agents[aid] = {
                        "outputs": self.coordination_display.get_agent_content(aid),
                        "model": agent_model,
                    }
            self._show_modal_async(AgentOutputModal(agent_id, agent_outputs, model_name, all_agents, self._current_question))

        def on_resize(self, event: events.Resize) -> None:
            """Refresh widgets when the terminal window is resized with debounce."""
            if self._resize_debounce_handle:
                try:
                    self._resize_debounce_handle.stop()
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

            debounce_time = 0.15 if self.coordination_display._terminal_type in ("vscode", "windows_terminal") else 0.05
            try:
                self._resize_debounce_handle = self.set_timer(
                    debounce_time,
                    lambda: (self.refresh(layout=True), self.call_later(self._refresh_welcome_context_hint)),
                )
            except Exception:
                self.call_later(lambda: (self.refresh(layout=True), self._refresh_welcome_context_hint()))

    # Widget implementations
    class WelcomeScreen(Container):
        """Welcome screen with ASCII logo shown on startup."""

        MASSGEN_LOGO = """\
   ███╗   ███╗  █████╗  ███████╗ ███████╗  ██████╗  ███████╗ ███╗   ██╗
   ████╗ ████║ ██╔══██╗ ██╔════╝ ██╔════╝ ██╔════╝  ██╔════╝ ████╗  ██║
   ██╔████╔██║ ███████║ ███████╗ ███████╗ ██║  ███╗ █████╗   ██╔██╗ ██║
   ██║╚██╔╝██║ ██╔══██║ ╚════██║ ╚════██║ ██║   ██║ ██╔══╝   ██║╚██╗██║
   ██║ ╚═╝ ██║ ██║  ██║ ███████║ ███████║ ╚██████╔╝ ███████╗ ██║ ╚████║
   ╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚══════╝ ╚══════╝  ╚═════╝  ╚══════╝ ╚═╝  ╚═══╝"""

        MASSGEN_LOGO_COMPACT = "MASSGEN"

        def __init__(self, agents_info: list = None):
            super().__init__(id="welcome_screen")
            self.agents_info = agents_info or []
            self._logo_label: Label | None = None
            self._divider_label: Static | None = None
            self._agents_label: Label | None = None
            self._hint_label: Label | None = None

        def compose(self) -> ComposeResult:
            self._logo_label = Label(self.MASSGEN_LOGO, id="welcome_logo")
            yield self._logo_label
            yield Label("Multi-Agent Collaboration System", id="welcome_tagline")
            self._divider_label = Static("", id="welcome_divider")
            yield self._divider_label
            with Container(id="welcome_agents_wrap"):
                self._agents_label = Label("", id="welcome_agents")
                yield self._agents_label
            self._hint_label = Label("", id="welcome_hint")
            yield self._hint_label

        def on_mount(self) -> None:
            """Apply responsive formatting once widget dimensions are known."""
            self.call_after_refresh(self._refresh_for_size)

        def on_resize(self, event: events.Resize) -> None:
            """Reflow welcome content when terminal size changes."""
            del event
            self._refresh_for_size()

        def _refresh_for_size(self) -> None:
            """Keep welcome screen readable at narrow widths/heights."""
            width = self.size.width or (self.app.size.width if self.app else 120)
            height = self.size.height or (self.app.size.height if self.app else 40)

            if self._logo_label:
                logo = self.MASSGEN_LOGO_COMPACT if width < 110 or height < 26 else self.MASSGEN_LOGO
                self._logo_label.update(logo)

            if self._divider_label:
                self._divider_label.update(self._build_divider(width))

            if self._agents_label:
                self._agents_label.update(self._build_agent_summary(width))

            if self._hint_label:
                if width < 84:
                    self._hint_label.update("Type your question and press Enter.")
                else:
                    self._hint_label.update("Type your question below, then press Enter.")

        def _build_divider(self, width: int) -> str:
            """Return a balanced separator line for the welcome card."""
            length = max(26, min(72, width - 18))
            return "─" * length

        def _build_agent_summary(self, width: int) -> str:
            """Build a readable summary of ready agents and models."""
            if not self.agents_info:
                return "Ready: 0 agents"

            entries: list[tuple[str, str]] = []
            for item in self.agents_info:
                if isinstance(item, dict):
                    agent_id = str(item.get("id", "") or "").strip()
                    model = str(item.get("model", "") or "").strip()
                else:
                    agent_text = str(item).strip()
                    if " (" in agent_text and agent_text.endswith(")"):
                        agent_id, model = agent_text.rsplit(" (", 1)
                        model = model[:-1]
                    else:
                        agent_id, model = agent_text, ""
                    agent_id = agent_id.strip()
                    model = model.strip()

                if agent_id:
                    entries.append((agent_id, model))

            summary_lines = [f"Ready: {len(entries)} agents"]
            agent_col_width = max((len(agent_id) for agent_id, _ in entries), default=0)

            for agent_id, model in entries:
                if not model:
                    summary_lines.append(agent_id)
                    continue

                model_budget = max(12, width - agent_col_width - 8)
                summary_lines.append(
                    f"{agent_id.ljust(agent_col_width)} - {self._truncate_middle(model, model_budget)}",
                )
            return "\n".join(summary_lines)

        @staticmethod
        def _truncate_middle(value: str, max_length: int) -> str:
            """Truncate long values while preserving start/end context."""
            if len(value) <= max_length:
                return value
            if max_length <= 8:
                return value[:max_length]
            head = (max_length - 1) // 2
            tail = max_length - head - 1
            return f"{value[:head]}…{value[-tail:]}"

    class HeaderWidget(Static):
        """Compact header widget showing minimal branding and session info."""

        def __init__(
            self,
            question: str,
            session_id: str = None,
            turn: int = 1,
            agents_info: list = None,
            mode: str = "Multi-Agent",
        ):
            super().__init__(id="header_widget")
            self.question = question
            self.session_id = session_id
            self.turn = turn
            self.agents_info = agents_info or []
            self.mode = mode
            # Set initial content
            self.update(self._build_status_line())

        def _build_status_line(self) -> str:
            """Build compact status line with optional question preview."""
            num_agents = len(self.agents_info)
            base = f"MassGen • {num_agents} agents • Turn {self.turn}"

            # Add truncated question if available
            if self.question and self.question != "Welcome! Type your question below...":
                # Truncate question to fit in header (max ~100 chars for better visibility)
                q = self.question.replace("\n", " ").strip()
                q = q[:100] + "..." if len(q) > 100 else q
                return f"{base} • {q}"
            return base

        def update_question(self, question: str) -> None:
            """Update the displayed question and refresh header."""
            self.question = question
            self.update(self._build_status_line())

        def update_turn(self, turn: int) -> None:
            """Update the displayed turn number."""
            self.turn = turn
            self.update(self._build_status_line())

        def show_restart_banner(
            self,
            reason: str,
            instructions: str,
            attempt: int,
            max_attempts: int,
        ):
            """Show restart banner."""
            banner_text = f"RESTART ({attempt}/{max_attempts}): {reason}"
            self.update(banner_text)

        def show_restart_context(self, reason: str, instructions: str):
            """Show restart context - handled via status line."""
            pass  # Restart info shown via show_restart_banner  # Restart info shown via show_restart_banner

    class AgentPanel(Container, BaseTUILayoutMixin):
        """Panel for individual agent output.

        Note: This is a Container, not ScrollableContainer. Scrolling happens
        in the inner TimelineSection widget which inherits from ScrollableContainer.

        Inherits BaseTUILayoutMixin for shared content pipeline functionality.
        """

        def __init__(self, agent_id: str, display: TextualTerminalDisplay, key_index: int = 0):
            self.agent_id = agent_id
            self.coordination_display = display
            self.key_index = key_index
            self._dom_safe_id = self._make_dom_safe_id(agent_id)
            # Assign color class based on key_index (cycles through 8 colors)
            color_class = f"agent-color-{((key_index - 1) % 8) + 1}" if key_index > 0 else "agent-color-1"
            super().__init__(id=f"agent_{self._dom_safe_id}", classes=color_class)
            self.status = "waiting"
            self._start_time: datetime | None = None
            self._has_content = False  # Track if we've received any content

            # Legacy RichLog for fallback
            self.content_log = RichLog(
                id=f"log_{self._dom_safe_id}",
                highlight=self.coordination_display.enable_syntax_highlighting,
                markup=True,
                wrap=True,
            )
            self._line_buffer = ""
            self.current_line_label = Label("", classes="streaming_label")
            self._header_dom_id = f"header_{self._dom_safe_id}"
            self._loading_id = f"loading_{self._dom_safe_id}"
            self._not_in_use_id = f"not_in_use_{self._dom_safe_id}"
            self._is_in_use = True  # Track if panel is active in single-agent mode

            # Batch tracker (used by start_new_round, show_restart_separator, etc.)
            self._batch_tracker = ToolBatchTracker()

            # Section widget IDs - using timeline for chronological view
            self._timeline_section_id = f"timeline_section_{self._dom_safe_id}"
            # Keep old IDs as aliases for compatibility
            self._tool_section_id = self._timeline_section_id
            self._thinking_section_id = self._timeline_section_id
            self._status_badge_id = f"status_badge_{self._dom_safe_id}"
            self._completion_footer_id = f"completion_footer_{self._dom_safe_id}"

            self._reasoning_header_shown = False

            # Session/restart tracking
            self._session_completed = False
            self._session_count = 1
            self._presentation_shown = False
            self._last_restart_separator_key: tuple[int, str, str] | None = None

            # Context tracking (per-round for view switching)
            self._context_sources: list[str] = []
            self._context_by_round: dict[int, list[str]] = {}  # round_num -> context_sources
            self._context_label_id = f"context_{self._dom_safe_id}"

            # Timer for updating elapsed time display
            self._header_timer = None

            # Timeout state tracking (for per-agent timeout display)
            self._timeout_state: dict[str, Any] | None = None

            # Task plan host (shared pinned UI)
            from massgen.frontend.displays.textual_widgets.task_plan_host import (
                TaskPlanHost,
            )

            self._task_plan_host = TaskPlanHost(
                agent_id=self.agent_id,
                ribbon=None,
                has_persisted_plan=self._has_persisted_task_plan,
                id=f"task_plan_host_{self._dom_safe_id}",
                classes="pinned-task-plan hidden",
            )

            # Phase 12: CSS-based round navigation (no storage needed - widgets stay in DOM)
            self._current_round: int = 1  # which round content is being received
            self._current_view: str = "round"  # "round" or "final_answer"
            self._viewed_round: int = 1  # which round is currently displayed

            # Final answer storage
            self._final_answer_content: str | None = None
            self._final_answer_metadata: dict[str, Any] | None = None

            # Terminal tool transition tracking (new_answer, vote)
            # When a terminal tool completes, we delay round transitions so users can see the action
            self._last_tool_was_terminal: bool = False
            self._transition_pending: bool = False
            self._transition_timer: Any | None = None
            self._pending_round_transition: tuple[int, bool, bool] | None = None  # (round_num, is_context_reset, defer_banner)

            # Final presentation tracking
            # When True, content flows through the normal pipeline but is tagged as final presentation
            self._is_final_presentation_round: bool = False

        def _has_persisted_task_plan(self) -> bool:
            """Return whether this agent's current workspace has a persisted plan/spec artifact."""
            try:
                orchestrator = getattr(self.coordination_display, "orchestrator", None)
                agents = getattr(orchestrator, "agents", None)
                if not isinstance(agents, dict):
                    return True

                agent = agents.get(self.agent_id)
                if agent is None:
                    return True

                filesystem_manager = getattr(agent, "filesystem_manager", None)
                get_workspace = getattr(filesystem_manager, "get_current_workspace", None)
                if not callable(get_workspace):
                    return True

                workspace = get_workspace()
                if not workspace:
                    return True

                workspace_path = Path(str(workspace))
                candidates = (
                    workspace_path / "tasks" / "plan.json",
                    workspace_path / "tasks" / "spec.json",
                    workspace_path / "plan.json",
                    workspace_path / "spec.json",
                )
                return any(path.exists() for path in candidates)
            except Exception:
                return True

        def reset_round_state(self) -> None:
            """Reset round tracking state for a new turn."""
            from massgen.logger_config import logger

            logger.info(f"[AgentPanel] reset_round_state() called for agent {self.agent_id}")
            logger.info(f"[AgentPanel] Before reset: _current_round={self._current_round}, _viewed_round={self._viewed_round}")

            self._current_round = 1
            self._viewed_round = 1
            self._context_by_round.clear()
            self._is_final_presentation_round = False
            self._final_answer_content = None
            self._final_answer_metadata = None
            self._last_restart_separator_key = None

            logger.info(f"[AgentPanel] After reset: _current_round={self._current_round}, _viewed_round={self._viewed_round}")

            # Clear task plan state for the new turn (new workspace starts empty)
            try:
                if hasattr(self, "_task_plan_host") and self._task_plan_host:
                    self._task_plan_host.clear()
            except Exception as e:
                logger.warning(f"[AgentPanel] Failed to clear task plan for {self.agent_id}: {e}")

            # Reset round state in child widgets
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                logger.info("[AgentPanel] Found timeline widget, calling timeline.reset_round_state()")
                timeline.reset_round_state()
                logger.info(f"[AgentPanel] Timeline reset complete: _viewed_round={timeline._viewed_round}, _round_1_shown={timeline._round_1_shown}")
            except Exception as e:
                logger.warning(f"Failed to reset timeline round state for {self.agent_id}: {e}")

            # NOTE: Don't reset ribbon here - it's at app level, not inside panel
            # The ribbon is reset directly in update_turn_header() via self._status_ribbon.reset_round_state_all_agents()
            logger.info("[AgentPanel] Skipping ribbon reset (handled at app level)")

        def compose(self) -> ComposeResult:
            with Vertical():
                # NOTE: Agent header row removed in Phase 8c/10 - redundant with tab bar + status ribbon
                # Agent ID shown in tabs, round number shown in ribbon
                # Background tasks can be viewed via tool cards in timeline

                # Context sources label (hidden by default, shown when context is injected)
                yield Label(
                    "",
                    id=self._context_label_id,
                    classes="context-label hidden",
                )

                # Loading indicator - centered, shown when waiting with no content
                with Container(id=self._loading_id, classes="loading-container"):
                    yield ProgressIndicator(
                        message="Ready",
                        id=f"progress_{self._dom_safe_id}",
                    )

                # "Not in use" overlay - shown for inactive agents in single-agent mode
                with Container(id=self._not_in_use_id, classes="not-in-use-overlay hidden"):
                    yield Label("👤 Not in use", classes="not-in-use-label")
                    yield Label("Single-agent mode active", classes="not-in-use-sublabel")

                # Pinned task plan - stays at top, collapsible (hidden until task plan created)
                yield self._task_plan_host

                # Chronological timeline layout - tools and text interleaved
                yield TimelineSection(id=self._timeline_section_id)

                # Final Answer view (hidden by default, shown via view dropdown)
                from .textual_widgets import FinalAnswerView

                self._final_answer_view_id = f"final_answer_view_{self._dom_safe_id}"
                yield FinalAnswerView(
                    agent_id=self.agent_id,
                    id=self._final_answer_view_id,
                )

                yield CompletionFooter(id=self._completion_footer_id)

                # Legacy RichLog kept for fallback/compatibility
                yield self.content_log
                yield self.current_line_label

        # NOTE: on_click handler removed in Phase 8c/10 - header badges no longer exist
        # Background tasks can be viewed via tool cards in timeline
        # Task plan is shown in collapsible TaskPlanCard

        def _hide_loading(self):
            """Hide the loading indicator when content arrives."""
            if not self._has_content:
                self._has_content = True
                try:
                    # Stop spinner animation
                    progress = self.query_one(f"#progress_{self._dom_safe_id}")
                    progress.stop_spinner()
                    # Hide container
                    loading = self.query_one(f"#{self._loading_id}")
                    loading.add_class("hidden")
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

        def _update_loading_text(self, text: str):
            """Update the loading indicator text."""
            try:
                progress = self.query_one(f"#progress_{self._dom_safe_id}")
                progress.message = text
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _start_loading_spinner(self, message: str = "Waiting for agent..."):
            """Start the loading spinner with a message."""
            try:
                progress = self.query_one(f"#progress_{self._dom_safe_id}")
                progress.start_spinner(message)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def on_mount(self) -> None:
            """Start the loading spinner when the panel is mounted."""
            self._start_loading_spinner("Ready")

            # Note: Round 1 banner is added by TimelineSection.on_mount

            # Initialize ribbon with Round 1 so the dropdown shows it immediately
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_round(self.agent_id, 1, False)
                    logger.debug(f"AgentPanel.on_mount: Initialized ribbon with Round 1 for {self.agent_id}")
                    self._task_plan_host.set_ribbon(app._status_ribbon)
            except Exception as e:
                logger.debug(f"AgentPanel.on_mount: Failed to initialize ribbon: {e}")

        # -------------------------------------------------------------------------
        # BaseTUILayoutMixin abstract method implementations
        # -------------------------------------------------------------------------

        def _get_timeline(self) -> TimelineSection | None:
            """Get the TimelineSection widget (implements BaseTUILayoutMixin)."""
            try:
                return self.query_one(f"#{self._timeline_section_id}", TimelineSection)
            except Exception:
                return None

        def _get_ribbon(self) -> AgentStatusRibbon | None:
            """Get the AgentStatusRibbon widget (implements BaseTUILayoutMixin)."""
            try:
                return self.coordination_display._agent_status_ribbon
            except Exception:
                return None

        def set_in_use(self, in_use: bool) -> None:
            """Set whether this panel is in use (for single-agent mode).

            Args:
                in_use: True if this agent is active, False to show "Not in use" overlay.
            """
            self._is_in_use = in_use
            try:
                overlay = self.query_one(f"#{self._not_in_use_id}")
                if in_use:
                    overlay.add_class("hidden")
                else:
                    overlay.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def is_in_use(self) -> bool:
            """Check if this panel is currently in use."""
            return self._is_in_use

        def update_context_display(self, context_sources: list[str]) -> None:
            """Update the context sources display in the panel header.

            Args:
                context_sources: List of answer labels this agent can see (e.g., ["agent1.1", "agent2.1"])
            """
            self._context_sources = context_sources.copy()
            # Store context by current round for view switching
            self._context_by_round[self._current_round] = context_sources.copy()

            try:
                context_label = self.query_one(f"#{self._context_label_id}", Label)

                if context_sources:
                    # Format: "Context: A1.1, A2.1" or "Context: A1.1 +2 more"
                    # Shorten labels: "agent1.1" -> "A1.1"
                    short_labels = []
                    for label in context_sources[:3]:
                        # Convert "agent1.1" to "A1.1"
                        if label.startswith("agent"):
                            short_labels.append("A" + label[5:])
                        else:
                            short_labels.append(label)

                    ctx_text = f"Context: {', '.join(short_labels)}"
                    if len(context_sources) > 3:
                        ctx_text += f" +{len(context_sources) - 3}"

                    context_label.update(ctx_text)
                    context_label.remove_class("hidden")
                else:
                    context_label.update("")
                    context_label.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def update_task_plan(self, tasks: list[dict[str, Any]], plan_id: str = None, operation: str = "create") -> None:
            """Update the active task plan for this agent.

            Args:
                tasks: List of task dictionaries
                plan_id: ID of the task plan (tool_id)
                operation: Type of operation (create, update, etc.)
            """
            self._task_plan_host.update_task_plan(tasks, plan_id=plan_id, operation=operation)

        def get_task_plan_tasks(self) -> list[dict[str, Any]] | None:
            """Return the active task plan tasks, if any."""
            return self._task_plan_host.get_active_tasks()

        def _refresh_header(self) -> None:
            """Refresh the header display.

            NOTE: Agent header row removed in Phase 8c/10 - now a no-op.
            Round number shown in status ribbon, agent ID in tabs.
            Background tasks visible via tool cards in timeline.
            """
            # Header row was removed - ribbon and tabs show this info now

        def toggle_task_plan(self) -> None:
            """Toggle the visibility of the pinned task plan."""
            self._task_plan_host.toggle()

        def _update_pinned_task_plan(
            self,
            tasks: list[dict[str, Any]],
            focused_task_id: str | None = None,
            operation: str = "update",
            show_notification: bool = True,
        ) -> None:
            """Update the pinned task plan widget.

            Args:
                tasks: List of task dictionaries
                focused_task_id: Task to highlight
                operation: Type of operation
                show_notification: Whether to show update notification in timeline
            """
            try:
                self._task_plan_host.update_pinned_task_plan(
                    tasks=tasks,
                    focused_task_id=focused_task_id,
                    operation=operation,
                    show_notification=show_notification,
                )
            except Exception as e:
                tui_log(f"_update_pinned_task_plan error: {e}")

        def show_restart_separator(self, attempt: int = 1, reason: str = "", instructions: str = ""):
            """Handle orchestration-level restart (new attempt).

            Resets round counter back to 1 and shows an "Attempt N" separator
            so users can distinguish orchestration restarts from within-attempt
            round changes.
            """
            from massgen.logger_config import logger

            restart_key = (
                int(attempt),
                (reason or "").strip(),
                (instructions or "").strip(),
            )
            if self._last_restart_separator_key == restart_key:
                logger.debug(
                    "[AgentPanel] Skipping duplicate restart separator for %s (attempt=%s)",
                    self.agent_id,
                    attempt,
                )
                return
            self._last_restart_separator_key = restart_key

            # Mark that non-tool content arrived (prevents future batching across this content)
            self._batch_tracker.mark_content_arrived()
            # Finalize any current batch when restart occurs
            self._batch_tracker.finalize_current_batch()

            # Reset round counter so the new attempt starts at round 1
            self._current_round = 1
            self._viewed_round = 1
            self._current_view = "round"

            # Reset timeline tracking for the new attempt (don't scroll —
            # the new banner appends at the bottom and auto-scrolls there)
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.set_viewed_round(1)
                timeline.clear_tools_tracking()
                # Add attempt banner
                timeline.add_attempt_banner(
                    attempt=attempt,
                    reason=reason,
                    instructions=instructions,
                    round_number=1,
                )

                # Add Round 1 banner under the attempt separator
                timeline._round_1_shown = True
                timeline.add_separator("Round 1", round_number=1)
            except Exception as e:
                logger.error(f"AgentPanel.show_restart_separator timeline error: {e}")

            # Reset per-attempt UI state
            self._hide_completion_footer()
            self._batch_tracker.reset()
            self._reasoning_header_shown = False

        def _is_planning_mcp_tool(self, tool_name: str) -> bool:
            """Check if a tool is a Planning MCP tool (should show TaskPlanCard instead of tool card)."""
            from massgen.frontend.displays.task_plan_support import is_planning_tool

            return is_planning_tool(tool_name)

        def _is_subagent_tool(self, tool_name: str, args_payload: Any | None = None) -> bool:
            """Check if a tool is a subagent tool (should show SubagentCard instead of tool card).

            Args:
                tool_name: The tool name to check

            Returns:
                True if this is a subagent spawning tool
            """
            subagent_tools = [
                "spawn_subagents",
                "spawn_subagent",
                "continue_subagent",
            ]
            tool_lower = str(tool_name or "").lower()
            if any(st in tool_lower for st in subagent_tools):
                return True

            if _is_start_background_tool_name(tool_name):
                args_data = _extract_spawn_subagents_args_for_tool(tool_name, args_payload)
                if isinstance(args_data, dict):
                    target_tool = str(args_data.get("tool_name") or args_data.get("tool") or "").lower()
                    if any(st in target_tool for st in subagent_tools):
                        return True
                    if isinstance(args_data.get("tasks"), list):
                        return True

            return False

        def _show_subagent_card_from_args(
            self,
            tool_data,
            timeline,
            round_number: int | None = None,
        ) -> None:
            """Show SubagentCard when subagent tools start, parsing args payloads.

            This allows users to see subagents as they're being spawned, not just after completion.
            NOTE: This is a fallback path - the callback via show_subagent_card_from_spawn
            should create the card immediately. This path only runs when the "running" chunk
            arrives (which may be delayed due to stream buffering).
            """
            from massgen.subagent.models import SubagentDisplayData

            # Check if card already exists (created by callback)
            card_id = _subagent_card_dom_id(tool_data.tool_id)
            try:
                timeline.query_one(f"#{card_id}", SubagentCard)
                tui_log(f"_show_subagent_card_from_args: card {card_id} already exists, skipping")
                return
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")  # Card doesn't exist, continue to create it

            # Also check if a card for THIS tool call already exists under a different ID
            # (callback path might use a different ID scheme)
            try:
                for existing_card in timeline.query(SubagentCard):
                    existing_tool_call_id = getattr(existing_card, "tool_call_id", None) or getattr(existing_card, "_tool_call_id", None)
                    if str(existing_tool_call_id) == str(tool_data.tool_id):
                        tui_log(f"_show_subagent_card_from_args: card for tool {tool_data.tool_id} already exists ({existing_card.id}), skipping")
                        return
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Parse args to get task list
            args = tool_data.args_full
            if not args:
                tui_log("_show_subagent_card_from_args: no args_full")
                return

            args_data = _extract_spawn_subagents_args_for_tool(
                getattr(tool_data, "tool_name", ""),
                args,
            )
            if args_data is None:
                tui_log(f"_show_subagent_card_from_args: failed to parse args: {str(args)[:100]}")
                return

            # Extract tasks from args.
            tasks = args_data.get("tasks", [])
            if not isinstance(tasks, list):
                tasks = []

            def _find_existing_subagent(subagent_id: str) -> SubagentDisplayData | None:
                try:
                    for existing_card in timeline.query(SubagentCard):
                        for candidate in getattr(existing_card, "subagents", []):
                            if getattr(candidate, "id", None) == subagent_id:
                                return candidate
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")
                return None

            if not tasks:
                # continue_subagent payloads target a single subagent instead of tasks[].
                subagent_id = str(args_data.get("subagent_id") or args_data.get("id") or "").strip()
                if subagent_id:
                    existing = _find_existing_subagent(subagent_id)
                    continue_message = str(args_data.get("message") or "").strip()
                    existing_task = str(getattr(existing, "task", "") or "").strip() if existing else ""
                    task_desc = str(args_data.get("task") or "").strip()
                    if not task_desc:
                        task_desc = existing_task
                    if not task_desc and continue_message:
                        task_desc = continue_message
                    if not task_desc:
                        task_desc = "Continue subagent"
                    timeout_seconds = args_data.get("timeout_seconds") or (getattr(existing, "timeout_seconds", None) if existing else None) or 300
                    tasks = [
                        {
                            "subagent_id": subagent_id,
                            "task": task_desc,
                            "timeout_seconds": timeout_seconds,
                            "context_paths": list(getattr(existing, "context_paths", []) or []) if existing else [],
                            "subagent_type": getattr(existing, "subagent_type", None) if existing else None,
                        },
                    ]

            if not tasks:
                tui_log("_show_subagent_card_from_args: no tasks in args")
                return

            tui_log(f"_show_subagent_card_from_args: found {len(tasks)} tasks to spawn")

            # Resolve base log directory for subagents in this session
            subagent_logs_base = None
            try:
                from massgen.logger_config import get_log_session_dir

                log_dir = get_log_session_dir()
                if log_dir:
                    subagent_logs_base = log_dir / "subagents"
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Create SubagentDisplayData for each task (all pending/running)
            subagents = []
            for task_data in tasks:
                subagent_id = task_data.get("subagent_id", task_data.get("id", f"subagent_{len(subagents)}"))
                task_desc = task_data.get("task", "")
                log_path = str(subagent_logs_base / subagent_id) if subagent_logs_base else None
                context_paths = _normalize_subagent_context_paths(task_data.get("context_paths", []))
                subagent_type = _normalize_subagent_type(task_data.get("subagent_type"))

                subagents.append(
                    SubagentDisplayData(
                        id=subagent_id,
                        task=task_desc,
                        status="running",  # All start as running
                        progress_percent=0,
                        elapsed_seconds=0.0,
                        timeout_seconds=task_data.get("timeout_seconds", 300),
                        workspace_path="",  # Not yet assigned
                        workspace_file_count=0,
                        last_log_line="Starting...",
                        error=None,
                        answer_preview=None,
                        log_path=log_path,
                        context_paths=context_paths,
                        subagent_type=subagent_type,
                    ),
                )

            if not subagents:
                return

            # Create and add SubagentCard to timeline
            resolved_round = round_number
            if resolved_round is None:
                resolved_round = getattr(self, "_current_round", getattr(timeline, "_viewed_round", 1))
            try:
                resolved_round = max(1, int(resolved_round or 1))
            except Exception:
                resolved_round = 1
            card = SubagentCard(
                subagents=subagents,
                tool_call_id=tool_data.tool_id,
                status_callback=None,
                id=card_id,
            )

            app = getattr(self, "app", None)
            if app and hasattr(app, "_build_spawn_status_callback"):
                try:
                    try:
                        status_callback = app._build_spawn_status_callback(
                            agent_id=self.agent_id,
                            seed_subagents=subagents,
                            card=card,
                        )
                    except TypeError:
                        # Backward compatibility for tests/overrides that still expose
                        # the older two-argument callback builder shape.
                        status_callback = app._build_spawn_status_callback(
                            agent_id=self.agent_id,
                            seed_subagents=subagents,
                        )
                    if status_callback is not None:
                        card.set_status_callback(status_callback)
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

            timeline.add_widget(card, round_number=resolved_round)
            tui_log(f"_show_subagent_card_from_args: added SubagentCard with {len(subagents)} pending subagents")

        def _update_subagent_card_with_results(self, tool_data, timeline) -> None:
            """Update existing SubagentCard with completion results.

            Called when spawn_subagents tool completes to update status, progress, answers, etc.
            """
            # Find existing card - check both possible IDs since callback might use different ID
            card_id = _subagent_card_dom_id(tool_data.tool_id)
            card = None
            try:
                card = timeline.query_one(f"#{card_id}", SubagentCard)
                tui_log(f"_update_subagent_card_with_results: found card by tool_id: {card_id}")
            except Exception:
                # Also try querying by tool_call_id if different
                if hasattr(tool_data, "tool_call_id") and tool_data.tool_call_id != tool_data.tool_id:
                    alt_id = _subagent_card_dom_id(tool_data.tool_call_id)
                    try:
                        card = timeline.query_one(f"#{alt_id}", SubagentCard)
                        tui_log(f"_update_subagent_card_with_results: found card by tool_call_id: {alt_id}")
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

                # Try finding card by explicit tool_call_id metadata.
                if card is None:
                    try:
                        cards = list(timeline.query(SubagentCard))
                        target_ids = {str(tool_data.tool_id)}
                        if hasattr(tool_data, "tool_call_id") and tool_data.tool_call_id:
                            target_ids.add(str(tool_data.tool_call_id))
                        for candidate in cards:
                            candidate_tool_call_id = getattr(candidate, "tool_call_id", None) or getattr(candidate, "_tool_call_id", None)
                            if candidate_tool_call_id is not None and str(candidate_tool_call_id) in target_ids:
                                card = candidate
                                tui_log(
                                    "_update_subagent_card_with_results: " f"found card by metadata: {candidate.id}",
                                )
                                break
                    except Exception as e:
                        tui_log(f"[TextualDisplay] {e}")

            if card is None:
                tui_log(f"_update_subagent_card_with_results: no card found (tried {card_id}), skipping duplicate creation")
                # Don't create a new card - the callback already created one
                # Just log and return to avoid duplicates
                return

            result_data, spawned = _extract_spawned_subagents(tool_data.result_full)
            if result_data is None:
                return

            # Remove card only on true spawn failure (no results at all)
            if not result_data.get("success", True) and not spawned:
                try:
                    card.remove()
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")
                return
            if not spawned:
                return

            # Build updated subagent list
            updated_subagents = []
            for idx, sa_data in enumerate(spawned):
                subagent_id = str(sa_data.get("subagent_id") or sa_data.get("id") or "")
                existing = None
                if subagent_id:
                    for candidate in card.subagents:
                        if candidate.id == subagent_id:
                            existing = candidate
                            break
                # Positional fallback: card was created with placeholder IDs
                # (e.g. "subagent_0") before the MCP server assigned real sequential
                # IDs (e.g. "subagent_1").  subagent_type now flows directly from
                # the spawn result, so this mainly preserves any other pre-existing
                # display state (task text, etc.) when ID lookup fails.
                if existing is None and idx < len(card.subagents):
                    existing = card.subagents[idx]
                updated_subagents.append(_build_subagent_display_data(sa_data, existing))

            if updated_subagents:
                card.update_subagents(updated_subagents)
                tui_log(f"_update_subagent_card_with_results: updated card with {len(updated_subagents)} subagents")

        def _check_and_display_subagent_card(self, tool_data, timeline) -> None:
            """Check if tool result is from subagent spawn and display SubagentCard.

            Subagent tools include:
            - spawn_subagents
            - spawn_subagent
            - continue_subagent
            """
            # Check if tool name matches a subagent tool
            tool_name = tool_data.tool_name.lower()
            is_subagent_tool = self._is_subagent_tool(
                tool_name,
                getattr(tool_data, "args_full", None),
            )
            tui_log(f"_check_and_display_subagent_card: tool_name={tool_name}, is_subagent={is_subagent_tool}")
            if not is_subagent_tool:
                return

            _, spawned = _extract_spawned_subagents(tool_data.result_full)
            tui_log(f"_check_and_display_subagent_card: found {len(spawned) if spawned else 0} spawned subagents")
            if not spawned:
                return

            # Create SubagentDisplayData for each spawned subagent
            subagents = []
            for sa_data in spawned:
                subagents.append(_build_subagent_display_data(sa_data))

            if not subagents:
                return

            # Create and add SubagentCard to timeline
            import re as _re

            _safe_id = _re.sub(r"[^a-zA-Z0-9_-]", "_", tool_data.tool_id)
            card = SubagentCard(
                subagents=subagents,
                tool_call_id=tool_data.tool_id,
                id=f"subagent_{_safe_id}",
            )
            timeline.add_widget(card)
            tui_log(f"_check_and_display_subagent_card: added SubagentCard with {len(subagents)} subagents")

        def _check_and_display_task_plan(self, tool_data, timeline) -> None:
            """Check if tool result is from Planning MCP and display/update TaskPlanCard."""
            from massgen.frontend.displays.task_plan_support import (
                update_task_plan_from_tool,
            )

            update_task_plan_from_tool(self._task_plan_host, tool_data, timeline, log=tui_log)

        def _clear_timeline(self):
            """Clear the timeline for a new session/round."""
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.clear()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Reset per-round state
            self._reset_round_state()

        def _reset_round_state(self):
            """Reset per-round state (task plan, background tools indicator, etc.)."""
            # Clear task plan tracking + UI
            self._task_plan_host.clear()

            # Clear tools tracking (resets bg count) but keep visual timeline
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.clear_tools_tracking()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Refresh header to hide badges (bg shells will be killed by orchestrator)
            self._refresh_header()

        def _clear_tool_section(self):
            """Clear the tool section for a new session (legacy, calls _clear_timeline)."""
            self._clear_timeline()
            try:
                tool_section = self.query_one(f"#{self._tool_section_id}", ToolSection)
                tool_section.clear()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _show_completion_footer(self):
            """Show the completion footer."""
            try:
                footer = self.query_one(f"#{self._completion_footer_id}", CompletionFooter)
                footer.show_completed()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def _hide_completion_footer(self):
            """Hide the completion footer."""
            try:
                footer = self.query_one(f"#{self._completion_footer_id}", CompletionFooter)
                footer.hide()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        # ========================================================================
        # Phase 12: CSS-based round navigation
        # ========================================================================
        # Storage methods removed - widgets stay in DOM with round-N tags

        def start_new_round(
            self,
            round_number: int,
            is_context_reset: bool = False,
            defer_banner: bool = False,
        ) -> None:
            """Start a new round - update tracking and switch visibility.

            Phase 12: With CSS-based visibility, all round content stays in the DOM.
            We switch visibility to show the new round and hide old round content.

            Terminal Tool Delay: When a terminal tool (new_answer, vote) just completed,
            we delay the transition by 3 seconds so users can see the completed action
            before the view switches to the new round.

            IMPORTANT: This method is atomic - tracking is updated FIRST before any
            visibility changes to ensure all new content gets tagged with the correct
            round number.

            Args:
                round_number: The new round number
                is_context_reset: Whether this round started with a context reset
                defer_banner: If True, defer the round banner until first content
            """
            from massgen.logger_config import logger

            logger.debug(
                f"AgentPanel.start_new_round: round={round_number}, " f"prev_round={self._current_round}, context_reset={is_context_reset}, defer_banner={defer_banner}",
            )

            # Terminal tool transition delay - give users time to see completed action
            if self._transition_pending:
                # Already waiting for a transition - update the pending round
                self._pending_round_transition = (round_number, is_context_reset, defer_banner)
                return

            if self._last_tool_was_terminal:
                self._last_tool_was_terminal = False  # Reset for next round

            # Execute the round transition immediately
            self._execute_round_transition_impl(round_number, is_context_reset, defer_banner)

        def _execute_round_transition(self) -> None:
            """Execute a delayed round transition (called by timer)."""
            self._transition_pending = False
            self._transition_timer = None

            if self._pending_round_transition:
                round_number, is_context_reset, defer_banner = self._pending_round_transition
                self._pending_round_transition = None
                self._execute_round_transition_impl(round_number, is_context_reset, defer_banner)

        def _execute_round_transition_impl(
            self,
            round_number: int,
            is_context_reset: bool = False,
            defer_banner: bool = False,
        ) -> None:
            """Execute the actual round transition logic."""
            from massgen.logger_config import logger

            # Step 1: Update round tracking FIRST (before any visibility changes)
            # This ensures all subsequent content gets tagged with the new round number
            self._current_round = round_number
            self._viewed_round = round_number  # Auto-follow to new round
            self._current_view = "round"

            # Step 2: Switch timeline visibility to new round (hides old round content)
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.switch_to_round(round_number)
                # Clear tools tracking so new round's tool_ids don't collide with old round's
                timeline.clear_tools_tracking()

                # Step 3: Add (or defer) "Round X" banner at the top of each new round
                if round_number >= 1:
                    subtitle = "Restart" if round_number > 1 else None
                    if is_context_reset:
                        subtitle = (subtitle or "") + " • Context cleared"
                    if defer_banner and hasattr(timeline, "defer_round_banner"):
                        timeline.defer_round_banner(
                            round_number,
                            f"Round {round_number}",
                            subtitle if subtitle else None,
                        )
                    elif round_number > 1:
                        timeline.add_separator(
                            f"Round {round_number}",
                            round_number=round_number,
                            subtitle=subtitle if subtitle else None,
                        )
            except Exception as e:
                logger.error(f"AgentPanel.start_new_round timeline error: {e}")

            # Step 4: Reset per-round UI state
            self._hide_completion_footer()
            self._batch_tracker.reset()
            self._reasoning_header_shown = False

            # Step 5: Clear context display for new round (will be updated when context is injected)
            self._restore_context_for_round(round_number)

            # Step 6: Notify the status ribbon about the new round
            self._update_ribbon_round(round_number, is_context_reset)

            logger.debug(f"AgentPanel.start_new_round: completed round={round_number}")

        def mark_terminal_tool_complete(self) -> None:
            """Mark that a terminal tool (new_answer, vote) has just completed.

            This triggers a delayed transition when start_new_round is called,
            giving users time to see the completed action before the view switches.
            """
            self._last_tool_was_terminal = True

        def start_final_presentation(self, vote_counts: dict[str, int] | None = None, answer_labels: dict[str, str] | None = None) -> None:
            """Start the final presentation phase - shows fresh view with distinct banner.

            This is similar to start_new_round but uses a "Final Presentation" banner
            with a distinct green color scheme to indicate the winning agent presenting.

            Args:
                vote_counts: Optional dict of {agent_id: vote_count} for vote summary display
                answer_labels: Optional dict of {agent_id: label} for display (e.g., {"agent1": "A1.1"})
            """
            from massgen.logger_config import logger

            # Increment round for final presentation
            new_round = self._current_round + 1

            logger.debug(
                f"AgentPanel.start_final_presentation: agent={self.agent_id}, " f"new_round={new_round}",
            )

            # Step 1: Update round tracking
            self._current_round = new_round
            self._viewed_round = new_round
            self._current_view = "round"
            self._is_final_presentation_round = True  # Mark as final presentation round

            # Step 2: Build vote summary subtitle using answer labels (e.g., "A1.1")
            subtitle = ""
            if vote_counts:
                # Format: "Votes: A1.1(2), A2.1(1)"
                sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
                vote_parts = []
                for agent_id, count in sorted_votes:
                    # Use answer label if available, otherwise fall back to shortened agent name
                    if answer_labels and agent_id in answer_labels:
                        label = answer_labels[agent_id]
                    else:
                        # Fallback: "agent_a" -> "Aa", "agent1" -> "A1"
                        label = agent_id.replace("agent_", "A").replace("agent", "A")
                    vote_parts.append(f"{label} ({count})")
                subtitle = f"Votes: {', '.join(vote_parts)}"

            # Step 3: Switch timeline visibility and add final presentation banner
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.switch_to_round(new_round)
                # Clear tool tracking to prevent tool_id collisions with previous round
                timeline.clear_tools_tracking()

                # Add "Final Presentation" banner with distinct styling and vote summary
                has_banner = False
                if hasattr(timeline, "_has_round_banner"):
                    try:
                        has_banner = timeline._has_round_banner(new_round)
                    except Exception:
                        has_banner = False
                if not has_banner:
                    timeline.add_separator("FINAL PRESENTATION", round_number=new_round, subtitle=subtitle)
            except Exception as e:
                logger.error(f"AgentPanel.start_final_presentation timeline error: {e}")

            # Step 4: Reset per-round UI state
            self._hide_completion_footer()
            self._batch_tracker.reset()
            self._reasoning_header_shown = False

            # Step 4: Clear context display for final presentation (will be updated if needed)
            self._restore_context_for_round(new_round)

            # Step 5: Update ribbon to show "F" for final presentation round
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    # Mark this as a final presentation round - shows "F" instead of "R{n}"
                    app._status_ribbon.set_round(self.agent_id, new_round, is_final_presentation=True)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            logger.debug("AgentPanel.start_final_presentation: completed")

        def _update_ribbon_round(self, round_number: int, is_context_reset: bool = False) -> None:
            """Update the status ribbon with the current round info."""
            try:
                # Find the ribbon in the parent hierarchy
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_round(self.agent_id, round_number, is_context_reset)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def switch_to_round(self, round_number: int) -> None:
            """Scroll to a specific round in the unified timeline.

            All round content stays visible in a continuous timeline.
            Selecting a round smoothly scrolls to that round's separator banner.

            Args:
                round_number: The round number to scroll to
            """
            self._viewed_round = round_number
            self._current_view = "round"

            # Use TimelineSection's scroll-to behavior
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.switch_to_round(round_number)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Update ribbon to show we're viewing this round
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_viewed_round(self.agent_id, round_number)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Restore context display for this round
            self._restore_context_for_round(round_number)

        def _restore_context_for_round(self, round_number: int) -> None:
            """Restore the context display for a specific round.

            When viewing historical rounds, show the context that was active during that round.
            """
            # Get context sources for this round (empty if not set)
            context_sources = self._context_by_round.get(round_number, [])
            self._context_sources = context_sources

            try:
                context_label = self.query_one(f"#{self._context_label_id}", Label)

                if context_sources:
                    # Format: "Context: A1.1, A2.1" (same as update_context_display)
                    short_labels = []
                    for label in context_sources[:3]:
                        if label.startswith("agent"):
                            short_labels.append("A" + label[5:])
                        else:
                            short_labels.append(label)

                    ctx_text = f"Context: {', '.join(short_labels)}"
                    if len(context_sources) > 3:
                        ctx_text += f" +{len(context_sources) - 3}"

                    context_label.update(ctx_text)
                    context_label.remove_class("hidden")
                else:
                    context_label.update("")
                    context_label.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def switch_to_final_answer(self) -> None:
            """Switch the view to display the final answer."""
            from .textual_widgets import FinalAnswerView

            self._current_view = "final_answer"

            # Hide timeline, show final answer view
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Show the final answer view and update its content
            try:
                final_view = self.query_one(f"#{self._final_answer_view_id}", FinalAnswerView)
                if self._final_answer_content:
                    final_view.set_content(self._final_answer_content)
                if self._final_answer_metadata:
                    final_view.set_metadata(self._final_answer_metadata)
                final_view.show()
            except Exception as e:
                tui_log(f"switch_to_final_answer error showing view: {e}")

            # Update ribbon
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_viewing_final_answer(self.agent_id, True)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def switch_from_final_answer(self) -> None:
            """Switch back from final answer view to round view."""
            from .textual_widgets import FinalAnswerView

            self._current_view = "round"

            # Show timeline, hide final answer view
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                timeline.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            try:
                final_view = self.query_one(f"#{self._final_answer_view_id}", FinalAnswerView)
                final_view.hide()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Update ribbon
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_viewing_final_answer(self.agent_id, False)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def set_final_answer(self, content: str, metadata: dict[str, Any] | None = None) -> None:
            """Store the final answer content for this agent.

            Args:
                content: The final answer text
                metadata: Optional metadata (votes, presenting agent, rounds, etc.)
            """
            self._final_answer_content = content
            self._final_answer_metadata = metadata or {}

            # Mark final answer as available in the ribbon
            try:
                app = self.app
                if hasattr(app, "_status_ribbon") and app._status_ribbon:
                    app._status_ribbon.set_final_answer_available(self.agent_id, True)
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def get_current_round(self) -> int:
            """Get the current round number being received."""
            return self._current_round

        def get_viewed_round(self) -> int:
            """Get the round number currently being viewed."""
            return self._viewed_round

        def get_view_state(self) -> tuple[str, int | None]:
            """Get the current view state.

            Returns:
                Tuple of (view_type, round_number) where view_type is "round" or "final_answer"
            """
            if self._current_view == "final_answer":
                return ("final_answer", None)
            return ("round", self._viewed_round)

        # ========================================================================
        # End Phase 12.2
        # ========================================================================

        def update_status(self, status: str):
            """Update agent status."""
            if self._line_buffer.strip():
                self.content_log.write(Text(self._line_buffer))
                self._line_buffer = ""
                self.current_line_label.update(Text(""))

            if status == "working" and self.status != "working":
                self._start_time = datetime.now()
                # Update loading text when working
                self._update_loading_text("🔄 Agent thinking...")
                # Start timer to update elapsed time display
                self._start_header_timer()
            elif status == "streaming":
                self._update_loading_text("📝 Agent responding...")
                # Keep timer running during streaming
                if self._header_timer is None:
                    self._start_header_timer()
            elif status in ("completed", "error", "waiting"):
                self._start_time = None
                # Stop timer when done
                self._stop_header_timer()

            self.status = status
            self.remove_class("status-waiting", "status-working", "status-streaming", "status-completed", "status-error")
            self.add_class(f"status-{status}")

            # Update header labels
            self._refresh_header()

        def dim(self) -> None:
            """Dim this panel to indicate it's not the active/winner panel."""
            self.add_class("dimmed-panel")

        def undim(self) -> None:
            """Remove dimming from this panel."""
            self.remove_class("dimmed-panel")

        def _start_header_timer(self) -> None:
            """Start the header timer to update elapsed time."""
            if self._header_timer is None:
                self._header_timer = self.set_interval(1.0, self._update_header_timer)

        def _stop_header_timer(self) -> None:
            """Stop the header timer."""
            if self._header_timer is not None:
                self._header_timer.stop()
                self._header_timer = None

        def _update_header_timer(self) -> None:
            """Update the header with current elapsed time."""
            if self._start_time is None:
                self._stop_header_timer()
                return
            # Update header labels
            self._refresh_header()

        def update_timeout(self, timeout_state: dict[str, Any]) -> None:
            """Update timeout display state.

            Args:
                timeout_state: Timeout state from orchestrator.get_agent_timeout_state()
            """
            self._timeout_state = timeout_state
            # Header refresh happens via the timer (_update_header_timer runs every second)

        def jump_to_latest(self):
            """Scroll to latest entry if supported."""
            try:
                self.content_log.scroll_end(animate=False)
            except Exception:
                try:
                    self.content_log.scroll_end()
                except Exception as e:
                    tui_log(f"[TextualDisplay] {e}")

        def add_hook_to_tool(self, tool_call_id: str | None, hook_info: dict[str, Any]):
            """Route hook execution info to the TimelineSection's tool card.

            Args:
                tool_call_id: The tool call ID to attach the hook to
                hook_info: Hook execution information dict
            """
            from massgen.logger_config import logger

            logger.info(
                f"[AgentPanel] add_hook_to_tool called: agent={self.agent_id}, " f"tool_call_id={tool_call_id}, hook={hook_info.get('hook_name')}",
            )
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                logger.info(f"[AgentPanel] Found timeline section: {timeline}")
                timeline.add_hook_to_tool(tool_call_id, hook_info)
            except Exception as e:
                logger.error(f"[AgentPanel] add_hook_to_tool failed: {e}")
                pass  # Timeline section not found or not available

        def _header_text_left(self) -> str:
            """Compose left side of header: agent info, backend, status."""
            backend = self.coordination_display._get_agent_backend_name(self.agent_id)
            status_icon = self._status_icon(self.status)

            parts = [f"{status_icon} {self.agent_id}"]
            if backend and backend != "Unknown":
                parts.append(f"({backend})")
            if self.key_index and 1 <= self.key_index <= 9:
                parts.append(f"[{self.key_index}]")

            # Add spacing before time to separate it visually
            if self._start_time and self.status in ("working", "streaming"):
                elapsed = datetime.now() - self._start_time
                elapsed_str = self._format_elapsed(elapsed.total_seconds())
                parts.append(f"  ⏱ {elapsed_str}")  # Extra spaces before timer

            # Add timeout countdown if active
            if self._timeout_state and self.status in ("working", "streaming"):
                timeout_text = self._format_timeout_display()
                if timeout_text:
                    parts.append(timeout_text)

            # Status in brackets
            parts.append(f"  [{self.status}]")

            return " ".join(parts)

        def _format_bg_badge(self) -> str:
            """Format background tasks badge text."""
            bg_count = self._get_background_tools_count()
            if bg_count > 0:
                return f"⚙️ {bg_count} bg"
            return ""

        def _format_tasks_badge(self) -> str:
            """Format task plan badge text.

            Note: Disabled - task info now shown in collapsible TaskPlanCard.
            """
            return ""

        def _header_text_right(self) -> str:
            """Compose right side of header (for compatibility)."""
            parts = []
            bg_badge = self._format_bg_badge()
            if bg_badge:
                parts.append(bg_badge)
            tasks_badge = self._format_tasks_badge()
            if tasks_badge:
                parts.append(tasks_badge)
            return "  ".join(parts)

        def _get_background_tools_count(self) -> int:
            """Get count of background/async operations for this agent."""
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                return timeline.get_background_tools_count()
            except Exception:
                return 0

        def _get_running_tools_count(self) -> int:
            """Get count of running/background tools for this agent."""
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                return timeline.get_running_tools_count()
            except Exception:
                return 0

        def _get_background_tools(self) -> list:
            """Get list of background/async operations for this agent."""
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                return timeline.get_background_tools()
            except Exception:
                return []

        def _get_background_tool_history(self) -> list:
            """Get background job history (active + recent terminal statuses)."""
            try:
                timeline = self.query_one(f"#{self._timeline_section_id}", TimelineSection)
                return timeline.get_background_tool_history()
            except Exception:
                return []

        def _update_running_tools_count(self) -> None:
            """Delegate running/background tool counter refresh to the app."""
            app = self.app
            updater = getattr(app, "_update_running_tools_count", None)
            if callable(updater):
                updater()

        def _header_text(self) -> str:
            """Compose full header text (for compatibility)."""
            left = self._header_text_left()
            right = self._header_text_right()
            if right:
                return f"{left}  {right}"
            return left

        def _format_task_plan_header(self) -> str | None:
            """Format task plan summary for header display.

            Returns:
                Formatted task plan string or None if no active plan.
            """
            tasks = self._task_plan_host.get_active_tasks()
            if not tasks:
                return None

            total = len(tasks)
            # Count both "completed" and "verified" as done
            completed = sum(1 for t in tasks if t.get("status") in ("completed", "verified"))
            in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")

            # Format: "Tasks: 3/9" or "Tasks: 3/9 ●2" if tasks in progress
            task_text = f"Tasks: {completed}/{total}"
            if in_progress > 0:
                task_text += f" ●{in_progress}"

            return task_text

        def _format_timeout_display(self) -> str | None:
            """Format timeout countdown for display in header.

            Returns:
                Formatted timeout string or None if no timeout active.
            """
            if not self._timeout_state:
                return None

            active_timeout = self._timeout_state.get("active_timeout")
            if not active_timeout:
                return None

            round_start_time = self._timeout_state.get("round_start_time")
            grace_seconds = self._timeout_state.get("grace_seconds", 0)
            soft_timeout_fired = self._timeout_state.get("soft_timeout_fired", False)
            wrap_up_requested = self._timeout_state.get("wrap_up_requested", False)

            if round_start_time is None:
                return None

            # Calculate remaining time locally for smooth 1-second updates
            elapsed = time.time() - round_start_time
            remaining_soft = max(0, active_timeout - elapsed)
            remaining_hard = max(0, active_timeout + grace_seconds - elapsed)
            is_hard_blocked = remaining_hard == 0

            # Get round number (0 = initial answer, 1+ = voting rounds)
            round_num = self._timeout_state.get("round_number", 0)

            # Format time as M:SS
            def fmt_time(secs: float) -> str:
                mins = int(secs // 60)
                s = int(secs % 60)
                return f"{mins}:{s:02d}"

            # Format the limit time
            limit_str = fmt_time(active_timeout)

            if is_hard_blocked:
                # Hard timeout active - tools are blocked
                return f"| [bold red]🚫 BLOCKED - round {round_num} limit was {limit_str}[/bold red]"
            elif soft_timeout_fired:
                # In grace period - show remaining time until hard block
                return f"| [bold yellow]⚠️ Round {round_num} grace: {fmt_time(remaining_hard)} left[/bold yellow]"
            elif wrap_up_requested:
                return f"| [yellow]⚠️ Round {round_num}: wrap up requested[/yellow]"
            elif remaining_soft <= 60:
                # Less than 1 minute - show warning in yellow
                return f"| [yellow]⏰ Round {round_num}: {fmt_time(remaining_soft)} / {limit_str}[/yellow]"
            else:
                # Normal countdown - show remaining / limit
                return f"| [dim]Round {round_num}: {fmt_time(remaining_soft)} / {limit_str}[/dim]"

        def _format_elapsed(self, seconds: float) -> str:
            """Format elapsed seconds into human-readable string."""
            if seconds < 60:
                return f"{int(seconds)}s"
            elif seconds < 3600:
                mins = int(seconds // 60)
                secs = int(seconds % 60)
                return f"{mins}m{secs}s"
            else:
                hours = int(seconds // 3600)
                mins = int((seconds % 3600) // 60)
                return f"{hours}h{mins}m"

        def _status_icon(self, status: str) -> str:
            """Return emoji (or fallback) for the given status."""
            icon_map = {
                "waiting": "⏳",
                "working": "🔄",
                "streaming": "📝",
                "completed": "✅",
                "error": "❌",
            }
            return self.coordination_display._get_icon(icon_map.get(status, "🤖"))

        def _make_dom_safe_id(self, raw_id: str) -> str:
            """Convert arbitrary agent IDs into Textual-safe DOM identifiers."""
            MAX_DOM_ID_LENGTH = 80

            truncated = raw_id[:MAX_DOM_ID_LENGTH] if len(raw_id) > MAX_DOM_ID_LENGTH else raw_id
            safe = re.sub(r"[^0-9a-zA-Z_-]", "_", truncated)

            if not safe:
                safe = "agent_default"

            if safe[0].isdigit():
                safe = f"agent_{safe}"

            base_safe = safe
            counter = 1
            used_ids = set(self.coordination_display._dom_id_mapping.values())

            while safe in used_ids:
                suffix = f"__{counter}"
                max_base_len = MAX_DOM_ID_LENGTH - len(suffix)
                safe = base_safe[:max_base_len] + suffix
                counter += 1

            if safe != base_safe:
                logger.debug(
                    f"DOM ID collision resolved for agent '{raw_id}': " f"'{base_safe}' -> '{safe}' (suffix added to avoid duplicate)",
                )

            self.coordination_display._dom_id_mapping[raw_id] = safe

            return safe

    # =============================================================================
    # Modal classes have been extracted to massgen/frontend/displays/textual/widgets/modals/
    # They are now imported at module level:
    # - KeyboardShortcutsModal, MCPStatusModal
    # - AnswerBrowserModal, TimelineModal, BrowserTabsModal, WorkspaceBrowserModal
    # - VoteResultsModal, OrchestratorEventsModal, CoordinationTableModal, AgentSelectorModal
    # - SystemStatusModal, TextContentModal, CostBreakdownModal, MetricsModal
    # - ContextModal, ConversationHistoryModal, TurnDetailModal
    # - BroadcastPromptModal, StructuredBroadcastPromptModal
    # - WorkspaceFilesModal, FileInspectionModal
    # - AgentOutputModal
    # =============================================================================

    class PostEvaluationPanel(Static):
        """Displays the most recent post-evaluation snippets."""

        def __init__(self):
            super().__init__(id="post_eval_container")
            self.agent_label = Label("", id="post_eval_label")
            self.log_view = RichLog(id="post_eval_log", highlight=True, markup=True, wrap=True)
            self.styles.display = "none"

        def compose(self) -> ComposeResult:
            yield self.agent_label
            yield self.log_view

        def update_lines(self, agent_id: str, lines: list[str]):
            """Show the last few post-evaluation lines."""
            self.styles.display = "block"
            self.agent_label.update(f"🔍 Post-Evaluation — {agent_id}")
            self.log_view.clear()
            if not lines:
                self.log_view.write("Evaluating answer...")
                return
            for entry in lines[-5:]:
                self.log_view.write(entry)

        def hide(self):
            """Hide the post-evaluation panel."""
            self.styles.display = "none"

    class FinalStreamPanel(Static):
        """Live view of the winning agent's presentation stream with action buttons.

        Layout principle: User sees everything they need at a glance without scrolling.
        - Fixed header with winner info and status
        - Scrollable content area for the full answer
        - Fixed footer with action buttons and follow-up input
        """

        def __init__(self, coordination_display: "TextualTerminalDisplay" = None):
            super().__init__(id="final_stream_container")
            self.coordination_display = coordination_display
            self.agent_label = Label("", id="final_stream_label")
            self.log_view = RichLog(id="final_stream_log", highlight=True, markup=True, wrap=True)
            self.current_line_label = Label("", classes="streaming_label")
            self._line_buffer = ""
            self._header_base = ""
            self._vote_summary = ""
            self._is_streaming = False
            self._winner_agent_id = ""
            self._winner_model_name = ""
            self._final_content: list[str] = []
            self.styles.display = "none"

        def compose(self) -> ComposeResult:
            # Fixed header section
            with Vertical(id="final_stream_header"):
                yield self.agent_label
            # Scrollable content area - takes remaining space
            with VerticalScroll(id="final_stream_content"):
                yield self.log_view
                yield self.current_line_label
            # Fixed footer section with buttons and follow-up input
            with Vertical(id="final_stream_footer", classes="hidden"):
                with Horizontal(id="final_stream_buttons"):
                    yield Button("Copy", id="final_copy_button", classes="action-primary")
                    yield Button("Workspace", id="final_workspace_button")
                yield Label("Ask a follow-up question:", id="followup_label")
                yield Input(placeholder="Continue the conversation...", id="followup_input")

        def begin(self, agent_id: str, model_name: str, vote_results: dict[str, Any]):
            """Reset panel with agent metadata including model name."""
            self.styles.display = "block"
            self._is_streaming = True
            self._winner_agent_id = agent_id
            self._winner_model_name = model_name or ""
            self._final_content = []
            self.add_class("streaming-active")

            # Build header with model name
            if model_name:
                self._header_base = f"🎤 Final Presentation — {agent_id} ({model_name})"
            else:
                self._header_base = f"🎤 Final Presentation — {agent_id}"

            self._vote_summary = self._format_vote_summary(vote_results or {})
            header = self._header_base
            if self._vote_summary:
                header = f"{header} | {self._vote_summary} | 🔴 LIVE"
            else:
                header = f"{header} | 🔴 LIVE"
            self.agent_label.update(header)
            self.log_view.clear()
            self._line_buffer = ""
            self.current_line_label.update("")

            # Hide footer during streaming (will show when complete)
            try:
                self.query_one("#final_stream_footer").add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Hide the main input area when final answer is displayed (webui parity)
            try:
                input_area = self.app.query_one("#input_area")
                input_area.add_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def append_chunk(self, chunk: str):
            """Append streaming text with buffering."""
            if not chunk:
                return

            def log_and_store(line: str):
                self.log_view.write(line)
                self._final_content.append(line)

            self._line_buffer = _process_line_buffer(
                self._line_buffer,
                chunk,
                log_and_store,
            )
            self.current_line_label.update(self._line_buffer)

        def end(self):
            """Mark presentation as complete, show buttons and follow-up input."""
            if self._line_buffer.strip():
                self.log_view.write(self._line_buffer)
                self._final_content.append(self._line_buffer)
            self._line_buffer = ""
            self.current_line_label.update("")
            self._is_streaming = False
            self.remove_class("streaming-active")
            self.add_class("winner-complete")

            header = self._header_base or str(self.agent_label.renderable)
            if self._vote_summary:
                header = f"{header} | {self._vote_summary}"
            self.agent_label.update(f"{header} | ✅ Completed")

            # Show footer with buttons and follow-up input
            try:
                self.query_one("#final_stream_footer").remove_class("hidden")
                # Focus the follow-up input
                followup_input = self.query_one("#followup_input", Input)
                followup_input.focus()
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle action button presses."""
            if event.button.id == "final_copy_button":
                self._copy_to_clipboard()
            elif event.button.id == "final_workspace_button":
                self._open_workspace()

        @on(Input.Submitted, "#followup_input")
        def on_followup_submitted(self, event: Input.Submitted) -> None:
            """Handle follow-up question submission."""
            question = event.value.strip()
            if not question:
                return

            # Clear the input
            event.input.value = ""

            # Hide the final stream panel and show main input
            self.styles.display = "none"
            self.remove_class("winner-complete")

            # Show the main input area again
            try:
                input_area = self.app.query_one("#input_area")
                input_area.remove_class("hidden")
            except Exception as e:
                tui_log(f"[TextualDisplay] {e}")

            # Submit the follow-up question through the app
            if hasattr(self.app, "_submit_followup_question"):
                self.app._submit_followup_question(question)
            elif self.coordination_display:
                # Fallback: use the question callback if available
                try:
                    self.app.call_later(
                        lambda: self.coordination_display._handle_question_submit(question),
                    )
                except Exception as e:
                    self.app.notify(f"Failed to submit follow-up: {e}", severity="error")

        def _copy_to_clipboard(self) -> None:
            """Copy final answer to system clipboard."""
            import platform
            import subprocess

            full_content = "\n".join(self._final_content)
            try:
                system = platform.system()
                if system == "Darwin":  # macOS
                    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    process.communicate(full_content.encode("utf-8"))
                elif system == "Windows":
                    process = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
                    process.communicate(full_content.encode("utf-8"))
                else:  # Linux
                    process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                    process.communicate(full_content.encode("utf-8"))
                self.app.notify(f"Copied {len(self._final_content)} lines to clipboard", severity="information")
            except Exception as e:
                self.app.notify(f"Failed to copy: {e}", severity="error")

        def _open_workspace(self) -> None:
            """Open workspace browser for the winning agent."""
            if not self.coordination_display or not self._winner_agent_id:
                self.app.notify("Cannot open workspace: missing context", severity="warning")
                return

            # Find the app's method to show workspace browser
            try:
                app = self.app
                if hasattr(app, "_show_workspace_browser_for_agent"):
                    app._show_workspace_browser_for_agent(self._winner_agent_id)
                else:
                    self.app.notify("Workspace browser not available", severity="warning")
            except Exception as e:
                self.app.notify(f"Failed to open workspace: {e}", severity="error")

        def _format_vote_summary(self, vote_results: dict[str, Any]) -> str:
            """Condensed vote summary for header."""
            if not vote_results:
                return ""
            mapping = vote_results.get("vote_counts") or {}
            if not mapping:
                return ""
            winner = vote_results.get("winner")
            is_tie = vote_results.get("is_tie", False)
            summary_pairs = ", ".join(f"{aid}:{count}" for aid, count in mapping.items())
            if winner:
                tie_note = " (tie)" if is_tie else ""
                return f"Votes — {summary_pairs}; Winner: {winner}{tie_note}"
            return f"Votes — {summary_pairs}"


def is_textual_available() -> bool:
    """Check if Textual is available."""
    return TEXTUAL_AVAILABLE


def create_textual_display(agent_ids: list[str], **kwargs) -> TextualTerminalDisplay | None:
    """Factory function to create Textual display if available."""
    if not TEXTUAL_AVAILABLE:
        return None
    return TextualTerminalDisplay(agent_ids, **kwargs)
