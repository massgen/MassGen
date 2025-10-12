# ADR-0003: Multi-Agent Collaborative Architecture

**Status:** Accepted
**Date:** 2024-10-08 (decision made ~2024-06, documented retroactively)
**Deciders:** @Leezekun, core team
**Technical Story:** Core architectural decision defining MassGen's approach

## Context and Problem Statement

Complex AI tasks often benefit from multiple perspectives and iterative refinement. Single-agent systems can get stuck in local optima or miss alternative approaches. How should MassGen enable effective collaboration between multiple AI agents?

**Key challenges:**
- How do agents share insights without overwhelming each other?
- How to achieve consensus while maintaining diverse perspectives?
- How to scale to multiple agents without exponential communication overhead?
- How to detect when collaboration has converged on a solution?

## Considered Options

1. **Sequential Chain** - Agents work one after another, passing results forward
2. **Parallel Independent + Vote** - Agents work separately, majority vote on result
3. **Collaborative Refinement (Chosen)** - Agents work in parallel, observe others, refine iteratively
4. **Hierarchical Delegation** - Master agent delegates subtasks to specialized agents
5. **Debate/Adversarial** - Agents argue different positions until consensus

## Decision

We chose **Collaborative Refinement with Parallel Processing**.

### Core Architecture

**Key principles:**
1. **Parallel Processing**: Multiple agents tackle the problem simultaneously
2. **Intelligence Sharing**: Agents can observe each other's work-in-progress
3. **Iterative Refinement**: Agents update their approaches based on peer observations
4. **Natural Convergence**: No forced voting - agents converge organically when quality plateaus
5. **Diverse Perspectives**: Different models/configurations bring complementary strengths

**Workflow:**
1. All agents receive the same initial prompt
2. Agents work in parallel on their individual approaches
3. After each round, agents see summaries of peers' progress
4. Agents can adopt better ideas, correct errors they notice in others, or continue their approach
5. Process continues until convergence is detected (changes become minimal)
6. Orchestrator synthesizes the final result from converged agent outputs

### Rationale

- **Inspired by effective research groups**: Mimics how human experts collaborate
- **Leverages model diversity**: Different models have different strengths (reasoning, creativity, factual knowledge)
- **Avoids premature convergence**: No forced voting allows better solutions to emerge
- **Scales well**: Communication is controlled (snapshots, not continuous chatter)
- **Natural quality signal**: Convergence indicates solution stability
- **Flexible**: Works for various task types (reasoning, generation, analysis)

Based on insights from:
- "Threads of Thought" concept from "The Myth of Reasoning" (AG2 blog)
- xAI's Grok Heavy multi-model approach
- Google DeepMind's Gemini Deep Think system
- Classic multi-agent conversation from AG2 framework

## Consequences

### Positive

- **Higher quality outputs**: Multiple perspectives catch errors and find better solutions
- **Robustness**: Not dependent on any single model's weaknesses
- **Natural consensus**: Agents converge organically rather than through forced voting
- **Interpretable**: Can observe how agents influenced each other
- **Model-agnostic**: Works with any LLM backend
- **Scalable**: Controlled communication prevents quadratic blowup

### Negative

- **Increased latency**: Multiple rounds of generation take time
- **Higher cost**: Multiple agents mean more API calls
- **Complexity**: Orchestration logic is more complex than single-agent
- **Non-determinism**: Different runs may converge differently
- **Communication overhead**: Agents must process peer observations

### Neutral

- Need good convergence detection heuristics
- Requires careful prompt engineering for collaboration
- Balance needed between agent autonomy and coordination

## Implementation Notes

**Core components:**
- **Orchestrator** (`massgen/orchestrator/`): Manages agent lifecycle and communication
- **Agent backends** (`massgen/backends/`): Pluggable LLM integrations
- **Snapshot system**: Captures and shares agent progress
- **Convergence detection**: Monitors when changes plateau
- **Coordination UI**: Rich terminal display showing agent progress

**Configuration:**
- Agents configured via YAML files
- Support for different models, prompts, temperatures per agent
- Flexible stopping conditions (rounds, convergence threshold, time)

**Key Features:**
- Parallel execution with async/await
- Snapshot-based communication (not full message history)
- Voting and consensus mechanisms
- Live visualization of agent coordination
- Session persistence for multi-turn interactions

## Validation

Success metrics:
- ✅ Agents demonstrably improve based on peer observations
- ✅ Quality of final output exceeds single-agent approaches
- ✅ Convergence detected reliably
- ✅ Scales to 3-7 agents effectively
- ✅ Works across diverse task types

Validated through case studies showing measurable improvements over single-agent baselines.

## Related Decisions

- Enables case-driven development methodology (ADR-0004)
- Informed by research on multi-agent systems
- May evolve with:
  - More sophisticated communication protocols
  - Hierarchical agent organizations
  - Specialized agent roles
  - Dynamic agent spawning

## References

- [The Myth of Reasoning](https://docs.ag2.ai/latest/docs/blog/2025/04/16/Reasoning/) - "Threads of thought" concept
- [Berkeley Agentic AI Summit 2025 Talk](https://www.youtube.com/watch?v=xM2Uguw1UsQ) - Background context
- xAI Grok Heavy - Multi-model collaborative approach
- Google DeepMind Gemini Deep Think - Extended multi-step reasoning
- AG2 Framework - Classic multi-agent conversation patterns

---

*This is the foundational architectural decision that defines MassGen's unique approach. All major features build on this collaborative multi-agent paradigm.*

*Last updated: 2024-10-08 by @ncrispin*
