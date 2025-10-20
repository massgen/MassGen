# -*- coding: utf-8 -*-
"""
Test AG2 (AutoGen) Lesson Planner Tool
Tests the interoperability feature where AutoGen nested chat is wrapped as a MassGen custom tool.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from massgen.tool._extraframework_agents.ag2_lesson_planner_tool import ag2_lesson_planner  # noqa: E402
from massgen.tool._result import ExecutionResult  # noqa: E402


class TestAG2LessonPlannerTool:
    """Test AG2 Lesson Planner Tool functionality."""

    @pytest.mark.asyncio
    async def test_basic_lesson_plan_creation(self):
        """Test basic lesson plan creation with a simple topic."""
        # Skip if no API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        # Test with a simple topic
        result = await ag2_lesson_planner(topic="photosynthesis", api_key=api_key)

        # Verify result structure
        assert isinstance(result, ExecutionResult)
        assert len(result.output_blocks) > 0
        # Check that the result doesn't contain an error
        assert not result.output_blocks[0].data.startswith("Error:")

        # Verify lesson plan contains expected elements
        lesson_plan = result.output_blocks[0].data
        assert "photosynthesis" in lesson_plan.lower()

    @pytest.mark.asyncio
    async def test_lesson_plan_with_env_api_key(self):
        """Test lesson plan creation using environment variable for API key."""
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        # Test without passing api_key parameter (should use env var)
        result = await ag2_lesson_planner(topic="fractions")

        assert isinstance(result, ExecutionResult)
        assert len(result.output_blocks) > 0
        # Check that the result doesn't contain an error
        assert not result.output_blocks[0].data.startswith("Error:")

    @pytest.mark.asyncio
    async def test_missing_api_key_error(self):
        """Test error handling when API key is missing."""
        # Temporarily save and remove env var
        original_key = os.environ.get("OPENAI_API_KEY")
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        try:
            result = await ag2_lesson_planner(topic="test topic")

            # Should return error result
            assert isinstance(result, ExecutionResult)
            assert result.output_blocks[0].data.startswith("Error:")
            assert "OPENAI_API_KEY not found" in result.output_blocks[0].data
        finally:
            # Restore env var
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key

    @pytest.mark.asyncio
    async def test_different_topics(self):
        """Test lesson plan creation with different topics."""
        # Skip if no API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        topics = ["addition", "animals", "water cycle"]

        for topic in topics:
            result = await ag2_lesson_planner(topic=topic, api_key=api_key)

            assert isinstance(result, ExecutionResult)
            assert len(result.output_blocks) > 0
            # Check that the result doesn't contain an error
            assert not result.output_blocks[0].data.startswith("Error:")
            assert topic.lower() in result.output_blocks[0].data.lower()

    @pytest.mark.asyncio
    async def test_concurrent_lesson_plan_creation(self):
        """Test creating multiple lesson plans concurrently."""
        # Skip if no API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        topics = ["math", "science", "reading"]

        # Create tasks for concurrent execution
        tasks = [ag2_lesson_planner(topic=topic, api_key=api_key) for topic in topics]

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        # Verify all results
        assert len(results) == len(topics)
        for i, result in enumerate(results):
            assert isinstance(result, ExecutionResult)
            assert len(result.output_blocks) > 0
            # Check that the result doesn't contain an error
            assert not result.output_blocks[0].data.startswith("Error:")
            assert topics[i].lower() in result.output_blocks[0].data.lower()


class TestAG2ToolIntegration:
    """Test AG2 tool integration with MassGen tool system."""

    def test_tool_function_signature(self):
        """Test that the tool has the correct async signature."""
        import inspect

        assert inspect.iscoroutinefunction(ag2_lesson_planner)

        # Get function signature
        sig = inspect.signature(ag2_lesson_planner)
        params = sig.parameters

        # Verify parameters
        assert "topic" in params
        assert "api_key" in params

        # Verify return annotation
        assert sig.return_annotation == ExecutionResult

    @pytest.mark.asyncio
    async def test_execution_result_structure(self):
        """Test that the returned ExecutionResult has the correct structure."""
        # Skip if no API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        result = await ag2_lesson_planner(topic="test", api_key=api_key)

        # Verify ExecutionResult structure
        assert hasattr(result, "output_blocks")
        assert isinstance(result.output_blocks, list)
        assert len(result.output_blocks) > 0
        # Check that the result doesn't contain an error
        assert not result.output_blocks[0].data.startswith("Error:")

        # Verify TextContent structure
        from massgen.tool._result import TextContent

        assert isinstance(result.output_blocks[0], TextContent)
        assert hasattr(result.output_blocks[0], "data")
        assert isinstance(result.output_blocks[0].data, str)


class TestAG2ToolWithBackend:
    """Test AG2 tool with ResponseBackend."""

    @pytest.mark.asyncio
    async def test_backend_registration(self):
        """Test registering AG2 tool with ResponseBackend."""
        from massgen.backend.response import ResponseBackend

        api_key = os.getenv("OPENAI_API_KEY", "test-key")

        # Import the tool
        from massgen.tool._extraframework_agents.ag2_lesson_planner_tool import ag2_lesson_planner

        # Register with backend
        backend = ResponseBackend(
            api_key=api_key,
            custom_tools=[
                {
                    "func": ag2_lesson_planner,
                    "description": "Create a comprehensive lesson plan using AG2 nested chat",
                }
            ],
        )

        # Verify tool is registered
        assert "ag2_lesson_planner" in backend._custom_tool_names

        # Verify schema generation
        schemas = backend._get_custom_tools_schemas()
        assert len(schemas) >= 1

        # Find our tool's schema
        ag2_schema = None
        for schema in schemas:
            if schema["function"]["name"] == "ag2_lesson_planner":
                ag2_schema = schema
                break

        assert ag2_schema is not None
        assert ag2_schema["type"] == "function"
        assert "parameters" in ag2_schema["function"]


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    # Run pytest
    pytest.main([__file__, "-v"])
