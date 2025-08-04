#!/usr/bin/env python3
"""
MassGen (Multi-Agent Scaling System) - Programmatic Interface

This module provides programmatic interfaces for running the MassGen system.
For command-line usage, use: uv run python -m massgen.v1.cli

Programmatic usage examples:
    # Using YAML configuration
    from mass import run_mass_with_config, load_config_from_yaml
    config = load_config_from_yaml("config.yaml")
    result = run_mass_with_config("Your question here", config)
    
    # Using simple model list
    from mass import run_mass_agents
    result = run_mass_agents("What is 2+2?", ["gpt-4o", "gemini-2.5-flash"])
    
    # Using configuration objects
    from mass import MassSystem, create_config_from_models
    config = create_config_from_models(["gpt-4o", "grok-3"])
    system = MassSystem(config)
    result = system.run("Complex question here")
"""

import sys
import os
import logging
import time
import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

from .types import TaskInput, MassConfig, ModelConfig, AgentConfig
from .config import create_config_from_models
from .orchestrator import MassOrchestrator  
from .agents import create_agent
from .streaming_display import create_streaming_display
from .logging import MassLogManager

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _run_single_agent_simple(question: str, config: MassConfig) -> Dict[str, Any]:
    """
    Simple single-agent processing that bypasses the multi-agent orchestration system.
    
    Args:
        question: The question to solve
        config: MassConfig object with exactly one agent
        
    Returns:
        Dict containing the answer and detailed results
    """
    start_time = time.time()
    agent_config = config.agents[0]
    
    logger.info(f"🤖 Running single agent mode with {agent_config.model_config.model}")
    logger.info(f"   Question: {question}")
    
    # Create log manager for single agent mode to ensure result.json is saved
    log_manager = MassLogManager(
        log_dir=config.logging.log_dir,
        session_id=config.logging.session_id,
        non_blocking=config.logging.non_blocking
    )
    
    try:
        # Create the single agent without orchestrator (None)
        agent = create_agent(
            agent_type=agent_config.agent_type,
            agent_id=agent_config.agent_id,
            orchestrator=None,  # No orchestrator needed for single agent
            model_config=agent_config.model_config,
            stream_callback=None  # Simple mode without streaming
        )
        
        # Create simple conversation format
        messages = [
            {
                "role": "system", 
                "content": f"You are an expert agent equipped with tools to solve complex tasks. Please provide a comprehensive answer to the user's question."
            },
            {
                "role": "user", 
                "content": question
            }
        ]
        
        # Get available tools from agent configuration
        tools = agent_config.model_config.tools if agent_config.model_config.tools else []
        
        # Call process_message directly
        result = agent.process_message(messages=messages, tools=tools)
        
        # Calculate duration
        session_duration = time.time() - start_time
        
        # Format response to match multi-agent system format
        response = {
            "answer": result.text if result.text else "No response generated",
            "consensus_reached": True,  # Trivially true for single agent
            "representative_agent_id": agent_config.agent_id,
            "session_duration": session_duration,
            "summary": {
                "total_agents": 1,
                "failed_agents": 0,
                "total_votes": 1,
                "final_vote_distribution": {agent_config.agent_id: 1},  # Single agent votes for itself
            },
            "model_used": agent_config.model_config.model,
            "citations": result.citations if hasattr(result, 'citations') else [],
            "code": result.code if hasattr(result, 'code') else [],
            "single_agent_mode": True
        }
        
        # Save result to result.json in the session directory
        if log_manager and not log_manager.non_blocking:
            try:
                result_file = log_manager.session_dir / "result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"💾 Single agent result saved to {result_file}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to save result.json: {e}")
        
        logger.info(f"✅ Single agent completed in {session_duration:.1f}s")
        return response
        
    except Exception as e:
        session_duration = time.time() - start_time
        logger.error(f"❌ Single agent failed: {e}")
        
        # Return error response in same format
        error_response = {
            "answer": f"Error in single agent processing: {str(e)}",
            "consensus_reached": False,
            "representative_agent_id": None,
            "session_duration": session_duration,
            "summary": {
                "total_agents": 1,
                "failed_agents": 1,
                "total_votes": 0,
                "final_vote_distribution": {},
            },
            "model_used": agent_config.model_config.model,
            "citations": [],
            "code": [],
            "single_agent_mode": True,
            "error": str(e)
        }
        
        # Save error result to result.json in the session directory
        if log_manager and not log_manager.non_blocking:
            try:
                result_file = log_manager.session_dir / "result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(error_response, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"💾 Single agent error result saved to {result_file}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to save result.json: {e}")
        
        return error_response
    finally:
        # Cleanup log manager
        if log_manager:
            try:
                log_manager.cleanup()
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up log manager: {e}")


