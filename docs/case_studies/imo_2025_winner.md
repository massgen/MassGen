# MassGen Case Study: IMO 2025 AI Winners

This case study demonstrates MassGen's ability to achieve unanimous consensus through strategic vote switching, where agents recognize and reward superior detail and structure in responses to current events queries. This case study was run on version v0.0.3.

**Command:**
```
massgen --config @examples/basic_multi_gemini_4o_claude "Which AI won IMO 2025?"
```

**Prompt:** Which AI won IMO 2025?

**Agents:**
* Agent 1: gemini2.5flash
* Agent 2: gpt-4o (Designated Winner)
* Agent 3: claude-3-5-haiku

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/JxoJoHpdWjc/0.jpg)](https://www.youtube.com/watch?v=JxoJoHpdWjc)

**Duration:** 141.0s | 735 chunks | 15 events

## The Collaborative Process

### Initial Response Diversity

Each agent approached the recent AI achievement query with different levels of detail and research depth:

* **Agent 1 (gemini2.5flash)** provided accurate foundational information, correctly identifying that both Google's Gemini Deep Think and OpenAI's experimental model achieved gold medal scores. However, its initial response lacked specific performance metrics and structural organization.

* **Agent 2 (gpt-4o)** conducted comprehensive web research and delivered a well-structured response with specific details: both models solved "five out of six problems" and achieved gold medal-level performance, with clear distinctions between official participation (Google) and independent verification (OpenAI).

* **Agent 3 (claude-3-5-haiku)** performed extensive research with detailed background context, providing rich information about IMO structure, grading processes, and broader implications, but with less concise organization.

### The Strategic Vote Switch

The voting pattern revealed a sophisticated recognition of quality and comprehensiveness:

**Initial Position:**
- Agent 1 initially voted for itself, citing accuracy in differentiating evaluation methods
- All agents provided accurate information, creating potential for close competition

**The Decisive Shift:**
- **Agent 1** switched its vote to Agent 2, explicitly stating: *"Both agents provide accurate information. Agent 2 offers slightly more detail regarding the performance metrics (number of problems solved and score), which makes it a more comprehensive answer."*
- **Agent 3** also voted for Agent 2, praising its *"more structured and concise overview"* and *"clear, balanced manner"*
- **Agent 2** voted for itself, citing its *"clear and concise comparison between Google's and OpenAI's AI models' performances"*

This resulted in a unanimous 3-0 consensus for Agent 2.

### Quality Recognition Factors

The agents specifically recognized Agent 2's superior qualities:

1. **Specific Performance Metrics:** "Five out of six problems" rather than just "gold medal scores"
2. **Clear Structural Organization:** Bullet-pointed comparison format with distinct sections for each company
3. **Balanced Coverage:** Equal treatment of both Google's and OpenAI's achievements
4. **Concise Presentation:** Streamlined information delivery without sacrificing accuracy
5. **Contextual Details:** Inclusion of verification methods and participation status

## The Final Answer

**Agent 2** presented the final response, featuring:

- **Precise Achievement Details:** Both models solved exactly 5 out of 6 IMO problems
- **Clear Differentiation:** Google's official participation vs. OpenAI's independent verification
- **Structural Clarity:** Well-organized bullet points for each company's achievement
- **Verification Context:** Explanation of how results were validated by IMO judges and former medalists
- **Broader Significance:** Positioned as a milestone in AI's complex problem-solving capabilities

## Conclusion

This case study exemplifies MassGen's effectiveness in recognizing and promoting superior response quality through strategic vote switching. Rather than agents simply defending their own answers, the system demonstrated sophisticated quality assessment where Agent 1 specifically acknowledged that Agent 2's additional detail about performance metrics made it "more comprehensive." The unanimous consensus emerged from agents recognizing concrete improvements in structure, specificity, and presentation. This showcases MassGen's strength in achieving quality-driven consensus on current events queries, where accuracy is baseline but comprehensiveness and clarity determine the winning response. The system successfully balanced factual accuracy with presentation quality, resulting in a final answer that was both informative and well-organized for optimal user understanding.
