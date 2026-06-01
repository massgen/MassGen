"""Skills configuration validation, extracted from Orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


def _builtin_skills_dir() -> Path:
    """Resolve the bundled skills directory against a STABLE anchor.

    IMPORTANT: This must NOT anchor to this collaborator module's ``__file__``
    (that would point at ``massgen/orchestrator_collaborators/skills``, which
    does not exist). Instead anchor to the ``massgen.orchestrator`` module's
    ``__file__``, which lives directly under ``massgen/`` -> ``<repo>/massgen``,
    so the built-in skills resolve to ``<repo>/massgen/skills`` exactly as the
    original ``Path(__file__).parent / "skills"`` did. Importing the orchestrator
    module here (rather than caching its path) also preserves the ability to
    patch ``massgen.orchestrator.__file__`` for tests.
    """
    import massgen.orchestrator as orchestrator_module

    return Path(orchestrator_module.__file__).parent / "skills"


class SkillsConfigValidator:
    """Validate that skills (external or built-in) are available for a run.

    Stateless aside from a back-reference to the orchestrator, used only to
    read ``config.coordination_config.skills_directory``.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def validate(self) -> None:
        """
        Validate skills configuration.

        Checks that skills directory exists and is not empty. Agents access skills
        directly from the filesystem via workspace tools MCP (no dedicated skills
        MCP server needed).

        Raises:
            RuntimeError: If no skills are found
        """
        orchestrator = self._orchestrator

        # Check if skills are available (external or built-in)
        skills_dir = Path(orchestrator.config.coordination_config.skills_directory)
        logger.info(
            f"[Orchestrator] Checking skills configuration - directory: {skills_dir}",
        )

        # Check for external skills (from openskills)
        has_external_skills = skills_dir.exists() and skills_dir.is_dir() and any(skills_dir.iterdir())

        # Check for built-in skills (bundled with MassGen). Resolve against the
        # massgen package root so this works regardless of where this module lives.
        builtin_skills_dir = _builtin_skills_dir()
        has_builtin_skills = builtin_skills_dir.exists() and any(
            builtin_skills_dir.iterdir(),
        )

        # At least one type of skills must be available
        if not has_external_skills and not has_builtin_skills:
            raise RuntimeError(
                f"No skills found. To use skills:\n"
                f"Install external skills: 'npm i -g openskills && openskills install anthropics/skills --universal -y'\n"
                f"This creates '{skills_dir}' with skills like pdf, xlsx, pptx, etc.\n\n"
                f"Built-in skills (file-search, serena, semtools) should be bundled with MassGen in {builtin_skills_dir}",
            )

        logger.info(
            f"[Orchestrator] Skills available (external: {has_external_skills}, builtin: {has_builtin_skills})",
        )
