# MassGen v3 Case Study Test Commands

This document contains commands to test all the case studies from `docs/case_studies/` using the three agents default configuration.

## Quick Commands

All tests use the `three_agents_default.yaml` configuration with:
- **Gemini 2.5 Flash** (web search enabled)
- **GPT-4o-mini** (web search + code interpreter)  
- **Grok 3 mini** (web search with citations)

### 1. Collaborative Creative Writing
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "Write a short story about a robot who discovers music."

# From tests directory:
python ../cli.py --config ../configs/three_agents_default.yaml "Write a short story about a robot who discovers music."
```
**Original:** gpt-4o, gemini-2.5-flash, grok-3-mini  
**Current:** gemini2.5flash, 4omini, grok3mini with builtin tools  

### 2. AI News Synthesis
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "find big AI news this week"

# From tests directory:
python ../cli.py --config ../configs/three_agents_default.yaml "find big AI news this week"
```
**Original:** gpt-4.1, gemini-2.5-flash, grok-3-mini  
**Current:** gemini2.5flash, 4omini, grok3mini with web search  

### 3. Grok HLE Cost Estimation
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "How much does it cost to run HLE benchmark with Grok-4"

# From tests directory:
python ../cli.py --config ../configs/three_agents_default.yaml "How much does it cost to run HLE benchmark with Grok-4"
```
**Original:** gpt-4o, gemini-2.5-flash, grok-3-mini  
**Current:** gemini2.5flash, 4omini, grok3mini with web search  

### 4. IMO 2025 Winner
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "Which AI won IMO 2025?"

# From tests directory:
python ../cli.py --config ../configs/three_agents_default.yaml "Which AI won IMO 2025?"
```
**Original:** gemini-2.5-flash, gpt-4.1 (2 agents)  
**Current:** gemini2.5flash, 4omini, grok3mini (3 agents with web search)  

### 5. Stockholm Travel Guide
```bash
# From project root:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "what's best to do in Stockholm in October 2025"

# From tests directory:
python ../cli.py --config ../configs/three_agents_default.yaml "what's best to do in Stockholm in October 2025"
```
**Original:** gemini-2.5-flash, gpt-4o (2 agents)  
**Current:** gemini2.5flash, 4omini, grok3mini with web search for current info

## Configuration Details

The `three_agents_default.yaml` configuration provides:

### Agent Capabilities
- **gemini2.5flash**: Gemini 2.5 Flash with web search
- **4omini**: GPT-4o-mini with web search + code interpreter  
- **grok3mini**: Grok 3 mini with web search and citations

### UI Features
- Rich terminal display with enhanced visualization
- Real-time coordination updates
- Logging enabled for debugging

### Custom Queries
```bash
# Use for any question with the three agents setup:
python massgen/v3/cli.py --config massgen/v3/configs/three_agents_default.yaml "your question here"
```

## Running All Tests

Use the interactive test script:
```bash
# From project root:
./massgen/v3/tests/test_case_studies.sh

# From tests directory:
./test_case_studies.sh
```

## Requirements

- **OpenAI API Key:** Set `OPENAI_API_KEY` environment variable (for GPT-4o-mini)
- **Gemini API Key:** Set `GOOGLE_API_KEY` environment variable (for Gemini 2.5 Flash)
- **Grok API Key:** Set `XAI_API_KEY` environment variable (for Grok 3 mini)

## Notes

- All tests now use the unified `three_agents_default.yaml` configuration
- Combines three different model providers for diverse perspectives
- Built-in tools (web search, code execution) available across agents
- Rich terminal UI provides enhanced visualization and real-time updates
- Each agent brings unique strengths:
  - Gemini: Advanced reasoning with web search
  - GPT-4o-mini: Cost-effective with code execution
  - Grok: Real-time information with citations