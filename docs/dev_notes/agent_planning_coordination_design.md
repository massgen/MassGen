# Agent Planning and Coordination System Design

**Author:** MassGen Team
**Date:** 2025-10-26
**Status:** Design Phase

## Overview

This design doc covers the implementation of a multi-agent planning and coordination system that allows agents to:
1. Maintain their own task lists (create, edit, mark as done)
2. Broadcast messages to interrupt all other agents
3. Delegate tasks to sub-orchestrators
4. Work in parallel while waiting for delegated tasks

## Problem Statement

Currently, MassGen agents operate independently without:
- **Internal task planning**: Agents cannot break down complex tasks into manageable steps
- **Inter-agent communication**: No mechanism for agents to coordinate or share information
- **Task delegation**: Agents cannot spawn sub-orchestrators for subtasks
- **Parallel work coordination**: No way to work on other tasks while waiting for delegated work

This limits agents' ability to:
- Handle complex multi-step tasks systematically
- Coordinate on shared resources or dependencies
- Scale work by delegating to specialized sub-agents
- Efficiently utilize time when blocked on external operations

## Goals

### Primary Goals
1. Enable each agent to maintain a personal task list with planning tools
2. Implement broadcast system for agent-to-agent interrupts
3. Support task delegation to sub-orchestrators
4. Allow parallel work while waiting for delegated tasks
5. Maintain backward compatibility with existing orchestrator architecture

### Non-Goals
- Direct peer-to-peer messaging (broadcasts only)
- Complex synchronization primitives (locks, semaphores)
- Multi-level delegation hierarchies (only one level deep initially)

## Architecture

### High-Level Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Orchestrator (Main)                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         Broadcast Channel (Event Bus)                      │ │
│  │  - Receives broadcasts from any agent                      │ │
│  │  - Interrupts all agents                                   │ │
│  │  - Collects responses before resuming                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Agent A    │  │   Agent B    │  │   Agent C    │          │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤          │
│  │ Task List:   │  │ Task List:   │  │ Task List:   │          │
│  │ □ Task 1     │  │ ☑ Task X     │  │ □ Task α     │          │
│  │ ☑ Task 2     │  │ □ Task Y     │  │ □ Task β     │          │
│  │ ⋯ Task 3     │  │ ⋯ Task Z     │  │              │          │
│  │              │  │              │  │              │          │
│  │ Tools:       │  │ Tools:       │  │ Tools:       │          │
│  │ - plan_task  │  │ - plan_task  │  │ - plan_task  │          │
│  │ - edit_plan  │  │ - edit_plan  │  │ - edit_plan  │          │
│  │ - mark_done  │  │ - mark_done  │  │ - mark_done  │          │
│  │ - broadcast  │  │ - broadcast  │  │ - broadcast  │          │
│  │ - delegate   │  │ - delegate   │  │ - delegate   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘          │
│         │                 │                                      │
│         │ delegate_task() │                                      │
│         ↓                 ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Sub-Orchestrator Pool                             │  │
│  │  - Spawned on-demand for delegated tasks                 │  │
│  │  - Runs in parallel with parent agent                     │  │
│  │  - Returns results when complete                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Design

### 1. Agent Task Planning Tools

**Location:** `massgen/tools/planning_tools.py` (new file)

**MCP Server:** `massgen/tools/_planning_mcp_server.py` (new file)

Each agent gets access to planning tools via MCP:

```python
@dataclass
class Task:
    """Represents a single task in an agent's plan."""
    id: str  # UUID
    description: str
    status: Literal["pending", "in_progress", "completed", "blocked"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)  # List of task IDs
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    """Agent's complete task plan."""
    agent_id: str
    tasks: List[Task]
    created_at: datetime
    updated_at: datetime


# MCP Tools exposed to agents
@mcp.tool()
def create_task_plan(tasks: List[Union[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Create a new task plan with a list of tasks.

    Tasks can be simple strings or structured dictionaries with dependencies.

    Args:
        tasks: List of task descriptions or task objects

    Returns:
        Dictionary with plan_id and created task list

    Examples:
        # Simple tasks (no dependencies)
        create_task_plan([
            "Research existing authentication methods",
            "Design new OAuth flow",
            "Implement backend endpoints"
        ])

        # Tasks with dependencies (by index)
        create_task_plan([
            "Research OAuth providers",
            {
                "description": "Implement OAuth endpoints",
                "depends_on": [0]  # Depends on task at index 0
            },
            {
                "description": "Write integration tests",
                "depends_on": [1]  # Depends on task at index 1
            }
        ])

        # Tasks with named IDs and dependencies
        create_task_plan([
            {
                "id": "research_oauth",
                "description": "Research OAuth providers"
            },
            {
                "id": "research_db",
                "description": "Research database schema best practices"
            },
            {
                "id": "implement_oauth",
                "description": "Implement OAuth endpoints",
                "depends_on": ["research_oauth"]
            },
            {
                "id": "implement_db",
                "description": "Implement database models",
                "depends_on": ["research_db"]
            },
            {
                "id": "integration_tests",
                "description": "Run integration tests",
                "depends_on": ["implement_oauth", "implement_db"]
            }
        ])

        # Mixed format
        create_task_plan([
            "Research authentication options",  # Task 0
            {
                "description": "Implement chosen auth method",
                "depends_on": [0]  # Reference by index
            }
        ])

    Dependency Rules:
        - Can reference by index (0-based) or by custom task ID
        - Dependencies must reference earlier tasks in the list
        - Circular dependencies are rejected
        - Tasks with no dependencies can start immediately
        - Tasks with dependencies wait until all deps are completed
    """
    pass


@mcp.tool()
def add_task(
    description: str,
    after_task_id: Optional[str] = None,
    depends_on: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Add a new task to the plan.

    Args:
        description: Task description
        after_task_id: Optional ID to insert after (otherwise appends)
        depends_on: Optional list of task IDs this task depends on

    Returns:
        Dictionary with new task details

    Example:
        # Add task with dependencies
        add_task(
            "Deploy to production",
            depends_on=["run_tests", "update_docs"]
        )
    """
    pass


@mcp.tool()
def update_task_status(
    task_id: str,
    status: Literal["pending", "in_progress", "completed", "blocked"]
) -> Dict[str, Any]:
    """
    Update the status of a task.

    Args:
        task_id: ID of task to update
        status: New status

    Returns:
        Dictionary with updated task details
    """
    pass


@mcp.tool()
def edit_task(task_id: str, description: Optional[str] = None) -> Dict[str, Any]:
    """
    Edit a task's description.

    Args:
        task_id: ID of task to edit
        description: New description (if provided)

    Returns:
        Dictionary with updated task details
    """
    pass


@mcp.tool()
def get_task_plan() -> Dict[str, Any]:
    """
    Get the current task plan for this agent.

    Returns:
        Dictionary with complete task plan including all tasks and their statuses
    """
    pass


@mcp.tool()
def delete_task(task_id: str) -> Dict[str, Any]:
    """
    Remove a task from the plan.

    Args:
        task_id: ID of task to delete

    Returns:
        Success confirmation
    """
    pass


@mcp.tool()
def get_ready_tasks() -> List[Dict[str, Any]]:
    """
    Get all tasks that are ready to start (dependencies satisfied).

    Returns:
        List of tasks with status='pending' and all dependencies completed

    Use cases:
        - Identify which tasks can be worked on now
        - Find tasks that can be delegated in parallel
        - Avoid blocking on incomplete dependencies

    Example:
        ready = get_ready_tasks()
        # ready = [
        #   {"id": "task_a", "description": "Implement OAuth", ...},
        #   {"id": "task_b", "description": "Setup DB schema", ...}
        # ]
        # Both have no dependencies or all deps completed
    """
    pass


@mcp.tool()
def get_blocked_tasks() -> List[Dict[str, Any]]:
    """
    Get all tasks that are blocked by incomplete dependencies.

    Returns:
        List of tasks with status='pending' but dependencies not completed

    Use cases:
        - Understand what's blocking progress
        - Prioritize completing blocking tasks
        - Visualize dependency chains

    Example:
        blocked = get_blocked_tasks()
        # blocked = [
        #   {
        #     "id": "task_c",
        #     "description": "Integration tests",
        #     "waiting_on": ["task_a", "task_b"]
        #   }
        # ]
    """
    pass
```

