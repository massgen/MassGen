#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Planning MCP Server for MassGen

This MCP server provides task planning and management tools for agents,
enabling them to create, track, and manage task plans with dependencies.

Tools provided:
- create_task_plan: Create a new task plan with dependencies
- add_task: Add a new task to the plan
- update_task_status: Update task status and detect newly ready tasks
- edit_task: Edit a task's description
- get_task_plan: Get the complete current task plan
- delete_task: Remove a task from the plan
- get_ready_tasks: Get tasks ready to start (dependencies satisfied)
- get_blocked_tasks: Get tasks blocked by dependencies
"""

import argparse
import uuid
from typing import Any, Dict, List, Optional, Union

import fastmcp

from massgen.mcp_tools.planning.planning_dataclasses import TaskPlan

# Global storage for task plans (keyed by agent_id)
_task_plans: Dict[str, TaskPlan] = {}


def _get_or_create_plan(agent_id: str, orchestrator_id: str) -> TaskPlan:
    """
    Get existing plan or create new one for agent.

    Args:
        agent_id: Agent identifier
        orchestrator_id: Orchestrator identifier

    Returns:
        TaskPlan for the agent
    """
    key = f"{orchestrator_id}:{agent_id}"
    if key not in _task_plans:
        _task_plans[key] = TaskPlan(agent_id=key)
    return _task_plans[key]


def _resolve_dependency_references(
    task_list: List[Union[str, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Resolve dependency references (indices -> IDs) in task list.

    Args:
        task_list: List of task specifications

    Returns:
        List of normalized task dictionaries with resolved dependencies

    Raises:
        ValueError: If dependencies are invalid
    """
    # First pass: Generate IDs for all tasks
    normalized_tasks = []
    for i, task_spec in enumerate(task_list):
        if isinstance(task_spec, str):
            # Simple string task
            task_dict = {
                "id": f"task_{i}_{uuid.uuid4().hex[:8]}",
                "description": task_spec,
                "depends_on": [],
            }
        elif isinstance(task_spec, dict):
            # Dictionary task
            task_dict = task_spec.copy()
            if "id" not in task_dict:
                task_dict["id"] = f"task_{i}_{uuid.uuid4().hex[:8]}"
            if "depends_on" not in task_dict:
                task_dict["depends_on"] = []
        else:
            raise ValueError(f"Invalid task specification at index {i}: {task_spec}")

        normalized_tasks.append(task_dict)

    # Second pass: Resolve index-based dependencies to IDs
    for i, task_dict in enumerate(normalized_tasks):
        resolved_deps = []
        for dep in task_dict.get("depends_on", []):
            if isinstance(dep, int):
                # Index-based reference
                if dep < 0 or dep >= len(normalized_tasks):
                    raise ValueError(
                        f"Task '{task_dict['id']}': Invalid dependency index {dep}",
                    )
                if dep >= i:
                    raise ValueError(
                        f"Task '{task_dict['id']}': Dependencies must reference earlier tasks",
                    )
                resolved_deps.append(normalized_tasks[dep]["id"])
            else:
                # ID-based reference
                resolved_deps.append(dep)

        task_dict["depends_on"] = resolved_deps

    return normalized_tasks


