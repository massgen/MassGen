"""
Display implementations for MassGen v2 frontend.
"""

from typing import List, Optional, Dict, Callable, Union
import time
import os
import threading
import unicodedata
import sys
import re
import asyncio
from datetime import datetime
from .base import StreamingDisplay


class SimpleStreamingDisplay(StreamingDisplay):
    """Simple terminal-based streaming display for MassGen v2 orchestrator output."""
    
    def __init__(self, 
                 show_agent_prefixes: bool = True,
                 show_events: bool = True,
                 show_timestamps: bool = False):
        """Initialize simple streaming display.
        
        Args:
            show_agent_prefixes: Whether to show [agent_id] prefixes
            show_events: Whether to show orchestrator events
            show_timestamps: Whether to show timestamps
        """
        super().__init__(
            show_agent_prefixes=show_agent_prefixes,
            show_events=show_events,
            show_timestamps=show_timestamps
        )
        self.show_agent_prefixes = show_agent_prefixes
        self.show_events = show_events
        self.show_timestamps = show_timestamps
    
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """Initialize the display with question and agent IDs."""
        self.agent_ids = agent_ids
        self.agent_outputs = {aid: [] for aid in agent_ids}
        
        print(f"🎯 MassGen v2 Coordination: {question}")
        print(f"👥 Agents: {', '.join(agent_ids)}")
        print("=" * 60)
    
    def display_content(self, source: Optional[str], content: str, chunk_type: str = "content") -> None:
        """Display content from a source (agent or orchestrator)."""
        if not content.strip():
            return
        
        clean_content = content.strip()
        
        # Add timestamp if requested
        timestamp = f"[{time.strftime('%H:%M:%S')}] " if self.show_timestamps else ""
        
        # Handle agent content
        if source and source in self.agent_ids:
            self._display_agent_content(source, clean_content, chunk_type, timestamp)
        
        # Handle orchestrator content
        elif source in ["coordination_hub", "orchestrator", None]:
            self._display_orchestrator_content(clean_content, timestamp)
        
        # Handle other sources
        else:
            print(f"{timestamp}[{source}] {clean_content}")
    
    def _display_agent_content(self, agent_id: str, content: str, chunk_type: str, timestamp: str) -> None:
        """Display content from a specific agent."""
        # Store content
        self._store_agent_output(agent_id, content)
        
        # Format prefix
        prefix = f"[{agent_id}] " if self.show_agent_prefixes else ""
        
        # Display based on type
        if "🔧" in content or chunk_type == "tool_calls":
            print(f"{timestamp}{prefix}🔧 {content}")
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            print(f"{timestamp}{prefix}📊 {content}")
        else:
            print(f"{timestamp}{prefix}{content}", end="", flush=True)
    
    def _display_orchestrator_content(self, content: str, timestamp: str) -> None:
        """Display content from orchestrator."""
        # Handle coordination events
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]) and self.show_events:
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line:
                event = f"🎭 {clean_line}"
                self._store_event(event)
                print(f"\n{timestamp}{event}")
        
        # Handle regular content
        elif not content.startswith('---') and not content.startswith('*Coordinated by'):
            print(f"{timestamp}{content}", end="", flush=True)
    
    def show_final_summary(self) -> None:
        """Show final coordination summary."""
        print(f"\n\n✅ Coordination completed with {len(self.agent_ids)} agents")
        print(f"📊 Total events: {len(self.orchestrator_events)}")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        pass


