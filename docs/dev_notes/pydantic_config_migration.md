# Pydantic config migration — plan

## STATUS: Phase A COMPLETE ✅
All 8 config classes migrated to `@pydantic.dataclasses.dataclass` and verified:
StepModeConfig, TimeoutConfig, PromptImproverConfig, CoordinationConfig,
AgentConfig (agent_config.py) + PersonaGeneratorConfig, EvaluationCriteriaGeneratorConfig,
TaskDecomposerConfig (their own files). `pydantic>=2.0` is now a declared dependency
(uv.lock updated). Validation regression tests in
`massgen/tests/test_config_pydantic_validation.py`. Full broad suite holds at the
59 pre-existing failures (zero new); all 282 bundled configs validate.

Notable fix surfaced by validation: `CoordinationConfig.from_dict` used to pass
absent keys as `None`, silently overriding non-None field defaults (e.g.
`write_mode` became `None` instead of `"auto"`). `from_dict` now drops `None`
values so field defaults apply. `subagent_orchestrator` and `message_templates`
are typed `Any` (TYPE_CHECKING-only forward refs pydantic can't resolve) — Phase B.



## Goal
Replace MassGen's untyped `dict[str, Any]` + hand-rolled config dataclasses with
pydantic-validated config models, so config errors are caught at parse time and
the schema is the single source of truth. Root-cause fix behind ~5 audit findings.

## Vehicle: `pydantic.dataclasses.dataclass` (not BaseModel)
This codebase is heavily dataclass-based: `__post_init__`, `from_dict`/`to_dict`,
`fields()` (agent_config.py:63), construction with all-defaults, and in-place
mutation (`orchestrator` sets `config.X = Y`). `pydantic.dataclasses.dataclass`
is a near drop-in that ADDS type validation/coercion on construction while
preserving ALL of those semantics. `BaseModel` would break `fields()`,
`__post_init__`, and require rewriting `from_dict`/`to_dict` — much higher risk.

Mechanics per class:
- `from dataclasses import dataclass` -> `from pydantic.dataclasses import dataclass`
  (keep `field`, `fields` from stdlib dataclasses).
- Keep field defaults / `field(default_factory=...)`, `__post_init__`, methods.
- Landmines to handle: (a) fields annotated with TYPE_CHECKING-only types
  (pydantic needs the real type at runtime — import it, or annotate `Any`, or set
  `arbitrary_types_allowed`); (b) lax coercion changing values — watch tests.

## Order (leaf-first, test after each)
1. `StepModeConfig`, `TimeoutConfig`, `PromptImproverConfig` (agent_config.py) — small, scalar.
2. Cross-file nested configs: `PersonaGeneratorConfig` (persona_generator.py),
   `EvaluationCriteriaGeneratorConfig` (evaluation_criteria_generator.py),
   `TaskDecomposerConfig` (task_decomposer.py), `SubagentOrchestratorConfig` (subagent/models.py).
3. `CoordinationConfig` (agent_config.py:93) — has nested model fields + `__post_init__`.
4. `AgentConfig` (agent_config.py:742) — top-level, complex `from_dict`/`to_dict`.

## Test gate
After each class: `import massgen`, the class's own tests, and the focused config
test set. After all: full broad suite must hold at the 59 pre-existing failures.

## Phase B (follow-up, NOT this migration)
- Unknown-key detection (warn/forbid) by validating the whole YAML dict.
- Enum/Literal for modes (coordination_mode, write_mode, display_type).
- Consolidate the 2.1k-line `config_validator.py` into model validation.
- Declare `pydantic` as a direct dependency + `uv lock`.

## What's Next
After config models are pydantic-validated and green, Phase B (above) tightens
validation and removes the duplicate validator.
