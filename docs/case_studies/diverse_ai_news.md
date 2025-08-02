# MassGen Case Study: Synthesis from Diverse Perspectives

This case study demonstrates how MassGen (v0.0.1alpha) handles subjective prompts by tasking a representative agent to synthesize a final, comprehensive answer from multiple, diverse viewpoints.

**Command:**
```bash
uv run python cli.py --config examples/fast_config.yaml "find big AI news this week"
```

**Prompt:** `find big AI news this week`

**Agents:**
*   Agent 1: `gpt-4.1` (Designated Representative Agent)
*   Agent 2: `gemini-2.5-flash`
*   Agent 3: `grok-3-mini`

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/SMmgCG7MZ2M/0.jpg)](https://www.youtube.com/watch?v=SMmgCG7MZ2M)

## The Collaborative Process

### Divergent Interpretations

Given the subjective nature of the prompt, each agent interpreted "big news" differently, leading to three distinct and valuable initial answers:

*   **Agent 1 (gpt-4.1)** focused on high-impact, headline-grabbing news like major policy changes and corporate launches.
*   **Agent 2 (gemini-2.5-flash)** provided a highly detailed, categorized list that included more technical and research-oriented updates.
*   **Agent 3 (grok-3-mini)** prioritized news with clear sources and attempted to provide a broad, balanced summary.

### The Vote: A Tie Between Strong Opinions

Each agent, confident in its own unique and valid interpretation, voted for its own answer. This resulted in a 1-1-1 tie. This outcome highlights the different strengths and priorities of each model, and it provides the system with three different lenses through which to view the week's AI news.

## The Final Answer: Synthesis by the Representative Agent

Instead of simply defaulting to one answer, MassGen's orchestrator designated a `representative_agent` (Agent 1) to perform a final, crucial step: **synthesis**.

Agent 1 was tasked with reviewing its own answer, the answers from Agents 2 and 3, and the voting results. It then created a *new, final answer* that integrated the best elements from all participants. The final output explicitly states it is "**integrating all agents’ highlights**" and combines the policy news from Agent 1, the research breakthroughs from Agent 2, and the sourced consumer news from Agent 3 into a single, cohesive, and comprehensive summary.

## Conclusion

This case study demonstrates a sophisticated feature of MassGen. When a simple consensus isn't possible, the system doesn't fail; it intelligently leverages the diverse outputs to create a synthesized result that is more complete and well-rounded than any single agent's initial response. This makes it exceptionally powerful for exploring complex, subjective topics where multiple viewpoints are not just valid, but essential for a full understanding.