#!/usr/bin/env python3
"""
MassGen Command Line Interface

A clean CLI for MassGen with file-based configuration support.
Supports both interactive mode and single-question mode.

Usage examples:
    # Use YAML/JSON configuration file
    massgen --config config.yaml "What is the capital of France?"

    # Quick setup with backend and model
    massgen --backend openai --model gpt-4o-mini "What is 2+2?"

    # Interactive mode
    massgen --config config.yaml
    massgen  # Uses default config if available

    # Multiple agents from config
    massgen --config multi_agent.yaml "Compare different approaches to renewable energy"
"""

import argparse
import asyncio
import copy
import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
)

if TYPE_CHECKING:
    from .agent_config import CoordinationConfig
    from .plan_storage import PlanSession

import questionary
import yaml
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agent_config import AgentConfig, TimeoutConfig
from .backend.azure_openai import AzureOpenAIBackend
from .backend.chat_completions import ChatCompletionsBackend
from .backend.claude import ClaudeBackend
from .backend.claude_code import ClaudeCodeBackend
from .backend.codex import CodexBackend
from .backend.copilot import CopilotBackend
from .backend.gemini import GeminiBackend
from .backend.gemini_cli import GeminiCLIBackend
from .backend.grok import GrokBackend
from .backend.inference import InferenceBackend
from .backend.lmstudio import LMStudioBackend
from .backend.response import ResponseBackend
from .chat_agent import ConfigurableAgent, SingleAgent
from .config_builder import ConfigBuilder, normalize_quickstart_config_filename
from .dspy_paraphraser import (
    QuestionParaphraser,
    create_dspy_lm_from_backend_config,
    is_dspy_available,
)
from .frontend.coordination_ui import CoordinationUI
from .logger_config import is_debug_mode as _is_debug_mode
from .logger_config import logger, save_execution_metadata, setup_logging
from .orchestrator import Orchestrator
from .path_handling import AtPathCompleter
from .utils import get_backend_type_from_model

# Session storage is internal state management - HARDCODED, NOT CONFIGURABLE
# Old configs with orchestrator.session_storage are backwards compatible (value ignored)
SESSION_STORAGE = ".massgen/sessions"


# Load environment variables from .env files
def load_env_file():
    """Load environment variables from .env files.

    Search order (later files override earlier ones):
    1. MassGen package .env (development fallback)
    2. User home ~/.massgen/.env (global user config)
    3. User config ~/.config/massgen/.env
    4. Project configs/.env (project-specific, optional)
    5. Current directory .env (project-specific, highest priority)
    """
    # Load in priority order (later overrides earlier)
    load_dotenv(Path(__file__).parent / ".env")  # Package fallback
    load_dotenv(Path.home() / ".massgen" / ".env")  # User global
    load_dotenv(Path.home() / ".config" / "massgen" / ".env")  # User config
    load_dotenv(Path.cwd() / "configs" / ".env")  # Project configs
    load_dotenv()  # Current directory (highest priority)


# Load .env file at module import
load_env_file()


def _quickstart_config_uses_skills(config_path: str | None) -> bool:
    """Return True when a config enables coordination skills."""
    if not config_path:
        return False

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug(f"[Quickstart] Failed to read config for skill check ({config_path}): {e}")
        return False

    if not isinstance(config, dict):
        return False

    orchestrator = config.get("orchestrator", {})
    if not isinstance(orchestrator, dict):
        return False

    coordination = orchestrator.get("coordination", {})
    if not isinstance(coordination, dict):
        return False

    return bool(coordination.get("use_skills", False))


def _ensure_quickstart_skills_ready(
    config_path: str | None,
    install_requested: bool = True,
) -> bool:
    """Install quickstart skill packages when generated config enables skills."""
    if not install_requested:
        logger.info("[Quickstart] Skipping skill package installation by user choice")
        return True

    if not _quickstart_config_uses_skills(config_path):
        return True

    try:
        from .utils.skills_installer import install_quickstart_skills

        return install_quickstart_skills()
    except Exception as e:
        logger.warning(f"[Quickstart] Skill setup failed: {e}")
        return False


def _pull_docker_image_headless() -> bool:
    """Pull default Docker image without interactive prompts.

    Returns:
        True if image was pulled successfully, False otherwise.
    """
    import subprocess

    image = "ghcr.io/massgen/mcp-runtime-sudo:latest"
    try:
        subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            timeout=300,
        )
        return True
    except Exception:
        return False


def _print_headless_quickstart_summary(result: dict) -> None:
    """Print structured, machine-parseable summary of headless quickstart."""
    print(f"\n{'=' * 50}")
    print("MASSGEN HEADLESS QUICKSTART")
    print(f"{'=' * 50}")

    # API Keys
    print("\nAPI Keys:")
    for key_name, available in result.get("api_keys_summary", {}).items():
        status = "available" if available else "not set"
        print(f"  {key_name}: {status}")

    # Selection
    if result.get("backends") and result.get("models"):
        # Multi-backend mode
        pairs = list(zip(result["backends"], result["models"]))
        print(f"\nSelected ({len(pairs)} backends):")
        for b, m in pairs:
            print(f"  {b} / {m}")
    elif result.get("backend") and result.get("model"):
        print(f"\nSelected: {result['backend']} / {result['model']}")
    else:
        print("\nSelected: none (no API keys found)")

    # Config
    if result.get("config_path"):
        print(f"Config: {result['config_path']}")
    elif result.get("env_template_path"):
        print(f"Env template: {result['env_template_path']}")

    # Docker
    docker_status = "available" if result.get("docker_available") else "not available"
    if result.get("docker_pulled"):
        docker_status += ", image pulled"
    print(f"Docker: {docker_status}")

    # Skills
    skills_status = "installed" if result.get("skills_installed") else "not installed"
    print(f"Skills: {skills_status}")

    # Status
    if result["success"]:
        print("\nSTATUS: SUCCESS")
        print("\nRun with:")
        config = result["config_path"]
        print(
            f"  massgen --automation --config {config}" ' "Your question"',
        )
    else:
        print("\nSTATUS: NEEDS_CONFIG")
        for step in result.get("manual_steps", []):
            print(f"  -> {step}")

    print()


def _print_backends_table() -> None:
    """Print a table of all supported backends with models, capabilities, and auth."""
    from massgen.backend.capabilities import BACKEND_CAPABILITIES

    # Column widths
    w_type = 16
    w_name = 22
    w_default = 26
    w_auth = 28
    w_caps = 40

    header = f"{'Backend Type':<{w_type}}" f"{'Provider':<{w_name}}" f"{'Default Model':<{w_default}}" f"{'Auth':<{w_auth}}" f"{'Key Capabilities'}"
    sep = "-" * (w_type + w_name + w_default + w_auth + w_caps)

    print(f"\n{sep}")
    print("MASSGEN SUPPORTED BACKENDS")
    print(f"{sep}\n")
    print(header)
    print(sep)

    for backend_type, caps in sorted(BACKEND_CAPABILITIES.items()):
        # Auth info
        if caps.env_var:
            auth = f"{caps.env_var}"
            # Agent-based backends also support login
            if backend_type in ("claude_code", "codex"):
                auth += " or login"
            elif backend_type == "copilot":
                auth = "GitHub Copilot subscription"
        else:
            auth = "none"

        # Key capabilities (abbreviated)
        cap_list = []
        if "web_search" in caps.supported_capabilities:
            cap_list.append("web")
        if "code_execution" in caps.supported_capabilities:
            cap_list.append("code")
        if caps.filesystem_support == "native":
            cap_list.append("fs-native")
        elif caps.filesystem_support == "mcp":
            cap_list.append("fs-mcp")
        if "mcp" in caps.supported_capabilities:
            cap_list.append("mcp")
        if "reasoning" in caps.supported_capabilities:
            cap_list.append("reasoning")
        if "image_generation" in caps.supported_capabilities:
            cap_list.append("img-gen")
        if "image_understanding" in caps.supported_capabilities:
            cap_list.append("vision")
        cap_str = ", ".join(cap_list) if cap_list else "basic"

        print(
            f"{backend_type:<{w_type}}" f"{caps.provider_name:<{w_name}}" f"{caps.default_model:<{w_default}}" f"{auth:<{w_auth}}" f"{cap_str}",
        )

    print(f"\n{sep}")
    print("MODELS PER BACKEND")
    print(f"{sep}\n")

    for backend_type, caps in sorted(BACKEND_CAPABILITIES.items()):
        models_str = ", ".join(caps.models[:8])
        if len(caps.models) > 8:
            models_str += f" (+{len(caps.models) - 8} more)"
        print(f"  {backend_type}: {models_str}")

    print(f"\n{sep}")
    print(
        "Use with: massgen --quickstart --headless" " --config-backend <type> --config-model <model>",
    )
    print(
        "Mixed providers: massgen --quickstart --headless"
        " --quickstart-agent backend=claude,model=claude-opus-4-6"
        " --quickstart-agent backend=openai,model=gpt-5.4"
        " --quickstart-agent backend=gemini,model=gemini-3-flash-preview",
    )
    print()


def _quickstart_filename_from_config_arg(config_path_arg: str | None) -> str | None:
    """Extract quickstart filename override from --config when --quickstart is used."""
    if not config_path_arg:
        return None

    value = config_path_arg.strip()
    if not value:
        return None

    return normalize_quickstart_config_filename(value)


def _headless_quickstart_output_path_from_config_arg(config_path_arg: str | None) -> str | None:
    """Extract an exact output path for headless quickstart from --config."""
    if not config_path_arg:
        return None

    value = config_path_arg.strip()
    if not value:
        return None

    return str(Path(value).expanduser())


def _parse_quickstart_agent_specs(values: list[str] | None) -> list[dict[str, str | None]]:
    """Parse repeated --quickstart-agent values into explicit agent specs."""
    specs: list[dict[str, str | None]] = []
    if not values:
        return specs

    allowed_keys = {"id", "backend", "type", "model", "reasoning_effort"}
    for raw_value in values:
        spec: dict[str, str | None] = {}
        for item in raw_value.split(","):
            key, sep, value = item.partition("=")
            key = key.strip()
            value = value.strip()
            if not sep or not key or not value:
                raise ValueError(
                    "Each --quickstart-agent value must use key=value pairs, " "for example backend=claude,model=claude-opus-4-6",
                )
            if key not in allowed_keys:
                allowed = ", ".join(sorted(allowed_keys))
                raise ValueError(
                    f"Unsupported --quickstart-agent field '{key}'. " f"Allowed fields: {allowed}",
                )
            spec[key] = value

        if not (spec.get("backend") or spec.get("type")):
            raise ValueError(
                "Each --quickstart-agent requires backend=<type>.",
            )
        specs.append(spec)

    return specs


def _setup_logfire_observability() -> bool:
    """Configure Logfire observability and instrument all LLM providers.

    This sets up structured logging/tracing via Logfire and instruments
    all supported LLM provider clients (OpenAI, Anthropic, Google GenAI).

    Returns:
        True if Logfire was successfully configured, False otherwise.
    """
    try:
        import logfire  # noqa: F401 - Check if logfire is installed
    except ImportError:
        print(
            f"{BRIGHT_YELLOW}⚠️  Logfire not installed. " f"Install with: pip install massgen[observability]{RESET}",
        )
        return False

    from .logger_config import integrate_logfire_with_loguru
    from .structured_logging import configure_observability, get_tracer

    success = configure_observability(enabled=True)
    if not success:
        return False

    integrate_logfire_with_loguru()
    # Instrument all LLM providers globally
    tracer = get_tracer()
    tracer.instrument_google_genai()  # Gemini
    tracer.instrument_openai()  # OpenAI-compatible APIs
    tracer.instrument_anthropic()  # Claude
    return True


# Module-level flag: when True, stdout is reserved for JSONL events
_stream_events_active = False


def _automation_print(msg: str) -> None:
    """Print automation-mode status lines (LOG_DIR, STATUS, OUTPUT_FILE, etc.).

    When event streaming is active, stdout is reserved for JSONL, so these
    lines are routed to stderr instead. Always flush so background processes
    with piped stdout (block-buffered) emit lines immediately.
    """
    print(msg, file=sys.stderr if _stream_events_active else sys.stdout, flush=True)


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


def _apply_orchestrator_runtime_params(
    orchestrator_config: AgentConfig,
    orchestrator_cfg: dict[str, Any] | None,
) -> None:
    """Apply orchestrator-level runtime params from config onto an AgentConfig."""
    if not orchestrator_cfg:
        return

    direct_fields = (
        "voting_sensitivity",
        "voting_threshold",
        "max_new_answers_per_agent",
        "max_new_answers_global",
        "answer_novelty_requirement",
        "fairness_enabled",
        "fairness_lead_cap_answers",
        "max_midstream_injections_per_round",
        "defer_peer_updates_until_restart",
        "allow_midstream_peer_updates_before_checklist_submit",
        "defer_voting_until_all_answered",
        "coordination_mode",
        "presenter_agent",
        "final_answer_strategy",
    )
    for field_name in direct_fields:
        if field_name in orchestrator_cfg:
            setattr(orchestrator_config, field_name, orchestrator_cfg[field_name])

    if "checklist_require_gap_report" in orchestrator_cfg:
        orchestrator_config.checklist_require_gap_report = orchestrator_cfg["checklist_require_gap_report"]
    if "gap_report_mode" in orchestrator_cfg:
        orchestrator_config.gap_report_mode = orchestrator_cfg["gap_report_mode"]
    elif "checklist_require_gap_report" in orchestrator_cfg and "gap_report_mode" not in orchestrator_cfg:
        orchestrator_config.gap_report_mode = "separate" if orchestrator_cfg["checklist_require_gap_report"] else "none"

    if orchestrator_cfg.get("debug_final_answer"):
        orchestrator_config.debug_final_answer = orchestrator_cfg["debug_final_answer"]

    for bool_field in ("skip_final_presentation", "skip_voting", "disable_injection", "skip_coordination_rounds"):
        if bool_field in orchestrator_cfg:
            setattr(orchestrator_config, bool_field, bool(orchestrator_cfg[bool_field]))


def _is_planning_turn(
    mode_state: Any | None,
    cli_plan_enabled: bool = False,
) -> bool:
    """Return True when the current turn is a planning turn."""
    if mode_state and getattr(mode_state, "plan_mode", None) in {"plan", "plan_and_execute"}:
        return True
    return bool(cli_plan_enabled)


def _disable_evaluation_criteria_generation_for_planning(
    coordination_config: Any | None,
) -> bool:
    """Disable dynamic evaluation criteria generation for planning turns.

    Returns True when a config value was changed.
    """
    if coordination_config is None:
        return False

    # YAML/dict config path
    if isinstance(coordination_config, dict):
        ec_cfg = coordination_config.get("evaluation_criteria_generator")
        if not isinstance(ec_cfg, dict):
            return False
        if not ec_cfg.get("enabled", False):
            return False
        ec_cfg["enabled"] = False
        return True

    # Dataclass/object config path
    ec_cfg = getattr(coordination_config, "evaluation_criteria_generator", None)
    if ec_cfg is None:
        return False
    if not getattr(ec_cfg, "enabled", False):
        return False
    ec_cfg.enabled = False
    return True


def _set_planning_checklist_criteria_defaults(
    coordination_config: Any | None,
) -> bool:
    """Set planning-specific checklist preset when no explicit criteria source exists.

    Returns True when checklist_criteria_preset was set to "planning".
    """
    if coordination_config is None:
        return False

    # YAML/dict config path
    if isinstance(coordination_config, dict):
        inline = coordination_config.get("checklist_criteria_inline")
        preset = coordination_config.get("checklist_criteria_preset")
        if inline or preset:
            return False
        coordination_config["checklist_criteria_preset"] = "planning"
        return True

    # Dataclass/object config path
    inline = getattr(coordination_config, "checklist_criteria_inline", None)
    preset = getattr(coordination_config, "checklist_criteria_preset", None)
    if inline or preset:
        return False
    setattr(coordination_config, "checklist_criteria_preset", "planning")
    return True


def _setup_event_streaming() -> None:
    """Configure event streaming to stdout for subprocess-based TUI display.

    When --stream-events is passed, this adds a listener to the EventEmitter
    that writes all events as JSON lines to stdout. This enables parent processes
    (like the TUI subagent modal) to receive real-time updates by reading stdout.

    Events are written in JSONL format (one JSON object per line), flushed
    immediately for real-time streaming.
    """
    global _stream_events_active
    _stream_events_active = True

    from .events import get_event_emitter

    def stream_to_stdout(event):
        """Write event as JSON line to stdout."""
        sys.stdout.write(event.to_json() + "\n")
        sys.stdout.flush()

    # Get the event emitter (initialized by setup_logging)
    emitter = get_event_emitter()
    if emitter:
        emitter.add_listener(stream_to_stdout)


def _setup_timeline_event_recording() -> None:
    """Emit timeline_entry events derived from streaming events (env-gated)."""
    import os

    if not os.environ.get("MASSGEN_TUI_TIMELINE_EVENTS"):
        return

    from .events import get_event_emitter
    from .frontend.displays.timeline_event_recorder import TimelineEventRecorder

    emitter = get_event_emitter()
    if not emitter:
        return

    def emit_line(line: str) -> None:
        emitter.emit_raw("timeline_entry", line=line)

    recorder = TimelineEventRecorder(emit_line)

    def record_event(event):
        try:
            recorder.handle_event(event)
        except Exception:
            pass

    emitter.add_listener(record_event)

    try:
        import atexit

        atexit.register(recorder.flush)
    except Exception:
        pass


# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Color constants for terminal output
BRIGHT_CYAN = "\033[96m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_RED = "\033[91m"
BRIGHT_WHITE = "\033[97m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Exit code constants for automation mode
EXIT_SUCCESS = 0  # Coordination completed successfully
EXIT_CONFIG_ERROR = 1  # Configuration or validation error
EXIT_EXECUTION_ERROR = 2  # Agent failure, API error, or execution error
EXIT_TIMEOUT = 3  # Orchestrator or agent timeout
EXIT_INTERRUPTED = 4  # KeyboardInterrupt (Ctrl+C)

# Custom questionary style for polished selection interface
MASSGEN_QUESTIONARY_STYLE = Style(
    [
        ("qmark", "fg:#00d7ff bold"),  # Bright cyan question mark
        ("question", "fg:#ffffff bold"),  # White question text
        ("answer", "fg:#00d7ff bold"),  # Bright cyan answer
        ("pointer", "fg:#00d7ff bold"),  # Bright cyan pointer (▸)
        ("highlighted", "fg:#00d7ff bold"),  # Bright cyan highlighted option
        ("selected", "fg:#00ff87"),  # Bright green selected
        ("separator", "fg:#6c6c6c"),  # Gray separators
        ("instruction", "fg:#808080"),  # Gray instructions
        ("text", "fg:#ffffff"),  # White text
        ("disabled", "fg:#6c6c6c italic"),  # Gray disabled
    ],
)


def _build_coordination_ui(ui_config: dict[str, Any]) -> CoordinationUI:
    """Create a CoordinationUI with display_kwargs passthrough (incl. theme)."""
    display_kwargs = dict(ui_config.get("display_kwargs", {}) or {})
    theme = ui_config.get("theme")
    if theme is not None and "theme" not in display_kwargs:
        display_kwargs["theme"] = theme
    if ui_config.get("automation_mode"):
        display_kwargs["automation_mode"] = True
    if ui_config.get("skip_agent_selector"):
        display_kwargs["skip_agent_selector"] = True

    return CoordinationUI(
        display_type=ui_config.get("display_type", "textual_terminal"),
        logging_enabled=ui_config.get("logging_enabled", True),
        enable_final_presentation=True,  # Ensures final presentation is generated/saved
        **display_kwargs,
    )


def _restore_terminal_for_input() -> None:
    """Restore terminal settings to a known good state for input().

    This is needed after Rich display cancellation, which can leave
    the terminal in a non-canonical mode.
    """
    try:
        import sys

        if sys.stdin.isatty():
            try:
                import termios

                # Get current settings
                current = termios.tcgetattr(sys.stdin.fileno())
                # Enable echo and canonical mode (required for input())
                current[3] = current[3] | termios.ECHO | termios.ICANON
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, current)
                # Flush any pending input
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except ImportError:
                pass  # termios not available (Windows)
    except Exception:
        pass  # Best effort


def _format_chunk_target_line(target_chunks: int | None) -> str:
    """Return chunk guidance text for planning/spec prompts."""
    if target_chunks == 1 or target_chunks is None:
        return "- Target chunks: exactly 1"
    if target_chunks > 1:
        return f"- Target chunks: around {target_chunks}"
    return "- Target chunks: exactly 1"


def should_include_quick_edit_hint(planning_turn_mode: str | None) -> bool:
    """Show quick-edit hint only for explicit single-turn refinement mode."""
    return planning_turn_mode == "single"


def get_task_planning_prompt_prefix(
    plan_depth: str = "dynamic",
    target_steps: int | None = None,
    target_chunks: int | None = None,
    enable_subagents: bool = False,
    broadcast_mode: Literal["human", "agents"] | bool = False,
    thoroughness: str = "standard",
) -> str:
    """Generate the user prompt prefix for task planning mode.

    This prefix is prepended to the user's question when --plan mode is active.
    It instructs agents to interactively create structured feature lists.

    Args:
        plan_depth: One of "dynamic", "shallow", "medium", or "deep" controlling task granularity.
        target_steps: Optional explicit target number of tasks (None = dynamic sizing).
        target_chunks: Optional explicit target number of chunks (None = default single-chunk planning).
        enable_subagents: Whether subagents are enabled for research tasks.
        broadcast_mode: One of "human", "agents", or False. Controls whether ask_others() is available.
        thoroughness: One of "standard" or "thorough" controlling strategic reasoning depth.

    Returns:
        The prompt prefix string to prepend to the user's question.
    """
    depth_config = {
        "dynamic": {"target": "dynamic", "detail": "scope-adaptive granularity"},
        "shallow": {"target": "5-10", "detail": "high-level phases only"},
        "medium": {"target": "20-50", "detail": "sections with tasks"},
        "deep": {"target": "100-200+", "detail": "granular step-by-step"},
    }
    normalized_depth = plan_depth if plan_depth in depth_config else "dynamic"
    cfg = depth_config[normalized_depth]

    if target_steps is not None and target_steps > 0:
        task_target_line = f"- Target tasks: around {target_steps}"
    elif normalized_depth == "dynamic":
        task_target_line = "- Target tasks: dynamic based on scope complexity"
    else:
        task_target_line = f"- Target tasks: {cfg['target']}"

    chunk_target_line = _format_chunk_target_line(target_chunks)

    # Thoroughness section (controls strategic reasoning depth)
    thoroughness_section = ""
    if thoroughness == "thorough":
        thoroughness_section = """
## Thoroughness: THOROUGH

You are striving for excellence — in both the quality of your strategic \
reasoning and the originality of your approach. Do not accept a plan that \
is merely complete or structurally sound. A thorough plan is one where \
every major decision reflects deep understanding of the problem, where \
the chosen direction is genuinely the strongest option (not just the \
first or safest), and where the resulting work would impress someone who \
knows this domain well.

**Quality bar:** Standard is not enough. Push past the obvious approach. \
If your plan could have been written by someone who spent 5 minutes on \
the problem, it's not thorough. Invest the time to understand what \
separates excellent work from adequate work in this specific domain, and \
let that understanding shape every task.

**Required auxiliary depth:**
- `research/` — analyze the problem domain, audience, competitive landscape, \
and what distinguishes excellent results from adequate ones in this space
- `framework/` — document your strategic choices: why this approach over \
alternatives, what anti-patterns to avoid, what principles should guide \
execution. Name specific failure modes and how to prevent them
- `risks/` — identify what could go wrong, what assumptions are most fragile, \
and what the pivot strategy is if key assumptions fail

**Plan structure expectations:**
- Separate strategic decisions from implementation details. Early tasks should \
establish the strategic foundation (audience, narrative, design principles, \
interaction strategy) before any section-level work begins
- Creative and architectural direction should be exploratory tasks with \
success criteria, not deterministic tasks with locked-in values
- Evolution hooks should question the fundamental direction, not just tweak \
parameters within it
- The plan should tell a coherent story about WHY this approach will produce \
excellent results — an evaluator should be able to read the auxiliary docs \
and understand the reasoning behind every major decision
"""

    # Subagent research section (only if enabled)
    subagent_section = ""
    if enable_subagents:
        subagent_section = """
## Research with Subagents

You have subagents available for research. Use them to:
- Investigate specific areas of the codebase in parallel
- Research technical options or dependencies
- Explore integration points with existing code
- Gather information to inform scope decisions

Spawn subagents for research tasks before finalizing your plan.
"""

    # Conditional scope confirmation section based on broadcast mode
    if broadcast_mode == "human":
        scope_section = """### 1. Scope Confirmation (REQUIRED FIRST)

Before any deep research, analyze the request and verify scope with the user.

**Step 1: Categorize requirements and assumptions**

Parse the user's request into three categories:

1. **Explicitly Stated** - Things the user directly mentioned
   - Example: "Build a REST API" → User said "REST API"

2. **Critical Assumptions** - High-level decisions that affect scope/direction (NEED HUMAN VERIFICATION)
   - User intent or business logic
   - Major architectural choices (monolith vs microservices, SQL vs NoSQL)
   - Security/compliance requirements
   - Feature scope boundaries
   - Example: "Build a REST API" → Is this for internal use or public? What data sensitivity?

3. **Technical/Implementation Assumptions** - Lower-level choices (AGENT CONSENSUS via voting)
   - Specific technologies/frameworks
   - Code organization patterns
   - Standard practices (error handling, logging, validation)
   - Example: "Build a REST API" → Express vs FastAPI, JWT details, specific DB choice

**Step 2: Verify ONLY THE MOST CRITICAL assumptions with human**

Be selective - only ask about assumptions where you truly cannot make a good decision without human input.

**When to ask the human**:
- User intent is ambiguous (internal tool vs public product?)
- Business/domain knowledge required (compliance, data sensitivity)
- Major scope decisions (which features are in/out?)
- Trade-offs that depend on user priorities (speed vs security vs cost)

**When NOT to ask the human** (let consensus decide):
- Technical implementation details (framework, database, auth method)
- Standard practices (error handling, logging, testing approach)
- Scope refinements that you can revisit after initial consensus
- Decisions where you can make a reasonable recommendation

**IMPORTANT**: When you DO ask, offer recommendations with reasoning:

GOOD (selective + recommendations):
```
I need to clarify scope before planning this REST API:

1. **Usage context**: Is this for internal use or public-facing?
   - Recommendation: I'll assume internal unless you specify, which means simpler auth and fewer rate limits

2. **Data sensitivity**: What type of data will this handle?
   - Recommendation: I'll plan for standard business data (not public, not highly sensitive) unless you need HIPAA/PCI compliance

3. **Integration needs**: Do you have existing systems this must integrate with?
   - If yes, please specify - this affects the approach significantly

Let me know if my assumptions are wrong or if there are other critical requirements.
```

BAD (asking everything):
```
Should I use Express or FastAPI?
Should I use JWT or OAuth?
Should I use PostgreSQL or MongoDB?
Which testing framework?
How should I structure the code?
```

**Step 3: Document technical assumptions and recommendations for consensus**

For technical/implementation assumptions, present your recommendations with reasoning in your answer.

**Be opinionated**: Make specific technical recommendations based on:
- The user's explicit requirements
- Industry best practices
- Your analysis of the codebase (if extending existing project)
- Trade-offs you've considered

Other agents will:
- Propose alternative approaches if they disagree
- Challenge your technical choices with their reasoning
- Refine scope to keep tasks focused and useful
- Vote when they're happy with the combination of choices

**Benefits of consensus**:
- Explores wider design space through agent debate
- Ensures all tasks are critical and actively useful
- Prevents scope divergence through multi-agent validation
- Catches assumptions one agent might miss

**Note**: You can always ask the human for clarification in later rounds after seeing consensus. Start with your best recommendations, refine through voting, then verify critical decisions if needed.

**Step 4: Feature scope (with recommendations)**

If the request contains **multiple distinct features**, recommend which to prioritize:

GOOD (scoped recommendation):
```
I see this request involves three main features:
1. User authentication (CORE - needed for everything else)
2. Todo CRUD operations (CORE - primary functionality)
3. Email notifications (NICE-TO-HAVE - can add later)

Recommendation: Let's scope this planning session to features 1-2, then add notifications in a follow-up. Does that work?
```

BAD (asking without recommendation):
```
This has multiple features. Which ones do you want?
```

**After critical verification (minimal ask_others calls), proceed to research. Technical assumptions and scope refinements will be refined through voting.**"""
    else:
        # No human interaction - agents make all decisions through consensus
        scope_section = """### 1. Scope Analysis (REQUIRED FIRST)

Before any deep research, analyze the request and make decisions through agent consensus.

**Step 1: Categorize requirements and assumptions**

Parse the user's request into three categories:

1. **Explicitly Stated** - Things the user directly mentioned
   - Example: "Build a REST API" → User said "REST API"

2. **Critical Assumptions** - High-level decisions that affect scope/direction
   - User intent or business logic
   - Major architectural choices (monolith vs microservices, SQL vs NoSQL)
   - Security/compliance requirements
   - Feature scope boundaries
   - Example: "Build a REST API" → Assume internal use or public-facing?

3. **Technical/Implementation Assumptions** - Lower-level choices
   - Specific technologies/frameworks
   - Code organization patterns
   - Standard practices (error handling, logging, validation)
   - Example: "Build a REST API" → Express vs FastAPI, JWT details, specific DB choice

**Step 2: Make opinionated recommendations for ALL assumptions**

Since you don't have human interaction, you MUST make decisions autonomously.

**Be opinionated**: Make specific recommendations for ALL assumptions based on:
- The user's explicit requirements
- Industry best practices
- Your analysis of the codebase (if extending existing project)
- Trade-offs you've considered
- Reasonable defaults when ambiguous

**Document your reasoning**: For each assumption, explain WHY you chose that approach.

Example:
```
I'm making these decisions for this REST API:

1. **Usage context**: Internal use (simpler auth, no rate limiting needed)
   - Reasoning: No mention of public users, so assuming internal tooling

2. **Data sensitivity**: Standard business data (moderate security)
   - Reasoning: No compliance requirements mentioned, so standard practices

3. **Tech stack**: FastAPI + PostgreSQL + JWT
   - Reasoning: FastAPI for async support, PostgreSQL for reliability, JWT for stateless auth

4. **Scope**: Core features only (auth + CRUD), no notifications yet
   - Reasoning: Start with MVP, can add features later
```

**Step 3: Refine through consensus**

Other agents will:
- Propose alternative approaches if they disagree
- Challenge your assumptions with their reasoning
- Suggest different scope boundaries
- Vote when they're happy with the combination of choices

**Benefits of consensus**:
- Explores wider design space through agent debate
- Ensures all tasks are critical and actively useful
- Prevents scope divergence through multi-agent validation
- Catches assumptions one agent might miss

**Critical**: ALL decisions must be made through consensus. No human will verify them, so agents must carefully debate and validate each choice.

**After consensus is reached, proceed to research. All assumptions and scope will be refined through voting.**"""

    return f"""# TASK PLANNING MODE

You are in task planning mode. Your goal is to **interactively** create a comprehensive task plan.

## CRITICAL: PLANNING ONLY - DO NOT BUILD THE DELIVERABLE

**YOU ARE A PLANNER, NOT AN EXECUTOR.**

- **DO NOT** create the actual deliverable (no final code, no implementations)
- **DO NOT** execute the user's task - only plan it
- **DO** create `project_plan.json` listing tasks that a FUTURE agent will execute
- **DO** research and explore to understand the task scope

**Allowed files:**
1. `project_plan.json` - the task list for future execution (REQUIRED)
2. Supporting docs - requirements, design decisions, technical approach
3. Scratch/research files - scripts to parse data, analyze structure, gather info FOR PLANNING
4. `prototypes/` - rough proof-of-concept artifacts for exploratory tasks (see Mini-Prototyping below)

**NOT allowed:**
- The actual deliverable the user requested (SVG, website, app, final code, etc.)
- Implementation code that would be the end product

If you find yourself building what the user asked for - STOP. You're only planning it.
A different agent will execute this plan later.

### Mini-Prototyping for Exploratory Tasks

For tasks classified as `exploratory` (see Task Type Classification below), \
you MAY create rough proof-of-concept artifacts to validate assumptions:
- **Visual tasks**: a rough SVG sketch, wireframe, or color palette test
- **Code tasks**: a minimal spike proving the algorithm or approach works
- **Writing tasks**: a paragraph sample testing voice or tone

Store prototypes in `prototypes/` alongside the plan. They validate \
assumptions — they are NOT deliverables. Reference which assumptions each \
prototype validated or invalidated in the plan's auxiliary files.

**When to prototype**: when the plan's success depends on an assumption you \
can't verify by reasoning alone (e.g., "will this visual approach render \
well in SVG?" or "does this algorithm scale?"). When in doubt, prototype.

## Planning Process

Follow this process in order:

{scope_section}

### 2. Research & Exploration
Once scope is confirmed:
- Explore the codebase to understand existing structure
- Investigate integration points
- Identify potential technical challenges{subagent_section}

### 3. Clarifying Questions
As you research, ask follow-up questions about:
- Edge cases and error handling expectations
- Performance or security requirements
- User experience preferences
- Anything ambiguous you discovered

### 4. Plan Creation
Only after scope confirmation and sufficient research:
- Create the feature list at the specified depth
- Organize features by logical grouping
- If multiple distinct features exist, consider separate spec files

## Output Requirements

1. **Primary artifact**: `project_plan.json` - Write this file using file write tools:
   - If `deliverable/` folder exists in your workspace, put it there: `deliverable/project_plan.json`
   - Otherwise, put it in your workspace root: `project_plan.json`
2. **Auxiliary files** (optional, organized into purpose-driven subdirectories):
   - `research/` — background research, prior art, feasibility analysis, codebase exploration notes
   - `framework/` — architecture decisions, technology choices with rationale, design patterns selected
   - `risks/` — risk register, mitigation strategies, dependency analysis
   - `requirements/` — user stories, acceptance criteria, requirements docs
   - `prototypes/` — quick proof-of-concept artifacts for exploratory tasks (see Mini-Prototyping)
   Auxiliary files support the plan but are NOT the plan — `project_plan.json` is always the source of truth.

**IMPORTANT**: Write `project_plan.json` directly as a file. Do NOT use MCP planning tools
(create_task_plan, update_task_status, etc.) to create this deliverable - those tools are for
tracking your own internal work progress, not for creating the project plan deliverable.

## Planning Principles

**Focus on outcomes, not implementation details.** Describe WHAT the final product needs, not HOW to build it. Implementation choices happen during execution.

**Show strategic depth, not just task structure.** A good plan demonstrates \
that you deeply understood the problem before breaking it into tasks. \
Before specifying tasks, reason about the problem space: who is this for, \
what impression or experience matters most, what distinguishes an excellent \
result from a competent one? Capture this reasoning in auxiliary files \
(research/, framework/, decisions/) and let it drive task design. If your \
plan reads like a generic template with project-specific nouns swapped in, \
it lacks the specificity that produces excellent results. Each major \
decision should have rationale tied to the actual problem context — not \
just "best practice" or "modern trend."

**Think about final product quality:**
- If it's visual, it should LOOK good - include quality visuals, not just code
- If it produces output, that output should be polished and professional
- Consider what a user/viewer would actually experience

**Verification should test the PRODUCT FIRST, then source code:**
1. Does the final product work? (run it, use it, see it)
2. Does it look/feel right? (visual quality, UX)
3. Only then: is the code correct? (builds, tests pass)

**Your JSON output IS the iteration surface.** Prefer tightening existing \
tasks — sharpen descriptions, add missing verification, fix dependency \
ordering — over adding new tasks or prose. Adding tasks to fill genuine \
gaps is fine; adding tasks that don't serve a clear purpose is not.

**Question your own direction.** Your first approach is a hypothesis, not \
a commitment. When iterating, don't just polish the current direction — \
challenge whether it's the right direction. Ask: is this the strongest \
approach, or just the first one I reached for? Would a different \
architecture, structure, or creative direction produce a fundamentally \
better result? A sophisticated plan isn't one that executes a safe idea \
thoroughly — it's one that identifies the most promising direction and \
specifies it with enough depth and detail that the executor can build \
something genuinely impressive.

**Tasks should be achievable with the available tools.** Executing agents will have access to the configured tools and will figure out how to use them.
{thoroughness_section}
## Task Type Classification

Every task MUST be classified as `deterministic` or `exploratory`:

**Deterministic tasks**:
- Have a single correct implementation path
- Can be fully specified upfront (data schemas, API contracts, configs, build setup)
- Verification is binary: it works or it doesn't
- The plan specifies WHAT + HOW in detail

**Exploratory tasks**:
- Have multiple valid approaches where the best one emerges through iteration
- Cannot be fully specified upfront because quality is subjective or context-dependent
- Verification requires qualitative assessment (render it, read it, experience it)
- The plan specifies **success criteria + constraints**, NOT implementation steps
- The executor has explicit permission to exceed or diverge from the plan when \
they discover something better
- MUST include `success_criteria`: 2-4 concrete criteria for what "good" looks \
like (not how to get there)
- SHOULD include `evolution_hooks` in metadata: what discoveries during \
implementation should trigger a plan revision

**Classification test**: "If two competent engineers followed this task \
independently, would they produce essentially the same output?" \
Yes -> deterministic. No -> exploratory.

## Plan Evolution Protocol

Plans are hypotheses, not contracts. Include explicit mechanisms for evolution:

**Discovery annotations**: for each chunk, note:
- What assumptions could this chunk invalidate?
- What would you learn during execution that you can't know now?
- If this chunk reveals the approach is wrong, what's the pivot?

**Evaluation integration points**: mark tasks where evaluation should be \
invoked mid-execution by adding `"eval_checkpoint": true` to the task's \
metadata. Place these at:
- After the first exploratory chunk completes (early signal on approach viability)
- After any chunk whose `evolution_hooks` flag high-risk assumptions
- Before the final polish chunk (ensure the foundation is worth polishing)

## Task List Format
Write `project_plan.json` with this structure:
```json
{{
  "tasks": [
    {{
      "id": "F001",
      "chunk": "C01_foundation",
      "task_type": "deterministic|exploratory",
      "description": "Feature Name - What this feature accomplishes and the expected outcome",
      "status": "pending",
      "depends_on": ["F000"],
      "priority": "high|medium|low",
      "success_criteria": ["Only for exploratory tasks: what good looks like, not how to get there"],
      "metadata": {{
        "verification": "How to verify this task is complete",
        "verification_method": "Output-first verification approach",
        "verification_group": "optional_group_name",
        "evolution_hooks": ["Discoveries during this task that should trigger plan revision"],
        "eval_checkpoint": false
      }}
    }}
  ]
}}
```

### Required Chunking Rules
- Every task **MUST** include a non-empty `chunk` string.
- Use ordered chunk labels (for example: `C01_foundation`, `C02_backend`, `C03_ui`).
- Dependencies must not point to future chunks.
- Keep chunk order deterministic by using consistent, increasing labels.
- Respect the chunk target guidance below while preserving a valid dependency DAG.

### Metadata Fields (Optional but Recommended)
- **verification**: What to check - testable completion criteria (e.g., "Homepage displays correctly", "API returns 200")
- **verification_method**: Output-first verification approach. Start with user-visible checks (run it, click through it, inspect the rendered/output result), then add automated checks where useful.
- **verification_group**: Group related tasks for batch verification (e.g., "foundation", "frontend_ui", "api_endpoints").
  During execution, tasks are marked `completed` then later `verified` in groups.

## Planning Size Controls
- Depth mode: {normalized_depth.upper()}
{task_target_line}
{chunk_target_line}
- Detail level: {cfg["detail"]}

## Quality Criteria
- Each task should be independently verifiable
- Dependencies (depends_on) should form a valid DAG (no cycles)
- Descriptions must include both WHAT and HOW — not just "Create hero \
section" but specific layout, content, and behavior. A developer reading \
the task should know what to build without asking questions
- Where tasks connect or produce artifacts consumed by other tasks, \
specify interface contracts: data shapes, file conventions, API \
signatures. Independent execution should not require reverse-engineering \
unstated agreements
- Scope should be confirmed with user before detailed planning
- Verification criteria should be testable and specific
- Use verification_group to batch related tasks (e.g., verify all pages after building them)
- For user-facing tasks, include at least one verification step that checks the actual user-visible output
- Prefer tightening existing tasks over adding new ones. Growth is fine when filling genuine gaps; growth without clear purpose is sprawl

---

USER'S REQUEST:
"""


