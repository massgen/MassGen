#!/usr/bin/env python3
"""Prompt-prefix builders for planning, spec creation, log analysis, and skill organization.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Literal,
)

if TYPE_CHECKING:
    pass


def _format_chunk_target_line(target_chunks: int | None) -> str:
    """Return chunk guidance text for planning/spec prompts."""
    if target_chunks == 1 or target_chunks is None:
        return "- Target chunks: exactly 1"
    if target_chunks > 1:
        return f"- Target chunks: around {target_chunks}"
    return "- Target chunks: exactly 1"


def should_include_quick_edit_hint(planning_turn_mode: str | None) -> bool:
    """Show quick-edit hint only for explicit single-turn refinement mode."""
    return planning_turn_mode == "single"


def get_task_planning_prompt_prefix(
    plan_depth: str = "dynamic",
    target_steps: int | None = None,
    target_chunks: int | None = None,
    enable_subagents: bool = False,
    broadcast_mode: Literal["human", "agents"] | bool = False,
    thoroughness: str = "standard",
) -> str:
    """Generate the user prompt prefix for task planning mode.

    This prefix is prepended to the user's question when --plan mode is active.
    It instructs agents to interactively create structured feature lists.

    Args:
        plan_depth: One of "dynamic", "shallow", "medium", or "deep" controlling task granularity.
        target_steps: Optional explicit target number of tasks (None = dynamic sizing).
        target_chunks: Optional explicit target number of chunks (None = default single-chunk planning).
        enable_subagents: Whether subagents are enabled for research tasks.
        broadcast_mode: One of "human", "agents", or False. Controls whether ask_others() is available.
        thoroughness: One of "standard" or "thorough" controlling strategic reasoning depth.

    Returns:
        The prompt prefix string to prepend to the user's question.
    """
    depth_config = {
        "dynamic": {"target": "dynamic", "detail": "scope-adaptive granularity"},
        "shallow": {"target": "5-10", "detail": "high-level phases only"},
        "medium": {"target": "20-50", "detail": "sections with tasks"},
        "deep": {"target": "100-200+", "detail": "granular step-by-step"},
    }
    normalized_depth = plan_depth if plan_depth in depth_config else "dynamic"
    cfg = depth_config[normalized_depth]

    if target_steps is not None and target_steps > 0:
        task_target_line = f"- Target tasks: around {target_steps}"
    elif normalized_depth == "dynamic":
        task_target_line = "- Target tasks: dynamic based on scope complexity"
    else:
        task_target_line = f"- Target tasks: {cfg['target']}"

    chunk_target_line = _format_chunk_target_line(target_chunks)

    # Thoroughness section (controls strategic reasoning depth)
    thoroughness_section = ""
    if thoroughness == "thorough":
        thoroughness_section = """
## Thoroughness: THOROUGH

You are striving for excellence — in both the quality of your strategic \
reasoning and the originality of your approach. Do not accept a plan that \
is merely complete or structurally sound. A thorough plan is one where \
every major decision reflects deep understanding of the problem, where \
the chosen direction is genuinely the strongest option (not just the \
first or safest), and where the resulting work would impress someone who \
knows this domain well.

**Quality bar:** Standard is not enough. Push past the obvious approach. \
If your plan could have been written by someone who spent 5 minutes on \
the problem, it's not thorough. Invest the time to understand what \
separates excellent work from adequate work in this specific domain, and \
let that understanding shape every task.

**Required auxiliary depth:**
- `research/` — analyze the problem domain, audience, competitive landscape, \
and what distinguishes excellent results from adequate ones in this space
- `framework/` — document your strategic choices: why this approach over \
alternatives, what anti-patterns to avoid, what principles should guide \
execution. Name specific failure modes and how to prevent them
- `risks/` — identify what could go wrong, what assumptions are most fragile, \
and what the pivot strategy is if key assumptions fail

**Plan structure expectations:**
- Separate strategic decisions from implementation details. Early tasks should \
establish the strategic foundation (audience, narrative, design principles, \
interaction strategy) before any section-level work begins
- Creative and architectural direction should be exploratory tasks with \
success criteria, not deterministic tasks with locked-in values
- Evolution hooks should question the fundamental direction, not just tweak \
parameters within it
- The plan should tell a coherent story about WHY this approach will produce \
excellent results — an evaluator should be able to read the auxiliary docs \
and understand the reasoning behind every major decision
"""

    # Subagent research section (only if enabled)
    subagent_section = ""
    if enable_subagents:
        subagent_section = """
## Research with Subagents

You have subagents available for research. Use them to:
- Investigate specific areas of the codebase in parallel
- Research technical options or dependencies
- Explore integration points with existing code
- Gather information to inform scope decisions

Spawn subagents for research tasks before finalizing your plan.
"""

    # Conditional scope confirmation section based on broadcast mode
    if broadcast_mode == "human":
        scope_section = """### 1. Scope Confirmation (REQUIRED FIRST)

