# -*- coding: utf-8 -*-
"""
DSPy-based question paraphrasing for multi-agent coordination.

This module provides intelligent question paraphrasing using DSPy to enhance
diversity in multi-agent systems while maintaining semantic equivalence.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    import dspy
except ImportError:
    dspy = None

from .logger_config import logger

if dspy is not None:

    class ParaphraseSignature(dspy.Signature):
        """Signature for paraphrasing questions while preserving meaning.

        This signature ensures semantic equivalence while encouraging diverse phrasing.
        """

        original_question: str = dspy.InputField(
            desc="The original question from the user that needs to be paraphrased",
        )
        context: str = dspy.InputField(
            desc="Context about how to paraphrase (e.g., diverse, conservative, adaptive)",
            default="Create a natural rephrasing that maintains the exact meaning and intent",
        )
        rewritten_question: str = dspy.OutputField(
            desc="A paraphrased version with identical meaning but different phrasing. " "Must ask for the same information using different words and structure.",
        )

    class SemanticValidationSignature(dspy.Signature):
        """Signature for validating semantic equivalence between questions."""

        original: str = dspy.InputField(desc="Original question")
        paraphrase: str = dspy.InputField(desc="Paraphrased question")
        equivalent: bool = dspy.OutputField(
            desc="True if both questions ask for exactly the same information",
        )
        confidence: float = dspy.OutputField(
            desc="Confidence score between 0 and 1",
        )

else:
    ParaphraseSignature = None
    SemanticValidationSignature = None


class QuestionParaphraser:
    """DSPy-based question paraphraser for multi-agent coordination.

    This class generates diverse paraphrases of questions to encourage different
    perspectives from agents while maintaining semantic equivalence.
    """

    def __init__(
        self,
        lm: "dspy.LM",
        num_variants: int = 3,
        strategy: str = "balanced",
        cache_enabled: bool = True,
        semantic_threshold: float = 0.85,
        temperature_range: Tuple[float, float] = (0.3, 0.9),
        use_chain_of_thought: bool = False,
        validate_semantics: bool = True,
    ):
        """Initialize the paraphraser.

        Args:
            lm: DSPy language model instance
            num_variants: Number of paraphrase variants to generate
            strategy: Paraphrasing strategy ('balanced', 'diverse',
                     'conservative', 'adaptive')
            cache_enabled: Whether to cache paraphrases
            semantic_threshold: Minimum semantic similarity threshold
            temperature_range: Temperature range for diversity control
            use_chain_of_thought: Use ChainOfThought for better reasoning (default: False for cost efficiency)
            validate_semantics: Whether to validate semantic equivalence
        """
        if dspy is None:
            raise ImportError(
                "DSPy is not installed. Install with: pip install 'dspy>=2.5.0'",
            )

        self.lm = lm
        self.num_variants = num_variants
        self.strategy = strategy
        self.cache_enabled = cache_enabled
        self.semantic_threshold = semantic_threshold
        self.temperature_range = temperature_range
        self.use_chain_of_thought = use_chain_of_thought
        self.validate_semantics = validate_semantics
        self._lm_lock = threading.Lock()

        # Temperature handling: respect LM's temperature if explicitly set (fixed value for all variants)
        # If LM was created with explicit temperature, use that fixed value for all paraphrases
        # Otherwise, use temperature_range for dynamic diversity
        lm_temperature = lm.kwargs.get("temperature") if lm.kwargs else None
        if lm_temperature is not None:
            # LM has explicit temperature - use it as fixed value (ignore temperature_range for all variants)
            self.temperature_range = (lm_temperature, lm_temperature)
            self._use_fixed_temperature = True
            logger.info(f"Using fixed temperature {lm_temperature} from backend config (overrides temperature_range)")
        else:
            # No LM temperature - use dynamic temperature_range for diversity
            self._use_fixed_temperature = False
            logger.debug(f"Using dynamic temperature range {self.temperature_range}")

        # Configure DSPy
        dspy.configure(lm=self.lm)

        # Create paraphraser module (ChainOfThought optional for deeper reasoning)
        if use_chain_of_thought:
            self.paraphraser = dspy.ChainOfThought(ParaphraseSignature)
        else:
            self.paraphraser = dspy.Predict(ParaphraseSignature)

        # Create semantic validator if enabled
        if validate_semantics:
            self.validator = dspy.Predict(SemanticValidationSignature)

        # Simple in-memory cache
        self._cache: Dict[str, List[str]] = {}

        # Metrics tracking for optimization
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_paraphrases": 0,
            "failed_validations": 0,
            "semantic_failures": 0,
            "generation_attempts": 0,
        }

    def generate_variants(
        self,
        question: str,
        context: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> List[str]:
        """Generate N paraphrased variants of the question.

        Args:
            question: Original question to paraphrase
            context: Optional context for paraphrasing
            force_regenerate: Bypass cache and regenerate

        Returns:
            List of paraphrased variants
        """
        # Check cache
        if self.cache_enabled and not force_regenerate:
            cache_key = self._get_cache_key(question, context)
            if cache_key in self._cache:
                self._metrics["cache_hits"] += 1
                return self._cache[cache_key]
            self._metrics["cache_misses"] += 1

        variants = []
        seen_paraphrases = {question.lower()}  # Track normalized versions to avoid duplicates

        # Use different temperatures for diversity across variants
        temperatures = self._get_temperature_schedule()

        attempts = 0
        max_attempts = self.num_variants * 4  # Allow more retries to avoid failures

        while len(variants) < self.num_variants and attempts < max_attempts:
            attempts += 1
            self._metrics["generation_attempts"] += 1  # Track attempts to generate variants

            # Adjust temperature for this attempt and generate under lock to avoid race conditions
            temp_idx = len(variants) % len(temperatures)

            with self._lm_lock:
                # Only change temperature if not using fixed temperature from backend config
                if not self._use_fixed_temperature:
                    self.lm.kwargs["temperature"] = temperatures[temp_idx]

                try:
                    # Generate paraphrase with context to guide the paraphrasing process
                    prompt_context = context or self._get_strategy_context()

                    # Add diversity hint if we're struggling to generate variants
                    if attempts > self.num_variants * 2:
                        prompt_context += " Be creative and use very different wording."

                    result = self.paraphraser(
                        original_question=question,
                        context=prompt_context,
                    )

                    # Extract paraphrase (handle ChainOfThought output if used)
                    if hasattr(result, "rewritten_question"):
                        paraphrase = result.rewritten_question.strip()
                    else:
                        # Fallback for different output formats
                        paraphrase = str(result).strip()

                    # Validate uniqueness and quality
                    normalized = paraphrase.lower()
                    if normalized not in seen_paraphrases:
                        # Validate semantic equivalence if enabled to ensure the paraphrased question asks for the same information
                        if self.validate_semantics:
                            is_valid = self._validate_semantic_equivalence(
                                question,
                                paraphrase,
                            )
                            if not is_valid:
                                self._metrics["semantic_failures"] += 1
                                continue

                        # Basic quality validation to ensure the paraphrased question is valid
                        if self._validate_paraphrase_quality(question, paraphrase):
                            variants.append(paraphrase)
                            seen_paraphrases.add(normalized)  # Track normalized versions to avoid duplicates
                            self._metrics["total_paraphrases"] += 1
                        else:
                            self._metrics["failed_validations"] += 1

                except Exception as e:
                    # Log error but continue to avoid blocking the main process
                    logger.debug(f"Paraphrase generation error: {e}")
                    continue

        # Fallback: if we couldn't generate enough variants to meet the required number of variants
        if len(variants) < self.num_variants:
            # Add slight variations of the original question to ensure we have enough variants
            fallback_variants = self._generate_fallback_variants(
                question,
                self.num_variants - len(variants),
            )
            variants.extend(fallback_variants)

        # Ensure we have exactly num_variants
        variants = variants[: self.num_variants]

        # Cache results to avoid regenerating the same paraphrases
        if self.cache_enabled:
            cache_key = self._get_cache_key(question, context)
            self._cache[cache_key] = variants

        return variants

    def _get_temperature_schedule(self) -> List[float]:
        """Get temperature schedule based on strategy to control diversity across variants."""
        min_temp, max_temp = self.temperature_range

        # Different temperature schedules for different strategies
        schedules = {
            "diverse": [min_temp, (min_temp + max_temp) / 2, max_temp],
            "conservative": [min_temp, min_temp + 0.1, min_temp + 0.2],
            "balanced": [
                (min_temp + max_temp) / 2 - 0.1,
                (min_temp + max_temp) / 2,
                (min_temp + max_temp) / 2 + 0.1,
            ],
            "adaptive": [min_temp, min_temp + 0.2, max_temp - 0.2, max_temp],
        }

        return schedules.get(self.strategy, schedules["balanced"])

    def _get_strategy_context(self) -> str:
        """Get context prompt based on strategy to guide the paraphrasing process."""
        contexts = {
            "diverse": ("Provide a significantly different phrasing that asks for " "exactly the same information using completely different words"),  # Generate significantly different paraphrases
            "conservative": ("Slightly rephrase this question with minimal structural changes " "but different word choices"),  # Slightly rephrase with minimal changes
            "balanced": (  # Naturally rephrase as someone else might ask it
                "Naturally rephrase this question as someone else might ask it, " "maintaining the same meaning with moderately different phrasing"
            ),
            "adaptive": (  # Intelligently rephrase based on the question type to maintain semantic equivalence
                "Intelligently rephrase based on the question type, using " "appropriate terminology and structure variations"
            ),
        }
        return contexts.get(self.strategy, contexts["balanced"])

    def _validate_semantic_equivalence(
        self,
        original: str,
        paraphrase: str,
    ) -> bool:
        """Validate semantic equivalence using DSPy validator to ensure the paraphrased question asks for the same information.

        Args:
            original: Original question
            paraphrase: Generated paraphrase

        Returns:
            True if semantically equivalent above threshold
        """
        if not self.validate_semantics or not hasattr(self, "validator"):  # If semantic validation is disabled or the validator is not available, return True
            return True

        try:  # Try to validate the semantic equivalence
            result = self.validator(original=original, paraphrase=paraphrase)

            # Check both boolean and confidence to ensure the paraphrased question asks for the same information
            if hasattr(result, "equivalent") and hasattr(result, "confidence"):
                return result.equivalent and result.confidence >= self.semantic_threshold
            # Fallback to basic validation
            logger.warning(f"validator returned unexpected format: {result}")
            return False
        # If validation fails, assume it's not valid
        except Exception as e:
            logger.warning(f"Semantic validation error: {e}. Assuming paraphrase is not valid.")
            return False

    def _validate_paraphrase_quality(
        self,
        original: str,
        paraphrase: str,
    ) -> bool:
        """Validate paraphrase quality with comprehensive checks.

        Args:
            original: Original question
            paraphrase: Generated paraphrase

        Returns:
            True if paraphrase meets quality criteria
        """
        # Basic validation
        if not paraphrase or len(paraphrase) < 5:
            return False

        # Check it's actually different
        if paraphrase.lower().strip() == original.lower().strip():  # If the paraphrased question is the same as the original question, return False
            return False

        # Check minimum length ratio (avoid over-compression or expansion)
        length_ratio = len(paraphrase) / len(original)
        if length_ratio < 0.4 or length_ratio > 2.5:
            return False

        # Check word overlap (should have some different words)
        original_words = set(original.lower().split())
        paraphrase_words = set(paraphrase.lower().split())

        # Calculate Jaccard similarity
        intersection = original_words & paraphrase_words
        union = original_words | paraphrase_words

        if len(union) > 0:
            similarity = len(intersection) / len(union)
            # Want some overlap but not too much
            if similarity > 0.95 or similarity < 0.2:
                return False

        return True

    def _generate_fallback_variants(
        self,
        question: str,
        count: int,
    ) -> List[str]:
        """Generate simple fallback variants when DSPy fails.

        Args:
            question: Original question
            count: Number of variants needed

        Returns:
            List of simple variants
        """
        variants = []

        # Simple transformations
        templates = [
            "Can you explain {}?",
            "Please tell me about {}",
            "I'd like to know: {}",
            "Could you describe {}?",
            "What about {}?",
        ]

        # Remove question marks and common prefixes
        core = question.rstrip("?").strip()
        for prefix in ["What is", "How do", "Can you", "Please", "Could you"]:
            if core.lower().startswith(prefix.lower()):
                core = core[len(prefix) :].strip()
                break

        for i in range(min(count, len(templates))):
            variant = templates[i].format(core)
            variants.append(variant)

        # If still need more, just use original
        while len(variants) < count:
            variants.append(question)

        return variants

    def _get_cache_key(self, question: str, context: Optional[str]) -> str:
        """Generate cache key from question and configuration.

        Args:
            question: Question to cache

        Returns:
            MD5 hash key
        """
        resolved_context = context or self._get_strategy_context()

        key_payload = {
            "question": question,
            "context": resolved_context,
            "strategy": self.strategy,
            "num_variants": self.num_variants,
            "temperature_range": self.temperature_range,
            "use_chain_of_thought": self.use_chain_of_thought,
            "validate_semantics": self.validate_semantics,
            "semantic_threshold": self.semantic_threshold,
        }

        serialized = json.dumps(key_payload, sort_keys=True)
        return hashlib.md5(serialized.encode()).hexdigest()

    def get_metrics(self) -> Dict[str, Any]:
        """Get paraphraser metrics for monitoring and optimization.

        Returns:
            Dictionary of metrics
        """
        return self._metrics.copy()

    def clear_cache(self) -> None:
        """Clear the paraphrase cache."""
        self._cache.clear()
        self._metrics["cache_hits"] = 0
        self._metrics["cache_misses"] = 0


def create_dspy_lm_from_backend_config(
    backend_config: Dict[str, Any],
) -> Optional["dspy.LM"]:
    # If DSPy is not available, return None
    if dspy is None:
        return None

    # Get the backend type, model, api key, and base url from the backend config
    backend_type = backend_config.get("type", "").lower()
    model = backend_config.get("model")
    api_key = backend_config.get("api_key")
    base_url = backend_config.get("base_url")
    # Map MassGen backend types to DSPy provider strings
    provider_map = {
        "openai": "openai",
        "claude": "anthropic",
        "anthropic": "anthropic",  # Alias for claude
        "gemini": "gemini",
        "chatcompletion": "openai",  # chatcompletion is OpenAI-compatible
        "lmstudio": "openai",  # LMStudio is OpenAI-compatible
        "vllm": "openai",  # vLLM is OpenAI-compatible
        "sglang": "openai",  # SGLang is OpenAI-compatible
        "cerebras": "openai",  # Cerebras is OpenAI-compatible
    }

    # Validate backend type (fail-fast on unknown providers)
    if backend_type not in provider_map:
        logger.error(
            f"Unsupported backend type '{backend_type}' for DSPy. " f"Supported: {', '.join(sorted(provider_map.keys()))}",
        )
        return None

    provider = provider_map[backend_type]

    # Validate model is provided
    if not model:
        logger.error(f"Model name required for backend type '{backend_type}'")
        return None

    # Build model string for DSPy
    if backend_type in ["lmstudio", "vllm", "sglang", "chatcompletion", "cerebras"]:
        # Local/custom endpoints use openai prefix
        model_string = f"openai/{model}"
    else:
        # Standard provider/model format (openai, anthropic, gemini)
        model_string = f"{provider}/{model}"

    # Build LM kwargs
    lm_kwargs = {}

    # API key handling (with environment variable fallback)
    if api_key:
        lm_kwargs["api_key"] = api_key
    else:
        # Environment variable fallback
        env_keys = {
            "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "cerebras": "CEREBRAS_API_KEY",
        }

        if backend_type in env_keys:
            keys = env_keys[backend_type]
            if isinstance(keys, list):
                for key in keys:
                    api_key = os.getenv(key)
                    if api_key:
                        lm_kwargs["api_key"] = api_key
                        break
            else:
                api_key = os.getenv(keys)
                if api_key:
                    lm_kwargs["api_key"] = api_key

    # Base URL for custom endpoints (user-provided takes priority)
    if base_url:
        lm_kwargs["api_base"] = base_url
    else:
        # Default localhost URLs for local inference servers
        default_urls = {
            "lmstudio": "http://localhost:1234/v1",
            "vllm": "http://localhost:8000/v1",
            "sglang": "http://localhost:30000/v1",
        }
        if backend_type in default_urls:
            lm_kwargs["api_base"] = default_urls[backend_type]

    # Model parameters
    if "temperature" in backend_config:
        lm_kwargs["temperature"] = backend_config["temperature"]
    if "max_tokens" in backend_config:
        lm_kwargs["max_tokens"] = backend_config["max_tokens"]
    if "top_p" in backend_config:
        lm_kwargs["top_p"] = backend_config["top_p"]

    # Reliability defaults
    lm_kwargs.setdefault("num_retries", 3)  # num_retries is the number of times to retry on transient API errors
    lm_kwargs.setdefault("timeout", 60)  # 60 second timeout per request

    # Create and return LM instance
    try:
        return dspy.LM(model_string, **lm_kwargs)
    except Exception as e:
        logger.warning(f"Failed to create DSPy LM: {e}")
        return None


def is_dspy_available() -> bool:
    """Return True when DSPy is available in the current environment.

    Returns:
        bool: True if DSPy is available, False otherwise
    """
    return dspy is not None
