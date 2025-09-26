#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for testing the final presentation fallback functionality.
This tests the specific changes we made to handle empty final presentations.
"""

import asyncio
import os
import sys
from unittest.mock import Mock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.mark.asyncio
async def test_final_presentation_fallback():
    """Test that the final presentation fallback works when content is empty."""
    try:
        try:
            from massgen.orchestrator import Orchestrator
        except ModuleNotFoundError as e:
            # Skip if optional backend deps are missing during package import
            if "claude_code_sdk" in str(e):
                pytest.skip("Skipping: optional dependency 'claude_code_sdk' not installed")
            raise

        # Create a mock orchestrator with minimal setup
        orchestrator = Orchestrator(agents={})

        # Mock the agent states to simulate a stored answer
        orchestrator.agent_states = {"test_agent": Mock(answer="This is a stored answer for testing purposes.")}

        # Mock the message templates
        orchestrator.message_templates = Mock()
        orchestrator.message_templates.build_final_presentation_message.return_value = "Test message"
        orchestrator.message_templates.final_presentation_system_message.return_value = "Test system message"

        # Mock the current task
        orchestrator.current_task = "Test task"

        # Create a mock agent that returns no content
        mock_agent = Mock()

        # Simulate empty response from agent
        async def empty_response(*args, **kwargs):
            # Yield a done chunk with no content
            yield Mock(type="done", content="")

        # Set the chat method to return the async generator
        mock_agent.chat = empty_response

        # Add the mock agent to orchestrator
        orchestrator.agents = {"test_agent": mock_agent}

        # Test the get_final_presentation method
        vote_results = {
            "vote_counts": {"test_agent": 1},
            "voter_details": {"test_agent": [{"voter": "other_agent", "reason": "Test reason"}]},
            "is_tie": False,
        }

        # Collect all chunks from the method
        chunks = []
        async for chunk in orchestrator.get_final_presentation("test_agent", vote_results):
            chunks.append(chunk)

        # Check if we got the fallback content
        fallback_found = any(getattr(c, "type", None) == "content" and (getattr(c, "content", "") or "").find("stored answer") != -1 for c in chunks)

        assert fallback_found, "Fallback content not found"
    except Exception as e:
        assert False, f"Error during fallback test: {e}"


@pytest.mark.asyncio
async def test_final_presentation_with_content():
    """Test that the final presentation works normally when content is provided."""
    try:
        from massgen.orchestrator import Orchestrator

        # Create a mock orchestrator with minimal setup
        orchestrator = Orchestrator(agents={})

        # Mock the agent states
        orchestrator.agent_states = {"test_agent": Mock(answer="This is a stored answer for testing purposes.")}

        # Mock the message templates
        orchestrator.message_templates = Mock()
        orchestrator.message_templates.build_final_presentation_message.return_value = "Test message"
        orchestrator.message_templates.final_presentation_system_message.return_value = "Test system message"

        # Mock the current task
        orchestrator.current_task = "Test task"

        # Create a mock agent that returns content
        mock_agent = Mock()

        # Simulate normal response from agent
        async def normal_response(*args, **kwargs):
            # Yield content chunks
            yield Mock(type="content", content="This is the final presentation content.")
            yield Mock(type="done", content="")

        # Set the chat method to return the async generator
        mock_agent.chat = normal_response

        # Add the mock agent to orchestrator
        orchestrator.agents = {"test_agent": mock_agent}

        # Test the get_final_presentation method
        vote_results = {
            "vote_counts": {"test_agent": 1},
            "voter_details": {"test_agent": [{"voter": "other_agent", "reason": "Test reason"}]},
            "is_tie": False,
        }

        # Collect all chunks from the method
        chunks = []
        async for chunk in orchestrator.get_final_presentation("test_agent", vote_results):
            chunks.append(chunk)

        # Check if we got the normal content (no fallback needed)
        content_found = any(getattr(c, "type", None) == "content" and (getattr(c, "content", "") or "").find("final presentation content") != -1 for c in chunks)

        assert content_found, "Normal content not found"
    except Exception as e:
        assert False, f"Error during normal content test: {e}"


@pytest.mark.asyncio
async def test_no_stored_answer_fallback():
    """Test that the fallback handles the case when there's no stored answer."""
    try:
        from massgen.orchestrator import Orchestrator

        # Create a mock orchestrator with minimal setup
        orchestrator = Orchestrator(agents={})

        # Mock the agent states with no stored answer
        orchestrator.agent_states = {"test_agent": Mock(answer="")}  # No stored answer

        # Mock the message templates
        orchestrator.message_templates = Mock()
        orchestrator.message_templates.build_final_presentation_message.return_value = "Test message"
        orchestrator.message_templates.final_presentation_system_message.return_value = "Test system message"

        # Mock the current task
        orchestrator.current_task = "Test task"

        # Create a mock agent that returns no content
        mock_agent = Mock()

        # Simulate empty response from agent
        async def empty_response(*args, **kwargs):
            # Yield a done chunk with no content
            yield Mock(type="done", content="")

        # Set the chat method to return the async generator
        mock_agent.chat = empty_response

        # Add the mock agent to orchestrator
        orchestrator.agents = {"test_agent": mock_agent}

        # Test the get_final_presentation method
        vote_results = {
            "vote_counts": {"test_agent": 1},
            "voter_details": {"test_agent": [{"voter": "other_agent", "reason": "Test reason"}]},
            "is_tie": False,
        }

        # Collect all chunks from the method
        chunks = []
        async for chunk in orchestrator.get_final_presentation("test_agent", vote_results):
            chunks.append(chunk)

        # Check if we got the no-content fallback message
        fallback_found = any(getattr(c, "type", None) == "content" and (getattr(c, "content", "") or "").find("No content generated") != -1 for c in chunks)

        assert fallback_found, "No-content fallback message not found"
    except Exception as e:
        assert False, f"Error during no stored answer test: {e}"


async def main():
    """Main test runner."""
    print("🚀 MassGen Final Presentation Fallback Test Suite")
    print("Testing the specific changes we made to handle empty final presentations...")
    print("=" * 80)

    tests = [
        ("Final Presentation Fallback", test_final_presentation_fallback),
        ("Normal Final Presentation", test_final_presentation_with_content),
        ("No Stored Answer Fallback", test_no_stored_answer_fallback),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        if await test_func():
            passed += 1
        print()

    print("=" * 80)
    print("🏁 Final Test Summary")
    print("=" * 80)

    if passed == total:
        print("🎉 All tests passed! The final presentation fallback is working correctly.")
        print("\n✅ What we've verified:")
        print("  • Fallback to stored answer works when final presentation is empty")
        print("  • Normal final presentation still works when content is provided")
        print("  • Proper error message when no stored answer is available")
        print("\n✅ The orchestrator changes are robust and won't break the program!")
        return 0
    else:
        print(f"❌ {total - passed} tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error during testing: {e}")
        sys.exit(1)