**Implementation Details:**

- **Storage:** Task plans stored in-memory in orchestrator's state manager
- **Persistence:** Serialized to JSON in orchestrator logs for resumability
- **Agent-specific:** Each agent has its own isolated task plan
- **Thread-safe:** All operations use locks for concurrent access

**Dependency Management:**

Dependencies are specified at task creation time and automatically enforced by the orchestrator:

```python
class TaskPlan:
    """Manages an agent's task plan with dependency tracking."""

    def can_start_task(self, task_id: str) -> bool:
        """
        Check if a task can be started (all dependencies completed).

        Args:
            task_id: Task to check

        Returns:
            True if all dependencies are completed, False otherwise
        """
        task = self.get_task(task_id)

        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if dep_task.status != "completed":
                return False

        return True

    def get_ready_tasks(self) -> List[Task]:
        """Get all tasks ready to start."""
        return [
            task for task in self.tasks
            if task.status == "pending" and self.can_start_task(task.id)
        ]

    def get_blocked_tasks(self) -> List[Task]:
        """Get all tasks blocked by dependencies."""
        return [
            task for task in self.tasks
            if task.status == "pending" and not self.can_start_task(task.id)
        ]

    def validate_dependencies(self, task_list: List[Dict[str, Any]]) -> None:
        """
        Validate dependencies when creating a task plan.

        Checks:
            - Dependencies reference valid tasks (earlier in list or by valid ID)
            - No circular dependencies
            - No self-references

        Raises:
            ValueError: If validation fails
        """
        # Build dependency graph and check for cycles
        pass
```

**Automatic Status Updates:**

When a task is marked complete, the orchestrator notifies the agent about newly unblocked tasks:

```python
def update_task_status(task_id: str, status: str) -> Dict[str, Any]:
    """Update task status and detect newly unblocked tasks."""
    task = get_task(task_id)
    task.status = status

    if status == "completed":
        task.completed_at = datetime.now()

        # Find newly ready tasks
        newly_ready = []
        for other_task in self.tasks:
            if (other_task.status == "pending" and
                task_id in other_task.dependencies and
                self.can_start_task(other_task.id)):
                newly_ready.append(other_task)

        return {
            "task": task.to_dict(),
            "newly_ready_tasks": [t.to_dict() for t in newly_ready]
        }

    return {"task": task.to_dict()}
```

**Parallel Execution with Dependencies:**

Agents can use dependencies to identify tasks for parallel delegation:

```python
# Example workflow
plan = create_task_plan([
    {
        "id": "research_oauth",
        "description": "Research OAuth providers"
    },
    {
        "id": "research_db",
        "description": "Research database schema"
    },
    {
        "id": "impl_oauth",
        "description": "Implement OAuth",
        "depends_on": ["research_oauth"]
    },
    {
        "id": "impl_db",
        "description": "Implement DB models",
        "depends_on": ["research_db"]
    }
])

# Get ready tasks (both research tasks have no dependencies)
ready = get_ready_tasks()
# ready = [research_oauth, research_db]

# Delegate both in parallel
for task in ready:
    delegate_task(
        task['description'],
        task_id=task['id'],
        wait=False  # Parallel execution
    )

# When both complete, impl_oauth and impl_db become ready
# Can delegate those in parallel too
```

### 2. Broadcast System

**Location:** `massgen/orchestrator/_broadcast_channel.py` (new file)

**Key Components:**

```python
@dataclass
class BroadcastMessage:
    """Message broadcast to all agents."""
    id: str  # UUID
    sender_agent_id: str
    content: str
    timestamp: datetime
    requires_response: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BroadcastResponse:
    """Response from an agent to a broadcast."""
    broadcast_id: str
    agent_id: str
    content: str
    timestamp: datetime


class BroadcastChannel:
    """
    Manages broadcast communication between agents.

    Workflow:
    1. Agent calls broadcast_message()
    2. Channel interrupts all other agents
    3. Each agent receives broadcast and responds
    4. All responses collected
    5. Original agent receives responses
    6. All agents resume normal operation
    """

    def __init__(self, orchestrator: "Orchestrator"):
        self.orchestrator = orchestrator
        self.pending_broadcasts: Dict[str, BroadcastMessage] = {}
        self.responses: Dict[str, List[BroadcastResponse]] = {}
        self._lock = asyncio.Lock()

    async def broadcast(
        self,
        sender_id: str,
        message: str,
        requires_response: bool = True
    ) -> List[BroadcastResponse]:
        """
        Broadcast a message to all other agents and collect responses.

        Args:
            sender_id: ID of agent sending broadcast
            message: Message content
            requires_response: Whether agents must respond

        Returns:
            List of responses from all agents

        Process:
            1. Create broadcast message
            2. Interrupt all agents except sender
            3. Inject broadcast as high-priority message
            4. Wait for all responses
            5. Return responses to sender
        """
        async with self._lock:
            broadcast_id = str(uuid.uuid4())
            broadcast_msg = BroadcastMessage(
                id=broadcast_id,
                sender_agent_id=sender_id,
                content=message,
                timestamp=datetime.now(),
                requires_response=requires_response
            )

            # Store for tracking
            self.pending_broadcasts[broadcast_id] = broadcast_msg

            # Interrupt all agents except sender
            await self._interrupt_agents(sender_id, broadcast_msg)

            # Wait for responses with timeout
            responses = await self._collect_responses(
                broadcast_id,
                timeout=300  # 5 minutes
            )

            # Cleanup
            del self.pending_broadcasts[broadcast_id]

            return responses

    async def _interrupt_agents(
        self,
        sender_id: str,
        broadcast: BroadcastMessage
    ):
        """
        Interrupt all agents except sender with broadcast message.

        Implementation:
            - Sets interrupt flag on each agent
            - Injects broadcast as next message in agent's queue
            - Agents check interrupt flag at turn boundaries
        """
        for agent in self.orchestrator.agents:
            if agent.id != sender_id:
                await agent.interrupt_with_broadcast(broadcast)

    async def _collect_responses(
        self,
        broadcast_id: str,
        timeout: int
    ) -> List[BroadcastResponse]:
        """
        Collect responses from all agents with timeout.

        Returns:
            List of responses (may be incomplete if timeout)
        """
        pass


# MCP Tool for agents
@mcp.tool()
def broadcast_message(
    message: str,
    requires_response: bool = True
) -> Dict[str, Any]:
    """
    Broadcast a message to all other agents and wait for responses.

    WARNING: This will interrupt all other agents. Use sparingly.

    Args:
        message: Message to broadcast
        requires_response: Whether to wait for agent responses

    Returns:
        Dictionary with responses from all agents

    Example:
        broadcast_message(
            "I'm about to modify the shared database schema. "
            "Does anyone have pending writes?"
        )
    """
    pass
```

