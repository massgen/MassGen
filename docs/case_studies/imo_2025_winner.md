# MassGen Case Study: IMO AI Winners

This case study demonstrates **MassGen**'s ability to do fact checking based on recent news and to achieve unanimous consensus on current events research, showcasing how agents can effectively collaborate to gather and verify real-time information through sophisticated web search and fact-checking. This case study was run on version v0.0.11. 

---

## Command

```bash
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "Which AI won IMO 2025?"
```

**Prompt:**  
`Which AI won IMO 2025?`

---

## Agents

- **Agent 1**: gemini-2.5-flash (**Designated Representative Agent**)  
- **Agent 2**: gpt-4o  
- **Agent 3**: claude-3-5-haiku

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/QgZJ-KnsuVc/0.jpg)](https://www.youtube.com/watch?v=QgZJ-KnsuVc)

---

## The Collaborative Process

### Research Approaches and Information Gathering

Each agent demonstrated distinct research methodologies and information verification strategies:

- **Agent 1 (gemini-2.5-flash)** conducted comprehensive multi-query web searches, performing five separate searches including "AI won IMO 2025," "IMO 2025 results AI," and "International Mathematical Olympiad 2025 AI winner." The agent demonstrated sophisticated fact-checking by distinguishing between official recognition and independent verification.

- **Agent 2 (gpt-4o)** took a focused approach with a single targeted search for "IMO 2025 AI winner," providing clear documentation of sources and emphasizing the historic nature of the achievement with proper context about official participation versus evaluation.

- **Agent 3 (claude-3-5-haiku)** performed initial broad research on general IMO 2025 results before pivoting to AI-specific queries, demonstrating adaptive research methodology and providing extensive contextual analysis about the significance of the breakthrough.

---

### Information Quality Assessment and Accuracy

A defining feature of this session was the agents' sophisticated evaluation of factual accuracy and completeness:

- **Comprehensive Coverage**: Agent 1's response was consistently praised for being _"most comprehensive, accurately listing all three AI systems that achieved gold-medal level performance"_ including Google DeepMind's Gemini Deep Think, OpenAI's experimental model, and the third system, Harmonic.

- **Source Verification**: Multiple agents noted the importance of _"correctly distinguishing between official recognition and independent verification based on search results,"_ showing sophisticated understanding of information credibility.

- **Contextual Analysis**: Agent 3's detailed research was appreciated for providing _"specific details about the scoring and the breakthrough in AI mathematical reasoning"_ and going _"beyond just stating the results."_

---

## The Voting Pattern: Unanimous Research Excellence

The voting process revealed remarkable consensus on research quality and information accuracy:

- **Self-Assessment**: Agent 1 voted for itself twice, citing comprehensive coverage and accurate distinction between different types of AI participation.

- **Cross-Agent Recognition**: Agent 2 voted for Agent 1, noting it _"provided a comprehensive answer including the names of the AI models, their accomplishments, and context on the significance of the achievement."_

- **Research Quality Validation**: Agent 3 voted for Agent 1, praising it as providing _"the most comprehensive and detailed account of the AI performance at IMO 2025"_ with context about the achievement's significance.

- **Final Unanimous Decision**: All three agents ultimately voted for Agent 1, achieving **perfect consensus (3 out of 3 votes).**

---

## The Final Answer: Research Excellence

**Agent 1** was selected to present the final answer, featuring:

- **Comprehensive Coverage**: Identification of all three AI systems that achieved gold-medal performance (Google DeepMind's Gemini Deep Think, OpenAI's experimental model, and Harmonic)
- **Accurate Distinctions**: Clear differentiation between official IMO recognition and independent verification processes
- **Technical Precision**: Specific scoring details (35 out of 42 points, solving 5 out of 6 problems)
- **Historical Context**: Recognition of this as the first official AI participation in IMO history
- **Methodological Insight**: Description of natural-language reasoning approaches and competition time constraints

---

## Conclusion

This case study showcases **MassGen**'s exceptional ability to collaborate on **up-to-date information research**, demonstrating how agents can perform **sophisticated fact-checking**, **source verification**, and **comprehensive information gathering**. The unanimous consensus reflects not just agreement, but a **shared understanding of research quality**, **factual accuracy**, and **information completeness**.

**Agent 1's response** earned recognition for its **thorough multi-source research**, **accurate fact distinction**, and **comprehensive coverage of all relevant AI systems**. This demonstrates **MassGen**'s strength in **current events research** where **factual accuracy** and **source credibility** are paramount, making it particularly valuable for **journalism**, **fact-checking**, **market research**, and any task requiring **real-time information synthesis** with high accuracy standards.

The case also highlights the system's ability to handle **rapidly evolving topics** where information may be scattered across multiple sources and requires careful verification and contextualization.
