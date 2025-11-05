# -*- coding: utf-8 -*-
"""
Task Planning Data Structures for MassGen

Provides dataclasses for managing agent task plans with dependency tracking,
status management, and validation.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional


@dataclass
class Task:
    """
    Represents a single task in an agent's plan.

    Attributes:
        id: Unique task identifier (UUID or custom string)
        description: Human-readable task description
        status: Current task status (pending/in_progress/completed/blocked)
        created_at: Timestamp when task was created
        completed_at: Timestamp when task was completed (if applicable)
        dependencies: List of task IDs this task depends on
        metadata: Additional task-specific metadata
    """

    id: str
    description: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dependencies": self.dependencies.copy(),
            "metadata": self.metadata.copy(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create task from dictionary."""
        return cls(
            id=data["id"],
            description=data["description"],
            status=data["status"],
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            dependencies=data.get("dependencies", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskPlan:
    """
    Manages an agent's task plan with dependency tracking.

    Attributes:
        agent_id: ID of the agent who owns this plan
        tasks: List of tasks in the plan
        created_at: Timestamp when plan was created
        updated_at: Timestamp when plan was last updated
    """

    agent_id: str
    tasks: List[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize task index for fast lookups."""
        self._task_index: Dict[str, Task] = {task.id: task for task in self.tasks}

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task if found, None otherwise
        """
        return self._task_index.get(task_id)

    def can_start_task(self, task_id: str) -> bool:
        """
        Check if a task can be started (all dependencies completed).

        Args:
            task_id: Task to check

        Returns:
            True if all dependencies are completed, False otherwise
        """
        task = self.get_task(task_id)
        if not task:
            return False

        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if not dep_task or dep_task.status != "completed":
                return False

        return True

    def get_ready_tasks(self) -> List[Task]:
        """
        Get all tasks ready to start (pending with satisfied dependencies).

        Returns:
            List of tasks with status='pending' and all dependencies completed
        """
        return [task for task in self.tasks if task.status == "pending" and self.can_start_task(task.id)]

    def get_blocked_tasks(self) -> List[Task]:
        """
        Get all tasks blocked by dependencies.

        Returns:
            List of tasks with status='pending' but dependencies not completed,
            including information about what each task is waiting on
        """
        blocked = []
        for task in self.tasks:
            if task.status == "pending" and not self.can_start_task(task.id):
                blocked.append(task)
        return blocked

    def get_blocking_tasks(self, task_id: str) -> List[str]:
        """
        Get list of incomplete dependency task IDs blocking a task.

        Args:
            task_id: Task to check

        Returns:
            List of task IDs that are blocking this task
        """
        task = self.get_task(task_id)
        if not task:
            return []

        blocking = []
        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if dep_task and dep_task.status != "completed":
                blocking.append(dep_id)

        return blocking

    def add_task(
        self,
        description: str,
        task_id: Optional[str] = None,
        after_task_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ) -> Task:
        """
        Add a new task to the plan.

        Args:
            description: Task description
            task_id: Optional custom task ID (generates UUID if not provided)
            after_task_id: Optional ID to insert after (otherwise appends)
            depends_on: Optional list of task IDs this task depends on

        Returns:
            The newly created task

        Raises:
            ValueError: If dependencies are invalid or circular
        """
        # Generate ID if not provided
        if not task_id:
            task_id = str(uuid.uuid4())

        # Validate task ID is unique
        if task_id in self._task_index:
            raise ValueError(f"Task ID already exists: {task_id}")

        # Validate dependencies exist
        if depends_on:
            for dep_id in depends_on:
                if dep_id not in self._task_index:
                    raise ValueError(f"Dependency task does not exist: {dep_id}")

        # Create task
        task = Task(
            id=task_id,
            description=description,
            dependencies=depends_on or [],
        )

        # Check for circular dependencies before adding
        temp_tasks = self.tasks + [task]
        if self._has_circular_dependency(task_id, temp_tasks):
            raise ValueError(f"Circular dependency detected for task: {task_id}")

        # Add to plan
        if after_task_id:
            # Find position and insert
            for i, t in enumerate(self.tasks):
                if t.id == after_task_id:
                    self.tasks.insert(i + 1, task)
                    break
            else:
                raise ValueError(f"after_task_id not found: {after_task_id}")
        else:
            # Append to end
            self.tasks.append(task)

        # Update index and timestamp
        self._task_index[task_id] = task
        self.updated_at = datetime.now()

        return task

    def update_task_status(
        self,
        task_id: str,
        status: Literal["pending", "in_progress", "completed", "blocked"],
    ) -> Dict[str, Any]:
        """
        Update task status and detect newly unblocked tasks.

        Args:
            task_id: ID of task to update
            status: New status

        Returns:
            Dictionary with updated task and newly_ready_tasks

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.status = status
        self.updated_at = datetime.now()

        if status == "completed":
            task.completed_at = datetime.now()

            # Find newly ready tasks
            newly_ready = []
            for other_task in self.tasks:
                if other_task.status == "pending" and task_id in other_task.dependencies and self.can_start_task(other_task.id):
                    newly_ready.append(other_task)

            return {
                "task": task.to_dict(),
                "newly_ready_tasks": [t.to_dict() for t in newly_ready],
            }

        return {"task": task.to_dict()}

    def edit_task(self, task_id: str, description: Optional[str] = None) -> Task:
        """
        Edit a task's description.

        Args:
            task_id: ID of task to edit
            description: New description (if provided)

        Returns:
            Updated task

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if description is not None:
            task.description = description

        self.updated_at = datetime.now()
        return task

    def delete_task(self, task_id: str) -> None:
        """
        Remove a task from the plan.

        Args:
            task_id: ID of task to delete

        Raises:
            ValueError: If task not found or other tasks depend on it
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Check if any tasks depend on this one
        for other_task in self.tasks:
            if task_id in other_task.dependencies:
                raise ValueError(
                    f"Cannot delete task {task_id}: task {other_task.id} depends on it",
                )

        # Remove from list and index
        self.tasks.remove(task)
        del self._task_index[task_id]
        self.updated_at = datetime.now()

    def validate_dependencies(self, task_list: List[Dict[str, Any]]) -> None:
        """
        Validate dependencies when creating a task plan.

        Checks:
        - Dependencies reference valid tasks (earlier in list or by valid ID)
        - No circular dependencies
        - No self-references

        Args:
            task_list: List of task dictionaries with potential dependencies

        Raises:
            ValueError: If validation fails
        """
        # Build ID mapping
        task_ids = set()
        for i, task_spec in enumerate(task_list):
            if isinstance(task_spec, dict) and "id" in task_spec:
                task_id = task_spec["id"]
            else:
                task_id = f"task_{i}"
            task_ids.add(task_id)

        # Validate each task's dependencies
        for i, task_spec in enumerate(task_list):
            if isinstance(task_spec, dict):
                task_id = task_spec.get("id", f"task_{i}")
                depends_on = task_spec.get("depends_on", [])

                if depends_on:
                    for dep in depends_on:
                        # Handle index-based dependency
                        if isinstance(dep, int):
                            if dep < 0 or dep >= len(task_list):
                                raise ValueError(
                                    f"Task {task_id}: Invalid dependency index {dep}",
                                )
                            if dep >= i:
                                raise ValueError(
                                    f"Task {task_id}: Dependencies must reference earlier tasks (index {dep} >= {i})",
                                )
                        # Handle ID-based dependency
                        else:
                            if dep not in task_ids:
                                raise ValueError(
                                    f"Task {task_id}: Dependency {dep} not found in task list",
                                )
                            if dep == task_id:
                                raise ValueError(
                                    f"Task {task_id}: Self-dependency detected",
                                )

    def _has_circular_dependency(self, task_id: str, all_tasks: List[Task]) -> bool:
        """
        Check if adding a task would create a circular dependency.

        Args:
            task_id: ID of task to check
            all_tasks: All tasks including the new one

        Returns:
            True if circular dependency detected, False otherwise
        """
        # Build dependency graph
        task_map = {t.id: t for t in all_tasks}

        # DFS to detect cycles
        visited = set()
        rec_stack = set()

        def has_cycle(tid: str) -> bool:
            if tid in rec_stack:
                return True
            if tid in visited:
                return False

            visited.add(tid)
            rec_stack.add(tid)

            task = task_map.get(tid)
            if task:
                for dep_id in task.dependencies:
                    if has_cycle(dep_id):
                        return True

            rec_stack.remove(tid)
            return False

        return has_cycle(task_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "tasks": [task.to_dict() for task in self.tasks],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPlan":
        """Create plan from dictionary."""
        tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
        plan = cls(
            agent_id=data["agent_id"],
            tasks=tasks,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
        return plan
