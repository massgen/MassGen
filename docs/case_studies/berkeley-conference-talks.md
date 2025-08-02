# MassGen Case Study: Berkeley Agent Framework Research – Precision Through Collaboration

This case study demonstrates **MassGen**'s ability to handle specialized academic queries by combining focused research with collaborative verification to produce authoritative, well-sourced answers on niche technical topics.

---

## Command

```bash
uv run python cli.py --config examples/fast_config.yaml "give me all the talks on agent frameworks at Berkeley Agentic AI Summit 2025"
```

---

## Agents

- **Agent 1**: gpt-4o  
- **Agent 2**: gemini-2.5-flash (**Designated Representative Agent**)  
- **Agent 3**: grok-3-mini

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/rH6_feyIhxE/0.jpg)](https://www.youtube.com/watch?v=rH6_feyIhxE)

---

## The Collaborative Process

### Initial Research Approaches and Information Quality

Each agent demonstrated different research methodologies and attention to detail:

- **Agent 1 (gpt-4o)** provided a **concise, accurate answer** focusing on the core _"Frameworks & Stacks for Agentic Systems"_ session, including key speakers like **Ion Stoica**, **Matei Zaharia**, and **Sherwin Wu**. The response was well-structured and included the official event link.

- **Agent 2 (gemini-2.5-flash)** delivered the **most comprehensive research**, providing detailed coverage of not just the main frameworks session but also related sessions on _"Building Infrastructure for Agents"_ and _"Foundations of Agents"_. It included specific **talk titles**, **speaker credentials**, and **panel details**.

- **Agent 3 (grok-3-mini)** took a **broader interpretive approach**, attempting to include related events and competitions, but with **less precision** in distinguishing between different summit events and their specific programming.

---

### Information Verification and Source Quality

A critical aspect of this session was the agents' ability to distinguish between different events with similar names:

- **Agent 2** explicitly noted the importance of distinguishing _"this in-person summit from other events also named 'Agentic AI Summit 2025,' which are virtual training events with different agendas."_  

This attention to detail prevented confusion between the **Berkeley academic summit** and other **commercial training events**.

---

### The Voting Pattern: Recognition of Thoroughness

The voting process demonstrated clear recognition of research quality and completeness:

- **Agent 1** initially **voted for itself**, confident in its focused, accurate answer.

- **Crucial Vote Change**:  
  Agent 1 **changed its vote** to support Agent 2, explicitly recognizing Agent 2's _"comprehensive list of all talks"_ and noting it _"includes all the speakers, session details, and additional related sessions, offering a complete view of the relevant content."_  

- **Consistent Recognition**:  
  Agent 3 **voted for Agent 2**, praising its _"thorough and accurate"_ response with a _"detailed list of talks"_ while noting Agent 2's success in _"avoiding confusion with other events."_  

- **Self-Confidence**:  
  Agent 2 **voted for itself**, citing its comprehensive coverage and correct identification of the specific summit sessions.

- **Final Result**:  
  **Agent 2 achieved majority consensus (3 out of 3 votes)**, with all agents ultimately recognizing its **superior research quality**.

---

## The Final Answer: Academic Research Excellence

**Agent 2's answer** was selected as the final output, featuring:

- **Event Precision**: Clear identification of the specific **Berkeley summit** vs. other similarly named events  
- **Comprehensive Coverage**: Three full sessions with detailed speaker lineups and talk titles  
- **Academic Credibility**: Proper attribution of speakers' academic and industry credentials  
- **Structured Organization**: Sessions organized chronologically with clear time stamps  
- **Authoritative Sources**: Distinction between official **Berkeley programming** and external events

---

## Conclusion

This case study highlights **MassGen**'s effectiveness in academic and professional research contexts where **precision** and **comprehensive coverage** are paramount. The system successfully identified and promoted the most thorough research approach, with agents demonstrating the ability to **recognize superior methodology** and **change their votes accordingly**.

**Agent 2's systematic approach** to distinguishing between similar events and providing complete session coverage ultimately earned unanimous support, showcasing how **MassGen** can produce **authoritative answers** for specialized academic queries that require **careful source verification** and **comprehensive information synthesis**.
