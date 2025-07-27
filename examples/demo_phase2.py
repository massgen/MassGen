#!/usr/bin/env python3
"""
MassGen v0.0.2 Phase 2 Demo - Orchestrator Implementation

This demo showcases the completed Phase 2 implementation:
- Issue #20: Orchestrator as ChatAgent ✅
- Issue #22: Message Templates and Workflow Tools ✅

The orchestrator implements the proven MASS binary decision framework
with proper anonymous agent coordination and workflow tools.
"""

import asyncio
import os
import sys

# Add parent directory to path for massgen imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from massgen.v2 import (
    create_orchestrator, MessageTemplates,
    StreamChunk, AgentState
)


class MockSpecializedAgent:
    """Mock specialized agent with different expertise."""
    
    def __init__(self, agent_id: str, expertise: str, response_style: str):
        self.agent_id = agent_id
        self.expertise = expertise
        self.response_style = response_style
        self.session_id = f"mock_session_{agent_id}"
        self.conversation_history = []
    
    async def chat(self, messages, tools=None, reset_chat=False, clear_history=False):
        """Mock chat method with specialized responses."""
        # Check system message to understand context
        system_message = ""
        user_message = ""
        
        for message in messages:
            if message.get("role") == "system":
                system_message = message.get("content", "")
            elif message.get("role") == "user":
                user_message = message.get("content", "")
        
        # Determine if this is initial answer or voting phase
        is_voting_phase = "CURRENT ANSWERS" in user_message and "(no answers available yet)" not in user_message
        
        if tools:
            tool_names = []
            for tool in tools:
                if "function" in tool:
                    tool_names.append(tool["function"]["name"])
                elif "name" in tool:
                    tool_names.append(tool["name"])
            
            if is_voting_phase and "vote" in tool_names:
                # Voting phase - analyze answers and vote
                yield StreamChunk(type="content", content=f"[{self.expertise}] Analyzing the provided answers...", source=self.agent_id)
                
                # Simple voting logic - vote for agent1 if it exists
                tool_call = {
                    "function": {
                        "name": "vote",
                        "arguments": {"agent_id": "agent1", "reason": f"From my {self.expertise} perspective, this answer aligns well with established principles"}
                    }
                }
                yield StreamChunk(type="tool_calls", content=[tool_call], source=self.agent_id)
                
            elif "new_answer" in tool_names:
                # Initial answer phase
                answer = self._generate_specialized_answer()
                yield StreamChunk(type="content", content=f"[{self.expertise}] {answer}", source=self.agent_id)
                
                tool_call = {
                    "function": {
                        "name": "new_answer",
                        "arguments": {"content": answer}
                    }
                }
                yield StreamChunk(type="tool_calls", content=[tool_call], source=self.agent_id)
        
        yield StreamChunk(type="done", source=self.agent_id)
    
    def _generate_specialized_answer(self) -> str:
        """Generate specialized answer based on expertise."""
        if self.expertise == "philosophy":
            return "The meaning of life is a profound question that has occupied philosophers for millennia. From an existentialist perspective, life's meaning is created through our choices and authentic existence, while others argue for inherent purposes tied to virtue, happiness, or transcendence."
        elif self.expertise == "science":
            return "From a scientific standpoint, life's meaning can be understood through our biological imperative to survive and reproduce, our role in the cosmic evolution of complexity, and our unique capacity as conscious beings to understand and appreciate the universe."
        elif self.expertise == "practical":
            return "Practically speaking, life's meaning often comes from our relationships, contributions to society, personal growth, and the positive impact we have on others. It's about finding purpose in daily actions and building something meaningful."
        else:
            return f"From my {self.expertise} perspective, life has meaning through our understanding and application of relevant principles."
    
    def get_status(self):
        return {"agent_id": self.agent_id, "expertise": self.expertise, "status": "ready"}
    
    def reset(self):
        self.conversation_history = []
    
    def add_to_history(self, role: str, content: str, **kwargs):
        """Add message to conversation history."""
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.conversation_history.append(message)


