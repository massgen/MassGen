# MassGen Case Study: Collaborative Monte Carlo Simulation

This case study demonstrates MassGen's ability to handle complex technical requests requiring actual computation and simulation, showcasing how agents can distinguish between theoretical explanations and practical execution.

## Command:
```bash
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "estimate the price of NVIDIA 5 years from now through actual simulation, not just talking about simulation"
```

**Prompt:** estimate the price of NVIDIA 5 years from now through actual simulation, not just talking about simulation

**Configuration File (gemini_4o_claude.yaml):**
*Note: All agents have code execution capabilities enabled*

```yaml
agents:
  - id: "gemini2.5flash"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_web_search: true
      enable_code_execution: true

  - id: "gpt-4o"
    backend:
      type: "openai"
      model: "gpt-4o"
      enable_web_search: true
      enable_code_interpreter: true

  - id: "claude-3-5-haiku"
    backend:
      type: "claude"
      model: "claude-3-5-haiku-20241022"
      enable_web_search: true
      enable_code_execution: true

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

**Agents:**
* Agent 1: gemini2.5flash (Designated Representative Agent)
* Agent 2: gpt-4o
* Agent 3: claude-3-5-haiku

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/RPg0ybUtl04/0.jpg)](https://www.youtube.com/watch?v=RPg0ybUtl04)

---

## The Collaborative Process

### Initial Challenge: Theory vs. Practice
The user's prompt presented a critical distinction that tested each agent's ability to deliver actual computational results rather than theoretical explanations. The phrase "not just talking about simulation" created a clear evaluation criterion for the agents.

### Divergent Approaches to Simulation

**Agent 1 (gemini2.5flash)** took the most comprehensive approach:
- Initially attempted to use external libraries (yfinance) but gracefully handled the limitation
- Performed an actual Monte Carlo simulation using realistic market parameters
- Provided concrete numerical results: Mean price $6,431.94, Median $4,575.57, with 10th-90th percentile range of $1,604.92-$12,873.79
- Used sophisticated parameters: 72.79% annualized drift and 36.92% volatility based on recent market data

**Agent 2 (gpt-4o)** provided a hybrid approach:
- Offered theoretical framework with Geometric Brownian Motion explanation
- Supplied Python code that users could execute independently
- Did not perform the actual simulation within the environment
- Focused on methodology and implementation details

**Agent 3 (claude-3-5-haiku)** attempted practical execution but with limitations:
- Conducted web searches for current market data
- Performed a Monte Carlo simulation but with questionable parameters
- Used an unrealistically low volatility (1.70%) that produced conservative results
- Generated visualizations and provided contextual market analysis

### The Unanimous Consensus
Unlike previous case studies with split decisions, this session achieved a rare unanimous consensus (3/3 votes) for Agent 1's approach. The voting reflected clear technical evaluation criteria:

**Agent 1's self-assessment:** Emphasized that it "performed an actual simulation and provided results" while Agent 2 "only described the simulation process without executing it."

**Agent 2's vote change:** Initially supported its own methodological approach but ultimately recognized Agent 1's superior execution of the actual simulation requirement.

**Agent 3's validation:** Praised Agent 1's "comprehensive and rigorous simulation" with "realistic parameters" that "align with expert forecasts."

---

## The Final Answer: Technical Excellence

**Agent 1** was selected to present the final answer, which featured:

### Methodology Transparency
- Clear explanation of Geometric Brownian Motion (GBM) model
- Mathematical formula presentation with variable definitions
- Detailed parameter estimation methodology

### Realistic Market Parameters
- Starting Price: $178.50 (current market data)
- Annualized Drift: 72.79% (reflecting NVIDIA's recent performance)
- Annualized Volatility: 36.92% (based on market analysis)
- 1,000 simulations over 1,260 trading days (5 years)

### Concrete Results
- **Mean Simulated Price:** $6,545.33
- **Median Simulated Price:** $4,802.88
- **80% Confidence Interval:** $1,751.84 - $13,198.02

### Contextual Analysis
- Discussion of NVIDIA's market position in AI and semiconductors
- Acknowledgment of model limitations and assumptions
- Clear disclaimers about probabilistic nature vs. guarantees

---

## Conclusion

This case study highlights MassGen's effectiveness in technical domains where the distinction between explanation and execution is crucial. The system successfully:

1. **Interpreted user intent accurately** - Understanding that "actual simulation" meant computational execution, not theoretical description
2. **Evaluated technical competency** - Agents could assess the quality and realism of simulation parameters
3. **Achieved unanimous technical consensus** - All agents recognized the superior approach when technical criteria were clear
4. **Delivered actionable results** - Provided specific numerical forecasts with appropriate uncertainty quantification

The case demonstrates MassGen's strength in collaborative technical problem-solving, where multiple agents can contribute different expertise (market research, methodology, execution) while converging on the most technically sound solution. This makes it particularly valuable for quantitative analysis tasks requiring both domain knowledge and computational execution.
