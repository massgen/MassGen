# MassGen v3 Case Study Test Commands

This document contains commands to test all the case studies from `docs/case_studies/` using the current v3 implementation.

## Quick Commands

### 1. Collaborative Creative Writing
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/creative_team.yaml "Write a short story about a robot who discovers music."

# From tests directory:
python ../cli.py --config ../configs/creative_team.yaml "Write a short story about a robot who discovers music."
```
**Original:** gpt-4o, gemini-2.5-flash, grok-3-mini  
**Adapted:** storyteller (gpt-4o), editor (gpt-4o-mini), critic (grok-3-mini)  
**Temperature:** 0.8 (creative)

### 2. AI News Synthesis
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/news_analysis.yaml "find big AI news this week"

# From tests directory:
python ../cli.py --config ../configs/news_analysis.yaml "find big AI news this week"
```
**Original:** gpt-4.1, gemini-2.5-flash, grok-3-mini  
**Adapted:** news_gatherer (gpt-4o), trend_analyst (grok-3-mini), news_synthesizer (gpt-4o-mini)  
**Temperature:** 0.4 (balanced)

### 3. Grok HLE Cost Estimation
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/technical_analysis.yaml "How much does it cost to run HLE benchmark with Grok-4"

# From tests directory:
python ../cli.py --config ../configs/technical_analysis.yaml "How much does it cost to run HLE benchmark with Grok-4"
```
**Original:** gpt-4o, gemini-2.5-flash, grok-3-mini  
**Adapted:** technical_researcher (gpt-4o), cost_analyst (grok-3-mini), technical_advisor (grok-4o-mini)  
**Temperature:** 0.2 (precise)

### 4. IMO 2025 Winner
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/two_agents.yaml "Which AI won IMO 2025?"

# From tests directory:
python ../cli.py --config ../configs/two_agents.yaml "Which AI won IMO 2025?"
```
**Original:** gemini-2.5-flash, gpt-4.1 (2 agents)  
**Adapted:** primary_agent (gpt-4o), secondary_agent (gpt-4o-mini)  
**Temperature:** 0.5 (neutral)

### 5. Stockholm Travel Guide
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/travel_planning.yaml "what's best to do in Stockholm in October 2025"

# From tests directory:
python ../cli.py --config ../configs/travel_planning.yaml "what's best to do in Stockholm in October 2025"
```
**Original:** gemini-2.5-flash, gpt-4o (2 agents)  
**Adapted:** travel_researcher (gpt-4o), local_expert (grok-3-mini), travel_planner (gpt-4o-mini)  
**Temperature:** 0.6 (balanced creativity)

## Alternative Configurations

### General Multi-Agent (Mixed OpenAI + Grok)
```bash
python massgen/v3/cli.py --config massgen/v3/configs/multi_agent.yaml "your question here"
```
**Agents:** researcher (gpt-4o-mini), analyst (grok-3-mini), communicator (gpt-4o-mini)

### All OpenAI Agents
```bash
python massgen/v3/cli.py --config massgen/v3/configs/multi_agent_oai.yaml "your question here"
```
**Agents:** researcher, analyst, communicator (all gpt-4o-mini)

### Research Team
```bash
python massgen/v3/cli.py --config massgen/v3/configs/research_team.yaml "your question here"
```
**Agents:** information_gatherer (grok-3-mini), domain_expert (gpt-4o), synthesizer (gpt-4o-mini)  
**Features:** Web search enabled, lower temperature (0.3)

### Single Agent
```bash
python massgen/v3/cli.py --config massgen/v3/configs/single_agent.yaml "your question here"
```
**Agent:** assistant (gpt-4o-mini)

## Running All Tests

Use the interactive test script:
```bash
# From project root:
./massgen/v3/tests/test_case_studies.sh

# From tests directory:
./test_case_studies.sh
```

## Requirements

- **OpenAI API Key:** Set `OPENAI_API_KEY` environment variable
- **Grok API Key:** Set `XAI_API_KEY` environment variable (for Grok-based configs)

## Notes

- Original case studies used Gemini models which are not yet supported in v3
- Adapted configurations use equivalent model combinations with OpenAI and Grok
- Temperature settings are optimized per use case:
  - Creative tasks: 0.8
  - Technical analysis: 0.2  
  - News/travel: 0.4-0.6
  - General: 0.5
- All configurations include proper agent role specialization matching the original case study intents