**Agent Integration:**

```python
# In massgen/agent.py

class Agent:
    def __init__(self, ...):
        self._interrupt_flag = asyncio.Event()
        self._broadcast_queue: asyncio.Queue[BroadcastMessage] = asyncio.Queue()

    async def interrupt_with_broadcast(self, broadcast: BroadcastMessage):
        """
        Interrupt this agent with a broadcast message.

        Args:
            broadcast: The broadcast message to handle
        """
        await self._broadcast_queue.put(broadcast)
        self._interrupt_flag.set()

    async def _check_interrupts(self) -> Optional[BroadcastMessage]:
        """
        Check for pending broadcasts and handle them.
        Called at safe interrupt points (turn boundaries).

        Returns:
            Broadcast message if one is pending, None otherwise
        """
        if self._interrupt_flag.is_set():
            try:
                broadcast = self._broadcast_queue.get_nowait()
                self._interrupt_flag.clear()
                return broadcast
            except asyncio.QueueEmpty:
                self._interrupt_flag.clear()
        return None

    async def _handle_broadcast(self, broadcast: BroadcastMessage) -> str:
        """
        Process a broadcast and generate a response.

        Args:
            broadcast: The broadcast to handle

        Returns:
            Response message
        """
        # Inject broadcast into conversation
        system_message = f"""
        BROADCAST FROM {broadcast.sender_agent_id}:
        {broadcast.content}

        Please provide a brief response to this broadcast.
        After responding, you will resume your previous task.
        """

        # Get response from agent
        response = await self._generate_response(system_message)

        # Submit response to broadcast channel
        await self.orchestrator.broadcast_channel.submit_response(
            broadcast.id,
            self.id,
            response
        )

        return response
```

### 3. Task Delegation System

**Location:** `massgen/orchestrator/_task_delegation.py` (new file)

**Key Components:**

```python
@dataclass
class DelegatedTask:
    """Represents a task delegated to a sub-orchestrator."""
    id: str  # UUID
    parent_agent_id: str
    parent_task_id: Optional[str]  # Task ID from agent's plan
    description: str
    config: Dict[str, Any]  # Sub-orchestrator config
    status: Literal["pending", "running", "completed", "failed"]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskDelegationManager:
    """
    Manages delegation of tasks to sub-orchestrators.

    Features:
    - Spawn sub-orchestrators on-demand
    - Run sub-orchestrators in parallel with parent
    - Track delegation status
    - Return results when complete
    """

    def __init__(self, orchestrator: "Orchestrator"):
        self.orchestrator = orchestrator
        self.delegated_tasks: Dict[str, DelegatedTask] = {}
        self.sub_orchestrators: Dict[str, "Orchestrator"] = {}
        self._tasks = {}  # asyncio.Task objects

    async def delegate_task(
        self,
        parent_agent_id: str,
        description: str,
        config: Optional[Dict[str, Any]] = None,
        wait: bool = False,
        parent_task_id: Optional[str] = None
    ) -> str:
        """
        Delegate a task to a sub-orchestrator.

        Args:
            parent_agent_id: ID of agent delegating the task
            description: Task description
            config: Optional custom config for sub-orchestrator
            wait: If True, block until task completes. If False, run in parallel.
            parent_task_id: Optional task ID from parent agent's plan

        Returns:
            Delegation ID for tracking

        Example (wait):
            delegation_id = await delegate_task(
                "agent_a",
                "Research OAuth 2.0 implementations",
                wait=True
            )
            result = get_delegation_result(delegation_id)

        Example (parallel):
            delegation_id = await delegate_task(
                "agent_a",
                "Run comprehensive test suite",
                wait=False
            )
            # Continue working on other tasks
            while not is_delegation_complete(delegation_id):
                # Do other work
                await work_on_other_task()
            result = get_delegation_result(delegation_id)
        """
        delegation_id = str(uuid.uuid4())

        # Create delegated task record
        delegated_task = DelegatedTask(
            id=delegation_id,
            parent_agent_id=parent_agent_id,
            parent_task_id=parent_task_id,
            description=description,
            config=config or {},
            status="pending",
            created_at=datetime.now()
        )
        self.delegated_tasks[delegation_id] = delegated_task

        # Create sub-orchestrator config
        sub_config = self._create_sub_orchestrator_config(
            parent_agent_id,
            description,
            config
        )

        # Spawn sub-orchestrator
        sub_orchestrator = await self._spawn_sub_orchestrator(
            delegation_id,
            sub_config
        )
        self.sub_orchestrators[delegation_id] = sub_orchestrator

        # Run in background
        task = asyncio.create_task(
            self._run_delegation(delegation_id, sub_orchestrator)
        )
        self._tasks[delegation_id] = task

        # Wait if requested
        if wait:
            await task

        return delegation_id

    async def _run_delegation(
        self,
        delegation_id: str,
        sub_orchestrator: "Orchestrator"
    ):
        """
        Run a sub-orchestrator and track completion.

        Args:
            delegation_id: ID of delegation
            sub_orchestrator: Sub-orchestrator instance
        """
        delegated_task = self.delegated_tasks[delegation_id]

        try:
            delegated_task.status = "running"
            delegated_task.started_at = datetime.now()

            # Run sub-orchestrator
            result = await sub_orchestrator.run()

            delegated_task.status = "completed"
            delegated_task.completed_at = datetime.now()
            delegated_task.result = result

        except Exception as e:
            delegated_task.status = "failed"
            delegated_task.completed_at = datetime.now()
            delegated_task.error = str(e)

    def _create_sub_orchestrator_config(
        self,
        parent_agent_id: str,
        description: str,
        custom_config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create configuration for sub-orchestrator.

        Inherits settings from parent orchestrator unless overridden.

        Args:
            parent_agent_id: ID of parent agent
            description: Task description
            custom_config: Optional custom config overrides

        Returns:
            Configuration dictionary for sub-orchestrator
        """
        # Start with parent config
        base_config = self.orchestrator.config.copy()

        # Modify for sub-orchestrator
        base_config["task"] = description
        base_config["parent_orchestrator_id"] = self.orchestrator.id
        base_config["parent_agent_id"] = parent_agent_id

        # Apply custom overrides
        if custom_config:
            base_config.update(custom_config)

        return base_config

    async def _spawn_sub_orchestrator(
        self,
        delegation_id: str,
        config: Dict[str, Any]
    ) -> "Orchestrator":
        """
        Create and initialize a sub-orchestrator.

        Args:
            delegation_id: ID for tracking
            config: Orchestrator configuration

        Returns:
            Initialized sub-orchestrator instance
        """
        from massgen.orchestrator import Orchestrator

        sub_orchestrator = Orchestrator(
            config=config,
            parent_delegation_id=delegation_id
        )
        await sub_orchestrator.initialize()

        return sub_orchestrator

    def get_delegation_status(self, delegation_id: str) -> Dict[str, Any]:
        """Get current status of a delegated task."""
        if delegation_id not in self.delegated_tasks:
            raise ValueError(f"Unknown delegation ID: {delegation_id}")

        task = self.delegated_tasks[delegation_id]
        return {
            "id": task.id,
            "status": task.status,
            "description": task.description,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error
        }

    def is_delegation_complete(self, delegation_id: str) -> bool:
        """Check if a delegated task is complete."""
        task = self.delegated_tasks.get(delegation_id)
        return task and task.status in ["completed", "failed"]


# MCP Tools for agents
@mcp.tool()
def delegate_task(
    description: str,
    task_id: Optional[str] = None,
    wait: bool = False,
    custom_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Delegate a task to a sub-orchestrator.

    The sub-orchestrator will run independently with its own agents.
    You can either wait for completion or continue working in parallel.

    Args:
        description: Clear description of the task to delegate
        task_id: Optional task ID from your plan
        wait: If True, block until complete. If False, run in parallel.
        custom_config: Optional config overrides (agents, backends, etc.)

    Returns:
        Dictionary with delegation_id and initial status

    Example (blocking):
        result = delegate_task(
            "Research and document OAuth 2.0 best practices",
            wait=True
        )
        # Use result['delegation_id'] to get details

    Example (parallel):
        delegation = delegate_task(
            "Run full test suite and generate coverage report",
            wait=False
        )
        # Continue working on other tasks
        # Check status with check_delegation_status(delegation_id)
    """
    pass


@mcp.tool()
def check_delegation_status(delegation_id: str) -> Dict[str, Any]:
    """
    Check the status of a delegated task.

    Args:
        delegation_id: ID returned from delegate_task

    Returns:
        Dictionary with current status and results (if complete)
    """
    pass


@mcp.tool()
def get_delegation_result(delegation_id: str) -> Dict[str, Any]:
    """
    Get the result of a completed delegated task.

    Args:
        delegation_id: ID returned from delegate_task

    Returns:
        Dictionary with task results

    Raises:
        ValueError: If task is not yet complete
    """
    pass
```

