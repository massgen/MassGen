# System Prompt Architecture Redesign

**Date**: 2025-11-12
**Status**: Design
**Author**: System refactoring based on prompt engineering best practices research

## Problem Statement

### Current Issues

The MassGen system prompt assembly has become bloated and poorly structured, leading to:

1. **Skills not being loaded proactively** - Skills section is buried after ~500+ lines of other instructions
2. **Memory system underutilized** - Memory instructions appear after ~400+ lines
3. **Inverted hierarchy** - Evaluation/coordination mechanics appear before agent identity
4. **Poor attention management** - No clear priority signaling or structural hierarchy
5. **Monolithic sections** - Filesystem instructions are a 200-line undifferentiated block

### Current Assembly Order (Problems Highlighted)

```
orchestrator.py lines 2665-2893:

1. Agent custom message
2. Filesystem instructions (200+ lines) ⚠️ Too early, too large
3. Planning mode instructions (conditional)
4. Evaluation system message ⚠️ Gets prepended FIRST by build_initial_conversation()
5. Task planning guidance (100+ lines)
6. Memory system message (100+ lines) ⚠️ Too late
7. Skills system message ⚠️ Dead last, buried
```

**Result**: Critical behavioral instructions (skills, memory) are lost in the noise. Agents read through 500+ lines before seeing skills.

## Research Findings

### Best Practices for LLM System Prompts

Based on 2025 prompt engineering research, effective system prompt design requires:

#### 1. Hierarchical Structure
- **Meta-instructions before task details** - High-level behavioral guidance comes first
- **Critical instructions at top or bottom** - Position creates emphasis
- **Task-specific instructions after core behaviors** - What to do now vs. how you operate
- **Source**: Lakera AI Prompt Engineering Guide [1], Anthropic Claude Best Practices [2]

#### 2. XML Structure for Claude
- **Claude is trained on XML-tagged content** - Special attention to XML structure
- **Use semantic tags** - `<skills>`, `<memory>`, `<evaluation>` create clear boundaries
- **Priority attributes** - Make importance explicit in tags
- **Source**: Anthropic Claude 4 Prompt Engineering Best Practices [2]

#### 3. Attention Management
- **Treat like UX design** - If humans struggle to follow it, models will too
- **Visual/logical separation** - Use headers, whitespace, clear sections
- **Avoid burying critical instructions** - Middle of prompts gets overlooked
- **Source**: Dextra Labs Prompt Engineering Guide [3], Position is Power Research [4]

#### 4. Priority Signaling
- **Explicit hierarchy prevents conflicts** - Clear priority = clear behavior
- **Group related instructions** - Skills with skills, memory with memory
- **Separate concerns** - Identity vs. operations vs. task context
- **Source**: Prompt Engineering Hierarchical Structure Research [5]

#### 5. Breaking Down Complexity
- **Monolithic blocks reduce comprehension** - Break large sections into subsections
- **Hierarchical subsections** - Parent sections contain focused child sections
- **Progressive detail** - Critical facts first, details later
- **Source**: AWS Claude Best Practices [6], Hierarchical Prompting Taxonomy [7]

## Proposed Architecture

### Class-Based Section System

Replace ad-hoc string concatenation with structured section objects:

```python
# New file: massgen/system_prompt_sections.py

class Priority(IntEnum):
    """Explicit priority levels"""
    CRITICAL = 1      # Agent identity, MassGen primitives (vote/new_answer), core behaviors
    HIGH = 5          # Skills, memory, filesystem workspace - essential context
    MEDIUM = 10       # Operational guidance, task planning
    LOW = 15          # Task-specific context
    AUXILIARY = 20    # Optional guidance, best practices

@dataclass
class SystemPromptSection(ABC):
    """Base class for all sections"""
    title: str
    priority: Priority
    xml_tag: Optional[str] = None
    enabled: bool = True
    subsections: List['SystemPromptSection'] = None

    @abstractmethod
    def build_content(self) -> str:
        """Build section content"""
        pass

    def render(self) -> str:
        """Render with XML structure"""
        # XML wrapping, subsection handling, etc.
        pass
```