Before any deep research, analyze the request and verify scope with the user.

**Step 1: Categorize requirements and assumptions**

Parse the user's request into three categories:

1. **Explicitly Stated** - Things the user directly mentioned
   - Example: "Build a REST API" → User said "REST API"

2. **Critical Assumptions** - High-level decisions that affect scope/direction (NEED HUMAN VERIFICATION)
   - User intent or business logic
   - Major architectural choices (monolith vs microservices, SQL vs NoSQL)
   - Security/compliance requirements
   - Feature scope boundaries
   - Example: "Build a REST API" → Is this for internal use or public? What data sensitivity?

3. **Technical/Implementation Assumptions** - Lower-level choices (AGENT CONSENSUS via voting)
   - Specific technologies/frameworks
   - Code organization patterns
   - Standard practices (error handling, logging, validation)
   - Example: "Build a REST API" → Express vs FastAPI, JWT details, specific DB choice

**Step 2: Verify ONLY THE MOST CRITICAL assumptions with human**

Be selective - only ask about assumptions where you truly cannot make a good decision without human input.

**When to ask the human**:
- User intent is ambiguous (internal tool vs public product?)
- Business/domain knowledge required (compliance, data sensitivity)
- Major scope decisions (which features are in/out?)
- Trade-offs that depend on user priorities (speed vs security vs cost)

**When NOT to ask the human** (let consensus decide):
- Technical implementation details (framework, database, auth method)
- Standard practices (error handling, logging, testing approach)
- Scope refinements that you can revisit after initial consensus
- Decisions where you can make a reasonable recommendation

**IMPORTANT**: When you DO ask, offer recommendations with reasoning:

GOOD (selective + recommendations):
```
I need to clarify scope before planning this REST API:

1. **Usage context**: Is this for internal use or public-facing?
   - Recommendation: I'll assume internal unless you specify, which means simpler auth and fewer rate limits

2. **Data sensitivity**: What type of data will this handle?
   - Recommendation: I'll plan for standard business data (not public, not highly sensitive) unless you need HIPAA/PCI compliance

3. **Integration needs**: Do you have existing systems this must integrate with?
   - If yes, please specify - this affects the approach significantly

Let me know if my assumptions are wrong or if there are other critical requirements.
```

BAD (asking everything):
```
Should I use Express or FastAPI?
Should I use JWT or OAuth?
Should I use PostgreSQL or MongoDB?
Which testing framework?
How should I structure the code?
```

**Step 3: Document technical assumptions and recommendations for consensus**

For technical/implementation assumptions, present your recommendations with reasoning in your answer.

**Be opinionated**: Make specific technical recommendations based on:
- The user's explicit requirements
- Industry best practices
- Your analysis of the codebase (if extending existing project)
- Trade-offs you've considered

Other agents will:
- Propose alternative approaches if they disagree
- Challenge your technical choices with their reasoning
- Refine scope to keep tasks focused and useful
- Vote when they're happy with the combination of choices

**Benefits of consensus**:
- Explores wider design space through agent debate
- Ensures all tasks are critical and actively useful
- Prevents scope divergence through multi-agent validation
- Catches assumptions one agent might miss

**Note**: You can always ask the human for clarification in later rounds after seeing consensus. Start with your best recommendations, refine through voting, then verify critical decisions if needed.

**Step 4: Feature scope (with recommendations)**

If the request contains **multiple distinct features**, recommend which to prioritize:

GOOD (scoped recommendation):
```
I see this request involves three main features:
1. User authentication (CORE - needed for everything else)
2. Todo CRUD operations (CORE - primary functionality)
3. Email notifications (NICE-TO-HAVE - can add later)

Recommendation: Let's scope this planning session to features 1-2, then add notifications in a follow-up. Does that work?
```

BAD (asking without recommendation):
```
This has multiple features. Which ones do you want?
```

**After critical verification (minimal ask_others calls), proceed to research. Technical assumptions and scope refinements will be refined through voting.**"""
    else:
        # No human interaction - agents make all decisions through consensus
        scope_section = """### 1. Scope Analysis (REQUIRED FIRST)

Before any deep research, analyze the request and make decisions through agent consensus.

**Step 1: Categorize requirements and assumptions**

Parse the user's request into three categories:

1. **Explicitly Stated** - Things the user directly mentioned
   - Example: "Build a REST API" → User said "REST API"

2. **Critical Assumptions** - High-level decisions that affect scope/direction
   - User intent or business logic
   - Major architectural choices (monolith vs microservices, SQL vs NoSQL)
   - Security/compliance requirements
   - Feature scope boundaries
   - Example: "Build a REST API" → Assume internal use or public-facing?

3. **Technical/Implementation Assumptions** - Lower-level choices
   - Specific technologies/frameworks
   - Code organization patterns
   - Standard practices (error handling, logging, validation)
   - Example: "Build a REST API" → Express vs FastAPI, JWT details, specific DB choice

