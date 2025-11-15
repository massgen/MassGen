"""
Tests for RL Integration

This test suite verifies the basic functionality of the RL integration,
including trace collection, storage, and reward computation.
"""

import asyncio
import tempfile
import shutil
from pathlib import Path

import pytest

from massgen.rl import (
    RLConfig,
    StoreConfig,
    TraceCollector,
    RewardComputer,
    LightningStore,
    Trace,
    PromptSpan,
    ToolSpan,
    RewardSpan,
)


class TestRLConfig:
    """Test RL configuration classes"""

    def test_store_config_defaults(self):
        """Test StoreConfig default values"""
        config = StoreConfig()
        assert config.type == "local"
        assert config.path == "./rl_data"

    def test_rl_config_defaults(self):
        """Test RLConfig default values"""
        config = RLConfig()
        assert config.enable_rl == False
        assert config.enable_tool_rewards == True
        assert config.enable_answer_quality_rewards == True
        assert config.collect_only == False


class TestSpans:
    """Test span data structures"""

    def test_prompt_span(self):
        """Test PromptSpan creation and serialization"""
        span = PromptSpan(
            span_id="test_span_1",
            timestamp=1234567890.0,
            input="Hello",
            output="Hi there",
            model="gpt-4o"
        )
        assert span.span_type == "prompt"
        assert span.input == "Hello"
        assert span.output == "Hi there"

        # Test serialization
        data = span.to_dict()
        assert data['span_id'] == "test_span_1"
        assert data['input'] == "Hello"

    def test_tool_span(self):
        """Test ToolSpan creation and serialization"""
        span = ToolSpan(
            span_id="test_span_2",
            timestamp=1234567890.0,
            tool_name="web_search",
            arguments={"query": "test"},
            result={"results": []},
            success=True
        )
        assert span.span_type == "tool"
        assert span.tool_name == "web_search"
        assert span.success == True

        # Test serialization
        data = span.to_dict()
        assert data['tool_name'] == "web_search"

    def test_reward_span(self):
        """Test RewardSpan creation"""
        span = RewardSpan(
            span_id="test_span_3",
            timestamp=1234567890.0,
            reward=1.0,
            reward_type="tool",
            reason="Success"
        )
        assert span.span_type == "reward"
        assert span.reward == 1.0
        assert span.reward_type == "tool"


class TestTrace:
    """Test trace data structure"""

    def test_trace_creation(self):
        """Test Trace creation"""
        trace = Trace(
            trace_id="test_trace_1",
            agent_id="agent_1",
            task="Test task"
        )
        assert trace.trace_id == "test_trace_1"
        assert trace.agent_id == "agent_1"
        assert trace.status == "running"
        assert len(trace.spans) == 0

    def test_trace_add_span(self):
        """Test adding spans to trace"""
        trace = Trace(
            trace_id="test_trace_1",
            agent_id="agent_1",
            task="Test task"
        )

        # Add prompt span
        span1 = PromptSpan(
            span_id="span_1",
            input="Hello",
            output="Hi",
            model="gpt-4o"
        )
        trace.add_span(span1)
        assert len(trace.spans) == 1

        # Add reward span
        span2 = RewardSpan(
            span_id="span_2",
            reward=1.5,
            reward_type="tool"
        )
        trace.add_span(span2)
        assert len(trace.spans) == 2
        assert trace.total_reward == 1.5

    def test_trace_serialization(self):
        """Test trace serialization and deserialization"""
        trace = Trace(
            trace_id="test_trace_1",
            agent_id="agent_1",
            task="Test task"
        )

        span = PromptSpan(
            span_id="span_1",
            input="Hello",
            output="Hi",
            model="gpt-4o"
        )
        trace.add_span(span)
        trace.end()

        # Serialize
        data = trace.to_dict()
        assert data['trace_id'] == "test_trace_1"
        assert data['status'] == "completed"
        assert len(data['spans']) == 1

        # Deserialize
        restored_trace = Trace.from_dict(data)
        assert restored_trace.trace_id == trace.trace_id
        assert restored_trace.agent_id == trace.agent_id
        assert len(restored_trace.spans) == 1


