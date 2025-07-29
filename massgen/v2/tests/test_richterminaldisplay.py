#!/usr/bin/env python3
"""
Test RichTerminalDisplay implementation.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent, create_orchestrator, OrchestratorConfig, stream_coordination
from massgen.v2.frontend.displays import RichTerminalDisplay


async def test_richterminaldisplay():
    """Test RichTerminalDisplay with orchestrator functionality."""
    print("🎭 Testing RichTerminalDisplay")
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
    
    # Create orchestrator configuration  
    orchestrator_config = OrchestratorConfig(
        orchestrator_id="richterminaldisplay_orchestrator",
        max_duration=10,  # 10 seconds for multi-agent coordination
    )
    
    # Create orchestrator with multiple agents
    agents_dict = {
        "math_expert": math_agent,
        "science_expert": science_agent,
        "writing_expert": writing_agent
    }
    
    orchestrator = create_orchestrator(
        agents=agents_dict,
        orchestrator_id="richterminaldisplay_orchestrator",
        config=orchestrator_config.to_dict()
    )
    
    print(f"✅ Created orchestrator with {len(agents_dict)} agents")
    for agent_id, agent in agents_dict.items():
        print(f"📊 Agent: {agent_id} (gpt-4o-mini)")
    print(f"🔧 Orchestrator Status: {orchestrator.get_status()['workflow_phase']}")
    
    # Create RichTerminalDisplay instance with silent mode
    display = RichTerminalDisplay(
        display_enabled=True,
        max_lines=5,
        save_logs=False,  # Disable file logs for cleaner test
        silent_mode=True,  # Enable silent mode to suppress intermediate logs
        show_agent_prefixes=True,
        show_events=True,
        show_timestamps=False
    )
    
    print(f"🖥️  Created RichTerminalDisplay with silent mode enabled")
    
    # Test questions specifically for RichTerminalDisplay
    test_questions = [
        "What is the square root of 256?",
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n" + "=" * 60)
        print(f"🔍 Test {i}/1: {question}")
        print(f"📝 Using RichTerminalDisplay for coordination...")
        print()
        
        # Initialize display
        agent_ids = list(agents_dict.keys())
        display.initialize(question, agent_ids)
        
        # Test display content methods
        display.display_content("orchestrator", f"Starting coordination for: {question}")
        display.display_content("math_expert", "Analyzing mathematical problem...")
        display.display_content("science_expert", "Checking for scientific context...")
        display.display_content("writing_expert", "Reviewing question clarity...")
        
        # Update agent statuses
        display.update_agent_status("math_expert", "working")
        display.update_agent_status("science_expert", "working") 
        display.update_agent_status("writing_expert", "working")
        
        # Simulate some agent output
        display.stream_output_sync("math_expert", "The square root of 256 is 16.")
        display.stream_output_sync("science_expert", "This is a basic mathematical calculation.")
        display.stream_output_sync("writing_agent", "The question is clear and well-formed.")
        
        # Update final statuses
        display.update_agent_status("math_expert", "voted")
        display.update_agent_status("science_expert", "voted")
        display.update_agent_status("writing_expert", "voted")
        
        # Show final summary
        display.show_final_summary()
        
        # Show status after each question
        status = orchestrator.get_status()
        print(f"\n📊 Question {i} Status:")
        print(f"  - Selected Agent: {status.get('selected_agent', 'None')}")
        print(f"  - Phase: {status['workflow_phase']}")
    
    # Test cleanup
    display.cleanup()
    
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
    
    print(f"\n🎉 RichTerminalDisplay test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_richterminaldisplay())