def run_mass_with_config(question: str, config: MassConfig) -> Dict[str, Any]:
    """
    Run MassGen system with a complete configuration object.
    
    Args:
        question: The question to solve
        config: Complete MassConfig object
        
    Returns:
        Dict containing the answer and detailed results
    """
    # Validate configuration
    config.validate()
    
    # Check for single agent case
    if len(config.agents) == 1:
        logger.info("🔄 Single agent detected - using simple processing mode")
        return _run_single_agent_simple(question, config)
    
    # Continue with multi-agent orchestration for multiple agents
    logger.info("🔄 Multiple agents detected - using multi-agent orchestration")
    
    # Create task input
    task = TaskInput(question=question)
    
    # Create log manager first to get answers directory
    log_manager = MassLogManager(
        log_dir=config.logging.log_dir,
        session_id=config.logging.session_id,
        non_blocking=config.logging.non_blocking
    )
    
    # Create streaming display with answers directory from log manager
    streaming_orchestrator = None
    if config.streaming_display.display_enabled:
        streaming_orchestrator = create_streaming_display(
            display_enabled=config.streaming_display.display_enabled,
            max_lines=config.streaming_display.max_lines,
            save_logs=config.streaming_display.save_logs,
            stream_callback=config.streaming_display.stream_callback,
            answers_dir=str(log_manager.answers_dir) if not log_manager.non_blocking else None
        )
    
    # Create orchestrator with full configuration
    orchestrator = MassOrchestrator(
        max_duration=config.orchestrator.max_duration,
        consensus_threshold=config.orchestrator.consensus_threshold,
        max_debate_rounds=config.orchestrator.max_debate_rounds,
        status_check_interval=config.orchestrator.status_check_interval,
        thread_pool_timeout=config.orchestrator.thread_pool_timeout,
        streaming_orchestrator=streaming_orchestrator
    )
    
    # Set log manager
    orchestrator.log_manager = log_manager
    
    # Register agents
    for agent_config in config.agents:
        # Create stream callback that connects agent to streaming display
        stream_callback = None
        if streaming_orchestrator:
            # Create a proper closure that captures the agent_id
            def create_stream_callback(agent_id):
                def callback(content):
                    streaming_orchestrator.stream_output(agent_id, content)
                return callback
            stream_callback = create_stream_callback(agent_config.agent_id)
        
        agent = create_agent(
            agent_type=agent_config.agent_type,
            agent_id=agent_config.agent_id,
            orchestrator=orchestrator,
            model_config=agent_config.model_config,
            stream_callback=stream_callback
        )
        orchestrator.register_agent(agent)
    
    logger.info(f"🚀 Starting MassGen with {len(config.agents)} agents")
    logger.info(f"   Question: {question}")
    logger.info(f"   Models: {[agent.model_config.model for agent in config.agents]}")
    logger.info(f"   Max duration: {config.orchestrator.max_duration}s")
    logger.info(f"   Consensus threshold: {config.orchestrator.consensus_threshold}")
    
    # Start the task and get results
    try:
        result = orchestrator.start_task(task)
        logger.info("✅ MassGen completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"❌ MassGen failed: {e}")
        raise
    finally:
        # Cleanup
        orchestrator.cleanup()


class MassSystem:
    """
    Enhanced MassGen system interface with configuration support.
    """
    
    def __init__(self, config: MassConfig):
        """
        Initialize the MassGen system.
        
        Args:
            config: MassConfig object with complete configuration.
        """
        self.config = config
        
    def run(self, question: str) -> Dict[str, Any]:
        """
        Run MassGen system on a question using the configured setup.
        
        Args:
            question: The question to solve
            
        Returns:
            Dict containing the answer and detailed results
        """
        return run_mass_with_config(question, self.config)
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration parameters.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        # Update orchestrator config
        if 'max_duration' in kwargs:
            self.config.orchestrator.max_duration = kwargs['max_duration']
        if 'consensus_threshold' in kwargs:
            self.config.orchestrator.consensus_threshold = kwargs['consensus_threshold']
        if 'max_debate_rounds' in kwargs:
            self.config.orchestrator.max_debate_rounds = kwargs['max_debate_rounds']
            
        # Validate updated configuration
        self.config.validate()


def run_mass_agents(question: str, 
                   models: List[str],
                   max_duration: int = 600,
                   consensus_threshold: float = 0.0,
                   streaming_display: bool = True,
                   **kwargs) -> Dict[str, Any]:
    """
    Simple function to run MassGen agents on a question (backward compatibility).
    
    Args:
        question: The question to solve
        models: List of model names (e.g., ["gpt-4o", "gemini-2.5-flash"])
        max_duration: Maximum duration in seconds
        consensus_threshold: Consensus threshold
        streaming_display: Whether to show real-time progress
        **kwargs: Additional configuration parameters
        
    Returns:
        Dict containing the answer and detailed results
    """
    # Create configuration from models
    config = create_config_from_models(
        models=models,
        orchestrator_config={
            "max_duration": max_duration,
            "consensus_threshold": consensus_threshold,
            **{k: v for k, v in kwargs.items() if k in ['max_debate_rounds', 'status_check_interval']}
        },
        streaming_config={
            "display_enabled": streaming_display,
            **{k: v for k, v in kwargs.items() if k in ['max_lines', 'save_logs']}
        }
    )
    
    return run_mass_with_config(question, config) 