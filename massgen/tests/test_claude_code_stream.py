#!/usr/bin/env python3
"""
Real test of ClaudeCodeStreamBackend with actual Claude Code API calls.
This test outputs the actual stream chunks to verify functionality.
"""

import asyncio
import os
from massgen.backend.claude_code_cli_stream import ClaudeCodeStreamBackend


async def test_real_stream_with_tools():
    """Test real streaming with Claude Code API and output stream chunks."""
    
    # Check if API key is available
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not found in environment")
        print("Set your API key: export ANTHROPIC_API_KEY=your-key-here")
        return
    
    print("🚀 Testing ClaudeCodeStreamBackend with real Claude Code API")
    print("=" * 60)
    
    # Initialize backend
    backend = ClaudeCodeStreamBackend()
    print(f"✅ Backend initialized: {backend.get_provider_name()}")
    print(f"📊 Supported tools: {len(backend.get_supported_builtin_tools())} tools")
    
    # Test single turn conversation
    print("\n🔄 Testing single turn conversation...")
    messages = [
        {"role": "user", "content": "Hello! Can you tell me what 2+2 equals and show your calculation?"}
    ]
    
    try:
        print("\n📨 Sending messages:", messages)
        print("\n📡 Stream chunks received:")
        print("-" * 40)
        
        chunk_count = 0
        total_content = ""
        
        async for chunk in backend.stream_with_tools(messages, []):
            chunk_count += 1
            print(f"[{chunk_count:2d}] Type: {chunk.type:<20} Source: {chunk.source or 'None':<20}")
            
            if chunk.type == "content":
                print(f"     Content: {repr(chunk.content)}")
                total_content += chunk.content or ""
            elif chunk.type == "complete_message":
                print(f"     Complete message: {chunk.complete_message}")
            elif chunk.type == "complete_response":
                print(f"     Response metadata: {chunk.response}")
            elif chunk.type == "agent_status":
                print(f"     Status: {chunk.status} - {chunk.content}")
            elif chunk.type == "builtin_tool_results":
                print(f"     Tool results: {chunk.builtin_tool_results}")
            elif chunk.type == "tool_calls":
                print(f"     Tool calls: {chunk.tool_calls}")
            elif chunk.type == "error":
                print(f"     Error: {chunk.error}")
            elif chunk.type == "done":
                print(f"     ✅ Stream completed")
                break
            
            print()
        
        print("-" * 40)
        print(f"📊 Total chunks: {chunk_count}")
        print(f"📝 Total content length: {len(total_content)} chars")
        print(f"💰 Token usage: {backend.get_token_usage()}")
        print(f"🔗 Session ID: {backend.get_current_session_id()}")
        
        if total_content:
            print(f"\n📄 Complete response:\n{total_content}")
        
    except Exception as e:
        print(f"❌ Error during streaming: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test multi-turn conversation
    print("\n" + "=" * 60)
    print("🔄 Testing multi-turn conversation...")
    
    # Add assistant response to conversation
    messages.append({
        "role": "assistant", 
        "content": total_content
    })
    
    # Add follow-up question
    messages.append({
        "role": "user", 
        "content": "Great! Now can you show me how to calculate the result times 5?"
    })
    
    try:
        print("\n📨 Sending multi-turn messages:")
        for i, msg in enumerate(messages):
            print(f"  [{i+1}] {msg['role']}: {msg['content'][:100]}{'...' if len(msg['content']) > 100 else ''}")
        
        print("\n📡 Stream chunks received:")
        print("-" * 40)
        
        chunk_count = 0
        turn2_content = ""
        
        async for chunk in backend.stream_with_tools(messages, []):
            chunk_count += 1
            print(f"[{chunk_count:2d}] Type: {chunk.type:<20} Source: {chunk.source or 'None':<20}")
            
            if chunk.type == "content":
                print(f"     Content: {repr(chunk.content)}")
                turn2_content += chunk.content or ""
            elif chunk.type == "complete_response":
                print(f"     Response metadata: {chunk.response}")
            elif chunk.type == "done":
                print(f"     ✅ Stream completed")
                break
            
            print()
        
        print("-" * 40)
        print(f"📊 Turn 2 chunks: {chunk_count}")
        print(f"📝 Turn 2 content length: {len(turn2_content)} chars")
        print(f"💰 Cumulative token usage: {backend.get_token_usage()}")
        print(f"🔗 Session ID: {backend.get_current_session_id()}")
        
        if turn2_content:
            print(f"\n📄 Turn 2 response:\n{turn2_content}")
        
    except Exception as e:
        print(f"❌ Error during multi-turn: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n✅ Multi-turn conversation test completed successfully!")


async def test_with_workflow_tools():
    """Test with MassGen workflow tools."""
    
    print("\n" + "=" * 60)
    print("🛠️  Testing with workflow tools...")
    
    backend = ClaudeCodeStreamBackend()
    
    # Define workflow tools
    workflow_tools = [
        {
            "type": "function",
            "function": {
                "name": "new_answer",
                "description": "Provide an improved answer to the ORIGINAL MESSAGE",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Your improved answer"
                        }
                    },
                    "required": ["content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "vote", 
                "description": "Vote for the best agent to present final answer",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID to vote for"
                        },
                        "reason": {
                            "type": "string", 
                            "description": "Reason for voting"
                        }
                    },
                    "required": ["agent_id", "reason"]
                }
            }
        }
    ]
    
    messages = [
        {"role": "user", "content": "You are participating in a multi-agent workflow. Please provide an answer about the benefits of Python programming, then use the new_answer tool to submit your response."}
    ]
    
    try:
        print(f"\n📨 Sending workflow tool message with {len(workflow_tools)} tools")
        print(f"🛠️  Tools: {[t['function']['name'] for t in workflow_tools]}")
        
        print("\n📡 Stream chunks received:")
        print("-" * 40)
        
        chunk_count = 0
        workflow_content = ""
        detected_tool_calls = []
        
        async for chunk in backend.stream_with_tools(messages, workflow_tools):
            chunk_count += 1
            print(f"[{chunk_count:2d}] Type: {chunk.type:<20} Source: {chunk.source or 'None':<20}")
            
            if chunk.type == "content":
                print(f"     Content: {repr(chunk.content)}")
                workflow_content += chunk.content or ""
            elif chunk.type == "tool_calls":
                print(f"     🛠️  Tool calls detected: {chunk.tool_calls}")
                detected_tool_calls.extend(chunk.tool_calls or [])
            elif chunk.type == "complete_response":
                print(f"     Response metadata: {chunk.response}")
            elif chunk.type == "done":
                print(f"     ✅ Stream completed")
                break
            
            print()
        
        print("-" * 40)
        print(f"📊 Workflow chunks: {chunk_count}")
        print(f"📝 Workflow content length: {len(workflow_content)} chars")
        print(f"🛠️  Detected tool calls: {len(detected_tool_calls)}")
        for i, tool_call in enumerate(detected_tool_calls):
            print(f"     [{i+1}] {tool_call.get('function', {}).get('name', 'unknown')}: {tool_call}")
        print(f"💰 Token usage: {backend.get_token_usage()}")
        
        if workflow_content:
            print(f"\n📄 Workflow response:\n{workflow_content}")
        
    except Exception as e:
        print(f"❌ Error during workflow test: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n✅ Workflow tools test completed!")


async def main():
    """Run all real tests."""
    print("🧪 ClaudeCodeStreamBackend Real API Tests")
    print("=" * 60)
    
    await test_real_stream_with_tools()
    await test_with_workflow_tools()
    
    print("\n🎉 All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())