async def create_server() -> fastmcp.FastMCP:
    """Factory function to create and configure the planning MCP server."""

    parser = argparse.ArgumentParser(description="Planning MCP Server")
    parser.add_argument(
        "--agent-id",
        type=str,
        required=True,
        help="ID of the agent using this planning server",
    )
    parser.add_argument(
        "--orchestrator-id",
        type=str,
        required=True,
        help="ID of the orchestrator managing this agent",
    )
    args = parser.parse_args()

    # Create the FastMCP server
    mcp = fastmcp.FastMCP("Agent Task Planning")

    # Store agent and orchestrator IDs
    mcp.agent_id = args.agent_id
    mcp.orchestrator_id = args.orchestrator_id

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
                    "id": "implement_oauth",
                    "description": "Implement OAuth endpoints",
                    "depends_on": ["research_oauth"]
                },
                {
                    "id": "integration_tests",
                    "description": "Run integration tests",
                    "depends_on": ["implement_oauth"]
                }
            ])

        Dependency Rules:
            - Can reference by index (0-based) or by custom task ID
            - Dependencies must reference earlier tasks in the list
            - Circular dependencies are rejected
            - Tasks with no dependencies can start immediately
            - Tasks with dependencies wait until all deps are completed
        """
        try:
            # Get or create plan for this agent
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)

            # Clear existing tasks (creating new plan)
            plan.tasks.clear()
            plan._task_index.clear()

            # Validate and resolve dependencies
            normalized_tasks = _resolve_dependency_references(tasks)
            plan.validate_dependencies(normalized_tasks)

            # Create tasks
            created_tasks = []
            for task_spec in normalized_tasks:
                task = plan.add_task(
                    description=task_spec["description"],
                    task_id=task_spec["id"],
                    depends_on=task_spec.get("depends_on", []),
                )
                created_tasks.append(task.to_dict())

            return {
                "success": True,
                "operation": "create_task_plan",
                "plan_id": plan.agent_id,
                "tasks": created_tasks,
                "summary": {
                    "total_tasks": len(created_tasks),
                    "ready_tasks": len(plan.get_ready_tasks()),
                    "blocked_tasks": len(plan.get_blocked_tasks()),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "create_task_plan",
                "error": str(e),
            }

    @mcp.tool()
    def add_task(
        description: str,
        after_task_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
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
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)

            task = plan.add_task(
                description=description,
                after_task_id=after_task_id,
                depends_on=depends_on or [],
            )

            return {
                "success": True,
                "operation": "add_task",
                "task": task.to_dict(),
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "add_task",
                "error": str(e),
            }

    @mcp.tool()
    def update_task_status(
        task_id: str,
        status: str,  # Will be validated as Literal in the function
    ) -> Dict[str, Any]:
        """
        Update the status of a task.

        Args:
            task_id: ID of task to update
            status: New status (pending/in_progress/completed/blocked)

        Returns:
            Dictionary with updated task details and newly ready tasks

        Example:
            update_task_status("research_oauth", "completed")
        """
        try:
            # Validate status
            valid_statuses = ["pending", "in_progress", "completed", "blocked"]
            if status not in valid_statuses:
                raise ValueError(
                    f"Invalid status '{status}'. Must be one of: {valid_statuses}",
                )

            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)
            result = plan.update_task_status(task_id, status)

            return {
                "success": True,
                "operation": "update_task_status",
                **result,
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "update_task_status",
                "error": str(e),
            }

    @mcp.tool()
    def edit_task(
        task_id: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Edit a task's description.

        Args:
            task_id: ID of task to edit
            description: New description (if provided)

        Returns:
            Dictionary with updated task details

        Example:
            edit_task("research_oauth", "Research OAuth 2.0 providers and best practices")
        """
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)
            task = plan.edit_task(task_id, description)

            return {
                "success": True,
                "operation": "edit_task",
                "task": task.to_dict(),
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "edit_task",
                "error": str(e),
            }

    @mcp.tool()
    def get_task_plan() -> Dict[str, Any]:
        """
        Get the current task plan for this agent.

        Returns:
            Dictionary with complete task plan including all tasks and their statuses

        Example:
            plan = get_task_plan()
            print(f"Total tasks: {plan['summary']['total_tasks']}")
            print(f"Ready tasks: {plan['summary']['ready_tasks']}")
        """
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)

            ready_tasks = plan.get_ready_tasks()
            blocked_tasks = plan.get_blocked_tasks()

            return {
                "success": True,
                "operation": "get_task_plan",
                "plan": plan.to_dict(),
                "summary": {
                    "total_tasks": len(plan.tasks),
                    "completed_tasks": sum(1 for t in plan.tasks if t.status == "completed"),
                    "in_progress_tasks": sum(1 for t in plan.tasks if t.status == "in_progress"),
                    "ready_tasks": len(ready_tasks),
                    "blocked_tasks": len(blocked_tasks),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "get_task_plan",
                "error": str(e),
            }

    @mcp.tool()
    def delete_task(task_id: str) -> Dict[str, Any]:
        """
        Remove a task from the plan.

        Args:
            task_id: ID of task to delete

        Returns:
            Success confirmation

        Raises:
            Error if other tasks depend on this task

        Example:
            delete_task("obsolete_task_id")
        """
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)
            plan.delete_task(task_id)

            return {
                "success": True,
                "operation": "delete_task",
                "deleted_task_id": task_id,
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "delete_task",
                "error": str(e),
            }

    @mcp.tool()
    def get_ready_tasks() -> Dict[str, Any]:
        """
        Get all tasks that are ready to start (dependencies satisfied).

        Returns:
            Dictionary with list of tasks that have status='pending' and all
            dependencies completed

        Use cases:
            - Identify which tasks can be worked on now
            - Find tasks that can be delegated in parallel
            - Avoid blocking on incomplete dependencies

        Example:
            result = get_ready_tasks()
            for task in result['ready_tasks']:
                print(f"Ready: {task['description']}")
        """
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)
            ready_tasks = plan.get_ready_tasks()

            return {
                "success": True,
                "operation": "get_ready_tasks",
                "ready_tasks": [t.to_dict() for t in ready_tasks],
                "count": len(ready_tasks),
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "get_ready_tasks",
                "error": str(e),
            }

    @mcp.tool()
    def get_blocked_tasks() -> Dict[str, Any]:
        """
        Get all tasks that are blocked by incomplete dependencies.

        Returns:
            Dictionary with list of tasks that have status='pending' but
            dependencies not completed, including what each task is waiting on

        Use cases:
            - Understand what's blocking progress
            - Prioritize completing blocking tasks
            - Visualize dependency chains

        Example:
            result = get_blocked_tasks()
            for task in result['blocked_tasks']:
                print(f"Blocked: {task['description']}")
                print(f"  Waiting on: {task['blocking_task_ids']}")
        """
        try:
            plan = _get_or_create_plan(mcp.agent_id, mcp.orchestrator_id)
            blocked_tasks = plan.get_blocked_tasks()

            # Add blocking task info for each blocked task
            blocked_with_info = []
            for task in blocked_tasks:
                task_dict = task.to_dict()
                task_dict["blocking_task_ids"] = plan.get_blocking_tasks(task.id)
                blocked_with_info.append(task_dict)

            return {
                "success": True,
                "operation": "get_blocked_tasks",
                "blocked_tasks": blocked_with_info,
                "count": len(blocked_tasks),
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "get_blocked_tasks",
                "error": str(e),
            }

    return mcp


if __name__ == "__main__":
    import asyncio

    import fastmcp

    asyncio.run(fastmcp.run(create_server))