def get_spec_creation_prompt_prefix(
    broadcast_mode: "Literal['human', 'agents'] | bool" = False,
    target_chunks: int | None = None,
) -> str:
    """Generate the user prompt prefix for spec creation mode.

    This prefix is prepended to the user's question when --spec mode is active.
    It instructs agents to create a structured requirements specification using
    EARS notation (Easy Approach to Requirements Syntax).

    Args:
        broadcast_mode: One of "human", "agents", or False.
            Controls whether ask_others() is available for scope confirmation.
        target_chunks: Optional target number of execution chunks.

    Returns:
        The prompt prefix string to prepend to the user's question.
    """
    chunk_target_line = _format_chunk_target_line(target_chunks)

    # Scope section reuses the same human vs autonomous pattern as plan mode
    if broadcast_mode == "human":
        scope_section = """\
### 1. Scope Confirmation (REQUIRED FIRST)

Before any deep research, analyze the request and verify scope with the user.

**Categorize the request** into:
1. **Explicitly Stated** - What the user directly mentioned
2. **Critical Assumptions** - High-level decisions needing human verification \
(intent, architecture, compliance, scope boundaries)
3. **Technical Assumptions** - Lower-level choices for agent consensus \
(frameworks, patterns, practices)

**Ask the human** only about critical assumptions where you cannot make a \
good decision without input. Offer recommendations with reasoning.

**After critical verification, proceed to research.**"""
    else:
        scope_section = """\
### 1. Scope Analysis (REQUIRED FIRST)

Before any deep research, analyze the request and make decisions \
through agent consensus.

**Categorize the request** into:
1. **Explicitly Stated** - What the user directly mentioned
2. **Critical Assumptions** - High-level decisions (intent, architecture, \
compliance, scope boundaries)
3. **Technical Assumptions** - Lower-level choices (frameworks, patterns, \
practices)

**Make opinionated recommendations** for ALL assumptions with reasoning. \
Other agents will challenge, refine, and vote on consensus.

**After consensus is reached, proceed to research.**"""

    return f"""\
# SPEC CREATION MODE

You are in spec creation mode. Your goal is to **interactively** create \
a structured requirements specification.

## CRITICAL: SPEC ONLY - DO NOT BUILD THE DELIVERABLE

**YOU ARE A SPEC WRITER, NOT AN EXECUTOR.**

- **DO NOT** create the actual deliverable (no final code, no implementations)
- **DO NOT** execute the user's task - only specify it
- **DO** create `project_spec.json` with requirements that a FUTURE agent \
will implement
- **DO** research and explore to understand the task scope

**Allowed files:**
1. `project_spec.json` - the requirements specification (REQUIRED)
2. Supporting docs - design decisions, technical context, user stories
3. Scratch/research files - scripts to parse data, analyze structure, \
gather info FOR SPEC WRITING

**NOT allowed:**
- The actual deliverable the user requested (code, website, app, etc.)
- Implementation code that would be the end product

If you find yourself building what the user asked for - STOP. \
You're only specifying it. A different agent will implement this spec later.

## Spec Process

Follow this process in order:

{scope_section}

### 2. Research & Exploration
Once scope is confirmed:
- Explore the codebase to understand existing structure
- Investigate integration points
- Identify potential technical challenges

### 3. Clarifying Questions
As you research, ask follow-up questions about:
- Edge cases and error handling expectations
- Performance or security requirements
- User experience preferences
- Anything ambiguous you discovered

### 4. Spec Creation
Only after scope confirmation and sufficient research:
- Create the requirements specification
- Use EARS notation for each requirement
- Group requirements into execution chunks
- Include verification criteria for each requirement

## Output Requirements

1. **Primary artifact**: `project_spec.json` - Write this file using \
file write tools:
   - If `deliverable/` folder exists in your workspace, put it there: \
`deliverable/project_spec.json`
   - Otherwise, put it in your workspace root: `project_spec.json`
2. **Auxiliary files** (optional, organized into purpose-driven subdirectories):
   - `research/` — domain analysis, user research, competitive analysis, prior art
   - `design/` — system design notes, data models, API contracts, integration points
   - `decisions/` — architectural decision records (ADRs), trade-off analyses
   - `requirements/` — user stories, acceptance criteria, persona descriptions
   Auxiliary files support the spec but are NOT the spec — `project_spec.json` \
is always the source of truth.

**IMPORTANT**: Write `project_spec.json` directly as a file. Do NOT use \
MCP planning tools (create_task_plan, update_task_status, etc.) to create \
this deliverable.

**Show strategic depth, not just requirements structure.** A good spec \
demonstrates that you deeply understood the problem before writing \
requirements. Reason about the problem space: who is this for, what \
experience matters most, what distinguishes an excellent result from a \
competent one? Capture this reasoning in auxiliary files (research/, \
design/, decisions/) and let it drive requirement design. If your spec \
reads like a generic template with project-specific nouns swapped in, it \
lacks the specificity that produces excellent results.

**Your JSON output IS the iteration surface.** Prefer tightening existing \
requirements — sharpen EARS statements, add missing verification, \
resolve ambiguities — over adding new requirements or prose. Adding \
requirements to fill genuine gaps is fine; adding them without clear \
purpose is not.

**Question your own direction.** Your first approach is a hypothesis, not \
a commitment. When iterating, don't just polish the current spec — \
challenge whether the underlying design direction is the right one. Ask: \
is this the strongest approach, or just the first one I reached for? \
Would a different architecture, interaction model, or system design \
produce a fundamentally better result? A strong spec identifies the most \
promising direction and specifies it with enough depth that the executor \
can build something genuinely excellent.

## EARS Notation

Use the **Easy Approach to Requirements Syntax** (EARS) for each \
requirement's `ears` field:
- **Event-driven**: WHEN <trigger> THE SYSTEM SHALL <response>
- **State-driven**: WHILE <state> THE SYSTEM SHALL <behavior>
- **Unwanted behavior**: IF <condition> THEN THE SYSTEM SHALL <response>
- **Optional**: WHERE <feature> THE SYSTEM SHALL <behavior>

Examples:
- WHEN user submits login form THE SYSTEM SHALL validate credentials \
and return a session token
- WHILE server load exceeds 80% THE SYSTEM SHALL reject new connections \
with 503 status
- IF database connection fails THEN THE SYSTEM SHALL retry with \
exponential backoff up to 3 times

## Spec Format
Write `project_spec.json` with this structure:
```json
{{{{
  "feature": "Feature Name",
  "overview": "2-3 sentence description of what this feature accomplishes",
  "requirements": [
    {{{{
      "id": "REQ-001",
      "chunk": "C01_core",
      "title": "Short descriptive title",
      "priority": "P0|P1|P2",
      "type": "functional|non-functional",
      "ears": "WHEN <trigger> THE SYSTEM SHALL <response>",
      "rationale": "Why this requirement exists",
      "verification": "How to verify this requirement is met",
      "depends_on": ["REQ-000"]
    }}}}
  ]
}}}}
```

### Required Chunking Rules
- Every requirement **MUST** include a non-empty `chunk` string.
- Use ordered chunk labels (for example: `C01_core`, `C02_api`, \
`C03_frontend`).
- Dependencies must not point to future chunks.
- Keep chunk order deterministic by using consistent, increasing labels.
- Respect the chunk target guidance below while preserving a valid \
dependency DAG.

### Field Descriptions
- **id**: Unique requirement identifier (REQ-001, REQ-002, etc.)
- **chunk**: Execution phase grouping (C01_core, C02_api, etc.)
- **title**: Short descriptive title for the requirement
- **priority**: P0 (critical), P1 (important), P2 (nice-to-have)
- **type**: "functional" (what it does) or "non-functional" \
(how well it does it)
- **ears**: EARS-formatted requirement statement
- **rationale**: Why this requirement exists - the "why" behind the "what"
- **verification**: Testable criteria to verify the requirement is met
- **depends_on**: List of requirement IDs this depends on

## Spec Size Controls
{chunk_target_line}
- Requirements should be specific enough to implement and verify

## Quality Criteria
- Each requirement should be independently verifiable
- Dependencies (depends_on) should form a valid DAG (no cycles)
- EARS statements should be unambiguous and testable — a single behavior per requirement
- Scope should be confirmed with user before detailed spec writing
- Verification criteria should be specific and measurable
- Rationale should explain the business or technical reason
- Prefer tightening existing requirements over adding new ones. Growth is fine when filling genuine gaps; growth without clear purpose is sprawl

---

USER'S REQUEST:
"""


def build_plan_review_refinement_appendix(
    *,
    question: str,
    planning_feedback: str,
    include_quick_edit_hint: bool,
) -> str:
    """Build optional prompt appendix for planning-review refinement turns.

    Avoids duplicating feedback blocks when the current question already embeds
    plan-review feedback text (common when users include it directly).
    """
    sections: list[str] = []

    feedback = (planning_feedback or "").strip()
    normalized_question = " ".join((question or "").lower().split())
    normalized_feedback = " ".join(feedback.lower().split())

    feedback_already_present = False
    if feedback:
        if normalized_feedback and normalized_feedback in normalized_question:
            feedback_already_present = True
        elif "plan review feedback" in normalized_question:
            feedback_already_present = True

    if feedback and not feedback_already_present:
        sections.append(
            "## Plan Review Feedback\n" f"{feedback}\n\n" "Apply this feedback while keeping a valid chunk-labeled task DAG.",
        )

    if include_quick_edit_hint:
        sections.append(
            "## Quick Edit Planning Turn\n" "Make precise updates and preserve valid chunk/dependency structure.",
        )

    return "\n\n".join(sections)


def _load_skill_creator_reference() -> str:
    """Load the skill-creator SKILL.md for prompt inclusion."""
    try:
        path = Path(".agent") / "skills" / "skill-creator" / "SKILL.md"
        return path.read_text(encoding="utf-8")
    except Exception:
        # Minimal fallback if file is missing
        return "---\nname: descriptive-skill-name\n" "description: Clear explanation of what this workflow does\n---\n" "# Skill Name\n\n## Purpose\n## Workflow\n"


def _get_log_session_original_query(log_dir: str | None) -> str | None:
    """Extract the original user query from a log session's status.json.

    Args:
        log_dir: Path to the log session directory.

    Returns:
        The original query string, or None if not found.
    """
    if not log_dir:
        return None
    import json

    log_path = Path(log_dir)
    for status_path in sorted(log_path.glob("turn_*/attempt_*/status.json")):
        try:
            data = json.loads(status_path.read_text())
            question = data.get("meta", {}).get("question", "")
            if question:
                return question.strip()
        except Exception:
            continue
    return None


def get_log_analysis_prompt_prefix(
    log_dir: str | None,
    turn: int | None,
    profile: str = "dev",
    skill_lifecycle_mode: str = "create_or_update",
) -> str:
    """Generate the user prompt prefix for Textual analysis mode.

    Args:
        log_dir: Selected log session directory path, or None for auto/current.
        turn: Selected turn number, or None for latest available turn.
        profile: Analysis profile ("dev" or "user").

    Returns:
        Prefix instructions to prepend to the user's question.
    """
    from massgen.filesystem_manager.skills_manager import normalize_skill_lifecycle_mode

    normalized_profile = profile if profile in ("dev", "user") else "dev"
    normalized_lifecycle_mode = normalize_skill_lifecycle_mode(skill_lifecycle_mode)
    target_log = log_dir or "auto-select current/latest log session"
    target_turn = f"turn_{turn}" if turn is not None else "latest available turn"

    original_query = _get_log_session_original_query(log_dir)
    original_query_section = ""
    if original_query:
        original_query_section = f"""- Original task: {original_query}
"""

    if normalized_profile == "user":
        skill_creator_ref = _load_skill_creator_reference()
        lifecycle_instructions = {
            "create_or_update": """- Lifecycle mode: create_or_update (default).
- First look for the best existing skill in `.agent/skills/` and update it when it matches the same domain workflow.
- Only create a new skill if no existing skill is a strong match.
""",
            "create_new": """- Lifecycle mode: create_new.
- Always create a new skill directory in `.agent/skills/`.
- Do not modify existing skills in this mode.
""",
        }.get(normalized_lifecycle_mode, "")
        profile_section = f"""## Profile Focus: USER (skills-first)

Primary objective:
- Read the logs from this run to understand what workflow was executed and how.
- Distill the workflow into a single reusable skill that lets someone repeat or adapt it.

IMPORTANT constraints:
- Create exactly ONE skill unless the run covered genuinely distinct, unrelated tasks.
- The skill must be about the DOMAIN TASK (the original query above), NOT about "analyzing logs" or "evaluating runs".
- The skill should encode the workflow, techniques, prompt patterns, and tool usage that made this run effective.
- Name the skill after what it DOES (e.g., "poem-workshop", "website-builder"), not after analysis.
{lifecycle_instructions}

Required outputs:
- Create a skill directory on disk: `.agent/skills/<skill-name>/SKILL.md` using filesystem tools.
- The SKILL.md should capture the specific workflow, prompts, and patterns from the logs so someone else can reproduce or build on this work.
- Add provenance metadata so MassGen can classify this as an evolving skill:
  - `massgen_origin: "{target_log}::{target_turn}"`
  - `evolving: true`

## Skill Creation Reference

<skill-creator-reference>
{skill_creator_ref}
</skill-creator-reference>

When creating a skill from analysis findings:
1. Choose a descriptive kebab-case name that reflects the domain task (NOT "log-analysis" or similar).
2. Write the SKILL.md file directly to `.agent/skills/<name>/SKILL.md` using filesystem tools.
3. Include YAML frontmatter with at least `name`, `description`, `massgen_origin`, and `evolving`.
4. Focus the skill content on the actual workflow and techniques, not on meta-analysis.
5. Respect lifecycle mode `{normalized_lifecycle_mode}` when deciding whether to update existing skills, create a new one, or consolidate overlaps.
6. If a SKILL_REGISTRY.md exists in `.agent/skills/`, append the new skill to it under a "## Recently Added" section \
with format: `- **skill-name** (project): description`. This ensures the skill is visible to agents before the next \
full registry reorganization.
"""
    else:
        profile_section = """## Profile Focus: DEV (internals-first)

Primary objective:
- Diagnose runtime behavior, coordination quality, and implementation-level issues in MassGen.

Required outputs:
- Prioritize root causes, regressions, and concrete internal improvements.
- Be specific about signals from logs/events, likely causes, and fix direction.
"""

    return f"""# LOG ANALYSIS MODE

You are in MassGen Textual analysis mode.

Analysis target:
- Log session: {target_log}
- Turn: {target_turn}
{original_query_section}
{profile_section}

General constraints:
- Use the available skills and local log artifacts as the primary evidence source.
- Focus on actionable conclusions, not generic summaries.
- If evidence is incomplete, state exactly what is missing and why it matters.

USER'S ANALYSIS REQUEST:
"""


def get_skill_organization_prompt_prefix() -> str:
    """Generate the user prompt prefix for skill organization analysis mode.

    This prompt instructs the agent to read all installed skills, identify
    overlapping or confusable skills, merge where appropriate, and produce
    a compact SKILL_REGISTRY.md routing guide.

    Returns:
        Prefix instructions to prepend to the user's question.
    """
    return """# SKILL ORGANIZATION MODE

You are in MassGen skill organization mode. Your task is to analyze, reorganize,
and catalog all installed skills.

IMPORTANT: Start by reading the skill-organizer skill's instructions from
.agent/skills/skill-organizer/SKILL.md for the detailed workflow.

## Step 1: Inventory all skills

List all skill directories in the .agent/skills/ folder. Then read each skill's
SKILL.md file to understand what it does, its scope, and its quality.

## Step 2: Identify overlapping or confusable skills

Look for:
- Skills that do the same thing with slightly different names or descriptions
- Skills whose scopes overlap significantly (one is a subset of another)
- Skills that could be combined into a single broader skill with multiple sections

## Step 3: Merge into hierarchical parent skills

For each group of overlapping or related skills, create a single parent skill
with sections covering each sub-capability:
- Choose a broader parent name (e.g., `web-app-dev` instead of separate
  `react-frontend`, `nodejs-backend`, `web-testing`)
- Write one comprehensive SKILL.md with clearly labeled sections for each
  sub-capability
- Move bundled resources into subdirectories of the parent skill directory
- Remove the redundant skill directories

When merging, prefer the skill with:
- Better-quality instructions and examples
- More complete bundled resources
- A more descriptive, general name

Fewer, richer skills with sections beats many shallow skills.

## Step 4: Generate SKILL_REGISTRY.md

Write a compact `SKILL_REGISTRY.md` to `.agent/skills/SKILL_REGISTRY.md` that serves
as a routing guide for skill selection. For each skill, include:

- **What it does** in one sentence
- **Use when**: trigger condition — when should the agent read this skill?
- **Sections**: what sub-capabilities/sections live inside (for hierarchical skills)

Group skills by purpose/domain (not alphabetically). Stay under 50 entries total.
Include a "Recently Added" section for uncategorized new skills.

The registry is injected into agent system prompts to help them pick the right skill
without loading all skill details upfront.

## Step 5: Report what you did

Summarize:
- How many skills were found
- Which skills were merged (old names → new name)
- Which skills were kept as-is
- The final registry structure

## Constraints

- Do NOT use keyword matching, Jaccard similarity, or heuristic categorization.
  Use your understanding of what each skill does.
- Be aggressive about merging — fewer high-quality skills is better than many overlapping ones.
- Preserve all bundled resources (templates, examples, configs) during merges.
- The SKILL_REGISTRY.md is a routing guide, not documentation. Keep it concise.

USER'S ORGANIZATION REQUEST:
"""


# Global PromptSession instance (reused across prompts for better terminal handling)
_prompt_session: PromptSession | None = None


def _get_prompt_session() -> PromptSession:
    """Get or create the PromptSession instance with AtPathCompleter."""
    global _prompt_session
    if _prompt_session is None:
        _prompt_session = PromptSession(
            completer=AtPathCompleter(),
            complete_while_typing=True,
        )
    return _prompt_session