### Section Types

#### Critical Priority (P1) - Foundational Knowledge
- **AgentIdentitySection**: Agent's role, expertise, personality (WHO they are)
- **CoreBehaviorsSection**: Default to action, parallel tool calling, file cleanup (HOW to act)
- **EvaluationSection**: MassGen primitives - vote/new_answer tools and coordination mechanics

#### High Priority (P5) - Essential Context
- **SkillsSection**: Available skills table with "REVIEW FIRST" emphasis
- **MemorySection**: Memory tiers and proactive usage guidance
- **FilesystemSection** (parent)
  - **WorkspaceStructureSection**: Critical workspace paths
  - **FilesystemOperationsSection**: Tool usage instructions
  - **FilesystemBestPracticesSection**: Optional guidance

#### Medium Priority (P10) - Operational Guidance
- **TaskPlanningSection**: When/how to create task plans
- **PlanningModeSection**: Planning mode instructions (conditional)

#### Low Priority (P15) - Task-Specific Context
- **EvaluationSection**: MassGen coordination mechanics (vote vs new_answer)

### Builder Pattern

```python
class SystemPromptBuilder:
    """Assembles sections in priority order"""

    def add_section(self, section: SystemPromptSection) -> 'SystemPromptBuilder':
        """Builder pattern - chain section additions"""
        pass

    def build(self) -> str:
        """Assemble final system prompt"""
        # 1. Sort sections by priority
        # 2. Render each section
        # 3. Wrap in root <system_prompt> XML
        # 4. Return final string
        pass
```

### Example Output Structure

```xml
<system_prompt>

<agent_identity priority="critical">
You are a research agent specializing in AI safety...
</agent_identity>

<core_behaviors priority="critical">
## Core Behavioral Principles

**Default to Action:**
By default, implement changes rather than only suggesting them...

**Parallel Tool Calling:**
If you intend to call multiple tools with no dependencies, call them in parallel...

**File Cleanup:**
Remove temporary files at the end of the task...
</core_behaviors>

<massgen_coordination priority="critical">
## MassGen Coordination Mechanics

You are evaluating answers from multiple agents. Use the `vote` tool to
record your vote, or the `new_answer` tool to submit a new response...
</massgen_coordination>

<skills priority="high">
## IMPORTANT: Review Available Skills Before Starting Work

You have access to specialized skills that can dramatically improve
your performance. ALWAYS consider which skills apply to your task.

Available Skills:
| Skill | Description | When to Use |
|-------|-------------|-------------|
| web_research | Deep web research | Information gathering |
...
</skills>

<memory priority="high">
## Memory System

You have access to a tiered memory system for context retention...
</memory>

<filesystem priority="high">
<workspace_structure priority="high">
## Workspace Paths
- Workspace: /path/to/workspace/
- Context paths: [...]
</workspace_structure>

<filesystem_operations priority="medium">
## Filesystem Tools
- create_answer: Create new answer files...
</filesystem_operations>

<filesystem_best_practices priority="auxiliary">
## Best Practices
- Keep workspace clean by removing outdated files...
</filesystem_best_practices>
</filesystem>

<task_planning priority="medium">
## Task Planning Guidance
When tasks are complex, create a structured plan...
</task_planning>

<evaluation priority="low">
## Evaluation & Coordination
You are part of a multi-agent system. When evaluating...
</evaluation>

</system_prompt>
```

## Implementation Plan

### Phase 1: Core Infrastructure

**File**: `massgen/system_prompt_sections.py` (NEW)

1. Create `Priority` enum with 5 levels
2. Create `SystemPromptSection` abstract base class with:
   - `title`, `priority`, `xml_tag`, `enabled`, `subsections`
   - `build_content()` abstract method
   - `render()` implementation with XML wrapping
