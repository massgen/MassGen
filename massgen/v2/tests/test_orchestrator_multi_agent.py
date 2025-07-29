#!/usr/bin/env python3
"""
Test orchestrator with multiple agents of different types.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent, create_orchestrator, OrchestratorConfig, stream_coordination


async def test_orchestrator_multi_agent():
    """Test orchestrator functionality with multiple agents of different types."""
    print("🎭 Testing Orchestrator with Multiple Agents")
    print("=" * 60)
    
    # Create multiple agents with different specializations
    math_agent = create_simple_agent(
        agent_id="math_expert",
        model="gpt-4o-mini",
        system_message="You are a math expert specializing in calculations and mathematical problem solving."
    )
    
    science_agent = create_simple_agent(
        agent_id="science_expert",
        model="gpt-4o-mini",
        system_message="You are a science expert specializing in physics, chemistry, and biology concepts."
    )
    
    writing_agent = create_simple_agent(
        agent_id="writing_expert",
        model="gpt-4o-mini",
        system_message="You are a writing expert specializing in grammar, composition, and creative writing."
    )
    
    general_agent = create_simple_agent(
        agent_id="general_assistant",
        model="gpt-4o-mini",
        system_message="You are a general assistant that can help with various tasks and questions."
    )
    
    # Create orchestrator configuration
    orchestrator_config = OrchestratorConfig(
        orchestrator_id="multi_agent_orchestrator",
        max_duration=10,  # 10 seconds for multi-agent coordination
    )
    
    # Create orchestrator with multiple agents
    agents_dict = {
        "math_expert": math_agent,
        "science_expert": science_agent,
        "writing_expert": writing_agent,
        "general_assistant": general_agent
    }
    
    orchestrator = create_orchestrator(
        agents=agents_dict,
        orchestrator_id="multi_agent_orchestrator",
        config=orchestrator_config.to_dict()
    )
    
    print(f"✅ Created orchestrator with {len(agents_dict)} agents")
    for agent_id, agent in agents_dict.items():
        print(f"📊 Agent: {agent_id} (gpt-4o-mini)")
    print(f"🔧 Orchestrator Status: {orchestrator.get_status()['workflow_phase']}")
    
    # Test with different types of questions
    test_questions = [
        "What is the square root of 144?",
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n" + "=" * 60)
        print(f"🔍 Test {i}/4: {question}")
        print(f"📝 Using streaming frontend for coordination...")
        print()
        
        full_response = await stream_coordination(
            orchestrator, 
            question,
            show_agent_prefixes=True,
            show_events=True
        )
        
        # Show status after each question
        status = orchestrator.get_status()
        print(f"\n📊 Question {i} Status:")
        print(f"  - Selected Agent: {status.get('selected_agent', 'None')}")
        print(f"  - Phase: {status['workflow_phase']}")
    
    # Show final comprehensive status
    final_status = orchestrator.get_status()
    print(f"\n" + "=" * 60)
    print(f"📊 Final Orchestrator Status:")
    print(f"  - Orchestrator ID: {final_status['orchestrator_id']}")
    print(f"  - Phase: {final_status['workflow_phase']}")
    print(f"  - Total Agents: {len(final_status['sub_agents'])}")
    print(f"  - Last Selected Agent: {final_status.get('selected_agent', 'None')}")
    
    # Show individual agent statuses
    print(f"\n🤖 Individual Agent Statuses:")
    for agent_id, agent in agents_dict.items():
        agent_status = agent.get_status()
        print(f"  - {agent_id}: {agent_status['status']}")
    
    print(f"\n🎉 Orchestrator multi-agent test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_orchestrator_multi_agent())