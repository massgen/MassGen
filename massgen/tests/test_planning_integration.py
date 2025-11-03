# -*- coding: utf-8 -*-
"""
Integration tests for planning tools.

Tests complete workflows with task plans, dependencies, and status transitions.
"""

import pytest

from massgen.mcp_tools.planning.planning_dataclasses import TaskPlan


class TestPlanningWorkflows:
    """Test complete planning workflows."""

    def test_simple_linear_workflow(self):
        """Test simple linear workflow: create plan → execute → complete."""
        plan = TaskPlan(agent_id="agent_1")

        # Create plan
        plan.add_task("Research authentication options", task_id="research")
        plan.add_task("Design auth flow", task_id="design", depends_on=["research"])
        plan.add_task("Implement auth", task_id="implement", depends_on=["design"])
        plan.add_task("Write tests", task_id="tests", depends_on=["implement"])

        # Verify initial state
        ready = plan.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "research"

        blocked = plan.get_blocked_tasks()
        assert len(blocked) == 3

        # Execute workflow
        # Step 1: Start and complete research
        plan.update_task_status("research", "in_progress")
        result = plan.update_task_status("research", "completed")

        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "design"

        # Step 2: Start and complete design
        plan.update_task_status("design", "in_progress")
        result = plan.update_task_status("design", "completed")

        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "implement"

        # Step 3: Start and complete implementation
        plan.update_task_status("implement", "in_progress")
        result = plan.update_task_status("implement", "completed")

        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "tests"

        # Step 4: Complete tests
        plan.update_task_status("tests", "in_progress")
        result = plan.update_task_status("tests", "completed")

        # All done
        assert len(result.get("newly_ready_tasks", [])) == 0
        assert len(plan.get_ready_tasks()) == 0
        assert len(plan.get_blocked_tasks()) == 0
        assert all(t.status == "completed" for t in plan.tasks)

    def test_parallel_workflow(self):
        """Test workflow with parallel tasks."""
        plan = TaskPlan(agent_id="agent_1")

        # Create plan with parallel research tasks
        plan.add_task("Research OAuth providers", task_id="research_oauth")
        plan.add_task("Research database schema", task_id="research_db")

        plan.add_task("Implement OAuth", task_id="impl_oauth", depends_on=["research_oauth"])
        plan.add_task("Implement DB models", task_id="impl_db", depends_on=["research_db"])

        plan.add_task(
            "Integration tests",
            task_id="integration",
            depends_on=["impl_oauth", "impl_db"],
        )

        # Initially, both research tasks are ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"research_oauth", "research_db"}

        # Complete first research task
        plan.update_task_status("research_oauth", "in_progress")
        result = plan.update_task_status("research_oauth", "completed")

        # impl_oauth becomes ready
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "impl_oauth"

        # research_db is still ready (pending), impl_oauth is now also ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"research_db", "impl_oauth"}

        # Complete second research task
        plan.update_task_status("research_db", "in_progress")
        result = plan.update_task_status("research_db", "completed")

        # impl_db becomes ready
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "impl_db"

        # Now both impl tasks are ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"impl_oauth", "impl_db"}

        # Complete both implementation tasks
        plan.update_task_status("impl_oauth", "in_progress")
        result = plan.update_task_status("impl_oauth", "completed")
        assert len(result.get("newly_ready_tasks", [])) == 0  # integration still blocked

        plan.update_task_status("impl_db", "in_progress")
        result = plan.update_task_status("impl_db", "completed")

        # Integration test becomes ready after both implementations complete
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "integration"

        # Complete integration
        plan.update_task_status("integration", "in_progress")
        plan.update_task_status("integration", "completed")

        # All done
        assert all(t.status == "completed" for t in plan.tasks)

    def test_dynamic_task_addition(self):
        """Test adding tasks dynamically during workflow execution."""
        plan = TaskPlan(agent_id="agent_1")

        # Initial plan
        plan.add_task("Initial task", task_id="task_1")
        plan.add_task("Dependent task", task_id="task_2", depends_on=["task_1"])

        # Start executing
        plan.update_task_status("task_1", "in_progress")

        # Discover new task needed during execution
        plan.add_task(
            "Additional task discovered",
            task_id="task_1_5",
            after_task_id="task_1",
            depends_on=["task_1"],
        )

        # Complete task_1
        result = plan.update_task_status("task_1", "completed")

        # Both task_2 and task_1_5 should become ready
        assert len(result["newly_ready_tasks"]) == 2
        newly_ready_ids = {t["id"] for t in result["newly_ready_tasks"]}
        assert newly_ready_ids == {"task_2", "task_1_5"}

        # Modify task_2 to also depend on task_1_5
        task2_obj = plan.get_task("task_2")
        task2_obj.dependencies.append("task_1_5")

        # Now task_2 should be blocked again
        assert not plan.can_start_task("task_2")
        blocked = plan.get_blocked_tasks()
        assert "task_2" in [t.id for t in blocked]

        # Complete task_1_5
        plan.update_task_status("task_1_5", "in_progress")
        result = plan.update_task_status("task_1_5", "completed")

        # task_2 becomes ready again
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "task_2"

    def test_complex_dependency_graph(self):
        """Test complex dependency graph with multiple paths."""
        plan = TaskPlan(agent_id="agent_1")

        # Create complex graph:
        #     A
        #    / \
        #   B   C
        #  / \ / \
        # D   E   F
        #  \ / \ /
        #   G   H
        #    \ /
        #     I

        plan.add_task("A", task_id="a")
        plan.add_task("B", task_id="b", depends_on=["a"])
        plan.add_task("C", task_id="c", depends_on=["a"])
        plan.add_task("D", task_id="d", depends_on=["b"])
        plan.add_task("E", task_id="e", depends_on=["b", "c"])
        plan.add_task("F", task_id="f", depends_on=["c"])
        plan.add_task("G", task_id="g", depends_on=["d", "e"])
        plan.add_task("H", task_id="h", depends_on=["e", "f"])
        plan.add_task("I", task_id="i", depends_on=["g", "h"])

        # Only A is ready initially
        ready = plan.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "a"

        # Complete A
        plan.update_task_status("a", "completed")
        ready = plan.get_ready_tasks()
        assert {t.id for t in ready} == {"b", "c"}

        # Complete B
        plan.update_task_status("b", "completed")
        ready = plan.get_ready_tasks()
        assert {t.id for t in ready} == {"c", "d"}  # C still pending, D ready

        # Complete C
        plan.update_task_status("c", "completed")
        ready = plan.get_ready_tasks()
        assert {t.id for t in ready} == {"d", "e", "f"}

        # Complete D, E, F
        plan.update_task_status("d", "completed")
        plan.update_task_status("e", "completed")
        plan.update_task_status("f", "completed")

        ready = plan.get_ready_tasks()
        assert {t.id for t in ready} == {"g", "h"}

        # Complete G and H
        plan.update_task_status("g", "completed")
        plan.update_task_status("h", "completed")

        ready = plan.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "i"

        # Complete I
        plan.update_task_status("i", "completed")

        # All done
        assert all(t.status == "completed" for t in plan.tasks)

    def test_task_editing_during_workflow(self):
        """Test editing task descriptions during workflow execution."""
        plan = TaskPlan(agent_id="agent_1")

        plan.add_task("Research OAuth", task_id="research")
        plan.add_task("Implement OAuth", task_id="impl", depends_on=["research"])

        # Start research
        plan.update_task_status("research", "in_progress")

        # Refine task description during execution
        plan.edit_task("research", "Research OAuth 2.0 providers and PKCE flow")

        updated = plan.get_task("research")
        assert updated.description == "Research OAuth 2.0 providers and PKCE flow"
        assert updated.status == "in_progress"  # Status unchanged

        # Complete research
        plan.update_task_status("research", "completed")

        # Edit implementation task before starting
        plan.edit_task("impl", "Implement OAuth 2.0 with PKCE and refresh tokens")

        updated = plan.get_task("impl")
        assert updated.description == "Implement OAuth 2.0 with PKCE and refresh tokens"

    def test_task_deletion_during_workflow(self):
        """Test deleting tasks during workflow execution."""
        plan = TaskPlan(agent_id="agent_1")

        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2")  # Independent
        plan.add_task("Task 3", task_id="task_3", depends_on=["task_1"])

        # Delete independent task
        plan.delete_task("task_2")
        assert len(plan.tasks) == 2
        assert plan.get_task("task_2") is None

        # Try to delete task_1 (should fail because task_3 depends on it)
        with pytest.raises(ValueError, match="depends on it"):
            plan.delete_task("task_1")

        # Complete task_1 first, then delete task_3
        plan.update_task_status("task_1", "completed")
        plan.delete_task("task_3")

        # Now only task_1 remains
        assert len(plan.tasks) == 1
        assert plan.tasks[0].id == "task_1"

    def test_mixed_dependency_format_workflow(self):
        """Test workflow using mixed dependency reference formats."""
        from massgen.mcp_tools.planning._planning_mcp_server import (
            _resolve_dependency_references,
        )

        # Simulate create_task_plan with mixed format
        task_specs = [
            {"id": "research_oauth", "description": "Research OAuth"},
            {"id": "research_db", "description": "Research DB"},
            {"description": "Design", "depends_on": [0, 1]},  # Index-based
            {
                "id": "impl_oauth",
                "description": "Implement OAuth",
                "depends_on": ["research_oauth"],  # ID-based
            },
            {
                "id": "impl_db",
                "description": "Implement DB",
                "depends_on": ["research_db"],  # ID-based
            },
            {
                "description": "Integration",
                "depends_on": [3, 4],  # Index-based to impl tasks
            },
        ]

        # Resolve dependencies
        resolved = _resolve_dependency_references(task_specs)

        # Create plan with resolved tasks
        plan = TaskPlan(agent_id="agent_1")
        for task_spec in resolved:
            plan.add_task(
                task_spec["description"],
                task_id=task_spec["id"],
                depends_on=task_spec["depends_on"],
            )

        # Verify structure
        assert len(plan.tasks) == 6

        # Research tasks should be ready
        ready = plan.get_ready_tasks()
        assert len(ready) == 2
        assert {t.id for t in ready} == {"research_oauth", "research_db"}

        # Design task should depend on both research tasks
        design_task = plan.tasks[2]
        assert set(design_task.dependencies) == {"research_oauth", "research_db"}

        # Integration task should depend on impl tasks
        integration_task = plan.tasks[5]
        assert set(integration_task.dependencies) == {"impl_oauth", "impl_db"}

    def test_workflow_with_blocked_status(self):
        """Test workflow using 'blocked' status for tasks waiting on external factors."""
        plan = TaskPlan(agent_id="agent_1")

        plan.add_task("Setup environment", task_id="setup")
        plan.add_task("Deploy to staging", task_id="deploy", depends_on=["setup"])
        plan.add_task("Run smoke tests", task_id="tests", depends_on=["deploy"])

        # Complete setup
        plan.update_task_status("setup", "completed")

        # Start deployment
        plan.update_task_status("deploy", "in_progress")

        # Deployment hits issue, mark as blocked
        plan.update_task_status("deploy", "blocked")

        # Tests should still be considered blocked (dependency not completed)
        blocked = plan.get_blocked_tasks()
        assert "tests" in [t.id for t in blocked]

        # Resolve deployment issue, resume
        plan.update_task_status("deploy", "in_progress")
        result = plan.update_task_status("deploy", "completed")

        # Tests become ready
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "tests"

    def test_serialization_during_workflow(self):
        """Test that plans can be serialized and restored during workflow execution."""
        plan = TaskPlan(agent_id="agent_1")

        plan.add_task("Task 1", task_id="task_1")
        plan.add_task("Task 2", task_id="task_2", depends_on=["task_1"])

        # Start task 1
        plan.update_task_status("task_1", "in_progress")

        # Serialize
        plan_dict = plan.to_dict()

        # Restore
        restored = TaskPlan.from_dict(plan_dict)

        # Verify state is preserved
        assert len(restored.tasks) == 2
        task1_restored = restored.get_task("task_1")
        assert task1_restored.status == "in_progress"

        # Continue workflow on restored plan
        result = restored.update_task_status("task_1", "completed")
        assert len(result["newly_ready_tasks"]) == 1
        assert result["newly_ready_tasks"][0]["id"] == "task_2"
