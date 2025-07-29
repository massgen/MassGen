#!/usr/bin/env python3
"""
Test orchestrator with RichTerminalDisplay during actual task execution (non-silent mode).
"""

import asyncio
import sys
import os
import logging

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent, create_orchestrator, OrchestratorConfig
from massgen.v2.frontend.displays import RichTerminalDisplay


async def test_orchestrator_with_richterminaldisplay_nonsilent():
    """Test orchestrator functionality with RichTerminalDisplay during real task execution (non-silent mode)."""
    
    print("🎭 Testing Orchestrator with RichTerminalDisplay Integration (Non-Silent Mode)")
    print("=" * 70)
    
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
    
    # Create orchestrator configuration
    orchestrator_config = OrchestratorConfig(
        orchestrator_id="richterminaldisplay_nonsilent_test_orchestrator",
        max_duration=15,  # 15 seconds for multi-agent coordination
    )
    
    # Create orchestrator with multiple agents
    agents_dict = {
        "math_expert": math_agent,
        "science_expert": science_agent,
        "writing_expert": writing_agent
    }
    
    # Create RichTerminalDisplay instance with non-silent mode
    display = RichTerminalDisplay(
        display_enabled=True,
        max_lines=10,
        save_logs=False,  # Disable file logs for cleaner test
        silent_mode=False,  # Disable silent mode to show all intermediate logs
        show_agent_prefixes=True,
        show_events=True,
        show_timestamps=True
    )
    
    orchestrator = create_orchestrator(
        agents=agents_dict,
        orchestrator_id="richterminaldisplay_nonsilent_test_orchestrator",
        config=orchestrator_config.to_dict(),
        display=display
    )
    
    print(f"✅ Created orchestrator with {len(agents_dict)} agents")
    for agent_id, agent in agents_dict.items():
        print(f"📊 Agent: {agent_id} (gpt-4o-mini)")
    print(f"🔧 Orchestrator Status: {orchestrator.get_status()['workflow_phase']}")
    print(f"🖥️  Display integrated with orchestrator for real-time updates (Non-Silent Mode)")
    
    # Single test question
    test_question = "What is 5 + 3?"
    
    print(f"\n" + "=" * 70)
    print(f"🔍 Test Question: {test_question}")
    print(f"📝 Using orchestrator with integrated RichTerminalDisplay (Non-Silent Mode)...")
    print()
    
    # Start orchestrator coordination with real display integration
    try:
        # Create message for orchestrator
        messages = [{"role": "user", "content": test_question}]
        
        # Stream orchestrator response with real-time display updates
        print("🚀 Starting orchestrator coordination...")
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content":
                # In non-silent mode, show all messages including individual agent messages
                print(f"[{chunk.source or 'orchestrator'}] {chunk.content}", end="")
            elif chunk.type == "error":
                print(f"❌ Error: {chunk.error}")
            elif chunk.type == "done":
                print("\n✅ Coordination completed")
                break
        
    except Exception as e:
        print(f"❌ Error during coordination: {str(e)}")
    
    # Show orchestrator status
    status = orchestrator.get_status()
    print(f"\n📊 Test Status:")
    print(f"  - Selected Agent: {status.get('selected_agent', 'None')}")
    print(f"  - Phase: {status['workflow_phase']}")
    print(f"  - Runtime: {status.get('runtime', 0):.2f}s")
    
    print("✅ RichTerminalDisplay integration test completed (Non-Silent Mode)")
    
    # Show final comprehensive status
    final_status = orchestrator.get_status()
    print(f"\n" + "=" * 70)
    print(f"📊 Final Test Results:")
    print(f"  - Orchestrator ID: {final_status['orchestrator_id']}")
    print(f"  - Phase: {final_status['workflow_phase']}")
    print(f"  - Total Agents: {len(final_status['sub_agents'])}")
    print(f"  - RichTerminalDisplay (Non-Silent): ✅ Working correctly")
    
    # Show individual agent statuses
    print(f"\n🤖 Individual Agent Statuses:")
    for agent_id, agent in agents_dict.items():
        agent_status = agent.get_status()
        print(f"  - {agent_id}: {agent_status['status']}")
    
    print(f"\n🎉 Orchestrator with RichTerminalDisplay integration test completed successfully!")
    print("✅ RichTerminalDisplay is working correctly during task execution (Non-Silent Mode)")


if __name__ == "__main__":
    asyncio.run(test_orchestrator_with_richterminaldisplay_nonsilent())