### 4. Integration with Orchestrator

**Location:** `massgen/orchestrator.py` (modifications)

```python
class Orchestrator:
    def __init__(self, config: Dict[str, Any], parent_delegation_id: Optional[str] = None):
        # Existing initialization...

        # New components
        self.broadcast_channel = BroadcastChannel(self)
        self.delegation_manager = TaskDelegationManager(self)
        self.task_plans: Dict[str, TaskPlan] = {}  # agent_id -> TaskPlan

        # Track if this is a sub-orchestrator
        self.parent_delegation_id = parent_delegation_id
        self.is_sub_orchestrator = parent_delegation_id is not None

    async def initialize(self):
        """Initialize orchestrator and all agents."""
        # Existing initialization...

        # Initialize planning tools for each agent
        for agent in self.agents:
            await self._inject_planning_tools(agent)

    async def _inject_planning_tools(self, agent: Agent):
        """
        Inject planning and coordination tools into agent's backend.

        Args:
            agent: Agent to inject tools into
        """
        # Create planning MCP server for this agent
        planning_mcp_config = self._create_planning_mcp_config(agent.id)

        # Inject into agent's backend
        agent.backend.add_mcp_server(planning_mcp_config)

    def _create_planning_mcp_config(self, agent_id: str) -> Dict[str, Any]:
        """
        Create MCP server config for planning tools.

        Args:
            agent_id: ID of agent

        Returns:
            MCP server configuration
        """
        script_path = Path(__file__).parent / "tools" / "_planning_mcp_server.py"

        config = {
            "name": f"planning_{agent_id}",
            "type": "stdio",
            "command": "fastmcp",
            "args": [
                "run",
                f"{script_path}:create_server",
                "--",
                "--agent-id", agent_id,
                "--orchestrator-id", self.id
            ]
        }

        return config

    async def run(self) -> Dict[str, Any]:
        """
        Main orchestrator loop.

        Returns:
            Results dictionary
        """
        # Existing run logic...

        # Before cleanup: ensure all delegated tasks complete
        if self.delegation_manager.delegated_tasks:
            await self._wait_for_delegations()

        return results

    async def _wait_for_delegations(self):
        """Wait for all delegated tasks to complete."""
        pending = [
            task_id
            for task_id, task in self.delegation_manager.delegated_tasks.items()
            if task.status in ["pending", "running"]
        ]

        if pending:
            await asyncio.gather(*[
                self.delegation_manager._tasks[task_id]
                for task_id in pending
            ])
```

## Configuration

### YAML Configuration

```yaml
# Enable planning and coordination features
orchestrator:
  enable_agent_planning: true
  enable_broadcasts: true
  enable_task_delegation: true

  # Broadcast settings
  broadcast_timeout: 300  # seconds to wait for responses
  broadcast_response_required: true

  # Delegation settings
  max_delegation_depth: 1  # Only one level of sub-orchestrators initially
  delegation_timeout: 3600  # Maximum time for delegated task

agents:
  - id: "agent_a"
    backend:
      type: "openai"
      model: "gpt-4o"
      # Planning tools auto-injected if enable_agent_planning=true

  - id: "agent_b"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
```

### Builder Integration

**Location:** `massgen/config_builder.py` (modifications)

Add prompts for planning features:
- "Enable agent task planning? (y/n)"
- "Enable broadcast communication? (y/n)"
- "Enable task delegation? (y/n)"

### Message Template Guidance

**Location:** `massgen/message_templates.py` (modifications)

**Critical:** Agents need explicit guidance in their system messages to understand when and how to use planning and coordination tools. Without this guidance, agents may not know these tools exist or how to use them effectively.

