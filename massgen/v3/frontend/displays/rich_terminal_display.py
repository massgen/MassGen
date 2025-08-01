"""
Rich Terminal Display for MassGen Coordination

Enhanced terminal interface using Rich library with live updates, 
beautiful formatting, code highlighting, and responsive layout.
"""

import re
import time
import threading
import asyncio
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
from .terminal_display import TerminalDisplay

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.text import Text
    from rich.layout import Layout
    from rich.align import Align
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.status import Status
    from rich.box import ROUNDED, HEAVY, DOUBLE
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Provide dummy classes when Rich is not available
    class Layout:
        pass
    class Panel:
        pass
    class Console:
        pass
    class Live:
        pass
    class Columns:
        pass
    class Table:
        pass
    class Syntax:
        pass
    class Text:
        pass
    class Align:
        pass
    class Progress:
        pass
    class SpinnerColumn:
        pass
    class TextColumn:
        pass
    class Status:
        pass
    ROUNDED = HEAVY = DOUBLE = None


class RichTerminalDisplay(TerminalDisplay):
    """Enhanced terminal display using Rich library for beautiful formatting."""
    
    def __init__(self, agent_ids: List[str], **kwargs):
        """Initialize rich terminal display.
        
        Args:
            agent_ids: List of agent IDs to display
            **kwargs: Additional configuration options
                - theme: Color theme ('dark', 'light', 'cyberpunk') (default: 'dark')
                - refresh_rate: Display refresh rate in Hz (default: 4)
                - enable_syntax_highlighting: Enable code syntax highlighting (default: True)
                - max_content_lines: Base lines per agent column before scrolling (default: 8)
                - show_timestamps: Show timestamps for events (default: True)
                - enable_status_jump: Enable jumping to latest status when agent status changes (default: True)
                - truncate_web_search_on_status_change: Truncate web search content when status changes (default: True)
                - max_web_search_lines_on_status_change: Max web search lines to keep on status changes (default: 3)
        """
        if not RICH_AVAILABLE:
            raise ImportError(
                "Rich library is required for RichTerminalDisplay. "
                "Install with: pip install rich"
            )
        
        super().__init__(agent_ids, **kwargs)
        
        # Rich-specific configuration
        self.theme = kwargs.get('theme', 'dark')
        self.refresh_rate = kwargs.get('refresh_rate', 30)  # Further increased refresh rate for near real-time updates
        self.enable_syntax_highlighting = kwargs.get('enable_syntax_highlighting', True)
        self.max_content_lines = kwargs.get('max_content_lines', 8)
        self.max_line_length = kwargs.get('max_line_length', 100)
        self.show_timestamps = kwargs.get('show_timestamps', True)
        
        # Initialize Rich console and detect terminal dimensions
        self.console = Console(force_terminal=True, legacy_windows=False)
        self.terminal_size = self.console.size
        # Fixed column width calculation - divide terminal width evenly among agents
        self.num_agents = len(agent_ids)
        self.fixed_column_width = max(20, self.terminal_size.width // self.num_agents - 1)
        self.agent_panel_height = max(10, self.terminal_size.height - 13)  # Reserve space for header(5) + footer(8)
        
        self.live = None
        self._lock = threading.RLock()
        self._last_update = 0
        self._update_interval = 0  # No throttling for immediate updates
        self._last_full_refresh = 0
        self._full_refresh_interval = 0.05  # Much faster full refresh for real-time consistency
        
        # Async refresh components - more workers for faster updates
        self._refresh_executor = ThreadPoolExecutor(max_workers=min(len(agent_ids) * 2 + 8, 20))
        self._agent_panels_cache = {}
        self._header_cache = None
        self._footer_cache = None
        self._layout_update_lock = threading.Lock()
        self._pending_updates = set()
        self._shutdown_flag = False
        
        # Priority update queue for critical status changes
        self._priority_updates = set()
        self._status_update_executor = ThreadPoolExecutor(max_workers=4)
        
        # Theme configuration
        self._setup_theme()
        
        # Interactive mode variables
        self._interactive_mode = kwargs.get('interactive_mode', True)
        self._key_handler = None
        
        # Code detection patterns
        self.code_patterns = [
            r'```(\w+)?\n(.*?)\n```',  # Markdown code blocks
            r'`([^`]+)`',  # Inline code
            r'def\s+\w+\s*\(',  # Python functions
            r'class\s+\w+\s*[:(\s]',  # Python classes
            r'import\s+\w+',  # Python imports
            r'from\s+\w+\s+import',  # Python from imports
        ]
        
        # Progress tracking
        self.agent_progress = {agent_id: 0 for agent_id in agent_ids}
        self.agent_activity = {agent_id: "waiting" for agent_id in agent_ids}
        
        # Status change tracking to prevent unnecessary refreshes
        self._last_agent_status = {agent_id: "waiting" for agent_id in agent_ids}
        self._last_agent_activity = {agent_id: "waiting" for agent_id in agent_ids}
        self._last_content_hash = {agent_id: "" for agent_id in agent_ids}
        
        # Debounce mechanism for updates - reduced for faster response
        self._debounce_timers = {}
        self._debounce_delay = 0.01  # 10ms debounce delay for near-instant updates
        
        # Message filtering settings - tool content always important
        self._important_content_types = {"presentation", "status", "tool", "error"}
        self._status_change_keywords = {"completed", "failed", "waiting", "error", "voted", "voting", "tool"}
        self._important_event_keywords = {"completed", "failed", "voting", "voted", "final", "error", "started", "coordination", "tool"}
        
        # Status jump mechanism for web search interruption
        self._status_jump_enabled = kwargs.get('enable_status_jump', True)  # Enable jumping to latest status
        self._web_search_truncate_on_status_change = kwargs.get('truncate_web_search_on_status_change', True)  # Truncate web search content on status changes
        self._max_web_search_lines = kwargs.get('max_web_search_lines_on_status_change', 3)  # Maximum lines to keep from web search when status changes
        
        # File-based output system
        self.output_dir = kwargs.get('output_dir', 'agent_outputs')
        self.agent_files = {}
        self._selected_agent = None
        self._setup_agent_files()
    
    def _setup_agent_files(self):
        """Setup individual txt files for each agent."""
        # Create output directory if it doesn't exist
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize file paths for each agent
        for agent_id in self.agent_ids:
            file_path = Path(self.output_dir) / f"{agent_id}.txt"
            self.agent_files[agent_id] = file_path
            # Clear existing file content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"=== {agent_id.upper()} OUTPUT LOG ===\n\n")
    
    def _setup_theme(self):
        """Setup color theme configuration."""
        themes = {
            'dark': {
                'primary': 'bright_cyan',
                'secondary': 'bright_blue', 
                'success': 'bright_green',
                'warning': 'bright_yellow',
                'error': 'bright_red',
                'info': 'bright_magenta',
                'text': 'white',
                'border': 'blue',
                'panel_style': 'blue',
                'header_style': 'bold bright_cyan'
            },
            'light': {
                'primary': 'blue',
                'secondary': 'cyan',
                'success': 'green', 
                'warning': 'yellow',
                'error': 'red',
                'info': 'magenta',
                'text': 'black',
                'border': 'blue',
                'panel_style': 'blue',
                'header_style': 'bold blue'
            },
            'cyberpunk': {
                'primary': 'bright_magenta',
                'secondary': 'bright_cyan',
                'success': 'bright_green',
                'warning': 'bright_yellow', 
                'error': 'bright_red',
                'info': 'bright_blue',
                'text': 'bright_white',
                'border': 'bright_magenta',
                'panel_style': 'bright_magenta',
                'header_style': 'bold bright_magenta'
            }
        }
        
        self.colors = themes.get(self.theme, themes['dark'])
    
    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize the rich display with question and optional log file."""
        self.log_filename = log_filename
        self.question = question
        
        # Clear screen
        self.console.clear()
        
        # Create initial layout
        self._create_initial_display()
        
        # Setup keyboard handling if in interactive mode
        if self._interactive_mode:
            self._setup_keyboard_handler()
        
        # Start live display with optimized settings
        self.live = Live(
            self._create_layout(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
            vertical_overflow="ellipsis",  # Enable scrolling when content overflows
            transient=False  # Keep content persistent for better performance
        )
        self.live.start()
        
        # Interactive mode is handled through input prompts
    
    def _create_initial_display(self):
        """Create the initial welcome display."""
        welcome_text = Text()
        welcome_text.append("🚀 MassGen Coordination Dashboard 🚀\n", style=self.colors['header_style'])
        welcome_text.append(f"Multi-Agent System with {len(self.agent_ids)} agents\n", style=self.colors['primary'])
        
        if self.log_filename:
            welcome_text.append(f"📁 Log: {self.log_filename}\n", style=self.colors['info'])
        
        welcome_text.append(f"🎨 Theme: {self.theme.title()}", style=self.colors['secondary'])
        
        welcome_panel = Panel(
            welcome_text,
            box=DOUBLE,
            border_style=self.colors['border'],
            title="[bold]Welcome[/bold]",
            title_align="center"
        )
        
        self.console.print(welcome_panel)
        self.console.print()
    
    def _create_layout(self) -> Layout:
        """Create the main layout structure with cached components."""
        layout = Layout()
        
        # Use cached components if available, otherwise create new ones
        header = self._header_cache if self._header_cache else self._create_header()
        agent_columns = self._create_agent_columns_from_cache()
        footer = self._footer_cache if self._footer_cache else self._create_footer()
        
        # Arrange layout
        layout.split_column(
            Layout(header, name="header", size=5),
            Layout(agent_columns, name="main"),
            Layout(footer, name="footer", size=8)
        )
        
        return layout
    
    def _create_agent_columns_from_cache(self) -> Columns:
        """Create agent columns using cached panels with fixed widths."""
        agent_panels = []
        
        for agent_id in self.agent_ids:
            if agent_id in self._agent_panels_cache:
                agent_panels.append(self._agent_panels_cache[agent_id])
            else:
                panel = self._create_agent_panel(agent_id)
                self._agent_panels_cache[agent_id] = panel
                agent_panels.append(panel)
        
        # Use fixed column widths with equal=False to enforce exact sizing
        return Columns(agent_panels, equal=False, expand=False, width=self.fixed_column_width)
    
    def _create_header(self) -> Panel:
        """Create the header panel."""
        header_text = Text()
        header_text.append("🚀 MassGen Multi-Agent Coordination System", style=self.colors['header_style'])
        
        if hasattr(self, 'question'):
            header_text.append(f"\n💡 Question: {self.question[:80]}{'...' if len(self.question) > 80 else ''}", 
                             style=self.colors['info'])
        
        return Panel(
            Align.center(header_text),
            box=ROUNDED,
            border_style=self.colors['border'],
            height=5
        )
    
    def _create_agent_columns(self) -> Columns:
        """Create columns for each agent with fixed widths."""
        agent_panels = []
        
        for agent_id in self.agent_ids:
            panel = self._create_agent_panel(agent_id)
            agent_panels.append(panel)
        
        # Use fixed column widths with equal=False to enforce exact sizing
        return Columns(agent_panels, equal=False, expand=False, width=self.fixed_column_width)
    
    def _setup_keyboard_handler(self):
        """Setup keyboard handler for interactive agent selection."""
        try:
            # Simple key mapping for agent selection
            self._agent_keys = {}
            for i, agent_id in enumerate(self.agent_ids):
                key = str(i + 1)
                self._agent_keys[key] = agent_id
                
        except ImportError:
            # Fall back to non-interactive mode if keyboard library not available
            self._interactive_mode = False
    
    def _handle_key_press(self, key):
        """Handle key press events for agent selection."""
        if key in self._agent_keys:
            agent_id = self._agent_keys[key]
            self._show_agent_full_content(agent_id)
        elif key == 'q':
            # Quit/return to main view
            self._selected_agent = None
            self._refresh_display()
    
    def _show_agent_full_content(self, agent_id: str):
        """Display full content of selected agent from txt file."""
        if agent_id not in self.agent_files:
            return
        
        try:
            file_path = self.agent_files[agent_id]
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Clear screen and show content
                self.console.clear()
                
                # Create header
                header_text = Text()
                header_text.append(f"📄 {agent_id.upper()} - Full Content", style=self.colors['header_style'])
                header_text.append("\nPress any key to return to main view", style=self.colors['info'])
                
                header_panel = Panel(
                    header_text,
                    box=DOUBLE,
                    border_style=self.colors['border']
                )
                
                # Create content panel
                content_panel = Panel(
                    content,
                    title=f"[bold]{agent_id.upper()} Output[/bold]",
                    border_style=self.colors['border'],
                    box=ROUNDED
                )
                
                self.console.print(header_panel)
                self.console.print(content_panel)
                
                # Wait for key press to return
                input("Press Enter to return to main view...")
                
                # Return to main display
                self.console.clear()
                if self.live:
                    self.live.update(self._create_layout())
                    
        except Exception as e:
            # Handle errors gracefully
            pass
    
    def show_agent_selector(self):
        """Show agent selector and handle user input."""
        if not self._interactive_mode or not hasattr(self, '_agent_keys'):
            return
        
        # Display available options
        options_text = Text()
        options_text.append("\n🎮 Select an agent to view full output:\n", style=self.colors['primary'])
        
        for key, agent_id in self._agent_keys.items():
            options_text.append(f"  {key}: {agent_id.upper()}\n", style=self.colors['text'])
        
        options_text.append("  q: Return to main view\n", style=self.colors['info'])
        
        self.console.print(Panel(
            options_text,
            title="[bold]Agent Selector[/bold]",
            border_style=self.colors['border']
        ))
        
        # Get user input
        try:
            choice = input("Enter your choice: ").strip().lower()
            
            if choice in self._agent_keys:
                self._show_agent_full_content(self._agent_keys[choice])
            elif choice == 'q':
                self.console.clear()
                if self.live:
                    self.live.update(self._create_layout())
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            pass
    
    def _create_agent_panel(self, agent_id: str) -> Panel:
        """Create a panel for a specific agent."""
        # Get agent content
        agent_content = self.agent_outputs.get(agent_id, [])
        status = self.agent_status.get(agent_id, "waiting")
        activity = self.agent_activity.get(agent_id, "waiting")
        
        # Create content text
        content_text = Text()
        
        # Show more lines since we now support scrolling
        # max_display_lines = min(len(agent_content), self.max_content_lines * 3) if agent_content else 0
        
        # if max_display_lines == 0:
        #     content_text.append("No activity yet...", style=self.colors['text'])
        # else:
        #     # Show recent content with scrolling support
        #     display_content = agent_content[-max_display_lines:] if max_display_lines > 0 else agent_content
            
        #     for line in display_content:
        #         formatted_line = self._format_content_line(line)
        #         content_text.append(formatted_line)
        #         content_text.append("\n")

        max_lines = max(0, self.agent_panel_height - 3)
        if not agent_content:
            content_text.append("No activity yet...", style=self.colors['text'])
        else:
             for line in agent_content[-max_lines:]:
                  formatted_line = self._format_content_line(line)
                  content_text.append(formatted_line)
                  content_text.append("\n")
        
        # Status indicator
        status_emoji = self._get_status_emoji(status, activity)
        status_color = self._get_status_color(status)
        
        # Get backend info if available
        backend_name = self._get_backend_name(agent_id)
        
        # Panel title with click indicator
        title = f"{status_emoji} {agent_id.upper()}"
        if backend_name != "Unknown":
            title += f" ({backend_name})"
        
        # Add interactive indicator if enabled
        if self._interactive_mode and hasattr(self, '_agent_keys'):
            agent_key = next((k for k, v in self._agent_keys.items() if v == agent_id), None)
            if agent_key:
                title += f" [Press {agent_key}]"
        
        # Create panel with scrollable content
        return Panel(
            content_text,
            title=f"[{status_color}]{title}[/{status_color}]",
            border_style=status_color,
            box=ROUNDED,
            height=self.agent_panel_height,
            width=self.fixed_column_width
        )
    
    def _format_content_line(self, line: str) -> Text:
        """Format a content line with syntax highlighting and styling."""
        formatted = Text()
        
        # Skip empty lines
        if not line.strip():
            return formatted
        
        # Enhanced handling for web search content
        if self._is_web_search_content(line):
            return self._format_web_search_line(line)
        
        # Truncate line if too long
        if len(line) > self.max_line_length:
            line = line[:self.max_line_length - 3] + "..."
        
        # Check for special prefixes and format accordingly
        if line.startswith("→"):
            # Tool usage
            formatted.append("→ ", style=self.colors['warning'])
            formatted.append(line[2:], style=self.colors['text'])
        elif line.startswith("🎤"):
            # Presentation content
            formatted.append("🎤 ", style=self.colors['success'])
            formatted.append(line[3:], style=f"bold {self.colors['success']}")
        elif line.startswith("⚡"):
            # Working indicator or status jump indicator
            formatted.append("⚡ ", style=self.colors['warning'])
            if "jumped to latest" in line:
                formatted.append(line[3:], style=f"bold {self.colors['info']}")
            else:
                formatted.append(line[3:], style=f"italic {self.colors['warning']}")
        elif self._is_code_content(line):
            # Code content - apply syntax highlighting
            if self.enable_syntax_highlighting:
                formatted = self._apply_syntax_highlighting(line)
            else:
                formatted.append(line, style=f"bold {self.colors['info']}")
        else:
            # Regular content
            formatted.append(line, style=self.colors['text'])
        
        return formatted
    
    def _is_web_search_content(self, line: str) -> bool:
        """Check if content is from web search and needs special formatting."""
        web_search_indicators = [
            "[Provider Tool: Web Search]",
            "🔍 [Search Query]",
            "✅ [Provider Tool: Web Search]",
            "🔍 [Provider Tool: Web Search]"
        ]
        return any(indicator in line for indicator in web_search_indicators)
    
    def _format_web_search_line(self, line: str) -> Text:
        """Format web search content with better truncation and styling."""
        formatted = Text()
        
        # Handle different types of web search lines
        if "[Provider Tool: Web Search] Starting search" in line:
            formatted.append("🔍 ", style=self.colors['info'])
            formatted.append("Web search starting...", style=self.colors['text'])
        elif "[Provider Tool: Web Search] Searching" in line:
            formatted.append("🔍 ", style=self.colors['warning'])
            formatted.append("Searching...", style=self.colors['text'])
        elif "[Provider Tool: Web Search] Search completed" in line:
            formatted.append("✅ ", style=self.colors['success'])
            formatted.append("Search completed", style=self.colors['text'])
        elif "🔍 [Search Query]" in line:
            # Extract and display search query
            query_part = line.split("🔍 [Search Query]", 1)
            if len(query_part) > 1:
                query = query_part[1].strip().strip("'\"")
                # Limit query display length
                if len(query) > 50:
                    query = query[:47] + "..."
                formatted.append("🔍 Query: ", style=self.colors['info'])
                formatted.append(query, style=f"italic {self.colors['text']}")
            else:
                formatted.append("🔍 Search query", style=self.colors['info'])
        else:
            # For long web search results, truncate more aggressively
            max_web_length = min(self.max_line_length // 2, 60)  # Much shorter for web content
            if len(line) > max_web_length:
                # Try to find a natural break point
                truncated = line[:max_web_length]
                # Look for sentence or phrase endings
                for break_char in ['. ', '! ', '? ', ', ', ': ']:
                    last_break = truncated.rfind(break_char)
                    if last_break > max_web_length // 2:
                        truncated = truncated[:last_break + 1]
                        break
                line = truncated + "..."
            
            formatted.append(line, style=self.colors['text'])
        
        return formatted
    
    def _should_filter_content(self, content: str, content_type: str) -> bool:
        """Determine if content should be filtered out to reduce noise."""
        # Never filter important content types
        if content_type in ["status", "presentation", "error"]:
            return False
        
        # Filter out very long web search results that are mostly noise
        if len(content) > 1000 and self._is_web_search_content(content):
            # Check if it contains mostly URLs and technical details
            url_count = content.count('http')
            technical_indicators = content.count('[') + content.count(']') + content.count('(') + content.count(')')
            
            # If more than 50% seems to be technical metadata, filter it
            if (url_count > 5 or technical_indicators > len(content) * 0.1):
                return True
        
        return False
    
    def _should_filter_line(self, line: str) -> bool:
        """Determine if a specific line should be filtered out."""
        # Filter lines that are pure metadata or formatting
        filter_patterns = [
            r'^\s*\([^)]+\)\s*$',  # Lines with just parenthetical citations
            r'^\s*\[[^\]]+\]\s*$',  # Lines with just bracketed metadata
            r'^\s*https?://\S+\s*$',  # Lines with just URLs
            r'^\s*\.\.\.\s*$',  # Lines with just ellipsis
        ]
        
        for pattern in filter_patterns:
            if re.match(pattern, line):
                return True
        
        return False
    
    def _truncate_web_search_content(self, agent_id: str):
        """Truncate web search content when important status updates occur."""
        if agent_id not in self.agent_outputs or not self.agent_outputs[agent_id]:
            return
        
        # Find web search content and truncate to keep only recent important lines
        content_lines = self.agent_outputs[agent_id]
        web_search_lines = []
        non_web_search_lines = []
        
        # Separate web search content from other content
        for line in content_lines:
            if self._is_web_search_content(line):
                web_search_lines.append(line)
            else:
                non_web_search_lines.append(line)
        
        # If there's a lot of web search content, truncate it
        if len(web_search_lines) > self._max_web_search_lines:
            # Keep only the first line (search start) and last few lines (search end/results)
            truncated_web_search = (
                web_search_lines[:1] +  # First line (search start)
                ["🔍 ... (web search content truncated due to status update) ..."] +
                web_search_lines[-(self._max_web_search_lines-2):]  # Last few lines
            )
            
            # Reconstruct the content with truncated web search
            # Keep recent non-web-search content and add truncated web search
            recent_non_web = non_web_search_lines[-(max(5, self.max_content_lines-len(truncated_web_search))):]
            self.agent_outputs[agent_id] = recent_non_web + truncated_web_search
        
        # Add a status jump indicator only if content was actually truncated
        if len(web_search_lines) > self._max_web_search_lines:
            self.agent_outputs[agent_id].append("⚡ Status updated - jumped to latest")
    
    def _is_code_content(self, content: str) -> bool:
        """Check if content appears to be code."""
        for pattern in self.code_patterns:
            if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
                return True
        return False
    
    def _apply_syntax_highlighting(self, content: str) -> Text:
        """Apply syntax highlighting to content."""
        try:
            # Try to detect language
            language = self._detect_language(content)
            
            if language:
                # Use Rich Syntax for highlighting (simplified for now)
                return Text(content, style=f"bold {self.colors['info']}")
            else:
                return Text(content, style=f"bold {self.colors['info']}")
        except:
            return Text(content, style=f"bold {self.colors['info']}")
    
    def _detect_language(self, content: str) -> Optional[str]:
        """Detect programming language from content."""
        content_lower = content.lower()
        
        if any(keyword in content_lower for keyword in ['def ', 'import ', 'class ', 'python']):
            return 'python'
        elif any(keyword in content_lower for keyword in ['function', 'var ', 'let ', 'const ']):
            return 'javascript'
        elif any(keyword in content_lower for keyword in ['<', '>', 'html', 'div']):
            return 'html'
        elif any(keyword in content_lower for keyword in ['{', '}', 'json']):
            return 'json'
        
        return None
    
    def _get_status_emoji(self, status: str, activity: str) -> str:
        """Get emoji for agent status."""
        if status == "working":
            return "🔄"
        elif status == "completed":
            if "voted" in activity.lower():
                return "🗳️"  # Vote emoji for any voting activity
            elif "failed" in activity.lower():
                return "❌"
            else:
                return "✅"
        elif status == "waiting":
            return "⏳"
        else:
            return "❓"
    
    def _get_status_color(self, status: str) -> str:
        """Get color for agent status."""
        status_colors = {
            "working": self.colors['warning'],
            "completed": self.colors['success'],
            "waiting": self.colors['info'],
            "failed": self.colors['error']
        }
        return status_colors.get(status, self.colors['text'])
    
    def _get_backend_name(self, agent_id: str) -> str:
        """Get backend name for agent."""
        try:
            if hasattr(self, 'orchestrator') and self.orchestrator and hasattr(self.orchestrator, 'agents'):
                agent = self.orchestrator.agents.get(agent_id)
                if agent and hasattr(agent, 'backend') and hasattr(agent.backend, 'get_provider_name'):
                    return agent.backend.get_provider_name()
        except:
            pass
        return "Unknown"
    
    def _create_footer(self) -> Panel:
        """Create the footer panel with status and events."""
        footer_content = Text()
        
        # Agent status summary
        footer_content.append("📊 Agent Status: ", style=self.colors['primary'])
        
        status_counts = {}
        for status in self.agent_status.values():
            status_counts[status] = status_counts.get(status, 0) + 1
        
        status_parts = []
        for status, count in status_counts.items():
            emoji = self._get_status_emoji(status, status)
            status_parts.append(f"{emoji} {status.title()}: {count}")
        
        footer_content.append(" | ".join(status_parts), style=self.colors['text'])
        footer_content.append("\n")
        
        # Recent events
        if self.orchestrator_events:
            footer_content.append("📋 Recent Events:\n", style=self.colors['primary'])
            recent_events = self.orchestrator_events[-3:]  # Show last 3 events
            for event in recent_events:
                footer_content.append(f"  • {event}\n", style=self.colors['text'])
        
        # Log file info
        if self.log_filename:
            footer_content.append(f"📁 Log: {self.log_filename}\n", style=self.colors['info'])
        
        # Interactive mode instructions
        if self._interactive_mode and hasattr(self, '_agent_keys'):
            footer_content.append("🎮 Interactive: Press 1-", style=self.colors['primary'])
            footer_content.append(f"{len(self.agent_ids)} to view agent details, 'q' to return", style=self.colors['text'])
            footer_content.append(f"\n📂 Output files saved in: {self.output_dir}/", style=self.colors['info'])
        
        return Panel(
            footer_content,
            title="[bold]System Status[/bold]",
            border_style=self.colors['border'],
            box=ROUNDED
        )
    
    def update_agent_content(self, agent_id: str, content: str, content_type: str = "thinking"):
        """Update content for a specific agent with rich formatting and file output."""
        
        if agent_id not in self.agent_ids:
            return
        
        with self._lock:
            # Initialize agent outputs if needed
            if agent_id not in self.agent_outputs:
                self.agent_outputs[agent_id] = []
            
            # Write content to agent's txt file
            self._write_to_agent_file(agent_id, content, content_type)
            
            # Check if this is a status-changing content that should trigger web search truncation
            is_status_change = (
                content_type in ["status", "presentation", "tool"] or
                any(keyword in content.lower() for keyword in self._status_change_keywords)
            )
            
            # If status jump is enabled and this is a status change, truncate web search content
            if (self._status_jump_enabled and 
                is_status_change and 
                self._web_search_truncate_on_status_change and
                self.agent_outputs[agent_id]):
                
                self._truncate_web_search_content(agent_id)
            
            # Enhanced filtering for web search content
            if self._should_filter_content(content, content_type):
                return
            
            # If content contains newlines, split and add as separate lines
            if '\n' in content:
                for line in content.splitlines():
                    if line.strip() and not self._should_filter_line(line):
                        self.agent_outputs[agent_id].append(line)
            else:
                # For short content (streaming words), append to last line or create new line
                if (self.agent_outputs[agent_id] and 
                    len(self.agent_outputs[agent_id][-1]) < self.max_line_length - len(content) - 1):
                    # Append to last line if it won't exceed max length
                    self.agent_outputs[agent_id][-1] += content
                else:
                    # Create new line
                    self.agent_outputs[agent_id].append(content.strip())
            
            # Always schedule update for new content with immediate refresh for status-related content
            self._pending_updates.add(agent_id)
            # Force immediate updates for status changes, tool usage, and important content
            force_immediate = content_type in ["tool", "status", "presentation"] or any(
                keyword in content.lower() for keyword in self._status_change_keywords
            )
            self._schedule_async_update(force_update=force_immediate)
    
    def _write_to_agent_file(self, agent_id: str, content: str, content_type: str):
        """Write content to agent's individual txt file."""
        if agent_id not in self.agent_files:
            return
        
        try:
            file_path = self.agent_files[agent_id]
            timestamp = time.strftime("%H:%M:%S")
            
            # Format content with timestamp and type
            formatted_content = f"[{timestamp}] [{content_type.upper()}] {content}\n"
            
            # Append to file
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(formatted_content)
                
        except Exception as e:
            # Handle file write errors gracefully
            pass
    
    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent with rich indicators."""
        if agent_id not in self.agent_ids:
            return
        
        with self._lock:
            old_status = self.agent_status.get(agent_id, "waiting")
            last_tracked_status = self._last_agent_status.get(agent_id, "waiting")
            
            # Check if this is a vote-related status change
            current_activity = self.agent_activity.get(agent_id, "")
            is_vote_status = ("voted" in status.lower() or "voted" in current_activity.lower())
            
            # Force update for vote statuses or actual status changes
            should_update = (old_status != status and last_tracked_status != status) or is_vote_status
            
            if should_update:
                # Truncate web search content when status changes for immediate focus on new status
                if (self._status_jump_enabled and 
                    self._web_search_truncate_on_status_change and
                    old_status != status and
                    agent_id in self.agent_outputs and
                    self.agent_outputs[agent_id]):
                    
                    self._truncate_web_search_content(agent_id)
                
                super().update_agent_status(agent_id, status)
                self._last_agent_status[agent_id] = status
                
                # Mark for priority update - status changes get highest priority
                self._priority_updates.add(agent_id)
                self._pending_updates.add(agent_id)
                self._pending_updates.add('footer')
                self._schedule_priority_update(agent_id)
                self._schedule_async_update(force_update=True)
            elif old_status != status:
                # Update the internal status but don't refresh display if already tracked
                super().update_agent_status(agent_id, status)
    
    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event with timestamp."""
        with self._lock:
            if self.show_timestamps:
                timestamp = time.strftime("%H:%M:%S")
                formatted_event = f"[{timestamp}] {event}"
            else:
                formatted_event = event
            
            # Check for duplicate events
            if (hasattr(self, 'orchestrator_events') and 
                self.orchestrator_events and 
                self.orchestrator_events[-1] == formatted_event):
                return  # Skip duplicate events
            
            super().add_orchestrator_event(formatted_event)
            
            # Only update footer for important events that indicate real status changes
            if any(keyword in event.lower() for keyword in self._important_event_keywords):
                # Mark footer for async update
                self._pending_updates.add('footer')
                self._schedule_async_update(force_update=True)
    
    def show_final_answer(self, answer: str):
        """Display the final coordinated answer prominently."""
        # 强制更新所有agent的最终状态
        with self._lock:
            for agent_id in self.agent_ids:
                self._pending_updates.add(agent_id)
            self._pending_updates.add('footer')
            self._schedule_async_update(force_update=True)
        
        # 等待更新完成 - increased delay to ensure all vote statuses are displayed
        time.sleep(0.5)
        
        self._force_display_final_vote_statuses()
        
        if self.live:
            try:
                self.live.update(self._create_layout())
            except Exception:
                pass

        # Wait longer to ensure all agent vote statuses are fully displayed
        time.sleep(1.0)

        if self.live:
            self.live.stop()

        # Create final answer display
        final_text = Text()
        final_text.append("🎯 FINAL COORDINATED ANSWER", style=f"bold {self.colors['success']}")
        
        final_panel = Panel(
            Align.center(Text(answer, style=self.colors['text'])),
            title="[bold bright_green]🎯 FINAL ANSWER[/bold bright_green]",
            border_style=self.colors['success'],
            box=DOUBLE,
             expand=False
        )
            
        self.console.print("\n")
        self.console.print(final_panel)
        self.console.print("\n")
    
    def _force_display_final_vote_statuses(self):
        """Force display update to show all agents' final vote statuses."""
        with self._lock:
            # Mark all agents for update to ensure final vote status is shown
            for agent_id in self.agent_ids:
                self._pending_updates.add(agent_id)
            self._pending_updates.add('footer')
            
            # Force immediate update with final status display
            self._schedule_async_update(force_update=True)
            
        # Wait longer to ensure all updates are processed and displayed
        import time
        time.sleep(0.3)  # Increased wait to ensure all vote statuses are displayed
    
    def cleanup(self):
        """Clean up display resources."""
        with self._lock:
            if self.live:
                self.live.stop()
                self.live = None
            
            # Stop keyboard handler if active
            if self._key_handler:
                try:
                    self._key_handler.stop()
                except:
                    pass
            
            # Set shutdown flag to prevent new timers
            self._shutdown_flag = True
            
            # Cancel all debounce timers
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()
            
            # Shutdown executors
            if hasattr(self, '_refresh_executor'):
                self._refresh_executor.shutdown(wait=True)
            if hasattr(self, '_status_update_executor'):
                self._status_update_executor.shutdown(wait=True)
            
            # Close agent files gracefully
            try:
                for agent_id, file_path in self.agent_files.items():
                    if file_path.exists():
                        with open(file_path, 'a', encoding='utf-8') as f:
                            f.write(f"\n=== SESSION ENDED at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            except:
                pass
    
    def _schedule_priority_update(self, agent_id: str):
        """Schedule immediate priority update for critical agent status changes."""
        if self._shutdown_flag:
            return
        
        def priority_update():
            try:
                # Update the specific agent panel immediately
                self._update_agent_panel_cache(agent_id)
                # Trigger immediate display update
                self._update_display_safe()
            except Exception:
                pass
        
        self._status_update_executor.submit(priority_update)
    
    def _schedule_async_update(self, force_update: bool = False):
        """Schedule asynchronous update with debouncing to prevent jitter."""
        current_time = time.time()
        
        # Check if we need a full refresh - less frequent for performance
        if (current_time - self._last_full_refresh) > self._full_refresh_interval:
            with self._lock:
                self._pending_updates.add('header')
                self._pending_updates.add('footer')
                self._pending_updates.update(self.agent_ids)
            self._last_full_refresh = current_time
        
        # For force updates (status changes, tool content), bypass debouncing completely
        if force_update:
            self._last_update = current_time
            # Submit multiple update tasks for even faster processing
            self._refresh_executor.submit(self._async_update_components)
            return
        
        # Cancel existing debounce timer if any
        if 'main' in self._debounce_timers:
            self._debounce_timers['main'].cancel()
        
        # Create new debounce timer
        def debounced_update():
            current_time = time.time()
            time_since_last_update = current_time - self._last_update
            
            if time_since_last_update >= self._update_interval:
                self._last_update = current_time
                self._refresh_executor.submit(self._async_update_components)
            
        self._debounce_timers['main'] = threading.Timer(self._debounce_delay, debounced_update)
        self._debounce_timers['main'].start()
    
    def _async_update_components(self):
        """Asynchronously update only the components that have changed."""
        try:
            updates_to_process = None
            
            with self._lock:
                if self._pending_updates:
                    updates_to_process = self._pending_updates.copy()
                    self._pending_updates.clear()
            
            if not updates_to_process:
                return
            
            # Update components in parallel
            futures = []
            
            for update_id in updates_to_process:
                if update_id == 'header':
                    future = self._refresh_executor.submit(self._update_header_cache)
                    futures.append(future)
                elif update_id == 'footer':
                    future = self._refresh_executor.submit(self._update_footer_cache)
                    futures.append(future)
                elif update_id in self.agent_ids:
                    future = self._refresh_executor.submit(self._update_agent_panel_cache, update_id)
                    futures.append(future)
            
            # Wait for all updates to complete
            for future in futures:
                future.result()
            
            # Update display with new layout
            self._update_display_safe()
            
        except Exception as e:
            # Silently handle errors to avoid disrupting display
            pass
    
    def _update_header_cache(self):
        """Update the cached header panel."""
        try:
            self._header_cache = self._create_header()
        except:
            pass
    
    def _update_footer_cache(self):
        """Update the cached footer panel."""
        try:
            self._footer_cache = self._create_footer()
        except:
            pass
    
    def _update_agent_panel_cache(self, agent_id: str):
        """Update the cached panel for a specific agent."""
        try:
            self._agent_panels_cache[agent_id] = self._create_agent_panel(agent_id)
        except:
            pass
    
    def _update_display_safe(self):
        """Safely update the live display with the current layout."""
        with self._layout_update_lock:
            if self.live:
                try:
                    self.live.update(self._create_layout())
                except Exception:
                    # Silently handle update failures
                    pass
    
    def _refresh_display(self):
        """Override parent's refresh method to use async updates."""
        # Only refresh if there are actual pending updates
        # This prevents unnecessary full refreshes
        if self._pending_updates:
            self._schedule_async_update()
    
    def _is_content_important(self, content: str, content_type: str) -> bool:
        """Determine if content is important enough to trigger a display update."""
        # Always important content types
        if content_type in self._important_content_types:
            return True
        
        # Check for status change indicators in content
        if any(keyword in content.lower() for keyword in self._status_change_keywords):
            return True
        
        # Check for error indicators
        if any(keyword in content.lower() for keyword in ["error", "exception", "failed", "timeout"]):
            return True
            
        return False
    
    def set_status_jump_enabled(self, enabled: bool):
        """Enable or disable status jumping functionality.
        
        Args:
            enabled: Whether to enable status jumping
        """
        with self._lock:
            self._status_jump_enabled = enabled
    
    def set_web_search_truncation(self, enabled: bool, max_lines: int = 3):
        """Configure web search content truncation on status changes.
        
        Args:
            enabled: Whether to enable web search truncation
            max_lines: Maximum web search lines to keep when truncating
        """
        with self._lock:
            self._web_search_truncate_on_status_change = enabled
            self._max_web_search_lines = max_lines


# Convenience function to check Rich availability
def is_rich_available() -> bool:
    """Check if Rich library is available."""
    return RICH_AVAILABLE


# Factory function for creating display
def create_rich_display(agent_ids: List[str], **kwargs) -> RichTerminalDisplay:
    """Create a RichTerminalDisplay instance.
    
    Args:
        agent_ids: List of agent IDs to display
        **kwargs: Configuration options for RichTerminalDisplay
        
    Returns:
        RichTerminalDisplay instance
        
    Raises:
        ImportError: If Rich library is not available
    """
    return RichTerminalDisplay(agent_ids, **kwargs)