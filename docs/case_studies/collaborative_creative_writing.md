# MassGen Case Study: Collaborative Creative Writing

This case study demonstrates MassGen's ability to facilitate collaborative creative writing, leading to a consensus on the most compelling narrative.

**Command:**
```bash
uv run python cli.py --config examples/fast_config.yaml "Write a short story about a robot who discovers music."
```

**Prompt:** `Write a short story about a robot who discovers music.`

**Agents:**
*   Agent 1: `gpt-4o` (Designated Representative Agent)
*   Agent 2: `gemini-2.5-flash`
*   Agent 3: `grok-3-mini`

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/vixSMvJ9UoU/0.jpg)](https://www.youtube.com/watch?v=vixSMvJ9UoU)

## The Collaborative Process

### Initial Creative Outputs

Each agent generated a unique short story based on the prompt:

*   **Agent 1 (gpt-4o)** crafted a story about a robot named Evo in Neo-Tokyo who stumbles upon a hidden record shop and discovers music through an old phonograph and a human, Mr. Tanaka. The story emphasizes emotional growth and connection.
*   **Agent 2 (gemini-2.5-flash)** created a narrative about Unit 734, or "Seven," a logic-driven robot that detects an unusual sonic anomaly in a derelict dwelling, leading to the discovery of music and a profound, inexplicable feeling.
*   **Agent 3 (grok-3-mini)** wrote about Echo, a maintenance robot in Neo-City, who encounters a street musician playing a violin in a forgotten alley. Echo learns to improvise and finds choice and creation through music.

### The Vote: Converging on the Best Narrative

This session showcased a clear convergence towards a single best answer, even in a creative task:

1.  **Agent 2** initially voted for its own story, believing it to be the most compelling.
2.  **Agent 1** voted for its own story, citing its completeness, emotional depth, and well-structured narrative.
3.  However, upon reviewing all submissions, **Agent 2 changed its vote to Agent 1's story**, acknowledging its superior structure, emotional resonance, and compelling narrative arc.
4.  **Agent 3** also voted for **Agent 1's story**, praising its completeness, vivid details, human-robot interaction, and overall polish.

This resulted in a strong consensus for Agent 1's story (3 out of 3 votes).

## The Final Answer

Agent 1's story, "Evo's Discovery," was chosen as the final output due to the unanimous consensus. It is a well-developed narrative that effectively addresses the prompt, demonstrating the capacity of MassGen to identify and select high-quality creative content through agent collaboration.

## Conclusion

This case study highlights MassGen's effectiveness in creative tasks. Even with subjective outputs, the multi-agent system can identify and converge on a preferred solution, leveraging the collective judgment of the agents to select the most compelling and well-executed creative piece. This demonstrates MassGen's potential beyond analytical tasks, extending to areas requiring nuanced qualitative assessment.