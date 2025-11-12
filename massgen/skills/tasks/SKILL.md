---
name: tasks
description: This skill should be used when agents need to break down complex work into manageable tasks, track progress, and coordinate based on dependencies. Provides filesystem-based task planning as a transparent alternative to task MCP tools.
license: MIT
---

# Tasks Skill

Manage task plans using the filesystem for transparent, version-controllable task tracking.

## Purpose

The tasks skill provides filesystem-based task planning to organize complex work. Store task plans as JSON files in the `tasks/` directory with clear status tracking and dependency management. This transparent approach replaces task MCP tools when skills are enabled, making task plans visible files that can be inspected, modified, and version-controlled.

## Directory Structure

```
your_workspace/
  ├── tasks/
  │   ├── plan.json        # Your current task plan
  │   └── archive/         # Completed task plans
  │       └── 2025-11-11_plan.json
  └── workspace/           # Your main working directory

<shared_reference>/      # Read-only access to other agents
  ├── agent1/             # (path varies by config, often temp_workspaces/)
  │   └── tasks/           # Agent 1's task plan (read-only)
  └── agent2/
      └── tasks/           # Agent 2's task plan (read-only)
```

**Note**: The shared reference path is shown in your system prompt under "Shared Reference". The default is typically `temp_workspaces/` but can be configured differently.

## Task Plan Format

Tasks are stored in JSON format with this structure:

```json
{
  "plan_id": "unique-plan-id",
  "created_at": "2025-11-11T10:30:00Z",
  "updated_at": "2025-11-11T10:35:00Z",
  "tasks": [
    {
      "id": "task-1",
      "title": "Set up project structure",
      "description": "Create directories and initial files",
      "status": "completed",
      "dependencies": [],
      "created_at": "2025-11-11T10:30:00Z",
      "completed_at": "2025-11-11T10:32:00Z"
    },
    {
      "id": "task-2",
      "title": "Implement authentication",
      "description": "Add login and signup functionality",
      "status": "in_progress",
      "dependencies": ["task-1"],
      "created_at": "2025-11-11T10:32:00Z"
    },
    {
      "id": "task-3",
      "title": "Write tests",
      "description": "Add unit tests for auth module",
      "status": "pending",
      "dependencies": ["task-2"],
      "created_at": "2025-11-11T10:33:00Z"
    }
  ]
}
```

## When to Use This Skill

Use the tasks skill when:

- Work is complex enough to benefit from task breakdown (5-10+ tasks)
- Dependencies between tasks need tracking
- Progress needs to be visible to other agents
- Task planning is enabled (`enable_agent_task_planning: true`)

Do not use for:

- Simple, linear work (just do it directly)
- Single-task workflows
- When task MCP is preferred over filesystem approach

## How to Use

### Creating a Task Plan

```bash
# Create a new task plan
cat > tasks/plan.json << 'EOF'
{
  "plan_id": "implement-auth-feature",
  "created_at": "$(date -Iseconds)",
  "updated_at": "$(date -Iseconds)",
  "tasks": [
    {
      "id": "task-1",
      "title": "Research authentication libraries",
      "description": "Compare JWT vs session-based auth",
      "status": "pending",
      "dependencies": []
    }
  ]
}
EOF
```

### Adding a Task

```bash
# Add a new task to existing plan using jq
jq '.tasks += [{
  "id": "task-2",
  "title": "Implement login endpoint",
  "description": "Create POST /api/login endpoint",
  "status": "pending",
  "dependencies": ["task-1"],
  "created_at": "'"$(date -Iseconds)"'"
}]' tasks/plan.json > tasks/plan.tmp && mv tasks/plan.tmp tasks/plan.json
```

### Updating Task Status

```bash
# Mark task as in_progress
jq '(.tasks[] | select(.id == "task-1") | .status) = "in_progress"' \
  tasks/plan.json > tasks/plan.tmp && mv tasks/plan.tmp tasks/plan.json

# Mark task as completed
jq '(.tasks[] | select(.id == "task-1") | .status) = "completed" |
    (.tasks[] | select(.id == "task-1") | .completed_at) = "'"$(date -Iseconds)"'"' \
  tasks/plan.json > tasks/plan.tmp && mv tasks/plan.tmp tasks/plan.json
```

### Viewing Task Plan

