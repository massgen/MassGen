# -*- coding: utf-8 -*-
"""
Comprehensive unit tests for planning tools.

Tests Task and TaskPlan dataclasses, dependency management,
and all MCP server operations.
"""

from datetime import datetime

import pytest

from massgen.tools.planning_dataclasses import Task, TaskPlan


class TestTask:
    """Test Task dataclass."""

    def test_task_creation(self):
        """Test basic task creation."""
        task = Task(
            id="test_task",
            description="Test task description",
            status="pending",
        )

        assert task.id == "test_task"
        assert task.description == "Test task description"
        assert task.status == "pending"
        assert task.dependencies == []
        assert task.completed_at is None
        assert isinstance(task.created_at, datetime)

    def test_task_with_dependencies(self):
        """Test task creation with dependencies."""
        task = Task(
            id="task_2",
            description="Task with dependencies",
            dependencies=["task_1"],
        )

        assert task.dependencies == ["task_1"]

    def test_task_serialization(self):
        """Test task to_dict and from_dict."""
        original = Task(
            id="task_1",
            description="Test task",
            status="in_progress",
            dependencies=["task_0"],
            metadata={"priority": "high"},
        )

        # Serialize
        task_dict = original.to_dict()
        assert task_dict["id"] == "task_1"
        assert task_dict["description"] == "Test task"
        assert task_dict["status"] == "in_progress"
        assert task_dict["dependencies"] == ["task_0"]
        assert task_dict["metadata"]["priority"] == "high"

        # Deserialize
        restored = Task.from_dict(task_dict)
        assert restored.id == original.id
        assert restored.description == original.description
        assert restored.status == original.status
        assert restored.dependencies == original.dependencies
        assert restored.metadata == original.metadata


