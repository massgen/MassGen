#!/usr/bin/env python3
"""Tests for conversation-context construction in MessageTemplates.

E1 fix: this file previously contained four collected ``test_*`` functions that
only ``print()`` computed booleans and returned ``None`` -- pytest passed them
unconditionally, giving false coverage on a core path. They are now real
assertions, with expectations verified against the actual rendered output:

  - the raw agent-id key is NOT echoed into the message (summaries are
    relabeled), so we assert on the summary *content* instead;
  - the ``User:`` history-label count equals the number of prior user turns;
  - the conversation-history section appears only when history is non-empty.

No API calls -- exercises MessageTemplates.build_conversation_with_context only.
"""

from __future__ import annotations

from massgen.message_templates import MessageTemplates


def test_turn1_context_no_history() -> None:
    """First turn: no history section, empty-answers section present."""
    conversation = MessageTemplates().build_conversation_with_context(
        current_task="What are the main benefits of renewable energy?",
        conversation_history=[],
        agent_summaries=None,
        valid_agent_ids=None,
    )
    user_msg = conversation["user_message"]

    assert "CONVERSATION_HISTORY" not in user_msg
    assert "ORIGINAL MESSAGE" in user_msg
    assert "What are the main benefits of renewable energy?" in user_msg
    assert "CURRENT ANSWERS" in user_msg
    assert "no answers available yet" in user_msg


def test_turn2_context_with_history_and_answers() -> None:
    """Second turn: history section present, prior turn rendered, summary content shown."""
    conversation_history = [
        {"role": "user", "content": "What are the main benefits of renewable energy?"},
        {"role": "assistant", "content": "Renewable energy reduces emissions and creates jobs."},
    ]
    conversation = MessageTemplates().build_conversation_with_context(
        current_task="What about the challenges and limitations?",
        conversation_history=conversation_history,
        agent_summaries={"researcher": "RESEARCHER_SUMMARY: environmental and economic advantages."},
        valid_agent_ids=["researcher"],
    )
    user_msg = conversation["user_message"]

    assert "CONVERSATION_HISTORY" in user_msg
    assert "What are the main benefits" in user_msg  # prior user turn rendered
    assert "ORIGINAL MESSAGE" in user_msg
    assert "challenges and limitations" in user_msg  # current task
    assert "CURRENT ANSWERS" in user_msg
    # Summary *content* is rendered (the raw agent id is relabeled, not echoed).
    assert "RESEARCHER_SUMMARY" in user_msg
    assert user_msg.count("User:") == 1  # exactly one prior user turn


def test_turn3_context_extended_history() -> None:
    """Third turn: two prior user turns and two distinct agent summaries."""
    conversation_history = [
        {"role": "user", "content": "What are the main benefits of renewable energy?"},
        {"role": "assistant", "content": "Environmental, economic, and energy-security benefits."},
        {"role": "user", "content": "What about the challenges and limitations?"},
        {"role": "assistant", "content": "High upfront costs, intermittency, infrastructure."},
    ]
    conversation = MessageTemplates().build_conversation_with_context(
        current_task="How can governments support the transition?",
        conversation_history=conversation_history,
        agent_summaries={
            "researcher": "RESEARCHER_SUMMARY: benefits.",
            "analyst": "ANALYST_SUMMARY: challenges.",
        },
        valid_agent_ids=["researcher", "analyst"],
    )
    user_msg = conversation["user_message"]

    assert "CONVERSATION_HISTORY" in user_msg
    assert "ORIGINAL MESSAGE" in user_msg
    assert "governments support" in user_msg
    assert "RESEARCHER_SUMMARY" in user_msg
    assert "ANALYST_SUMMARY" in user_msg
    assert user_msg.count("User:") == 2  # both prior user turns rendered


def test_context_grows_with_history() -> None:
    """User-message size grows monotonically as history accumulates."""
    templates = MessageTemplates()

    conv1 = templates.build_conversation_with_context(
        current_task="What is solar energy?",
        conversation_history=[],
        agent_summaries=None,
    )
    history = [
        {"role": "user", "content": "What is solar energy?"},
        {"role": "assistant", "content": "Solar energy is power derived from sunlight."},
    ]
    conv2 = templates.build_conversation_with_context(
        current_task="How efficient is it?",
        conversation_history=history,
        agent_summaries={"expert": "Solar harnesses sunlight."},
    )
    extended = history + [
        {"role": "user", "content": "How efficient is it?"},
        {"role": "assistant", "content": "Modern panels achieve 15-22% efficiency."},
    ]
    conv3 = templates.build_conversation_with_context(
        current_task="What are the costs?",
        conversation_history=extended,
        agent_summaries={"expert": "Solar harnesses sunlight.", "engineer": "15-22% efficiency."},
    )

    size1 = len(conv1["user_message"])
    size2 = len(conv2["user_message"])
    size3 = len(conv3["user_message"])
    assert size1 < size2 < size3

    assert "CONVERSATION_HISTORY" not in conv1["user_message"]
    assert "CONVERSATION_HISTORY" in conv2["user_message"]
    assert "CONVERSATION_HISTORY" in conv3["user_message"]