3. Create `SystemPromptBuilder` with:
   - `add_section()` builder method
   - `build()` assembly logic (sort by priority, render, wrap)

### Phase 2: Section Implementations

**File**: `massgen/system_prompt_sections.py` (continued)

Implement concrete section classes:

1. **AgentIdentitySection**
   - Priority: CRITICAL
   - Inputs: agent_message (from agent.get_configurable_system_message())
   - Content: Pass through agent's message unchanged

2. **SkillsSection**
   - Priority: CRITICAL
   - Inputs: skills list, built_in_skills list
   - Content: Migrate logic from `message_templates.skills_system_message()`
   - Enhancement: Add prominent "REVIEW FIRST" header

3. **MemorySection**
   - Priority: CRITICAL
   - Inputs: memory_config dict
   - Content: Migrate logic from `message_templates.get_memory_system_message()`
   - Enhancement: Emphasize proactive usage

4. **FilesystemSection** (parent)
   - Priority: HIGH
   - Subsections: WorkspaceStructure, Operations, BestPractices
   - Content: Brief intro, subsections handle details

5. **WorkspaceStructureSection**
   - Priority: HIGH
   - Inputs: workspace_path, context_paths
   - Content: Extract workspace/path info from current `filesystem_system_message()`

6. **FilesystemOperationsSection**
   - Priority: MEDIUM
   - Content: Extract tool usage instructions from `filesystem_system_message()`

7. **FilesystemBestPracticesSection**
   - Priority: AUXILIARY
   - Content: Extract optional guidance from `filesystem_system_message()`

8. **TaskPlanningSection**
   - Priority: MEDIUM
   - Inputs: planning_guidance string
   - Content: Migrate logic from `message_templates.get_planning_guidance()`

9. **EvaluationSection**
   - Priority: LOW
   - Inputs: evaluation_instructions string
   - Content: Migrate logic from `message_templates.evaluation_system_message()`

10. **PlanningModeSection**
    - Priority: MEDIUM
    - Inputs: enabled flag, planning_mode_instruction string
    - Content: Conditional planning mode instructions

### Phase 3: Orchestrator Integration

**File**: `massgen/orchestrator.py`

Replace system message assembly (lines 2665-2893):

```python
def _build_system_message(self, agent, planning_mode_enabled, ...) -> str:
    """Build system message using section-based architecture"""
    from massgen.system_prompt_sections import SystemPromptBuilder

    builder = SystemPromptBuilder()

    # Core identity (P1)
    builder.add_section(
        AgentIdentitySection(agent.get_configurable_system_message())
    )

    # Critical behaviors (P1)
    if use_skills:
        builder.add_section(SkillsSection(skills, built_in_skills))

    if enable_memory_filesystem_mode:
        builder.add_section(MemorySection(memory_config))

    # Essential context (P5-P10)
    builder.add_section(FilesystemSection(workspace_path, context_paths))

    if enable_agent_task_planning:
        builder.add_section(TaskPlanningSection(planning_guidance))

    if planning_mode_enabled:
        builder.add_section(PlanningModeSection(enabled=True))

    # Task context (P15)
    builder.add_section(EvaluationSection(evaluation_instructions))

    return builder.build()
```

**Key Changes**:
- Remove old assembly logic (lines 2665-2893)
- Replace with builder pattern calls
- Builder automatically handles:
  - Priority sorting
  - XML wrapping
  - Conditional sections (via enabled flag)
  - Subsection hierarchy

### Phase 4: Deprecation

**File**: `massgen/message_templates.py`

Mark old methods as deprecated (keep temporarily for fallback):

```python
def evaluation_system_message(self) -> str:
    """DEPRECATED: Use EvaluationSection instead"""
    # Keep implementation for now
    pass

def filesystem_system_message(self, ...) -> str:
    """DEPRECATED: Use FilesystemSection with subsections instead"""
    # Keep implementation for now
    pass

def skills_system_message(self, skills: List) -> str:
    """DEPRECATED: Use SkillsSection instead"""
    # Keep implementation for now
    pass
```