class TestTaskPlan:
    """Test TaskPlan dataclass."""

    def test_plan_creation(self):
        """Test basic plan creation."""
        plan = TaskPlan(agent_id="agent_1")

        assert plan.agent_id == "agent_1"
        assert len(plan.tasks) == 0
        assert isinstance(plan.created_at, datetime)
        assert isinstance(plan.updated_at, datetime)

    def test_add_task_simple(self):
        """Test adding a simple task."""
        plan = TaskPlan(agent_id="agent_1")
        task = plan.add_task("Task 1")

        assert len(plan.tasks) == 1
        assert task.description == "Task 1"
        assert task.id in plan._task_index

    def test_add_task_with_dependencies(self):
        """Test adding tasks with dependencies."""
        plan = TaskPlan(agent_id="agent_1")

        plan.add_task("Task 1", task_id="task_1")
        task2 = plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        assert task2.dependencies == ["task_1"]
        assert len(plan.tasks) == 2

    def test_add_task_invalid_dependency(self):
        """Test that adding task with invalid dependency raises error."""
        plan = TaskPlan(agent_id="agent_1")

        with pytest.raises(ValueError, match="Dependency task does not exist"):
            plan.add_task("Task 1", depends_on=["nonexistent"])

    def test_add_task_duplicate_id(self):
        """Test that adding task with duplicate ID raises error."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")

        with pytest.raises(ValueError, match="Task ID already exists"):
            plan.add_task("Task 2", task_id="task_1")

    def test_get_task(self):
        """Test getting a task by ID."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")

        retrieved = plan.get_task("task_1")
        assert retrieved is not None
        assert retrieved.id == "task_1"
        assert retrieved.description == "Task 1"

        # Non-existent task
        assert plan.get_task("nonexistent") is None

    def test_can_start_task_no_dependencies(self):
        """Test can_start_task for task with no dependencies."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")

        assert plan.can_start_task("task_1") is True

    def test_can_start_task_with_completed_dependencies(self):
        """Test can_start_task when dependencies are completed."""
        plan = TaskPlan(agent_id="agent_1")
        task1 = plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        # Initially task2 cannot start
        assert plan.can_start_task("task_2") is False

        # Complete task1
        task1.status = "completed"
        assert plan.can_start_task("task_2") is True

    def test_can_start_task_with_incomplete_dependencies(self):
        """Test can_start_task when dependencies are incomplete."""
        plan = TaskPlan(agent_id="agent_1")
        task1 = plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        # task1 is pending, so task2 cannot start
        assert plan.can_start_task("task_2") is False

        # Even if task1 is in progress, task2 still cannot start
        task1.status = "in_progress"
        assert plan.can_start_task("task_2") is False

    def test_get_ready_tasks(self):
        """Test getting ready tasks."""
        plan = TaskPlan(agent_id="agent_1")
        task1 = plan.add_task("Task 1", task_id="task_1")
        task2 = plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])
        task3 = plan.add_task("Task 3", task_id="task_3")

        # Initially, tasks 1 and 3 are ready (no dependencies)
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"task_1", "task_3"}

        # Complete task1
        task1.status = "completed"
        ready = plan.get_ready_tasks()
        assert len(ready) == 2  # Both task2 (now unblocked) and task3 are ready
        assert {t.id for t in ready} == {"task_2", "task_3"}

        # Mark task2 and task3 as in_progress
        task2.status = "in_progress"
        task3.status = "in_progress"
        ready = plan.get_ready_tasks()
        assert len(ready) == 0  # No pending tasks with satisfied dependencies

    def test_get_blocked_tasks(self):
        """Test getting blocked tasks."""
        plan = TaskPlan(agent_id="agent_1")
        task1 = plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])
        plan.add_task("Task 3", task_id="task_3")

        # Initially, task2 is blocked
        blocked = plan.get_blocked_tasks()
        assert len(blocked) == 1
        assert blocked[0].id == "task_2"

        # Complete task1
        task1.status = "completed"
        blocked = plan.get_blocked_tasks()
        assert len(blocked) == 0

    def test_get_blocking_tasks(self):
        """Test getting list of tasks blocking a task."""
        plan = TaskPlan(agent_id="agent_1")
        task1 = plan.add_task("Task 1", task_id="task_1")
        task2 = plan.add_task("Task 2", task_id="task_2")
        plan.add_task("Task 3", task_id="task_3", depends_on=["task_1", "task_2"])

        # task3 is blocked by both task1 and task2
        blocking = plan.get_blocking_tasks("task_3")
        assert set(blocking) == {"task_1", "task_2"}

        # Complete task1
        task1.status = "completed"
        blocking = plan.get_blocking_tasks("task_3")
        assert blocking == ["task_2"]

        # Complete task2
        task2.status = "completed"
        blocking = plan.get_blocking_tasks("task_3")
        assert blocking == []

    def test_update_task_status(self):
        """Test updating task status."""
        plan = TaskPlan(agent_id="agent_1")
        task = plan.add_task("Task 1", task_id="task_1")

        result = plan.update_task_status("task_1", "in_progress")
        assert task.status == "in_progress"
        assert "task" in result

    def test_update_task_status_to_completed(self):
        """Test updating task status to completed."""
        plan = TaskPlan(agent_id="agent_1")
        task = plan.add_task("Task 1", task_id="task_1")

        plan.update_task_status("task_1", "completed")
        assert task.status == "completed"
        assert task.completed_at is not None

    def test_update_task_status_unblocks_dependent_tasks(self):
        """Test that completing a task identifies newly ready tasks."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        result = plan.update_task_status("task_1", "completed")

        assert "newly_ready_tasks" in result
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "task_2"

    def test_update_task_status_nonexistent_task(self):
        """Test updating nonexistent task raises error."""
        plan = TaskPlan(agent_id="agent_1")

        with pytest.raises(ValueError, match="Task not found"):
            plan.update_task_status("nonexistent", "completed")

    def test_edit_task(self):
        """Test editing task description."""
        plan = TaskPlan(agent_id="agent_1")
        task = plan.add_task("Old description", task_id="task_1")

        updated = plan.edit_task("task_1", "New description")
        assert updated.description == "New description"
        assert task.description == "New description"

    def test_edit_task_nonexistent(self):
        """Test editing nonexistent task raises error."""
        plan = TaskPlan(agent_id="agent_1")

        with pytest.raises(ValueError, match="Task not found"):
            plan.edit_task("nonexistent", "New description")

    def test_delete_task(self):
        """Test deleting a task."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")

        plan.delete_task("task_1")
        assert len(plan.tasks) == 0
        assert "task_1" not in plan._task_index

    def test_delete_task_with_dependents(self):
        """Test that deleting a task with dependents raises error."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        with pytest.raises(ValueError, match="depends on it"):
            plan.delete_task("task_1")

    def test_delete_task_nonexistent(self):
        """Test deleting nonexistent task raises error."""
        plan = TaskPlan(agent_id="agent_1")

        with pytest.raises(ValueError, match="Task not found"):
            plan.delete_task("nonexistent")

    def test_validate_dependencies_simple(self):
        """Test validating simple dependencies."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            {"id": "task_1", "description": "Task 1"},
            {"id": "task_2", "description": "Task 2", "depends_on": ["task_1"]},
        ]

        # Should not raise
        plan.validate_dependencies(task_list)

    def test_validate_dependencies_index_based(self):
        """Test validating index-based dependencies."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            "Task 1",
            {"description": "Task 2", "depends_on": [0]},
        ]

        # Should not raise
        plan.validate_dependencies(task_list)

    def test_validate_dependencies_invalid_index(self):
        """Test that invalid index raises error."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            "Task 1",
            {"description": "Task 2", "depends_on": [5]},
        ]

        with pytest.raises(ValueError, match="Invalid dependency index"):
            plan.validate_dependencies(task_list)

    def test_validate_dependencies_forward_reference(self):
        """Test that forward reference raises error."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            {"description": "Task 1", "depends_on": [1]},
            "Task 2",
        ]

        with pytest.raises(ValueError, match="must reference earlier tasks"):
            plan.validate_dependencies(task_list)

    def test_validate_dependencies_self_reference(self):
        """Test that self-reference raises error."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            {"id": "task_1", "description": "Task 1", "depends_on": ["task_1"]},
        ]

        with pytest.raises(ValueError, match="Self-dependency detected"):
            plan.validate_dependencies(task_list)

    def test_validate_dependencies_nonexistent_id(self):
        """Test that nonexistent dependency ID raises error."""
        plan = TaskPlan(agent_id="agent_1")

        task_list = [
            {"id": "task_1", "description": "Task 1", "depends_on": ["nonexistent"]},
        ]

        with pytest.raises(ValueError, match="not found in task list"):
            plan.validate_dependencies(task_list)

    def test_circular_dependency_detection(self):
        """Test circular dependency detection."""
        plan = TaskPlan(agent_id="agent_1")

        # Create tasks that would form a cycle
        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        # Try to add task3 that depends on task2, then modify task1 to depend on task3
        # This should be caught by validation
        task3_data = {
            "id": "task_3",
            "description": "Task 3",
            "depends_on": ["task_2"],
        }

        # Add task3
        plan.add_task(task3_data["description"], task_id="task_3", depends_on=["task_2"])

        # Now try to make task1 depend on task3 (would create cycle)
        # This is done by trying to add a task with circular dependency
        with pytest.raises(ValueError):
            # Manually create circular dependency in new plan to test detection
            plan2 = TaskPlan(agent_id="agent_2")
            t1 = plan2.add_task("T1", task_id="t1")
            plan2.add_task("T2", task_id="t2", depends_on=["t1"])
            # Manually modify to create cycle
            t1.dependencies = ["t2"]
            # Try to add another task - this should trigger validation
            plan2.add_task("T3", task_id="t3", depends_on=["t2"])

    def test_plan_serialization(self):
        """Test plan to_dict and from_dict."""
        plan = TaskPlan(agent_id="agent_1")
        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        # Serialize
        plan_dict = plan.to_dict()
        assert plan_dict["agent_id"] == "agent_1"
        assert len(plan_dict["tasks"]) == 2

        # Deserialize
        restored = TaskPlan.from_dict(plan_dict)
        assert restored.agent_id == plan.agent_id
        assert len(restored.tasks) == 2
        assert restored.tasks[0].id == "task_1"
        assert restored.tasks[1].id == "task_2"
        assert restored.tasks[1].dependencies == ["task_1"]


class TestTaskPlanComplexScenarios:
    """Test complex task plan scenarios."""

    def test_parallel_tasks(self):
        """Test identifying parallel tasks."""
        plan = TaskPlan(agent_id="agent_1")

        # Two independent research tasks
        plan.add_task("Research OAuth", task_id="research_oauth")
        plan.add_task("Research DB schema", task_id="research_db")

        # Two implementation tasks depending on research
        plan.add_task("Implement OAuth", task_id="impl_oauth", depends_on=["research_oauth"])
        plan.add_task("Implement DB", task_id="impl_db", depends_on=["research_db"])

        # Integration test depending on both implementations
        plan.add_task(
            "Integration tests",
            task_id="integration",
            depends_on=["impl_oauth", "impl_db"],
        )

        # Initially, both research tasks are ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"research_oauth", "research_db"}

        # Complete both research tasks
        plan.update_task_status("research_oauth", "completed")
        plan.update_task_status("research_db", "completed")

        # Now both implementation tasks are ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"impl_oauth", "impl_db"}

        # Complete both implementations
        plan.update_task_status("impl_oauth", "completed")
        result = plan.update_task_status("impl_db", "completed")

        # Integration test should now be ready
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "integration"

    def test_diamond_dependency(self):
        """Test diamond dependency pattern."""
        plan = TaskPlan(agent_id="agent_1")

        # Diamond pattern: A -> B, A -> C, B -> D, C -> D
        plan.add_task("Task A", task_id="a")
        plan.add_task("Task B", task_id="b", depends_on=["a"])
        plan.add_task("Task C", task_id="c", depends_on=["a"])
        plan.add_task("Task D", task_id="d", depends_on=["b", "c"])

        # Initially, only A is ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "a"

        # Complete A
        result = plan.update_task_status("a", "completed")
        assert len(result["newly_ready_tasks"]) == 2
        assert {t["id"] for t in result["newly_ready_tasks"]} == {"b", "c"}

        # Complete B
        result = plan.update_task_status("b", "completed")
        assert len(result["newly_ready_tasks"]) == 0  # D still waiting on C

        # Complete C
        result = plan.update_task_status("c", "completed")
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "d"

    def test_long_chain(self):
        """Test long dependency chain."""
        plan = TaskPlan(agent_id="agent_1")

        # Create chain: task1 -> task2 -> task3 -> task4 -> task5
        prev_id = None
        for i in range(1, 6):
            task_id = f"task_{i}"
            depends_on = [prev_id] if prev_id else []
            plan.add_task(f"Task {i}", task_id=task_id, depends_on=depends_on)
            prev_id = task_id

        # Only first task should be ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_1"

        # Complete tasks in order
        for i in range(1, 6):
            task_id = f"task_{i}"
            plan.update_task_status(task_id, "completed")

            if i < 5:
                # Next task should become ready
                ready = plan.get_ready_tasks()
                assert len(ready) == 1
                assert ready[0].id == f"task_{i+1}"


class TestMCPServerIntegration:
    """Test MCP server tool functions (integration with dataclasses)."""

    def test_create_task_plan_simple(self):
        """Test creating a simple task plan via MCP."""
        from massgen.tools._planning_mcp_server import _resolve_dependency_references

        # Test simple task list
        tasks = ["Task 1", "Task 2", "Task 3"]
        resolved = _resolve_dependency_references(tasks)

        assert len(resolved) == 3
        for i, task in enumerate(resolved):
            assert "id" in task
            assert "description" in task
            assert task["description"] == f"Task {i+1}"
            assert task["depends_on"] == []

    def test_resolve_dependency_references_index_based(self):
        """Test resolving index-based dependency references."""
        from massgen.tools._planning_mcp_server import _resolve_dependency_references

        tasks = [
            "Task 1",
            {"description": "Task 2", "depends_on": [0]},
            {"description": "Task 3", "depends_on": [0, 1]},
        ]

        resolved = _resolve_dependency_references(tasks)
        assert len(resolved) == 3

        # Task 2 depends on Task 1 (by resolved ID)
        assert len(resolved[1]["depends_on"]) == 1
        assert resolved[1]["depends_on"][0] == resolved[0]["id"]

        # Task 3 depends on Task 1 and Task 2 (by resolved IDs)
        assert len(resolved[2]["depends_on"]) == 2
        assert resolved[2]["depends_on"][0] == resolved[0]["id"]
        assert resolved[2]["depends_on"][1] == resolved[1]["id"]

    def test_resolve_dependency_references_mixed(self):
        """Test resolving mixed dependency references (index and ID)."""
        from massgen.tools._planning_mcp_server import _resolve_dependency_references

        tasks = [
            {"id": "research", "description": "Research task"},
            {"description": "Design task", "depends_on": [0]},  # Index-based
            {"id": "implement", "description": "Implement", "depends_on": ["research"]},  # ID-based
            {"description": "Test", "depends_on": [2, "research"]},  # Mixed
        ]

        resolved = _resolve_dependency_references(tasks)
        assert len(resolved) == 4

        # Check that all dependencies are resolved to IDs
        assert resolved[1]["depends_on"] == ["research"]
        assert resolved[2]["depends_on"] == ["research"]
        assert "research" in resolved[3]["depends_on"]
        assert "implement" in resolved[3]["depends_on"]

    def test_resolve_dependency_references_invalid_index(self):
        """Test that invalid index raises error."""
        from massgen.tools._planning_mcp_server import _resolve_dependency_references

        tasks = [
            "Task 1",
            {"description": "Task 2", "depends_on": [5]},
        ]

        with pytest.raises(ValueError, match="Invalid dependency index"):
            _resolve_dependency_references(tasks)

    def test_resolve_dependency_references_forward_reference(self):
        """Test that forward index reference raises error."""
        from massgen.tools._planning_mcp_server import _resolve_dependency_references

        tasks = [
            {"description": "Task 1", "depends_on": [1]},
            "Task 2",
        ]

        with pytest.raises(ValueError, match="must reference earlier tasks"):
            _resolve_dependency_references(tasks)
