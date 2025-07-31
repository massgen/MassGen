# **MassGen Case Study: Ask for ODSC Conference Talks**

This case study demonstrates **MassGen's** ability to handle complex research queries by leveraging multiple agents to systematically gather, organize, and synthesize comprehensive information on a specialized technical topic.

**Command:**  
```python cli.py --config examples/fast_config.yaml "give me all the talks on agent frameworks in ODSC Agentic AI Summit 2025"```

**Agents:**

- **Agent 1:** gpt-4o
- **Agent 2:** gemini-2.5-flash (**Designated Representative Agent**)
- **Agent 3:** grok-3-mini

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/6ddfpZe45G4/0.jpg)](https://www.youtube.com/watch?v=6ddfpZe45G4)

## **The Collaborative Process**

### **Initial Information Gathering and Divergent Approaches**
Each agent approached the research query with different strategies and depths of investigation:

- **Agent 1 (gpt-4o)** provided a focused list of 5 specific talks with detailed speaker information and session overviews, emphasizing frameworks like **AG2**, **LangGraph**, and **MongoDB integrations**.
- **Agent 2 (gemini-2.5-flash)** took a systematic, comprehensive approach, organizing talks by the summit's actual weekly structure and providing extensive details on 15+ sessions, including frameworks like **CrewAI**, **Google ADK**, **MCP**, and **Vertex AI Agent Engine**.
- **Agent 3 (grok-3-mini)** started with a narrow focus on one key talk but through two iterations expanded to provide a structured overview by weeks, though with less detail than the other agents.

### **Dynamic Refinement and Cross-Agent Intelligence**
A key feature of this session was the iterative refinement process:

- **Agent 2** updated its answer significantly, expanding from 3,734 to 6,072 characters, incorporating additional frameworks and session details.
- **Agent 1** also refined its response, updating twice to provide more comprehensive coverage while maintaining its structured approach.
- **Agent 3** showed the most dramatic evolution, updating from a brief 423-character response to a more structured 750-character overview.

### **The Voting Pattern: Recognition of Quality**
The voting process revealed a clear recognition of comprehensive research quality:

- **Initial Self-Confidence:** All agents initially voted for their own answers, reflecting confidence in their different approaches.
- **Quality Recognition:** **Agent 1** changed its vote from self-voting to supporting **Agent 2**, explicitly noting **Agent 2's** "comprehensive list" and "detailed descriptions of sessions and relevant frameworks."
- **Consistent Quality Assessment:** **Agent 3** consistently voted for **Agent 2** across all three votes, praising its "comprehensive and well-structured" response with "detailed breakdown of talks by week."
- **Final Consensus:** **Agent 2** achieved unanimous support (3 out of 3 votes), demonstrating clear recognition of superior research quality.

### **The Final Answer: Research Excellence**
**Agent 2's** answer was selected as the final output, featuring:

- **Systematic Organization:** Talks organized by the summit's actual weekly structure
- **Comprehensive Coverage:** 15+ sessions across multiple weeks with detailed descriptions
- **Framework Specificity:** Explicit mention of relevant frameworks for each session (**CrewAI**, **AG2**, **LangGraph**, **MCP**, **Google ADK**, etc.)
- **Speaker Information:** Detailed speaker credentials and affiliations
- **Practical Value:** Direct links to official resources and actionable information

## **Conclusion**
This case study showcases **MassGen's** exceptional ability to handle complex research queries requiring comprehensive information gathering. The system's strength lies not just in aggregating multiple perspectives, but in its agents' ability to recognize and converge on the highest quality research output. **Agent 2's** systematic, well-organized approach ultimately won unanimous support, demonstrating how **MassGen** can identify and promote superior research methodology even in specialized technical domains. This makes it particularly powerful for academic research, event planning, and comprehensive information synthesis tasks.
