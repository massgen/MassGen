"""
MassGen RL Integration Module

This module provides reinforcement learning capabilities for MassGen agents,
following the design from massgen_rl_integration_design.md

The RL integration is:
- Minimally invasive: Existing functionality preserved, RL is optional
- Decoupled: Training and execution are separated
- Progressive: Start simple, expand to complex scenarios
- Backward compatible: No breaking changes

Core Components:
    - RLConfig: Configuration for RL features
    - TraceCollector: Collects execution traces
    - RewardComputer: Computes reward signals
    - RLAgentMixin: Adds RL to individual agents
    - RLOrchestratorMixin: Adds RL to orchestrator

Data Structures:
    - Trace: Complete execution trajectory
    - Spans: Individual events (PromptSpan, ToolSpan, RewardSpan, etc.)
    - LightningStore: Storage for traces

Example Usage:
    ```python
    from massgen.rl import RLAgentMixin, RLConfig, StoreConfig
    from massgen import ConfigurableAgent, AgentConfig

    # Create RL-enabled agent
    class RLAgent(RLAgentMixin, ConfigurableAgent):
        pass

    # Configure RL
    rl_config = RLConfig(
        enable_rl=True,
        store_config=StoreConfig(type="local", path="./rl_data"),
        enable_tool_rewards=True,
        enable_answer_quality_rewards=True
    )

    # Create agent
    agent = RLAgent(
        config=AgentConfig.create_openai_config(),
        enable_rl=True,
        rl_config=rl_config
    )

    # Use normally - traces are collected automatically
    async for chunk in agent.chat([{"role": "user", "content": "Hello"}]):
        print(chunk.content)
    ```
"""

# Configuration
from .config import AlgorithmConfig, RLConfig, StoreConfig

# Data structures
from .spans import (
    ContentSpan,
    CoordinationSpan,
    PromptSpan,
    ReasoningSpan,
    RewardSpan,
    ToolSpan,
)
from .trace import Trace

# Core components
from .store import LightningStore
from .trace_collector import TraceCollector
from .reward_computer import RewardComputer

# Mixins for agent integration
from .agent_mixin import RLAgentMixin
from .orchestrator_mixin import RLOrchestratorMixin

__all__ = [
    # Configuration
    "RLConfig",
    "StoreConfig",
    "AlgorithmConfig",
    # Data structures
    "Trace",
    "PromptSpan",
    "ToolSpan",
    "RewardSpan",
    "CoordinationSpan",
    "ContentSpan",
    "ReasoningSpan",
    # Core components
    "LightningStore",
    "TraceCollector",
    "RewardComputer",
    # Mixins
    "RLAgentMixin",
    "RLOrchestratorMixin",
]

__version__ = "0.1.0"