**New System Message Section:**

Add the following guidance when planning/coordination features are enabled:

```python
def get_planning_coordination_guidance(
    enable_planning: bool,
    enable_broadcasts: bool,
    enable_delegation: bool
) -> str:
    """
    Generate system message guidance for planning and coordination tools.

    This guidance is critical for agents to understand when and how to use
    these tools effectively.
    """

    guidance = []

    if enable_planning:
        guidance.append("""
## Task Planning and Management

You have access to task planning tools to organize complex work:

**When to create a task plan:**
- Multi-step tasks with dependencies
- Complex features requiring coordination
- Work that can be parallelized
- Long-running projects with clear milestones

**Tools available:**
- `create_task_plan(tasks)` - Create a plan with tasks and dependencies
- `get_ready_tasks()` - Get tasks ready to start (dependencies satisfied)
- `get_blocked_tasks()` - See what's waiting on dependencies
- `update_task_status(task_id, status)` - Mark progress (pending/in_progress/completed/blocked)
- `add_task(description, depends_on)` - Add new tasks as you discover them

**Best practices:**
1. **Break down complex work** into manageable tasks
2. **Model dependencies explicitly** when creating your plan
3. **Use named task IDs** for clarity (e.g., "research_oauth", "impl_endpoints")
4. **Check ready tasks** regularly to identify parallel work opportunities
5. **Update status immediately** as you complete tasks

**Example:**
```python
plan = create_task_plan([
    {"id": "research", "description": "Research OAuth providers"},
    {"id": "design", "description": "Design auth flow", "depends_on": ["research"]},
    {"id": "implement", "description": "Implement endpoints", "depends_on": ["design"]}
])

# Work on first task
update_task_status("research", "in_progress")
# ... do research ...
update_task_status("research", "completed")

# Check what's ready next
ready = get_ready_tasks()  # ["design"]
```
""")

    if enable_broadcasts:
        guidance.append("""
## Coordinating with Other Agents

You can communicate with other agents using broadcast tools:

**When to use broadcasts:**
- You need input or help from other agents
- Potential conflicts with others' work
- Clarifying questions about shared resources
- Coordinating on dependencies

**Tools available:**
- `broadcast_message(message)` - Send message to all agents (they will be interrupted)
- `ask_others(question)` - Ask for input (interrupts agents for responses)

**IMPORTANT:** Broadcasts interrupt all other agents. Use thoughtfully:
- ✅ "I'm about to refactor User model. Any concerns?"
- ✅ "Does anyone know which OAuth library we're using?"
- ✅ "I'm stuck on this bug. Ideas?"
- ❌ "I'm starting work" (too frequent/low value)
- ❌ "Still working on task X" (status updates don't need interrupts)

**Broadcast etiquette:**
- Be specific and actionable in your questions
- Only broadcast when you genuinely need coordination
- Respond helpfully when others broadcast to you
- If unsure, check task lists first to see what others are doing
""")

    if enable_delegation:
        guidance.append("""
## Delegating to Sub-Orchestrators

You can delegate tasks to sub-orchestrators that run independently:

**When to delegate:**
- Self-contained subtasks that can run independently
- Research or analysis that takes multiple steps
- Testing or validation work that's orthogonal to your main task
- Work that benefits from different agent configurations

**Tools available:**
- `delegate_task(description, wait=False)` - Delegate to sub-orchestrator
- `check_delegation_status(delegation_id)` - Check if delegation is complete
- `get_delegation_result(delegation_id)` - Get results when complete

**Delegation modes:**

1. **Blocking** (`wait=True`): Wait for results before continuing
   ```python
   result = delegate_task(
       "Research OAuth 2.0 best practices and write summary",
       wait=True
   )
   # Result available immediately
   ```

2. **Parallel** (`wait=False`): Continue working while delegation runs
   ```python
   delegation_id = delegate_task(
       "Run comprehensive test suite",
       wait=False
   )
   # Continue with other work
   # ... work on other tasks ...

   # Check if ready
   if check_delegation_status(delegation_id)['status'] == 'completed':
       result = get_delegation_result(delegation_id)
   ```

**Combining with task planning:**
- Link delegations to task IDs: `delegate_task(description, task_id="research_oauth")`
- Use `get_ready_tasks()` to find tasks you can delegate in parallel
- Delegate independent tasks simultaneously to maximize throughput

**Example: Parallel delegation**
```python
plan = create_task_plan([
    {"id": "research_oauth", "description": "Research OAuth"},
    {"id": "research_db", "description": "Research DB schema"},
    {"id": "implement", "description": "Implement", "depends_on": ["research_oauth", "research_db"]}
])

# Both research tasks are ready (no dependencies)
ready = get_ready_tasks()

# Delegate both in parallel
delegations = {}
for task in ready:
    delegations[task['id']] = delegate_task(task['description'], wait=False)

# Wait for both, then continue
```
""")

    return "\n".join(guidance)
```

**Integration Points:**

1. **In `build_system_message()`** or equivalent:
   ```python
   system_message_parts = [
       # ... existing sections ...
   ]

   # Add planning/coordination guidance
   if orchestrator.enable_agent_planning or orchestrator.enable_broadcasts or orchestrator.enable_task_delegation:
       planning_guidance = get_planning_coordination_guidance(
           orchestrator.enable_agent_planning,
           orchestrator.enable_broadcasts,
           orchestrator.enable_task_delegation
       )
       system_message_parts.append(planning_guidance)

   return "\n\n".join(system_message_parts)
   ```

2. **Context-specific guidance:**
   - Add reminders about task planning when the user's task seems complex
   - Suggest coordination tools when multiple agents are working on related areas
   - Prompt delegation for obvious subtasks

3. **Dynamic guidance based on state:**
   ```python
   # If agent has task plan with blocked tasks
   if agent.has_blocked_tasks():
       add_reminder("You have blocked tasks waiting on dependencies. "
                   "Check get_blocked_tasks() to see what's blocking progress.")

   # If multiple ready tasks exist
   if len(agent.get_ready_tasks()) > 1:
       add_reminder("Multiple tasks are ready to start. Consider delegating "
                   "some in parallel to maximize throughput.")
   ```

**Why this is critical:**
- MCP tools alone don't tell agents **when** to use them
- Without guidance, agents may never create task plans or coordinate
- Explicit examples show the expected usage patterns
- Best practices prevent misuse (e.g., too many broadcasts)
- Integration with existing workflows (task planning + delegation) isn't obvious without examples

## Usage Examples

### Example 1: Agent Task Planning with Dependencies