```bash
# View full plan
cat tasks/plan.json

# View just task titles and status
jq '.tasks[] | {title, status}' tasks/plan.json

# View pending tasks only
jq '.tasks[] | select(.status == "pending")' tasks/plan.json

# View tasks ready to start (dependencies met)
# This is a simplified check; real implementation would verify deps
jq '.tasks[] | select(.status == "pending" and (.dependencies | length == 0))' tasks/plan.json
```

### Viewing Other Agents' Task Plans

```bash
# See what another agent is working on (check system prompt for shared reference path)
# Example if shared reference is temp_workspaces/:
cat temp_workspaces/agent1/tasks/plan.json

# Compare progress across agents
for agent in temp_workspaces/*/; do
  echo "=== $(basename $agent) ==="
  jq '.tasks[] | {title, status}' "${agent}tasks/plan.json" 2>/dev/null || echo "No task plan"
done
```

## Task Statuses

- **pending**: Task not yet started
- **in_progress**: Currently working on this task
- **completed**: Task finished successfully
- **blocked**: Cannot proceed (waiting on external factor)
- **skipped**: Task no longer needed

## Best Practices

1. **Break Down Complex Work**: Create 5-10 tasks max per plan; break larger projects into sub-plans
2. **Clear Titles**: Use descriptive, actionable titles (e.g., "Implement user login" not "Login")
3. **Track Dependencies**: Set `dependencies` array to task IDs that must complete first
4. **Update Regularly**: Keep status current as you work through tasks
5. **Archive Completed Plans**: Move finished plans to `tasks/archive/` with date prefix

## Common Patterns

### Simple Sequential Plan

```json
{
  "plan_id": "fix-bug-123",
  "tasks": [
    {
      "id": "1",
      "title": "Reproduce the bug",
      "status": "completed"
    },
    {
      "id": "2",
      "title": "Identify root cause",
      "status": "in_progress",
      "dependencies": ["1"]
    },
    {
      "id": "3",
      "title": "Implement fix",
      "status": "pending",
      "dependencies": ["2"]
    },
    {
      "id": "4",
      "title": "Add regression test",
      "status": "pending",
      "dependencies": ["3"]
    }
  ]
}
```

### Parallel Tasks

```json
{
  "plan_id": "build-dashboard",
  "tasks": [
    {
      "id": "1",
      "title": "Design API endpoints",
      "status": "completed"
    },
    {
      "id": "2",
      "title": "Build frontend components",
      "status": "in_progress",
      "dependencies": ["1"]
    },
    {
      "id": "3",
      "title": "Implement backend logic",
      "status": "in_progress",
      "dependencies": ["1"]
    },
    {
      "id": "4",
      "title": "Integration testing",
      "status": "pending",
      "dependencies": ["2", "3"]
    }
  ]
}
```

### Archive Completed Plan

```bash
# Move completed plan to archive with timestamp
mkdir -p tasks/archive
mv tasks/plan.json "tasks/archive/$(date +%Y-%m-%d)_plan.json"
```

## Helper Scripts

### Check if Dependencies Are Met

```bash
#!/bin/bash
# check_ready_tasks.sh - Find tasks ready to start

jq -r '.tasks[] |
  select(.status == "pending") |
  select(
    .dependencies as $deps |
    .dependencies | length == 0 or
    all($deps[]; . as $dep_id |
      any($root.tasks[]; .id == $dep_id and .status == "completed")
    )
  ) |
  .title' tasks/plan.json
```

### Generate Progress Report

```bash
#!/bin/bash
# progress_report.sh - Show task completion stats

total=$(jq '.tasks | length' tasks/plan.json)
completed=$(jq '[.tasks[] | select(.status == "completed")] | length' tasks/plan.json)
in_progress=$(jq '[.tasks[] | select(.status == "in_progress")] | length' tasks/plan.json)
pending=$(jq '[.tasks[] | select(.status == "pending")] | length' tasks/plan.json)

echo "Task Plan Progress"
echo "=================="
echo "Total: $total"
echo "Completed: $completed ($((completed * 100 / total))%)"
echo "In Progress: $in_progress"
echo "Pending: $pending"
```

## Tips

- Use `jq` for JSON manipulation (pre-installed in Docker containers)
- Keep task descriptions concise but clear
- Review other agents' task plans to coordinate work
- Archive old plans to keep tasks/ directory clean
- Use timestamps in ISO 8601 format for consistency

## See Also

- `memory` skill - For storing long-term context
- `file_search` skill - For searching through task plans