class ColoredStreamingDisplay(SimpleStreamingDisplay):
    """Enhanced display with color coding and better formatting."""
    
    # ANSI color codes
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'bright_red': '\033[91m',
        'bright_green': '\033[92m',
        'bright_yellow': '\033[93m',
        'bright_blue': '\033[94m',
        'bright_magenta': '\033[95m',
        'bright_cyan': '\033[96m'
    }
    
    def __init__(self, 
                 show_agent_prefixes: bool = True,
                 show_events: bool = True,
                 show_timestamps: bool = False,
                 use_colors: bool = True):
        """Initialize colored streaming display.
        
        Args:
            show_agent_prefixes: Whether to show [agent_id] prefixes
            show_events: Whether to show orchestrator events
            show_timestamps: Whether to show timestamps
            use_colors: Whether to use color output
        """
        super().__init__(show_agent_prefixes, show_events, show_timestamps)
        self.use_colors = use_colors
        self.agent_colors = {}
    
    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.use_colors or color not in self.COLORS:
            return text
        return f"{self.COLORS[color]}{text}{self.COLORS['reset']}"
    
    def _get_agent_color(self, agent_id: str) -> str:
        """Get consistent color for an agent."""
        if agent_id not in self.agent_colors:
            # Assign colors in rotation
            color_options = ['blue', 'green', 'magenta', 'cyan', 'yellow']
            color_index = len(self.agent_colors) % len(color_options)
            self.agent_colors[agent_id] = color_options[color_index]
        return self.agent_colors[agent_id]
    
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """Initialize the display with question and agent IDs."""
        self.agent_ids = agent_ids
        self.agent_outputs = {aid: [] for aid in agent_ids}
        
        print(self._colorize("🎯 MassGen v2 Coordination:", 'bold') + f" {question}")
        
        # Color-code agent list
        colored_agents = []
        for agent_id in agent_ids:
            color = self._get_agent_color(agent_id)
            colored_agents.append(self._colorize(agent_id, color))
        
        print(f"👥 Agents: {', '.join(colored_agents)}")
        print(self._colorize("=" * 60, 'dim'))
    
    def _display_agent_content(self, agent_id: str, content: str, chunk_type: str, timestamp: str) -> None:
        """Display content from a specific agent with colors."""
        # Store content
        self._store_agent_output(agent_id, content)
        
        # Get agent color
        agent_color = self._get_agent_color(agent_id)
        
        # Format prefix with color
        if self.show_agent_prefixes:
            prefix = self._colorize(f"[{agent_id}]", agent_color) + " "
        else:
            prefix = ""
        
        # Display based on type with appropriate colors
        if "🔧" in content or chunk_type == "tool_calls":
            print(f"{timestamp}{prefix}{self._colorize('🔧', 'yellow')} {content}")
        elif any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]):
            status_color = 'green' if '✅' in content else 'bright_blue' if '🗳️' in content else 'yellow'
            print(f"{timestamp}{prefix}{self._colorize('📊', status_color)} {content}")
        else:
            print(f"{timestamp}{prefix}{content}", end="", flush=True)
    
    def _display_orchestrator_content(self, content: str, timestamp: str) -> None:
        """Display content from orchestrator with colors."""
        # Handle coordination events
        if any(marker in content for marker in ["✅", "🗳️", "🔄", "❌"]) and self.show_events:
            clean_line = content.replace('**', '').replace('##', '').strip()
            if clean_line:
                event = f"🎭 {clean_line}"
                self._store_event(event)
                colored_event = self._colorize(event, 'bright_magenta')
                print(f"\n{timestamp}{colored_event}")
        
        # Handle regular content
        elif not content.startswith('---') and not content.startswith('*Coordinated by'):
            print(f"{timestamp}{content}", end="", flush=True)
    
    def show_final_summary(self) -> None:
        """Show final coordination summary with colors."""
        summary = f"✅ Coordination completed with {len(self.agent_ids)} agents"
        events = f"📊 Total events: {len(self.orchestrator_events)}"
        
        print(f"\n\n{self._colorize(summary, 'bright_green')}")
        print(self._colorize(events, 'bright_blue'))


