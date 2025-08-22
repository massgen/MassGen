#!/usr/bin/env python3
"""
Simple tests for orchestrator's get_final_presentation method shape and imports.
"""

import os
import sys
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_orchestrator_import():
    from massgen.orchestrator import Orchestrator

    assert Orchestrator is not None


def test_get_final_presentation_method():
    from massgen.orchestrator import Orchestrator
    import inspect

    assert hasattr(Orchestrator, "get_final_presentation")
    sig = inspect.signature(Orchestrator.get_final_presentation)
    assert list(sig.parameters.keys()) == ["self", "selected_agent_id", "vote_results"]


def test_stream_chunk_import():
    from massgen.backend.base import StreamChunk

    assert StreamChunk is not None


def test_message_templates_import():
    from massgen.message_templates import MessageTemplates

    assert MessageTemplates is not None


@pytest.mark.asyncio
async def test_orchestrator_initialization():
    from massgen.orchestrator import Orchestrator

    orchestrator = Orchestrator(agents={})
    assert orchestrator is not None
