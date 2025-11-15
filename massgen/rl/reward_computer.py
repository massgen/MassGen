"""
Reward Computer for RL

This module computes different types of reward signals
for reinforcement learning, following the design from
massgen_rl_integration_design.md
"""

from typing import Any, Dict, Optional
import re


class RewardComputer:
    """
    Computes different types of reward signals.

    This class provides methods to compute rewards for:
    - Tool calls (success/failure, result quality)
    - Answer quality (structure, depth, accuracy)
    - Coordination (efficiency, consensus)
    - Voting (accuracy)
    """

    def __init__(self):
        """Initialize reward computer"""
        pass

    def compute_tool_reward(self, tool_call: Dict, result: Any) -> float:
        """
        Compute tool call reward.

        Reward is based on:
        - Tool call success/failure
        - Result usefulness
        - Execution efficiency

        Args:
            tool_call: Tool call information (name, arguments)
            result: Tool execution result

        Returns:
            Reward value (typically -1.0 to 1.0)
        """
        # Check if result indicates an error
        if isinstance(result, Exception):
            return -1.0  # Failure penalty

        if result is None:
            return -0.5  # No result

        # Base success reward
        reward = 1.0

        # Adjust based on tool type
        tool_name = tool_call.get('name', '')

        if 'search' in tool_name.lower():
            reward *= self._evaluate_search_quality(result)
        elif 'code' in tool_name.lower() or 'execute' in tool_name.lower():
            reward *= self._evaluate_code_quality(result)
        elif 'vote' in tool_name.lower():
            # Voting tool - neutral reward at call time
            # Actual reward computed after voting completes
            reward = 0.5
        elif 'new_answer' in tool_name.lower():
            # Answer submission - neutral reward at call time
            reward = 0.5

        return reward

    def _evaluate_search_quality(self, result: Any) -> float:
        """
        Evaluate search result quality.

        Args:
            result: Search result

        Returns:
            Quality multiplier (0.0 to 1.0)
        """
        if not result:
            return 0.0

        # Check if result has content
        if isinstance(result, dict):
            if result.get('error'):
                return 0.3
            if result.get('results') or result.get('articles'):
                return 1.0
            return 0.5
        elif isinstance(result, str):
            # Non-empty string result
            if len(result) > 100:
                return 1.0
            elif len(result) > 0:
                return 0.7
            return 0.3

        return 0.5

    def _evaluate_code_quality(self, result: Any) -> float:
        """
        Evaluate code execution result quality.

        Args:
            result: Code execution result

        Returns:
            Quality multiplier (0.0 to 1.0)
        """
        if not result:
            return 0.0

        if isinstance(result, dict):
            if result.get('error'):
                return 0.2
            if result.get('output') or result.get('stdout'):
                return 1.0
            return 0.5
        elif isinstance(result, str):
            # Check for error indicators
            if 'error' in result.lower() or 'exception' in result.lower():
                return 0.3
            # Successful execution
            return 1.0

        return 0.5

    def compute_answer_quality_reward(
        self,
        answer: str,
        reference: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Compute answer quality reward.

        Can be based on:
        - Similarity to reference answer
        - Structural quality (headings, paragraphs)
        - Content depth
        - Automatic evaluation metrics (BLEU, ROUGE, etc.)

        Args:
            answer: Answer text
            reference: Optional reference answer
            metrics: Optional pre-computed metrics

        Returns:
            Reward value (0.0 to 1.0+)
        """
        if not answer or len(answer.strip()) == 0:
            return 0.0

        reward = 0.0

        # Structural reward
        structure_score = self._evaluate_answer_structure(answer)
        reward += 0.3 * structure_score

        # Depth reward
        depth_score = self._evaluate_answer_depth(answer)
        reward += 0.4 * depth_score

        # Reference similarity (if available)
        if reference:
            similarity = self._compute_similarity(answer, reference)
            reward += 0.3 * similarity

        # External metrics (if provided)
        if metrics:
            avg_metric = sum(metrics.values()) / len(metrics)
            reward += 0.3 * avg_metric

        return reward

    def _evaluate_answer_structure(self, answer: str) -> float:
        """
        Evaluate answer structural quality.

        Checks for:
        - Clear paragraphs
        - Headings
        - Bullet points or numbered lists
        - Logical organization

        Args:
            answer: Answer text

        Returns:
            Structure score (0.0 to 1.0)
        """
        score = 0.0

        # Check for paragraphs (multiple line breaks)
        paragraphs = [p.strip() for p in answer.split('\n\n') if p.strip()]
        if len(paragraphs) >= 2:
            score += 0.3
        elif len(paragraphs) == 1:
            score += 0.1

        # Check for headings (lines starting with # or all caps)
        headings = re.findall(r'^#{1,6}\s+.+|^[A-Z\s]{5,}$', answer, re.MULTILINE)
        if len(headings) >= 2:
            score += 0.3
        elif len(headings) == 1:
            score += 0.15

        # Check for lists
        has_bullets = bool(re.search(r'^\s*[-*•]\s+', answer, re.MULTILINE))
        has_numbers = bool(re.search(r'^\s*\d+\.\s+', answer, re.MULTILINE))
        if has_bullets or has_numbers:
            score += 0.2

        # Check for conclusion keywords
        conclusion_keywords = ['conclusion', 'summary', 'in summary', 'to conclude', 'overall']
        if any(keyword in answer.lower() for keyword in conclusion_keywords):
            score += 0.2

        return min(score, 1.0)

    def _evaluate_answer_depth(self, answer: str) -> float:
        """
        Evaluate answer content depth.

        Considers:
        - Length (not too short, not too verbose)
        - Use of specific examples
        - Technical details
        - Reasoning/explanation

        Args:
            answer: Answer text

        Returns:
            Depth score (0.0 to 1.0)
        """
        score = 0.0

        # Length check (sweet spot: 200-2000 characters)
        length = len(answer)
        if 200 <= length <= 2000:
            score += 0.4
        elif 100 <= length < 200:
            score += 0.2
        elif length > 2000:
            score += 0.3  # Long but might be comprehensive

        # Check for examples
        example_keywords = ['for example', 'for instance', 'such as', 'e.g.', 'specifically']
        if any(keyword in answer.lower() for keyword in example_keywords):
            score += 0.2

        # Check for reasoning/explanation
        reasoning_keywords = ['because', 'therefore', 'thus', 'since', 'as a result', 'consequently']
        reasoning_count = sum(1 for keyword in reasoning_keywords if keyword in answer.lower())
        score += min(0.2, reasoning_count * 0.05)

        # Check for data/numbers (indicates specificity)
        has_numbers = bool(re.search(r'\d+\.?\d*%|\d+', answer))
        if has_numbers:
            score += 0.2

        return min(score, 1.0)

    def _compute_similarity(self, answer: str, reference: str) -> float:
        """
        Compute similarity between answer and reference.

        Uses simple word overlap as a proxy for more sophisticated
        metrics like BLEU or ROUGE.

        Args:
            answer: Answer text
            reference: Reference text

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Simple word-based similarity
        answer_words = set(answer.lower().split())
        reference_words = set(reference.lower().split())

        if not reference_words:
            return 0.0

        # Jaccard similarity
        intersection = answer_words & reference_words
        union = answer_words | reference_words

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def compute_coordination_reward(
        self,
        coordination_rounds: int,
        final_answer_quality: float,
        token_usage: int,
        consensus_achieved: bool,
        max_rounds: int = 5
    ) -> float:
        """
        Compute coordination process reward.

        Args:
            coordination_rounds: Number of coordination rounds
            final_answer_quality: Quality of final answer (0.0 to 1.0)
            token_usage: Total tokens used
            consensus_achieved: Whether consensus was reached
            max_rounds: Maximum expected rounds

        Returns:
            Coordination reward
        """
        # Penalize too many rounds
        round_penalty = -0.1 * max(0, coordination_rounds - 3)

        # Reward answer quality (most important)
        quality_reward = 2.0 * final_answer_quality

        # Penalize excessive token usage
        # Assume 10000 tokens is reasonable, penalize beyond that
        token_penalty = -0.001 * max(0, token_usage - 10000)

        # Reward consensus achievement
        consensus_reward = 1.0 if consensus_achieved else -0.5

        # Bonus for efficiency (quick consensus with quality)
        efficiency_bonus = 0.0
        if consensus_achieved and coordination_rounds <= 2 and final_answer_quality > 0.7:
            efficiency_bonus = 0.5

        total_reward = (
            round_penalty +
            quality_reward +
            token_penalty +
            consensus_reward +
            efficiency_bonus
        )

        return total_reward

    def compute_voting_reward(self, voted_for: str, actual_winner: str) -> float:
        """
        Compute voting accuracy reward.

        Args:
            voted_for: Agent ID that was voted for
            actual_winner: Agent ID that actually won

        Returns:
            Voting reward
        """
        if voted_for == actual_winner:
            return 1.0  # Correct vote
        else:
            return -0.5  # Incorrect vote

    def compute_restart_decision_reward(
        self,
        decision: bool,
        previous_quality: float,
        new_quality: Optional[float] = None
    ) -> float:
        """
        Compute reward for restart decision.

        Args:
            decision: Whether restart was triggered
            previous_quality: Quality before restart
            new_quality: Quality after restart (if restart happened)

        Returns:
            Restart decision reward
        """
        if not decision:
            # Decided not to restart
            if previous_quality > 0.7:
                return 0.5  # Good decision, quality was already high
            else:
                return -0.3  # Missed opportunity to improve

        # Decided to restart
        if new_quality is None:
            # Restart just triggered, can't evaluate yet
            return 0.0

        # Evaluate restart outcome
        improvement = new_quality - previous_quality
        if improvement > 0.2:
            return 1.0  # Great improvement
        elif improvement > 0:
            return 0.5  # Some improvement
        else:
            return -0.5  # Restart didn't help