**Step 2: Make opinionated recommendations for ALL assumptions**

Since you don't have human interaction, you MUST make decisions autonomously.

**Be opinionated**: Make specific recommendations for ALL assumptions based on:
- The user's explicit requirements
- Industry best practices
- Your analysis of the codebase (if extending existing project)
- Trade-offs you've considered
- Reasonable defaults when ambiguous

**Document your reasoning**: For each assumption, explain WHY you chose that approach.

Example:
```
I'm making these decisions for this REST API:

1. **Usage context**: Internal use (simpler auth, no rate limiting needed)
   - Reasoning: No mention of public users, so assuming internal tooling

2. **Data sensitivity**: Standard business data (moderate security)
   - Reasoning: No compliance requirements mentioned, so standard practices

3. **Tech stack**: FastAPI + PostgreSQL + JWT
   - Reasoning: FastAPI for async support, PostgreSQL for reliability, JWT for stateless auth

4. **Scope**: Core features only (auth + CRUD), no notifications yet
   - Reasoning: Start with MVP, can add features later
```

**Step 3: Refine through consensus**

Other agents will:
- Propose alternative approaches if they disagree
- Challenge your assumptions with their reasoning
- Suggest different scope boundaries
- Vote when they're happy with the combination of choices

**Benefits of consensus**:
- Explores wider design space through agent debate
- Ensures all tasks are critical and actively useful
- Prevents scope divergence through multi-agent validation
- Catches assumptions one agent might miss

**Critical**: ALL decisions must be made through consensus. No human will verify them, so agents must carefully debate and validate each choice.

**After consensus is reached, proceed to research. All assumptions and scope will be refined through voting.**"""

    return f"""# TASK PLANNING MODE

You are in task planning mode. Your goal is to **interactively** create a comprehensive task plan.

## CRITICAL: PLANNING ONLY - DO NOT BUILD THE DELIVERABLE

**YOU ARE A PLANNER, NOT AN EXECUTOR.**

- **DO NOT** create the actual deliverable (no final code, no implementations)
- **DO NOT** execute the user's task - only plan it
- **DO** create `project_plan.json` listing tasks that a FUTURE agent will execute
- **DO** research and explore to understand the task scope

**Allowed files:**
1. `project_plan.json` - the task list for future execution (REQUIRED)
2. Supporting docs - requirements, design decisions, technical approach
3. Scratch/research files - scripts to parse data, analyze structure, gather info FOR PLANNING
4. `prototypes/` - rough proof-of-concept artifacts for exploratory tasks (see Mini-Prototyping below)

**NOT allowed:**
- The actual deliverable the user requested (SVG, website, app, final code, etc.)
- Implementation code that would be the end product

If you find yourself building what the user asked for - STOP. You're only planning it.
A different agent will execute this plan later.

### Mini-Prototyping for Exploratory Tasks

For tasks classified as `exploratory` (see Task Type Classification below), \
you MAY create rough proof-of-concept artifacts to validate assumptions:
- **Visual tasks**: a rough SVG sketch, wireframe, or color palette test
- **Code tasks**: a minimal spike proving the algorithm or approach works
- **Writing tasks**: a paragraph sample testing voice or tone

Store prototypes in `prototypes/` alongside the plan. They validate \
assumptions — they are NOT deliverables. Reference which assumptions each \
prototype validated or invalidated in the plan's auxiliary files.

**When to prototype**: when the plan's success depends on an assumption you \
can't verify by reasoning alone (e.g., "will this visual approach render \
well in SVG?" or "does this algorithm scale?"). When in doubt, prototype.

## Planning Process

Follow this process in order:

{scope_section}

### 2. Research & Exploration
Once scope is confirmed:
- Explore the codebase to understand existing structure
- Investigate integration points
- Identify potential technical challenges{subagent_section}

### 3. Clarifying Questions
As you research, ask follow-up questions about:
- Edge cases and error handling expectations
- Performance or security requirements
- User experience preferences
- Anything ambiguous you discovered

### 4. Plan Creation
Only after scope confirmation and sufficient research:
- Create the feature list at the specified depth
- Organize features by logical grouping
- If multiple distinct features exist, consider separate spec files

## Output Requirements

1. **Primary artifact**: `project_plan.json` - Write this file using file write tools:
   - If `deliverable/` folder exists in your workspace, put it there: `deliverable/project_plan.json`
   - Otherwise, put it in your workspace root: `project_plan.json`
2. **Auxiliary files** (optional, organized into purpose-driven subdirectories):
   - `research/` — background research, prior art, feasibility analysis, codebase exploration notes
   - `framework/` — architecture decisions, technology choices with rationale, design patterns selected
   - `risks/` — risk register, mitigation strategies, dependency analysis
   - `requirements/` — user stories, acceptance criteria, requirements docs
   - `prototypes/` — quick proof-of-concept artifacts for exploratory tasks (see Mini-Prototyping)
   Auxiliary files support the plan but are NOT the plan — `project_plan.json` is always the source of truth.

