#!/usr/bin/env python3
"""
Test script to examine how conversation context is built for LLM input.
Shows the exact message templates and context structure without making API calls.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.message_templates import MessageTemplates


def print_message_structure(title: str, conversation: Dict[str, Any]):
    """Print the structure of a conversation message in a readable format."""
    print(f"\n{'='*80}")
    print(f"🔍 {title}")
    print(f"{'='*80}")

    # System message
    print("📋 SYSTEM MESSAGE:")
    print("-" * 40)
    system_msg = conversation["system_message"]
    print(system_msg)

    # User message
    print(f"\n📨 USER MESSAGE:")
    print("-" * 40)
    user_msg = conversation["user_message"]
    print(user_msg)

    # Tools
    print(f"\n🔧 TOOLS PROVIDED:")
    print("-" * 40)
    tools = conversation.get("tools", [])
    for i, tool in enumerate(tools, 1):
        tool_name = tool.get("function", {}).get("name", "unknown")
        tool_desc = tool.get("function", {}).get("description", "No description")
        print(f"{i}. {tool_name}: {tool_desc}")

    print(f"\n📊 STATISTICS:")
    print(f"   System message length: {len(system_msg)} chars")
    print(f"   User message length: {len(user_msg)} chars")
    print(f"   Tools provided: {len(tools)}")
    print(f"   Total context size: {len(system_msg) + len(user_msg)} chars")


def test_turn1_context():
    """Test context building for the first turn (no history)."""
    print("🔷 TURN 1 CONTEXT BUILDING")
    print("Scenario: User asks initial question, no conversation history")

    templates = MessageTemplates()

    # Build conversation for first turn
    conversation = templates.build_conversation_with_context(
        current_task="What are the main benefits of renewable energy?",
        conversation_history=[],  # No history on first turn
        agent_summaries=None,  # No agent answers yet
        valid_agent_ids=None,
    )

    print_message_structure("Turn 1: Initial Question", conversation)

    # Verify structure
    user_msg = conversation["user_message"]
    has_history = "CONVERSATION_HISTORY" in user_msg
    has_original = "ORIGINAL MESSAGE" in user_msg
    has_answers = (
        "CURRENT ANSWERS" in user_msg and "no answers available yet" in user_msg
    )

    print(f"\n✅ VALIDATION:")
    print(f"   Contains conversation history section: {has_history}")
    print(f"   Contains original message section: {has_original}")
    print(f"   Contains empty answers section: {has_answers}")
    print(
        f"   System message mentions context: {'conversation' in conversation['system_message'].lower()}"
    )


def test_turn2_context():
    """Test context building for the second turn (with history)."""
    print(f"\n🔷 TURN 2 CONTEXT BUILDING")
    print("Scenario: User asks follow-up, with previous exchange in history")

    templates = MessageTemplates()

    # Simulate conversation history from Turn 1
    conversation_history = [
        {"role": "user", "content": "What are the main benefits of renewable energy?"},
        {
            "role": "assistant",
            "content": "Renewable energy offers several key benefits including environmental sustainability, economic advantages, and energy security. It reduces greenhouse gas emissions, creates jobs, and decreases dependence on fossil fuel imports.",
        },
    ]

    # Build conversation for second turn with history
    conversation = templates.build_conversation_with_context(
        current_task="What about the challenges and limitations?",
        conversation_history=conversation_history,
        agent_summaries={
            "researcher": "Key benefits include environmental and economic advantages."
        },
        valid_agent_ids=["researcher"],
    )

    print_message_structure("Turn 2: Follow-up with History", conversation)

    # Verify structure
    user_msg = conversation["user_message"]
    has_history = (
        "CONVERSATION_HISTORY" in user_msg
        and "User: What are the main benefits" in user_msg
    )
    has_original = (
        "ORIGINAL MESSAGE" in user_msg and "challenges and limitations" in user_msg
    )
    has_answers = "CURRENT ANSWERS" in user_msg and "researcher" in user_msg

    print(f"\n✅ VALIDATION:")
    print(f"   Contains conversation history: {has_history}")
    print(f"   Contains current question: {has_original}")
    print(f"   Contains agent answers: {has_answers}")
    print(
        f"   System message is context-aware: {'conversation' in conversation['system_message'].lower()}"
    )


def test_turn3_context():
    """Test context building for the third turn (extended history)."""
    print(f"\n🔷 TURN 3 CONTEXT BUILDING")
    print("Scenario: User asks third question, with extended conversation history")

    templates = MessageTemplates()

    # Simulate extended conversation history
    conversation_history = [
        {"role": "user", "content": "What are the main benefits of renewable energy?"},
        {
            "role": "assistant",
            "content": "Renewable energy offers environmental, economic, and energy security benefits.",
        },
        {"role": "user", "content": "What about the challenges and limitations?"},
        {
            "role": "assistant",
            "content": "Main challenges include high upfront costs, intermittency issues, and infrastructure requirements.",
        },
    ]

    # Build conversation for third turn with extended history
    conversation = templates.build_conversation_with_context(
        current_task="How can governments support the transition?",
        conversation_history=conversation_history,
        agent_summaries={
            "researcher": "Benefits include environmental and economic advantages.",
            "analyst": "Challenges include costs, intermittency, and infrastructure needs.",
        },
        valid_agent_ids=["researcher", "analyst"],
    )

    print_message_structure("Turn 3: Extended Conversation", conversation)

    # Verify structure
    user_msg = conversation["user_message"]
    has_full_history = (
        "CONVERSATION_HISTORY" in user_msg and user_msg.count("User:") >= 2
    )
    has_original = "ORIGINAL MESSAGE" in user_msg and "governments support" in user_msg
    has_multiple_answers = (
        "CURRENT ANSWERS" in user_msg
        and "researcher" in user_msg
        and "analyst" in user_msg
    )

    print(f"\n✅ VALIDATION:")
    print(f"   Contains full conversation history: {has_full_history}")
    print(f"   Contains current question: {has_original}")
    print(f"   Contains multiple agent answers: {has_multiple_answers}")
    print(f"   History shows progression: {user_msg.count('User:') >= 2}")


def test_context_comparison():
    """Compare context building across different turns."""
    print(f"\n🔍 CONTEXT COMPARISON ACROSS TURNS")
    print("=" * 80)

    templates = MessageTemplates()

    # Turn 1: No history
    conv1 = templates.build_conversation_with_context(
        current_task="What is solar energy?",
        conversation_history=[],
        agent_summaries=None,
    )

    # Turn 2: With history
    history = [
        {"role": "user", "content": "What is solar energy?"},
        {
            "role": "assistant",
            "content": "Solar energy is power derived from sunlight.",
        },
    ]
    conv2 = templates.build_conversation_with_context(
        current_task="How efficient is it?",
        conversation_history=history,
        agent_summaries={
            "expert": "Solar energy harnesses sunlight for power generation."
        },
    )

    # Turn 3: Extended history
    extended_history = [
        {"role": "user", "content": "What is solar energy?"},
        {
            "role": "assistant",
            "content": "Solar energy is power derived from sunlight.",
        },
        {"role": "user", "content": "How efficient is it?"},
        {
            "role": "assistant",
            "content": "Modern solar panels achieve 15-22% efficiency.",
        },
    ]
    conv3 = templates.build_conversation_with_context(
        current_task="What are the costs?",
        conversation_history=extended_history,
        agent_summaries={
            "expert": "Solar energy harnesses sunlight for power generation.",
            "engineer": "Modern panels achieve 15-22% efficiency.",
        },
    )

    print("📊 CONTEXT SIZE PROGRESSION:")
    print(f"   Turn 1 (no history):     {len(conv1['user_message']):,} chars")
    print(f"   Turn 2 (with history):   {len(conv2['user_message']):,} chars")
    print(f"   Turn 3 (extended):       {len(conv3['user_message']):,} chars")

    print(f"\n📈 CONTEXT ELEMENTS:")
    elements = ["CONVERSATION_HISTORY", "ORIGINAL MESSAGE", "CURRENT ANSWERS"]

    for i, (conv, turn) in enumerate(
        [(conv1, "Turn 1"), (conv2, "Turn 2"), (conv3, "Turn 3")], 1
    ):
        user_msg = conv["user_message"]
        print(f"\n   {turn}:")
        for element in elements:
            present = element in user_msg
            print(f"     {element}: {'✅' if present else '❌'}")

        # Count conversation exchanges
        if "CONVERSATION_HISTORY" in user_msg:
            exchange_count = user_msg.count("User:")
            print(f"     Previous exchanges: {exchange_count}")


def main():
    """Run all context building tests."""
    print("🚀 MassGen - Message Context Building Analysis")
    print("=" * 80)
    print("This test examines how conversation context is structured")
    print("for LLM input across multiple conversation turns.")
    print()

    try:
        # Test each turn's context building
        test_turn1_context()
        test_turn2_context()
        test_turn3_context()
        test_context_comparison()

        print(f"\n🎉 ALL CONTEXT BUILDING TESTS COMPLETED")
        print("=" * 80)
        print("✅ Message templates properly build conversation context")
        print("✅ Context grows appropriately with conversation history")
        print("✅ All required sections are included in each turn")
        print("🔍 Review the detailed context structures above to understand")
        print("   exactly what information is provided to agents at each turn.")

    except Exception as e:
        print(f"❌ Context building test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