**Migration Timeline**:
1. Phase 1-3: New system in parallel, old system still works
2. Testing phase: Verify new system matches/improves behavior
3. After 1-2 releases: Remove deprecated methods

## Testing Strategy

### Unit Tests

**File**: `massgen/tests/test_system_prompt_sections.py` (NEW)

Test each section independently:

```python
def test_agent_identity_section():
    section = AgentIdentitySection("You are an expert in AI safety")
    rendered = section.render()
    assert "<agent_identity" in rendered
    assert 'priority="critical"' in rendered
    assert "You are an expert in AI safety" in rendered

def test_skills_section_with_skills():
    skills = [{"name": "web_research", "description": "..."}]
    section = SkillsSection(skills)
    rendered = section.render()
    assert "REVIEW FIRST" in rendered or "IMPORTANT" in rendered
    assert "web_research" in rendered

def test_system_prompt_builder_ordering():
    builder = SystemPromptBuilder()
    builder.add_section(EvaluationSection("eval"))  # P15
    builder.add_section(AgentIdentitySection("agent"))  # P1
    builder.add_section(SkillsSection([]))  # P1

    result = builder.build()

    # Verify agent identity comes before evaluation
    agent_pos = result.index("agent")
    eval_pos = result.index("eval")
    assert agent_pos < eval_pos
```

### Integration Tests

**File**: `massgen/tests/test_orchestrator_system_prompt.py` (NEW or extend existing)

Test full system prompt assembly:

```python
def test_system_prompt_includes_all_sections():
    orchestrator = Orchestrator(...)
    system_message = orchestrator._build_system_message(...)

    assert "<system_prompt>" in system_message
    assert "<agent_identity" in system_message
    assert "<skills" in system_message
    assert "<memory" in system_message
    assert "<filesystem" in system_message
    assert "<evaluation" in system_message

def test_skills_appear_before_evaluation():
    orchestrator = Orchestrator(config_with_skills=True)
    system_message = orchestrator._build_system_message(...)

    skills_pos = system_message.index("<skills")
    eval_pos = system_message.index("<evaluation")
    assert skills_pos < eval_pos, "Skills should appear before evaluation"
```

### Behavioral Tests

Run existing MassGen configs and verify:

1. **Skills are loaded proactively**
   - Monitor agent responses for skill usage mentions
   - Compare before/after: Are skills referenced earlier in conversations?

2. **Memory system used more effectively**
   - Check memory_filesystem operations
   - Verify agents create/load memories without explicit prompting

3. **No regressions**
   - Run full test suite
   - Compare outputs on standard benchmarks
   - Ensure voting/coordination still works

### Manual Verification

Capture actual system prompt output:

```python
# Add temporary debug logging
system_message = builder.build()
with open("/tmp/system_prompt_output.xml", "w") as f:
    f.write(system_message)
```

Review for:
- Proper XML structure
- Correct priority ordering
- Clear section boundaries
- Reasonable length (should be comparable to current, not dramatically longer)

## Migration Strategy

### Phase 1: Parallel Implementation (Week 1)
- Implement all section classes
- Implement builder
- Add feature flag: `use_structured_system_prompt = False` (default)
- Both systems coexist

### Phase 2: Testing & Refinement (Week 2)
- Enable feature flag in test environment
- Run integration tests
- Compare outputs side-by-side
- Collect feedback from test sessions
- Adjust priorities/content as needed

### Phase 3: Gradual Rollout (Week 3)
- Enable for specific agent types first (e.g., research agents)
- Monitor skill/memory usage metrics
- Enable for all agents
- Set `use_structured_system_prompt = True` as default