**IMPORTANT**: Write `project_plan.json` directly as a file. Do NOT use MCP planning tools
(create_task_plan, update_task_status, etc.) to create this deliverable - those tools are for
tracking your own internal work progress, not for creating the project plan deliverable.

## Planning Principles

**Focus on outcomes, not implementation details.** Describe WHAT the final product needs, not HOW to build it. Implementation choices happen during execution.

**Show strategic depth, not just task structure.** A good plan demonstrates \
that you deeply understood the problem before breaking it into tasks. \
Before specifying tasks, reason about the problem space: who is this for, \
what impression or experience matters most, what distinguishes an excellent \
result from a competent one? Capture this reasoning in auxiliary files \
(research/, framework/, decisions/) and let it drive task design. If your \
plan reads like a generic template with project-specific nouns swapped in, \
it lacks the specificity that produces excellent results. Each major \
decision should have rationale tied to the actual problem context — not \
just "best practice" or "modern trend."

**Think about final product quality:**
- If it's visual, it should LOOK good - include quality visuals, not just code
- If it produces output, that output should be polished and professional
- Consider what a user/viewer would actually experience

**Verification should test the PRODUCT FIRST, then source code:**
1. Does the final product work? (run it, use it, see it)
2. Does it look/feel right? (visual quality, UX)
3. Only then: is the code correct? (builds, tests pass)

**Your JSON output IS the iteration surface.** Prefer tightening existing \
tasks — sharpen descriptions, add missing verification, fix dependency \
ordering — over adding new tasks or prose. Adding tasks to fill genuine \
gaps is fine; adding tasks that don't serve a clear purpose is not.

**Question your own direction.** Your first approach is a hypothesis, not \
a commitment. When iterating, don't just polish the current direction — \
challenge whether it's the right direction. Ask: is this the strongest \
approach, or just the first one I reached for? Would a different \
architecture, structure, or creative direction produce a fundamentally \
better result? A sophisticated plan isn't one that executes a safe idea \
thoroughly — it's one that identifies the most promising direction and \
specifies it with enough depth and detail that the executor can build \
something genuinely impressive.

**Tasks should be achievable with the available tools.** Executing agents will have access to the configured tools and will figure out how to use them.
{thoroughness_section}
## Task Type Classification

Every task MUST be classified as `deterministic` or `exploratory`:

**Deterministic tasks**:
- Have a single correct implementation path
- Can be fully specified upfront (data schemas, API contracts, configs, build setup)
- Verification is binary: it works or it doesn't
- The plan specifies WHAT + HOW in detail

**Exploratory tasks**:
- Have multiple valid approaches where the best one emerges through iteration
- Cannot be fully specified upfront because quality is subjective or context-dependent
- Verification requires qualitative assessment (render it, read it, experience it)
- The plan specifies **success criteria + constraints**, NOT implementation steps
- The executor has explicit permission to exceed or diverge from the plan when \
they discover something better
- MUST include `success_criteria`: 2-4 concrete criteria for what "good" looks \
like (not how to get there)
- SHOULD include `evolution_hooks` in metadata: what discoveries during \
implementation should trigger a plan revision

**Classification test**: "If two competent engineers followed this task \
independently, would they produce essentially the same output?" \
Yes -> deterministic. No -> exploratory.

## Plan Evolution Protocol

Plans are hypotheses, not contracts. Include explicit mechanisms for evolution:

**Discovery annotations**: for each chunk, note:
- What assumptions could this chunk invalidate?
- What would you learn during execution that you can't know now?
- If this chunk reveals the approach is wrong, what's the pivot?

**Evaluation integration points**: mark tasks where evaluation should be \
invoked mid-execution by adding `"eval_checkpoint": true` to the task's \
metadata. Place these at:
- After the first exploratory chunk completes (early signal on approach viability)
- After any chunk whose `evolution_hooks` flag high-risk assumptions
- Before the final polish chunk (ensure the foundation is worth polishing)

## Task List Format
Write `project_plan.json` with this structure:
```json
{{
  "tasks": [
    {{
      "id": "F001",
      "chunk": "C01_foundation",
      "task_type": "deterministic|exploratory",
      "description": "Feature Name - What this feature accomplishes and the expected outcome",
      "status": "pending",
      "depends_on": ["F000"],
      "priority": "high|medium|low",
      "success_criteria": ["Only for exploratory tasks: what good looks like, not how to get there"],
      "metadata": {{
        "verification": "How to verify this task is complete",
        "verification_method": "Output-first verification approach",
        "verification_group": "optional_group_name",
        "evolution_hooks": ["Discoveries during this task that should trigger plan revision"],
        "eval_checkpoint": false
      }}
    }}
  ]
}}
```

### Required Chunking Rules
- Every task **MUST** include a non-empty `chunk` string.
- Use ordered chunk labels (for example: `C01_foundation`, `C02_backend`, `C03_ui`).
- Dependencies must not point to future chunks.
- Keep chunk order deterministic by using consistent, increasing labels.
- Respect the chunk target guidance below while preserving a valid dependency DAG.