class RichTerminalDisplay(StreamingDisplay):
    """Multi-region streaming display that inherits from StreamingDisplay base class."""
    
    def __init__(self, display_enabled: bool = True, max_lines: int = 10, save_logs: bool = True, answers_dir: Optional[str] = None, silent_mode: bool = False, **kwargs):
        """Initialize RichTerminalDisplay.
        
        Args:
            display_enabled: Whether display is enabled
            max_lines: Maximum lines to display per agent
            save_logs: Whether to save logs to files
            answers_dir: Directory for answer files
            silent_mode: Whether to suppress intermediate log output (only show terminal display)
            **kwargs: Additional configuration options passed to base class
        """
        super().__init__(**kwargs)
        self.display_enabled = display_enabled
        self.max_lines = max_lines
        self.save_logs = save_logs
        self.answers_dir = answers_dir
        self.silent_mode = silent_mode
        self.agent_models: Dict[str, str] = {}
        self.agent_statuses: Dict[str, str] = {}
        self.system_messages: List[str] = []
        self.start_time = time.time()
        self._lock = threading.RLock()
        
        # MassGen-specific state tracking
        self.current_phase = "collaboration"
        self.vote_distribution: Dict[int, int] = {}
        self.consensus_reached = False
        self.representative_agent_id: Optional[int] = None
        self.debate_rounds: int = 0
        
        # Detailed agent state tracking for display
        self._agent_vote_targets: Dict[str, Optional[int]] = {}
        self._agent_chat_rounds: Dict[str, int] = {}
        self._agent_update_counts: Dict[str, int] = {}
        self._agent_votes_cast: Dict[str, int] = {}
        
        # Display caching and debouncing
        self._display_cache = None
        self._last_agent_count = 0
        self._update_timer = None
        self._update_delay = 0.1
        self._display_updating = False
        self._pending_update = False
        
        # ANSI pattern for color handling
        self._ansi_pattern = re.compile(
            r'\x1B(?:'
            r'[@-Z\\-_]'
            r'|'
            r'\['
            r'[0-?]*[ -/]*[@-~]'
            r'|'
            r'\][^\x07]*(?:\x07|\x1B\\)'
            r'|'
            r'[PX^_][^\x1B]*\x1B\\'
            r')'
        )
        
        # Initialize logging if enabled
        if self.save_logs:
            self._setup_logging()
    
    def initialize(self, question: str, agent_ids: List[str]) -> None:
        """Initialize the display for a new coordination session."""
        with self._lock:
            self.agent_ids = agent_ids
            # Convert agent_ids to dict format expected by parent class
            self.agent_outputs = {aid: [] for aid in agent_ids}
            
            # Initialize agent tracking
            for agent_id in agent_ids:
                self.agent_statuses[agent_id] = "unknown"
                self._agent_chat_rounds[agent_id] = 0
                self._agent_update_counts[agent_id] = 0
                self._agent_votes_cast[agent_id] = 0
            
            # Add system message about initialization (only if not in silent mode)
            if not self.silent_mode:
                self.add_system_message(f"🎯 Session initialized: {question}")
                self.add_system_message(f"👥 Agents: {', '.join(agent_ids)}")
            
            # Force initial display update
            self.force_update_display()
    
    def display_content(self, source: Optional[str], content: str, chunk_type: str = "content") -> None:
        """Display content from a source (agent or orchestrator)."""
        if not self.display_enabled or not content.strip():
            return
        
        with self._lock:
            if source and source in self.agent_ids:
                # Agent content - store and display
                self._store_agent_output(source, content)
                self.stream_output_sync(source, content)
            elif source in ["coordination_hub", "orchestrator", None]:
                # Orchestrator content - add as system message (only if not in silent mode)
                if not self.silent_mode:
                    self.add_system_message(content.strip())
            else:
                # Other sources - add as system message with source prefix (only if not in silent mode)
                if not self.silent_mode:
                    self.add_system_message(f"[{source}] {content.strip()}")
    
    def show_final_summary(self) -> None:
        """Show final coordination summary."""
        summary_msg = f"✅ Coordination completed with {len(self.agent_ids)} agents"
        events_msg = f"📊 Total events: {len(self.orchestrator_events)}"
        
        if not self.silent_mode:
            self.add_system_message(summary_msg)
            self.add_system_message(events_msg)
        self.force_update_display()
    
    def cleanup(self) -> None:
        """Clean up resources when display is no longer needed."""
        with self._lock:
            if self._update_timer:
                self._update_timer.cancel()
                self._update_timer = None
            self._pending_update = False
            self._display_updating = False
    
    # Multi-region display methods adapted from streaming_display.py
    def _get_terminal_width(self):
        """Get terminal width with conservative fallback."""
        try:
            return os.get_terminal_size().columns
        except:
            return 120
    
    def _calculate_layout(self, num_agents: int):
        """Calculate layout dimensions for consistent display."""
        if (self._display_cache is None or 
            self._last_agent_count != num_agents):
            
            terminal_width = self._get_terminal_width()
            border_chars = num_agents + 1
            safety_margin = 10
            
            available_width = terminal_width - border_chars - safety_margin
            col_width = max(25, available_width // num_agents)
            total_width = (col_width * num_agents) + border_chars
            
            if total_width > terminal_width - 2:
                col_width = max(20, (terminal_width - border_chars - 4) // num_agents)
                total_width = (col_width * num_agents) + border_chars
            
            self._display_cache = {
                'col_width': col_width,
                'total_width': total_width,
                'terminal_width': terminal_width,
                'num_agents': num_agents,
                'border_chars': border_chars
            }
            self._last_agent_count = num_agents
        
        cache = self._display_cache
        return cache['col_width'], cache['total_width'], cache['terminal_width']
    
    def _get_display_width(self, text: str) -> int:
        """Calculate the actual display width of text with ANSI and Unicode handling."""
        if not text:
            return 0
        
        clean_text = self._ansi_pattern.sub('', text)
        width = 0
        
        for char in clean_text:
            if ord(char) < 32 or ord(char) == 127:
                continue
            if unicodedata.combining(char):
                continue
            width += self._get_char_width(char)
        
        return width
    
    def _get_char_width(self, char: str) -> int:
        """Get the display width of a single character."""
        char_code = ord(char)
        
        if 32 <= char_code <= 126:
            return 1
        
        # Handle emoji and wide characters
        if ((0x1F600 <= char_code <= 0x1F64F) or
            (0x1F300 <= char_code <= 0x1F5FF) or
            (0x1F680 <= char_code <= 0x1F6FF) or
            (0x2600 <= char_code <= 0x26FF)):
            return 2
        
        east_asian_width = unicodedata.east_asian_width(char)
        if east_asian_width in ('F', 'W'):
            return 2
        
        return 1
    
    def _pad_to_width(self, text: str, target_width: int, align: str = 'left') -> str:
        """Pad text to exact target width with proper ANSI and Unicode handling."""
        if target_width <= 0:
            return ""
        
        current_width = self._get_display_width(text)
        
        if current_width > target_width:
            # Simple truncation for now
            return text[:target_width-1] + "…" if target_width > 1 else "…"
        
        padding = target_width - current_width
        if padding <= 0:
            return text
        
        if align == 'center':
            left_pad = padding // 2
            right_pad = padding - left_pad
            return " " * left_pad + text + " " * right_pad
        elif align == 'right':
            return " " * padding + text
        else:
            return text + " " * padding
    
    def _create_bordered_line(self, content_parts: List[str], total_width: int) -> str:
        """Create a single bordered line with guaranteed correct width."""
        validated_parts = []
        for part in content_parts:
            if self._get_display_width(part) != self._display_cache['col_width']:
                part = self._pad_to_width(part, self._display_cache['col_width'], 'left')
            validated_parts.append(part)
        
        line = "│" + "│".join(validated_parts) + "│"
        
        # Final width validation
        actual_width = self._get_display_width(line)
        if actual_width != total_width:
            if actual_width > total_width:
                clean_line = self._ansi_pattern.sub('', line)
                if len(clean_line) > total_width:
                    clean_line = clean_line[:total_width-1] + "│"
                line = clean_line
            else:
                line += " " * (total_width - actual_width)
        
        return line
    
    def _create_system_bordered_line(self, content: str, total_width: int) -> str:
        """Create a system section line with borders."""
        content_width = total_width - 2
        if content_width <= 0:
            return "│" + " " * max(0, total_width - 2) + "│"
        
        padded_content = self._pad_to_width(content, content_width, 'left')
        line = f"│{padded_content}│"
        
        actual_width = self._get_display_width(line)
        if actual_width != total_width:
            if actual_width < total_width:
                line += " " * (total_width - actual_width)
            elif actual_width > total_width:
                clean_line = self._ansi_pattern.sub('', line)
                if len(clean_line) > total_width:
                    clean_line = clean_line[:total_width-1] + "│"
                line = clean_line
        
        return line
    
    def _clear_terminal_atomic(self):
        """Atomically clear terminal using proper ANSI sequences."""
        try:
            sys.stdout.write('\033[2J')
            sys.stdout.write('\033[H')
            sys.stdout.flush()
        except Exception:
            try:
                os.system('clear' if os.name == 'posix' else 'cls')
            except Exception:
                pass
    
    def _schedule_display_update(self):
        """Schedule a debounced display update to prevent rapid refreshes."""
        with self._lock:
            if self._update_timer:
                self._update_timer.cancel()
            
            self._pending_update = True
            self._update_timer = threading.Timer(self._update_delay, self._execute_display_update)
            self._update_timer.start()
    
    def _execute_display_update(self):
        """Execute the actual display update."""
        with self._lock:
            if not self._pending_update:
                return
                
            if self._display_updating:
                self._update_timer = threading.Timer(self._update_delay, self._execute_display_update)
                self._update_timer.start()
                return
            
            self._display_updating = True
            self._pending_update = False
        
        try:
            self._update_display_immediate()
        finally:
            with self._lock:
                self._display_updating = False
    
    def _setup_logging(self):
        """Set up the logging directory and initialize log files."""
        base_logs_dir = "logs"
        os.makedirs(base_logs_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_logs_dir = os.path.join(base_logs_dir, timestamp, "display")
        os.makedirs(self.session_logs_dir, exist_ok=True)
        
        self.agent_log_files = {}
        self.system_log_file = os.path.join(self.session_logs_dir, "system.txt")
        
        with open(self.system_log_file, 'w', encoding='utf-8') as f:
            f.write(f"MassGen System Messages Log\n")
            f.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
    
    def _get_agent_log_file(self, agent_id: str) -> str:
        """Get or create the log file path for a specific agent."""
        if agent_id not in self.agent_log_files:
            self.agent_log_files[agent_id] = os.path.join(self.session_logs_dir, f"agent_{agent_id}.txt")
            
            with open(self.agent_log_files[agent_id], 'w', encoding='utf-8') as f:
                f.write(f"MassGen Agent {agent_id} Output Log\n")
                f.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
        
        return self.agent_log_files[agent_id]
    
    def _write_agent_log(self, agent_id: str, content: str):
        """Write content to the agent's log file."""
        if not self.save_logs:
            return
            
        try:
            log_file = self._get_agent_log_file(agent_id)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(content)
                f.flush()
        except Exception as e:
            if not self.silent_mode:
                print(f"Error writing to agent {agent_id} log: {e}")
    
    def _write_system_log(self, message: str):
        """Write a system message to the system log file."""
        if not self.save_logs:
            return
            
        try:
            with open(self.system_log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%H:%M:%S')
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
        except Exception as e:
            if not self.silent_mode:
                print(f"Error writing to system log: {e}")
    
    def stream_output_sync(self, agent_id: str, content: str):
        """Stream output with debounced display updates."""
        if not self.display_enabled:
            return
            
        with self._lock:
            # Convert to list format expected by parent class
            if agent_id not in self.agent_outputs:
                self.agent_outputs[agent_id] = []
            
            # Handle special content markers
            display_content = content
            log_content = content
            
            if content.startswith('[CODE_DISPLAY_ONLY]'):
                display_content = content[len('[CODE_DISPLAY_ONLY]'):]
                log_content = ""
            elif content.startswith('[CODE_LOG_ONLY]'):
                display_content = ""
                log_content = content[len('[CODE_LOG_ONLY]'):]
            
            # Add to display output and store
            if display_content:
                self.agent_outputs[agent_id].append(display_content)
                self._store_agent_output(agent_id, display_content)
            
            # Write to log file
            if log_content:
                self._write_agent_log(agent_id, log_content)
            
            # Schedule display update
            if display_content:
                self._schedule_display_update()
    
    def add_system_message(self, message: str):
        """Add a system message with timestamp."""
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            self.system_messages.append(formatted_message)
            self._store_event(formatted_message)
            
            # Keep only recent messages
            if len(self.system_messages) > 20:
                self.system_messages = self.system_messages[-20:]
                
            # Write to system log
            self._write_system_log(formatted_message + "\n")
    
    def set_agent_model(self, agent_id: str, model_name: str):
        """Set the model name for a specific agent."""
        with self._lock:
            self.agent_models[agent_id] = model_name
            if agent_id not in self.agent_outputs:
                self.agent_outputs[agent_id] = []
    
    def update_agent_status(self, agent_id: str, status: str):
        """Update agent status."""
        with self._lock:
            old_status = self.agent_statuses.get(agent_id, "unknown")
            self.agent_statuses[agent_id] = status
            
            if agent_id not in self.agent_outputs:
                self.agent_outputs[agent_id] = []
            
            # Always show agent status updates regardless of silent_mode
            # as they are important system state information
            status_msg = f"Agent {agent_id}: {old_status} → {status}"
            self.add_system_message(status_msg)
            
            # Force display update to show status changes immediately
            self._schedule_display_update()
    
    def _update_display_immediate(self):
        """Immediate display update with multi-region layout."""
        if not self.display_enabled:
            return
            
        try:
            self._clear_terminal_atomic()
            
            agent_ids = sorted(self.agent_outputs.keys())
            if not agent_ids:
                return
            
            num_agents = len(agent_ids)
            col_width, total_width, terminal_width = self._calculate_layout(num_agents)
        except Exception as e:
            if not self.silent_mode:
                print(f"Display error: {e}")
                for agent_id in sorted(self.agent_outputs.keys()):
                    recent_output = self.agent_outputs[agent_id][-5:] if self.agent_outputs[agent_id] else []
                    print(f"Agent {agent_id}: {' '.join(recent_output)}")
            return
        
        # Prepare agent content lines
        agent_lines = {}
        max_lines = 0
        for agent_id in agent_ids:
            # Join list items and split into lines
            content = '\n'.join(self.agent_outputs[agent_id]) if self.agent_outputs[agent_id] else ""
            lines = content.split('\n')
            if len(lines) > self.max_lines:
                lines = lines[-self.max_lines:]
            agent_lines[agent_id] = lines
            max_lines = max(max_lines, len(lines))
        
        # Create display
        border_line = "─" * total_width
        
        # ANSI colors
        BRIGHT_CYAN = '\033[96m'
        BRIGHT_BLUE = '\033[94m'
        BRIGHT_GREEN = '\033[92m'
        BRIGHT_YELLOW = '\033[93m'
        BRIGHT_MAGENTA = '\033[95m'
        BRIGHT_RED = '\033[91m'
        BRIGHT_WHITE = '\033[97m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        
        # Header
        print("")
        header_top = f"{BRIGHT_CYAN}{BOLD}╔{'═' * (total_width - 2)}╗{RESET}"
        print(header_top)
        
        title_text = "🚀 MassGen v2 - Multi-Agent Coordination 🚀"
        title_line_content = self._pad_to_width(title_text, total_width - 2, 'center')
        title_line = f"{BRIGHT_CYAN}║{BRIGHT_YELLOW}{BOLD}{title_line_content}{RESET}{BRIGHT_CYAN}║{RESET}"
        print(title_line)
        
        header_bottom = f"{BRIGHT_CYAN}{BOLD}╚{'═' * (total_width - 2)}╝{RESET}"
        print(header_bottom)
        
        # Agent section
        print(f"\n{border_line}")
        
        # Agent headers
        header_parts = []
        for agent_id in agent_ids:
            model_name = self.agent_models.get(agent_id, "")
            status = self.agent_statuses.get(agent_id, "unknown")
            
            status_config = {
                "working": {"emoji": "🔄", "color": BRIGHT_YELLOW},
                "voted": {"emoji": "✅", "color": BRIGHT_GREEN}, 
                "failed": {"emoji": "❌", "color": BRIGHT_RED},
                "unknown": {"emoji": "❓", "color": BRIGHT_WHITE}
            }
            
            config = status_config.get(status, status_config["unknown"])
            emoji = config["emoji"]
            status_color = config["color"]
            
            if model_name:
                agent_header = f"{emoji} {BRIGHT_CYAN}Agent {agent_id}{RESET} {BRIGHT_MAGENTA}({model_name}){RESET} {status_color}[{status}]{RESET}"
            else:
                agent_header = f"{emoji} {BRIGHT_CYAN}Agent {agent_id}{RESET} {status_color}[{status}]{RESET}"
            
            header_content = self._pad_to_width(agent_header, col_width, 'center')
            header_parts.append(header_content)
        
        try:
            header_line = self._create_bordered_line(header_parts, total_width)
            print(header_line)
        except Exception:
            print("─" * total_width)
        
        print(border_line)
        
        # Content area
        for line_idx in range(max_lines):
            content_parts = []
            for agent_id in agent_ids:
                lines = agent_lines[agent_id]
                content = lines[line_idx] if line_idx < len(lines) else ""
                padded_content = self._pad_to_width(content, col_width, 'left')
                content_parts.append(padded_content)
            
            try:
                content_line = self._create_bordered_line(content_parts, total_width)
                print(content_line)
            except Exception:
                simple_line = " | ".join(content_parts)[:total_width-4]
                print(f"│ {simple_line} │")
        
        # System status section
        if self.system_messages:
            print(f"\n{border_line}")
            
            system_header_text = f"{BRIGHT_CYAN}📋 SYSTEM STATUS{RESET}"
            system_header_line = self._create_system_bordered_line(system_header_text, total_width)
            print(system_header_line)
            
            print(border_line)
            
            # System messages
            for message in self.system_messages[-5:]:  # Show last 5 messages
                max_content_width = total_width - 2
                if self._get_display_width(message) <= max_content_width:
                    line = self._create_system_bordered_line(message, total_width)
                    print(line)
                else:
                    # Simple word wrapping
                    words = message.split()
                    current_line = ""
                    
                    for word in words:
                        test_line = f"{current_line} {word}".strip()
                        if self._get_display_width(test_line) > max_content_width:
                            if current_line.strip():
                                line = self._create_system_bordered_line(current_line.strip(), total_width)
                                print(line)
                            current_line = word
                        else:
                            current_line = test_line
                    
                    if current_line.strip():
                        line = self._create_system_bordered_line(current_line.strip(), total_width)
                        print(line)
        
        # Final border
        print(border_line)
        sys.stdout.flush()
    
    def force_update_display(self):
        """Force an immediate display update."""
        with self._lock:
            if self._update_timer:
                self._update_timer.cancel()
            self._pending_update = True
        self._execute_display_update()
    
    # =============================================================================
    # ASYNC-FRIENDLY WRAPPER METHODS
    # =============================================================================
    
    def display_content_async_safe(self, source: Optional[str], content: str, chunk_type: str = "content") -> None:
        """Async-safe wrapper for display_content - can be called from async context."""
        try:
            # Use run_in_executor to avoid blocking the async event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, schedule the call to run in thread pool
                asyncio.create_task(
                    loop.run_in_executor(None, self.display_content, source, content, chunk_type)
                )
            else:
                # Not in async context, call directly
                self.display_content(source, content, chunk_type)
        except Exception:
            # Fallback to direct call if async approach fails
            self.display_content(source, content, chunk_type)
    
    def update_agent_status_async_safe(self, agent_id: str, status: str) -> None:
        """Async-safe wrapper for update_agent_status."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    loop.run_in_executor(None, self.update_agent_status, agent_id, status)
                )
            else:
                self.update_agent_status(agent_id, status)
        except Exception:
            self.update_agent_status(agent_id, status)
    
    def add_system_message_async_safe(self, message: str) -> None:
        """Async-safe wrapper for add_system_message."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    loop.run_in_executor(None, self.add_system_message, message)
                )
            else:
                self.add_system_message(message)
        except Exception:
            self.add_system_message(message)
    
    def show_final_summary_async_safe(self) -> None:
        """Async-safe wrapper for show_final_summary."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    loop.run_in_executor(None, self.show_final_summary)
                )
            else:
                self.show_final_summary()
        except Exception:
            self.show_final_summary()