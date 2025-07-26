#!/usr/bin/env python3
"""
Example usage of MassGen v0.0.2 New Architecture

This example shows how to use the new ChatAgent interface and SimpleAgent
implementation with the modern async streaming architecture.
"""

import asyncio
import os


async def basic_usage_example():
    """Basic usage example with SimpleAgent."""
    from massgen import create_simple_agent, StreamChunk
    
    print("🚀 MassGen v0.0.2 - Basic Usage Example\n")
    
    # Check if we have an OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  No OpenAI API key found in environment.")
        print("💡 To run this example with real API calls, set OPENAI_API_KEY environment variable.")
        print("🎯 For now, showing architecture and interface demonstration...\n")
        
        # Show interface demonstration
        agent = create_simple_agent(
            agent_id="demo_assistant",
            model="gpt-4o-mini",
            system_message="You are a helpful AI assistant."
        )
        
        print(f"✅ Created agent: {agent.agent_id}")
        print(f"📊 Agent status: {agent.get_status()}")
        print(f"🔧 Backend provider: {agent.backend.get_provider_name()}")
        return
    
    # Real usage with API calls
    print("🔑 OpenAI API key found - running live example...\n")
    
    # Create a simple agent
    agent = create_simple_agent(
        agent_id="helpful_assistant",
        model="gpt-4o-mini",
        system_message="You are a helpful AI assistant. Keep responses concise and friendly."
    )
    
    print(f"✅ Created agent: {agent.agent_id}")
    print(f"🔧 Backend: {agent.backend.get_provider_name()}")
    
    # Define conversation messages
    messages = [
        {"role": "user", "content": "Hello! Can you explain what makes a good AI assistant?"}
    ]
    
    print("\n💬 Starting conversation...")
    print("📝 Agent response:")
    
    # Stream the response
    full_response = ""
    async for chunk in agent.chat(messages):
        if chunk.type == "content" and chunk.content:
            full_response += chunk.content
            print(chunk.content, end="", flush=True)
        elif chunk.type == "done":
            print(f"\n\n✅ [{chunk.source}] Conversation completed")
        elif chunk.type == "error":
            print(f"\n❌ [{chunk.source}] Error: {chunk.error}")
    
    # Show final status
    status = agent.get_status()
    print(f"\n📊 Final agent status:")
    print(f"  - Status: {status['status']}")
    print(f"  - Token usage: {status['token_usage']['total_tokens']} tokens")
    print(f"  - Estimated cost: ${status['token_usage']['estimated_cost']:.4f}")


async def team_collaboration_example():
    """Example showing multiple agents working together."""
    from massgen import create_agent_team
    
    print("\n\n🤝 Team Collaboration Example")
    print("=" * 50)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Skipping team example - no API key found")
        return
    
    # Create a team of specialized agents
    agent_configs = [
        {
            "agent_id": "researcher",
            "model": "gpt-4o-mini",
            "system_message": "You are a research specialist. Focus on gathering and analyzing information."
        },
        {
            "agent_id": "writer",
            "model": "gpt-4o-mini", 
            "system_message": "You are a technical writer. Focus on clear, well-structured explanations."
        },
        {
            "agent_id": "reviewer",
            "model": "gpt-4o-mini",
            "system_message": "You are a quality reviewer. Focus on accuracy and clarity."
        }
    ]
    
    team = create_agent_team(agent_configs)
    print(f"✅ Created team with {len(team)} agents:")
    for agent_id in team.keys():
        print(f"  - {agent_id}")
    
    # Example task for each agent
    task = "Explain the concept of async programming in Python in 2-3 sentences."
    
    print(f"\n📋 Task: {task}")
    print("\n👥 Team responses:")
    
    for agent_id, agent in team.items():
        print(f"\n🤖 {agent_id.upper()}:")
        messages = [{"role": "user", "content": task}]
        
        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                print(chunk.content, end="", flush=True)
            elif chunk.type == "done":
                print(f" ✓")
                break


async def streaming_features_example():
    """Example showing streaming features and real-time updates."""
    from massgen import create_simple_agent
    
    print("\n\n🌊 Streaming Features Example")
    print("=" * 50)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Skipping streaming example - no API key found")
        return
    
    agent = create_simple_agent(
        agent_id="streaming_demo",
        model="gpt-4o-mini",
        system_message="You are demonstrating streaming responses. Be descriptive about your thinking process."
    )
    
    messages = [
        {"role": "user", "content": "Write a short creative story about a robot learning to paint. Show your creative process step by step."}
    ]
    
    print("🎨 Creative writing with live streaming:")
    print("=" * 40)
    
    chunk_count = 0
    start_time = asyncio.get_event_loop().time()
    
    async for chunk in agent.chat(messages):
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - start_time
        
        if chunk.type == "content" and chunk.content:
            chunk_count += 1
            # Show streaming in real-time with timestamps
            print(chunk.content, end="", flush=True)
            
        elif chunk.type == "agent_status":
            print(f"\n[{elapsed:.1f}s] 📊 Status: {chunk.status}")
            
        elif chunk.type == "done":
            print(f"\n\n[{elapsed:.1f}s] ✅ Story completed!")
            print(f"📈 Received {chunk_count} content chunks")
            break
        
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")


async def main():
    """Run all examples."""
    await basic_usage_example()
    await team_collaboration_example() 
    await streaming_features_example()
    
    print("\n" + "="*60)
    print("🎉 MassGen v0.0.2 examples completed!")
    print("📚 Key features demonstrated:")
    print("  ✅ Unified ChatAgent interface")
    print("  ✅ Async streaming responses")
    print("  ✅ String-based semantic agent IDs")
    print("  ✅ Token usage tracking")
    print("  ✅ Multi-agent team creation")
    print("  ✅ Real-time streaming with timestamps")


if __name__ == "__main__":
    asyncio.run(main())