```python
# Agent creates a plan with dependencies
plan = create_task_plan([
    {
        "id": "analyze_auth",
        "description": "Analyze existing authentication code"
    },
    {
        "id": "research_oauth",
        "description": "Research OAuth 2.0 best practices",
        "depends_on": ["analyze_auth"]
    },
    {
        "id": "design_flow",
        "description": "Design new authentication flow",
        "depends_on": ["research_oauth"]
    },
    {
        "id": "implement_endpoints",
        "description": "Implement OAuth endpoints",
        "depends_on": ["design_flow"]
    },
    {
        "id": "write_tests",
        "description": "Write tests for authentication",
        "depends_on": ["implement_endpoints"]
    }
])

# Check which tasks are ready (only first task has no dependencies)
ready = get_ready_tasks()
# ready = [{"id": "analyze_auth", ...}]

# Mark first task as in progress
update_task_status("analyze_auth", "in_progress")

# Work on task...

# Mark as completed
result = update_task_status("analyze_auth", "completed")
# result = {
#     "task": {...},
#     "newly_ready_tasks": [{"id": "research_oauth", ...}]
# }

# Add new task discovered during work
add_task(
    "Add rate limiting to OAuth endpoints",
    depends_on=["implement_endpoints"]
)
```

### Example 2: Broadcasting for Coordination

```python
# Agent A is about to modify shared resource
response = broadcast_message(
    "I'm about to refactor the User model. Does anyone have pending work on it?"
)

# Other agents interrupted and respond
# Agent B: "Yes, I'm writing a migration. Can you wait 5 minutes?"
# Agent C: "No dependencies from me, go ahead"

# Agent A waits then proceeds
```

### Example 3: Task Delegation (Blocking)

```python
# Agent delegates complex research task
result = delegate_task(
    description="Research all OAuth 2.0 providers and their API differences",
    wait=True  # Block until complete
)

# Result available immediately
print(result['result'])
```

### Example 4: Task Delegation (Parallel)

```python
# Agent delegates long-running task
delegation_id = delegate_task(
    description="Run full test suite and generate coverage report",
    wait=False  # Continue working
)

# Work on other tasks while delegation runs
update_task_status(current_task_id, "in_progress")
# ... do other work ...

# Check if delegation is done
while not check_delegation_status(delegation_id)['completed']:
    # Continue other work
    await work_on_next_task()

# Get results when ready
result = get_delegation_result(delegation_id)
```

### Example 5: Parallel Delegation with Dependencies

```python
# Agent creates plan with parallel opportunities
plan = create_task_plan([
    {
        "id": "research_oauth",
        "description": "Research OAuth 2.0 providers and best practices"
    },
    {
        "id": "research_db",
        "description": "Research database schema design patterns"
    },
    {
        "id": "impl_oauth",
        "description": "Implement OAuth endpoints",
        "depends_on": ["research_oauth"]
    },
    {
        "id": "impl_db",
        "description": "Implement database models",
        "depends_on": ["research_db"]
    },
    {
        "id": "integration_tests",
        "description": "Write and run integration tests",
        "depends_on": ["impl_oauth", "impl_db"]
    }
])

# Get ready tasks - both research tasks have no dependencies
ready = get_ready_tasks()
# ready = [research_oauth, research_db]

# Delegate both research tasks in parallel
delegations = {}
for task in ready:
    delegation_id = delegate_task(
        task['description'],
        task_id=task['id'],
        wait=False  # Run in parallel
    )
    delegations[task['id']] = delegation_id
    update_task_status(task['id'], "in_progress")

# Continue with other work while delegations run...

# Wait for both to complete
all_done = False
while not all_done:
    statuses = [
        check_delegation_status(delegations['research_oauth']),
        check_delegation_status(delegations['research_db'])
    ]
    all_done = all(s['status'] == 'completed' for s in statuses)
    if not all_done:
        await asyncio.sleep(5)

# Mark as completed
update_task_status("research_oauth", "completed")
result_db = update_task_status("research_db", "completed")

# Check newly ready tasks
print(result_db['newly_ready_tasks'])
# [{"id": "impl_oauth", ...}, {"id": "impl_db", ...}]

# Now delegate implementation tasks in parallel
ready = get_ready_tasks()
for task in ready:
    delegation_id = delegate_task(
        task['description'],
        task_id=task['id'],
        wait=False
    )
    delegations[task['id']] = delegation_id
    update_task_status(task['id'], "in_progress")

# Pattern continues: maximize parallelism based on dependencies
```

## Implementation Plan

**IMPORTANT:** Implement phases sequentially. Complete Phase 1 entirely before starting Phase 2, complete Phase 2 before Phase 3, etc. Each phase builds on the previous one.

### Phase 1: Task Planning Tools (IMPLEMENT FIRST)
**Priority: Highest - Foundation for all other features**

This phase provides the core planning infrastructure that broadcasts and delegation will build upon.

1. ✅ Design document created
2. ⏳ Create `TaskPlan` and `Task` dataclasses
   - Implement dependency tracking
   - Add validation for circular dependencies
3. ⏳ Implement planning MCP server (`massgen/tools/_planning_mcp_server.py`)
   - `create_task_plan()` with dependency support
   - `add_task()`, `update_task_status()`, `edit_task()`, `delete_task()`
   - `get_ready_tasks()`, `get_blocked_tasks()`, `get_task_plan()`
4. ⏳ Integrate with orchestrator
   - Store task plans per agent
   - Inject planning MCP server for each agent
   - Serialize task plans for resumability
5. ⏳ Add configuration options
   - `enable_agent_planning` flag
   - Max tasks per plan
6. ⏳ Update message templates (`massgen/message_templates.py`)
   - Add task planning guidance to system messages
   - Include when to use, best practices, examples
7. ⏳ Write unit tests
   - Task creation and dependency validation
   - Status updates and ready/blocked task detection
   - Serialization/deserialization
8. ⏳ Update documentation
   - User guide for task planning
   - API reference for tools

**Milestone:** Agents can create, manage, and track task plans with dependencies

### Phase 2: Broadcast/Coordination System (IMPLEMENT SECOND)
**Priority: Medium - Enables agent-to-agent and agent-to-human communication**

**Note on naming:** `broadcast_message()` and `ask_others()` are equivalent in implementation - same interrupt mechanism, just different framing. Start with `broadcast_message()` but be prepared to rename to `ask_others()` based on empirical usage patterns. The "ask_others" framing may be clearer for agents to understand when to use it.

1. ⏳ Implement `BroadcastChannel` class (`massgen/orchestrator/_broadcast_channel.py`)
   - Message queue and response collection
   - Timeout handling
   - Rate limiting per agent
2. ⏳ Add interrupt handling to `Agent` class
   - Interrupt flag and broadcast queue
   - Check interrupts at turn boundaries
   - Generate responses to broadcasts
3. ⏳ Create broadcast MCP tool
   - Start with `broadcast_message(message, requires_response)`
   - Consider renaming to `ask_others(question, allow_human_response)` if usage suggests
4. ⏳ Implement human participation (for `ask_others` variant)
   - Notification UI for human
   - Optional response from human alongside agents
   - "Skip all" option
5. ⏳ Add response collection
   - Parallel collection from all agents
   - Include human response if provided
