"""Broadcast channel for agent-to-agent and agent-to-human communication."""

import asyncio
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from massgen.broadcast.broadcast_dataclasses import (
    BroadcastRequest,
    BroadcastResponse,
    BroadcastStatus,
    StructuredQuestion,
    StructuredResponse,
)

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class BroadcastChannel:
    """Manages broadcast communication between agents and optionally humans.

    The BroadcastChannel handles the lifecycle of broadcast requests:
    1. Create broadcast request
    2. Inject question into agent queues
    3. Collect responses asynchronously
    4. Optionally wait for responses (blocking mode)
    5. Provide status and response retrieval

    When multiple agents call ask_others() simultaneously in human mode, their
    prompts are queued and shown one at a time to avoid overwhelming the user.

    Attributes:
        orchestrator: Reference to the orchestrator
        active_broadcasts: Dict of request_id -> BroadcastRequest
        broadcast_responses: Dict of request_id -> List[BroadcastResponse]
        response_events: Dict of request_id -> asyncio.Event (signals when responses complete)
        _lock: Lock for thread-safe operations on broadcast data
        _human_input_lock: Lock to serialize human input prompts (one modal at a time)
    """

    def __init__(self, orchestrator: "Orchestrator"):
        """Initialize the broadcast channel.

        Args:
            orchestrator: The orchestrator managing agents
        """
        self.orchestrator = orchestrator
        self.active_broadcasts: dict[str, BroadcastRequest] = {}
        self.broadcast_responses: dict[str, list[BroadcastResponse]] = {}
        self.response_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self._human_input_lock = asyncio.Lock()  # Serialize human input prompts
        self._human_ask_others_lock = asyncio.Lock()  # Serialize entire ask_others flow in human mode
        self._human_qa_history: list[dict[str, str]] = []  # Human Q&A pairs for this turn

    def get_human_qa_history(self) -> list[dict[str, str]]:
        """Get all human Q&A pairs from this turn.

        Returns:
            List of dicts with 'question' and 'answer' keys
        """
        return self._human_qa_history.copy()

    async def create_broadcast(
        self,
        sender_agent_id: str,
        question: str | list[StructuredQuestion],
        timeout: int | None = None,
        target_agents: list[str] | None = None,
    ) -> str:
        """Create a new broadcast request.

        Args:
            sender_agent_id: ID of the agent sending the broadcast
            question: The question to broadcast. Can be:
                - A simple string for open-ended questions
                - A list of StructuredQuestion objects for structured questions with options
            timeout: Maximum time to wait for responses (uses config default if None)
            target_agents: Optional list of specific agents to query (anonymous IDs like ['agent1', 'agent2']).
                If None, broadcasts to all other agents. If provided, only queries specified agents.

        Returns:
            The request_id for this broadcast

        Raises:
            ValueError: If sender_agent_id doesn't exist or rate limit exceeded
        """
        async with self._lock:
            # Check rate limiting
            sender_broadcasts = [b for b in self.active_broadcasts.values() if b.sender_agent_id == sender_agent_id]
            max_broadcasts = self.orchestrator.config.coordination_config.max_broadcasts_per_agent
            if len(sender_broadcasts) >= max_broadcasts:
                raise ValueError(
                    f"Agent {sender_agent_id} has reached the maximum number of " f"active broadcasts ({max_broadcasts})",
                )

            # Create broadcast request
            request_id = str(uuid.uuid4())
            if timeout is None:
                timeout = self.orchestrator.config.coordination_config.broadcast_timeout

            # Count expected responses based on mode and targeting
            if self.orchestrator.config.coordination_config.broadcast == "human":
                # Human mode: only human responds, not other agents
                expected_count = 1
            elif target_agents:
                # Targeted mode: only specified agents respond
                # Resolve anonymous IDs to real IDs and filter out sender
                real_target_ids = self._resolve_anonymous_to_real(target_agents)
                filtered_targets = [t for t in real_target_ids if t != sender_agent_id]

                # Validate that at least one valid target remains
                if not filtered_targets:
                    # Get valid anonymous agent IDs for error message
                    valid_anon_ids = list(self.orchestrator.coordination_tracker.get_anonymous_agent_mapping().keys())
                    # Filter out sender's anonymous ID
                    sender_anon_id = self.orchestrator.coordination_tracker.get_reverse_agent_mapping().get(sender_agent_id)
                    if sender_anon_id:
                        valid_anon_ids = [aid for aid in valid_anon_ids if aid != sender_anon_id]

                    error_msg = f"None of the specified target_agents are valid or available: {target_agents}. " f"Valid agent IDs (excluding sender): {valid_anon_ids}"
                    logger.error(f"📢 [Broadcast] {error_msg}")
                    raise ValueError(error_msg)

                expected_count = len(filtered_targets)
            else:
                # Broadcast mode: all agents except sender respond
                expected_count = len(self.orchestrator.agents) - 1

            broadcast = BroadcastRequest(
                id=request_id,
                sender_agent_id=sender_agent_id,
                question=question,
                timestamp=datetime.now(),
                timeout=timeout,
                expected_response_count=expected_count,
                target_agents=target_agents,  # Store for inject_into_agents()
            )

            self.active_broadcasts[request_id] = broadcast
            self.broadcast_responses[request_id] = []
            self.response_events[request_id] = asyncio.Event()

            return request_id

    async def inject_into_agents(self, request_id: str) -> None:
        """Handle broadcast distribution based on mode.

        In human mode: prompts the human for a response
        In agents mode: spawns shadow agents to respond in parallel

        Args:
            request_id: ID of the broadcast request

        Raises:
            ValueError: If request_id doesn't exist
        """
        async with self._lock:
            if request_id not in self.active_broadcasts:
                raise ValueError(f"Unknown broadcast request: {request_id}")

            broadcast = self.active_broadcasts[request_id]
            broadcast.status = BroadcastStatus.COLLECTING

        # Route based on broadcast mode
        if self.orchestrator.config.coordination_config.broadcast == "human":
            # Human mode: only prompt human, don't inject into other agents
            # This pauses execution until the human responds
            await self._prompt_human(request_id)
        else:
            # Agents mode: spawn shadow agents to respond in parallel
            await self._spawn_shadow_agents(request_id)

    async def _spawn_shadow_agents(self, request_id: str) -> None:
        """Spawn shadow agents to respond to a broadcast in parallel.

        Shadow agents share their parent's backend and context but have a
        simplified system prompt. They generate responses without interrupting
        the parent agent's work.

        Design: shadow tasks are fired as asyncio.create_task (fire-and-forget)
        so this method returns immediately, allowing wait_for_responses()'s
        broadcast_timeout to actually function as a guard. Each shadow task has
        its own per-task timeout (shadow_timeout) so a single slow/hung LLM call
        cannot block the entire broadcast indefinitely.

        Args:
            request_id: ID of the broadcast request
        """
        from .shadow_agent import ShadowAgentSpawner, inject_informational_to_parent

        broadcast = self.active_broadcasts[request_id]
        spawner = ShadowAgentSpawner(self.orchestrator)

        # Resolve per-shadow timeout from coordination config (default: 90s)
        shadow_timeout: int = 90
        try:
            shadow_timeout = int(
                getattr(self.orchestrator.config.coordination_config, "shadow_timeout", 90)
            )
        except Exception:
            pass

        # Get target agents based on broadcast.target_agents (if specified)
        if broadcast.target_agents:
            # Targeted mode: only query specified agents
            real_target_ids = self._resolve_anonymous_to_real(broadcast.target_agents)
            # Filter out sender and non-existent agents
            target_agents = [(agent_id, agent) for agent_id, agent in self.orchestrator.agents.items() if agent_id in real_target_ids and agent_id != broadcast.sender_agent_id]
            logger.info(
                f"[Broadcast] Targeting specific agents: {broadcast.target_agents} -> {[aid for aid, _ in target_agents]}",
            )
        else:
            # Broadcast mode: all agents except sender
            target_agents = [(agent_id, agent) for agent_id, agent in self.orchestrator.agents.items() if agent_id != broadcast.sender_agent_id]
            logger.info(
                "[Broadcast] Broadcasting to all agents",
            )

        if not target_agents:
            logger.warning(f"[Broadcast] No target agents for broadcast from {broadcast.sender_agent_id}")
            # FIX: set the event so wait_for_responses() doesn't block for broadcast_timeout
            async with self._lock:
                broadcast.status = BroadcastStatus.COMPLETE
            if request_id in self.response_events:
                self.response_events[request_id].set()
            return

        logger.info(
            f"[Broadcast] Spawning {len(target_agents)} shadow agents in parallel "
            f"for broadcast from {broadcast.sender_agent_id} "
            f"(shadow_timeout={shadow_timeout}s each)",
        )

        async def shadow_task_with_collect(target_id: str, target_agent) -> None:
            """Run one shadow agent, collect its response, inject to parent.

            Each shadow has an individual timeout (shadow_timeout). On timeout
            or error a placeholder response is collected so the broadcast can
            still complete within broadcast_timeout.

            Note: collect_response calls are guarded against the case where
            cleanup_broadcast() has already removed the request (e.g. broadcast_timeout
            fired and the caller cleaned up before this task finished).
            """
            async def _safe_collect(content: str) -> None:
                """Collect response, silently ignoring post-cleanup races."""
                try:
                    await self.collect_response(
                        request_id=request_id,
                        responder_id=f"shadow_{target_id}",
                        content=content,
                        is_human=False,
                    )
                except ValueError:
                    # broadcast was already cleaned up (timeout fired) — ignore
                    logger.debug(
                        f"[Broadcast] Shadow {target_id} tried to collect after cleanup "
                        f"(broadcast {request_id[:8]}... already removed) — ignoring",
                    )

            try:
                response = await asyncio.wait_for(
                    spawner.spawn_and_respond(target_agent, broadcast),
                    timeout=shadow_timeout,
                )
                await _safe_collect(response)
                # Inject informational message to parent agent
                parent_agent = self.orchestrator.agents.get(target_id)
                if parent_agent:
                    await inject_informational_to_parent(parent_agent, broadcast, response)

            except asyncio.TimeoutError:
                logger.warning(
                    f"[Broadcast] Shadow for {target_id} timed out after {shadow_timeout}s "
                    f"(broadcast {request_id[:8]}...)",
                )
                await _safe_collect(
                    f"[Shadow agent timed out after {shadow_timeout}s — no response available]"
                )

            except Exception as e:
                logger.error(f"[Broadcast] Shadow for {target_id} failed: {e}")
                await _safe_collect(f"[Shadow agent error: {e}]")

        # Fire all shadow tasks concurrently and return immediately.
        # collect_response inside each task sets the response_events when the last
        # response arrives. wait_for_responses()'s broadcast_timeout is now the
        # real upper bound for the entire broadcast.
        for target_id, target_agent in target_agents:
            asyncio.create_task(shadow_task_with_collect(target_id, target_agent))

        logger.info(
            f"[Broadcast] {len(target_agents)} shadow task(s) launched for "
            f"broadcast {request_id[:8]}... — returning to caller, "
            f"broadcast_timeout will guard completion",
        )

    async def wait_for_responses(
        self,
        request_id: str,
        timeout: int | None = None,
    ) -> dict[str, any]:
        """Wait for responses to be collected (blocking mode).

        Args:
            request_id: ID of the broadcast request
            timeout: Maximum time to wait (uses broadcast timeout if None)

        Returns:
            Dictionary with status and responses

        Raises:
            ValueError: If request_id doesn't exist
        """
        if request_id not in self.active_broadcasts:
            raise ValueError(f"Unknown broadcast request: {request_id}")

        broadcast = self.active_broadcasts[request_id]
        if timeout is None:
            timeout = broadcast.timeout

        # Wait for responses or timeout
        try:
            await asyncio.wait_for(
                self.response_events[request_id].wait(),
                timeout=timeout,
            )
        except TimeoutError:
            async with self._lock:
                broadcast.status = BroadcastStatus.TIMEOUT

        return self.get_broadcast_responses(request_id)

    async def collect_response(
        self,
        request_id: str,
        responder_id: str,
        content: str | list[StructuredResponse],
        is_human: bool = False,
    ) -> None:
        """Collect a response from an agent or human.

        Args:
            request_id: ID of the broadcast request
            responder_id: ID of the responder (agent ID or "human")
            content: The response content. Can be:
                - A simple string for text responses
                - A list of StructuredResponse objects for structured question responses
            is_human: Whether this is a human response

        Raises:
            ValueError: If request_id doesn't exist
        """
        async with self._lock:
            if request_id not in self.active_broadcasts:
                raise ValueError(f"Unknown broadcast request: {request_id}")

            broadcast = self.active_broadcasts[request_id]

            # Create response
            response = BroadcastResponse(
                request_id=request_id,
                responder_id=responder_id,
                content=content,
                timestamp=datetime.now(),
                is_human=is_human,
            )

            self.broadcast_responses[request_id].append(response)
            broadcast.responses_received += 1

            # Check if all responses collected
            if broadcast.responses_received >= broadcast.expected_response_count:
                broadcast.status = BroadcastStatus.COMPLETE
                self.response_events[request_id].set()

    def get_broadcast_status(self, request_id: str) -> dict[str, any]:
        """Get the current status of a broadcast request.

        Args:
            request_id: ID of the broadcast request

        Returns:
            Dictionary with status information

        Raises:
            ValueError: If request_id doesn't exist
        """
        if request_id not in self.active_broadcasts:
            raise ValueError(f"Unknown broadcast request: {request_id}")

        broadcast = self.active_broadcasts[request_id]
        responses = self.broadcast_responses.get(request_id, [])

        # Determine which agents are still pending
        responding_agent_ids = {r.responder_id for r in responses if not r.is_human}
        all_agent_ids = {aid for aid in self.orchestrator.agents.keys() if aid != broadcast.sender_agent_id}
        waiting_for = list(all_agent_ids - responding_agent_ids)

        return {
            "status": broadcast.status.value,
            "response_count": broadcast.responses_received,
            "expected_count": broadcast.expected_response_count,
            "waiting_for": waiting_for,
        }

    def get_broadcast_responses(self, request_id: str) -> dict[str, any]:
        """Get responses for a broadcast request.

        Args:
            request_id: ID of the broadcast request

        Returns:
            Dictionary with status and responses

        Raises:
            ValueError: If request_id doesn't exist
        """
        if request_id not in self.active_broadcasts:
            raise ValueError(f"Unknown broadcast request: {request_id}")

        broadcast = self.active_broadcasts[request_id]
        responses = self.broadcast_responses.get(request_id, [])

        return {
            "status": broadcast.status.value,
            "responses": [r.to_dict() for r in responses],
        }

    async def _prompt_human(self, request_id: str) -> None:
        """Prompt human for response (BLOCKING - pauses all agent execution).

        This method uses a lock to ensure only one human prompt is shown at a time.
        If multiple agents call ask_others() simultaneously, they will queue up.

        Args:
            request_id: ID of the broadcast request
        """
        if request_id not in self.active_broadcasts:
            logger.warning(f"📢 [Human] Broadcast request {request_id[:8]}... not found")
            return

        broadcast = self.active_broadcasts[request_id]

        # Check if lock is already held (another prompt is active)
        if self._human_input_lock.locked():
            logger.info(f"📢 [Human] Waiting in queue for broadcast from {broadcast.sender_agent_id} (another prompt is active)")

        # Acquire lock to serialize human prompts - only one modal at a time
        async with self._human_input_lock:
            question_preview = broadcast.question_text[:50] if broadcast.question_text else "structured questions"
            logger.info(f"📢 [Human] Prompting human for broadcast from {broadcast.sender_agent_id}: {question_preview}...")

            # Use coordination UI to prompt human
            if hasattr(self.orchestrator, "coordination_ui") and self.orchestrator.coordination_ui:
                try:
                    human_response = await asyncio.wait_for(
                        self.orchestrator.coordination_ui.prompt_for_broadcast_response(broadcast),
                        timeout=broadcast.timeout,
                    )

                    if human_response:
                        # Handle response based on type
                        if isinstance(human_response, list):
                            # Structured response - convert dicts to StructuredResponse objects if needed
                            structured_responses = []
                            for resp in human_response:
                                if isinstance(resp, StructuredResponse):
                                    structured_responses.append(resp)
                                elif isinstance(resp, dict):
                                    structured_responses.append(StructuredResponse.from_dict(resp))
                            response_content = structured_responses
                            response_preview = f"structured ({len(structured_responses)} answers)"
                        else:
                            # Simple string response
                            response_content = human_response
                            response_preview = human_response[:50] if isinstance(human_response, str) else str(human_response)[:50]

                        logger.info(f"📢 [Human] Received response: {response_preview}...")
                        await self.collect_response(
                            request_id=request_id,
                            responder_id="human",
                            content=response_content,
                            is_human=True,
                        )

                        # Store Q&A for context injection
                        # For structured questions, store serialized form
                        if broadcast.is_structured:
                            question_data = [q.to_dict() for q in broadcast.structured_questions]
                            answer_data = [r.to_dict() if isinstance(r, StructuredResponse) else r for r in (response_content if isinstance(response_content, list) else [response_content])]
                        else:
                            question_data = broadcast.question
                            answer_data = response_content

                        self._human_qa_history.append(
                            {
                                "question": question_data,
                                "answer": answer_data,
                            },
                        )
                        logger.info(f"📢 [Human] Stored Q&A (total: {len(self._human_qa_history)})")
                    else:
                        logger.info("📢 [Human] No response provided (skipped)")
                except TimeoutError:
                    logger.info("📢 [Human] Timeout - no response received")
                except Exception as e:
                    logger.error(f"📢 [Human] Error prompting for response: {e}")
            else:
                logger.warning("📢 [Human] No coordination_ui available for prompting")

    def _resolve_anonymous_to_real(self, anonymous_ids: list[str]) -> list[str]:
        """Map anonymous agent IDs (agent1, agent2) to real IDs (agent_a, agent_b).

        Args:
            anonymous_ids: List of anonymous agent IDs (e.g., ['agent1', 'agent2'])

        Returns:
            List of real agent IDs corresponding to the anonymous IDs

        Note:
            Uses coordination tracker's forward mapping to resolve anonymous IDs.
            Invalid anonymous IDs are filtered out (not included in result).
        """
        # Get forward mapping from coordination tracker (anonymous_id -> real_id)
        anon_to_real = self.orchestrator.coordination_tracker.get_anonymous_agent_mapping()

        # Map anonymous IDs to real IDs, filtering out invalid ones
        real_ids = []
        for anon_id in anonymous_ids:
            real_id = anon_to_real.get(anon_id)
            if real_id:
                real_ids.append(real_id)
            else:
                logger.warning(f"📢 [Broadcast] Invalid anonymous agent ID: {anon_id} (not in mapping)")

        return real_ids

    async def cleanup_broadcast(self, request_id: str) -> None:
        """Clean up resources for a completed broadcast.

        Args:
            request_id: ID of the broadcast request

        Raises:
            ValueError: If request_id doesn't exist
        """
        async with self._lock:
            if request_id in self.active_broadcasts:
                del self.active_broadcasts[request_id]
            if request_id in self.broadcast_responses:
                del self.broadcast_responses[request_id]
            if request_id in self.response_events:
                del self.response_events[request_id]