async def demo_orchestrator_architecture():
    """Demonstrate the orchestrator architecture and components."""
    print("🏗️ MassGen v0.0.2 Phase 2 - Orchestrator Architecture")
    print("=" * 60)
    
    print("\n📋 Completed Phase 2 Components:")
    print("✅ Issue #20: Orchestrator as ChatAgent")
    print("✅ Issue #22: Message Templates and Workflow Tools")
    
    print("\n🔧 Architecture Components:")
    print("├── Orchestrator: Unified ChatAgent interface with coordination")
    print("├── MessageTemplates: Proven MASS binary decision framework")
    print("├── Workflow Tools: vote() and new_answer() functions")  
    print("├── AgentState: Runtime coordination state tracking")
    print("└── Anonymous Agent IDs: Bias reduction in voting")
    
    # Demo message templates
    templates = MessageTemplates()
    
    print("\n📝 Message Template Demo:")
    print("Case 1 (Initial):")
    case1 = templates.build_case1_user_message("What is the meaning of life?")
    print(f"  System: {templates.evaluation_system_message()[:100]}...")
    print(f"  User: {case1[:150]}...")
    
    print("\nCase 2 (With Answers):")
    sample_answers = {
        "philosopher": "Life's meaning comes from virtue and wisdom",
        "scientist": "Life's meaning emerges from consciousness and evolution"
    }
    case2 = templates.build_case2_user_message("What is the meaning of life?", sample_answers)
    print(f"  User: {case2[:200]}...")
    
    print("\n🔧 Workflow Tools:")
    tools = templates.get_standard_tools(["agent1", "agent2"])
    for tool in tools:
        tool_name = tool["function"]["name"]
        tool_desc = tool["function"]["description"]
        print(f"  - {tool_name}(): {tool_desc}")


async def demo_orchestrator_coordination():
    """Demonstrate full orchestrator coordination."""
    print("\n\n🎯 Live Orchestrator Coordination Demo")
    print("=" * 60)
    
    # Create specialized mock agents
    agents = {
        "philosophy_expert": MockSpecializedAgent("philosophy_expert", "philosophy", "analytical"),
        "science_expert": MockSpecializedAgent("science_expert", "science", "empirical"),
        "practical_advisor": MockSpecializedAgent("practical_advisor", "practical", "pragmatic")
    }
    
    # Create orchestrator
    orchestrator = create_orchestrator(
        agents=agents,
        orchestrator_id="meaning_of_life_coordinator"
    )
    
    print(f"✅ Created orchestrator with {len(agents)} specialized agents:")
    for agent_id, agent in agents.items():
        print(f"  - {agent_id}: {agent.expertise} expertise")
    
    # Test coordination
    task = "What is the meaning of life, and how should we approach finding it?"
    messages = [{"role": "user", "content": task}]
    
    print(f"\n📝 Task: {task}")
    print("\n🎯 Starting Coordination:")
    print("-" * 40)
    
    try:
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content":
                print(chunk.content, end="")
            elif chunk.type == "done":
                print("\n✅ Coordination completed successfully!")
                break
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                break
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
    
    # Show final status
    status = orchestrator.get_status()
    print(f"\n📊 Final Status:")
    print(f"  - Phase: {status['workflow_phase']}")
    print(f"  - Task: {status['current_task'][:50]}...")
    print(f"  - Agents: {len(status['sub_agents'])}")
    
    # Show agent states
    print(f"\n👥 Agent States:")
    for agent_id, state in status['agent_states'].items():
        print(f"  - {agent_id}: {'✓' if state['has_answer'] else '○'} answer, {'✓' if state['has_voted'] else '○'} voted")


async def demo_phase2_summary():
    """Show Phase 2 completion summary."""
    print("\n\n🎉 Phase 2 Implementation Complete!")
    print("=" * 60)
    
    print("\n📋 What's Been Accomplished:")
    print("✅ Orchestrator as ChatAgent (Issue #20)")
    print("  - Unified chat interface for coordination")
    print("  - Transparent multi-agent workflow")
    print("  - Compatible with all ChatAgent implementations")
    
    print("\n✅ Message Templates and Workflow Tools (Issue #22)")
    print("  - Binary decision framework (vote OR new_answer)")
    print("  - Anonymous agent coordination")
    print("  - Standardized conversation building")
    print("  - Proven MASS workflow patterns")
    
    print("\n🔄 Integration Points:")
    print("  - Works with SimpleAgent implementations")
    print("  - Supports recursive orchestrator composition")
    print("  - Streaming real-time coordination")
    print("  - Session management and state tracking")
    
    print("\n🚀 Ready for Phase 3:")
    print("  - Issue #21: Factory Functions and AgentConfig")
    print("  - Issue #23: Frontend Integration")
    print("  - Issue #24: Recursive Orchestrator Composition")
    
    print("\n💡 Usage Examples:")
    print("```python")
    print("from massgen.v2 import create_orchestrator, create_simple_agent")
    print("")
    print("# Create specialized agents")
    print("agents = {")
    print("    'researcher': create_simple_agent('researcher', 'gpt-4o'),") 
    print("    'writer': create_simple_agent('writer', 'claude-3-sonnet')")
    print("}")
    print("")
    print("# Create orchestrator")
    print("coordinator = create_orchestrator(agents)")
    print("")
    print("# Use like any ChatAgent")
    print("async for chunk in coordinator.chat(messages):")
    print("    print(chunk.content)")
    print("```")


async def main():
    """Run all Phase 2 demonstrations."""
    await demo_orchestrator_architecture()
    await demo_orchestrator_coordination()
    await demo_phase2_summary()


if __name__ == "__main__":
    asyncio.run(main())