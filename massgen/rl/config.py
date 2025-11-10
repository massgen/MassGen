"""
RL Configuration System for MassGen

This module defines configuration classes for the RL integration,
following the design from massgen_rl_integration_design.md
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StoreConfig:
    """Lightning Store configuration"""
    type: str = "local"  # "local" or "remote"
    path: Optional[str] = "./rl_data"
    host: Optional[str] = None
    port: Optional[int] = None


@dataclass
class AlgorithmConfig:
    """Training algorithm configuration"""
    algorithm: str = "lightningrl"  # "lightningrl", "apo", "sft"
    learning_rate: float = 1e-5
    batch_size: int = 32
    num_epochs: int = 10
    optimizer: str = "adam"

    # LightningRL specific parameters
    gamma: float = 0.99  # Discount factor
    lambda_gae: float = 0.95  # GAE lambda
    clip_epsilon: float = 0.2  # PPO clip

    # APO specific parameters
    num_prompt_candidates: int = 5
    prompt_diversity_threshold: float = 0.7


@dataclass
class RLConfig:
    """Overall RL configuration"""
    enable_rl: bool = False
    store_config: StoreConfig = field(default_factory=StoreConfig)
    algorithm_config: AlgorithmConfig = field(default_factory=AlgorithmConfig)

    # Reward settings
    enable_tool_rewards: bool = True
    enable_answer_quality_rewards: bool = True
    enable_coordination_rewards: bool = True
    enable_human_feedback: bool = False

    # Training settings
    collect_only: bool = False  # Only collect data, don't train
    checkpoint_dir: str = "./rl_checkpoints"
    log_dir: str = "./rl_logs"
