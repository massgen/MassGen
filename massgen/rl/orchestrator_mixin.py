"""
RL Orchestrator Mixin

This module provides a mixin class to add RL trace collection
capabilities to the Orchestrator class for multi-agent coordination.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional
import time

from .config import RLConfig
from .trace_collector import TraceCollector
from .reward_computer import RewardComputer
from ..stream_chunk import ChunkType, TextStreamChunk


class RLOrchestratorMixin:
    """
    Mixin to add coordination strategy learning capabilities to Orchestrator.

    This mixin enables the orchestrator to collect traces about:
    - Voting decisions and outcomes
    - Answer submission timing
    - Restart decisions
    - Coordination efficiency

    Usage:
        class RLOrchestrator(RLOrchestratorMixin, Orchestrator):
            pass

        orchestrator = RLOrchestrator(
            agents=agents,
            enable_rl=True,
            rl_config=RLConfig(...)
        )
    """

    def __init__(
        self,
        *args,
        enable_rl: bool = False,
        rl_config: Optional[RLConfig] = None,
        **kwargs
    ):
        """
        Initialize RL capabilities for orchestrator.

        Args:
            enable_rl: Whether to enable RL trace collection
            rl_config: RL configuration
            *args, **kwargs: Arguments for the parent class
        """
        # Initialize parent class first
        super().__init__(*args, **kwargs)

        # RL configuration
        self.enable_rl = enable_rl
        self.rl_config = rl_config or RLConfig()

        # Initialize RL components if enabled
        if self.enable_rl:
            # Get orchestrator_id from self
            orchestrator_id = getattr(self, 'orchestrator_id', 'orchestrator')

            self.trace_collector = TraceCollector(
                agent_id=orchestrator_id,
                store_config=self.rl_config.store_config
            )
            self.reward_computer = RewardComputer()
            self._coordination_trace_id = None
            self._coordination_start_time = 0
            self._coordination_rounds_count = 0
            self._total_tokens_at_start = 0

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[TextStreamChunk, None]:
        """
        Override chat method to add coordination trace collection.

        Args:
            messages: Conversation messages
            **kwargs: Additional arguments

        Yields:
            StreamChunk: Streaming response chunks
        """
        # Start coordination trace if RL is enabled
        if self.enable_rl:
            # Extract task from messages
            task = self._extract_task_from_messages(messages)

            # Get number of agents
            num_agents = len(getattr(self, 'agents', {}))

            self._coordination_trace_id = self.trace_collector.start_coordination_trace(
                task=task,
                num_agents=num_agents,
                metadata={
                    'orchestrator_id': getattr(self, 'orchestrator_id', 'unknown'),
                    'num_agents': num_agents,
                    'agent_ids': list(getattr(self, 'agents', {}).keys())
                }
            )

            self._coordination_start_time = time.time()
            self._coordination_rounds_count = 0
            self._total_tokens_at_start = getattr(self, 'total_tokens', 0)

        # Call parent chat method and collect coordination spans
        try:
            async for chunk in super().chat(messages, **kwargs):
                # Collect coordination span from chunk
                if self.enable_rl:
                    await self._collect_coordination_span(chunk)

                yield chunk

            # Successfully completed - compute coordination reward
            if self.enable_rl and self._coordination_trace_id:
                await self._record_coordination_reward()
                await self.trace_collector.end_trace(self._coordination_trace_id)
                self._coordination_trace_id = None

        except Exception as e:
            # Handle errors
            if self.enable_rl and self._coordination_trace_id:
                await self.trace_collector.fail_trace(
                    self._coordination_trace_id,
                    error=str(e)
                )
                self._coordination_trace_id = None
            raise

    def _extract_task_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Extract task description from messages.

        Args:
            messages: List of messages

        Returns:
            Task description (usually the last user message)
        """
        # Find last user message
        for message in reversed(messages):
            if message.get('role') == 'user':
                content = message.get('content', '')
                # Truncate if too long
                if len(content) > 500:
                    return content[:500] + "..."
                return content

        return "Unknown task"

    async def _collect_coordination_span(self, chunk: TextStreamChunk):
        """
        Collect spans from coordination process.

        This method monitors chunks for coordination-related events
        like voting, answer submission, and restart decisions.

        Args:
            chunk: Stream chunk from orchestrator
        """
        if not self._coordination_trace_id:
            return

        # We can infer coordination events from chunk metadata
        # In a real implementation, we would need hooks into the
        # orchestrator's internal methods. For now, we track
        # what we can from the stream.

        # Track content chunks (may indicate coordination rounds)
        if chunk.type == ChunkType.CONTENT and chunk.source:
            # This is an agent response
            pass

        # Track agent status changes
        if chunk.type == ChunkType.AGENT_STATUS:
            if chunk.status:
                # Record agent status change
                self.trace_collector.emit_coordination_span(
                    trace_id=self._coordination_trace_id,
                    action_type="agent_status",
                    action_data={
                        "status": chunk.status,
                        "source": chunk.source
                    },
                    coordination_round=self._coordination_rounds_count
                )

    async def _record_vote_event(
        self,
        voter_id: str,
        voted_for: str,
        reasoning: Optional[str] = None
    ):
        """
        Record a voting event.

        This should be called when an agent casts a vote.

        Args:
            voter_id: Agent ID that is voting
            voted_for: Agent ID being voted for
            reasoning: Optional voting reasoning
        """
        if not self.enable_rl or not self._coordination_trace_id:
            return

        # Get current agent states
        agent_states = getattr(self, 'agent_states', {})

        self.trace_collector.emit_coordination_span(
            trace_id=self._coordination_trace_id,
            action_type="vote",
            action_data={
                "voter": voter_id,
                "voted_for": voted_for,
                "reasoning": reasoning
            },
            agent_states=agent_states,
            coordination_round=self._coordination_rounds_count
        )

    async def _record_new_answer_event(
        self,
        agent_id: str,
        answer_summary: str
    ):
        """
        Record a new answer submission event.

        This should be called when an agent submits a new answer.

        Args:
            agent_id: Agent ID submitting the answer
            answer_summary: Summary of the answer
        """
        if not self.enable_rl or not self._coordination_trace_id:
            return

        # Get current agent states
        agent_states = getattr(self, 'agent_states', {})

        self.trace_collector.emit_coordination_span(
            trace_id=self._coordination_trace_id,
            action_type="new_answer",
            action_data={
                "agent_id": agent_id,
                "answer_summary": answer_summary[:200]  # Truncate
            },
            agent_states=agent_states,
            coordination_round=self._coordination_rounds_count
        )

    async def _record_restart_decision(
        self,
        should_restart: bool,
        reason: Optional[str] = None
    ):
        """
        Record a restart decision.

        This should be called when the orchestrator decides
        whether to restart coordination.

        Args:
            should_restart: Whether restart was triggered
            reason: Reason for the decision
        """
        if not self.enable_rl or not self._coordination_trace_id:
            return

        # Get current agent states
        agent_states = getattr(self, 'agent_states', {})
        current_attempt = getattr(self, 'current_attempt', 0)
        max_attempts = getattr(self, 'max_attempts', 1)

        self.trace_collector.emit_coordination_span(
            trace_id=self._coordination_trace_id,
            action_type="restart_decision",
            action_data={
                "should_restart": should_restart,
                "reason": reason,
                "current_attempt": current_attempt,
                "max_attempts": max_attempts
            },
            agent_states=agent_states,
            coordination_round=self._coordination_rounds_count
        )

    async def _record_coordination_reward(self):
        """
        Calculate and record overall coordination quality reward.

        This is called at the end of coordination to evaluate
        the overall performance.
        """
        if not self.enable_rl or not self._coordination_trace_id:
            return

        if not self.rl_config.enable_coordination_rewards:
            return

        # Get coordination metrics
        duration = time.time() - self._coordination_start_time
        current_attempt = getattr(self, 'current_attempt', 0)
        coordination_rounds = current_attempt + 1

        # Get token usage
        total_tokens_used = getattr(self, 'total_tokens', 0) - self._total_tokens_at_start

        # Check if consensus was achieved
        selected_agent = getattr(self, '_selected_agent', None)
        consensus_achieved = selected_agent is not None

        # Evaluate final answer quality
        final_answer_quality = 0.7  # Default
        if consensus_achieved and hasattr(self, 'agent_states'):
            agent_states = getattr(self, 'agent_states', {})
            if selected_agent and selected_agent in agent_states:
                answer = agent_states[selected_agent].answer
                if answer:
                    final_answer_quality = self.reward_computer.compute_answer_quality_reward(
                        answer=answer
                    )

        # Compute coordination reward
        coordination_reward = self.reward_computer.compute_coordination_reward(
            coordination_rounds=coordination_rounds,
            final_answer_quality=final_answer_quality,
            token_usage=total_tokens_used,
            consensus_achieved=consensus_achieved
        )

        # Record reward
        self.trace_collector.emit_reward_span(
            trace_id=self._coordination_trace_id,
            reward=coordination_reward,
            reward_type="coordination",
            reason=f"Coordination completed in {coordination_rounds} rounds, "
                   f"consensus={'achieved' if consensus_achieved else 'failed'}, "
                   f"quality={final_answer_quality:.2f}"
        )

        # Also record voting rewards for agents that voted correctly
        if consensus_achieved and hasattr(self, 'agent_states'):
            agent_states = getattr(self, 'agent_states', {})
            for agent_id, state in agent_states.items():
                if state.has_voted and state.votes:
                    voted_for = state.votes.get('for_agent_id')
                    if voted_for:
                        voting_reward = self.reward_computer.compute_voting_reward(
                            voted_for=voted_for,
                            actual_winner=selected_agent
                        )

                        # Record voting reward
                        # Note: In a full implementation, this would be recorded
                        # to the individual agent's trace, not the coordination trace
                        self.trace_collector.emit_reward_span(
                            trace_id=self._coordination_trace_id,
                            reward=voting_reward,
                            reward_type="voting",
                            reason=f"Agent {agent_id} voting accuracy reward"
                        )

    def get_rl_statistics(self) -> Dict[str, Any]:
        """
        Get RL coordination statistics.

        Returns:
            Dictionary with statistics
        """
        if not self.enable_rl:
            return {"enabled": False}

        return {
            "enabled": True,
            "coordination_trace_active": self._coordination_trace_id is not None,
            "coordination_trace_id": self._coordination_trace_id,
            "coordination_rounds": self._coordination_rounds_count,
            "config": {
                "enable_coordination_rewards": self.rl_config.enable_coordination_rewards,
                "collect_only": self.rl_config.collect_only
            }
        }

    def increment_coordination_round(self):
        """
        Increment the coordination round counter.

        This should be called at the start of each coordination round.
        """
        if self.enable_rl:
            self._coordination_rounds_count += 1