### Metadata Fields (Optional but Recommended)
- **verification**: What to check - testable completion criteria (e.g., "Homepage displays correctly", "API returns 200")
- **verification_method**: Output-first verification approach. Start with user-visible checks (run it, click through it, inspect the rendered/output result), then add automated checks where useful.
- **verification_group**: Group related tasks for batch verification (e.g., "foundation", "frontend_ui", "api_endpoints").
  During execution, tasks are marked `completed` then later `verified` in groups.

## Planning Size Controls
- Depth mode: {normalized_depth.upper()}
{task_target_line}
{chunk_target_line}
- Detail level: {cfg["detail"]}

## Quality Criteria
- Each task should be independently verifiable
- Dependencies (depends_on) should form a valid DAG (no cycles)
- Descriptions must include both WHAT and HOW — not just "Create hero \
section" but specific layout, content, and behavior. A developer reading \
the task should know what to build without asking questions
- Where tasks connect or produce artifacts consumed by other tasks, \
specify interface contracts: data shapes, file conventions, API \
signatures. Independent execution should not require reverse-engineering \
unstated agreements
- Scope should be confirmed with user before detailed planning
- Verification criteria should be testable and specific
- Use verification_group to batch related tasks (e.g., verify all pages after building them)
- For user-facing tasks, include at least one verification step that checks the actual user-visible output
- Prefer tightening existing tasks over adding new ones. Growth is fine when filling genuine gaps; growth without clear purpose is sprawl

---

USER'S REQUEST:
"""


def get_spec_creation_prompt_prefix(
    broadcast_mode: "Literal['human', 'agents'] | bool" = False,
    target_chunks: int | None = None,
) -> str:
    """Generate the user prompt prefix for spec creation mode.

    This prefix is prepended to the user's question when --spec mode is active.
    It instructs agents to create a structured requirements specification using
    EARS notation (Easy Approach to Requirements Syntax).

    Args:
        broadcast_mode: One of "human", "agents", or False.
            Controls whether ask_others() is available for scope confirmation.
        target_chunks: Optional target number of execution chunks.

    Returns:
        The prompt prefix string to prepend to the user's question.
    """
    chunk_target_line = _format_chunk_target_line(target_chunks)

    # Scope section reuses the same human vs autonomous pattern as plan mode
    if broadcast_mode == "human":
        scope_section = """\
### 1. Scope Confirmation (REQUIRED FIRST)

Before any deep research, analyze the request and verify scope with the user.

**Categorize the request** into:
1. **Explicitly Stated** - What the user directly mentioned
2. **Critical Assumptions** - High-level decisions needing human verification \
(intent, architecture, compliance, scope boundaries)
3. **Technical Assumptions** - Lower-level choices for agent consensus \
(frameworks, patterns, practices)

**Ask the human** only about critical assumptions where you cannot make a \
good decision without input. Offer recommendations with reasoning.

**After critical verification, proceed to research.**"""
    else:
        scope_section = """\
### 1. Scope Analysis (REQUIRED FIRST)

Before any deep research, analyze the request and make decisions \
through agent consensus.

**Categorize the request** into:
1. **Explicitly Stated** - What the user directly mentioned
2. **Critical Assumptions** - High-level decisions (intent, architecture, \
compliance, scope boundaries)
3. **Technical Assumptions** - Lower-level choices (frameworks, patterns, \
practices)

**Make opinionated recommendations** for ALL assumptions with reasoning. \
Other agents will challenge, refine, and vote on consensus.

**After consensus is reached, proceed to research.**"""

    return f"""\
# SPEC CREATION MODE

You are in spec creation mode. Your goal is to **interactively** create \
a structured requirements specification.

## CRITICAL: SPEC ONLY - DO NOT BUILD THE DELIVERABLE

**YOU ARE A SPEC WRITER, NOT AN EXECUTOR.**

- **DO NOT** create the actual deliverable (no final code, no implementations)
- **DO NOT** execute the user's task - only specify it
- **DO** create `project_spec.json` with requirements that a FUTURE agent \
will implement
- **DO** research and explore to understand the task scope

**Allowed files:**
1. `project_spec.json` - the requirements specification (REQUIRED)
2. Supporting docs - design decisions, technical context, user stories
3. Scratch/research files - scripts to parse data, analyze structure, \
gather info FOR SPEC WRITING

**NOT allowed:**
- The actual deliverable the user requested (code, website, app, etc.)
- Implementation code that would be the end product

If you find yourself building what the user asked for - STOP. \
You're only specifying it. A different agent will implement this spec later.

## Spec Process

Follow this process in order:

{scope_section}

### 2. Research & Exploration
Once scope is confirmed:
- Explore the codebase to understand existing structure
- Investigate integration points
- Identify potential technical challenges

