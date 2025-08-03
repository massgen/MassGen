#!/usr/bin/env python3
"""
Test script for MassGen v3 two-agent coordination with terminal display.
Tests orchestrator coordination between two agents with different expertise.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.openai_backend import OpenAIBackend
from massgen.chat_agent import SingleAgent
from massgen.orchestrator import MassOrchestrator
from massgen.frontend.coordination_ui import CoordinationUI


async def test_two_agents_coordination():
    """Test two-agent coordination with different expertise areas."""
    print("🚀 MassGen - Two Agents Coordination Test")
    print("=" * 60)
    
    # Check if API key is available
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment variables")
        print("⚠️  Set OPENAI_API_KEY to test two-agent coordination")
        return False
    
    try:
        # Create backend
        backend = OpenAIBackend(api_key=api_key)
        
        # Create two agents with different expertise
        scientist = SingleAgent(
            backend=backend,
            agent_id="scientist",
            system_message="You are a brilliant scientist who excels at explaining complex scientific concepts clearly and accurately. Focus on scientific accuracy and clear explanations."
        )
        
        educator = SingleAgent(
            backend=backend,
            agent_id="educator", 
            system_message="You are an experienced educator who specializes in making complex topics accessible to students. Focus on pedagogical clarity and engaging explanations."
        )
        
        # Create orchestrator with two agents
        agents = {
            "scientist": scientist,
            "educator": educator
        }
        
        orchestrator = MassOrchestrator(agents=agents)
        
        # Create UI for coordination display
        ui = CoordinationUI(display_type="terminal", logging_enabled=True)
        
        print("👥 Created two-agent system:")
        print("   🔬 Scientist - Scientific accuracy and explanations")
        print("   🎓 Educator - Pedagogical clarity and accessibility")
        print()
        
        # Test question that benefits from both perspectives
        test_question = "How does photosynthesis work and why is it important for life on Earth?"
        
        print(f"📝 Question: {test_question}")
        print("\n🎭 Starting two-agent coordination...")
        print("=" * 60)
        
        # Coordinate with UI (returns final response)
        final_response = await ui.coordinate(orchestrator, test_question)
        
        print("\n" + "=" * 60)
        print("✅ Two-agent coordination completed successfully!")
        print(f"📄 Final response length: {len(final_response)} characters")
        
        return True
        
    except Exception as e:
        print(f"❌ Two-agent coordination test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_two_agents_simple():
    """Simple two-agent test without UI for basic functionality verification."""
    print("\n🧪 Simple Two-Agent Test (No UI)")
    print("-" * 40)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping simple test")
        return False
    
    try:
        backend = OpenAIBackend(api_key=api_key)
        
        # Create minimal agents
        agent1 = SingleAgent(
            backend=backend,
            agent_id="analyst",
            system_message="You are a data analyst. Provide analytical insights."
        )
        
        agent2 = SingleAgent(
            backend=backend,
            agent_id="reviewer",
            system_message="You are a reviewer. Provide critical evaluation."
        )
        
        orchestrator = MassOrchestrator(agents={"analyst": agent1, "reviewer": agent2})
        
        print("📤 Testing simple coordination...")
        
        messages = [{"role": "user", "content": "What are the benefits of renewable energy?"}]
        
        response_content = ""
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return False
            elif chunk.type == "done":
                break
        
        print(f"\n✅ Simple test completed. Response length: {len(response_content)} characters")
        return True
        
    except Exception as e:
        print(f"❌ Simple two-agent test failed: {e}")
        return False


async def main():
    """Run two-agent coordination tests."""
    print("🚀 MassGen - Two Agents Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run simple test first
    results.append(await test_two_agents_simple())
    
    # Run full coordination test
    if results[0]:  # Only run if simple test passes
        results.append(await test_two_agents_coordination())
    else:
        print("⚠️  Skipping full coordination test due to simple test failure")
        results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"✅ Passed: {sum(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("🎉 All two-agent tests passed!")
        print("✅ Two-agent coordination is working correctly")
    else:
        print("⚠️  Some tests failed - check API key and network connection")


if __name__ == "__main__":
    asyncio.run(main())