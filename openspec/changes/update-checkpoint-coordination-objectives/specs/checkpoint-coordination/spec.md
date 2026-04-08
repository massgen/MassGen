## ADDED Requirements

### Requirement: Objective-Based Calling Mode
The `checkpoint` tool SHALL support an objective-based calling mode, dispatched by the presence of the `objective` field. The existing delegation mode (`task` field) is unchanged.

#### Scenario: Mode dispatch — objective mode
- **WHEN** a caller provides an `objective` field
- **THEN** the system SHALL run objective-based safety planning and return `criteria_applied` plus a structured `plan`

#### Scenario: Mode dispatch — delegation mode
- **WHEN** a caller provides a `task` field
- **THEN** the system SHALL run the existing delegation flow and return consensus text plus workspace changes

#### Scenario: Both fields rejected
- **WHEN** a caller provides both `objective` and `task`
- **THEN** the system SHALL return an error

### Requirement: Objective Mode Input
The objective mode input SHALL be compact. The caller describes the outcome to plan, optional action intents, and optional per-checkpoint criteria.

#### Scenario: Minimal objective input
- **WHEN** a caller provides only `objective`
- **THEN** the system SHALL accept the request and produce a plan using the global safety policy as the sole evaluation criteria

#### Scenario: Action goals input
- **WHEN** a caller provides `action_goals`
- **THEN** each entry SHALL have an `id` and `goal`, with optional `preferred_tools` and `constraints`
- **AND** the system SHALL use these to resolve specific `approved_action` entries in the output plan

#### Scenario: Per-checkpoint eval criteria
- **WHEN** a caller provides `eval_criteria`
- **THEN** the system SHALL apply them in addition to the global safety policy, never as a replacement

#### Scenario: No context path filtering
- **WHEN** checkpoint agents are planning an objective
- **THEN** they SHALL have access to the full cloned workspace, not a caller-selected subset
- **AND** the input schema SHALL NOT include a `context_paths` field

### Requirement: Automatically Provided Context
The orchestrator SHALL automatically provide the following to checkpoint agents without requiring the caller to specify them.

#### Scenario: Full workspace provided
- **WHEN** a checkpoint subprocess is launched
- **THEN** checkpoint agents SHALL receive a full clone of the main agent's workspace

#### Scenario: Execution trace provided
- **WHEN** a checkpoint subprocess is launched
- **THEN** checkpoint agents SHALL receive the main agent's execution trace up to the checkpoint call, including assistant responses, tool calls, tool results, and any available reasoning

#### Scenario: Main agent tool list provided
- **WHEN** a checkpoint subprocess is launched
- **THEN** checkpoint agents SHALL receive the full list of tools available to the main agent, so they can reason about which calls require explicit approval

### Requirement: Objective Mode Output
Objective mode output SHALL include the criteria applied, and an ordered plan with per-step constraints, optional approved actions, and optional recovery trees.

#### Scenario: Criteria applied returned
- **WHEN** an objective mode checkpoint completes
- **THEN** the result SHALL include `criteria_applied` listing the global policy entries and per-checkpoint criteria that shaped the plan

#### Scenario: Ordered plan returned
- **WHEN** an objective mode checkpoint completes
- **THEN** the result SHALL include an ordered `plan` as a list of steps the main agent must follow

#### Scenario: Per-step constraints
- **WHEN** a plan step restricts what the agent may do
- **THEN** that step SHALL include a `constraints` list of directive strings
- **AND** constraints SHALL cover both goal-directed restrictions (blocking alternative paths toward the goal) and adjacency restrictions (blocking scope creep that may arise while pursuing the step)

#### Scenario: Approved action as sole exception
- **WHEN** a plan step includes both `constraints` and an `approved_action`
- **THEN** the `approved_action` SHALL be the only permitted exception to those constraints
- **AND** the agent SHALL use exactly the specified tool and args — no alternatives
- **AND** when `constraints` is present but `approved_action` is absent, the capability SHALL be fully blocked for that step

#### Scenario: Per-step recovery tree
- **WHEN** a plan step includes a `recovery` field
- **THEN** it SHALL be a `RecoveryNode` with an `if` condition and `then`/`else` branches
- **AND** each branch SHALL be either a terminal value or another `RecoveryNode`
- **AND** terminal values SHALL be one of: `"proceed"`, `"recheckpoint"`, `"refuse"`

### Requirement: Subprocess Execution Model
Checkpoint SHALL execute as a subprocess in both delegation and objective modes.

#### Scenario: Subprocess launch
- **WHEN** the main agent calls checkpoint
- **THEN** the orchestrator SHALL launch a `massgen --stream-events` subprocess with a generated config
- **AND** the main workspace SHALL NOT be mutated during checkpoint execution

#### Scenario: Event relay for WebUI
- **WHEN** the checkpoint subprocess emits events
- **THEN** the parent process SHALL relay them with remapped agent IDs (appending `-ckptN` suffix)
- **AND** the WebUI SHALL display checkpoint agent activity without blank channels

#### Scenario: No workspace writeback in objective mode
- **WHEN** an objective mode checkpoint completes
- **THEN** the orchestrator SHALL NOT copy files from checkpoint scratch back to the main workspace
- **AND** the output SHALL be the structured plan only