### Phase 4: Cleanup (Week 4+)
- Remove old assembly code from orchestrator
- Remove deprecated methods from message_templates
- Remove feature flag
- Update documentation

## Benefits

### Immediate Benefits
1. **Skills visible** - Appear after only agent identity (~50 lines vs ~500 lines)
2. **Memory prominent** - Critical priority, shown early
3. **Correct hierarchy** - Agent identity first, evaluation last
4. **Clear structure** - XML tags with explicit priorities

### Long-Term Benefits
1. **Maintainable** - Section logic encapsulated in classes
2. **Testable** - Unit test individual sections
3. **Extensible** - Add new section types easily
4. **Flexible** - Reorder by changing priority values
5. **Debuggable** - Clear separation makes issues easy to isolate
6. **Documented** - Class docstrings provide self-documentation

### Performance Benefits
1. **Better attention** - Critical instructions at top, not buried
2. **Reduced confusion** - Clear priorities prevent instruction conflicts
3. **Improved compliance** - XML structure Claude is trained on
4. **Behavioral improvements** - Skills/memory used proactively

## Risks & Mitigations

### Risk 1: Behavioral Changes
**Risk**: New structure might change agent behavior in unexpected ways
**Mitigation**: Feature flag allows A/B testing, gradual rollout, easy rollback

### Risk 2: Length Increase
**Risk**: XML tags might significantly increase prompt length
**Mitigation**: XML adds ~50-100 tokens max, negligible for long contexts

### Risk 3: Backwards Compatibility
**Risk**: Existing configs might break
**Mitigation**: Keep old methods as fallback during migration period

### Risk 4: Integration Complexity
**Risk**: Many files touch system prompt assembly
**Mitigation**: Centralize in orchestrator, single integration point

## Success Metrics

### Quantitative
- **Skills usage rate**: % of conversations where agents proactively mention skills
- **Memory operations**: Count of create_memory/load_memory calls
- **Response quality**: Compare outputs on standard benchmarks
- **System prompt length**: Should be comparable (±10%)

### Qualitative
- **Code maintainability**: Developer ease of adding new sections
- **Debugging ease**: Time to isolate system prompt issues
- **Agent compliance**: Do agents follow instructions more consistently?

### Target Improvements
- Skills mentioned 50%+ more often in conversations
- Memory operations increase 30%+
- Zero regressions on existing benchmarks
- Developer velocity: 50% faster to add new system prompt features

## References

[1] Lakera AI. (2025). "The Ultimate Guide to Prompt Engineering in 2025."
https://www.lakera.ai/blog/prompt-engineering-guide

[2] Anthropic. (2025). "Claude 4 Prompt Engineering Best Practices."
https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices

[3] Dextra Labs. (2025). "Prompt Engineering for LLMs: Best Technical Guide in 2025."
https://dextralabs.com/blog/prompt-engineering-for-llm/

[4] Academic Research. (2025). "Position is Power: System Prompts as a Mechanism of Bias in Large Language Models."
https://arxiv.org/html/2505.21091v2

[5] News.aakashg.com. (2025). "Prompt Engineering in 2025: The Latest Best Practices."
https://www.news.aakashg.com/p/prompt-engineering

[6] AWS Machine Learning Blog. (2024). "Prompt Engineering Techniques and Best Practices: Learn by Doing with Anthropic's Claude 3."
https://aws.amazon.com/blogs/machine-learning/prompt-engineering-techniques-and-best-practices-learn-by-doing-with-anthropics-claude-3-on-amazon-bedrock/

[7] Academic Research. (2024). "Hierarchical Prompting Taxonomy: A Universal Evaluation Framework for Large Language Models."
https://arxiv.org/html/2406.12644v3

## Next Steps

1. Review and approve this design document
2. Create GitHub issue for tracking implementation
3. Begin Phase 1: Core infrastructure implementation
4. Set up testing framework
5. Execute migration plan

---

**Status**: Awaiting approval to proceed with implementation