class TestLightningStore:
    """Test Lightning Store"""

    @pytest.fixture
    def temp_store(self):
        """Create temporary store for testing"""
        temp_dir = tempfile.mkdtemp()
        config = StoreConfig(type="local", path=temp_dir)
        store = LightningStore(config)
        yield store
        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_store_save_and_load(self, temp_store):
        """Test saving and loading traces"""
        # Create trace
        trace = Trace(
            trace_id="test_trace_1",
            agent_id="agent_1",
            task="Test task"
        )
        span = PromptSpan(
            span_id="span_1",
            input="Hello",
            output="Hi",
            model="gpt-4o"
        )
        trace.add_span(span)
        trace.end()

        # Save
        success = await temp_store.save_trace(trace)
        assert success == True

        # Load
        loaded_trace = await temp_store.load_trace("test_trace_1")
        assert loaded_trace is not None
        assert loaded_trace.trace_id == "test_trace_1"
        assert len(loaded_trace.spans) == 1

    @pytest.mark.asyncio
    async def test_store_get_traces_by_agent(self, temp_store):
        """Test getting traces by agent ID"""
        # Create multiple traces
        for i in range(3):
            trace = Trace(
                trace_id=f"trace_{i}",
                agent_id="agent_1",
                task=f"Task {i}"
            )
            trace.end()
            await temp_store.save_trace(trace)

        # Get traces for agent
        traces = await temp_store.get_traces_by_agent("agent_1")
        assert len(traces) == 3

    @pytest.mark.asyncio
    async def test_store_statistics(self, temp_store):
        """Test store statistics"""
        # Create and save trace
        trace = Trace(
            trace_id="test_trace_1",
            agent_id="agent_1",
            task="Test task"
        )
        reward_span = RewardSpan(
            span_id="span_1",
            reward=2.5,
            reward_type="tool"
        )
        trace.add_span(reward_span)
        trace.end()
        await temp_store.save_trace(trace)

        # Get statistics
        stats = await temp_store.get_statistics()
        assert stats['total_traces'] == 1
        assert stats['total_agents'] == 1
        assert stats['total_reward'] == 2.5


class TestTraceCollector:
    """Test Trace Collector"""

    @pytest.fixture
    def temp_collector(self):
        """Create temporary collector for testing"""
        temp_dir = tempfile.mkdtemp()
        config = StoreConfig(type="local", path=temp_dir)
        collector = TraceCollector(agent_id="test_agent", store_config=config)
        yield collector
        # Cleanup
        shutil.rmtree(temp_dir)

    def test_collector_start_trace(self, temp_collector):
        """Test starting a trace"""
        trace_id = temp_collector.start_trace(
            task="Test task",
            metadata={"test": "data"}
        )
        assert trace_id is not None
        assert trace_id in temp_collector.active_traces

    def test_collector_emit_spans(self, temp_collector):
        """Test emitting various spans"""
        trace_id = temp_collector.start_trace(task="Test task")

        # Emit prompt span
        temp_collector.emit_prompt_span(
            trace_id=trace_id,
            prompt="Hello",
            response="Hi",
            model="gpt-4o"
        )

        # Emit tool span
        temp_collector.emit_tool_span(
            trace_id=trace_id,
            tool_name="web_search",
            arguments={"query": "test"}
        )

        # Emit reward span
        temp_collector.emit_reward_span(
            trace_id=trace_id,
            reward=1.0,
            reward_type="tool"
        )

        # Check trace
        trace = temp_collector.get_active_trace(trace_id)
        assert len(trace.spans) == 3

    @pytest.mark.asyncio
    async def test_collector_end_trace(self, temp_collector):
        """Test ending and saving a trace"""
        trace_id = temp_collector.start_trace(task="Test task")

        temp_collector.emit_reward_span(
            trace_id=trace_id,
            reward=1.0,
            reward_type="tool"
        )

        # End trace
        success = await temp_collector.end_trace(trace_id)
        assert success == True
        assert trace_id not in temp_collector.active_traces


class TestRewardComputer:
    """Test Reward Computer"""

    def test_tool_reward_success(self):
        """Test tool reward for successful execution"""
        computer = RewardComputer()

        tool_call = {"name": "web_search"}
        result = {"results": ["item1", "item2"]}

        reward = computer.compute_tool_reward(tool_call, result)
        assert reward > 0

    def test_tool_reward_failure(self):
        """Test tool reward for failed execution"""
        computer = RewardComputer()

        tool_call = {"name": "web_search"}
        result = Exception("Error")

        reward = computer.compute_tool_reward(tool_call, result)
        assert reward < 0

    def test_answer_quality_reward(self):
        """Test answer quality reward"""
        computer = RewardComputer()

        # Good answer with structure
        answer = """
        # Analysis

        Here is a detailed analysis:

        1. First point
        2. Second point

        ## Conclusion

        In conclusion, the answer is clear.
        """

        reward = computer.compute_answer_quality_reward(answer)
        assert reward > 0.3  # Should have good structure score

    def test_coordination_reward(self):
        """Test coordination reward"""
        computer = RewardComputer()

        reward = computer.compute_coordination_reward(
            coordination_rounds=2,
            final_answer_quality=0.8,
            token_usage=5000,
            consensus_achieved=True
        )
        assert reward > 0  # Should be positive for good coordination

    def test_voting_reward(self):
        """Test voting reward"""
        computer = RewardComputer()

        # Correct vote
        reward = computer.compute_voting_reward(
            voted_for="agent_1",
            actual_winner="agent_1"
        )
        assert reward == 1.0

        # Incorrect vote
        reward = computer.compute_voting_reward(
            voted_for="agent_1",
            actual_winner="agent_2"
        )
        assert reward < 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
