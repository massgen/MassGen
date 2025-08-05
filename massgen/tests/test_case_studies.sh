#!/bin/bash
# MassGen Case Study Test Commands
# Based on the original case studies from docs/case_studies/

echo "🚀 MassGen Case Study Test Suite"
echo "===================================="
echo ""

# Set absolute paths for configs
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
CONFIG_PATH="$PROJECT_ROOT/massgen/configs"

# Verify we have the right directory structure
if [ ! -d "$CONFIG_PATH" ]; then
    echo "❌ Cannot find configs directory at: $CONFIG_PATH"
    exit 1
fi

# Check for required API keys
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY not set. Some tests may fail."
fi

if [ -z "$XAI_API_KEY" ]; then
    echo "⚠️  Warning: XAI_API_KEY not set. Grok-based tests will fail."
fi

echo "📋 Available Case Studies:"
echo "1. Collaborative Creative Writing"
echo "2. AI News Synthesis"
echo "3. Grok HLE Cost Estimation"
echo "4. IMO 2025 Winner"
echo "5. Stockholm Travel Guide"
echo ""

# Function to run a test case
run_test() {
    local test_name="$1"
    local config="$2"
    local prompt="$3"
    
    echo "🔷 Running: $test_name"
    echo "📁 Config: $config"
    echo "❓ Prompt: $prompt"
    echo "---"
    
    # Run with proper Python path setup
    PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" python -m massgen.cli --config "$config" "$prompt"
    
    echo ""
    echo "✅ Completed: $test_name"
    echo "=================================="
    echo ""
}

# Case Study 1: Collaborative Creative Writing
echo "🎨 Case Study 1: Collaborative Creative Writing"
echo "Original: Used gpt-4o, gemini-2.5-flash, grok-3-mini"
echo "Adapted: Using creative_team.yaml (storyteller, editor, critic)"
read -p "Press Enter to run or Ctrl+C to skip..."
run_test "Creative Writing" \
    "$CONFIG_PATH/creative_team.yaml" \
    "Write a short story about a robot who discovers music."

# Case Study 2: AI News Synthesis
echo "📰 Case Study 2: AI News Synthesis"
echo "Original: Used gpt-4.1, gemini-2.5-flash, grok-3-mini"
echo "Adapted: Using news_analysis.yaml (news_gatherer, trend_analyst, news_synthesizer)"
read -p "Press Enter to run or Ctrl+C to skip..."
run_test "News Synthesis" \
    "$CONFIG_PATH/news_analysis.yaml" \
    "find big AI news this week"

# Case Study 3: Grok HLE Cost Estimation
echo "💰 Case Study 3: Grok HLE Cost Estimation"
echo "Original: Used gpt-4o, gemini-2.5-flash, grok-3-mini"
echo "Adapted: Using technical_analysis.yaml (technical_researcher, cost_analyst, technical_advisor)"
read -p "Press Enter to run or Ctrl+C to skip..."
run_test "Cost Estimation" \
    "$CONFIG_PATH/technical_analysis.yaml" \
    "How much does it cost to run HLE benchmark with Grok-4"

# Case Study 4: IMO 2025 Winner
echo "🏆 Case Study 4: IMO 2025 Winner"
echo "Original: Used gemini-2.5-flash, gpt-4.1 (2 agents)"
echo "Adapted: Using two_agents.yaml (primary_agent, secondary_agent)"
read -p "Press Enter to run or Ctrl+C to skip..."
run_test "IMO Winner" \
    "$CONFIG_PATH/two_agents.yaml" \
    "give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025"

# Case Study 5: Stockholm Travel Guide
echo "✈️ Case Study 5: Stockholm Travel Guide"
echo "Original: Used gemini-2.5-flash, gpt-4o (2 agents)"
echo "Adapted: Using travel_planning.yaml (travel_researcher, local_expert, travel_planner)"
read -p "Press Enter to run or Ctrl+C to skip..."
run_test "Travel Guide" \
    "$CONFIG_PATH/travel_planning.yaml" \
    "what's best to do in Stockholm in October 2025"

echo "🎉 All case studies completed!"
echo ""
echo "📊 Alternative configurations you can try:"
echo "• $CONFIG_PATH/multi_agent.yaml - Mixed OpenAI + Grok (3 agents)"
echo "• $CONFIG_PATH/multi_agent_oai.yaml - All OpenAI agents (3 agents)"
echo "• $CONFIG_PATH/research_team.yaml - Research-optimized (3 agents)"
echo "• $CONFIG_PATH/single_agent.yaml - Single agent mode"
echo ""
echo "💡 Example alternative commands:"
echo "PYTHONPATH=$PROJECT_ROOT python -m massgen.cli --config $CONFIG_PATH/research_team.yaml \"your question\""
echo "PYTHONPATH=$PROJECT_ROOT python -m massgen.cli --config $CONFIG_PATH/multi_agent.yaml \"your question\""