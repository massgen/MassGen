# MassGen Case Study: Constrained Research Excellence - Source Verification and Framework Precision

This case study demonstrates **MassGen**'s ability to handle specialized research queries with strict constraints, showcasing how agents can recognize and prioritize responses that precisely meet user specifications while maintaining high academic standards.

---

## Command

```bash
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025, note, the sources must include the word Berkeley, don't include talks from any other agentic AI summits"
```

**Prompt:**  
`give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025, note, the sources must include the word Berkeley, don't include talks from any other agentic AI summits`

---

## Agents

- **Agent 1**: gemini-2.5-flash (**Designated Representative Agent**)  
- **Agent 2**: gpt-4o  
- **Agent 3**: claude-3-5-haiku

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/Dp2oldJJImw/0.jpg)](https://www.youtube.com/watch?v=Dp2oldJJImw)

---

## The Collaborative Process

### Research Approaches and Constraint Adherence

Each agent demonstrated different levels of precision in adhering to the user's strict source requirements:

- **Agent 1 (gemini-2.5-flash)** focused on framework-specific talks with explicit mention of technologies like _DSPy_, _Google Agent Development Kit (ADK)_, and _Model Context Protocol (MCP)_ while carefully ensuring **Berkeley-sourced information**.

- **Agent 2 (gpt-4o)** provided **comprehensive session coverage** with detailed workshop information, organizing content by sessions and **explicitly noting Berkeley sources** in the response structure.

- **Agent 3 (claude-3-5-haiku)** took a **broader approach**, including research presentations like _SkyRL Framework_, _Maris Project_, and _CVE-Bench_, but with **less specificity** on core agent frameworks mentioned in the user's request.

---

### Critical Constraint Recognition

A defining feature of this session was the agents' ability to recognize and evaluate adherence to the user's explicit constraints:

- **Source Verification**:  
  Agent 1 explicitly acknowledged in its voting that it _"correctly ensured that the sources included the word 'Berkeley' and did not include talks from other summits, fulfilling all constraints of the original message."_

- **Framework Specificity**:  
  Agent 1's second vote specifically noted its _"more focused list of talks directly related to 'agent frameworks', explicitly mentioning specific frameworks like DSPy and the Google Agent Development Kit (ADK).”_

- **Precision Recognition**:  
  Agent 2 emphasized that its response _"ensures relevancy by explicitly mentioning Berkeley, per the original request."_

---

### The Voting Pattern: Constraint Compliance Excellence

The voting process revealed sophisticated evaluation of constraint adherence and research precision:

- **Self-Assessment with Constraint Awareness**:  
  Agent 1 voted for itself twice, with both votes explicitly referencing **constraint compliance** and **framework specificity**.

- **Quality vs. Constraint Tension**:  
  Agent 2 voted for itself, recognizing its comprehensive coverage while emphasizing **Berkeley source compliance**.

- **Cross-Agent Validation**:  
  Agent 3 voted for Agent 1, praising it for providing _"the most comprehensive and verified information about the Berkeley Agentic AI Summit 2025, with specific details about agent framework talks sourced directly from the summit's materials."_

- **Final Consensus**:  
  **Agent 1 achieved majority support (2 out of 3 votes)**, with agents specifically recognizing its **superior constraint adherence** and **framework precision**.

---

## The Final Answer: Constrained Research Mastery

**Agent 1's answer** was selected as the final output, featuring:

- **Strict Source Compliance**: All information explicitly tied to **Berkeley-sourced materials**  
- **Framework Precision**: Talk titles that explicitly mentioned specific frameworks (_DSPy_, _ADK_, _MCP_, _LlamaIndex_)  
- **Constraint Acknowledgment**: Clear distinction from other **non-Berkeley agentic AI summits**  
- **Technical Accuracy**: Proper identification of **framework-specific** versus general agentic system content  
- **Comprehensive Coverage**: Both **keynotes** and **technical sessions** while maintaining constraint adherence

---

## Conclusion

This case study showcases **MassGen**'s exceptional ability to handle research queries with **explicit constraints**, demonstrating how agents can **recognize**, **evaluate**, and **prioritize** responses that precisely meet user specifications. The system successfully identified and promoted the approach that best balanced **comprehensive research** with **strict constraint adherence**.

**Agent 1's methodology**—which explicitly tracked **constraint compliance** while maintaining **technical precision**—ultimately earned recognition from other agents who could evaluate both the **quality of research** and **adherence to user requirements**.

This demonstrates **MassGen**'s strength in academic and professional contexts where **following specific guidelines** and **constraints** is as important as **research comprehensiveness**, making it particularly valuable for **compliance-sensitive research tasks** and **constrained information gathering scenarios**.