### 3. Clarifying Questions
As you research, ask follow-up questions about:
- Edge cases and error handling expectations
- Performance or security requirements
- User experience preferences
- Anything ambiguous you discovered

### 4. Spec Creation
Only after scope confirmation and sufficient research:
- Create the requirements specification
- Use EARS notation for each requirement
- Group requirements into execution chunks
- Include verification criteria for each requirement

## Output Requirements

1. **Primary artifact**: `project_spec.json` - Write this file using \
file write tools:
   - If `deliverable/` folder exists in your workspace, put it there: \
`deliverable/project_spec.json`
   - Otherwise, put it in your workspace root: `project_spec.json`
2. **Auxiliary files** (optional, organized into purpose-driven subdirectories):
   - `research/` — domain analysis, user research, competitive analysis, prior art
   - `design/` — system design notes, data models, API contracts, integration points
   - `decisions/` — architectural decision records (ADRs), trade-off analyses
   - `requirements/` — user stories, acceptance criteria, persona descriptions
   Auxiliary files support the spec but are NOT the spec — `project_spec.json` \
is always the source of truth.

**IMPORTANT**: Write `project_spec.json` directly as a file. Do NOT use \
MCP planning tools (create_task_plan, update_task_status, etc.) to create \
this deliverable.

**Show strategic depth, not just requirements structure.** A good spec \
demonstrates that you deeply understood the problem before writing \
requirements. Reason about the problem space: who is this for, what \
experience matters most, what distinguishes an excellent result from a \
competent one? Capture this reasoning in auxiliary files (research/, \
design/, decisions/) and let it drive requirement design. If your spec \
reads like a generic template with project-specific nouns swapped in, it \
lacks the specificity that produces excellent results.

**Your JSON output IS the iteration surface.** Prefer tightening existing \
requirements — sharpen EARS statements, add missing verification, \
resolve ambiguities — over adding new requirements or prose. Adding \
requirements to fill genuine gaps is fine; adding them without clear \
purpose is not.

**Question your own direction.** Your first approach is a hypothesis, not \
a commitment. When iterating, don't just polish the current spec — \
challenge whether the underlying design direction is the right one. Ask: \
is this the strongest approach, or just the first one I reached for? \
Would a different architecture, interaction model, or system design \
produce a fundamentally better result? A strong spec identifies the most \
promising direction and specifies it with enough depth that the executor \
can build something genuinely excellent.

## EARS Notation

Use the **Easy Approach to Requirements Syntax** (EARS) for each \
requirement's `ears` field:
- **Event-driven**: WHEN <trigger> THE SYSTEM SHALL <response>
- **State-driven**: WHILE <state> THE SYSTEM SHALL <behavior>
- **Unwanted behavior**: IF <condition> THEN THE SYSTEM SHALL <response>
- **Optional**: WHERE <feature> THE SYSTEM SHALL <behavior>

Examples:
- WHEN user submits login form THE SYSTEM SHALL validate credentials \
and return a session token
- WHILE server load exceeds 80% THE SYSTEM SHALL reject new connections \
with 503 status
- IF database connection fails THEN THE SYSTEM SHALL retry with \
exponential backoff up to 3 times

## Spec Format
Write `project_spec.json` with this structure:
```json
{{{{
  "feature": "Feature Name",
  "overview": "2-3 sentence description of what this feature accomplishes",
  "requirements": [
    {{{{
      "id": "REQ-001",
      "chunk": "C01_core",
      "title": "Short descriptive title",
      "priority": "P0|P1|P2",
      "type": "functional|non-functional",
      "ears": "WHEN <trigger> THE SYSTEM SHALL <response>",
      "rationale": "Why this requirement exists",
      "verification": "How to verify this requirement is met",
      "depends_on": ["REQ-000"]
    }}}}
  ]
}}}}
```

### Required Chunking Rules
- Every requirement **MUST** include a non-empty `chunk` string.
- Use ordered chunk labels (for example: `C01_core`, `C02_api`, \
`C03_frontend`).
- Dependencies must not point to future chunks.
- Keep chunk order deterministic by using consistent, increasing labels.
- Respect the chunk target guidance below while preserving a valid \
dependency DAG.

### Field Descriptions
- **id**: Unique requirement identifier (REQ-001, REQ-002, etc.)
- **chunk**: Execution phase grouping (C01_core, C02_api, etc.)
- **title**: Short descriptive title for the requirement
- **priority**: P0 (critical), P1 (important), P2 (nice-to-have)
- **type**: "functional" (what it does) or "non-functional" \
(how well it does it)
- **ears**: EARS-formatted requirement statement
- **rationale**: Why this requirement exists - the "why" behind the "what"
- **verification**: Testable criteria to verify the requirement is met
- **depends_on**: List of requirement IDs this depends on

## Spec Size Controls
{chunk_target_line}
- Requirements should be specific enough to implement and verify