6. ⏳ Add configuration options
   - `enable_broadcasts` flag
   - `broadcast_timeout`, max broadcasts per agent
7. ⏳ Update message templates
   - Add broadcast/coordination guidance
   - Examples of good vs bad broadcasts
   - Etiquette and best practices
8. ⏳ Write unit tests
   - Broadcast delivery and interrupts
   - Response collection and timeouts
   - Rate limiting
9. ⏳ Update documentation
   - User guide for coordination
   - Examples of coordination patterns

**Milestone:** Agents can communicate with each other and optionally the human via broadcasts

**Decision point:** After initial usage, evaluate whether to rename `broadcast_message` → `ask_others` based on:
- How often agents use it appropriately vs inappropriately
- User feedback on naming clarity
- Whether human participation feature is valuable

### Phase 3: Task Delegation (IMPLEMENT THIRD)
**Priority: Lower - Advanced feature building on planning and coordination**

Delegation is the most complex feature and benefits from having planning (Phase 1) and coordination (Phase 2) already working.

1. ⏳ Implement `TaskDelegationManager` (`massgen/orchestrator/_task_delegation.py`)
   - Track delegated tasks
   - Manage sub-orchestrator lifecycle
   - Handle delegation failures
2. ⏳ Add sub-orchestrator spawning logic
   - Create sub-orchestrator from parent config
   - Inherit settings (filesystem, context paths)
   - Run in parallel via asyncio.Task
3. ⏳ Create delegation MCP tools
   - `delegate_task(description, wait, task_id)`
   - `check_delegation_status(delegation_id)`
   - `get_delegation_result(delegation_id)`
4. ⏳ Implement parallel execution support
   - Non-blocking delegation (wait=False)
   - Track multiple concurrent delegations
   - Automatic cleanup when complete
5. ⏳ Add result collection
   - Structured results from sub-orchestrators
   - Error handling and reporting
   - Link results back to parent task plan
6. ⏳ Add configuration options
   - `enable_task_delegation` flag
   - `max_delegation_depth`, `delegation_timeout`
   - `max_concurrent_delegations`
7. ⏳ Update message templates
   - Add delegation guidance
   - Examples of blocking vs parallel delegation
   - Combining delegation with task planning
8. ⏳ Write unit tests
   - Sub-orchestrator spawning
   - Parallel delegation tracking
   - Result collection and error handling
9. ⏳ Update documentation
   - User guide for delegation
   - Advanced patterns (parallel delegation with dependencies)

**Milestone:** Agents can delegate subtasks to sub-orchestrators and work in parallel

### Phase 4: Integration & Testing (IMPLEMENT LAST)
**Priority: Final validation**

1. ⏳ End-to-end integration tests
   - Complete workflow: planning → broadcast → delegation
   - Multi-agent scenarios
   - Error recovery and edge cases
2. ⏳ Performance testing with multiple agents
   - Overhead measurements
   - Scalability testing
   - Optimization if needed
3. ⏳ Documentation updates
   - Complete user guide
   - Advanced examples and case studies
   - Troubleshooting guide
4. ⏳ Config builder updates
   - Interactive prompts for all features
   - Validation and examples
5. ⏳ Case study demonstrating features
   - Real-world scenario using all three capabilities
   - Show performance benefits of parallel delegation

**Milestone:** Production-ready planning and coordination system

## Security Considerations

### Planning Tools
- **Isolation**: Each agent's task plan is isolated
- **Validation**: Task IDs validated to prevent cross-agent access
- **Resource limits**: Maximum tasks per plan (e.g., 100)

### Broadcast System
- **Rate limiting**: Maximum broadcasts per agent per hour
- **Content filtering**: Validate broadcast messages for sensitive data
- **Timeout enforcement**: Prevent indefinite waits
- **Interrupt boundaries**: Only interrupt at safe points (turn boundaries)

### Task Delegation
- **Depth limits**: Prevent deep delegation hierarchies (max 1 level initially)
- **Resource quotas**: Limit number of concurrent delegations
- **Config validation**: Validate sub-orchestrator configs
- **Isolation**: Sub-orchestrators isolated from parent state

## Performance Considerations

### Task Planning
- **In-memory storage**: Fast access, minimal overhead
- **Lazy serialization**: Only serialize on orchestrator save/resume
- **Efficient lookups**: Use dict-based storage (O(1) lookups)

### Broadcasts
- **Async interrupts**: Non-blocking interrupt delivery
- **Parallel response collection**: Gather responses concurrently
- **Timeout handling**: Prevent deadlocks
- **Estimated overhead**: ~1-5 seconds per broadcast (depending on agent response time)

### Task Delegation
- **Parallel execution**: Sub-orchestrators run in separate asyncio tasks
- **Resource pooling**: Reuse sub-orchestrator infrastructure where possible
- **Lazy cleanup**: Clean up sub-orchestrators after results retrieved
- **Estimated overhead**: Sub-orchestrator startup ~2-5 seconds

## Testing Strategy

### Unit Tests

**Planning Tools** (`massgen/tests/test_planning_tools.py`):
```python
class TestTaskPlan:
    """Test task plan data structures"""

class TestPlanningMCPServer:
    """Test planning MCP server tools"""

class TestTaskOperations:
    """Test create, update, delete operations"""
```

**Broadcast System** (`massgen/tests/test_broadcast_channel.py`):
```python
class TestBroadcastChannel:
    """Test broadcast channel functionality"""

class TestAgentInterrupts:
    """Test agent interrupt handling"""

class TestBroadcastResponses:
    """Test response collection"""
```

**Task Delegation** (`massgen/tests/test_task_delegation.py`):
```python
class TestDelegationManager:
    """Test delegation manager"""

class TestSubOrchestrator:
    """Test sub-orchestrator spawning"""

class TestParallelDelegation:
    """Test parallel execution"""
```

### Integration Tests

**End-to-End** (`massgen/tests/integration/test_planning_coordination.py`):
```python
async def test_full_coordination_workflow():
    """
    Test complete workflow:
    1. Agent creates task plan
    2. Agent delegates one task
    3. Agent broadcasts status
    4. Other agents respond
    5. Delegated task completes
    6. Agent marks tasks done
    """
```

## Success Criteria

- ⏳ Agents can create and manage task plans
- ⏳ Agents can broadcast and interrupt each other
- ⏳ Agents can delegate tasks to sub-orchestrators
- ⏳ Parallel delegation works without blocking
- ⏳ All operations are thread-safe
- ⏳ Unit test coverage >80%
- ⏳ Integration tests pass
- ⏳ Documentation complete
- ⏳ Performance overhead <10% for typical workflows

## Future Enhancements

### 1. Multi-Level Delegation
- Allow sub-orchestrators to delegate further
- Track delegation trees
- Implement resource quotas across levels

### 2. Direct Peer-to-Peer Messaging
- Agent-to-agent messages without broadcast
- Private channels between agent pairs
- Message queuing and delivery guarantees