async def read_multiline_input_async(
    prompt: str,
    enable_path_completion: bool = True,
    use_ansi_prompt: bool = False,
) -> str:
    """Async version of read_multiline_input for use in async contexts.

    Uses prompt_toolkit's async prompt_async() method which works correctly
    inside an already-running event loop.

    Args:
        prompt: The prompt string (can contain ANSI codes if use_ansi_prompt=True)
        enable_path_completion: Whether to enable @path autocomplete
        use_ansi_prompt: If True, interpret prompt as ANSI-formatted text
    """
    try:
        session = _get_prompt_session()
        # Wrap prompt in ANSI() if it contains escape codes
        formatted_prompt = ANSI(prompt) if use_ansi_prompt else prompt
        with patch_stdout():
            if not enable_path_completion:
                first_line = (await session.prompt_async(formatted_prompt, completer=None)).strip()
            else:
                first_line = (await session.prompt_async(formatted_prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception as e:
        if _is_debug_mode():
            logger.debug(f"prompt_toolkit async failed; falling back to input(): {e}")
        # Fallback to basic input - run in executor to not block
        loop = asyncio.get_running_loop()
        # Strip ANSI codes for fallback
        plain_prompt = prompt if not use_ansi_prompt else "User: "
        first_line = await loop.run_in_executor(
            None,
            lambda: input(plain_prompt).strip(),
        )

    # Check for multi-line delimiters
    if first_line.startswith('"""'):
        delimiter = '"""'
        content = first_line[3:]
    elif first_line.startswith("'''"):
        delimiter = "'''"
        content = first_line[3:]
    else:
        return first_line

    # Check if closing delimiter is on the same line
    if delimiter in content:
        return content[: content.index(delimiter)]

    # Collect multi-line input
    lines = [content] if content else []
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            raise
        if delimiter in line:
            final_part = line[: line.index(delimiter)]
            if final_part:
                lines.append(final_part)
            break
        lines.append(line)

    return "\n".join(lines)


def read_multiline_input(prompt: str, enable_path_completion: bool = True) -> str:
    """Read user input with support for multi-line input and @path completion.

    Uses prompt_toolkit PromptSession to provide inline file completion when user types @.
    If input starts with ''' or \""", continues reading until closing quotes.
    Otherwise returns single line input.

    Note: This synchronous version will fallback to basic input() if called from
    within an async context. Use read_multiline_input_async() instead in async code.

    Args:
        prompt: The prompt to display to the user
        enable_path_completion: If True, enable @path autocomplete (default True)

    Returns:
        The complete user input (single or multi-line)
    """
    # Check if we're in an async context
    try:
        import asyncio

        asyncio.get_running_loop()
        # We're in an async context - can't use sync prompt
        # Fallback to basic input
        first_line = input(prompt).strip()
    except RuntimeError:
        # No running loop - safe to use sync prompt
        try:
            session = _get_prompt_session()
            if not enable_path_completion:
                first_line = session.prompt(prompt, completer=None).strip()
            else:
                first_line = session.prompt(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as e:
            import sys

            print(f"\n[DEBUG] prompt_toolkit failed: {e}", file=sys.stderr)
            first_line = input(prompt).strip()

    # Check for multi-line delimiters
    if first_line.startswith('"""'):
        delimiter = '"""'
        content = first_line[3:]  # Remove opening delimiter
    elif first_line.startswith("'''"):
        delimiter = "'''"
        content = first_line[3:]  # Remove opening delimiter
    else:
        # Single line input
        return first_line

    # Check if closing delimiter is on the same line
    if delimiter in content:
        return content[: content.index(delimiter)]

    # Multi-line mode: read until closing delimiter
    lines = [content] if content else []
    print(
        f"   {BRIGHT_CYAN}(Multi-line mode: enter {delimiter} on a new line to finish){RESET}",
        flush=True,
    )

    while True:
        try:
            line = input("   ")
            if delimiter in line:
                # Found closing delimiter
                before_delimiter = line[: line.index(delimiter)]
                if before_delimiter:
                    lines.append(before_delimiter)
                break
            lines.append(line)
        except EOFError:
            # Handle Ctrl+D
            break

    return "\n".join(lines)


class ConfigurationError(Exception):
    """Configuration error for CLI."""


def _substitute_variables(obj: Any, variables: dict[str, str]) -> Any:
    """Recursively substitute ${var} references in config with actual values.

    Args:
        obj: Config object (dict, list, str, or other)
        variables: Dict of variable names to values

    Returns:
        Config object with variables substituted
    """
    if isinstance(obj, dict):
        return {k: _substitute_variables(v, variables) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_variables(item, variables) for item in obj]
    elif isinstance(obj, str):
        # Replace ${var} with value
        result = obj
        for var_name, var_value in variables.items():
            result = result.replace(f"${{{var_name}}}", var_value)
        return result
    else:
        return obj


_MASSGEN_WORKSPACES_PREFIX = ".massgen/workspaces/"


def _route_workspace_path(cwd: str) -> str:
    """Route relative workspace paths under .massgen/workspaces/.

    Absolute paths are returned unchanged. Paths already under
    .massgen/workspaces/ are not double-prefixed.
    """
    from pathlib import PurePath

    p = PurePath(cwd)
    if p.is_absolute():
        return cwd
    # Don't double-prefix
    normalized = str(p).replace("\\", "/")
    if normalized.startswith(_MASSGEN_WORKSPACES_PREFIX) or normalized.startswith(".massgen/workspaces"):
        return cwd
    return f"{_MASSGEN_WORKSPACES_PREFIX}{cwd}"


def resolve_config_path(config_arg: str | None) -> Path | None:
    """Resolve config file with flexible syntax.

    Priority order:

    **If --config flag provided (highest priority):**
    1. @examples/NAME → Package examples (search configs directory)
    2. Absolute/relative paths (exact path as specified)
    3. Named configs in ~/.config/massgen/agents/

    **If NO --config flag (auto-discovery):**
    1. .massgen/config.yaml (project-level config in current directory)
    2. ~/.config/massgen/config.yaml (global default config)
    3. None → trigger config builder

    Args:
        config_arg: Config argument from --config flag (can be @examples/NAME, path, or None)

    Returns:
        Path to config file, or None if config builder should run

    Raises:
        ConfigurationError: If config file not found
    """
    # Check for default configs if no config_arg provided
    if not config_arg:
        # Priority 1: Project-level config (.massgen/config.yaml in current directory)
        project_config = Path.cwd() / ".massgen" / "config.yaml"
        if project_config.exists():
            return project_config

        # Priority 2: Global default config
        global_config = Path.home() / ".config/massgen/config.yaml"
        if global_config.exists():
            return global_config

        return None  # Trigger builder

    # Handle @examples/ prefix - search in package configs
    if config_arg.startswith("@examples/"):
        name = config_arg[10:]  # Remove '@examples/' prefix
        try:
            from importlib.resources import files

            configs_root = files("massgen") / "configs"

            # Search recursively for matching name
            # Try to find by filename stem match
            for config_file in configs_root.rglob("*.yaml"):
                # Check if name matches the file stem or is contained in the path
                if name in config_file.name or name in str(config_file):
                    return Path(str(config_file))

            raise ConfigurationError(
                f"Config '{config_arg}' not found in package.\n" f"Use --list-examples to see available configs.",
            )
        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise ConfigurationError(f"Error loading package config: {e}")

    # Try as regular path (absolute or relative)
    path = Path(config_arg).expanduser()
    if path.exists():
        return path

    # Try in user config directory (~/.config/massgen/agents/)
    user_agents_dir = Path.home() / ".config/massgen/agents"
    # Try with config_arg as-is first
    user_config = user_agents_dir / config_arg
    if user_config.exists():
        return user_config

    # Also try with .yaml extension if not provided
    if not config_arg.endswith((".yaml", ".yml")):
        user_config_with_ext = user_agents_dir / f"{config_arg}.yaml"
        if user_config_with_ext.exists():
            return user_config_with_ext
        # For error message, show the path with .yaml extension
        user_config = user_config_with_ext

    # Config not found anywhere
    raise ConfigurationError(
        f"Configuration file not found: {config_arg}\n"
        f"Searched in:\n"
        f"  - Current directory: {Path.cwd() / config_arg}\n"
        f"  - User configs: {user_config}\n"
        f"Use --list-examples to see available package configs.",
    )


def load_config_file(config_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load configuration from YAML or JSON file.

    Search order:
    1. Exact path as provided (absolute or relative to CWD)
    2. If just a filename, search in package's configs/ directory
    3. If a relative path, also try within package's configs/ directory

    Supports variable substitution: ${VAR_NAME} in any string will be replaced
    with the value of the VAR_NAME environment variable.

    Returns:
        Tuple of (expanded_config, raw_config) where:
        - expanded_config: Config with ${VAR} replaced by actual env values
        - raw_config: Original config preserving ${VAR} syntax (safe for logging)
    """
    path = Path(config_path)

    # Try the path as-is first (handles absolute paths and relative to CWD)
    if path.exists():
        pass  # Use this path
    elif path.is_absolute():
        # Absolute path that doesn't exist
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    else:
        # Relative path or just filename - search in package configs
        package_configs_dir = Path(__file__).parent / "configs"

        # Try 1: Just the filename in package configs root
        candidate1 = package_configs_dir / path.name
        # Try 2: The full relative path within package configs
        candidate2 = package_configs_dir / path

        if candidate1.exists():
            path = candidate1
        elif candidate2.exists():
            path = candidate2
        else:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}\n" f"Searched in:\n" f"  - {Path.cwd() / config_path}\n" f"  - {candidate1}\n" f"  - {candidate2}",
            )

    try:
        with open(path, encoding="utf-8") as f:
            if path.suffix.lower() in [".yaml", ".yml"]:
                raw_config = yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                raw_config = json.load(f)
            else:
                raise ConfigurationError(
                    f"Unsupported config file format: {path.suffix}",
                )

            # Return both expanded (for runtime) and raw (for logging)
            expanded_config = _expand_env_vars(copy.deepcopy(raw_config))
            return expanded_config, raw_config
    except Exception as e:
        raise ConfigurationError(f"Error reading config file: {e}")


def _expand_env_vars(config: Any) -> Any:
    """Recursively expand environment variables in config.

    Replaces ${VAR_NAME} with the value of the VAR_NAME environment variable.
    If the variable is not set, leaves the ${VAR_NAME} string as-is.
    """
    import re

    if isinstance(config, dict):
        return {k: _expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_expand_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Replace ${VAR} with environment variable value
        pattern = r"\$\{([^}]+)\}"

        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))

        return re.sub(pattern, replacer, config)
    return config


def _api_key_error_message(
    provider_name: str,
    env_var: str,
    config_path: str | None = None,
) -> str:
    """Generate standard API key error message."""
    msg = (
        f"{provider_name} API key not found. Set {env_var} environment variable.\n"
        "You can add it to a .env file in:\n"
        "  - Current directory: .env\n"
        "  - User config: ~/.config/massgen/.env\n"
        "  - Global: ~/.massgen/.env\n"
        "\nOr run: massgen --setup"
    )
    if config_path:
        msg += f"\n\n📄 Using config: {config_path}"
    return msg


def create_backend(backend_type: str, **kwargs) -> Any:
    """Create backend instance from type and parameters.

    Supported backend types:
    - openai: OpenAI API (requires OPENAI_API_KEY)
    - grok: xAI Grok (requires XAI_API_KEY)
    - sglang: SGLang inference server (local)
    - claude: Anthropic Claude (requires ANTHROPIC_API_KEY)
    - gemini: Google Gemini (requires GOOGLE_API_KEY or GEMINI_API_KEY)
    - chatcompletion: OpenAI-compatible providers (auto-detects API key based on base_url)
    - nvidia_nim: Nvidia NIM (requires NGC_API_KEY)

    Supported backend with external dependencies:
    - ag2/autogen: AG2 (AutoGen) framework agents

    For chatcompletion backend, the following providers are auto-detected:
    - Cerebras AI (cerebras.ai) -> CEREBRAS_API_KEY
    - Together AI (together.ai/together.xyz) -> TOGETHER_API_KEY
    - Fireworks AI (fireworks.ai) -> FIREWORKS_API_KEY
    - Groq (groq.com) -> GROQ_API_KEY
    - Nebius AI Studio (studio.nebius.ai) -> NEBIUS_API_KEY
    - OpenRouter (openrouter.ai) -> OPENROUTER_API_KEY
    - Nvidia NIM (nvidia.com) -> NGC_API_KEY
    - POE (poe.com) -> POE_API_KEY
    - Qwen (dashscope.aliyuncs.com) -> QWEN_API_KEY

    External agent frameworks are supported via the adapter registry.
    """
    backend_type = backend_type.lower()

    # Extract config path for error messages (and remove it from kwargs so it doesn't interfere)
    config_path = kwargs.pop("_config_path", None)

    # Check if this is a framework/adapter type
    from massgen.adapters import adapter_registry

    if backend_type in adapter_registry:
        # Use ExternalAgentBackend for all registered adapter types
        from massgen.backend.external import ExternalAgentBackend

        return ExternalAgentBackend(adapter_type=backend_type, **kwargs)

    if backend_type == "openai":
        api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("OpenAI", "OPENAI_API_KEY", config_path),
            )
        return ResponseBackend(api_key=api_key, **kwargs)

    elif backend_type == "grok":
        api_key = kwargs.get("api_key") or os.getenv("XAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Grok", "XAI_API_KEY", config_path),
            )
        return GrokBackend(api_key=api_key, **kwargs)

    elif backend_type == "claude":
        api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Claude", "ANTHROPIC_API_KEY", config_path),
            )
        return ClaudeBackend(api_key=api_key, **kwargs)

    elif backend_type == "gemini":
        api_key = kwargs.get("api_key") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Gemini", "GOOGLE_API_KEY", config_path),
            )
        return GeminiBackend(api_key=api_key, **kwargs)

    elif backend_type == "copilot":
        # Copilot uses local auth via SDK, no API key required here
        return CopilotBackend(api_key="copilot-local", **kwargs)

    elif backend_type == "chatcompletion":
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")

        # Determine API key based on base URL if not explicitly provided
        if not api_key:
            if base_url and "cerebras.ai" in base_url:
                api_key = os.getenv("CEREBRAS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Cerebras AI API key not found. Set CEREBRAS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "together.xyz" in base_url:
                api_key = os.getenv("TOGETHER_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Together AI API key not found. Set TOGETHER_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "fireworks.ai" in base_url:
                api_key = os.getenv("FIREWORKS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Fireworks AI API key not found. Set FIREWORKS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "groq.com" in base_url:
                api_key = os.getenv("GROQ_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Groq API key not found. Set GROQ_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "nebius.com" in base_url:
                api_key = os.getenv("NEBIUS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Nebius AI Studio API key not found. Set NEBIUS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "openrouter.ai" in base_url:
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and ("z.ai" in base_url or "bigmodel.cn" in base_url):
                api_key = os.getenv("ZAI_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "ZAI API key not found. Set ZAI_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and ("moonshot.ai" in base_url or "moonshot.cn" in base_url):
                api_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Kimi/Moonshot API key not found. Set MOONSHOT_API_KEY or KIMI_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "nvidia.com" in base_url:
                api_key = os.getenv("NGC_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Nvidia NIM API key not found. Set NGC_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "poe.com" in base_url:
                api_key = os.getenv("POE_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "POE API key not found. Set POE_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "aliyuncs.com" in base_url:
                api_key = os.getenv("QWEN_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Qwen API key not found. Set QWEN_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )

        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "zai":
        # ZAI (Zhipu.ai) uses OpenAI-compatible Chat Completions at a custom base_url
        # Supports both global (z.ai) and China (bigmodel.cn) endpoints
        api_key = kwargs.get("api_key") or os.getenv("ZAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "ZAI API key not found. Set ZAI_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
            )
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "cerebras":
        # Cerebras AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Cerebras AI", "CEREBRAS_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.cerebras.ai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "together":
        # Together AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Together AI", "TOGETHER_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.together.xyz/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "fireworks":
        # Fireworks AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("FIREWORKS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Fireworks AI",
                    "FIREWORKS_API_KEY",
                    config_path,
                ),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.fireworks.ai/inference/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "groq":
        # Groq uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Groq", "GROQ_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.groq.com/openai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "openrouter":
        # OpenRouter uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("OpenRouter", "OPENROUTER_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "moonshot":
        # Kimi/Moonshot AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Moonshot AI", "MOONSHOT_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.moonshot.cn/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "nvidia_nim":
        # Nvidia NIM uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("NGC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Nvidia NIM", "NGC_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://integrate.api.nvidia.com/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "nebius":
        # Nebius AI Studio uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("NEBIUS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Nebius AI Studio",
                    "NEBIUS_API_KEY",
                    config_path,
                ),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.studio.nebius.ai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "poe":
        # POE uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("POE_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("POE", "POE_API_KEY", config_path),
            )
        # base_url must be provided in config as it's platform-specific
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "qwen":
        # Qwen uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Qwen", "QWEN_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "lmstudio":
        # LM Studio local server (OpenAI-compatible). Defaults handled by backend.
        return LMStudioBackend(**kwargs)

    elif backend_type == "vllm":
        # vLLM local server (OpenAI-compatible). Defaults handled by backend.
        return InferenceBackend(backend_type="vllm", **kwargs)

    elif backend_type == "sglang":
        # SGLang local server (OpenAI-compatible). Defaults handled by backend.
        return InferenceBackend(backend_type="sglang", **kwargs)

    elif backend_type == "claude_code":
        # ClaudeCodeBackend using claude-code-sdk-python
        # Authentication handled by backend (API key or subscription)

        # Validate claude-code-sdk availability
        try:
            pass
        except ImportError:
            raise ConfigurationError(
                "claude-code-sdk not found. Install with: pip install claude-code-sdk",
            )

        return ClaudeCodeBackend(**kwargs)

    elif backend_type == "codex":
        # CodexBackend using OpenAI Codex CLI subprocess wrapper
        # Authentication: API key (OPENAI_API_KEY) or ChatGPT OAuth
        # Requires: npm install -g @openai/codex

        return CodexBackend(**kwargs)

    elif backend_type == "gemini_cli":
        # GeminiCLIBackend using Google Gemini CLI subprocess wrapper
        # Authentication: CLI login (gemini) or GOOGLE_API_KEY/GEMINI_API_KEY
        # Requires: npm install -g @google/gemini-cli

        return GeminiCLIBackend(**kwargs)

    elif backend_type == "azure_openai":
        api_key = kwargs.get("api_key") or os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = kwargs.get("base_url") or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Azure OpenAI",
                    "AZURE_OPENAI_API_KEY",
                    config_path,
                ),
            )
        if not endpoint:
            raise ConfigurationError(
                "Azure OpenAI endpoint not found. Set AZURE_OPENAI_ENDPOINT or provide base_url in config.",
            )
        return AzureOpenAIBackend(**kwargs)

    else:
        raise ConfigurationError(f"Unsupported backend type: {backend_type}")


def create_agents_from_config(
    config: dict[str, Any],
    orchestrator_config: dict[str, Any] | None = None,
    enable_rate_limit: bool = False,
    config_path: str | None = None,
    memory_session_id: str | None = None,
    debug: bool = False,
    filesystem_session_id: str | None = None,
    session_storage_base: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, ConfigurableAgent]:
    """Create agents from configuration.

    TIMING: This function is instrumented for performance analysis.

    Args:
        config: Configuration dictionary
        orchestrator_config: Optional orchestrator configuration
        enable_rate_limit: Whether to enable rate limiting (from CLI flag)
        config_path: Optional path to the config file for error messages
        memory_session_id: Optional session ID to use for memory isolation.
                          If provided, overrides session_name from YAML config.
        filesystem_session_id: Optional session ID for Docker session pre-mounting.
                   Enables faster multi-turn by avoiding container recreation.
        session_storage_base: Base directory for session storage (e.g., ".massgen/sessions").
                             Required with filesystem_session_id for session pre-mounting.
        progress_callback: Optional callback for progress updates (status, detail).
    """
    agents = {}

    agent_entries = [config["agent"]] if "agent" in config else config.get("agents", None)

    if not agent_entries:
        raise ConfigurationError(
            "Configuration must contain either 'agent' or 'agents' section",
        )

    # Create shared Qdrant client for all agents (avoids concurrent access errors)
    # ONE client can be used by multiple mem0 instances safely
    shared_qdrant_client = None
    global_memory_config = config.get("memory", {})
    if global_memory_config.get("enabled", False) and global_memory_config.get(
        "persistent_memory",
        {},
    ).get("enabled", False):
        try:
            from qdrant_client import QdrantClient

            pm_config = global_memory_config.get("persistent_memory", {})

            # Support both server mode and file-based mode
            qdrant_config = pm_config.get("qdrant", {})
            mode = qdrant_config.get("mode", "local")  # "local" or "server"

            if mode == "server":
                # Server mode (RECOMMENDED for multi-agent)
                host = qdrant_config.get("host", "localhost")
                port = qdrant_config.get("port", 6333)
                shared_qdrant_client = QdrantClient(host=host, port=port)
                logger.info(
                    f"🗄️  Shared Qdrant client created (server mode: {host}:{port})",
                )
            else:
                # Local file-based mode (single agent only)
                # WARNING: Does NOT support concurrent access by multiple agents
                qdrant_path = pm_config.get("path", ".massgen/qdrant")
                shared_qdrant_client = QdrantClient(path=qdrant_path)
                logger.info(
                    f"🗄️  Shared Qdrant client created (local mode: {qdrant_path})",
                )
                if len(agent_entries) > 1:
                    logger.warning(
                        "⚠️  Multi-agent setup detected with local Qdrant mode. "
                        "This may cause concurrent access errors. "
                        "Consider using server mode: set memory.persistent_memory.qdrant.mode='server'",
                    )
        except Exception as e:
            logger.warning(f"⚠️  Failed to create shared Qdrant client: {e}")
            logger.warning("   Persistent memory will be disabled for all agents")
            logger.warning(
                "   For multi-agent setup, start Qdrant server: docker-compose -f docker-compose.qdrant.yml up -d",
            )

    for i, agent_data in enumerate(agent_entries, start=1):
        backend_config = agent_data.get("backend", {})

        # Inject rate limiting flag from CLI
        backend_config["enable_rate_limit"] = enable_rate_limit

        # Inject two-tier workspace setting from coordination config
        orchestrator_section = orchestrator_config or {}
        coordination_settings_for_injection = orchestrator_section.get(
            "coordination",
            {},
        )
        if coordination_settings_for_injection.get("use_two_tier_workspace", False):
            backend_config["use_two_tier_workspace"] = True

        # Inject write_mode so FilesystemManager knows to suppress Docker context mounts
        write_mode_setting = coordination_settings_for_injection.get("write_mode")
        if write_mode_setting:
            backend_config["write_mode"] = write_mode_setting

        # Inject session mount parameters for multi-turn Docker support
        # This enables the session directory to be pre-mounted so all turn
        # workspaces are automatically visible without container recreation
        if filesystem_session_id and session_storage_base:
            backend_config["filesystem_session_id"] = filesystem_session_id
            backend_config["session_storage_base"] = session_storage_base

        # Substitute variables like ${cwd} in backend config, then apply unique suffix
        if "cwd" in backend_config:
            variables = {"cwd": backend_config["cwd"]}
            backend_config = _substitute_variables(backend_config, variables)

            # Route relative workspace paths under .massgen/workspaces/
            backend_config["cwd"] = _route_workspace_path(backend_config["cwd"])

            # Apply unique suffix to workspace paths to prevent filesystem conflicts
            # and identity leakage between agents. Each agent gets a unique suffix.
            # This runs for ALL entrypoints (CLI, SDK, Web UI).
            import uuid
            from pathlib import PurePath

            original_cwd = backend_config["cwd"]
            cwd_path = PurePath(original_cwd)
            leaf = cwd_path.name
            # Normalize only "workspaceN" pattern to prevent identity leakage
            if re.fullmatch(r"workspace\d+", leaf):
                leaf = re.sub(r"\d+$", "", leaf)
                base_name = str(cwd_path.with_name(leaf))
            else:
                base_name = str(cwd_path)
            # Generate unique suffix per agent
            agent_workspace_suffix = uuid.uuid4().hex[:8]
            backend_config["cwd"] = f"{base_name}_{agent_workspace_suffix}"
            logger.debug(
                f"Auto-generated unique workspace: {original_cwd} -> {backend_config['cwd']}",
            )

        # Infer backend type from model if not explicitly provided
        backend_type = backend_config.get("type") or (get_backend_type_from_model(backend_config["model"]) if "model" in backend_config else None)
        if not backend_type:
            raise ConfigurationError(
                "Backend type must be specified or inferrable from model",
            )

        # Add orchestrator context for filesystem setup if available
        if orchestrator_config:
            if "agent_temporary_workspace" in orchestrator_config:
                backend_config["agent_temporary_workspace"] = _scope_agent_temporary_workspace(
                    orchestrator_config["agent_temporary_workspace"],
                )
            # Add orchestrator-level context_paths to all agents
            if "context_paths" in orchestrator_config:
                # Merge orchestrator context_paths with agent-specific ones
                agent_context_paths = backend_config.get("context_paths", [])
                orchestrator_context_paths = orchestrator_config["context_paths"]

                # Deduplicate paths - orchestrator paths take precedence
                merged_paths = orchestrator_context_paths.copy()
                orchestrator_paths_set = {path.get("path") for path in orchestrator_context_paths}

                for agent_path in agent_context_paths:
                    if agent_path.get("path") not in orchestrator_paths_set:
                        merged_paths.append(agent_path)

                backend_config["context_paths"] = merged_paths

            # Inherit enable_multimodal_tools from orchestrator if not set per-agent
            if "enable_multimodal_tools" in orchestrator_config:
                if "enable_multimodal_tools" not in backend_config:
                    backend_config["enable_multimodal_tools"] = orchestrator_config["enable_multimodal_tools"]

            # Inherit generation config from orchestrator if not set per-agent
            # These set default backends/models for image/video/audio generation
            generation_config_keys = [
                "image_generation_backend",
                "image_generation_model",
                "video_generation_backend",
                "video_generation_model",
                "audio_generation_backend",
                "audio_generation_model",
            ]
            for key in generation_config_keys:
                if key in orchestrator_config and key not in backend_config:
                    backend_config[key] = orchestrator_config[key]

            # Also support nested multimodal_config from orchestrator
            if "multimodal_config" in orchestrator_config:
                if "multimodal_config" not in backend_config:
                    backend_config["multimodal_config"] = orchestrator_config["multimodal_config"]

        # Add config path for better error messages
        if config_path:
            backend_config["_config_path"] = config_path

        # Get agent_id for AgentConfig and backend (needed for MCP tool span correlation)
        agent_id = agent_data.get("id", f"agent{i}")

        # Emit progress for this agent
        total = len(agent_entries)
        if progress_callback:
            progress_callback(
                f"🤖 Initializing {agent_id} ({i}/{total})...",
                f"Backend: {backend_type}",
            )

        # Pass agent_id to backend for MCP tool span correlation
        backend = create_backend(backend_type, agent_id=agent_id, **backend_config)
        backend_params = {k: v for k, v in backend_config.items() if k not in ("type", "_config_path")}

        backend_type_lower = backend_type.lower()
        if backend_type_lower == "openai":
            agent_config = AgentConfig.create_openai_config(**backend_params)
        elif backend_type_lower == "claude":
            agent_config = AgentConfig.create_claude_config(**backend_params)
        elif backend_type_lower == "grok":
            agent_config = AgentConfig.create_grok_config(**backend_params)
        elif backend_type_lower == "gemini":
            agent_config = AgentConfig.create_gemini_config(**backend_params)
        elif backend_type_lower == "zai":
            agent_config = AgentConfig.create_zai_config(**backend_params)
        elif backend_type_lower == "chatcompletion":
            agent_config = AgentConfig.create_chatcompletion_config(**backend_params)
        elif backend_type_lower in [
            "cerebras",
            "together",
            "fireworks",
            "groq",
            "openrouter",
            "moonshot",
            "nvidia_nim",
            "nebius",
            "poe",
            "qwen",
        ]:
            agent_config = AgentConfig.create_chatcompletion_config(**backend_params)
        elif backend_type_lower == "lmstudio":
            agent_config = AgentConfig.create_lmstudio_config(**backend_params)
        elif backend_type_lower == "vllm":
            agent_config = AgentConfig.create_vllm_config(**backend_params)
        elif backend_type_lower == "sglang":
            agent_config = AgentConfig.create_sglang_config(**backend_params)
        elif backend_type_lower == "claude_code":
            agent_config = AgentConfig.create_claude_code_config(**backend_params)
        elif backend_type_lower == "gemini_cli":
            agent_config = AgentConfig(backend_params=backend_params)
        elif backend_type_lower == "copilot":
            # Copilot maps to standard Config with minimal params?
            # Or dedicated config if needed. For now standard.
            agent_config = AgentConfig(backend_params=backend_params)
        elif backend_type_lower == "azure_openai":
            agent_config = AgentConfig.create_azure_openai_config(**backend_params)
        else:
            agent_config = AgentConfig(backend_params=backend_params)

        agent_config.agent_id = agent_id
        agent_config.subagent_agents = copy.deepcopy(agent_data.get("subagent_agents", []))

        # System message handling: all backends use system_message at agent level
        system_msg = agent_data.get("system_message")
        if system_msg:
            # Set on AgentConfig (ConfigurableAgent will extract it)
            agent_config._custom_system_instruction = system_msg

        # Timeout configuration will be applied to orchestrator instead of individual agents

        # Merge global and per-agent memory configuration
        global_memory_config = config.get("memory", {})
        agent_memory_config = agent_data.get("memory", {})

        # Deep merge: agent config overrides global config
        def merge_configs(global_cfg, agent_cfg):
            """Recursively merge agent config into global config."""
            merged = global_cfg.copy()
            for key, value in agent_cfg.items():
                if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                    merged[key] = merge_configs(merged[key], value)
                else:
                    merged[key] = value
            return merged

        memory_config = merge_configs(global_memory_config, agent_memory_config)

        # Create context monitor if memory config is enabled
        context_monitor = None
        if memory_config.get("enabled", False):
            from .memory._context_monitor import ContextWindowMonitor

            compression_config = memory_config.get("compression", {})
            trigger_threshold = compression_config.get("trigger_threshold", 0.75)
            target_ratio = compression_config.get("target_ratio", 0.40)

            # Get model name from backend config
            model_name = backend_config.get("model", "unknown")

            # Normalize provider name for monitor
            provider_map = {
                "openai": "openai",
                "anthropic": "anthropic",
                "claude": "anthropic",
                "google": "google",
                "gemini": "google",
                "gemini_cli": "google",
            }
            provider = provider_map.get(backend_type_lower, backend_type_lower)

            context_monitor = ContextWindowMonitor(
                model_name=model_name,
                provider=provider,
                trigger_threshold=trigger_threshold,
                target_ratio=target_ratio,
                enabled=True,
            )
            logger.info(
                f"📊 Context monitor created for {agent_config.agent_id}: " f"{context_monitor.context_window:,} tokens, " f"trigger={trigger_threshold * 100:.0f}%, target={target_ratio * 100:.0f}%",
            )

        # Enable NLIP per-agent if configured in YAML
        agent_nlip_section = agent_data.get("nlip") or {}
        agent_enable_nlip = bool(agent_data.get("enable_nlip"))
        if isinstance(agent_nlip_section, dict):
            agent_enable_nlip = agent_enable_nlip or agent_nlip_section.get(
                "enabled",
                False,
            )

        if agent_enable_nlip:
            agent_config.enable_nlip = True
            if isinstance(agent_nlip_section, dict) and agent_nlip_section:
                agent_config.nlip_config = agent_nlip_section
            logger.info(
                f"[CLI] NLIP enabled for agent {agent_config.agent_id} via config file",
            )

        # Create per-agent memory objects if memory is enabled
        conversation_memory = None
        persistent_memory = None

        if memory_config.get("enabled", False):
            from .memory import ConversationMemory

            # Create conversation memory for this agent
            if memory_config.get("conversation_memory", {}).get("enabled", True):
                conversation_memory = ConversationMemory()
                logger.info(
                    f"💾 Conversation memory created for {agent_config.agent_id}",
                )

            # Create persistent memory for this agent (if enabled)
            if memory_config.get("persistent_memory", {}).get("enabled", False):
                from .memory import PersistentMemory

                pm_config = memory_config.get("persistent_memory", {})

                # Get persistent memory configuration
                agent_name = pm_config.get("agent_name", agent_config.agent_id)

                # Use unified session: memory_session_id (from CLI) > YAML session_name > None
                session_name = memory_session_id or pm_config.get("session_name")

                on_disk = pm_config.get("on_disk", True)
                qdrant_path = pm_config.get(
                    "path",
                    ".massgen/qdrant",
                )  # Project dir, not /tmp

                try:
                    # Configure LLM for memory operations (fact extraction)
                    # RECOMMENDED: Use mem0's native LLMs (no adapter overhead, no async complexity)
                    llm_cfg = pm_config.get("llm", {})

                    if not llm_cfg:
                        # Default: gpt-4.1-nano-2025-04-14 (mem0's default, fast and cheap for memory ops)
                        llm_cfg = {
                            "provider": "openai",
                            "model": "gpt-4.1-nano-2025-04-14",
                        }

                    # Add API key if not specified
                    if "api_key" not in llm_cfg:
                        llm_provider = llm_cfg.get("provider", "openai")
                        if llm_provider == "openai":
                            llm_cfg["api_key"] = os.getenv("OPENAI_API_KEY")
                        elif llm_provider == "anthropic":
                            llm_cfg["api_key"] = os.getenv("ANTHROPIC_API_KEY")
                        elif llm_provider == "groq":
                            llm_cfg["api_key"] = os.getenv("GROQ_API_KEY")
                        # Add more providers as needed

                    # Configure embedding for persistent memory
                    # RECOMMENDED: Use mem0's native embedders (no adapter overhead)
                    embedding_cfg = pm_config.get("embedding", {})

                    if not embedding_cfg:
                        # Default: OpenAI text-embedding-3-small
                        embedding_cfg = {
                            "provider": "openai",
                            "model": "text-embedding-3-small",
                        }

                    # Add API key if not specified
                    if "api_key" not in embedding_cfg:
                        emb_provider = embedding_cfg.get("provider", "openai")
                        if emb_provider == "openai":
                            api_key = os.getenv("OPENAI_API_KEY")
                            if not api_key:
                                logger.warning(
                                    "⚠️  OPENAI_API_KEY not found in environment - embedding will fail!",
                                )
                            else:
                                logger.debug(
                                    f"✅ Using OPENAI_API_KEY from environment (key starts with: {api_key[:7]}...)",
                                )
                            embedding_cfg["api_key"] = api_key
                        elif emb_provider == "together":
                            embedding_cfg["api_key"] = os.getenv("TOGETHER_API_KEY")
                        elif emb_provider == "azure_openai":
                            embedding_cfg["api_key"] = os.getenv("AZURE_OPENAI_API_KEY")
                        # Add more providers as needed

                    # Use shared Qdrant client if available
                    if shared_qdrant_client:
                        persistent_memory = PersistentMemory(
                            agent_name=agent_name,
                            session_name=session_name,
                            llm_config=llm_cfg,  # Use native mem0 LLM
                            embedding_config=embedding_cfg,  # Use native mem0 embedder
                            qdrant_client=shared_qdrant_client,  # Share ONE client from server
                            debug=debug,  # Enable memory debug mode if --debug flag used
                            on_disk=on_disk,
                        )
                        logger.info(
                            f"💾 Persistent memory created for {agent_config.agent_id} "
                            f"(agent_name={agent_name}, session={session_name or 'cross-session'}, "
                            f"llm={llm_cfg.get('provider')}/{llm_cfg.get('model')}, "
                            f"embedder={embedding_cfg.get('provider')}/{embedding_cfg.get('model')}, shared_qdrant=True)",
                        )
                    else:
                        # Fallback: create individual vector store (for backward compatibility)
                        # WARNING: File-based Qdrant doesn't support concurrent access
                        from mem0.vector_stores.configs import VectorStoreConfig

                        vector_store_config = VectorStoreConfig(
                            config={
                                "on_disk": on_disk,
                                "path": qdrant_path,
                            },
                        )

                        persistent_memory = PersistentMemory(
                            agent_name=agent_name,
                            session_name=session_name,
                            llm_config=llm_cfg,  # Use native mem0 LLM
                            embedding_config=embedding_cfg,  # Use native mem0 embedder
                            vector_store_config=vector_store_config,
                            debug=debug,  # Enable memory debug mode if --debug flag used
                            on_disk=on_disk,
                        )
                        logger.info(
                            f"💾 Persistent memory created for {agent_config.agent_id} "
                            f"(agent_name={agent_name}, session={session_name or 'cross-session'}, "
                            f"llm={llm_cfg.get('provider')}/{llm_cfg.get('model')}, "
                            f"embedder={embedding_cfg.get('provider')}/{embedding_cfg.get('model')}, path={qdrant_path})",
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️  Failed to create persistent memory for {agent_config.agent_id}: {e}",
                    )
                    persistent_memory = None

        # Get memory recording settings
        recording_config = memory_config.get("recording", {})
        record_all_tool_calls = recording_config.get("record_all_tool_calls", False)
        record_reasoning = recording_config.get("record_reasoning", False)

        # Get per-agent voting sensitivity (if specified)
        agent_voting_sensitivity = agent_data.get("voting_sensitivity")

        # Create agent
        agent = ConfigurableAgent(
            config=agent_config,
            backend=backend,
            conversation_memory=conversation_memory,
            persistent_memory=persistent_memory,
            context_monitor=context_monitor,
            record_all_tool_calls=record_all_tool_calls,
            record_reasoning=record_reasoning,
            voting_sensitivity=agent_voting_sensitivity,
        )

        # Configure retrieval settings from YAML (if memory is enabled)
        if memory_config.get("enabled", False):
            retrieval_config = memory_config.get("retrieval", {})
            agent._retrieval_limit = retrieval_config.get("limit", 5)
            agent._retrieval_exclude_recent = retrieval_config.get(
                "exclude_recent",
                False,
            )

            if retrieval_config or recording_config:  # Log if custom config provided
                config_info = []
                if retrieval_config:
                    config_info.append(
                        f"retrieval(limit={agent._retrieval_limit}, exclude_recent={agent._retrieval_exclude_recent})",
                    )
                if recording_config:
                    config_info.append(
                        f"recording(all_tools={record_all_tool_calls}, reasoning={record_reasoning})",
                    )
                logger.info(
                    f"🔧 Memory configured for {agent_config.agent_id}: {', '.join(config_info)}",
                )

        agents[agent.config.agent_id] = agent

    return agents


def create_dspy_paraphraser_from_config(
    config: dict[str, Any],
    *,
    config_path: str | None = None,
) -> QuestionParaphraser | None:
    """Instantiate DSPy paraphraser from orchestrator configuration.

    Returns:
        QuestionParaphraser instance when DSPy is enabled and properly configured; otherwise None.
    """

    orchestrator_cfg = config.get("orchestrator", {}) if isinstance(config, dict) else {}
    dspy_cfg = orchestrator_cfg.get("dspy") if isinstance(orchestrator_cfg, dict) else None

    if not isinstance(dspy_cfg, dict) or not dspy_cfg.get("enabled", False):
        return None

    if not is_dspy_available():
        location = f" ({config_path})" if config_path else ""
        logger.warning("DSPy is not installed")
        return None

    backend_cfg = dspy_cfg.get("backend", {})
    if not isinstance(backend_cfg, dict) or not backend_cfg:
        logger.warning(
            "DSPy paraphrasing enabled but no backend configuration provided. Skipping DSPy setup.",
        )
        return None

    lm = create_dspy_lm_from_backend_config(backend_cfg)
    if lm is None:
        logger.warning(
            "Failed to initialize DSPy language model from backend configuration. Skipping DSPy setup.",
        )
        return None

    paraphraser_kwargs: dict[str, Any] = {}

    # Simple pass-through configuration values
    for key in [
        "num_variants",
        "strategy",
        "cache_enabled",
        "semantic_threshold",
        "use_chain_of_thought",
        "validate_semantics",
    ]:
        if key in dspy_cfg:
            paraphraser_kwargs[key] = dspy_cfg[key]

    # Temperature range expects a tuple of two numeric values
    temperature_range = dspy_cfg.get("temperature_range")
    if isinstance(temperature_range, (list, tuple)) and len(temperature_range) == 2:
        try:
            paraphraser_kwargs["temperature_range"] = (
                float(temperature_range[0]),
                float(temperature_range[1]),
            )
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid DSPy temperature_range; expected two numeric values.",
            )
    elif temperature_range is not None:
        logger.warning(
            "Ignoring invalid DSPy temperature_range; expected a list/tuple with two values.",
        )

    try:
        paraphraser = QuestionParaphraser(lm=lm, **paraphraser_kwargs)
    except Exception as exc:
        location = f" ({config_path})" if config_path else ""
        logger.warning(f"Failed to initialize DSPy paraphraser{location}: {exc}")
        return None

    logger.info(
        "✅ DSPy question paraphrasing enabled (strategy=%s, variants=%s)",
        paraphraser_kwargs.get("strategy", "balanced"),
        paraphraser_kwargs.get("num_variants", 3),
    )
    return paraphraser


def _scope_snapshot_storage(base: str | None) -> str | None:
    """Scope ``snapshot_storage`` by the current log session root name.

    Two concurrent CLI processes using the same config would otherwise write
    to the same ``.massgen/snapshots/agent_a/`` directory.  Appending the
    microsecond-timestamped session root name keeps them isolated.

    Args:
        base: Raw ``snapshot_storage`` value from YAML config, or None.

    Returns:
        Scoped path string (e.g., ``.massgen/snapshots/log_20260301_XXX``),
        or None if *base* is None.
    """
    if base is None:
        return None
    from pathlib import Path as _Path

    from .logger_config import get_log_session_root as _get_root

    try:
        session_root_name = _get_root().name
        return str(_Path(base) / session_root_name)
    except Exception:
        return base  # Fallback: return unchanged if session root unavailable


def _scope_agent_temporary_workspace(base: str | None) -> str | None:
    """Scope ``agent_temporary_workspace`` by the current log session root name.

    Two concurrent CLI processes using the same config would otherwise share
    the same temp workspace parent.  Appending the microsecond-timestamped
    session root name keeps them isolated -- process B's
    ``clear_temp_workspace()`` only removes its own scoped subdirectory.

    Args:
        base: Raw ``agent_temporary_workspace`` value from YAML config,
            or None.

    Returns:
        Scoped path string, or None if *base* is None.
    """
    if base is None:
        return None
    from pathlib import Path as _Path

    from .logger_config import get_log_session_root as _get_root

    try:
        session_root_name = _get_root().name
        return str(_Path(base) / session_root_name)
    except Exception:
        return base  # Fallback: return unchanged if session root unavailable


def create_simple_config(
    backend_type: str,
    model: str,
    system_message: str | None = None,
    base_url: str | None = None,
    ui_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a simple single-agent configuration."""
    backend_config = {"type": backend_type, "model": model}
    if base_url:
        backend_config["base_url"] = base_url

    # Add required workspace configuration for Claude Code backend
    if backend_type == "claude_code":
        backend_config["cwd"] = "workspace"

    # Use provided UI config or default to rich_terminal for CLI usage
    if ui_config is None:
        ui_config = {"display_type": "rich_terminal", "logging_enabled": True}

    config = {
        "agent": {
            "id": "agent1",
            "backend": backend_config,
            "system_message": system_message or "You are a helpful AI assistant.",
        },
        "ui": ui_config,
    }

    # Add orchestrator config with .massgen/ structure for Claude Code
    if backend_type == "claude_code":
        config["orchestrator"] = {
            "snapshot_storage": ".massgen/snapshots",
            "agent_temporary_workspace": ".massgen/temp_workspaces",
            # Note: session_storage is hardcoded to .massgen/sessions (not configurable)
        }

    return config


def apply_cli_cwd_context_path(
    config: dict[str, Any],
    cwd_context_mode: str | None,
) -> None:
    """Apply --cwd-context flag by injecting CWD into orchestrator context paths.

    Args:
        config: MassGen configuration dict (modified in-place).
        cwd_context_mode: CLI mode ("ro"/"read" or "rw"/"write"), or None.
    """
    if not cwd_context_mode:
        return

    mode = cwd_context_mode.lower()
    permission = "write" if mode in ("rw", "write") else "read"
    cwd_path = str(Path.cwd().resolve())

    orchestrator_cfg = config.setdefault("orchestrator", {})
    context_paths = orchestrator_cfg.get("context_paths")
    if not isinstance(context_paths, list):
        context_paths = []
        orchestrator_cfg["context_paths"] = context_paths

    existing_index = None
    for idx, entry in enumerate(context_paths):
        entry_path = entry.get("path") if isinstance(entry, dict) else entry
        if not entry_path:
            continue
        try:
            normalized_entry_path = str(Path(entry_path).resolve())
        except Exception:
            normalized_entry_path = str(entry_path)

        if normalized_entry_path == cwd_path:
            existing_index = idx
            break

    if existing_index is None:
        context_paths.append(
            {
                "path": cwd_path,
                "permission": permission,
            },
        )
        logger.info(
            f"[CLI] Added CWD to context_paths via --cwd-context: {cwd_path} ({permission})",
        )
        return

    existing = context_paths[existing_index]
    if isinstance(existing, dict):
        existing["path"] = cwd_path
        existing["permission"] = permission
    else:
        context_paths[existing_index] = {
            "path": cwd_path,
            "permission": permission,
        }
    logger.info(
        f"[CLI] Updated CWD context path via --cwd-context: {cwd_path} ({permission})",
    )


def validate_context_paths(config: dict[str, Any]) -> None:
    """Validate that all context paths in the config exist.

    Context paths can be either files or directories.
    File-level context paths allow access to specific files without exposing sibling files.
    Raises ConfigurationError with clear message if any paths don't exist.
    """
    orchestrator_cfg = config.get("orchestrator", {})
    context_paths = orchestrator_cfg.get("context_paths", [])

    missing_paths = []

    for context_path_config in context_paths:
        if isinstance(context_path_config, dict):
            path = context_path_config.get("path")
        else:
            # Handle string format for backwards compatibility
            path = context_path_config

        if path:
            path_obj = Path(path)
            if not path_obj.exists():
                missing_paths.append(path)

    if missing_paths:
        errors = ["Context paths not found:"]
        for path in missing_paths:
            errors.append(f"  - {path}")
        errors.append("\nPlease update your configuration with valid paths.")
        raise ConfigurationError("\n".join(errors))


def add_mode_flags_to_parser(parser: argparse.ArgumentParser) -> None:
    """Add mode bar toggle flags to an argparse parser.

    These flags mirror the TUI mode bar toggles, allowing CLI control
    of agent mode, coordination mode, refinement, and persona generation.
    """
    mode_group = parser.add_argument_group(
        "mode settings",
        "Override execution mode (mirrors TUI mode bar toggles)",
    )
    mode_group.add_argument(
        "--single-agent",
        nargs="?",
        const=True,
        default=None,
        metavar="AGENT_ID",
        help="Single-agent mode. Optionally specify agent ID (default: first agent). " "Overrides multi-agent config to use only one agent.",
    )
    mode_group.add_argument(
        "--coordination-mode",
        choices=["parallel", "decomposition"],
        default=None,
        help="Coordination mode: parallel (voting) or decomposition (subtask-based). " "Overrides coordination_mode from config file.",
    )
    mode_group.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: disable refinement. Agents produce one answer with no " "voting loop. Equivalent to TUI 'Refine OFF' toggle.",
    )
    mode_group.add_argument(
        "--personas",
        choices=["off", "perspective", "implementation", "methodology"],
        default=None,
        help="Enable parallel persona generation with specified diversity mode. " "'off' disables persona generation. Requires parallel coordination mode.",
    )


def validate_mode_flag_combinations(args: argparse.Namespace) -> list[str]:
    """Validate that CLI mode flag combinations are compatible.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if getattr(args, "single_agent", None) is not None and getattr(args, "coordination_mode", None) == "decomposition":
        errors.append(
            "--single-agent and --coordination-mode decomposition are incompatible. " "Decomposition requires multiple agents.",
        )

    personas = getattr(args, "personas", None)
    if personas is not None and personas != "off" and getattr(args, "coordination_mode", None) == "decomposition":
        errors.append(
            "--personas requires parallel coordination mode, not decomposition.",
        )

    if getattr(args, "web_quickstart", False) and getattr(args, "web", False):
        errors.append(
            "--web-quickstart already launches a dedicated browser setup flow; do not combine it with --web.",
        )

    quickstart_agents = getattr(args, "quickstart_agents", None)
    if quickstart_agents:
        if not getattr(args, "quickstart", False) or not getattr(args, "headless", False):
            errors.append(
                "--quickstart-agent requires --quickstart --headless.",
            )
        if getattr(args, "config_backend", None) or getattr(args, "config_model", None) or getattr(args, "config_agent_id", None) or getattr(args, "config_agents", None) is not None:
            errors.append(
                "--quickstart-agent cannot be combined with --config-backend, --config-model, --config-agent-id, or --config-agents.",
            )

    return errors


def apply_mode_flags_to_config(
    config: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    """Apply CLI mode flags to the config dict.

    Mirrors the logic in TuiModeState.get_orchestrator_overrides() from
    tui_modes.py, but applies overrides to the raw config dict before
    the orchestrator is constructed.
    """
    coordination_mode = getattr(args, "coordination_mode", None)
    quick = getattr(args, "quick", False)
    personas = getattr(args, "personas", None)
    single_agent = getattr(args, "single_agent", None)

    # Nothing to do if no mode flags set
    if coordination_mode is None and not quick and personas is None:
        return

    if "orchestrator" not in config:
        config["orchestrator"] = {}
    orch = config["orchestrator"]

    # Coordination mode
    if coordination_mode is not None:
        orch["coordination_mode"] = "decomposition" if coordination_mode == "decomposition" else "voting"

    # Quick mode (refinement OFF)
    if quick:
        orch["max_new_answers_per_agent"] = 1
        orch["skip_final_presentation"] = True

        if single_agent is not None:
            # Single agent + quick = skip voting too
            orch["skip_voting"] = True
        else:
            # Multi-agent + quick = independent work, deferred single vote
            orch["disable_injection"] = True
            orch["defer_voting_until_all_answered"] = True
            orch["final_answer_strategy"] = "synthesize"

    # Personas
    if personas is not None:
        if "coordination" not in orch:
            orch["coordination"] = {}
        if personas == "off":
            if "persona_generator" in orch["coordination"]:
                orch["coordination"]["persona_generator"]["enabled"] = False
        else:
            orch["coordination"]["persona_generator"] = {
                "enabled": True,
                "diversity_mode": personas,
            }


def filter_agents_for_single_mode(
    agents: dict[str, Any],
    single_agent_arg: Any,
) -> dict[str, Any]:
    """Filter agents dict for --single-agent mode.

    Args:
        agents: Dict mapping agent IDs to agent objects.
        single_agent_arg: The parsed --single-agent value.
            None = no filtering, True = pick first, str = pick by ID.

    Returns:
        Filtered agents dict (single entry or unchanged).

    Raises:
        ValueError: If specified agent ID not found.
    """
    if single_agent_arg is None:
        return agents

    if single_agent_arg is True:
        # Pick first agent
        first_id = next(iter(agents.keys()))
        return {first_id: agents[first_id]}

    # Pick by ID
    agent_id = str(single_agent_arg)
    if agent_id not in agents:
        available = ", ".join(agents.keys())
        raise ValueError(
            f"Agent '{agent_id}' not found in config. " f"Available agents: {available}",
        )
    return {agent_id: agents[agent_id]}


def build_cli_mode_defaults(args: argparse.Namespace) -> dict[str, Any]:
    """Build a dict of CLI mode defaults for passing to the TUI.

    Returns an empty dict if no mode flags were set.
    """
    defaults: dict[str, Any] = {}

    single_agent = getattr(args, "single_agent", None)
    if single_agent is not None:
        defaults["agent_mode"] = "single"
        if single_agent is not True:
            defaults["selected_agent"] = str(single_agent)

    coordination_mode = getattr(args, "coordination_mode", None)
    if coordination_mode is not None:
        defaults["coordination_mode"] = coordination_mode

    personas = getattr(args, "personas", None)
    if personas is not None:
        defaults["personas"] = personas

    if getattr(args, "quick", False):
        defaults["refinement_enabled"] = False

    if getattr(args, "plan", False):
        defaults["plan_mode"] = "plan"
    elif getattr(args, "spec", False):
        defaults["plan_mode"] = "spec"

    return defaults


def _build_cli_overrides_dict(args: argparse.Namespace) -> dict[str, Any]:
    """Build a dict of CLI overrides for forwarding to the WebUI server.

    Extracts config-affecting CLI flags that would otherwise be lost when
    ``--web`` bypasses ``main()``.  Returns an empty dict when no flags apply.
    """
    overrides: dict[str, Any] = {}
    if getattr(args, "eval_criteria", None):
        overrides["eval_criteria"] = args.eval_criteria
    if getattr(args, "checklist_criteria_preset", None):
        overrides["checklist_criteria_preset"] = args.checklist_criteria_preset
    if getattr(args, "orchestrator_timeout", None) is not None:
        overrides["orchestrator_timeout"] = args.orchestrator_timeout
    if getattr(args, "cwd_context", None):
        overrides["cwd_context"] = args.cwd_context
    if getattr(args, "web_review", False):
        overrides["web_review"] = True
    return overrides


def _parse_coordination_config(coord_cfg: dict[str, Any]) -> "CoordinationConfig":
    """Parse a coordination config dict into a CoordinationConfig object.

    Centralizes the parsing logic used by run_question_with_history,
    run_single_question, and run_textual_interactive_mode.
    """
    from .agent_config import CoordinationConfig, PromptImproverConfig
    from .evaluation_criteria_generator import EvaluationCriteriaGeneratorConfig
    from .persona_generator import PersonaGeneratorConfig
    from .subagent.models import SubagentOrchestratorConfig
    from .task_decomposer import TaskDecomposerConfig

    # Parse persona_generator config if present
    persona_generator_config = PersonaGeneratorConfig()
    if "persona_generator" in coord_cfg:
        pg_cfg = coord_cfg["persona_generator"]
        persona_generator_config = PersonaGeneratorConfig(
            enabled=pg_cfg.get("enabled", False),
            diversity_mode=pg_cfg.get("diversity_mode", "perspective"),
            persona_guidelines=pg_cfg.get("persona_guidelines"),
            persist_across_turns=pg_cfg.get("persist_across_turns", False),
            after_first_answer=pg_cfg.get("after_first_answer", "drop"),
        )

    # Parse evaluation_criteria_generator config if present
    eval_criteria_config = EvaluationCriteriaGeneratorConfig()
    if "evaluation_criteria_generator" in coord_cfg:
        ec_cfg = coord_cfg["evaluation_criteria_generator"]
        eval_criteria_config = EvaluationCriteriaGeneratorConfig(
            enabled=ec_cfg.get("enabled", False),
            persist_across_turns=ec_cfg.get("persist_across_turns", False),
            min_criteria=ec_cfg.get("min_criteria", 4),
            max_criteria=ec_cfg.get("max_criteria", 10),
        )

    # Parse prompt_improver config if present
    prompt_improver_config = PromptImproverConfig()
    if "prompt_improver" in coord_cfg:
        pi_cfg = coord_cfg["prompt_improver"]
        prompt_improver_config = PromptImproverConfig(
            enabled=pi_cfg.get("enabled", False),
            persist_across_turns=pi_cfg.get("persist_across_turns", False),
        )

    # Parse task_decomposer config if present
    task_decomposer_config = TaskDecomposerConfig()
    if "task_decomposer" in coord_cfg:
        td_cfg = coord_cfg["task_decomposer"]
        task_decomposer_config = TaskDecomposerConfig(
            enabled=td_cfg.get("enabled", True),
            decomposition_guidelines=td_cfg.get("decomposition_guidelines"),
            timeout_seconds=td_cfg.get("timeout_seconds", 300),
        )

    # Parse subagent_orchestrator config if present
    subagent_orchestrator_config = None
    if "subagent_orchestrator" in coord_cfg:
        so_cfg = coord_cfg["subagent_orchestrator"]
        subagent_orchestrator_config = SubagentOrchestratorConfig.from_dict(so_cfg)

    return CoordinationConfig(
        enable_planning_mode=coord_cfg.get("enable_planning_mode", False),
        planning_mode_instruction=coord_cfg.get(
            "planning_mode_instruction",
            "During coordination, describe what you would do without actually executing actions. Only provide concrete implementation details without calling external APIs or tools.",
        ),
        max_orchestration_restarts=coord_cfg.get("max_orchestration_restarts", 0),
        enable_agent_task_planning=coord_cfg.get("enable_agent_task_planning", False),
        max_tasks_per_plan=coord_cfg.get("max_tasks_per_plan", 10),
        broadcast=coord_cfg.get("broadcast", False),
        broadcast_sensitivity=coord_cfg.get("broadcast_sensitivity", "medium"),
        response_depth=coord_cfg.get("response_depth", "medium"),
        broadcast_timeout=coord_cfg.get("broadcast_timeout", 300),
        shadow_timeout=coord_cfg.get("shadow_timeout", 90),
        broadcast_wait_by_default=coord_cfg.get("broadcast_wait_by_default", True),
        max_broadcasts_per_agent=coord_cfg.get("max_broadcasts_per_agent", 10),
        task_planning_filesystem_mode=coord_cfg.get("task_planning_filesystem_mode", False),
        enable_memory_filesystem_mode=coord_cfg.get("enable_memory_filesystem_mode", False),
        learning_capture_mode=coord_cfg.get("learning_capture_mode", "round"),
        disable_final_only_round_capture_fallback=coord_cfg.get(
            "disable_final_only_round_capture_fallback",
            False,
        ),
        compression_target_ratio=coord_cfg.get("compression_target_ratio", 0.20),
        use_skills=coord_cfg.get("use_skills", False),
        massgen_skills=coord_cfg.get("massgen_skills", []),
        skills_directory=coord_cfg.get("skills_directory", ".agent/skills"),
        load_previous_session_skills=coord_cfg.get("load_previous_session_skills", False),
        persona_generator=persona_generator_config,
        evaluation_criteria_generator=eval_criteria_config,
        prompt_improver=prompt_improver_config,
        pre_collab_voting_threshold=coord_cfg.get("pre_collab_voting_threshold"),
        enable_subagents=coord_cfg.get("enable_subagents", False),
        subagent_default_timeout=coord_cfg.get("subagent_default_timeout", 300),
        subagent_max_concurrent=coord_cfg.get("subagent_max_concurrent", 3),
        subagent_round_timeouts=coord_cfg.get("subagent_round_timeouts"),
        subagent_runtime_mode=coord_cfg.get("subagent_runtime_mode", "isolated"),
        subagent_runtime_fallback_mode=coord_cfg.get("subagent_runtime_fallback_mode"),
        subagent_host_launch_prefix=coord_cfg.get("subagent_host_launch_prefix"),
        subagent_orchestrator=subagent_orchestrator_config,
        background_subagents=coord_cfg.get("background_subagents"),
        use_two_tier_workspace=coord_cfg.get("use_two_tier_workspace", False),
        task_decomposer=task_decomposer_config,
        write_mode=coord_cfg.get("write_mode"),
        drift_conflict_policy=coord_cfg.get("drift_conflict_policy", "skip"),
        enable_changedoc=coord_cfg.get("enable_changedoc", True),
        subagent_types=coord_cfg.get("subagent_types"),
        round_evaluator_before_checklist=coord_cfg.get("round_evaluator_before_checklist", False),
        orchestrator_managed_round_evaluator=coord_cfg.get("orchestrator_managed_round_evaluator", False),
        round_evaluator_skip_synthesis=coord_cfg.get("round_evaluator_skip_synthesis", False),
        round_evaluator_refine=coord_cfg.get("round_evaluator_refine", False),
        round_evaluator_transformation_pressure=coord_cfg.get("round_evaluator_transformation_pressure", "balanced"),
        enable_execution_trace_analyzer=coord_cfg.get("enable_execution_trace_analyzer", False),
        auto_trace_analysis=coord_cfg.get("auto_trace_analysis", False),
        evolving_criteria=coord_cfg.get("evolving_criteria", False),
        evolving_criteria_score_threshold=coord_cfg.get("evolving_criteria_score_threshold", 8),
        evolving_criteria_max_evolutions=coord_cfg.get("evolving_criteria_max_evolutions", 2),
        evolving_criteria_min_high_score_count=coord_cfg.get("evolving_criteria_min_high_score_count", 2),
        evolving_criteria_timeout=coord_cfg.get("evolving_criteria_timeout", 300),
        enable_evaluator_personas=coord_cfg.get("enable_evaluator_personas", False),
        enable_quality_rethink_on_iteration=coord_cfg.get("enable_quality_rethink_on_iteration", False),
        enable_novelty_on_iteration=coord_cfg.get("enable_novelty_on_iteration", False),
        novelty_injection=coord_cfg.get("novelty_injection", "none"),
        improvements=coord_cfg.get("improvements", {}) or {},
        checklist_criteria_preset=coord_cfg.get("checklist_criteria_preset"),
        checklist_criteria_inline=coord_cfg.get("checklist_criteria_inline"),
        resume_from_log=coord_cfg.get("resume_from_log"),
        checkpoint_enabled=coord_cfg.get("checkpoint_enabled", False),
        checkpoint_mode=coord_cfg.get("checkpoint_mode", "conversation"),
        checkpoint_guidance=coord_cfg.get("checkpoint_guidance", ""),
        checkpoint_gated_patterns=coord_cfg.get("checkpoint_gated_patterns", []),
        web_review=coord_cfg.get("web_review", False),
        fast_iteration_mode=coord_cfg.get("fast_iteration_mode", False),
    )


def inject_prompt_context_paths(
    prompt: str,
    config: dict[str, Any],
    parse_at_references: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Parse @references from prompt and inject into config.

    Extracts @path and @path:w references from the prompt, validates that
    the paths exist, and injects them into config["orchestrator"]["context_paths"].

    This displays extracted paths to the user for transparency when parsing is enabled.

    Args:
        prompt: User's raw prompt potentially containing @references.
        config: MassGen configuration dict (modified in-place).
        parse_at_references: Whether to parse @path references from prompt text.

    Returns:
        Tuple of (cleaned_prompt, modified_config).

    Raises:
        ConfigurationError: If any referenced paths don't exist.
    """
    if not parse_at_references:
        return prompt, config

    from .path_handling import PromptParserError, parse_prompt_for_context

    try:
        parsed = parse_prompt_for_context(prompt)
    except PromptParserError as e:
        raise ConfigurationError(str(e)) from e

    if not parsed.context_paths:
        return prompt, config

    # Display extracted paths to user (always, for transparency)
    print(f"\n{BRIGHT_CYAN}📂 Context paths from prompt:{RESET}")
    for ctx in parsed.context_paths:
        perm_icon = "📝" if ctx["permission"] == "write" else "📖"
        print(f"   {perm_icon} {ctx['path']} ({ctx['permission']})")

    # Show consolidation suggestions
    for suggestion in parsed.suggestions:
        print(f"   {BRIGHT_YELLOW}💡 {suggestion}{RESET}")

    print()

    # Inject into config
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "context_paths" not in config["orchestrator"]:
        config["orchestrator"]["context_paths"] = []

    # Add extracted paths (avoiding duplicates)
    existing_paths = {p.get("path") for p in config["orchestrator"]["context_paths"]}
    for ctx in parsed.context_paths:
        if ctx["path"] not in existing_paths:
            config["orchestrator"]["context_paths"].append(ctx)
            existing_paths.add(ctx["path"])
        else:
            # If path exists but with different permission, upgrade to write if needed
            for existing in config["orchestrator"]["context_paths"]:
                if existing.get("path") == ctx["path"] and ctx["permission"] == "write":
                    existing["permission"] = "write"
                    break

    return parsed.cleaned_prompt, config


def relocate_filesystem_paths(config: dict[str, Any]) -> None:
    """Relocate filesystem paths (orchestrator paths and agent workspaces) to be under .massgen/ directory.

    Modifies the config in-place to ensure all MassGen state is organized
    under .massgen/ for clean project structure.
    """
    massgen_dir = Path(".massgen")

    # Relocate orchestrator paths
    orchestrator_cfg = config.get("orchestrator", {})
    if orchestrator_cfg:
        path_fields = [
            "snapshot_storage",
            "agent_temporary_workspace",
            # Note: session_storage is not in this list - it's hardcoded to .massgen/sessions
            # Old configs with session_storage are backwards compatible (value is ignored)
        ]

        for field in path_fields:
            if field in orchestrator_cfg:
                user_path = orchestrator_cfg[field]
                # If user provided an absolute path or already starts with .massgen/, keep as-is
                if Path(user_path).is_absolute() or user_path.startswith(".massgen/"):
                    continue
                # Otherwise, relocate under .massgen/
                orchestrator_cfg[field] = str(massgen_dir / user_path)

    # Relocate agent workspaces (cwd fields)
    agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
    for agent_data in agent_entries:
        backend_config = agent_data.get("backend", {})
        if "cwd" in backend_config:
            user_cwd = backend_config["cwd"]
            # If user provided an absolute path or already starts with .massgen/, keep as-is
            if Path(user_cwd).is_absolute() or user_cwd.startswith(".massgen/"):
                continue
            # Otherwise, relocate under .massgen/workspaces/
            backend_config["cwd"] = str(massgen_dir / "workspaces" / user_cwd)


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

    # Get previous turns and winning agents history from session_info if already loaded,
    # otherwise restore from session storage for multi-turn conversations
    previous_turns = session_info.get("previous_turns", [])
    winning_agents_history = session_info.get("winning_agents_history", [])

    # If not provided in session_info but session_id exists, restore from storage
    if not previous_turns and not winning_agents_history and session_id:
        from massgen.session import restore_session

        try:
            session_state = restore_session(session_id, SESSION_STORAGE)
            if session_state:
                previous_turns = session_state.previous_turns
                winning_agents_history = session_state.winning_agents_history
        except (ValueError, Exception) as e:
            # Session doesn't exist yet or has no turns - that's ok for new sessions
            logger.debug(f"Could not restore session for previous turns: {e}")

    # Get generated personas from session info if persist_across_turns is enabled
    # By default, generate new personas each turn (persist_across_turns=False)
    generated_personas = None
    if (
        hasattr(orchestrator_config, "coordination_config")
        and orchestrator_config.coordination_config
        and orchestrator_config.coordination_config.persona_generator
        and orchestrator_config.coordination_config.persona_generator.persist_across_turns
    ):
        generated_personas = session_info.get("generated_personas")
        if generated_personas:
            logger.info("[CLI] Reusing persisted personas from previous turn")

    # Get generated evaluation criteria from session info if persist_across_turns is enabled
    generated_evaluation_criteria = None
    if (
        hasattr(orchestrator_config, "coordination_config")
        and orchestrator_config.coordination_config
        and hasattr(orchestrator_config.coordination_config, "evaluation_criteria_generator")
        and orchestrator_config.coordination_config.evaluation_criteria_generator
        and orchestrator_config.coordination_config.evaluation_criteria_generator.persist_across_turns
    ):
        raw_criteria = session_info.get("generated_evaluation_criteria")
        if raw_criteria:
            from .evaluation_criteria_generator import GeneratedCriterion

            generated_evaluation_criteria = [
                GeneratedCriterion(
                    id=c.get("id", f"E{i + 1}"),
                    text=c.get("text") or c.get("description") or c.get("name", ""),
                    category=c.get("category", "standard"),
                )
                for i, c in enumerate(raw_criteria)
                if c.get("text") or c.get("description") or c.get("name")
            ]
            logger.info("[CLI] Reusing persisted evaluation criteria from previous turn")

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

    # Store generated personas in session_info for persistence across turns
    # This allows subsequent turns to reuse personas instead of regenerating
    if orchestrator.get_generated_personas():
        session_info["generated_personas"] = orchestrator.get_generated_personas()

    # Store generated evaluation criteria in session_info for persistence across turns
    if orchestrator.get_generated_evaluation_criteria():
        session_info["generated_evaluation_criteria"] = [{"id": c.id, "text": c.text, "category": c.category} for c in orchestrator.get_generated_evaluation_criteria()]

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


def prompt_for_context_paths(
    original_config: dict[str, Any],
    orchestrator_cfg: dict[str, Any],
) -> bool:
    """Prompt user to add context paths in interactive mode.

    Returns True if config was modified, False otherwise.
    """
    # Check if filesystem is enabled (at least one agent has cwd)
    agent_entries = [original_config["agent"]] if "agent" in original_config else original_config.get("agents", [])
    has_filesystem = any("cwd" in agent.get("backend", {}) for agent in agent_entries)

    if not has_filesystem:
        return False

    # Skip prompting if context_paths was explicitly configured (even if empty)
    # This means user already made a decision during config creation (e.g., quickstart)
    if "context_paths" in orchestrator_cfg:
        return False

    # Show current context paths
    existing_paths = orchestrator_cfg.get("context_paths", [])
    cwd = Path.cwd()

    # Use Rich for better display
    from rich.console import Console as RichConsole
    from rich.panel import Panel as RichPanel

    rich_console = RichConsole()

    # Build context paths display
    context_content = []
    if existing_paths:
        for path_config in existing_paths:
            path = path_config.get("path") if isinstance(path_config, dict) else path_config
            permission = path_config.get("permission", "read") if isinstance(path_config, dict) else "read"
            context_content.append(
                f"  [green]✓[/green] {path} [dim]({permission})[/dim]",
            )
    else:
        context_content.append("  [yellow]No context paths configured[/yellow]")

    context_panel = RichPanel(
        "\n".join(context_content),
        title="[bold bright_cyan]📂 Context Paths[/bold bright_cyan]",
        border_style="cyan",
        padding=(0, 2),
        width=80,
    )
    rich_console.print(context_panel)
    print()

    # Check if CWD is already in context paths
    cwd_str = str(cwd)
    cwd_already_added = any((path_config.get("path") if isinstance(path_config, dict) else path_config) == cwd_str for path_config in existing_paths)

    if not cwd_already_added:
        # Create prompt panel
        prompt_content = [
            "[bold cyan]Add current directory as context path?[/bold cyan]",
            f"  [yellow]{cwd}[/yellow]",
            "",
            "  [dim]Context paths give agents access to your project files.[/dim]",
            "  [dim]• Read-only during coordination (prevents conflicts)[/dim]",
            "  [dim]• Write permission for final agent to save results[/dim]",
            "",
            "  [dim]Options:[/dim]",
            "  [green]Y[/green] → Add with write permission (default)",
            "  [cyan]P[/cyan] → Add with protected paths (e.g., .env, secrets)",
            "  [yellow]N[/yellow] → Skip",
            "  [blue]C[/blue] → Add custom path",
        ]
        prompt_panel = RichPanel(
            "\n".join(prompt_content),
            border_style="cyan",
            padding=(1, 2),
            width=80,
        )
        rich_console.print(prompt_panel)
        print()
        try:
            response = input(f"   {BRIGHT_CYAN}Your choice [Y/P/N/C]:{RESET} ").strip().lower()

            if response in ["y", "yes", ""]:
                # Add CWD with write permission
                if "context_paths" not in orchestrator_cfg:
                    orchestrator_cfg["context_paths"] = []
                orchestrator_cfg["context_paths"].append(
                    {"path": cwd_str, "permission": "write"},
                )
                print(f"   {BRIGHT_GREEN}✅ Added: {cwd} (write){RESET}", flush=True)
                return True
            elif response in ["p", "protected"]:
                # Add CWD with write permission and protected paths
                protected_paths = []
                print(
                    f"\n   {BRIGHT_CYAN}Enter protected paths (one per line, empty to finish):{RESET}",
                    flush=True,
                )
                print(
                    f"   {BRIGHT_YELLOW}Tip: Protected paths are relative to {cwd}{RESET}",
                    flush=True,
                )
                while True:
                    protected_input = input(f"   {BRIGHT_CYAN}→{RESET} ").strip()
                    if not protected_input:
                        break
                    protected_paths.append(protected_input)
                    print(
                        f"     {BRIGHT_GREEN}✓ Added: {protected_input}{RESET}",
                        flush=True,
                    )

                if "context_paths" not in orchestrator_cfg:
                    orchestrator_cfg["context_paths"] = []

                context_config = {"path": cwd_str, "permission": "write"}
                if protected_paths:
                    context_config["protected_paths"] = protected_paths

                orchestrator_cfg["context_paths"].append(context_config)
                print(
                    f"\n   {BRIGHT_GREEN}✅ Added: {cwd} (write) with {len(protected_paths)} protected path(s){RESET}",
                    flush=True,
                )
                return True
            elif response in ["n", "no"]:
                # User explicitly declined
                return False
            elif response in ["c", "custom"]:
                # Loop until valid path or user cancels
                print()
                while True:
                    custom_path = input(
                        f"   {BRIGHT_CYAN}Enter path (absolute or relative):{RESET} ",
                    ).strip()
                    if not custom_path:
                        print(f"   {BRIGHT_YELLOW}⚠️  Cancelled{RESET}", flush=True)
                        return False

                    # Resolve to absolute path
                    abs_path = str(Path(custom_path).resolve())

                    # Check if path exists
                    if not Path(abs_path).exists():
                        print(
                            f"   {BRIGHT_RED}✗ Path does not exist: {abs_path}{RESET}",
                            flush=True,
                        )
                        retry = input(f"   {BRIGHT_CYAN}Try again? [Y/n]:{RESET} ").strip().lower()
                        if retry in ["n", "no"]:
                            return False
                        continue

                    # Valid path (file or directory), ask for permission
                    permission = (
                        input(
                            f"   {BRIGHT_CYAN}Permission [read/write] (default: write):{RESET} ",
                        )
                        .strip()
                        .lower()
                        or "write"
                    )
                    if permission not in ["read", "write"]:
                        permission = "write"

                    # Ask about protected paths if write permission
                    protected_paths = []
                    if permission == "write":
                        add_protected = (
                            input(
                                f"   {BRIGHT_CYAN}Add protected paths? [y/N]:{RESET} ",
                            )
                            .strip()
                            .lower()
                        )
                        if add_protected in ["y", "yes"]:
                            print(
                                f"   {BRIGHT_CYAN}Enter protected paths (one per line, empty to finish):{RESET}",
                                flush=True,
                            )
                            while True:
                                protected_input = input(
                                    f"   {BRIGHT_CYAN}→{RESET} ",
                                ).strip()
                                if not protected_input:
                                    break
                                protected_paths.append(protected_input)
                                print(
                                    f"     {BRIGHT_GREEN}✓ Added: {protected_input}{RESET}",
                                    flush=True,
                                )

                    if "context_paths" not in orchestrator_cfg:
                        orchestrator_cfg["context_paths"] = []

                    context_config = {"path": abs_path, "permission": permission}
                    if protected_paths:
                        context_config["protected_paths"] = protected_paths

                    orchestrator_cfg["context_paths"].append(context_config)
                    if protected_paths:
                        print(
                            f"   {BRIGHT_GREEN}✅ Added: {abs_path} ({permission}) with {len(protected_paths)} protected path(s){RESET}",
                            flush=True,
                        )
                    else:
                        print(
                            f"   {BRIGHT_GREEN}✅ Added: {abs_path} ({permission}){RESET}",
                            flush=True,
                        )
                    return True
            else:
                # Invalid response - clarify options
                print(
                    f"\n   {BRIGHT_RED}✗ Invalid option: '{response}'{RESET}",
                    flush=True,
                )
                print(
                    f"   {BRIGHT_YELLOW}Please choose: Y (yes), P (protected), N (no), or C (custom){RESET}",
                    flush=True,
                )
                return False
        except (KeyboardInterrupt, EOFError):
            print()  # New line after Ctrl+C
            return False

    return False


def show_available_examples():
    """Display available example configurations from package."""
    try:
        from importlib.resources import files

        configs_root = files("massgen") / "configs"

        print(f"\n{BRIGHT_CYAN}Available Example Configurations{RESET}")
        print("=" * 60)

        # Organize by category
        categories = {}
        for config_file in sorted(configs_root.rglob("*.yaml")):
            # Get relative path from configs root
            rel_path = str(config_file).replace(str(configs_root) + "/", "")
            # Extract category (first directory)
            parts = rel_path.split("/")
            category = parts[0] if len(parts) > 1 else "root"

            if category not in categories:
                categories[category] = []

            # Create a short name for @examples/
            # Use the path without .yaml extension
            short_name = rel_path.replace(".yaml", "").replace("/", "_")

            categories[category].append((short_name, rel_path))

        # Display categories
        for category, configs in sorted(categories.items()):
            print(f"\n{BRIGHT_YELLOW}{category.title()}:{RESET}")
            for short_name, rel_path in configs[:10]:  # Limit to avoid overwhelming
                print(f"  {BRIGHT_GREEN}@examples/{short_name:<40}{RESET} {rel_path}")

            if len(configs) > 10:
                print(f"  ... and {len(configs) - 10} more")

        print(f"\n{BRIGHT_BLUE}Usage:{RESET}")
        print('  massgen --config @examples/SHORTNAME "Your question"')
        print("  massgen --example SHORTNAME > my-config.yaml")
        print()

    except Exception as e:
        print(f"Error listing examples: {e}")
        print("Examples may not be available (development mode?)")


def print_example_config(name: str):
    """Print an example config to stdout.

    Args:
        name: Name of the example (can include or exclude @examples/ prefix)
    """
    try:
        # Remove @examples/ prefix if present
        if name.startswith("@examples/"):
            name = name[10:]

        # Try to resolve the config
        resolved = resolve_config_path(f"@examples/{name}")
        if resolved:
            with open(resolved) as f:
                print(f.read())
        else:
            print(f"Error: Could not find example '{name}'", file=sys.stderr)
            print("Use --list-examples to see available configs", file=sys.stderr)
            sys.exit(1)

    except ConfigurationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error printing example config: {e}", file=sys.stderr)
        sys.exit(1)


def discover_available_configs() -> dict[str, list[tuple[str, Path]]]:
    """Discover all available configuration files.

    Returns:
        Dict with categories as keys and list of (display_name, path) tuples as values
    """
    configs = {
        "User Configs": [],
        "Project Configs": [],
        "Current Directory": [],
        "Package Examples": [],
    }

    # 1. User configs (~/.config/massgen/agents/)
    user_agents_dir = Path.home() / ".config/massgen/agents"
    if user_agents_dir.exists():
        for config_file in sorted(user_agents_dir.glob("*.yaml")):
            display_name = config_file.stem
            configs["User Configs"].append((display_name, config_file))

    # 2. Project configs (.massgen/)
    project_config_dir = Path.cwd() / ".massgen"
    if project_config_dir.exists():
        for config_file in sorted(project_config_dir.glob("*.yaml")):
            display_name = f".massgen/{config_file.name}"
            configs["Project Configs"].append((display_name, config_file))

    # 3. Current directory (*.yaml files, excluding .massgen/ and non-massgen configs)
    # Filter out common non-massgen YAML files
    exclude_patterns = {
        ".pre-commit-config.yaml",
        ".readthedocs.yaml",
        ".github",
        "docker-compose",
        "ansible",
        "kubernetes",
    }

    for config_file in sorted(Path.cwd().glob("*.yaml")):
        # Skip if inside .massgen/ (already covered)
        if ".massgen" in str(config_file):
            continue

        # Skip common non-massgen config files
        file_name = config_file.name.lower()
        if any(pattern in file_name for pattern in exclude_patterns):
            continue

        display_name = config_file.name
        configs["Current Directory"].append((display_name, config_file))

    # 4. Package examples (massgen/configs/)
    try:
        from importlib.resources import files

        configs_root = files("massgen") / "configs"

        # Organize by subdirectory
        for config_file in sorted(configs_root.rglob("*.yaml")):
            # Get relative path from configs root
            rel_path = str(config_file).replace(str(configs_root) + "/", "")
            # Skip README and docs
            if "README" in rel_path or "BACKEND_CONFIGURATION" in rel_path:
                continue
            # Use relative path as display name
            display_name = rel_path.replace(".yaml", "")
            configs["Package Examples"].append((display_name, Path(str(config_file))))

    except Exception as e:
        logger.warning(f"Could not load package examples: {e}")

    # Remove empty categories
    configs = {k: v for k, v in configs.items() if v}

    return configs


def interactive_config_selector() -> str | None:
    """Interactively select a configuration file.

    Shows user/project/current directory configs directly in a flat list.
    Package examples are shown hierarchically (category → config).

    Returns:
        Path to selected config file, or None if cancelled
    """
    # Create console instance for rich output
    selector_console = Console()

    # Discover all available configs
    configs = discover_available_configs()

    if not configs:
        selector_console.print(
            "\n[yellow]⚠️  No configurations found![/yellow]",
        )
        selector_console.print("[dim]Create one with: massgen --init[/dim]\n")
        return None

    # Create a summary table showing what's available
    summary_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    summary_table.add_column("Category", style="bright_cyan", no_wrap=True, width=25)
    summary_table.add_column("Count", justify="center", style="bright_yellow", width=10)
    summary_table.add_column("Location", style="dim")

    # Build summary and choices
    choices = []

    # Build summary table (overview only - no duplication)
    # User configs
    if "User Configs" in configs and configs["User Configs"]:
        summary_table.add_row(
            "👤 Your Configs",
            str(len(configs["User Configs"])),
            "~/.config/massgen/agents/",
        )
        choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["User Configs"]:
            choices.append(
                questionary.Choice(
                    title=f"  👤  {display_name}",
                    value=str(path),
                ),
            )

    # Project configs
    if "Project Configs" in configs and configs["Project Configs"]:
        summary_table.add_row(
            "📁 Project Configs",
            str(len(configs["Project Configs"])),
            ".massgen/",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        else:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["Project Configs"]:
            choices.append(
                questionary.Choice(
                    title=f"  📁  {display_name}",
                    value=str(path),
                ),
            )

    # Current directory configs
    if "Current Directory" in configs and configs["Current Directory"]:
        summary_table.add_row(
            "📂 Current Directory",
            str(len(configs["Current Directory"])),
            f"*.yaml in {Path.cwd().name}/",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        else:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["Current Directory"]:
            choices.append(
                questionary.Choice(
                    title=f"  📂  {display_name}",
                    value=str(path),
                ),
            )

    # Package examples
    if "Package Examples" in configs and configs["Package Examples"]:
        summary_table.add_row(
            "📦 Package Examples",
            str(len(configs["Package Examples"])),
            "Built-in examples (hierarchical browser)",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        choices.append(
            questionary.Choice(
                title=f"  📦  Browse {len(configs['Package Examples'])} example configs  →",
                value="__browse_examples__",
            ),
        )

    # Display summary table in a panel
    selector_console.print()
    selector_console.print(
        Panel(
            summary_table,
            title="[bold bright_cyan]🚀 Select a Configuration[/bold bright_cyan]",
            border_style="bright_cyan",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add cancel option
    choices.append(questionary.Separator("\n─────────────────────────────────"))
    choices.append(questionary.Choice(title="  ❌  Cancel", value="__cancel__"))

    # Show the selector
    selector_console.print()
    selected = questionary.select(
        "Select a configuration:",
        choices=choices,
        use_shortcuts=True,
        use_arrow_keys=True,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected is None or selected == "__cancel__":
        selector_console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    # If user wants to browse package examples, show hierarchical navigation
    if selected == "__browse_examples__":
        return _select_package_example(configs["Package Examples"], selector_console)

    # Otherwise, return the selected config path
    selector_console.print(
        f"\n[bold green]✓ Selected:[/bold green] [cyan]{selected}[/cyan]\n",
    )
    return selected


def _select_package_example(
    examples: list[tuple[str, Path]],
    console: Console,
) -> str | None:
    """Show hierarchical navigation for package examples.

    Args:
        examples: List of (display_name, path) tuples
        console: Rich console for output

    Returns:
        Path to selected config, or None if cancelled/back
    """
    # Organize examples by category (first directory in path)
    categories = {}
    for display_name, path in examples:
        # Extract category from display name (e.g., "basic/multi/config" -> "basic")
        parts = display_name.split("/")
        category = parts[0] if len(parts) > 1 else "other"

        if category not in categories:
            categories[category] = []
        categories[category].append((display_name, path))

    # Emoji mapping for categories
    category_emojis = {
        "basic": "🎯",
        "tools": "🛠️",
        "providers": "🌐",
        "configs": "⚙️",
        "other": "📋",
    }

    # Create category summary table
    category_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    category_table.add_column("Category", style="bright_cyan", no_wrap=True, width=20)
    category_table.add_column(
        "Count",
        justify="center",
        style="bright_yellow",
        width=10,
    )
    category_table.add_column("Description", style="dim")

    # Category descriptions
    category_descriptions = {
        "basic": "Simple configurations for getting started",
        "tools": "Configs demonstrating tool integrations",
        "providers": "Provider-specific example configs",
        "configs": "Advanced configuration examples",
        "other": "Miscellaneous configurations",
    }

    # Build category table and choices
    category_choices = []
    for category in sorted(categories.keys()):
        count = len(categories[category])
        emoji = category_emojis.get(category, "📁")
        description = category_descriptions.get(category, "Example configurations")

        category_table.add_row(
            f"{emoji} {category.title()}",
            str(count),
            description,
        )

        category_choices.append(
            questionary.Choice(
                title=f"  {emoji}  {category.title()}  ({count} config{'s' if count != 1 else ''})",
                value=category,
            ),
        )

    # Display category summary in a panel
    console.print()
    console.print(
        Panel(
            category_table,
            title="[bold bright_yellow]📦 Package Examples - Select Category[/bold bright_yellow]",
            border_style="bright_yellow",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add back option
    category_choices.append(
        questionary.Separator("\n─────────────────────────────────"),
    )
    category_choices.append(
        questionary.Choice(title="  ← Back to main menu", value="__back__"),
    )

    # Step 1: Select category
    console.print()
    selected_category = questionary.select(
        "Select a category:",
        choices=category_choices,
        use_shortcuts=True,
        use_arrow_keys=True,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected_category is None or selected_category == "__cancel__":
        console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    if selected_category == "__back__":
        # Go back to main selector
        return interactive_config_selector()

    # Create configs table
    emoji = category_emojis.get(selected_category, "📁")
    configs_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    configs_table.add_column("#", style="dim", width=5, justify="right")
    configs_table.add_column("Configuration", style="bright_cyan")

    # Build config choices and table
    config_choices = []
    for idx, (display_name, path) in enumerate(
        sorted(categories[selected_category]),
        1,
    ):
        # Show relative path within category
        short_name = display_name.replace(f"{selected_category}/", "")
        configs_table.add_row(str(idx), short_name)
        config_choices.append(
            questionary.Choice(
                title=f"  {idx:2d}. {short_name}",
                value=str(path),
            ),
        )

    # Display configs in a panel
    console.print()
    console.print(
        Panel(
            configs_table,
            title=f"[bold bright_green]{emoji} {selected_category.title()} Configurations[/bold bright_green]",
            border_style="bright_green",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add back option
    config_choices.append(questionary.Separator("\n─────────────────────────────────"))
    config_choices.append(
        questionary.Choice(title="  ← Back to categories", value="__back__"),
    )

    # Step 2: Select config
    # For large lists: disable shortcuts (max 36) and enable search filter for better UX
    # Note: When search filter is enabled, j/k keys must be disabled (they conflict with search)
    use_shortcuts = len(config_choices) <= 36
    use_search_filter = len(config_choices) > 36
    console.print()
    selected_config = questionary.select(
        "Select a configuration:",
        choices=config_choices,
        use_shortcuts=use_shortcuts,
        use_arrow_keys=True,
        use_search_filter=use_search_filter,
        use_jk_keys=not use_search_filter,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected_config is None or selected_config == "__cancel__":
        console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    if selected_config == "__back__":
        # Recursively call to go back to category selection
        return _select_package_example(examples, console)

    # Return the selected config path
    console.print(
        f"\n[bold green]✓ Selected:[/bold green] [cyan]{selected_config}[/cyan]\n",
    )
    return selected_config


def check_docker_available() -> bool:
    """Check if Docker is installed, running, and MassGen images are available.

    Returns:
        True if Docker is ready with MassGen images, False otherwise
    """
    from massgen.utils.docker_diagnostics import diagnose_docker

    diagnostics = diagnose_docker()
    return diagnostics.is_available


def get_docker_diagnostics():
    """Get detailed Docker diagnostics for error reporting.

    Returns:
        DockerDiagnostics object with full diagnostic information
    """
    from massgen.utils.docker_diagnostics import diagnose_docker

    return diagnose_docker()


def setup_docker() -> None:
    """Pull MassGen Docker executor images from GitHub Container Registry.

    Shows full diagnostics checklist and only offers to pull missing images.
    """
    import subprocess

    import questionary
    from questionary import Style

    from massgen.utils.docker_diagnostics import diagnose_docker

    print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
    print(f"{BRIGHT_CYAN}  🐳  MassGen Docker Setup{RESET}")
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}\n")

    # Run comprehensive diagnostics INCLUDING image check
    print(f"{BRIGHT_CYAN}Checking Docker status...{RESET}\n")
    diagnostics = diagnose_docker(check_images=True)

    # Display full diagnostics checklist
    version_info = f" ({diagnostics.docker_version})" if diagnostics.docker_version else ""
    binary_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.binary_installed else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {binary_status} Docker binary installed{version_info}")

    pip_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.pip_library_installed else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {pip_status} Docker Python library")

    daemon_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.daemon_running else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {daemon_status} Docker daemon running")

    perm_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.has_permissions else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {perm_status} Permissions OK")

    # If not available, show error and resolution steps
    if not diagnostics.is_available:
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return

    # Define available images with metadata
    AVAILABLE_IMAGES = [
        {
            "name": "ghcr.io/massgen/mcp-runtime-sudo:latest",
            "description": "Sudo image (recommended - allows package installation)",
            "default": True,  # Pre-selected by default
        },
        {
            "name": "ghcr.io/massgen/mcp-runtime:latest",
            "description": "Standard image (no sudo access)",
            "default": False,
        },
    ]

    # Show installed images status
    print(f"\n{BRIGHT_CYAN}Installed Images:{RESET}")
    installed_images = []
    missing_images = []
    for img in AVAILABLE_IMAGES:
        img_name = img["name"]
        if diagnostics.images_available.get(img_name, False):
            print(f"  {BRIGHT_GREEN}✓{RESET} {img_name}")
            installed_images.append(img_name)
        else:
            print(f"  {BRIGHT_RED}✗{RESET} {img_name}")
            missing_images.append(img)

    # If all images are installed, we're done
    if not missing_images:
        print(f"\n{BRIGHT_GREEN}✅ All Docker images are already installed!{RESET}\n")
        return

    # Create questionary style matching the rest of the CLI
    custom_style = Style(
        [
            ("qmark", "fg:#00CED1 bold"),
            ("question", "fg:#00CED1 bold"),
            ("answer", "fg:#32CD32 bold"),
            ("pointer", "fg:#00CED1 bold"),
            ("highlighted", "fg:#00CED1 bold"),
            ("selected", "fg:#32CD32"),
            ("separator", "fg:#6C6C6C"),
            ("instruction", "fg:#A9A9A9"),
        ],
    )

    # Only offer to pull MISSING images
    print(f"\n{BRIGHT_CYAN}Pull missing images?{RESET}")
    print(f"{BRIGHT_YELLOW}(Use Space to select/deselect, Enter to confirm){RESET}\n")

    try:
        # Only show missing images in the selection
        choices = [
            questionary.Choice(
                title=f"{img['description']}",
                value=img["name"],
                checked=img["default"],
            )
            for img in missing_images
        ]

        selected_images = questionary.checkbox(
            "",
            choices=choices,
            style=custom_style,
        ).ask()

        if selected_images is None:  # User cancelled (Ctrl+C)
            print(f"\n{BRIGHT_YELLOW}Setup cancelled{RESET}\n")
            return

        if not selected_images:
            print(
                f"\n{BRIGHT_YELLOW}No images selected. Skipping Docker setup.{RESET}\n",
            )
            return

    except (KeyboardInterrupt, EOFError):
        print(f"\n{BRIGHT_YELLOW}Setup cancelled{RESET}\n")
        return

    # Pull images with real-time progress display
    print(f"\n{BRIGHT_CYAN}Pulling {len(selected_images)} image(s)...{RESET}\n")

    success_count = 0
    failed_images = []

    for i, image in enumerate(selected_images, 1):
        print(f"{BRIGHT_CYAN}[{i}/{len(selected_images)}] Pulling {image}...{RESET}\n")

        try:
            # Don't capture output so Docker's progress bars are visible
            result = subprocess.run(
                ["docker", "pull", image],
                timeout=600,  # 10 minutes max per image
            )

            print()  # Add spacing after progress bars

            if result.returncode == 0:
                print(
                    f"{BRIGHT_GREEN}✓ [{i}/{len(selected_images)}] Completed: {image}{RESET}\n",
                )
                success_count += 1
            else:
                print(
                    f"{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Failed: {image}{RESET}\n",
                )
                failed_images.append(image)

        except subprocess.TimeoutExpired:
            print(
                f"\n{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Timed out: {image}{RESET}\n",
            )
            failed_images.append(image)
        except Exception as e:
            print(
                f"\n{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Error: {image} - {e}{RESET}\n",
            )
            failed_images.append(image)

    # Summary
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
    if success_count == len(selected_images):
        print(f"{BRIGHT_GREEN}  ✅ Docker setup complete!{RESET}")
        print(f"{BRIGHT_GREEN}  Successfully pulled {success_count} image(s){RESET}")
        print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
        print(
            f"\n{BRIGHT_CYAN}You can now use Docker execution mode in your configs.{RESET}",
        )
        print(
            f"{BRIGHT_CYAN}Run 'massgen --quickstart' to create a config with Docker enabled.{RESET}\n",
        )
    elif success_count > 0:
        print(
            f"{BRIGHT_YELLOW}  ⚠️  Partial success: {success_count}/{len(selected_images)} images pulled{RESET}",
        )
        print(f"{BRIGHT_YELLOW}{'=' * 60}{RESET}")
        if failed_images:
            print(f"\n{BRIGHT_YELLOW}Failed images:{RESET}")
            for img in failed_images:
                print(f"  - {img}")
        print()
    else:
        print(f"{BRIGHT_RED}  ❌ Docker setup failed{RESET}")
        print(f"{BRIGHT_RED}{'=' * 60}{RESET}")
        print(f"\n{BRIGHT_YELLOW}The images may not be published yet.{RESET}")
        print(f"{BRIGHT_YELLOW}You can build locally instead:{RESET}")
        print("  bash massgen/docker/build.sh --sudo\n")


def setup_computer_use_docker() -> bool:
    """Setup Docker container for Computer Use Agent (CUA) automation.

    Creates a Docker container with:
    - Ubuntu 22.04 with Xfce desktop
    - X11 virtual display (Xvfb) on :99
    - xdotool for GUI automation
    - Firefox and Chromium browsers
    - scrot for screenshots

    This is required for computer_use_docker_example.yaml configs.

    Returns:
        True if setup succeeded, False otherwise
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from massgen.utils.docker_diagnostics import diagnose_docker

    print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
    print(f"{BRIGHT_CYAN}  🖥️  Computer Use Docker Container Setup{RESET}")
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}\n")

    # Run comprehensive diagnostics (skip image check since we're setting up)
    print(f"{BRIGHT_CYAN}Checking Docker...{RESET}", end=" ", flush=True)
    diagnostics = diagnose_docker(check_images=False)

    # Check if Docker is ready (binary, pip library, permissions, daemon)
    if not diagnostics.binary_installed or not diagnostics.pip_library_installed:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    if not diagnostics.has_permissions:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    if not diagnostics.daemon_running:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    print(f"{BRIGHT_GREEN}✓{RESET}")
    if diagnostics.docker_version:
        print(f"{BRIGHT_CYAN}  Docker version: {diagnostics.docker_version}{RESET}")

    # Check if container already exists
    print(
        f"{BRIGHT_CYAN}Checking for existing container...{RESET}",
        end=" ",
        flush=True,
    )
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=cua-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "cua-container" in result.stdout:
            print(f"{BRIGHT_YELLOW}⚠{RESET}")
            print(f"\n{BRIGHT_YELLOW}Container 'cua-container' already exists{RESET}")

            # Check if it's running
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "name=cua-container",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "cua-container" in result.stdout:
                print(f"{BRIGHT_GREEN}✓ Container is already running{RESET}\n")
                return True
            else:
                print(
                    f"{BRIGHT_CYAN}Starting existing container...{RESET}",
                    end=" ",
                    flush=True,
                )
                result = subprocess.run(
                    ["docker", "start", "cua-container"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    print(f"{BRIGHT_GREEN}✓{RESET}\n")
                    return True
                else:
                    print(f"{BRIGHT_RED}✗{RESET}")
                    print(
                        f"{BRIGHT_YELLOW}Removing broken container and rebuilding...{RESET}",
                    )
                    subprocess.run(
                        ["docker", "rm", "-f", "cua-container"],
                        capture_output=True,
                        timeout=30,
                    )
        else:
            print(f"{BRIGHT_GREEN}✓{RESET}")
    except subprocess.TimeoutExpired:
        print(f"{BRIGHT_RED}✗{RESET}")

    # Create temporary directory for Dockerfile
    print(f"\n{BRIGHT_CYAN}Building Computer Use Docker image...{RESET}")
    print(
        f"{BRIGHT_YELLOW}This will download Ubuntu 22.04 and install desktop environment{RESET}",
    )
    print(
        f"{BRIGHT_YELLOW}Estimated time: 2-5 minutes (depending on internet speed){RESET}\n",
    )

    build_dir = tempfile.mkdtemp(prefix="massgen-cua-")
    dockerfile_path = Path(build_dir) / "Dockerfile"

    # Create Dockerfile (matching setup_docker_cua.sh)
    dockerfile_content = """FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites for adding PPAs
RUN apt-get update && apt-get install -y \\
    software-properties-common \\
    wget \\
    gnupg \\
    && rm -rf /var/lib/apt/lists/*

# Add Mozilla PPA for real Firefox (not snap)
RUN add-apt-repository -y ppa:mozillateam/ppa

# Set up apt preferences to prioritize Mozilla PPA
RUN echo 'Package: *' > /etc/apt/preferences.d/mozilla-firefox && \\
    echo 'Pin: release o=LP-PPA-mozillateam' >> /etc/apt/preferences.d/mozilla-firefox && \\
    echo 'Pin-Priority: 1001' >> /etc/apt/preferences.d/mozilla-firefox

# Install desktop environment and tools
RUN apt-get update && apt-get install -y \\
    xvfb \\
    x11vnc \\
    xfce4 \\
    xfce4-terminal \\
    firefox \\
    chromium-browser \\
    scrot \\
    xdotool \\
    imagemagick \\
    xdg-utils \\
    && rm -rf /var/lib/apt/lists/*

# Set Firefox as the default browser
RUN update-alternatives --set x-www-browser /usr/bin/firefox && \\
    update-alternatives --set gnome-www-browser /usr/bin/firefox && \\
    xdg-settings set default-web-browser firefox.desktop

# Set up X11
ENV DISPLAY=:99

# Start script
RUN echo '#!/bin/bash' > /start.sh && \\
    echo 'Xvfb :99 -screen 0 1280x800x24 &' >> /start.sh && \\
    echo 'sleep 2' >> /start.sh && \\
    echo 'xfce4-session &' >> /start.sh && \\
    echo 'tail -f /dev/null' >> /start.sh && \\
    chmod +x /start.sh

CMD ["/start.sh"]
"""

    try:
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        # Build the image
        print(f"{BRIGHT_CYAN}Step 1/2: Building Docker image 'cua-ubuntu'...{RESET}")
        result = subprocess.run(
            ["docker", "build", "-t", "cua-ubuntu", build_dir],
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            print(f"\n{BRIGHT_RED}❌ Docker build failed{RESET}\n")
            return False

        print(f"\n{BRIGHT_GREEN}✓ Image built successfully{RESET}\n")

        # Remove existing container if it exists
        subprocess.run(
            ["docker", "rm", "-f", "cua-container"],
            capture_output=True,
            timeout=10,
        )

        # Run the container
        print(
            f"{BRIGHT_CYAN}Step 2/2: Starting container 'cua-container'...{RESET}",
            end=" ",
            flush=True,
        )
        result = subprocess.run(
            ["docker", "run", "-d", "--name", "cua-container", "cua-ubuntu"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"{BRIGHT_RED}✗{RESET}")
            print(f"\n{BRIGHT_RED}❌ Failed to start container{RESET}")
            print(f"{BRIGHT_YELLOW}Error: {result.stderr}{RESET}\n")
            return False

        print(f"{BRIGHT_GREEN}✓{RESET}")

        # Wait for container to be ready
        import time

        time.sleep(3)

        # Test the container
        print(f"{BRIGHT_CYAN}Testing container...{RESET}", end=" ", flush=True)
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "DISPLAY=:99",
                "cua-container",
                "xdotool",
                "getmouselocation",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            print(f"{BRIGHT_GREEN}✓{RESET}")
            print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
            print(f"{BRIGHT_GREEN}  ✅ Computer Use Docker container ready!{RESET}")
            print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
            print(f"\n{BRIGHT_CYAN}Container details:{RESET}")
            print("  Name: cua-container")
            print("  Display: :99")
            print("  Resolution: 1280x800")
            print("  Desktop: Xfce4")
            print("  Browsers: Firefox, Chromium")
            print(f"\n{BRIGHT_CYAN}You can now run computer use examples:{RESET}")
            print(
                '  massgen --config @examples/tools/computer_use_docker_example.yaml "Open Firefox"',
            )
            print(
                '  massgen --config massgen/configs/tools/custom_tools/ui_tars_docker_example.yaml "..."\n',
            )
            return True
        else:
            print(f"{BRIGHT_RED}✗{RESET}")
            print(f"\n{BRIGHT_YELLOW}⚠️  Container created but test failed{RESET}")
            print(
                f"{BRIGHT_YELLOW}Please check container status: docker logs cua-container{RESET}\n",
            )
            return False

    except subprocess.TimeoutExpired:
        print(f"\n{BRIGHT_RED}❌ Setup timed out{RESET}\n")
        return False
    except Exception as e:
        print(f"\n{BRIGHT_RED}❌ Setup failed: {e}{RESET}\n")
        return False
    finally:
        # Cleanup temp directory
        import shutil

        try:
            shutil.rmtree(build_dir)
        except Exception:
            pass


def show_example_prompts() -> str | None:
    """Show example prompts that work with default quickstart config.

    These prompts work out-of-the-box with code execution, multimodal tools,
    and web scraping capabilities.

    Returns:
        Selected prompt text, or None if user skips/cancels
    """
    import questionary
    from questionary import Style

    example_prompts = [
        "Create a vibrant, interactive website about famous AI researchers using HTML, CSS, and JavaScript",
        "Write a Python script to analyze data from a CSV file, create visualizations, and generate a summary report",
        "Research recent developments in AI multi-agent systems by searching the web and summarize key trends with citations",
        "Generate 3 different logo concepts for a tech startup, then help me choose the best one based on design principles",
        "Create a lesson plan for teaching Python programming to beginners, with structured activities and code examples",
        "Build a web scraper to collect pricing data from e-commerce sites and analyze market trends",
        "Generate a presentation-ready infographic about climate change using text-to-image generation",
        "Research, plan, and write a technical blog post about multi-agent systems",
    ]

    # Custom style with highlighted autocomplete
    custom_style = Style(
        [
            ("answer", "#4A90E2 bold"),
            (
                "completion-menu.completion",
                "bg:#808080 fg:#ffffff",
            ),  # Dimmed gray background
            (
                "completion-menu.completion.current",
                "bg:#4A90E2 fg:#ffffff",
            ),  # Highlight current selection
        ],
    )

    try:
        print()
        # Show dimmed examples below the prompt
        print(
            "\033[2m" + "Example prompts (start typing to see autocomplete):" + "\033[0m",
        )
        for prompt in example_prompts[:3]:  # Show first 3 as hints
            print(
                "\033[2m" + f"  • {prompt[:70]}{'...' if len(prompt) > 70 else ''}" + "\033[0m",
            )
        print()

        choice = questionary.autocomplete(
            "Enter your prompt:",
            choices=example_prompts,
            style=custom_style,
            match_middle=True,
        ).ask()

        return choice if choice else None
    except (KeyboardInterrupt, EOFError):
        return None


def should_run_builder() -> bool:
    """Check if config builder should run automatically.

    Returns True if:
    - No default config exists at ~/.config/massgen/config.yaml
    """
    default_config = Path.home() / ".config/massgen/config.yaml"
    return not default_config.exists()


def _list_all_turns(
    session_id: str | None,
    current_turn: int,
    console: Console,
) -> None:
    """List all turns in the current session."""
    if not session_id:
        console.print("[yellow]No active session. Complete a turn first.[/yellow]")
        return

    session_dir = Path(SESSION_STORAGE) / session_id

    if not session_dir.exists():
        console.print("[yellow]No session data available.[/yellow]")
        return

    if current_turn == 0:
        console.print("[yellow]No turns completed yet.[/yellow]")
        return

    table = Table(title=f"Session: {session_id}")
    table.add_column("Turn", style="cyan", width=6)
    table.add_column("Task", style="white")
    table.add_column("Winner", style="green", width=15)

    for turn_num in range(1, current_turn + 1):
        turn_dir = session_dir / f"turn_{turn_num}"
        metadata_file = turn_dir / "metadata.json"

        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            task = metadata.get("task", "Unknown")
            # Truncate long tasks
            if len(task) > 60:
                task = task[:57] + "..."
            winner = metadata.get("winning_agent", "Unknown")
            table.add_row(str(turn_num), task, winner)

    console.print(table)
    console.print("\n[dim]Use /inspect <turn_number> to view details[/dim]")


def _find_log_dir_for_session(session_id: str, turn_number: int) -> Path | None:
    """Find the log directory for a given session and turn.

    Searches through log directories to find one that matches the session_id
    by checking execution_metadata.yaml files. Returns the attempt directory
    which contains the actual log data (agent_outputs, coordination_table, etc.).
    """
    logs_base = Path(".massgen/massgen_logs")
    if not logs_base.exists():
        return None

    # Search through log directories for matching session_id
    for log_dir in sorted(logs_base.iterdir(), reverse=True):  # Most recent first
        if not log_dir.is_dir() or not log_dir.name.startswith("log_"):
            continue

        turn_dir = log_dir / f"turn_{turn_number}"
        if not turn_dir.exists():
            continue

        # Look for attempt directories (e.g., attempt_1, attempt_2)
        # The actual log data is stored inside attempt directories
        for attempt_dir in sorted(turn_dir.iterdir(), reverse=True):
            if not attempt_dir.is_dir() or not attempt_dir.name.startswith("attempt_"):
                continue

            metadata_file = attempt_dir / "execution_metadata.yaml"
            if metadata_file.exists():
                try:
                    metadata = yaml.safe_load(metadata_file.read_text())
                    cli_args = metadata.get("cli_args", {})
                    if cli_args.get("session_id") == session_id:
                        return attempt_dir
                except Exception:
                    continue

    return None


def _show_turn_inspection(
    session_id: str,
    turn_number: int,
    agents: dict[str, Any],
) -> None:
    """Show inspection menu for a specific turn's outputs.

    Uses data from both session storage and log directories to provide
    full inspection capabilities including agent outputs, system status,
    and coordination events.
    """
    console = Console()
    session_dir = Path(SESSION_STORAGE) / session_id
    turn_dir = session_dir / f"turn_{turn_number}"

    if not turn_dir.exists():
        print(f"{BRIGHT_YELLOW}No data for turn {turn_number}.{RESET}", flush=True)
        return

    # Find the corresponding log directory for richer data
    log_turn_dir = _find_log_dir_for_session(session_id, turn_number)

    # Load metadata from session
    metadata_file = turn_dir / "metadata.json"
    metadata = {}
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())

    # Load answer from session
    answer_file = turn_dir / "answer.txt"
    answer_content = ""
    if answer_file.exists():
        answer_content = answer_file.read_text()

    # Check workspace from session
    workspace_dir = turn_dir / "workspace"
    workspace_files = []
    if workspace_dir.exists():
        workspace_files = list(workspace_dir.rglob("*"))
        workspace_files = [f for f in workspace_files if f.is_file()]

    # Check for log data
    agent_outputs_dir = log_turn_dir / "agent_outputs" if log_turn_dir else None
    system_status_file = agent_outputs_dir / "system_status.txt" if agent_outputs_dir else None
    log_turn_dir / "coordination_events.json" if log_turn_dir else None
    coordination_table_file = log_turn_dir / "coordination_table.txt" if log_turn_dir else None
    status_json_file = log_turn_dir / "status.json" if log_turn_dir else None

    # Get available agent output files
    agent_files = {}
    if agent_outputs_dir and agent_outputs_dir.exists():
        for f in agent_outputs_dir.glob("*.txt"):
            if f.name.startswith("agent_") and not f.name.startswith(
                "final_presentation",
            ):
                agent_id = f.stem.replace("agent_", "")
                agent_files[agent_id] = f

    # Get winning agent for display
    winning_agent = metadata.get("winning_agent", "winner")

    # Interactive menu - matches style of RichTerminalDisplay.show_agent_selector()
    while True:
        # Build menu content inside a panel like the original agent selector
        menu_lines = []

        # Intro description (matches original agent selector style)
        menu_lines.append(
            "This is a system inspection interface for diving into the multi-agent collaboration "
            "behind the scenes in MassGen. It lets you examine each agent's original output and "
            "compare it to the final MassGen answer in terms of quality. You can explore the "
            "detailed communication, collaboration, voting, and decision-making process.",
        )
        menu_lines.append("")

        # Turn metadata inline
        task_preview = metadata.get("task", "N/A")
        if len(task_preview) > 60:
            task_preview = task_preview[:57] + "..."
        menu_lines.append(
            f"[dim]Turn {turn_number} | Task: {task_preview} | Winner: {winning_agent}[/dim]",
        )
        menu_lines.append("")

        menu_lines.append("[bold green]🎮 Select an option to inspect:[/bold green]")

        # Agent outputs (from logs) - numbered options first
        if agent_files:
            for i, agent_id in enumerate(sorted(agent_files.keys()), 1):
                menu_lines.append(
                    f"  [yellow]{i}:[/yellow] Inspect the original answer and working log of agent {agent_id}",
                )

        # System status (s) - orchestrator log
        if system_status_file and system_status_file.exists():
            menu_lines.append(
                "  [yellow]s:[/yellow] Inspect the orchestrator working log including the voting process",
            )

        # Coordination table (r)
        if coordination_table_file and coordination_table_file.exists():
            menu_lines.append(
                "  [yellow]r:[/yellow] Display coordination table to see the full history of agent interactions and decisions",
            )

        # Cost breakdown (c)
        if status_json_file and status_json_file.exists():
            menu_lines.append(
                "  [yellow]c:[/yellow] Show cost breakdown and token usage",
            )

        # Final answer (f) - with winning agent info if available
        menu_lines.append(
            f"  [yellow]f:[/yellow] Show final presentation from Selected Agent ({winning_agent})",
        )

        # Workspace files (w/o)
        if workspace_files:
            menu_lines.append(
                f"  [yellow]w:[/yellow] List workspace files ({len(workspace_files)} files)",
            )
            menu_lines.append("  [yellow]o:[/yellow] Open workspace in file browser")

        # Quit (q)
        menu_lines.append("  [yellow]q:[/yellow] Quit Inspection")
        menu_lines.append("")

        # Display in a panel matching the original agent selector style
        console.print(
            Panel(
                "\n".join(menu_lines),
                title="[bold]Agent Selector[/bold]",
                border_style="cyan",
            ),
        )

        try:
            choice = input("Enter your choice: ").strip().lower()

            # Check for agent number selection
            if choice.isdigit():
                idx = int(choice)
                agent_ids = sorted(agent_files.keys())
                if 1 <= idx <= len(agent_ids):
                    agent_id = agent_ids[idx - 1]
                    agent_file = agent_files[agent_id]
                    content = agent_file.read_text()
                    # Escape Rich markup in content
                    if "[" in content:
                        content = content.replace("[", r"\[")
                    console.print("\n" + "=" * 80)
                    console.print(
                        Panel(
                            content,
                            title=f"[bold]{agent_id} Output[/bold]",
                            border_style="cyan",
                        ),
                    )
                    input("\nPress Enter to continue...")
                    console.print("=" * 80 + "\n")
                else:
                    console.print("[red]Invalid agent number.[/red]")
                continue

            if choice == "f":
                if answer_content:
                    console.print("\n" + "=" * 80)
                    # Escape Rich markup
                    display_content = answer_content
                    if "[" in display_content:
                        display_content = display_content.replace("[", r"\[")
                    console.print(
                        Panel(
                            display_content,
                            title=f"[bold]Final Answer (Turn {turn_number})[/bold]",
                            border_style="green",
                        ),
                    )
                    input("\nPress Enter to continue...")
                    console.print("=" * 80 + "\n")
                else:
                    console.print("[yellow]No answer content available.[/yellow]")

            elif choice == "s" and system_status_file and system_status_file.exists():
                content = system_status_file.read_text()
                if "[" in content:
                    content = content.replace("[", r"\[")
                console.print("\n" + "=" * 80)
                console.print(
                    Panel(
                        content,
                        title="[bold]System Status Log[/bold]",
                        border_style="magenta",
                    ),
                )
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "r" and coordination_table_file and coordination_table_file.exists():
                content = coordination_table_file.read_text()
                if "[" in content:
                    content = content.replace("[", r"\[")
                console.print("\n" + "=" * 80)
                console.print(
                    Panel(
                        content,
                        title="[bold]Coordination Table[/bold]",
                        border_style="yellow",
                    ),
                )
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "c" and status_json_file and status_json_file.exists():
                from rich.table import Table

                status_data = json.loads(status_json_file.read_text())
                console.print("\n" + "=" * 80)

                # Create cost table
                table = Table(
                    title="💰 Cost Breakdown & Token Usage",
                    show_header=True,
                    header_style="bold cyan",
                    border_style="cyan",
                )
                table.add_column("Agent", style="cyan", no_wrap=True)
                table.add_column("Input", justify="right", style="green")
                table.add_column("Output", justify="right", style="blue")
                table.add_column("Reasoning", justify="right", style="magenta")
                table.add_column("Cached", justify="right", style="yellow")
                table.add_column("Est. Cost", justify="right", style="bold green")

                # Get per-agent data
                agents_data = status_data.get("agents", {})
                for agent_id in sorted(agents_data.keys()):
                    agent_info = agents_data[agent_id]
                    tu = agent_info.get("token_usage", {})
                    if tu:
                        cost = tu.get("estimated_cost", 0)
                        if cost < 0.01:
                            cost_str = f"${cost:.4f}"
                        elif cost < 1.0:
                            cost_str = f"${cost:.3f}"
                        else:
                            cost_str = f"${cost:.2f}"
                        table.add_row(
                            agent_id,
                            f"{tu.get('input_tokens', 0):,}",
                            f"{tu.get('output_tokens', 0):,}",
                            (f"{tu.get('reasoning_tokens', 0):,}" if tu.get("reasoning_tokens", 0) > 0 else "-"),
                            (f"{tu.get('cached_input_tokens', 0):,}" if tu.get("cached_input_tokens", 0) > 0 else "-"),
                            cost_str,
                        )

                # Add totals row
                costs_data = status_data.get("costs", {})
                if costs_data and len(agents_data) > 1:
                    total_cost = costs_data.get("total_estimated_cost", 0)
                    if total_cost < 0.01:
                        total_cost_str = f"${total_cost:.4f}"
                    elif total_cost < 1.0:
                        total_cost_str = f"${total_cost:.3f}"
                    else:
                        total_cost_str = f"${total_cost:.2f}"
                    table.add_row(
                        "TOTAL",
                        f"{costs_data.get('total_input_tokens', 0):,}",
                        f"{costs_data.get('total_output_tokens', 0):,}",
                        "-",
                        "-",
                        total_cost_str,
                        style="bold",
                    )

                console.print(table)
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "w" and workspace_files:
                console.print("\n[bold]Workspace Files:[/bold]")
                for f in workspace_files[:20]:  # Limit to 20 files
                    rel_path = f.relative_to(workspace_dir)
                    console.print(f"  {rel_path}")
                if len(workspace_files) > 20:
                    console.print(f"  ... and {len(workspace_files) - 20} more files")
                console.print(f"\n[dim]Workspace path: {workspace_dir}[/dim]")
                input("\nPress Enter to continue...")

            elif choice == "o" and workspace_files:
                import platform
                import subprocess

                try:
                    system = platform.system()
                    if system == "Darwin":  # macOS
                        subprocess.run(["open", str(workspace_dir)])
                    elif system == "Windows":
                        subprocess.run(["explorer", str(workspace_dir)])
                    else:  # Linux
                        subprocess.run(["xdg-open", str(workspace_dir)])
                    console.print(f"[green]Opened workspace: {workspace_dir}[/green]")
                except Exception as e:
                    console.print(f"[red]Error opening workspace: {e}[/red]")

            elif choice == "q":
                break

            else:
                console.print("[red]Invalid choice. Please try again.[/red]")

        except KeyboardInterrupt:
            break

    console.print()


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
    import threading

    from massgen.agent_config import AgentConfig
    from massgen.cancellation import CancellationRequested
    from massgen.frontend.coordination_ui import CoordinationUI
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
    from massgen.orchestrator import Orchestrator

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
    agent_models = {}
    if agents is not None:
        agent_ids = list(agents.keys())
        # Extract model names from agent backends
        for agent_id, agent in agents.items():
            if hasattr(agent, "backend") and hasattr(agent.backend, "model"):
                agent_models[agent_id] = agent.backend.model
            elif hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
                agent_models[agent_id] = agent.config.backend_params.get("model", "")
    else:
        # Deferred agent creation - derive agent IDs and models from config
        if original_config:
            agent_configs = original_config.get("agents", [])
            if not agent_configs and "agent" in original_config:
                agent_configs = [original_config["agent"]]
        else:
            agent_configs = []
        agent_ids = [ac.get("id", f"agent_{i}") for i, ac in enumerate(agent_configs)]
        # Extract model names from config (model is nested in backend)
        for i, ac in enumerate(agent_configs):
            agent_id = ac.get("id", f"agent_{i}")
            # Model can be at top level or nested in backend
            model = ac.get("model") or ac.get("backend", {}).get("model", "")
            if model:
                agent_models[agent_id] = model

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
    async def run_turn(
        question: str,
        agents: dict[str, Any],
        ui_config: dict[str, Any],
        conversation_history: list,
        session_info: dict,
        **turn_kwargs,
    ) -> TurnResult:
        """Run a single turn through the orchestration engine."""
        nonlocal context  # Allow updating context.agents if we recreate them

        try:
            current_turn_num = session_info.get("current_turn", 0)
            sess_id = session_info.get("session_id")
            mode_state = display.get_mode_state()

            def _merge_readonly_context_path(config_dict: dict[str, Any], path_str: str, description: str) -> bool:
                """Add a read-only orchestrator context path if missing."""
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
                    from .path_handling import (
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
                        from .plan_execution import prepare_spec_execution_config

                        logger.info("[Textual] Execute mode - applying spec execution config")
                        modified_config = prepare_spec_execution_config(
                            modified_config,
                            mode_state.plan_session,
                        )
                    else:
                        from .plan_execution import prepare_plan_execution_config

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

                enable_rate_limit = kwargs.get("enable_rate_limit", False)
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
                enable_rate_limit = kwargs.get("enable_rate_limit", False)
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
                        enable_rate_limit = kwargs.get("enable_rate_limit", False)
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

            # Reload previous_turns and winning_agents_history from session storage
            # This ensures multi-turn memory sharing works correctly (same as Rich mode)
            previous_turns = session_info.get("previous_turns", [])
            winning_agents_history = session_info.get("winning_agents_history", [])

            if not previous_turns and not winning_agents_history and sess_id:
                from massgen.session import restore_session

                try:
                    session_state = restore_session(sess_id, SESSION_STORAGE)
                    if session_state:
                        previous_turns = session_state.previous_turns
                        winning_agents_history = session_state.winning_agents_history
                        logger.debug(
                            f"[Textual] Reloaded {len(previous_turns)} previous turn(s) " f"and {len(winning_agents_history)} winning agent(s) from session storage",
                        )
                except (ValueError, Exception) as e:
                    logger.debug(
                        f"[Textual] Could not restore session for previous turns: {e}",
                    )

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
            timeout_config = kwargs.get("timeout_config")
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
                    from .agent_config import CoordinationConfig

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
                        from .agent_config import CoordinationConfig

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
                        from .agent_config import CoordinationConfig

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

            # Get generated personas from session info if persist_across_turns is enabled
            # (matching Rich terminal path setup)
            generated_personas = None
            if (
                hasattr(orchestrator_config, "coordination_config")
                and orchestrator_config.coordination_config
                and orchestrator_config.coordination_config.persona_generator
                and orchestrator_config.coordination_config.persona_generator.persist_across_turns
            ):
                generated_personas = session_info.get("generated_personas")
                if generated_personas:
                    logger.info("[Textual] Reusing persisted personas from previous turn")

            # Get generated evaluation criteria from session info if persist_across_turns is enabled
            generated_evaluation_criteria = None
            if (
                hasattr(orchestrator_config, "coordination_config")
                and orchestrator_config.coordination_config
                and hasattr(orchestrator_config.coordination_config, "evaluation_criteria_generator")
                and orchestrator_config.coordination_config.evaluation_criteria_generator
                and orchestrator_config.coordination_config.evaluation_criteria_generator.persist_across_turns
            ):
                raw_criteria = session_info.get("generated_evaluation_criteria")
                if raw_criteria:
                    from .evaluation_criteria_generator import GeneratedCriterion

                    generated_evaluation_criteria = [
                        GeneratedCriterion(
                            id=c.get("id", f"E{i + 1}"),
                            text=c.get("text") or c.get("description") or c.get("name", ""),
                            category=c.get("category", "standard"),
                        )
                        for i, c in enumerate(raw_criteria)
                        if c.get("text") or c.get("description") or c.get("name")
                    ]
                    logger.info("[Textual] Reusing persisted evaluation criteria from previous turn")

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
                dspy_paraphraser=kwargs.get("dspy_paraphraser"),
                enable_rate_limit=kwargs.get("enable_rate_limit", False),
                enable_nlip=orchestrator_enable_nlip,
                nlip_config=orchestrator_nlip_config,
                generated_personas=generated_personas,
                generated_evaluation_criteria=generated_evaluation_criteria,
                plan_session_id=plan_session_id,
                raw_config=original_config or kwargs.get("raw_config"),
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
            # Extract models from all agents for session metadata
            models_dict = {}
            model_name_for_registry = None
            for agent_id, agent in agents.items():
                if hasattr(agent, "config") and hasattr(agent.config, "backend_params"):
                    model = agent.config.backend_params.get("model")
                    if model:
                        models_dict[agent_id] = model
            # Create comma-separated string for session registry
            if models_dict:
                unique_models = list(dict.fromkeys(models_dict.values()))
                model_name_for_registry = ", ".join(unique_models)
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

            # Store generated personas and evaluation criteria for multi-turn persistence
            if orchestrator.get_generated_personas():
                session_info["generated_personas"] = orchestrator.get_generated_personas()
            if orchestrator.get_generated_evaluation_criteria():
                session_info["generated_evaluation_criteria"] = [{"id": c.id, "text": c.text, "category": c.category} for c in orchestrator.get_generated_evaluation_criteria()]

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
    def orchestration_thread_fn():
        """Background thread that runs the controller."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(controller.run())
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
                    from .path_handling import (
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
    from .plan_storage import PLANS_DIR, PlanSession, PlanStorage

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

    from .logger_config import get_log_session_root
    from .plan_execution import (
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

    from .plan_storage import PlanStorage

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


async def main(args):
    """Main CLI entry point (async operations only)."""
    # Setup logging (only for actual agent runs, not special commands)
    setup_logging(debug=args.debug)

    # Configure event streaming to stdout if requested
    # This enables parent processes (TUI subagent modal) to receive real-time updates
    if getattr(args, "stream_events", False):
        # --stream-events implies --automation
        args.automation = True
        _setup_event_streaming()
        _setup_timeline_event_recording()

    # Configure Logfire observability if requested
    if getattr(args, "logfire", False):
        _setup_logfire_observability()

    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug(f"Command line arguments: {vars(args)}")

    # Initialize streaming buffer saving if requested
    if args.save_streaming_buffers:
        from .backend._streaming_buffer_mixin import set_save_streaming_buffers

        set_save_streaming_buffers(True)

    _metadata_saved_for_failure = False

    def _save_prompt_metadata_failure_fallback(
        failure_stage: str,
        failure_error: Exception | None = None,
    ) -> None:
        """Persist prompt metadata even when execution stops early."""
        nonlocal _metadata_saved_for_failure

        if _metadata_saved_for_failure:
            return

        if not getattr(args, "question", None):
            return

        try:
            cli_args = vars(args).copy()
            cli_args["failure_stage"] = failure_stage
            if failure_error is not None:
                cli_args["failure_error"] = str(failure_error)

            save_execution_metadata(
                query=args.question,
                config_path=str(resolved_path) if "resolved_path" in locals() and resolved_path else None,
                config_content=raw_config_for_metadata if "raw_config_for_metadata" in locals() else None,
                cli_args=cli_args,
            )
            _metadata_saved_for_failure = True
        except Exception as exc:  # pragma: no cover - best-effort metadata write
            logger.debug(f"Failed to save fallback execution metadata: {exc}")

    # Check if bare `massgen` with no args - use default config if it exists
    if not args.backend and not args.model and not args.config:
        # Use resolve_config_path to check project-level then global config
        resolved_default = resolve_config_path(None)
        if resolved_default:
            # Use discovered config for interactive mode (no question) or single query (with question)
            args.config = str(resolved_default)
        else:
            # No default config - this will be handled by wizard trigger in cli_main()
            if args.question:
                # User provided a question but no config exists - this is an error
                print(
                    "❌ Configuration error: No default configuration found.",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    "Run 'massgen --init' to create one, or use 'massgen --model MODEL \"question\"'",
                    file=sys.stderr,
                    flush=True,
                )
                _save_prompt_metadata_failure_fallback("missing_default_config")
                sys.exit(EXIT_CONFIG_ERROR)
            # No question and no config - wizard will be triggered in cli_main()
            return

    # Session config was already loaded in cli_main() if --session-id or --continue was used
    # Try to use config from session if it was set
    if args.session_id and not args.config and not args.model and not args.backend:
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        session_metadata = registry.get_session(args.session_id)
        if session_metadata:
            session_config_path = session_metadata.get("config_path")
            if session_config_path:
                args.config = session_config_path
                print(
                    f"   Using config from session: {Path(session_config_path).name}",
                    flush=True,
                )

    # Validate arguments (only if we didn't auto-set config above)
    if not args.backend:
        if not args.model and not args.config:
            print(
                "❌ Configuration error: Either --config, --model, or --backend must be specified",
                file=sys.stderr,
                flush=True,
            )
            _save_prompt_metadata_failure_fallback("missing_execution_source")
            sys.exit(EXIT_CONFIG_ERROR)

    # Track config path for error messages
    resolved_path = None

    try:
        # Load or create configuration
        if args.config:
            # Resolve config path (handles @examples/, paths, ~/.config/massgen/agents/)
            resolved_path = resolve_config_path(args.config)
            if resolved_path is None:
                # This shouldn't happen if we reached here, but handle it
                raise ConfigurationError("Could not resolve config path")
            config, raw_config_for_metadata = load_config_file(str(resolved_path))
            if args.debug:
                logger.debug(f"Resolved config path: {resolved_path}")
                logger.debug(f"Config content: {json.dumps(config, indent=2)}")

            # Capture prompt from config as early as possible for metadata capture on early failures
            if not args.question and "prompt" in config:
                args.question = config["prompt"]

            # Check if this is a computer use docker example - setup required
            config_filename = resolved_path.name if resolved_path else ""
            if "computer_use_docker_example" in config_filename:
                print(
                    f"\n{BRIGHT_CYAN}🖥️  Computer Use Docker Configuration Detected{RESET}",
                )
                print(
                    f"{BRIGHT_YELLOW}This configuration requires a special Docker container for GUI automation.{RESET}\n",
                )

                # Check if container exists and is running
                import subprocess

                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "ps",
                            "--filter",
                            "name=cua-container",
                            "--format",
                            "{{.Names}}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    container_running = "cua-container" in result.stdout
                except Exception:
                    container_running = False

                if not container_running:
                    print(
                        f"{BRIGHT_YELLOW}⚠️  Computer Use Docker container not found or not running{RESET}",
                    )
                    print(f"{BRIGHT_CYAN}Starting automatic setup...{RESET}\n")

                    if not setup_computer_use_docker():
                        print(
                            f"\n{BRIGHT_RED}❌ Failed to setup Computer Use Docker container{RESET}",
                        )
                        print(
                            f"{BRIGHT_YELLOW}Computer use features will not work without this container.{RESET}",
                        )
                        print(
                            f"{BRIGHT_YELLOW}You can try manual setup with: scripts/setup_docker_cua.sh{RESET}\n",
                        )
                        sys.exit(EXIT_CONFIG_ERROR)
                else:
                    print(
                        f"{BRIGHT_GREEN}✓ Computer Use Docker container is ready{RESET}\n",
                    )

            # Automatic config validation (unless --skip-validation flag is set)
            if not args.skip_validation:
                from .config_validator import ConfigValidator

                validator = ConfigValidator()
                validation_result = validator.validate_config(config)

                # Show errors if any
                if validation_result.has_errors():
                    print(validation_result.format_errors(), file=sys.stderr)
                    print(
                        f"\n{BRIGHT_RED}❌ Config validation failed. Fix errors above or use --skip-validation to bypass.{RESET}\n",
                    )
                    sys.exit(EXIT_CONFIG_ERROR)

                # Show warnings (non-blocking unless --strict-validation)
                if validation_result.has_warnings():
                    print(validation_result.format_warnings())
                    if args.strict_validation:
                        print(
                            f"\n{BRIGHT_RED}❌ Config validation failed in strict mode (warnings treated as errors).{RESET}\n",
                        )
                        sys.exit(EXIT_CONFIG_ERROR)
                    print()  # Extra newline for readability
        else:
            model = args.model
            if args.backend:
                backend = args.backend
            else:
                backend = get_backend_type_from_model(model=model)
            if args.system_message:
                system_message = args.system_message
            else:
                system_message = None
            config = create_simple_config(
                backend_type=backend,
                model=model,
                system_message=system_message,
                base_url=args.base_url,
            )
            # For simple configs, there's no env var expansion, so raw = config
            raw_config_for_metadata = copy.deepcopy(config)
            if args.debug:
                logger.debug(
                    f"Created simple config with backend: {backend}, model: {model}",
                )
                logger.debug(f"Config content: {json.dumps(config, indent=2)}")

        # Apply CLI override for CWD context path before validating paths.
        apply_cli_cwd_context_path(config, args.cwd_context)

        # Validate that all context paths exist before proceeding
        validate_context_paths(config)

        # Relocate all filesystem paths to .massgen/ directory
        relocate_filesystem_paths(config)

        # Generate unique instance ID for parallel execution safety
        # This prevents Docker container naming conflicts when running multiple instances
        import uuid

        instance_id = uuid.uuid4().hex[:8]

        # Inject instance_id to all agent backend configs for Docker container naming
        # Note: Workspace suffixing is now handled in create_agents_from_config() for all entrypoints
        agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
        for agent_data in agent_entries:
            backend_config = agent_data.get("backend", {})
            backend_config["instance_id"] = instance_id

        # Apply command-line overrides
        ui_config = config.get("ui", {})
        # Set default display type to textual_terminal if not specified
        if "display_type" not in ui_config:
            ui_config["display_type"] = "textual_terminal"
        if args.automation:
            # Automation mode: silent display, keep logging enabled for status.json
            ui_config["display_type"] = "silent"
            ui_config["logging_enabled"] = True
            ui_config["automation_mode"] = True
        if args.skip_agent_selector:
            ui_config["skip_agent_selector"] = True
        if args.no_display:
            ui_config["display_type"] = "simple"
        # --display flag overrides --no-display if both specified
        if args.display:
            display_type_map = {"rich": "rich_terminal", "textual": "textual_terminal"}
            ui_config["display_type"] = display_type_map.get(
                args.display,
                "rich_terminal",
            )

        # Deprecation warning for rich_terminal (unless explicitly overridden with --display rich)
        if ui_config.get("display_type") == "rich_terminal" and not (args.display == "rich"):
            import warnings

            warnings.warn(
                "display_type 'rich_terminal' is deprecated. The Textual TUI will be used instead. " "Update your config to use 'textual_terminal', or use '--display rich' to force Rich display.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Override to textual_terminal
            ui_config["display_type"] = "textual_terminal"

        # Persist UI overrides onto config so downstream helpers (for example
        # plan-and-execute phases) see the same resolved display settings.
        config["ui"] = ui_config

        if args.no_logs:
            ui_config["logging_enabled"] = False
        if args.debug:
            ui_config["debug"] = True
            # Enable logging if debug is on
            ui_config["logging_enabled"] = True
            # # Force simple UI in debug mode
            # ui_config["display_type"] = "simple"

        # Apply timeout overrides from CLI arguments
        timeout_settings = config.get("timeout_settings", {})
        if args.orchestrator_timeout is not None:
            timeout_settings["orchestrator_timeout_seconds"] = args.orchestrator_timeout

        # Update config with timeout settings
        config["timeout_settings"] = timeout_settings

        # Handle --plan mode: auto-configure for task planning
        if getattr(args, "plan", False):
            # Ensure orchestrator section exists
            if "orchestrator" not in config:
                config["orchestrator"] = {}
            orchestrator_cfg_plan = config["orchestrator"]

            # Ensure coordination section exists
            if "coordination" not in orchestrator_cfg_plan:
                orchestrator_cfg_plan["coordination"] = {}

            # Broadcast mode: CLI flag wins; otherwise default to autonomous ("false")
            broadcast_arg = getattr(args, "broadcast", None)
            if broadcast_arg == "false":
                orchestrator_cfg_plan["coordination"]["broadcast"] = False
            elif broadcast_arg is not None:
                orchestrator_cfg_plan["coordination"]["broadcast"] = broadcast_arg
            else:
                orchestrator_cfg_plan["coordination"].setdefault("broadcast", False)

            # Set plan_depth and plan_thoroughness
            orchestrator_cfg_plan["coordination"]["plan_depth"] = getattr(
                args,
                "plan_depth",
                "dynamic",
            )
            orchestrator_cfg_plan["coordination"]["plan_thoroughness"] = getattr(
                args,
                "plan_thoroughness",
                "standard",
            )
            orchestrator_cfg_plan["coordination"]["plan_target_steps"] = getattr(
                args,
                "plan_steps",
                None,
            )
            resolved_plan_target_chunks = getattr(
                args,
                "plan_chunks",
                None,
            )
            if resolved_plan_target_chunks is None:
                existing_chunk_target = orchestrator_cfg_plan["coordination"].get("plan_target_chunks")
                if isinstance(existing_chunk_target, int) and existing_chunk_target > 0:
                    resolved_plan_target_chunks = existing_chunk_target
                else:
                    resolved_plan_target_chunks = 1
            orchestrator_cfg_plan["coordination"]["plan_target_chunks"] = resolved_plan_target_chunks

            if _disable_evaluation_criteria_generation_for_planning(orchestrator_cfg_plan["coordination"]):
                logger.info("[Plan Mode] Disabled evaluation criteria generation for planning turn")
            if _set_planning_checklist_criteria_defaults(orchestrator_cfg_plan["coordination"]):
                logger.info("[Plan Mode] Defaulted checklist_criteria_preset=planning")

            logger.info(
                "[Plan Mode] Enabled with depth=%s, target_steps=%s, target_chunks=%s, broadcast=%s",
                args.plan_depth,
                getattr(args, "plan_steps", None),
                resolved_plan_target_chunks,
                orchestrator_cfg_plan["coordination"].get("broadcast"),
            )

        # Apply CLI mode flags (--quick, --coordination-mode, --personas, --single-agent)
        apply_mode_flags_to_config(config, args)

        # Handle --eval-criteria: load JSON file and inject into coordination config
        if getattr(args, "eval_criteria", None):
            criteria = _load_eval_criteria(args.eval_criteria)
            _inject_eval_criteria_into_config(config, criteria)
            logger.info(
                "[CLI] Injected %d eval criteria from %s",
                len(criteria),
                args.eval_criteria,
            )

        # Handle --checklist-criteria-preset: inject preset into coordination config
        if getattr(args, "checklist_criteria_preset", None):
            _inject_checklist_criteria_preset_into_config(config, args.checklist_criteria_preset)
            logger.info(
                "[CLI] Set checklist_criteria_preset=%s",
                args.checklist_criteria_preset,
            )

        # Check for prompt in config if not provided via CLI
        if not args.question and "prompt" in config:
            args.question = config["prompt"]
            logger.info(f"Using prompt from config file: {args.question}")

        # Get rate limiting flag from CLI
        enable_rate_limit = args.rate_limit

        # Create agents
        if args.debug:
            logger.debug("Creating agents from config...")
            logger.debug(f"Rate limiting enabled: {enable_rate_limit}")
        # Extract orchestrator config for agent setup
        orchestrator_cfg = config.get("orchestrator", {})

        # Check if any agent has cwd (filesystem support) and validate orchestrator config
        agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
        has_cwd = any("cwd" in agent.get("backend", {}) for agent in agent_entries)

        if has_cwd:
            if not orchestrator_cfg:
                raise ConfigurationError(
                    "Agents with 'cwd' (filesystem support) require orchestrator configuration.\n"
                    "Please add an 'orchestrator' section to your config file.\n\n"
                    "Example (customize paths as needed):\n"
                    "orchestrator:\n"
                    '  snapshot_storage: "your_snapshot_dir"\n'
                    '  agent_temporary_workspace: "your_temp_dir"',
                )

            # Check for required fields in orchestrator config
            if "snapshot_storage" not in orchestrator_cfg:
                raise ConfigurationError(
                    "Missing 'snapshot_storage' in orchestrator configuration.\n"
                    "This is required for agents with filesystem support (cwd).\n\n"
                    "Add to your orchestrator section:\n"
                    '  snapshot_storage: "your_snapshot_dir"  # Directory for workspace snapshots',
                )

            if "agent_temporary_workspace" not in orchestrator_cfg:
                raise ConfigurationError(
                    "Missing 'agent_temporary_workspace' in orchestrator configuration.\n"
                    "This is required for agents with filesystem support (cwd).\n\n"
                    "Add to your orchestrator section:\n"
                    '  agent_temporary_workspace: "your_temp_dir"  # Directory for temporary agent workspaces',
                )

        # Create unified session ID for memory system (before creating agents)
        # This ensures memory is isolated per session and unifies orchestrator + memory sessions
        memory_session_id = None
        restore_existing_session = False  # Flag to indicate if we should restore session data

        # Determine model name for metadata (used in session registration and kwargs)
        model_name = None
        if "agent" in config:
            model_name = config["agent"].get("backend", {}).get("model")
        elif "agents" in config and config["agents"]:
            model_name = config["agents"][0].get("backend", {}).get("model")

        # Priority order: CLI arg > config file > generate new
        if args.session_id:
            # Use session_id from CLI argument (already validated) - RESTORE existing
            memory_session_id = args.session_id
            restore_existing_session = True
            logger.info(f"📚 Using session from CLI: {memory_session_id}")
        elif "session_id" in config:
            # Use session_id from YAML config - RESTORE existing
            memory_session_id = config["session_id"]
            restore_existing_session = True
            logger.info(f"📚 Using session from config: {memory_session_id}")
        else:
            # Generate new session for both interactive and single-question modes - DON'T restore
            from datetime import datetime

            memory_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            restore_existing_session = False
            mode = "single-question" if args.question else "interactive"
            logger.info(f"📝 Created session for {mode} mode: {memory_session_id}")

            # Write session_id sentinel for parent process discovery.
            # Subprocess cwd is the workspace (set via cwd= in manager.py),
            # so this writes to {workspace}/.massgen/.session_id.
            _sentinel_dir = Path(".massgen")
            _sentinel_dir.mkdir(parents=True, exist_ok=True)
            (Path(".massgen") / ".session_id").write_text(memory_session_id)

            # Register new session immediately (before first turn runs)
            # Get log directory for session metadata
            from massgen.logger_config import get_log_session_dir, get_log_session_root
            from massgen.session import SessionRegistry

            log_dir = get_log_session_root()
            log_dir_name = log_dir.name

            # Print LOG_DIR for automation mode (LLM agents need this to monitor progress)
            # LOG_DIR is the main session directory, STATUS includes turn/attempt subdirectory
            if args.automation:
                full_log_dir = get_log_session_dir()
                _automation_print(f"LOG_DIR: {Path(log_dir).resolve()}")
                _automation_print(f"STATUS: {Path(full_log_dir).resolve() / 'status.json'}")

            # Only register in global session registry if not suppressed (e.g., subagent runs)
            if not getattr(args, "no_session_registry", False):
                registry = SessionRegistry()

                # Auto-detect subagent sessions by session_id prefix
                is_subagent = memory_session_id.startswith("subagent_")

                registry.register_session(
                    session_id=memory_session_id,
                    config_path=str(resolved_path) if resolved_path else None,
                    model=model_name,
                    log_directory=log_dir_name,
                    subagent=is_subagent,  # Label subagent sessions
                )
                logger.info(
                    f"📝 Registered {'subagent' if is_subagent else 'new'} session in registry: {memory_session_id}",
                )
            else:
                logger.debug(
                    f"📝 Skipping session registry (--no-session-registry): {memory_session_id}",
                )

        # Parse @references from prompt BEFORE creating agents
        # This allows context_paths to be set up before FilesystemManager initialization
        if args.question:
            args.question, config = inject_prompt_context_paths(
                args.question,
                config,
                parse_at_references=getattr(args, "parse_at_references", True),
            )
            # Update orchestrator_cfg with any new context_paths
            orchestrator_cfg = config.get("orchestrator", {})

        # Textual mode handles plan/spec prompt prefixes from mode state at turn time.
        # For non-textual displays, keep CLI-side prefixing behavior.
        is_textual_display = ui_config.get("display_type") == "textual_terminal"

        # Prepend task planning instructions if --plan mode is active
        if args.question and getattr(args, "plan", False) and not is_textual_display:
            plan_depth = getattr(args, "plan_depth", "dynamic")
            plan_target_steps = getattr(args, "plan_steps", None)
            plan_target_chunks = getattr(args, "plan_chunks", None)
            # Check if subagents are enabled in config
            coordination_cfg = config.get("orchestrator", {}).get("coordination", {})
            enable_subagents = coordination_cfg.get("enable_subagents", False)
            if plan_target_steps is None:
                cfg_steps = coordination_cfg.get("plan_target_steps")
                if isinstance(cfg_steps, int) and cfg_steps > 0:
                    plan_target_steps = cfg_steps
            if plan_target_chunks is None:
                cfg_chunks = coordination_cfg.get("plan_target_chunks")
                if isinstance(cfg_chunks, int) and cfg_chunks > 0:
                    plan_target_chunks = cfg_chunks
            if plan_target_chunks is None:
                plan_target_chunks = 1

            # Broadcast mode priority: CLI arg > config > default false
            cli_broadcast = getattr(args, "broadcast", None)
            if cli_broadcast == "false":
                broadcast_mode = False
            elif cli_broadcast is not None:
                broadcast_mode = cli_broadcast
            else:
                broadcast_mode = coordination_cfg.get("broadcast", False)

            plan_thoroughness = getattr(args, "plan_thoroughness", "standard")
            planning_prefix = get_task_planning_prompt_prefix(
                plan_depth,
                target_steps=plan_target_steps,
                target_chunks=plan_target_chunks,
                enable_subagents=enable_subagents,
                broadcast_mode=broadcast_mode,
                thoroughness=plan_thoroughness,
            )
            args.question = planning_prefix + args.question
            logger.info(
                f"[Plan Mode] Prepended task planning instructions (depth={plan_depth}, thoroughness={plan_thoroughness}, "
                f"target_steps={plan_target_steps}, target_chunks={plan_target_chunks}, "
                f"subagents={enable_subagents}, broadcast={broadcast_mode})",
            )

        # Prepend spec creation instructions if --spec mode is active
        if args.question and getattr(args, "spec", False) and not getattr(args, "plan", False) and not is_textual_display:
            coordination_cfg = config.get("orchestrator", {}).get("coordination", {})
            plan_target_chunks = getattr(args, "plan_chunks", None)
            if plan_target_chunks is None:
                cfg_chunks = coordination_cfg.get("plan_target_chunks")
                if isinstance(cfg_chunks, int) and cfg_chunks > 0:
                    plan_target_chunks = cfg_chunks
            if plan_target_chunks is None:
                plan_target_chunks = 1

            # Broadcast mode priority: CLI arg > config > default false
            cli_broadcast = getattr(args, "broadcast", None)
            if cli_broadcast == "false":
                broadcast_mode = False
            elif cli_broadcast is not None:
                broadcast_mode = cli_broadcast
            else:
                broadcast_mode = coordination_cfg.get("broadcast", False)

            spec_prefix = get_spec_creation_prompt_prefix(
                broadcast_mode=broadcast_mode,
                target_chunks=plan_target_chunks,
            )
            args.question = spec_prefix + args.question
            logger.info(
                f"[Spec Mode] Prepended spec creation instructions " f"(target_chunks={plan_target_chunks}, broadcast={broadcast_mode})",
            )

        # For interactive mode without initial question, defer agent creation until first prompt
        # This allows @path references in the first prompt to be included in Docker mounts
        is_interactive_without_question = not args.question and not getattr(
            args,
            "interactive_with_initial_question",
            None,
        )

        if is_interactive_without_question:
            # Defer agent creation - will be done in run_interactive_mode after first prompt
            agents = None
        else:
            agents = create_agents_from_config(
                config,
                orchestrator_cfg,
                enable_rate_limit=enable_rate_limit,
                config_path=str(resolved_path) if resolved_path else None,
                memory_session_id=memory_session_id,
                debug=args.debug,
                # Session mount support for multi-turn Docker (pre-mount session dir)
                filesystem_session_id=memory_session_id,
                session_storage_base=SESSION_STORAGE,
            )

            if not agents:
                raise ConfigurationError("No agents configured")

            # Apply --single-agent filtering
            if getattr(args, "single_agent", None) is not None:
                try:
                    agents = filter_agents_for_single_mode(agents, args.single_agent)
                    logger.info(f"[CLI] Single-agent mode: using agent '{next(iter(agents.keys()))}'")
                except ValueError as e:
                    print(f"❌ {e}")
                    sys.exit(EXIT_CONFIG_ERROR)

        if args.debug and agents:
            logger.debug(f"Created {len(agents)} agent(s): {list(agents.keys())}")

        # Create timeout config from settings and put it in kwargs
        timeout_settings = config.get("timeout_settings", {})
        timeout_config = TimeoutConfig(**timeout_settings) if timeout_settings else TimeoutConfig()

        kwargs = {
            "timeout_config": timeout_config,
            "model_name": model_name,  # For session registration
            "config_path": (str(resolved_path) if resolved_path else None),  # For session registration
        }

        # Add orchestrator configuration if present
        if "orchestrator" in config:
            kwargs["orchestrator"] = config["orchestrator"]

        # Add raw agent configs for subtask parsing in decomposition mode
        if "agents" in config:
            kwargs["agents_config"] = config["agents"]
        elif "agent" in config:
            kwargs["agents_config"] = [config["agent"]]

        # Pass raw config dict for checkpoint subprocess config generation
        kwargs["raw_config"] = config

        # Add rate limit flag to kwargs for interactive mode
        kwargs["enable_rate_limit"] = enable_rate_limit
        kwargs["parse_at_references"] = getattr(args, "parse_at_references", True)

        # Add output file if specified
        if args.output_file:
            kwargs["output_file"] = args.output_file

        # Seed Textual Ctrl+P CWD mode when explicitly requested via CLI.
        if args.cwd_context:
            kwargs["cwd_context_mode"] = args.cwd_context

        # Pass CLI mode defaults to TUI for initial mode bar state
        cli_mode_defaults = build_cli_mode_defaults(args)
        if cli_mode_defaults:
            kwargs["cli_mode_defaults"] = cli_mode_defaults

        # Optionally enable DSPy paraphrasing
        dspy_paraphraser = create_dspy_paraphraser_from_config(
            config,
            config_path=str(resolved_path) if resolved_path else None,
        )
        if dspy_paraphraser:
            kwargs["dspy_paraphraser"] = dspy_paraphraser

        # Save execution metadata for debugging and reconstruction
        if args.question:
            # For single question mode, save metadata now (use raw config to avoid logging secrets)
            save_execution_metadata(
                query=args.question,
                config_path=(str(resolved_path) if args.config and "resolved_path" in locals() else None),
                config_content=raw_config_for_metadata,
                cli_args=vars(args),
            )

        # Handle step mode: run one agent for one step, then exit
        if getattr(args, "step", False):
            from .agent_config import StepModeConfig
            from .step_mode import (
                save_step_mode_output,
                validate_step_mode_args,
                validate_step_mode_config,
            )

            try:
                validate_step_mode_args(args)
                validate_step_mode_config(config)
            except ValueError as e:
                print(f"❌ Step mode validation error: {e}")
                sys.exit(1)

            # Step mode implies automation
            args.automation = True
            ui_config["display_type"] = "silent"
            ui_config["logging_enabled"] = True
            ui_config["automation_mode"] = True

            step_config = StepModeConfig(enabled=True, session_dir=args.session_dir)

            if not args.question:
                print("❌ --step requires a question/task")
                sys.exit(1)

            _automation_print(f"SESSION_DIR: {Path(args.session_dir).resolve()}")

            # Create agents (same as normal single-question mode)
            orchestrator_cfg = config.get("orchestrator", {})
            agents = create_agents_from_config(
                config,
                orchestrator_cfg,
                memory_session_id=memory_session_id,
            )

            # Build orchestrator config (mirrors the normal path)
            orchestrator_config = AgentConfig()
            timeout_settings = config.get("timeout_settings", {})
            if timeout_settings:
                orchestrator_config.timeout_config = TimeoutConfig(**timeout_settings)
            _apply_orchestrator_runtime_params(orchestrator_config, orchestrator_cfg)
            if "coordination" in orchestrator_cfg:
                orchestrator_config.coordination_config = _parse_coordination_config(
                    orchestrator_cfg["coordination"],
                )

            snapshot_storage = _scope_snapshot_storage(orchestrator_cfg.get("snapshot_storage"))
            agent_temporary_workspace = _scope_agent_temporary_workspace(
                orchestrator_cfg.get("agent_temporary_workspace"),
            )

            # Create orchestrator with step mode
            orchestrator = Orchestrator(
                agents=agents,
                config=orchestrator_config,
                session_id=memory_session_id,
                snapshot_storage=snapshot_storage,
                agent_temporary_workspace=agent_temporary_workspace,
                step_mode=step_config,
                raw_config=kwargs.get("raw_config"),
            )

            # Build UI and run question
            ui = _build_coordination_ui(ui_config)
            orchestrator.coordination_ui = ui

            import time as _time

            _step_start = _time.monotonic()

            async for chunk in orchestrator.chat(
                [{"role": "user", "content": args.question}],
            ):
                pass  # Stream through silently in automation mode

            _step_duration = _time.monotonic() - _step_start

            # Save step output
            if orchestrator._step_action_data:
                action_data = orchestrator._step_action_data
                real_agent_id = list(agents.keys())[0]

                # Get seen_steps for votes
                seen_steps = None
                if action_data["action"] == "vote":
                    from .step_mode import load_session_dir_inputs

                    inputs = load_session_dir_inputs(args.session_dir)
                    seen_steps = {}
                    for va_id, va_state in inputs.virtual_agents.items():
                        if va_state.latest_answer_step is not None:
                            seen_steps[va_id] = va_state.latest_answer_step

                save_step_mode_output(
                    session_dir=args.session_dir,
                    agent_id=real_agent_id,
                    action=action_data["action"],
                    answer_text=action_data.get("answer_text"),
                    vote_target=action_data.get("vote_target"),
                    vote_reason=action_data.get("vote_reason"),
                    seen_steps=seen_steps,
                    duration_seconds=_step_duration,
                    workspace_source=action_data.get("workspace_path"),
                    stale_workspace_paths=action_data.get("stale_workspace_paths"),
                )

                # Save post-coordination artifacts (final/, coordination_events.json, etc.)
                from massgen.logger_config import get_log_session_dir

                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    orchestrator.finalize_step_mode(log_session_dir)

                _automation_print(f"ACTION: {action_data['action']}")
                _automation_print(f"STATUS: {Path(args.session_dir).resolve() / 'agents' / real_agent_id / 'last_action.json'}")
            else:
                print("❌ Step mode: agent did not produce an answer or vote", file=sys.stderr)
                sys.exit(2)

            sys.exit(0)

        # Handle plan-and-execute mode
        if getattr(args, "plan_and_execute", False):
            if not args.question:
                print("❌ --plan-and-execute requires a question/task to plan and execute")
                sys.exit(1)

            from rich.console import Console
            from rich.panel import Panel

            # Default broadcast to "false" for plan-and-execute (batch workflow)
            # "human" broadcast is not supported because planning runs as subprocess with piped I/O
            broadcast = getattr(args, "broadcast", None)
            if broadcast == "human":
                print("❌ --broadcast human is not currently supported with --plan-and-execute")
                print("   Planning runs as a subprocess and cannot receive human input.")
                print("")
                print("   For human interaction, run planning and execution separately:")
                print('     1. uv run massgen --plan --broadcast human "your task"')
                print("     2. uv run massgen --execute-plan latest")
                print("")
                print("   Or use --broadcast false (default) or --broadcast agents for autonomous mode.")
                sys.exit(1)
            if broadcast is None:
                broadcast = "false"

            final_answer, plan_session = await run_plan_and_execute(
                config=config,
                question=args.question,
                plan_depth=getattr(args, "plan_depth", "dynamic") or "dynamic",
                plan_thoroughness=getattr(args, "plan_thoroughness", "standard") or "standard",
                plan_target_steps=getattr(args, "plan_steps", None),
                plan_target_chunks=getattr(args, "plan_chunks", None),
                broadcast_mode=broadcast,
                automation=args.automation,
                debug=args.debug,
                config_path=str(resolved_path) if resolved_path else None,
            )

            # Print results
            if not args.automation:
                console = Console()
                console.print(Panel(final_answer, title="Final Answer", border_style="green"))

            # Write output file if specified
            if args.output_file:
                output_path = Path(args.output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_answer)
                _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

            # Print plan location for automation mode
            if args.automation:
                _automation_print(f"PLAN_DIR: {plan_session.plan_dir}")
                _automation_print(f"PLAN_ID: {plan_session.plan_id}")

            sys.exit(0)

        # Handle --execute-plan mode (execute existing plan without planning phase)
        if getattr(args, "execute_plan", None):
            from rich.console import Console
            from rich.panel import Panel

            try:
                final_answer, plan_session = await run_execute_plan(
                    config=config,
                    plan_path=args.execute_plan,
                    question=args.question,  # Optional override
                    automation=args.automation,
                )

                # Print results
                if not args.automation:
                    console = Console()
                    console.print(Panel(final_answer, title="Final Answer", border_style="green"))

                # Write output file if specified
                if args.output_file:
                    output_path = Path(args.output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(final_answer)
                    _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

                # Print plan location for automation mode
                if args.automation:
                    _automation_print(f"PLAN_DIR: {plan_session.plan_dir}")
                    _automation_print(f"PLAN_ID: {plan_session.plan_id}")

                sys.exit(0)

            except FileNotFoundError as e:
                print(f"❌ {e}")
                sys.exit(1)

        # Handle --execute-spec mode (execute existing spec without spec creation phase)
        if getattr(args, "execute_spec", None):
            from rich.console import Console
            from rich.panel import Panel

            try:
                final_answer, plan_session = await run_execute_spec(
                    config=config,
                    spec_path=args.execute_spec,
                    question=args.question,  # Optional override
                    automation=args.automation,
                )

                # Print results
                if not args.automation:
                    console = Console()
                    console.print(Panel(final_answer, title="Final Answer", border_style="green"))

                # Write output file if specified
                if args.output_file:
                    output_path = Path(args.output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(final_answer)
                    _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

                # Print spec location for automation mode
                if args.automation:
                    _automation_print(f"SPEC_DIR: {plan_session.plan_dir}")
                    _automation_print(f"SPEC_ID: {plan_session.plan_id}")

                sys.exit(0)

            except FileNotFoundError as e:
                print(f"❌ {e}")
                sys.exit(1)

        # Run mode based on whether question was provided
        try:
            # Check if using textual display - textual always uses interactive mode
            # with question as initial_question (textual doesn't support single-question mode)
            is_textual_display = ui_config.get("display_type") == "textual_terminal"

            if args.question and not is_textual_display:
                await run_single_question(
                    args.question,
                    agents,
                    ui_config,
                    session_id=memory_session_id,
                    restore_session_if_exists=restore_existing_session,
                    **kwargs,
                )

                # Print FINAL_DIR for automation mode (allows plan-and-execute to capture workspace)
                if args.automation:
                    try:
                        from massgen.logger_config import get_log_session_dir

                        final_dir = get_log_session_dir() / "final"
                        if final_dir.exists():
                            _automation_print(f"FINAL_DIR: {final_dir}")
                    except Exception:
                        pass  # Log paths not available
            else:
                # Pass the config path and session_id to interactive mode
                config_file_path = str(resolved_path) if args.config and resolved_path else None
                # Check if we have an initial question from config builder or CLI arg (for textual mode)
                initial_q = getattr(args, "interactive_with_initial_question", None)
                # For textual display, use args.question as initial_question if provided
                if is_textual_display and args.question:
                    initial_q = args.question
                # Remove config_path and enable_rate_limit from kwargs to avoid duplicate argument
                interactive_kwargs = {k: v for k, v in kwargs.items() if k not in ("config_path", "enable_rate_limit")}
                await run_interactive_mode(
                    agents,
                    ui_config,
                    original_config=config,
                    orchestrator_cfg=orchestrator_cfg,
                    config_path=config_file_path,
                    memory_session_id=memory_session_id,
                    initial_question=initial_q,
                    restore_session_if_exists=restore_existing_session,
                    debug=args.debug,
                    raw_config_for_metadata=raw_config_for_metadata,
                    enable_rate_limit=enable_rate_limit,
                    session_storage_base=SESSION_STORAGE,
                    **interactive_kwargs,
                )
        finally:
            # Mark ALL sessions as completed
            if memory_session_id:
                from massgen.session import SessionRegistry

                registry = SessionRegistry()
                registry.complete_session(memory_session_id)
                if args.debug:
                    logger.debug(f"Marked session as completed: {memory_session_id}")

            # Cleanup all agents' filesystem managers (including Docker containers)
            # Note: agents may be None if deferred creation was used but no prompt was entered
            if agents:
                agents_with_docker = [
                    (agent_id, agent)
                    for agent_id, agent in agents.items()
                    if hasattr(agent, "backend")
                    and hasattr(agent.backend, "filesystem_manager")
                    and agent.backend.filesystem_manager
                    and hasattr(agent.backend.filesystem_manager, "docker_manager")
                    and agent.backend.filesystem_manager.docker_manager
                ]

                if agents_with_docker:
                    # Show spinner while cleaning up Docker containers in parallel
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    from rich.status import Status

                    def cleanup_agent(
                        agent_id: str,
                        agent,
                    ) -> tuple[str, Exception | None]:
                        """Cleanup a single agent's Docker container."""
                        try:
                            agent.backend.filesystem_manager.cleanup()
                            return (agent_id, None)
                        except Exception as e:
                            return (agent_id, e)

                    with Status(
                        f"[bold cyan]Cleaning up {len(agents_with_docker)} Docker container(s)...",
                        spinner="dots",
                    ):
                        with ThreadPoolExecutor(
                            max_workers=len(agents_with_docker),
                        ) as executor:
                            futures = {
                                executor.submit(
                                    cleanup_agent,
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

                    print("✅ Docker cleanup complete", flush=True)

                # Cleanup non-Docker filesystem managers (quick, no spinner needed)
                for agent_id, agent in agents.items():
                    if (agent_id, agent) not in agents_with_docker:
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

    except SystemExit as e:
        exit_code = getattr(e, "code", EXIT_EXECUTION_ERROR)
        if exit_code not in (None, 0):
            _save_prompt_metadata_failure_fallback(
                "system_exit",
                failure_error=SystemExit(exit_code),
            )
        raise
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr, flush=True)
        _save_prompt_metadata_failure_fallback("configuration_error", failure_error=e)
        sys.exit(EXIT_CONFIG_ERROR)
    except KeyboardInterrupt:
        # Show spinner while cleaning up
        from rich.console import Console as RichConsole
        from rich.status import Status

        rich_console = RichConsole()
        rich_console.print("\n[yellow]Cancelling...[/yellow]")

        # Cleanup agents if they exist
        if "agents" in locals() and agents:
            agents_with_docker = [
                (agent_id, agent)
                for agent_id, agent in agents.items()
                if hasattr(agent, "backend")
                and hasattr(agent.backend, "filesystem_manager")
                and agent.backend.filesystem_manager
                and hasattr(agent.backend.filesystem_manager, "docker_manager")
                and agent.backend.filesystem_manager.docker_manager
            ]

            if agents_with_docker:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def cleanup_agent(
                    agent_id: str,
                    agent,
                ) -> tuple[str, Exception | None]:
                    try:
                        agent.backend.filesystem_manager.cleanup()
                        return (agent_id, None)
                    except Exception as e:
                        return (agent_id, e)

                with Status("[bold cyan]Cleaning up...[/bold cyan]", spinner="dots"):
                    with ThreadPoolExecutor(
                        max_workers=len(agents_with_docker),
                    ) as executor:
                        futures = {executor.submit(cleanup_agent, agent_id, agent): agent_id for agent_id, agent in agents_with_docker}
                        for future in as_completed(futures):
                            pass  # Just wait for completion

        # Cleanup MCP servers → terminates subagent processes
        if "agents" in locals() and agents:
            for agent_id, agent in agents.items():
                if hasattr(agent, "backend") and hasattr(agent.backend, "cleanup_mcp"):
                    try:
                        await agent.backend.cleanup_mcp()
                    except Exception:
                        pass

        rich_console.print("[green]👋 Goodbye![/green]")
        _save_prompt_metadata_failure_fallback("keyboard_interrupt")
        sys.exit(EXIT_INTERRUPTED)
    except TimeoutError as e:
        print(f"❌ Timeout error: {e}", flush=True)
        _save_prompt_metadata_failure_fallback("timeout_error", failure_error=e)
        sys.exit(EXIT_TIMEOUT)
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        _save_prompt_metadata_failure_fallback("execution_error", failure_error=e)
        sys.exit(EXIT_EXECUTION_ERROR)


def cli_main():
    """Synchronous wrapper for CLI entry point."""
    # Handle 'viewer' subcommand — view a session in the TUI (read-only)
    if len(sys.argv) >= 2 and sys.argv[1] == "viewer":
        from .viewer import build_viewer_parser, viewer_command

        viewer_parser = build_viewer_parser()
        viewer_args = viewer_parser.parse_args(sys.argv[2:])
        sys.exit(viewer_command(viewer_args))

    # Handle 'logs' subcommand specially before main argument parsing
    # This avoids conflict with the positional 'question' argument
    if len(sys.argv) >= 2 and sys.argv[1] == "logs":
        from .logs_analyzer import logs_command

        # Create a separate parser just for logs subcommand
        logs_parser = argparse.ArgumentParser(
            prog="massgen logs",
            description="Analyze and display MassGen run logs",
        )
        logs_subparsers = logs_parser.add_subparsers(
            dest="logs_command",
            help="Log analysis commands",
        )

        # logs summary (default)
        summary_parser = logs_subparsers.add_parser(
            "summary",
            help="Display run summary (default)",
        )
        summary_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )
        summary_parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON",
        )

        # logs tools
        tools_parser = logs_subparsers.add_parser(
            "tools",
            help="Display tool breakdown",
        )
        tools_parser.add_argument(
            "--sort",
            choices=["time", "calls"],
            default="time",
            help="Sort by time or calls",
        )
        tools_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )
        tools_parser.add_argument("--json", action="store_true", help="Output as JSON")

        # logs list
        list_parser = logs_subparsers.add_parser("list", help="List recent runs")
        list_parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of runs to show",
        )
        list_parser.add_argument(
            "--analyzed",
            action="store_true",
            help="Show only logs with ANALYSIS_REPORT.md",
        )
        list_parser.add_argument(
            "--unanalyzed",
            action="store_true",
            help="Show only logs without ANALYSIS_REPORT.md",
        )
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")

        # logs open
        open_parser = logs_subparsers.add_parser(
            "open",
            help="Open log directory in file manager",
        )
        open_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )

        # logs analyze
        analyze_parser = logs_subparsers.add_parser(
            "analyze",
            help="Generate analysis prompt or run self-analysis",
        )
        analyze_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory (default: latest)",
        )
        analyze_parser.add_argument(
            "--mode",
            choices=["prompt", "self"],
            default="prompt",
            help="Analysis mode: prompt (for Claude Code) or self (multi-agent)",
        )
        analyze_parser.add_argument(
            "--config",
            type=str,
            help="Custom config file for self-analysis mode",
        )
        analyze_parser.add_argument(
            "--ui",
            choices=["automation", "rich_terminal", "webui"],
            default="rich_terminal",
            help="UI mode for self-analysis: rich_terminal (default), automation (headless), or webui",
        )
        analyze_parser.add_argument(
            "--turn",
            "-t",
            type=int,
            help="Specific turn number to analyze (default: latest turn)",
        )
        analyze_parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Overwrite existing report without prompting",
        )

        # Parse logs arguments (skip 'massgen logs')
        logs_args = logs_parser.parse_args(sys.argv[2:])
        sys.exit(logs_command(logs_args))

    # Handle 'serve' subcommand (OpenAI-compatible HTTP server)
    if len(sys.argv) >= 2 and sys.argv[1] == "serve":
        import uvicorn

        from massgen.server.app import create_app
        from massgen.server.settings import ServerSettings

        serve_parser = argparse.ArgumentParser(
            prog="massgen serve",
            description="Run MassGen OpenAI-compatible server (FastAPI + Uvicorn)",
        )
        serve_parser.add_argument(
            "--host",
            type=str,
            default=None,
            help="Host to bind (default: 0.0.0.0)",
        )
        serve_parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Port to bind (default: 4000)",
        )
        serve_parser.add_argument(
            "--config",
            type=str,
            default=None,
            help="Default MassGen config file path",
        )
        serve_parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable auto-reload (dev only)",
        )

        serve_args = serve_parser.parse_args(sys.argv[2:])

        # Reload env in case the user expects serve to pick up .env changes.
        load_env_file()

        # Resolve config path using same logic as main command
        # If --config provided, use it; otherwise auto-discover default config
        resolved_config = None
        try:
            if serve_args.config:
                resolved_config = resolve_config_path(serve_args.config)
            else:
                # Auto-discover: .massgen/config.yaml or ~/.config/massgen/config.yaml
                resolved_config = resolve_config_path(None)
                if resolved_config:
                    print(f"📁 Using default config: {resolved_config}")
        except ConfigurationError as e:
            print(f"❌ Configuration error: {e}", file=sys.stderr, flush=True)
            sys.exit(EXIT_CONFIG_ERROR)

        # Build settings from env, then apply CLI overrides using replace()
        # to preserve any future env-derived fields
        from dataclasses import replace

        settings = ServerSettings.from_env()
        overrides = {}
        if serve_args.host:
            overrides["host"] = serve_args.host
        if serve_args.port:
            overrides["port"] = serve_args.port
        if resolved_config:
            overrides["default_config"] = str(resolved_config)
        if overrides:
            settings = replace(settings, **overrides)

        app = create_app(settings=settings)
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            reload=serve_args.reload,
        )
        return

    # Handle 'export' subcommand specially before main argument parsing
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        from .session_exporter import export_command

        export_parser = argparse.ArgumentParser(
            prog="massgen export",
            description="Share MassGen session via GitHub Gist (requires gh CLI)",
        )
        export_parser.add_argument(
            "log_dir",
            nargs="?",
            help="Log directory to export (default: latest). Can be full path or log name.",
        )
        export_parser.add_argument(
            "--turns",
            "-t",
            default="all",
            help='Turn range to export: "all", "N" (turns 1-N), "N-M", or "latest" (default: all)',
        )
        export_parser.add_argument(
            "--no-workspace",
            action="store_true",
            help="Exclude workspace artifacts from export",
        )
        export_parser.add_argument(
            "--workspace-limit",
            default="500KB",
            help="Max workspace size per agent (e.g., 500KB, 1MB). Default: 500KB",
        )
        export_parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip interactive prompts and use defaults",
        )
        export_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be shared without creating gist",
        )
        export_parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Show detailed file listing",
        )
        export_parser.add_argument(
            "--json",
            action="store_true",
            help="Output result as JSON (useful for scripting)",
        )

        export_args = export_parser.parse_args(sys.argv[2:])
        sys.exit(export_command(export_args))

    # Handle 'shares' subcommand for managing shared sessions
    if len(sys.argv) >= 2 and sys.argv[1] == "shares":
        from rich.console import Console

        from .share import delete_share, list_shares

        shares_parser = argparse.ArgumentParser(
            prog="massgen shares",
            description="Manage shared MassGen sessions",
        )
        shares_subparsers = shares_parser.add_subparsers(dest="shares_command")

        # massgen shares list
        shares_subparsers.add_parser("list", help="List your shared sessions")

        # massgen shares delete <gist_id>
        delete_parser = shares_subparsers.add_parser(
            "delete",
            help="Delete a shared session",
        )
        delete_parser.add_argument("gist_id", help="Gist ID to delete")

        shares_args = shares_parser.parse_args(sys.argv[2:])
        console = Console()

        if shares_args.shares_command == "list":
            sys.exit(list_shares(console))
        elif shares_args.shares_command == "delete":
            sys.exit(delete_share(shares_args.gist_id, console))
        else:
            shares_parser.print_help()
            sys.exit(1)

    parser = main_parser()
    args = parser.parse_args()

    if args.plan_steps is not None and args.plan_steps <= 0:
        print("❌ --plan-steps must be a positive integer")
        sys.exit(2)
    if args.plan_chunks is not None and args.plan_chunks <= 0:
        print("❌ --plan-chunks must be a positive integer")
        sys.exit(2)

    # Validate mode flag combinations
    mode_errors = validate_mode_flag_combinations(args)
    if mode_errors:
        for err in mode_errors:
            print(f"❌ {err}")
        sys.exit(2)

    # Continue with the rest of cli_main() logic
    _cli_main_continued(args)


def main_parser() -> argparse.ArgumentParser:
    """Build and return the main CLI argument parser.

    Extracted so tests can parse arguments without running cli_main().
    """
    from massgen.backend.capabilities import get_all_backend_types

    parser = argparse.ArgumentParser(
        description="MassGen - Multi-Agent Coordination CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration file
  massgen --config config.yaml "What is machine learning?"

  # Quick single agent setup
  massgen --backend openai --model gpt-4o-mini "Explain quantum computing"
  massgen --backend claude --model claude-sonnet-4-20250514 "Analyze this data"

  # Use ChatCompletion backend with custom base URL
  massgen --backend chatcompletion --model gpt-oss-120b --base-url https://api.cerebras.ai/v1/chat/completions "What is 2+2?"

  # Interactive mode
  massgen --config config.yaml
  massgen  # Uses default config if available

  # Timeout control examples
  massgen --config config.yaml --orchestrator-timeout 600 "Complex task"

  # Enable rate limiting (uses limits from rate_limits.yaml)
  massgen --config config.yaml --rate-limit "Your question"

  # Configuration management
  massgen --init          # Create new configuration interactively
  massgen --select        # Choose from available configurations
  massgen --setup         # Set up API keys
  massgen --list-examples # View example configurations

Environment Variables:
    OPENAI_API_KEY      - Required for OpenAI backend
    XAI_API_KEY         - Required for Grok backend
    ANTHROPIC_API_KEY   - Required for Claude backend
    GOOGLE_API_KEY      - Required for Gemini backend (or GEMINI_API_KEY)
    ZAI_API_KEY         - Required for ZAI backend

    CEREBRAS_API_KEY    - For Cerebras AI (cerebras.ai)
    TOGETHER_API_KEY    - For Together AI (together.ai, together.xyz)
    FIREWORKS_API_KEY   - For Fireworks AI (fireworks.ai)
    GROQ_API_KEY        - For Groq (groq.com)
    NEBIUS_API_KEY      - For Nebius AI Studio (studio.nebius.ai)
    OPENROUTER_API_KEY  - For OpenRouter (openrouter.ai)
    POE_API_KEY         - For POE (poe.com)

  Note: The chatcompletion backend auto-detects the provider from the base_url
        and uses the appropriate environment variable for API key.
        """,
    )

    # Question (optional for interactive mode)
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (optional - if not provided, enters interactive mode)",
    )

    # Configuration options
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config",
        type=str,
        help=(
            "Path to YAML/JSON configuration file or @examples/NAME. With "
            "interactive --quickstart, this is used as the output filename under "
            ".massgen/. With --quickstart --headless, this is used as the exact "
            "output config path."
        ),
    )
    config_group.add_argument(
        "--select",
        action="store_true",
        help="Interactively select from available configurations",
    )
    config_group.add_argument(
        "--backend",
        type=str,
        choices=sorted(get_all_backend_types()),
        help="Backend type for quick setup",
    )

    # Quick setup options
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name for quick setup",
    )
    parser.add_argument(
        "--system-message",
        type=str,
        help="System message for quick setup",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        help="Base URL for API endpoint (e.g., https://api.cerebras.ai/v1/chat/completions)",
    )

    # UI options
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable visual coordination display",
    )
    parser.add_argument(
        "--display",
        type=str,
        choices=["rich", "textual"],
        default=None,
        help="Display type: textual (default, recommended TUI), rich (legacy)",
    )
    parser.add_argument(
        "--textual-serve",
        action="store_true",
        help="Serve Textual TUI in browser via textual-serve (http://localhost:8000)",
    )
    parser.add_argument(
        "--textual-serve-port",
        type=int,
        default=8000,
        help="Port for textual-serve (default: 8000)",
    )
    parser.add_argument("--no-logs", action="store_true", help="Disable logging")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging",
    )
    parser.add_argument(
        "--save-streaming-buffers",
        action="store_true",
        help="Save streaming buffers to files in streaming_buffers/ directory (works with all backends)",
    )
    parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Logfire observability for structured tracing of LLM calls, tool executions, and orchestration",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch web UI server for real-time visualization",
    )
    parser.add_argument(
        "--web-quickstart",
        action="store_true",
        help="Launch a temporary browser-based setup + quickstart flow that exits automatically when complete",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8000,
        help="Port for web UI server (default: 8000)",
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="127.0.0.1",
        help="Host for web UI server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open browser when using --web with a question",
    )
    parser.add_argument(
        "--web-review",
        action="store_true",
        default=False,
        help="Enable change review modal in WebUI for approving/rejecting git diffs (requires --web)",
    )
    parser.add_argument(
        "--automation",
        action="store_true",
        help="Enable automation mode: silent output (~10 lines), status.json tracking, meaningful exit codes. "
        "REQUIRED for LLM agents and background execution. Automatically isolates workspaces for parallel runs.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        default=False,
        help="Step mode: run one agent for one step (new_answer or vote), then exit. " "Config must define exactly one agent. Prior answers loaded from --session-dir.",
    )
    parser.add_argument(
        "--session-dir",
        type=str,
        default=None,
        help="Session directory for step mode. Contains agents/{id}/{step}/answer.json inputs " "and receives step outputs. Used with --step.",
    )
    parser.add_argument(
        "--stream-events",
        action="store_true",
        help="Stream events to stdout as JSON lines. Used by parent processes (e.g., TUI subagent modal) " "to receive real-time updates. Implies --automation.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Task planning mode. Agents interactively create structured feature lists and planning documents. "
        "Use --cwd-context to include current directory context and enable user questions via ask_others.",
    )
    parser.add_argument(
        "--cwd-context",
        choices=["ro", "rw", "read", "write"],
        help="Add current working directory to context paths. " "Use ro/read for read-only or rw/write for write permission.",
    )
    parser.add_argument(
        "--plan-depth",
        choices=["dynamic", "shallow", "medium", "deep"],
        default="dynamic",
        help="Plan granularity for --plan mode: dynamic (scope-adaptive), shallow (5-10 tasks), " "medium (20-50 tasks), deep (100-200+ tasks). Default: dynamic.",
    )
    parser.add_argument(
        "--plan-thoroughness",
        choices=["standard", "thorough"],
        default="standard",
        help="Strategic reasoning depth for --plan mode: standard (reasonable justification), "
        "thorough (deep strategic reasoning, anti-patterns, risk analysis, design principles). "
        "Orthogonal to --plan-depth which controls task count. Default: standard.",
    )
    parser.add_argument(
        "--plan-steps",
        type=int,
        default=None,
        help="Optional explicit planning target for task count (for example 30). Omit for dynamic sizing.",
    )
    parser.add_argument(
        "--plan-chunks",
        type=int,
        default=None,
        help="Optional explicit planning target for chunk count (for example 5). Default in plan mode: 1 chunk.",
    )
    parser.add_argument(
        "--broadcast",
        choices=["human", "agents", "false"],
        default=None,
        help="Broadcast mode for --plan mode: 'human' (agents ask critical questions), 'agents' (agents debate), 'false' (fully autonomous). "
        "If not specified, uses config file value or defaults to 'false'.",
    )
    parser.add_argument(
        "--plan-and-execute",
        action="store_true",
        help="Run full plan-and-execute workflow: agents create plan (Phase 1), then automatically execute it (Phase 2). "
        "Combines --plan with automatic execution. Plan stored in .massgen/plans/ for validation and adherence tracking.",
    )
    parser.add_argument(
        "--execute-plan",
        type=str,
        metavar="PLAN_PATH",
        help="Execute an existing plan. Provide the plan directory path (e.g., .massgen/plans/plan_20260115_173113_836955) "
        "or plan ID (e.g., 20260115_173113_836955) or 'latest' for most recent plan. "
        "Skips planning phase and runs execution directly from the frozen plan.",
    )
    parser.add_argument(
        "--spec",
        action="store_true",
        help="Spec creation mode. Agents produce a requirements specification (EARS notation) instead of a task plan. "
        "Output is project_spec.json with requirements, verification criteria, and chunked execution phases.",
    )
    parser.add_argument(
        "--execute-spec",
        type=str,
        metavar="SPEC_PATH",
        help="Execute against an existing spec. Provide the spec directory path, spec ID, or 'latest' for most recent spec session. "
        "Skips spec creation phase and runs execution directly from the frozen spec.",
    )
    parser.add_argument(
        "--no-session-registry",
        action="store_true",
        help="Don't register this session in the global session registry. Used for internal subagent runs.",
    )
    parser.add_argument(
        "--no-parse-at-references",
        action="store_false",
        dest="parse_at_references",
        help="Treat @tokens in prompt text as plain text instead of extracting @path/@path:w context references.",
    )
    parser.add_argument(
        "--eval-criteria",
        type=str,
        metavar="FILE",
        help="Path to JSON file with evaluation criteria. "
        "Each entry: {text, category (primary/standard/stretch), anti_patterns?, verify_by?}. "
        "Also accepts 'description' or 'name' as aliases for 'text'. "
        "Injected as checklist_criteria_inline in coordination config.",
    )
    parser.add_argument(
        "--checklist-criteria-preset",
        type=str,
        metavar="PRESET",
        help="Use a built-in criteria preset (e.g., planning, evaluation, persona, " "decomposition, prompt, analysis, spec). Overrides YAML checklist_criteria_preset.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        metavar="PATH",
        help="Write final answer to specified file path. Works in any mode (automation, interactive, etc.)",
    )
    parser.add_argument(
        "--skip-agent-selector",
        action="store_true",
        help="Skip the Agent Selector interface at the end (useful for terminal recordings/automation). " "MassGen will exit immediately after showing the final answer.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Launch interactive configuration builder to create config file",
    )
    parser.add_argument(
        "--quickstart",
        action="store_true",
        help="Quick setup: specify number of agents/models, get a full-featured config with code tools and Docker, and optionally install skill packages",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Non-interactive mode for --quickstart: auto-detect API keys, "
        "select best backend/model, generate config, pull Docker images, "
        "and install skills. Designed for programmatic use by AI agents.",
    )
    parser.add_argument(
        "--generate-config",
        type=str,
        metavar="PATH",
        help="Generate config file at specified path (non-interactive, requires --config-backend and --config-model)",
    )
    parser.add_argument(
        "--config-agents",
        type=int,
        default=None,
        help="Number of agents for --generate-config or --quickstart --headless (default: 1)",
    )
    parser.add_argument(
        "--config-backend",
        type=str,
        help="Backend provider for --generate-config (e.g., 'openai', 'anthropic', 'gemini')",
    )
    parser.add_argument(
        "--config-model",
        type=str,
        help="Model name for --generate-config (e.g., 'gpt-5', 'claude-sonnet-4', 'gemini-2.5-pro')",
    )
    parser.add_argument(
        "--config-agent-id",
        type=str,
        help="Explicit agent id for single-agent --generate-config or --quickstart --headless runs",
    )
    parser.add_argument(
        "--config-docker",
        action="store_true",
        help="Enable Docker execution mode in generated config",
    )
    parser.add_argument(
        "--config-context-path",
        type=str,
        help="Add context path to generated config",
    )
    parser.add_argument(
        "--quickstart-agent",
        action="append",
        dest="quickstart_agents",
        help="Explicit headless quickstart agent spec. Repeat for mixed providers, e.g. " "--quickstart-agent id=agent_a,backend=claude,model=claude-opus-4-6",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Launch interactive API key setup wizard to configure credentials",
    )
    parser.add_argument(
        "--setup-skills",
        action="store_true",
        help="Install skills (openskills CLI, Anthropic/OpenAI/Vercel collections, Agent Browser skill, Remotion, Crawl4AI)",
    )
    parser.add_argument(
        "--setup-docker",
        action="store_true",
        help="Interactively select and pull MassGen Docker executor images (sudo image recommended by default)",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="List all supported backends with models, capabilities, and auth requirements",
    )
    parser.add_argument(
        "--list-examples",
        action="store_true",
        help="List available example configurations from package",
    )
    parser.add_argument(
        "--example",
        type=str,
        help="Print example config to stdout (e.g., --example basic_multi)",
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Display configuration schema and available parameters",
    )
    parser.add_argument(
        "--schema-backend",
        type=str,
        help="Show schema for specific backend (use with --show-schema)",
    )
    parser.add_argument(
        "--with-examples",
        action="store_true",
        help="Include example configurations in schema display",
    )
    parser.add_argument(
        "--validate",
        type=str,
        metavar="CONFIG_FILE",
        help="Validate a configuration file without running it",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors during validation (use with --validate)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output validation results in JSON format (use with --validate)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip automatic config validation when loading config files",
    )
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Treat config warnings as errors and abort execution",
    )

    # Session options
    session_group = parser.add_argument_group(
        "session management",
        "Load or list memory sessions",
    )
    session_group.add_argument(
        "--session-id",
        type=str,
        help="Load memory from a previous session by ID (e.g., chat_session_a1b2c3d4)",
    )
    session_group.add_argument(
        "--continue",
        action="store_true",
        dest="continue_session",
        help="Continue the most recent session (shortcut for loading last session)",
    )
    session_group.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent memory sessions (default: 10 most recent)",
    )
    session_group.add_argument(
        "--all",
        action="store_true",
        dest="list_all_sessions",
        help="Show all sessions (use with --list-sessions for detailed view)",
    )

    # Timeout options
    timeout_group = parser.add_argument_group(
        "timeout settings",
        "Override timeout settings from config",
    )
    timeout_group.add_argument(
        "--orchestrator-timeout",
        type=int,
        help="Maximum time for orchestrator coordination in seconds (default: 1800)",
    )

    # Rate limit options
    parser.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable rate limiting (uses limits from rate_limits.yaml config)",
    )

    # Mode settings (mirror TUI mode bar toggles)
    add_mode_flags_to_parser(parser)

    return parser


def _load_eval_criteria(file_path: str) -> list[dict]:
    """Load and validate evaluation criteria from a JSON file.

    Returns a list of criteria dicts. Calls sys.exit on error.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"{BRIGHT_RED}Error: --eval-criteria file not found: {file_path}{RESET}")
        sys.exit(EXIT_CONFIG_ERROR)
    try:
        criteria_data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"{BRIGHT_RED}Error: --eval-criteria file is not valid JSON: {e}{RESET}")
        sys.exit(EXIT_CONFIG_ERROR)
    # Accept both bare array [...] and wrapped {"criteria": [...]} format
    # (the latter is what MassGen's quality tools produce)
    if isinstance(criteria_data, dict) and "criteria" in criteria_data:
        criteria_data = criteria_data["criteria"]
    if not isinstance(criteria_data, list):
        print(f'{BRIGHT_RED}Error: --eval-criteria must be a JSON array or {{"criteria": [...]}}{RESET}')
        sys.exit(EXIT_CONFIG_ERROR)

    # Validate each criterion has a text field (or common alias)
    for i, item in enumerate(criteria_data):
        if not isinstance(item, dict):
            print(f"{BRIGHT_RED}Error: --eval-criteria item {i + 1} must be a JSON object, got {type(item).__name__}{RESET}")
            sys.exit(EXIT_CONFIG_ERROR)
        has_text = item.get("text") or item.get("description") or item.get("name")
        if not has_text:
            print(
                f"{BRIGHT_RED}Error: --eval-criteria item {i + 1} missing 'text' field.\n"
                f'  Expected: {{"text": "...", "category": "primary|standard|stretch"}}\n'
                f"  Got keys: {list(item.keys())}{RESET}",
            )
            sys.exit(EXIT_CONFIG_ERROR)

    return criteria_data


def _inject_eval_criteria_into_config(
    config: dict,
    criteria: list[dict],
) -> None:
    """Inject evaluation criteria into config as checklist_criteria_inline.

    Merges into config["orchestrator"]["coordination"]["checklist_criteria_inline"],
    creating intermediate dicts as needed. CLI criteria override any YAML inline criteria.
    """
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "coordination" not in config["orchestrator"]:
        config["orchestrator"]["coordination"] = {}
    config["orchestrator"]["coordination"]["checklist_criteria_inline"] = criteria


def _inject_checklist_criteria_preset_into_config(
    config: dict,
    preset: str,
) -> None:
    """Inject checklist criteria preset into config from CLI flag.

    Sets config["orchestrator"]["coordination"]["checklist_criteria_preset"],
    creating intermediate dicts as needed. CLI flag overrides any YAML preset.
    """
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "coordination" not in config["orchestrator"]:
        config["orchestrator"]["coordination"] = {}
    config["orchestrator"]["coordination"]["checklist_criteria_preset"] = preset


def _cli_main_continued(args):
    """Continuation of cli_main() after argument parsing.

    This is split out because main_parser() was extracted between the parser
    construction and the post-parse logic. This function is called from cli_main().
    """
    # Handle --continue flag BEFORE setup_logging so we can reuse log directory
    if args.continue_session:
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        # Use get_most_recent_continuable_session to skip empty sessions
        recent_session = registry.get_most_recent_continuable_session()
        if not recent_session:
            print("❌ No continuable sessions found (all sessions are empty)")
            print("Run 'massgen --list-sessions' to see available sessions")
            sys.exit(1)
        args.session_id = recent_session["session_id"]
        print(f"🔄 Continuing most recent session: {args.session_id}")

    # Restore log directory from session if loading existing session
    if args.session_id:
        from massgen.logger_config import set_log_base_session_dir
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        if not registry.session_exists(args.session_id):
            print(
                f"❌ Session error: Session '{args.session_id}' not found in registry",
            )
            print("Run 'massgen --list-sessions' to see available sessions")
            sys.exit(1)

        session_metadata = registry.get_session(args.session_id)
        log_directory = session_metadata.get("log_directory")
        if log_directory:
            # Reuse the original log directory for this session
            set_log_base_session_dir(log_directory)
            print(f"📚 Loading session: {args.session_id} (log: {log_directory})")

        # Restore config from session if not explicitly provided
        session_config_path = session_metadata.get("config_path")
        if args.config and session_config_path:
            # Resolve both paths to compare actual files (handles @examples aliases)
            current_resolved = resolve_config_path(args.config)
            session_resolved = Path(session_config_path).resolve() if session_config_path else None

            if current_resolved and session_resolved and current_resolved.resolve() != session_resolved:
                # User is overriding with a different config - warn them
                print("⚠️  Warning: Using different config than original session")
                print(f"   Original: {session_config_path}")
                print(f"   Current:  {args.config}")
        elif not args.config and session_config_path:
            # Automatically load config from session
            args.config = session_config_path
            print(f"📄 Using config from session: {session_config_path}")

    # Handle special commands first (before logging setup to avoid creating log dirs)
    # Note: 'logs' subcommand is handled at the very start of cli_main()

    if args.list_sessions:
        from massgen.session import SessionRegistry, format_session_list

        registry = SessionRegistry()
        # Show all sessions if --all flag is provided, otherwise show recent 10
        limit = None if args.list_all_sessions else 10
        sessions = registry.list_sessions(limit=limit)
        print(format_session_list(sessions, show_all=args.list_all_sessions))
        return

    if args.validate:
        from .config_validator import ConfigValidator

        validator = ConfigValidator()
        result = validator.validate_config_file(args.validate)

        # Output results
        if args.json_output:
            # JSON output for machine parsing
            print(json.dumps(result.to_dict(), indent=2))
        else:
            # Human-readable output
            print(result.format_all())

        # Exit with appropriate code
        if not result.is_valid() or (args.strict and result.has_warnings()):
            sys.exit(1)
        sys.exit(0)

    if args.list_backends:
        _print_backends_table()
        return

    if args.list_examples:
        show_available_examples()
        return

    if args.example:
        print_example_config(args.example)
        return

    if args.show_schema:
        from .schema_display import show_schema

        show_schema(backend=args.schema_backend, show_examples=args.with_examples)
        return

    # Setup logging for all other commands (actual execution, setup, init, etc.)
    setup_logging(debug=args.debug)

    # Configure Logfire observability if requested
    if args.logfire:
        _setup_logfire_observability()

    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug(f"Command line arguments: {vars(args)}")

    quickstart_config_filename = _quickstart_filename_from_config_arg(args.config) if args.quickstart else None
    headless_quickstart_output_path = _headless_quickstart_output_path_from_config_arg(args.config) if args.quickstart else None

    def _run_quickstart_wizard_tui(config_filename: str | None = None):
        """Launch quickstart wizard TUI. Returns result dict or None."""
        try:
            from textual.app import App as _QApp

            from .frontend.displays.textual_widgets import (
                QuickstartWizard,
                WizardCancelled,
                WizardCompleted,
            )

            class _QuickstartWizardApp(_QApp):
                CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                BINDINGS = [("ctrl+c", "quit", "Quit")]

                def __init__(self, quickstart_config_filename: str | None = None):
                    super().__init__(css_path=str(self.CSS_PATH))
                    self._wizard_result = None
                    self._quickstart_config_filename = quickstart_config_filename

                def on_mount(self):
                    self.push_screen(
                        QuickstartWizard(config_filename=self._quickstart_config_filename),
                    )

                def on_wizard_completed(self, message: WizardCompleted) -> None:
                    self._wizard_result = message.result
                    self.exit(message.result)

                def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                    self.exit(None)

                def action_quit(self) -> None:
                    self.exit(None)

                def on_key(self, event) -> None:
                    if event.key == "escape" and len(self.screen_stack) <= 1:
                        self.exit(None)

            app = _QuickstartWizardApp(
                quickstart_config_filename=config_filename,
            )
            return app.run()
        except ImportError as e:
            logger.warning(f"TUI not available for quickstart wizard: {e}")
            return None

    def _handle_quickstart_result(result):
        """Handle quickstart wizard result - launch web/terminal or save only. Returns True if handled."""
        if not result:
            print(f"\n{BRIGHT_YELLOW}⚠️  Quickstart cancelled{RESET}")
            return True

        config_path = result.get("config_path")
        question = result.get("question", "")
        launch_option = result.get("launch_option", "save_only")
        install_skills_now = result.get("install_skills_now", True)

        if config_path:
            _ensure_quickstart_skills_ready(config_path, bool(install_skills_now))

        if config_path and launch_option == "web":
            try:
                from .frontend.web import run_server

                prompt_question = question if question else None
                print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                print(f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}")
                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                auto_url = None
                if prompt_question:
                    import urllib.parse

                    prompt_encoded = urllib.parse.quote(prompt_question)
                    auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                    config_encoded = urllib.parse.quote(config_path)
                    auto_url += f"&config={config_encoded}"
                    print(f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}")

                print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                def open_browser():
                    import time

                    time.sleep(0.5)
                    webbrowser.open(browser_url)

                threading.Thread(target=open_browser, daemon=True).start()
                run_server(
                    host=args.web_host,
                    port=args.web_port,
                    config_path=config_path,
                    automation_mode=False,
                )
            except ImportError as e:
                print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
                print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                logger.debug(f"Import error: {e}")
                sys.exit(1)
            return True
        elif config_path and launch_option == "terminal":
            args.config = config_path
            args.display = "textual"
            if question:
                args.interactive_with_initial_question = question
            args.question = None
            return False  # Continue with normal flow
        elif config_path:
            print(f"\n{BRIGHT_GREEN}✅ Configuration saved to: {config_path}{RESET}")
            print(f'{BRIGHT_CYAN}Run with: massgen --config {config_path} "Your question"{RESET}')
            return True
        else:
            return True

    # Launch interactive API key setup if requested
    # Skip terminal setup if --web is also provided (web UI will handle setup)
    if args.setup and not args.web:
        # Launch TUI Setup Wizard
        try:
            from textual.app import App

            from .frontend.displays.textual_widgets import (
                SetupWizard,
                WizardCancelled,
                WizardCompleted,
            )

            class SetupWizardApp(App):
                """Standalone app for setup wizard."""

                CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                SCREENS = {"wizard": SetupWizard}
                BINDINGS = [("ctrl+c", "quit", "Quit")]

                def __init__(self):
                    super().__init__(css_path=str(self.CSS_PATH))
                    self._wizard_result = None

                def on_mount(self):
                    self.push_screen("wizard")

                def on_wizard_completed(self, message: WizardCompleted) -> None:
                    """Handle wizard completion."""
                    self._wizard_result = message.result
                    self.exit(message.result)

                def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                    """Handle wizard cancellation - exit immediately."""
                    self.exit(None)

                def action_quit(self) -> None:
                    self.exit(None)

                def on_key(self, event) -> None:
                    if event.key == "escape" and len(self.screen_stack) <= 1:
                        self.exit(None)

            app = SetupWizardApp()
            result = app.run()

            if result and result.get("success"):
                print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                configured = result.get("configured_providers", [])
                if configured:
                    print(f"{BRIGHT_CYAN}💡 Configured providers: {', '.join(configured)}{RESET}")

                if result.get("launch_quickstart"):
                    qs_result = _run_quickstart_wizard_tui()
                    if not _handle_quickstart_result(qs_result):
                        pass  # Terminal launch - fall through to normal flow
                    else:
                        return
                else:
                    print(f"{BRIGHT_CYAN}💡 Run 'massgen --quickstart' to create a config and start.{RESET}\n")
            else:
                print(f"\n{BRIGHT_YELLOW}⚠️  Setup cancelled or no changes made{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to configure API keys{RESET}\n")

        except ImportError as e:
            logger.warning(f"TUI not available, falling back to CLI setup: {e}")
            # Fallback to CLI-based setup
            builder = ConfigBuilder()
            api_keys = builder.interactive_api_key_setup()

            if any(api_keys.values()):
                print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can now use MassGen with these providers{RESET}\n")
            else:
                print(f"\n{BRIGHT_YELLOW}⚠️  No API keys configured{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to set them up{RESET}\n")

        return

    # Install skills if requested
    if args.setup_skills:
        from .utils.skills_installer import install_skills

        install_skills()
        return

    # Setup Docker images if requested
    if args.setup_docker:
        setup_docker()
        return

    # Launch textual-serve to serve TUI in browser
    if args.textual_serve:
        try:
            from textual_serve.server import Server
        except ImportError:
            print(f"{BRIGHT_RED}❌ textual-serve not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: uv pip install textual-serve{RESET}")
            sys.exit(1)

        # Build the massgen command to run inside textual-serve
        cmd_parts = ["massgen", "--display", "textual"]
        if hasattr(args, "config") and args.config:
            cmd_parts.extend(["--config", args.config])
        if hasattr(args, "interactive") and args.interactive:
            cmd_parts.append("--interactive")
        if hasattr(args, "question") and args.question:
            cmd_parts.append(f'"{args.question}"')

        cmd = " ".join(cmd_parts)
        port = args.textual_serve_port

        print(f"{BRIGHT_CYAN}🌐 Starting MassGen Textual TUI Server...{RESET}")
        print(f"{BRIGHT_GREEN}   URL: http://localhost:{port}{RESET}")
        print(f"{BRIGHT_GREEN}   Command: {cmd}{RESET}")
        print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

        server = Server(cmd, port=port)
        server.serve()
        return

    if args.web_quickstart:
        try:
            from .frontend.web.server import run_temporary_quickstart_server

            print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web Quickstart...{RESET}")
            print(
                f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}/?temporary=1&wizard=open{RESET}",
            )
            print(
                f"{BRIGHT_YELLOW}   This temporary setup session will close automatically when complete{RESET}\n",
            )

            session_result = run_temporary_quickstart_server(
                host=args.web_host,
                port=args.web_port,
                no_browser=getattr(args, "no_browser", False),
            )
            if session_result.get("status") == "completed":
                config_path = session_result.get("config_path")
                if config_path:
                    print(f"{BRIGHT_GREEN}✅ Configuration saved to: {config_path}{RESET}")
                    print(
                        f'{BRIGHT_CYAN}Run with: massgen --config {config_path} "Your question"{RESET}',
                    )
                return

            print(f"{BRIGHT_YELLOW}⚠️  Web quickstart cancelled{RESET}")
            sys.exit(1)
        except ImportError as e:
            print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
            logger.debug(f"Import error: {e}")
            sys.exit(1)

    # Launch web UI server if requested
    if args.web:
        try:
            from .frontend.web import run_server

            config_path = args.config if hasattr(args, "config") and args.config else None
            question = getattr(args, "question", None)
            automation_mode = getattr(args, "automation", False)

            # Auto-resolve default config (same as main() does)
            if not config_path and automation_mode and question:
                resolved_default = resolve_config_path(None)
                if resolved_default:
                    config_path = str(resolved_default)

            print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
            print(
                f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}",
            )
            if config_path:
                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")
            else:
                print(
                    f"{BRIGHT_YELLOW}   No config specified - use --config or select in UI{RESET}",
                )

            # Build auto-launch URL. V2 is the default UI (no param needed).
            # The frontend auto-starts coordination when both prompt= and config=
            # are in the URL (see App.tsx useEffect at line ~226).
            import urllib.parse

            base_url = f"http://{args.web_host}:{args.web_port}/"
            url_params = []
            if question:
                url_params.append(f"prompt={urllib.parse.quote(question)}")
            if config_path:
                url_params.append(f"config={urllib.parse.quote(config_path)}")
            auto_url = f"{base_url}?{'&'.join(url_params)}" if url_params else base_url
            # Print a short URL for the terminal (no giant prompt)
            short_url_params = []
            if config_path:
                short_url_params.append(f"config={urllib.parse.quote(config_path)}")
            short_url = f"{base_url}?{'&'.join(short_url_params)}" if short_url_params else base_url
            print(f"{BRIGHT_GREEN}   UI: {short_url}{RESET}")

            if automation_mode:
                if question:
                    print(
                        f"{BRIGHT_YELLOW}   Run starting immediately — open browser anytime to monitor{RESET}",
                    )
                else:
                    print(
                        f"{BRIGHT_YELLOW}   No question provided — open the URL above to start a run{RESET}",
                    )

            print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

            # Auto-open browser (unless --no-browser or automation mode)
            no_browser = getattr(args, "no_browser", False)
            if not no_browser and not automation_mode:
                browser_url = auto_url
                separator = "&" if "?" in browser_url else "?"
                if getattr(args, "setup", False):
                    browser_url += f"{separator}setup=open"
                elif getattr(args, "quickstart", False):
                    browser_url += f"{separator}wizard=open"

                def open_browser():
                    import time

                    time.sleep(0.5)  # Wait for server to start
                    webbrowser.open(browser_url)

                threading.Thread(target=open_browser, daemon=True).start()
            cli_overrides = _build_cli_overrides_dict(args)
            run_server(
                host=args.web_host,
                port=args.web_port,
                config_path=config_path,
                automation_mode=automation_mode,
                cli_overrides=cli_overrides or None,
                question=question if question else None,
            )
        except ImportError as e:
            print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
            logger.debug(f"Import error: {e}")
            sys.exit(1)
        return

    # Launch interactive config selector if requested
    if args.select:
        selected_config = interactive_config_selector()
        if selected_config:
            # Update args to use the selected config
            args.config = selected_config
            # Continue to main() with the selected config
        else:
            # User cancelled selection
            return

    # Generate config programmatically if requested
    if args.generate_config:
        if not args.config_backend or not args.config_model:
            print(
                f"{BRIGHT_RED}❌ Error: --config-backend and --config-model are required with --generate-config{RESET}",
            )
            print(
                f"{BRIGHT_CYAN}Example: massgen --generate-config ./config.yaml --config-backend gemini --config-model gemini-2.5-pro{RESET}",
            )
            return

        try:
            builder = ConfigBuilder()
            success = builder.generate_config_programmatic(
                output_path=args.generate_config,
                num_agents=args.config_agents if args.config_agents is not None else 1,
                backend_type=args.config_backend,
                model=args.config_model,
                use_docker=args.config_docker,
                context_path=args.config_context_path,
                agent_id=args.config_agent_id,
            )
            if success:
                print(
                    f"{BRIGHT_GREEN}✅ Configuration saved to: {args.generate_config}{RESET}",
                )
                print(
                    f'{BRIGHT_CYAN}Run with: massgen --config {args.generate_config} "Your question"{RESET}',
                )
            return
        except ValueError as e:
            print(f"{BRIGHT_RED}❌ Error: {e}{RESET}")
            return
        except Exception as e:
            print(f"{BRIGHT_RED}❌ Unexpected error: {e}{RESET}")
            import traceback

            traceback.print_exc()
            return

    # Launch quickstart if requested
    # Skip terminal quickstart if --web is also provided (web UI will show wizard directly)
    if args.quickstart and not args.web:
        # Headless quickstart: auto-detect keys, generate config, no user interaction.
        # Also triggers when stdin is not a TTY (e.g., piped from an AI agent).
        if args.headless or not sys.stdin.isatty():
            builder = ConfigBuilder()
            quickstart_agent_specs = _parse_quickstart_agent_specs(
                getattr(args, "quickstart_agents", None),
            )
            headless_result = builder.run_quickstart_headless(
                output_dir=".massgen",
                output_path=headless_quickstart_output_path,
                num_agents=args.config_agents if args.config_agents is not None else 1,
                backend_override=args.config_backend,
                model_override=args.config_model,
                use_docker=args.config_docker if args.config_docker else None,
                context_path=args.config_context_path,
                agent_specs=quickstart_agent_specs or None,
                agent_id=args.config_agent_id,
            )

            # Docker pull if available and headless
            if headless_result.get("docker_available") and headless_result.get("success"):
                headless_result["docker_pulled"] = _pull_docker_image_headless()

            _print_headless_quickstart_summary(headless_result)

            # Install skills if config was generated
            if headless_result.get("config_path"):
                _ensure_quickstart_skills_ready(headless_result["config_path"], True)

            return

        # Launch TUI Quickstart Wizard
        try:
            result = _run_quickstart_wizard_tui(quickstart_config_filename)
            if _handle_quickstart_result(result):
                return
            # Terminal launch - fall through to normal flow

        except Exception as e:
            logger.warning(f"TUI not available, falling back to CLI quickstart: {e}")
            # Fallback to CLI-based quickstart
            builder = ConfigBuilder()
            result = builder.run_quickstart(
                quickstart_config_filename=quickstart_config_filename,
            )

            if result and len(result) >= 2:
                filepath = result[0]
                question = result[1]
                interface_choice = result[2] if len(result) >= 3 else "terminal"
                install_skills_now = result[3] if len(result) >= 4 else True

                if filepath:
                    _ensure_quickstart_skills_ready(filepath, bool(install_skills_now))

                if filepath and interface_choice == "web":
                    try:
                        from .frontend.web import run_server

                        config_path = filepath
                        prompt_question = question if question else None

                        print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                        print(f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}")
                        print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                        auto_url = None
                        if prompt_question:
                            import urllib.parse

                            prompt_encoded = urllib.parse.quote(prompt_question)
                            auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                            config_encoded = urllib.parse.quote(config_path)
                            auto_url += f"&config={config_encoded}"
                            print(f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}")

                        print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                        browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                        def open_browser():
                            import time

                            time.sleep(0.5)
                            webbrowser.open(browser_url)

                        threading.Thread(target=open_browser, daemon=True).start()
                        run_server(
                            host=args.web_host,
                            port=args.web_port,
                            config_path=config_path,
                            automation_mode=False,
                        )
                    except ImportError as e:
                        print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
                        print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                        logger.debug(f"Import error: {e}")
                        sys.exit(1)
                    return
                elif filepath and question:
                    args.config = filepath
                    args.question = question
                    args.interactive_with_initial_question = question
                    args.question = None
                elif filepath and question == "":
                    args.config = filepath
                    args.question = None
                elif filepath:
                    print(f"\n✅ Configuration saved to: {filepath}")
                    print(f'Run with: massgen --config {filepath} "Your question"')
                    return
                else:
                    return
            else:
                return

    # Launch interactive config builder if requested
    if args.init:
        builder = ConfigBuilder()
        result = builder.run()

        if result and len(result) == 2:
            filepath, question = result
            if filepath and question:
                # Update args to use the newly created config and launch interactive mode with initial question
                args.config = filepath
                args.question = question
                # Store initial question for interactive mode (don't run single-question mode)
                args.interactive_with_initial_question = question
                args.question = None  # Clear to trigger interactive mode instead of single-question
            elif filepath:
                # Config created but user chose not to run
                print(f"\n✅ Configuration saved to: {filepath}")
                print(f'Run with: massgen --config {filepath} "Your question"')
                return
            else:
                # User cancelled
                return
        else:
            # Builder returned None (cancelled or error)
            return

    # First-run detection: auto-trigger setup wizard → quickstart wizard via TUI
    # Note: If config has a 'prompt' key, it will be used (set above), so args.question will be set
    if not args.question and not args.config and not args.model and not args.backend:
        if should_run_builder():
            # Launch TUI Setup Wizard for first-run experience
            try:
                from textual.app import App as _FirstRunApp

                from .frontend.displays.textual_widgets import (
                    SetupWizard,
                    WizardCancelled,
                    WizardCompleted,
                )

                class _FirstRunSetupApp(_FirstRunApp):
                    CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                    SCREENS = {"wizard": SetupWizard}
                    BINDINGS = [("ctrl+c", "quit", "Quit")]

                    def __init__(self):
                        super().__init__(css_path=str(self.CSS_PATH))
                        self._wizard_result = None

                    def on_mount(self):
                        self.push_screen("wizard")

                    def on_wizard_completed(self, message: WizardCompleted) -> None:
                        self._wizard_result = message.result
                        self.exit(message.result)

                    def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                        self.exit(None)

                    def action_quit(self) -> None:
                        self.exit(None)

                    def on_key(self, event) -> None:
                        if event.key == "escape" and len(self.screen_stack) <= 1:
                            self.exit(None)

                setup_app = _FirstRunSetupApp()
                setup_result = setup_app.run()

                if setup_result and setup_result.get("success"):
                    print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                    configured = setup_result.get("configured_providers", [])
                    if configured:
                        print(f"{BRIGHT_CYAN}💡 Configured providers: {', '.join(configured)}{RESET}")

                    # Chain into quickstart wizard (auto-launch or if user clicked the button)
                    launch_qs = setup_result.get("launch_quickstart", False)
                    if launch_qs:
                        qs_result = _run_quickstart_wizard_tui()
                        if not _handle_quickstart_result(qs_result):
                            pass  # Terminal launch - fall through to normal flow
                        else:
                            return
                    else:
                        print(f"{BRIGHT_CYAN}💡 Run 'massgen --quickstart' to create a config and start.{RESET}\n")
                        return
                else:
                    print(f"\n{BRIGHT_YELLOW}⚠️  Setup cancelled{RESET}")
                    print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to configure API keys{RESET}\n")
                    return

            except ImportError:
                # Fallback to CLI-based first-run flow
                builder = ConfigBuilder(default_mode=True)
                existing_api_keys = builder.detect_api_keys()
                cloud_providers = ["openai", "anthropic", "gemini", "grok", "azure_openai"]
                has_api_keys = any(existing_api_keys.get(provider, False) for provider in cloud_providers)

                print()
                print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
                print(f"{BRIGHT_CYAN}  Welcome to MassGen!{RESET}")
                print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
                print()

                if not has_api_keys:
                    print("  Let's first set up your API keys...")
                    print()
                    api_keys = builder.interactive_api_key_setup()
                    if any(api_keys.values()):
                        print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}\n")
                    else:
                        print(f"\n{BRIGHT_YELLOW}⚠️  No API keys configured{RESET}\n")
                else:
                    print(f"{BRIGHT_GREEN}✅ API keys detected{RESET}\n")

                print()
                result = builder.run_quickstart(
                    quickstart_config_filename=quickstart_config_filename,
                )

                if result and len(result) >= 2:
                    filepath = result[0]
                    question = result[1]
                    interface_choice = result[2] if len(result) >= 3 else "terminal"
                    install_skills_now = result[3] if len(result) >= 4 else True

                    if filepath:
                        _ensure_quickstart_skills_ready(filepath, bool(install_skills_now))

                        # Set the config path
                        args.config = filepath

                        # Check if user chose web interface
                        if interface_choice == "web":
                            try:
                                from .frontend.web import run_server

                                config_path = filepath
                                prompt_question = question if question else None

                                print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                                print(
                                    f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}",
                                )
                                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                                auto_url = None
                                if prompt_question:
                                    import urllib.parse

                                    prompt_encoded = urllib.parse.quote(prompt_question)
                                    auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                                    config_encoded = urllib.parse.quote(config_path)
                                    auto_url += f"&config={config_encoded}"
                                    print(
                                        f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}",
                                    )

                                print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                                browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                                def open_browser():
                                    import time

                                    time.sleep(0.5)
                                    webbrowser.open(browser_url)

                                threading.Thread(target=open_browser, daemon=True).start()
                                run_server(
                                    host=args.web_host,
                                    port=args.web_port,
                                    config_path=config_path,
                                    automation_mode=False,
                                )
                            except ImportError as e:
                                print(
                                    f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}",
                                )
                                print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                                logger.debug(f"Import error: {e}")
                                sys.exit(1)
                            return
                        elif question:
                            args.question = question
                        else:
                            print(
                                f"\n{BRIGHT_GREEN}🚀 Launching interactive mode...{RESET}\n",
                            )
                    else:
                        # No filepath - user cancelled
                        return
                else:
                    # Builder returned None - user cancelled
                    return

    # Now call the async main with the parsed arguments
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        # User pressed Ctrl+C - exit gracefully without traceback
        _restore_terminal_for_input()


if __name__ == "__main__":
    cli_main()