## Quality Criteria
- Each requirement should be independently verifiable
- Dependencies (depends_on) should form a valid DAG (no cycles)
- EARS statements should be unambiguous and testable — a single behavior per requirement
- Scope should be confirmed with user before detailed spec writing
- Verification criteria should be specific and measurable
- Rationale should explain the business or technical reason
- Prefer tightening existing requirements over adding new ones. Growth is fine when filling genuine gaps; growth without clear purpose is sprawl

---

USER'S REQUEST:
"""


def build_plan_review_refinement_appendix(
    *,
    question: str,
    planning_feedback: str,
    include_quick_edit_hint: bool,
) -> str:
    """Build optional prompt appendix for planning-review refinement turns.

    Avoids duplicating feedback blocks when the current question already embeds
    plan-review feedback text (common when users include it directly).
    """
    sections: list[str] = []

    feedback = (planning_feedback or "").strip()
    normalized_question = " ".join((question or "").lower().split())
    normalized_feedback = " ".join(feedback.lower().split())

    feedback_already_present = False
    if feedback:
        if normalized_feedback and normalized_feedback in normalized_question:
            feedback_already_present = True
        elif "plan review feedback" in normalized_question:
            feedback_already_present = True

    if feedback and not feedback_already_present:
        sections.append(
            "## Plan Review Feedback\n" f"{feedback}\n\n" "Apply this feedback while keeping a valid chunk-labeled task DAG.",
        )

    if include_quick_edit_hint:
        sections.append(
            "## Quick Edit Planning Turn\n" "Make precise updates and preserve valid chunk/dependency structure.",
        )

    return "\n\n".join(sections)


def _load_skill_creator_reference() -> str:
    """Load the skill-creator SKILL.md for prompt inclusion."""
    try:
        path = Path(".agent") / "skills" / "skill-creator" / "SKILL.md"
        return path.read_text(encoding="utf-8")
    except Exception:
        # Minimal fallback if file is missing
        return "---\nname: descriptive-skill-name\n" "description: Clear explanation of what this workflow does\n---\n" "# Skill Name\n\n## Purpose\n## Workflow\n"


def _get_log_session_original_query(log_dir: str | None) -> str | None:
    """Extract the original user query from a log session's status.json.

    Args:
        log_dir: Path to the log session directory.

    Returns:
        The original query string, or None if not found.
    """
    if not log_dir:
        return None
    import json

    log_path = Path(log_dir)
    for status_path in sorted(log_path.glob("turn_*/attempt_*/status.json")):
        try:
            data = json.loads(status_path.read_text())
            question = data.get("meta", {}).get("question", "")
            if question:
                return question.strip()
        except Exception:
            continue
    return None


def get_log_analysis_prompt_prefix(
    log_dir: str | None,
    turn: int | None,
    profile: str = "dev",
    skill_lifecycle_mode: str = "create_or_update",
) -> str:
    """Generate the user prompt prefix for Textual analysis mode.

    Args:
        log_dir: Selected log session directory path, or None for auto/current.
        turn: Selected turn number, or None for latest available turn.
        profile: Analysis profile ("dev" or "user").

    Returns:
        Prefix instructions to prepend to the user's question.
    """
    from massgen.filesystem_manager.skills_manager import normalize_skill_lifecycle_mode

    normalized_profile = profile if profile in ("dev", "user") else "dev"
    normalized_lifecycle_mode = normalize_skill_lifecycle_mode(skill_lifecycle_mode)
    target_log = log_dir or "auto-select current/latest log session"
    target_turn = f"turn_{turn}" if turn is not None else "latest available turn"

    original_query = _get_log_session_original_query(log_dir)
    original_query_section = ""
    if original_query:
        original_query_section = f"""- Original task: {original_query}
"""

    if normalized_profile == "user":
        skill_creator_ref = _load_skill_creator_reference()
        lifecycle_instructions = {
            "create_or_update": """- Lifecycle mode: create_or_update (default).
- First look for the best existing skill in `.agent/skills/` and update it when it matches the same domain workflow.
- Only create a new skill if no existing skill is a strong match.
""",
            "create_new": """- Lifecycle mode: create_new.
- Always create a new skill directory in `.agent/skills/`.
- Do not modify existing skills in this mode.
""",
        }.get(normalized_lifecycle_mode, "")
        profile_section = f"""## Profile Focus: USER (skills-first)

Primary objective:
- Read the logs from this run to understand what workflow was executed and how.
- Distill the workflow into a single reusable skill that lets someone repeat or adapt it.

IMPORTANT constraints:
- Create exactly ONE skill unless the run covered genuinely distinct, unrelated tasks.
- The skill must be about the DOMAIN TASK (the original query above), NOT about "analyzing logs" or "evaluating runs".
- The skill should encode the workflow, techniques, prompt patterns, and tool usage that made this run effective.
- Name the skill after what it DOES (e.g., "poem-workshop", "website-builder"), not after analysis.
{lifecycle_instructions}