### 3. Advanced Synchronization
- Shared locks for resource coordination
- Barriers for multi-agent synchronization
- Semaphores for resource pooling

### 4. Task Dependencies
- Cross-agent task dependencies
- Automatic dependency resolution
- Deadlock detection and prevention

### 5. Planning Intelligence
- Automatic task breakdown using LLMs
- Task duration estimation
- Critical path analysis

### 6. (Important) Learn from Previous Planning Stages
Come up with some way where agents are smarter about how they act now based on previous. E.g., they will decide to vote better based on how the tasks completed, make better decisions on subagent handling. However, some of this might just be learned through the context, without a need for anything too explicit.

## Alternative Design Considerations

### Option 1: `ask_others()` - Unified Human/Agent Input

**Motivation:** The `broadcast_message()` framing may feel too heavy-handed, as agents might struggle to gauge when interrupting everyone is justified. Additionally, some model backends (like OpenAI) naturally ask more clarifying questions, while others don't. We want to simulate this natural questioning behavior across all backends.

**Proposed Alternative:** Rename and reframe `broadcast_message()` as **`ask_others()`** which serves dual purposes:

```python
@mcp.tool()
def ask_others(
    question: str,
    allow_human_response: bool = True,
    specific_agents: Optional[List[str]] = None,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Ask for input from other agents and/or the human user.

    This tool uses the same interrupt mechanism as broadcast_message(), but
    frames the interaction as requesting help/input rather than making an
    announcement. The human user can optionally respond alongside other agents.

    Args:
        question: Your question for others
        allow_human_response: If True, human can respond (default: True)
        specific_agents: Specific agent IDs to ask (or None for all)
        timeout: How long to wait for responses

    Returns:
        Dictionary with responses from agents and optionally human:
        {
            "responses": {
                "agent_a": "My response...",
                "agent_b": "My response...",
                "human": "Optional human response..."  # Only if human chose to respond
            },
            "human_responded": bool
        }

    Use cases:
        - "I'm about to refactor the User model. Any concerns or suggestions?"
        - "Does anyone know which OAuth library we decided to use?"
        - "I'm stuck on this authentication bug. Ideas?"
        - "Should I use approach A or approach B for this feature?"

    Benefits:
        - Feels more collaborative than "broadcast"
        - Clearer when to use (when you have a question)
        - Mirrors how questioning models like OpenAI naturally behave
        - Simulates human asking for input, but can be agent-to-agent
        - Human can participate if they want, or let agents handle it
    """
```

**Implementation Notes:**
- **Same interrupt mechanism** as broadcast_message() - all agents interrupted at turn boundaries
- **Human notification**: If `allow_human_response=True`, orchestrator shows notification to human:
  ```
  Agent A is asking for input:
  "I'm about to refactor the User model. Any concerns?"

  Other agents will respond automatically.
  Would you like to respond? [y/N/skip all]
  ```
- **Timeout applies to both**: If human doesn't respond within timeout, proceeds with agent responses only
- **Optional human participation**: Human can choose to respond, ignore, or set "skip all" to never be asked

**Benefits over `broadcast_message()`:**
- **Clearer use case**: "I have a question" vs "I'm broadcasting an announcement"
- **Encourages collaboration**: Natural to ask for help/input
- **Simulates human-like questioning**: Some models ask more questions naturally (OpenAI) - this extends that behavior to all backends
- **Flexible response**: Human can participate or let agents handle it

### Option 2: Read-Only Task Visibility

**Motivation:** Broadcasting interrupts everyone, which may be too disruptive. Agents might benefit from passive awareness of what others are doing.

**Proposed Tool:**
```python
@mcp.tool()
def view_agent_tasks(agent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    View task lists of other agents (read-only).

    Args:
        agent_id: Specific agent to view, or None to see all

    Returns:
        Dictionary with agent task lists (summary view only)

    Use cases:
        - Check if someone else is working on related tasks
        - Identify potential conflicts before they happen
        - Find opportunities to help or coordinate
        - Decide whether to ask_others() or proceed independently

    Example:
        tasks = view_agent_tasks()
        # See: Agent B is working on "Implement OAuth endpoints"
        # Decision: "I should ask_others() about OAuth library choice"
    """
```

**Benefits:**
- **Lightweight coordination** - No interruption, just awareness
- **Maintains independence** - Can't edit others' lists
- **Proactive coordination** - Helps agents decide when to use `ask_others()`

**Constraints:**
- **Read-only** - Cannot modify other agents' task plans
- **Summary view** - Just task descriptions/status, not full details
- **Optional usage** - Agents only check when they think it's relevant

### Option 3: Three-Tier Coordination Model

If we want maximum flexibility, provide a gradient of coordination options:

```
Least Disruptive                                Most Disruptive
      |                        |                        |
view_agent_tasks()       announce()              ask_others()
(no interrupt)      (async notification)    (synchronous interrupt)
      |                        |                        |
 "Let me check          "FYI everyone..."      "I need help with..."
  what others             [Agents see             [Agents interrupted,
  are doing"              next turn]               must respond]
```

**Tool 1: `view_agent_tasks()`** - Passive awareness (no interrupt)

**Tool 2: `announce()`** - Async FYI messages
```python
@mcp.tool()
def announce(message: str):
    """
    Send FYI announcement to other agents (non-blocking).

    Agents will see this message at the start of their next turn.
    Use for status updates that don't need immediate responses.

    Examples:
        - "I finished the OAuth implementation"
        - "Database migration complete"
    """
```

**Tool 3: `ask_others()`** - Synchronous question/help (interrupts for responses)

**System Prompt Guidance:**
```yaml
"You have three tools for coordinating with other agents:

1. **view_agent_tasks()** - See what others are working on (no interruption)
   Use when: Planning your work, checking for conflicts/overlaps

2. **announce()** - Send status update (agents see next turn)
   Use when: Completing major milestones, FYI information

3. **ask_others()** - Ask for input (interrupts for responses)
   Use when: You need help, unclear about approach, potential conflicts

Prefer less disruptive methods when possible."
```

### Recommendation

The **`ask_others()`** framing is the most important alternative to consider, as it:
1. Provides clearer guidance on when to use the tool (when you have a question)
2. Allows human participation without requiring it
3. Feels more collaborative than "broadcast"
4. Simulates the natural questioning behavior seen in models like OpenAI
5. Uses the same interrupt mechanism as `broadcast_message()`, just with better framing

The other options (read-only task visibility, announce) could be added later if needed, but `ask_others()` alone would provide significant value.

## References

- MassGen Orchestrator: `massgen/orchestrator.py`
- MassGen Agent: `massgen/agent.py`
- Existing MCP Integration: `massgen/filesystem_manager/_filesystem_manager.py`
- AsyncIO Documentation: https://docs.python.org/3/library/asyncio.html
- MCP Protocol: https://modelcontextprotocol.io/
