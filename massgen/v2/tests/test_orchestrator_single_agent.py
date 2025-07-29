#!/usr/bin/env python3
"""
Test orchestrator with a single gpt-4o-mini agent.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent, create_orchestrator, OrchestratorConfig, stream_coordination


async def test_orchestrator_single_agent():
    """Test orchestrator functionality with a single gpt-4o-mini agent."""
    print("🎭 Testing Orchestrator with Single gpt-4o-mini Agent")
    print("=" * 60)
    
    # Create single agent
    agent = create_simple_agent(
        agent_id="solo_agent",
        model="gpt-4o-mini",
        system_message="You are a helpful math tutor."
    )
    
    # Create orchestrator configuration
    orchestrator_config = OrchestratorConfig(
        orchestrator_id="single_agent_orchestrator",
        max_duration=5,  # 5 seconds
    )
    
    # Create orchestrator with single agent
    orchestrator = create_orchestrator(
        agents={"solo_agent": agent},
        orchestrator_id="single_agent_orchestrator",
        config=orchestrator_config.to_dict()
    )
    
    print(f"✅ Created orchestrator with 1 agent")
    print(f"📊 Agent: {agent.agent_id} (gpt-4o-mini)")
    print(f"🔧 Orchestrator Status: {orchestrator.get_status()['workflow_phase']}")
    
    # Use streaming frontend for coordination
    question = "What is 2 + 2?"
    print(f"\n📝 Using streaming frontend for coordination...")
    print()
    
    full_response = await stream_coordination(
        orchestrator, 
        question,
        show_agent_prefixes=True,
        show_events=True
    )
    
    # Show final status
    final_status = orchestrator.get_status()
    print(f"\n📊 Final Status:")
    print(f"  - Orchestrator ID: {final_status['orchestrator_id']}")
    print(f"  - Phase: {final_status['workflow_phase']}")
    print(f"  - Agents: {len(final_status['sub_agents'])}")
    print(f"  - Selected Agent: {final_status.get('selected_agent', 'None')}")
    
    # Show agent status
    agent_status = agent.get_status()
    print(f"\n🤖 Agent Status:")
    print(f"  - Agent ID: {agent_status['agent_id']}")
    print(f"  - Status: {agent_status['status']}")
    
    print(f"\n🎉 Orchestrator single agent test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_orchestrator_single_agent())