Required outputs:
- Create a skill directory on disk: `.agent/skills/<skill-name>/SKILL.md` using filesystem tools.
- The SKILL.md should capture the specific workflow, prompts, and patterns from the logs so someone else can reproduce or build on this work.
- Add provenance metadata so MassGen can classify this as an evolving skill:
  - `massgen_origin: "{target_log}::{target_turn}"`
  - `evolving: true`

## Skill Creation Reference

<skill-creator-reference>
{skill_creator_ref}
</skill-creator-reference>

When creating a skill from analysis findings:
1. Choose a descriptive kebab-case name that reflects the domain task (NOT "log-analysis" or similar).
2. Write the SKILL.md file directly to `.agent/skills/<name>/SKILL.md` using filesystem tools.
3. Include YAML frontmatter with at least `name`, `description`, `massgen_origin`, and `evolving`.
4. Focus the skill content on the actual workflow and techniques, not on meta-analysis.
5. Respect lifecycle mode `{normalized_lifecycle_mode}` when deciding whether to update existing skills, create a new one, or consolidate overlaps.
6. If a SKILL_REGISTRY.md exists in `.agent/skills/`, append the new skill to it under a "## Recently Added" section \
with format: `- **skill-name** (project): description`. This ensures the skill is visible to agents before the next \
full registry reorganization.
"""
    else:
        profile_section = """## Profile Focus: DEV (internals-first)

Primary objective:
- Diagnose runtime behavior, coordination quality, and implementation-level issues in MassGen.

Required outputs:
- Prioritize root causes, regressions, and concrete internal improvements.
- Be specific about signals from logs/events, likely causes, and fix direction.
"""

    return f"""# LOG ANALYSIS MODE

You are in MassGen Textual analysis mode.

Analysis target:
- Log session: {target_log}
- Turn: {target_turn}
{original_query_section}
{profile_section}

General constraints:
- Use the available skills and local log artifacts as the primary evidence source.
- Focus on actionable conclusions, not generic summaries.
- If evidence is incomplete, state exactly what is missing and why it matters.

USER'S ANALYSIS REQUEST:
"""


def get_skill_organization_prompt_prefix() -> str:
    """Generate the user prompt prefix for skill organization analysis mode.

    This prompt instructs the agent to read all installed skills, identify
    overlapping or confusable skills, merge where appropriate, and produce
    a compact SKILL_REGISTRY.md routing guide.

    Returns:
        Prefix instructions to prepend to the user's question.
    """
    return """# SKILL ORGANIZATION MODE

You are in MassGen skill organization mode. Your task is to analyze, reorganize,
and catalog all installed skills.

IMPORTANT: Start by reading the skill-organizer skill's instructions from
.agent/skills/skill-organizer/SKILL.md for the detailed workflow.

## Step 1: Inventory all skills

List all skill directories in the .agent/skills/ folder. Then read each skill's
SKILL.md file to understand what it does, its scope, and its quality.

## Step 2: Identify overlapping or confusable skills

Look for:
- Skills that do the same thing with slightly different names or descriptions
- Skills whose scopes overlap significantly (one is a subset of another)
- Skills that could be combined into a single broader skill with multiple sections

## Step 3: Merge into hierarchical parent skills

For each group of overlapping or related skills, create a single parent skill
with sections covering each sub-capability:
- Choose a broader parent name (e.g., `web-app-dev` instead of separate
  `react-frontend`, `nodejs-backend`, `web-testing`)
- Write one comprehensive SKILL.md with clearly labeled sections for each
  sub-capability
- Move bundled resources into subdirectories of the parent skill directory
- Remove the redundant skill directories

When merging, prefer the skill with:
- Better-quality instructions and examples
- More complete bundled resources
- A more descriptive, general name

Fewer, richer skills with sections beats many shallow skills.

## Step 4: Generate SKILL_REGISTRY.md

Write a compact `SKILL_REGISTRY.md` to `.agent/skills/SKILL_REGISTRY.md` that serves
as a routing guide for skill selection. For each skill, include:

- **What it does** in one sentence
- **Use when**: trigger condition — when should the agent read this skill?
- **Sections**: what sub-capabilities/sections live inside (for hierarchical skills)

Group skills by purpose/domain (not alphabetically). Stay under 50 entries total.
Include a "Recently Added" section for uncategorized new skills.

The registry is injected into agent system prompts to help them pick the right skill
without loading all skill details upfront.

## Step 5: Report what you did

Summarize:
- How many skills were found
- Which skills were merged (old names → new name)
- Which skills were kept as-is
- The final registry structure

## Constraints

- Do NOT use keyword matching, Jaccard similarity, or heuristic categorization.
  Use your understanding of what each skill does.
- Be aggressive about merging — fewer high-quality skills is better than many overlapping ones.
- Preserve all bundled resources (templates, examples, configs) during merges.
- The SKILL_REGISTRY.md is a routing guide, not documentation. Keep it concise.

USER'S ORGANIZATION REQUEST:
"""
