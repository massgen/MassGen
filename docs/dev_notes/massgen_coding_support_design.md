# MassGen Coding Support - Design Document

## Overview

This document outlines the comprehensive design for MassGen's coding support capabilities, transforming it into a powerful multi-agent coding assistant. The design focuses on four core areas:

1. **System Prompt Improvements** - Better prompts for coding iterations and quality
2. **Multi-turn Conversation Support** - Persistent context across coding sessions
3. **Better Workspace Logging** - Visibility into agent workspace differences
4. **Consolidated Directory Structure** - Clean `.massgen/` organization
5. **Docker-Based Overlay Workspaces** - Copy-on-write filesystem isolation (future)
6. **Drop-in CLI Usage** - Auto-detection and simplified workflows (future)
7. **Large-scale Task Decomposition** - Breaking complex tasks into subtasks (future)

## Current State & Problems

### Existing Issues
- **Limited New Answers**: Coding agents tend to give fewer iterations compared to other tasks ([#224](https://github.com/Leezekun/MassGen/issues/224))
- **Context Path Friction**: Users must manually edit YAML configs for each project
- **No Multi-turn Support**: No persistent context across conversation sessions ([#231](https://github.com/Leezekun/MassGen/issues/231))
- **Manual Context Reference**: Agents don't automatically use context paths unless explicitly mentioned in prompts
- **Workspace Contamination**: Agents see previous workspaces entirely, reducing independence
- **Poor Visibility**: Hard to see if agent workspaces differ significantly across iterations

### What's Already Done
- ✅ File copy MCP tools (`copy_files_batch`) for workspace copying
- ✅ Pre-tool-use hooks for permission validation
- ✅ Basic workspace and snapshot infrastructure

## Phase 1: System Prompt Improvements for Coding

### Addressing Issue #224: More New Answers

#### Problem Analysis
Coding agents provide fewer iterations because:
1. System prompts may be overwhelming or unclear about iteration expectations
2. Agents perceive code changes as more "final" than other outputs
3. Previous workspace visibility makes agents think less independent exploration is needed

#### Enhanced System Prompts

```python
CODING_AGENT_SYSTEM_MESSAGE = """
You are an expert software engineer collaborating with other agents on coding tasks.

IMPORTANT COLLABORATION GUIDELINES:
- You will likely see multiple drafts/approaches from other agents - this is expected and valuable
- Feel free to propose completely different approaches, not just incremental changes
- If you see flaws or improvement opportunities in previous work, create a new answer
- Don't assume previous solutions are final - iteration and diverse perspectives improve code quality
- Each new answer you provide should be a complete, working solution (not a diff or patch)

AVAILABLE TOOLS:
- copy_files_batch: Copy files from other agents' work or context paths efficiently
- Standard filesystem operations: read, write, edit files
- Bash execution: Run tests, builds, linters to validate your changes

WORKSPACE STRUCTURE:
- /workspace: Your isolated coding environment (clean slate each execution)
- /temp_workspace/agent*: Other agents' previous work (read-only, for reference)
- Context paths: The actual project you're modifying (specified in configuration)

ITERATION ENCOURAGEMENT:
- If you can improve code quality, performance, or architecture - do it
- Consider alternative implementations - different libraries, patterns, approaches
- Test your changes when possible - run existing tests or create new ones
- Each iteration makes the codebase better - don't settle for "good enough"
- Look at other agents' approaches for inspiration, but think independently

Remember: Multiple perspectives and iterations lead to better software. Your job is to provide the best solution YOU can create, not to defer to others.
"""
```

### Enhanced Voting Prompts
```python
CODING_VOTING_PROMPT = """
Evaluate these coding solutions based on:

TECHNICAL CRITERIA:
- Code quality and maintainability
- Performance and efficiency
- Security considerations
- Test coverage and reliability
- Architecture and design patterns

PRACTICAL CRITERIA:
- Completeness of implementation
- Handling of edge cases
- Documentation clarity
- Integration with existing codebase
- Ease of future modification

Vote for the solution that best balances technical excellence with practical requirements.
Perfect code that doesn't fully solve the problem is less valuable than good code that addresses all requirements.
"""
```

## Phase 2: Multi-turn Conversation Support

### Session Persistence Architecture

```
User's Project Directory:
├── .massgen/                          # All MassGen state (gitignored)
│   ├── sessions/
│   │   └── session_abc123/
│   │       ├── conversation.json      # Full conversation history
│   │       ├── turn_1_final/          # Final output from turn 1
│   │       ├── turn_2_final/          # Final output from turn 2
│   │       └── ...
│   ├── workspaces/                    # Agent workspaces (active)
│   ├── snapshots/                     # Workspace snapshots
│   └── temp_workspaces/               # Previous agent work for context
├── src/                               # Actual project files
├── package.json
└── ...
```

### Implementation Strategy

#### Session Management
```python
class CodingSessionManager:
    def __init__(self, session_id=None, project_root=None):
        self.project_root = Path(project_root or Path.cwd())
        self.massgen_dir = self.project_root / ".massgen"
        self.session_id = session_id or self._generate_session_id()
        self.session_dir = self.massgen_dir / "sessions" / self.session_id

        # Create session directory
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def save_turn(self, turn_number, question, final_answer, final_workspace):
        """Save a conversation turn with final output"""
        # Save turn metadata
        turn_data = {
            "turn": turn_number,
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "answer": self._normalize_paths(final_answer, turn_number)
        }

        # Append to conversation history
        history = self.load_conversation_history()
        history.append(turn_data)
        with open(self.session_dir / "conversation.json", "w") as f:
            json.dump(history, f, indent=2)

        # Save final workspace output
        turn_output_dir = self.session_dir / f"turn_{turn_number}_final"
        if turn_output_dir.exists():
            shutil.rmtree(turn_output_dir)
        shutil.copytree(final_workspace, turn_output_dir)

    def prepare_context_for_turn(self, turn_number):
        """Add previous turn outputs as read-only context paths"""
        context_paths = []

        for i in range(1, turn_number):
            turn_output = self.session_dir / f"turn_{i}_final"
            if turn_output.exists():
                context_paths.append({
                    "path": str(turn_output),
                    "permission": "read"
                })

        return context_paths

    def _normalize_paths(self, answer_text, turn_number):
        """
        Normalize workspace paths in answers to session-relative references
        so they remain valid and understandable across turns.

        Example: /tmp/massgen_workspace_agent1/auth.py
                 -> .massgen/sessions/abc123/turn_1_final/auth.py
        """
        # Replace temporary workspace paths with session paths
        turn_output = f".massgen/sessions/{self.session_id}/turn_{turn_number}_final"

        # Pattern matching for workspace paths
        normalized = re.sub(
            r'/tmp/massgen[^/]+/workspace[^/]*/([^/]+/)*',
            f'{turn_output}/',
            answer_text
        )

        return normalized
```

#### Interactive Multi-turn CLI
```bash
# Start new coding session (auto-creates session ID)
$ cd ~/my-project
$ massgen "Implement user authentication"
[Session abc123] Agents working on authentication...
[Session abc123] ✓ Complete! Modified: src/auth.py, src/models.py

# Continue session (auto-resumes most recent session in this directory)
$ massgen "Add password reset functionality"
[Session abc123] Loading context from turn 1...
[Session abc123] ✓ Complete! Modified: src/auth.py, src/email_utils.py

# Explicit session continuation
$ massgen --session abc123 "Add OAuth support"

# List session history
$ massgen --session abc123 --history
Session abc123 (started 2025-01-15 10:30:00):
  Turn 1: "Implement user authentication"
    → Modified: src/auth.py, src/models.py
  Turn 2: "Add password reset functionality"
    → Modified: src/auth.py, src/email_utils.py

# Start fresh session in same project
$ massgen --new-session "Refactor database layer"
[Session def456] Starting new session...
```

## Phase 3: Better Workspace Logging & Visibility

### Problem
Currently difficult to see:
- If an agent's first answer workspace differs from their second answer
- If different agents produced similar or different solutions
- What actually changed between iterations
- Whether agents are truly being independent or just copying each other

### Workspace Diff Logging

#### Automatic Diff Generation
```python
class WorkspaceDiffLogger:
    """Log workspace differences for debugging and analysis"""

    def log_workspace_diff(self, agent_id, iteration, workspace_path, previous_workspace=None):
        """Compare workspace with previous iteration and log differences"""

        if previous_workspace is None:
            logger.info(f"[{agent_id}] Iteration {iteration}: Initial workspace created")
            self._log_workspace_summary(agent_id, iteration, workspace_path)
            return

        # Compute diff
        diff_stats = self._compute_workspace_diff(workspace_path, previous_workspace)

        # Log summary
        logger.info(f"[{agent_id}] Iteration {iteration} vs {iteration-1}:")
        logger.info(f"  Files added: {len(diff_stats['added'])}")
        logger.info(f"  Files modified: {len(diff_stats['modified'])}")
        logger.info(f"  Files deleted: {len(diff_stats['deleted'])}")
        logger.info(f"  Files unchanged: {len(diff_stats['unchanged'])}")

        # Log detailed changes if significant
        if diff_stats['similarity_score'] < 0.9:  # Less than 90% similar
            logger.info(f"  Significant changes detected (similarity: {diff_stats['similarity_score']:.2%})")
            self._log_detailed_diff(agent_id, iteration, diff_stats)
        else:
            logger.warning(f"  Minimal changes (similarity: {diff_stats['similarity_score']:.2%}) - agent may not be exploring independently")

    def _compute_workspace_diff(self, workspace_a, workspace_b):
        """Compute detailed diff between two workspaces"""
        files_a = self._get_file_hashes(workspace_a)
        files_b = self._get_file_hashes(workspace_b)

        all_files = set(files_a.keys()) | set(files_b.keys())

        added = [f for f in files_a if f not in files_b]
        deleted = [f for f in files_b if f not in files_a]
        modified = [f for f in all_files if f in files_a and f in files_b and files_a[f] != files_b[f]]
        unchanged = [f for f in all_files if f in files_a and f in files_b and files_a[f] == files_b[f]]

        # Compute similarity score
        total_files = len(all_files)
        unchanged_count = len(unchanged)
        similarity_score = unchanged_count / total_files if total_files > 0 else 1.0

        return {
            'added': added,
            'deleted': deleted,
            'modified': modified,
            'unchanged': unchanged,
            'similarity_score': similarity_score
        }

    def _get_file_hashes(self, workspace_path):
        """Get SHA256 hash of each file in workspace"""
        import hashlib

        file_hashes = {}
        for root, dirs, files in os.walk(workspace_path):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(workspace_path)

                # Hash file content
                hasher = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())

                file_hashes[str(relative_path)] = hasher.hexdigest()

        return file_hashes

    def compare_agent_workspaces(self, agent_workspaces):
        """Compare final workspaces from all agents"""
        logger.info("=== Cross-Agent Workspace Comparison ===")

        agents = list(agent_workspaces.keys())
        for i, agent_a in enumerate(agents):
            for agent_b in agents[i+1:]:
                diff = self._compute_workspace_diff(
                    agent_workspaces[agent_a],
                    agent_workspaces[agent_b]
                )

                logger.info(f"{agent_a} vs {agent_b}: {diff['similarity_score']:.2%} similar")

                if diff['similarity_score'] > 0.95:
                    logger.warning(f"  ⚠️  Agents produced nearly identical results - may indicate lack of diversity")
                elif diff['similarity_score'] < 0.3:
                    logger.info(f"  ✓ Agents explored significantly different approaches")
```

#### Integration with Orchestrator
```python
# In orchestrator.py, when saving snapshots:
async def _save_agent_snapshot(self, agent_id, ...):
    # ... existing snapshot code ...

    # Compare with previous iteration
    previous_snapshot = self._get_previous_snapshot(agent_id)
    if previous_snapshot:
        self.diff_logger.log_workspace_diff(
            agent_id,
            current_iteration,
            current_workspace,
            previous_snapshot
        )

    # At end of coordination, compare all agent workspaces
    if all_agents_finished:
        final_workspaces = {aid: self._get_final_workspace(aid) for aid in self.agents}
        self.diff_logger.compare_agent_workspaces(final_workspaces)
```

#### Example Log Output
```
[agent1] Iteration 1: Initial workspace created
  Files: 3 (auth.py, models.py, utils.py)
  Total size: 4.2KB

[agent1] Iteration 2 vs 1:
  Files added: 1 (tests/test_auth.py)
  Files modified: 2 (auth.py, models.py)
  Files deleted: 0
  Files unchanged: 1 (utils.py)
  Significant changes detected (similarity: 65.43%)

[agent2] Iteration 1: Initial workspace created
  Files: 4 (auth.py, models.py, config.py, middleware.py)

=== Cross-Agent Workspace Comparison ===
agent1 vs agent2: 45.12% similar
  ✓ Agents explored significantly different approaches
agent1 vs agent3: 87.32% similar
agent2 vs agent3: 41.87% similar
  ✓ Agents explored significantly different approaches
```

## Phase 4: Consolidated .massgen Directory Structure

### Rationale

Currently, MassGen creates workspace-related directories in multiple locations:
- Temporary workspaces in various temp directories
- Snapshots wherever orchestrator specifies
- Logs in separate logging directory
- No clear project-level organization

#### Why Consolidate into `.massgen/`?

1. **Cleaner Project Root**: User's project directory stays clean, all MassGen state in one place
2. **Easy .gitignore**: Single line: `.massgen/` ignores all MassGen state
3. **Discoverability**: Developers can easily find and inspect MassGen's working state
4. **Per-Project Isolation**: Each project gets its own `.massgen/` directory, no cross-contamination
5. **Session Persistence**: Natural place for multi-turn conversation state
6. **Debugging**: All relevant files in one place when investigating issues

### Proposed Structure

```
project_root/
├── .massgen/                          # All MassGen state (add to .gitignore)
│   ├── config.yaml                    # Project-specific MassGen config (optional)
│   ├── sessions/                      # Multi-turn conversation sessions
│   │   ├── session_abc123/
│   │   │   ├── conversation.json
│   │   │   ├── turn_1_final/
│   │   │   └── turn_2_final/
│   │   └── session_def456/
│   ├── workspaces/                    # Active agent workspaces
│   │   ├── agent_1/
│   │   ├── agent_2/
│   │   └── agent_3/
│   ├── snapshots/                     # Workspace snapshots for context sharing
│   │   ├── agent_1/
│   │   ├── agent_2/
│   │   └── agent_3/
│   ├── temp_workspaces/               # Previous agent work for reference
│   │   ├── agent_1/
│   │   │   ├── agent1/                # Self
│   │   │   ├── agent2/                # Other agent's work
│   │   │   └── agent3/
│   │   └── agent_2/
│   ├── logs/                          # Detailed orchestration logs
│   │   └── session_20250115_103045/
│   │       ├── agent_1/
│   │       │   ├── 20250115_103045_123456/
│   │       │   │   ├── workspace/
│   │       │   │   ├── answer.txt
│   │       │   │   └── vote.json
│   │       │   └── ...
│   │       ├── agent_2/
│   │       ├── final/
│   │       └── orchestration.log
│   └── subtasks/                      # Outputs from task decomposition
│       ├── subtask_0_output/
│       ├── subtask_1_output/
│       └── ...
├── src/                               # User's actual project
├── package.json
└── ...
```

### Implementation Changes

```python
class MassGenProjectManager:
    """Manages .massgen directory structure for a project"""

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.massgen_dir = self.project_root / ".massgen"

        # Initialize directory structure
        self._init_directory_structure()

    def _init_directory_structure(self):
        """Create .massgen directory structure if it doesn't exist"""
        dirs_to_create = [
            self.massgen_dir / "sessions",
            self.massgen_dir / "workspaces",
            self.massgen_dir / "snapshots",
            self.massgen_dir / "temp_workspaces",
            self.massgen_dir / "logs",
            self.massgen_dir / "subtasks"
        ]

        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Create .gitignore if project has git
        if (self.project_root / ".git").exists():
            self._ensure_gitignore()

    def _ensure_gitignore(self):
        """Add .massgen to .gitignore"""
        gitignore_path = self.project_root / ".gitignore"

        if gitignore_path.exists():
            content = gitignore_path.read_text()
            if ".massgen" not in content:
                with open(gitignore_path, "a") as f:
                    f.write("\n# MassGen workspace state\n.massgen/\n")
        else:
            gitignore_path.write_text("# MassGen workspace state\n.massgen/\n")

    def get_workspace_dir(self, agent_id):
        return self.massgen_dir / "workspaces" / agent_id

    def get_snapshot_dir(self, agent_id):
        return self.massgen_dir / "snapshots" / agent_id

    def get_temp_workspace_dir(self, agent_id):
        return self.massgen_dir / "temp_workspaces" / agent_id

    def get_session_dir(self, session_id):
        return self.massgen_dir / "sessions" / session_id
```

### Migration Path
- New projects automatically use `.massgen/` structure
- Existing behavior remains default for backward compatibility
- Config flag to enable: `use_massgen_directory: true`
- Future: Make `.massgen/` the default in next major version

## Phase 5: Docker-Based Overlay Workspaces (Future)

### Overview
After the above improvements are complete and stable, implement Docker-based copy-on-write overlay filesystems for true workspace isolation.

### Architecture
```
Each Agent Container:
├── Base Layer: Context path (read-only)
├── Snapshot Layers: Previous agent work (read-only)
├── Upper Layer: Agent's changes (writable, CoW)
└── Merged View: /workspace (what agent sees)
```

### Key Benefits
- True copy-on-write behavior via Docker's overlay2 driver
- Complete isolation between agent workspaces
- Efficient storage (only deltas stored)
- Automatic cleanup via container lifecycle

### Implementation Notes
- MCP server runs inside each container
- Agent connects to containerized MCP via HTTP
- All filesystem operations automatically isolated
- Falls back to current approach if Docker unavailable

See filesystem_design.md for detailed Docker implementation plan.

## Phase 6: Drop-in CLI Usage (Future)

### Simplified Workflows

After Docker workspaces are stable, implement seamless CLI usage that auto-detects project context.

#### Current Workflow (Friction)
```bash
# User must edit YAML every time
cd ~/my-project
vim massgen-config.yaml  # Add context path manually
massgen --config massgen-config.yaml "Add user auth"
```

#### Proposed Workflow (Seamless)
```bash
# Auto-detect context path from current directory
cd ~/my-project
massgen "Add user authentication"

# Or explicit path
massgen --context ~/my-project "Add user auth"

# Or with custom config + override context path
massgen --config my-config.yaml --context ~/my-project "Add auth"
```

### Implementation
```python
def resolve_context_path(args):
    """Determine context path from args or auto-detect"""
    if args.context:
        return Path(args.context).resolve()
    elif args.auto_context or not args.config:
        cwd = Path.cwd()
        if is_project_directory(cwd):
            return cwd
    return None

def is_project_directory(path):
    """Check if directory looks like a code project"""
    indicators = [
        '.git', 'package.json', 'pyproject.toml', 'requirements.txt',
        'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle', 'CMakeLists.txt'
    ]
    return any((path / indicator).exists() for indicator in indicators)

def create_coding_config(context_path, base_config=None):
    """Generate config with auto-detected context path"""
    config = base_config or get_default_coding_config()
    if context_path:
        config.setdefault('orchestrator', {})
        config['orchestrator']['context_paths'] = [
            {"path": str(context_path), "permission": "write"}
        ]
    return config
```

## Phase 7: Large-scale Task Decomposition (Future)

### Hierarchical Task Planning

For very large coding tasks, break them into subtasks first, then execute incrementally with separate orchestration rounds.

#### Two-Phase Orchestration

**Phase 1: Task Planning**
```python
async def plan_coding_task(user_request):
    """Have agents collaboratively create a task breakdown"""
    planning_prompt = f"""
    Break down this coding task into 3-7 specific, actionable subtasks:

    Task: {user_request}

    Format each subtask as:
    1. [Task Name] - [Brief description] - [Complexity: Simple/Medium/Complex]

    Each subtask should be completable in one focused session.
    Dependencies between subtasks should be minimal and clear.
    """

    agent_plans = await orchestrator.coordinate_planning(planning_prompt)
    consensus_plan = await orchestrator.reach_consensus_on_plan(agent_plans)
    return consensus_plan.subtasks
```

**Phase 2: Task Execution**
```python
async def execute_coding_plan(subtasks, execution_mode="auto"):
    """Execute the task plan using chosen orchestration strategy"""
    if execution_mode == "auto":
        execution_mode = choose_execution_mode(subtasks)

    if execution_mode == "single_orchestrator":
        # Traditional: One orchestrator call handles all subtasks
        full_prompt = build_execution_prompt_with_subtasks(subtasks)
        return await orchestrator.coordinate(full_prompt)

    elif execution_mode == "multi_orchestrator":
        # New: Separate orchestrator call per subtask
        results = []
        for i, subtask in enumerate(subtasks):
            context_paths = prepare_subtask_context(i, results)
            result = await orchestrator.coordinate_subtask(
                subtask, context_paths=context_paths, subtask_index=i
            )
            save_subtask_output(i, result)
            results.append(result)
        return combine_subtask_results(results)
```

### CLI Integration
```bash
$ massgen --decompose "Migrate from REST API to GraphQL"
Planning phase:
  Agent 1 suggests: 5 subtasks
  Consensus: 5 subtasks

Executing subtasks:
  [1/5] Setup GraphQL schema and resolvers... ✓
  [2/5] Migrate user endpoints... ✓
  [3/5] Migrate product endpoints... ✓
  [4/5] Update frontend API client... ✓
  [5/5] Remove old REST endpoints... ✓
```

## Implementation Roadmap

### Sprint 1: System Prompts & Logging (Current Priority)
- Updated system prompts for coding agents (#224)
- Enhanced voting prompts
- Workspace diff logging implementation
- Cross-agent workspace comparison

### Sprint 2: Multi-turn Conversations
- Session management infrastructure (#231)
- Conversation history persistence
- Turn-based context preparation
- Path normalization for multi-turn
- Interactive session CLI commands

### Sprint 3: Consolidated Directory Structure
- `.massgen/` directory organization
- Auto-gitignore creation
- MassGenProjectManager implementation
- Migration path for existing users

### Sprint 4: Docker Workspaces (Future)
- Docker workspace manager implementation
- MCP server containerization
- Copy-on-write overlay setup
- Integration with existing orchestrator
- Fallback mode for non-Docker environments

### Sprint 5: Drop-in CLI (Future)
- Enhanced CLI with `--context` auto-detection
- Dynamic config generation
- Project directory detection heuristics
- Seamless workflow improvements

### Sprint 6: Task Decomposition (Future)
- Planning phase orchestration mode
- Consensus-based task breakdown
- Multi-orchestrator execution strategy
- Subtask context propagation
- Auto-execution mode selection

## Security & Safety

### Tool Execution Safety
```python
DANGEROUS_COMMANDS = [
    'rm -rf /', 'format', 'fdisk', 'dd if=',
    'chmod 777', 'curl | sh', 'wget | sh',
    'sudo', ':(){ :|:& };:'  # fork bomb
]

def validate_bash_command(command):
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous in command.lower():
            return False, f"Dangerous command blocked: {dangerous}"
    return True, None
```

### Permission Validation
- Pre-tool-use hooks enforce read/write permissions
- Context paths marked read-only during coordination
- Only final agent gets write access to original context

---

## Future Extensions

**Advanced collaboration patterns**: Specialized agents (architect, implementer, tester, reviewer) with distinct roles and orchestration strategies. **Incremental updates**: Real-time file watching and incremental re-execution when project files change externally. **IDE integration**: VS Code extension for inline MassGen suggestions and workspace visualization. **Performance profiling**: Automatic detection of slow agents or inefficient tool usage patterns. **Checkpointing**: Save/restore orchestration state mid-execution for very long-running tasks.