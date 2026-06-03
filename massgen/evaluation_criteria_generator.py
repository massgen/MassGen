"""GEPA-inspired evaluation criteria generation for MassGen.

This module generates task-specific evaluation criteria via a pre-collaboration
consensus run, replacing fixed T1-T4 items with dynamic E1-EN criteria tailored
to the actual task. When generation is disabled or fails, concrete static defaults
are used instead.

Criteria use category "primary" (at most one, the most impactful criterion),
"standard" (must-pass), or "stretch" (nice-to-have).
For backward compatibility: "must"/"core" → "standard", "should" → "standard",
"could"/"stretch" → "stretch".
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic.dataclasses import dataclass as pydantic_dataclass


@pydantic_dataclass
class EvaluationCriteriaGeneratorConfig:
    """Configuration for evaluation criteria generation.

    Attributes:
        enabled: Whether criteria generation is enabled
        persist_across_turns: If True, reuse criteria across interactive turns
        min_criteria: Minimum number of criteria to generate
        max_criteria: Maximum number of criteria to generate
    """

    enabled: bool = False
    persist_across_turns: bool = False
    min_criteria: int = 4
    max_criteria: int = 7


@dataclass
class GeneratedCriterion:
    """A single evaluation criterion.

    Attributes:
        id: Criterion identifier (e.g., "E1", "E2")
        text: The criterion description text — should be an opinionated quality
            definition that takes a position on what "good" means, not just a
            dimension label. See the Anthropic harness design article for context:
            https://www.anthropic.com/engineering/harness-design-long-running-apps
        category: "primary" (THE criterion where default model behavior is weakest
            — at most one per set), "standard" (must-pass), or "stretch" (nice-to-have).
            Legacy values "must"/"core" map to "standard", "should" maps to "standard",
            "could"/"stretch" maps to "stretch".
        verify_by: Optional free-form instruction for how to gather evidence for this
            criterion. Set when reading the output text is insufficient — e.g.
            "render each slide to PNG and view visually with read_media",
            "record a video of the full animation and review the motion",
            "listen to the audio output from start to finish",
            "open in browser and test: click all links, submit forms, check states".
            None when textual inspection of the output is sufficient.
        anti_patterns: Specific failure modes that should tank the score for this
            criterion. Concrete, not abstract — e.g. "heart/fire/ocean metaphors"
            not "avoid cliches". None when not applicable.
        score_anchors: Concrete descriptions of what specific score levels look like
            for THIS criterion on THIS task. Keys are score strings ("3", "5", "7", "9")
            mapping to brief behavioral descriptions. These calibrate evaluators by
            grounding abstract scores in observable output characteristics.
            None when not provided.
    """

    id: str
    text: str
    category: str  # "primary", "standard", or "stretch"
    verify_by: str | None = None
    anti_patterns: list[str] | None = None
    score_anchors: dict[str, str] | None = None


# Static defaults inspired by GEPA's diagnostic structure.
# These replace the legacy abstract T1-T4 items with concrete defaults
# that work for any task type.  Designed following the same principles the
# criteria generator prompt teaches:
#   - Opinionated quality definitions, not dimension labels
#   - One PRIMARY criterion (where default model behavior is weakest)
#   - Distinct, non-overlapping dimensions
#   - Per-part quality assessment (weakest part, not average)
_DEFAULT_CRITERIA: list[GeneratedCriterion] = [
    GeneratedCriterion(
        id="E1",
        text=(
            "Requirements fidelity: The output achieves what was specifically asked"
            " for — each stated requirement is met as described, not approximated or"
            " reinterpreted. Missing requirements, partially implemented features, or"
            " creative substitutions for what was actually requested count as failures."
        ),
        category="standard",
        anti_patterns=[
            "implementing 3 of 5 requested features and hoping nobody notices",
            "reinterpreting explicit requirements into something easier to build",
            "partially implementing a feature and declaring it done",
            "silently omitting requirements that are difficult or ambiguous",
        ],
        score_anchors={
            "3": "Multiple stated requirements missing or replaced with easier substitutes",
            "5": "All requirements addressed but several are approximations of what was asked",
            "7": "Every requirement met as stated, with minor interpretation differences on edge cases",
            "9": "Every requirement met precisely, including implicit constraints the user would expect",
        },
    ),
    GeneratedCriterion(
        id="E2",
        text=(
            "Multi-level correctness: The output works correctly as experienced, not"
            " just as inspected. Structural correctness (valid format, runnable code,"
            " proper syntax), content correctness (accurate information, right"
            " computations), and experiential correctness (renders properly,"
            " interactions work, no visual defects) are all required. A file that"
            " opens but displays incorrectly is wrong, not merely unpolished."
        ),
        category="standard",
        anti_patterns=[
            "code that passes lint but crashes on first real input",
            "HTML that validates but renders as a broken layout",
            "computations that look plausible but use wrong formulas or units",
            "content that reads well but contains factual errors",
        ],
        score_anchors={
            "3": "Fails structural checks — won't open, won't run, syntax errors",
            "5": "Structurally valid but content errors or experiential defects on inspection",
            "7": "Correct on all three levels with minor edge case issues",
            "9": "Works correctly as a user would actually experience it in all realistic scenarios",
        },
    ),
    GeneratedCriterion(
        id="E3",
        text=(
            "Per-part depth: Every significant component of the output independently"
            " meets a quality bar — no section is filler, placeholder, or carried by"
            " the strength of others. Evaluate the weakest part, not the average. A"
            " brilliant introduction with thin body sections, or a strong"
            " implementation with stub tests, fails this criterion."
        ),
        category="primary",
        anti_patterns=[
            "detailed first section followed by sections clearly running out of steam",
            "placeholder or TODO comments in supposedly complete work",
            "test files that only cover the happy path with stub error handling",
            "strong core logic with copy-pasted or boilerplate supporting code",
        ],
        score_anchors={
            "3": "Multiple sections are clearly filler or placeholder — quality varies wildly",
            "5": "Most sections adequate but 1-2 are noticeably thinner or more superficial",
            "7": "All sections meet a quality bar but the weakest is still visibly below the strongest",
            "9": "Every section could stand alone as quality work — no weak links in the chain",
        },
    ),
    GeneratedCriterion(
        id="E4",
        text=(
            "Intentional craft: The output reads as authored, not generated —"
            " structural choices, style decisions, and domain-specific details"
            " reflect judgment that went beyond the first adequate option. Every"
            " significant decision (organization, naming, emphasis, formatting)"
            " should feel deliberate rather than default. A domain expert would"
            " recognize thoughtful choices, not template-filling."
        ),
        category="standard",
        anti_patterns=[
            "every structural choice is the obvious first option — alphabetical ordering," " linear flow, default formatting",
            "no evidence alternatives were considered — the output reads like the first" " thing that came to mind",
            "style is functionally invisible — correct but characterless, like boilerplate",
            "domain-specific opportunities ignored in favor of generic treatment",
        ],
        score_anchors={
            "3": "Reads like auto-generated output — could have been produced by filling a template",
            "5": "Correct and competent but every choice is the default or obvious one",
            "7": "Several intentional choices visible but some sections revert to default mode",
            "9": "A domain expert would recognize authorial voice and deliberate decisions throughout",
        },
    ),
]

# Changedoc variant: same quality dimensions but anchored to a spec/changedoc
# rather than raw user requirements.
_CHANGEDOC_CRITERIA: list[GeneratedCriterion] = [
    GeneratedCriterion(
        id="E1",
        text=(
            "Spec fidelity: The output implements what the changedoc specifies —"
            " each goal and requirement is addressed as described, not approximated"
            " or reinterpreted. Missing goals, partially implemented requirements,"
            " or creative substitutions for what was specified count as failures."
        ),
        category="standard",
        anti_patterns=[
            "implementing goals partially and declaring them done",
            "drifting from the spec into preferred but unspecified approaches",
            "addressing the spirit of a requirement while missing its explicit constraints",
            "silently omitting goals that are difficult or ambiguous",
        ],
        score_anchors={
            "3": "Multiple spec goals missing or replaced with unspecified alternatives",
            "5": "All goals addressed but several are loose interpretations of the spec",
            "7": "Every goal met as specified, with minor interpretation differences on edge cases",
            "9": "Every goal and constraint met precisely — the spec could be used as a test plan",
        },
    ),
    GeneratedCriterion(
        id="E2",
        text=(
            "Multi-level correctness: The output works correctly as experienced, not"
            " just as inspected. Structural correctness (valid format, runnable code,"
            " proper syntax), content correctness (accurate information, right"
            " computations), and experiential correctness (renders properly,"
            " interactions work, no visual defects) are all required. A deliverable"
            " that passes structural checks but fails experientially is wrong, not"
            " merely unpolished."
        ),
        category="standard",
        anti_patterns=[
            "code that passes lint but crashes on first real input",
            "HTML that validates but renders as a broken layout",
            "computations that look plausible but use wrong formulas or units",
            "deliverable that passes structural checks but fails experientially",
        ],
        score_anchors={
            "3": "Fails structural checks — won't open, won't run, syntax errors",
            "5": "Structurally valid but content errors or experiential defects on inspection",
            "7": "Correct on all three levels with minor edge case issues",
            "9": "Works correctly as a user would actually experience it in all realistic scenarios",
        },
    ),
    GeneratedCriterion(
        id="E3",
        text=(
            "Per-part depth: Every significant component independently meets a"
            " quality bar — no section is filler, placeholder, or carried by the"
            " strength of others. Evaluate the weakest part, not the average. A"
            " brilliant first section with thin remaining sections, or strong core"
            " logic with stub supporting pieces, fails this criterion."
        ),
        category="primary",
        anti_patterns=[
            "detailed first section followed by sections clearly running out of steam",
            "placeholder or TODO comments in supposedly complete work",
            "strong core logic with copy-pasted or boilerplate supporting code",
            "one polished component carrying several half-finished ones",
        ],
        score_anchors={
            "3": "Multiple sections are clearly filler or placeholder — quality varies wildly",
            "5": "Most sections adequate but 1-2 are noticeably thinner or more superficial",
            "7": "All sections meet a quality bar but the weakest is still visibly below the strongest",
            "9": "Every section could stand alone as quality work — no weak links in the chain",
        },
    ),
    GeneratedCriterion(
        id="E4",
        text=(
            "Intentional craft: The output reads as authored, not generated —"
            " structural choices, style decisions, and domain-specific details"
            " reflect judgment that went beyond the first adequate option."
            " Structure, style, and detail reflect care about the result. A"
            " knowledgeable person in the domain would recognize thoughtful"
            " choices, not template-filling."
        ),
        category="standard",
        anti_patterns=[
            "every structural choice is the obvious first option — alphabetical ordering," " linear flow, default formatting",
            "no evidence alternatives were considered — the output reads like the first" " thing that came to mind",
            "style is functionally invisible — correct but characterless, like boilerplate",
            "domain-specific opportunities ignored in favor of generic treatment",
        ],
        score_anchors={
            "3": "Reads like auto-generated output — could have been produced by filling a template",
            "5": "Correct and competent but every choice is the default or obvious one",
            "7": "Several intentional choices visible but some sections revert to default mode",
            "9": "A domain expert would recognize authorial voice and deliberate decisions throughout",
        },
    ),
]

# ---------------------------------------------------------------------------
# Domain-specific criteria presets
# ---------------------------------------------------------------------------
# Each preset maps to a list of (text, category) tuples.  The criteria are
# sourced from docs/modules/composition.md and cover the well-defined quality
# characteristics of each special primitive.

_CRITERIA_PRESETS: dict[str, list[GeneratedCriterion]] = {
    # ── persona ──────────────────────────────────────────────────────────
    "persona": [
        GeneratedCriterion(
            id="E1",
            text=(
                "Each persona articulates a clear, specific perspective that would lead to"
                " meaningfully different outputs — not just surface variation in tone or"
                " vocabulary. Two personas that would produce essentially the same answer"
                " are a failure."
            ),
            category="standard",
            anti_patterns=[
                "personas that differ only in vocabulary or tone but share the same values and priorities",
                "one persona is just a more cautious or verbose version of another",
                "perspectives that are theoretically different but converge on the same recommendations",
            ],
            score_anchors={
                "3": "Most personas would produce near-identical outputs — differences are cosmetic",
                "5": "Personas differ in emphasis but fundamentally agree on approach and priorities",
                "7": "Personas would produce meaningfully different outputs but share some blind spots",
                "9": "Each persona would produce a genuinely different answer with different strengths and trade-offs",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Personas are grounded in the task's actual decision space — each perspective"
                " maps to a real trade-off, methodology, or value judgment the task demands."
                " A persona whose lens does not change any concrete decision in the output is"
                " decorative, not functional."
            ),
            category="standard",
            anti_patterns=[
                "a 'philosopher persona' on a code task that just adds philosophical quotes",
                "personas defined by identity markers rather than expertise or methodology",
                "'devil's advocate' persona with no domain-specific lens on what to advocate against",
                "perspectives that sound distinct but do not map to any actual decision in the task",
            ],
            score_anchors={
                "3": "Personas feel randomly assigned with no connection to the task's decision space",
                "5": "Personas are topically related but their lens doesn't change any concrete output decision",
                "7": "Most personas bring genuine domain insight but one feels shoehorned in",
                "9": "Every persona's perspective is clearly earned by the task's actual trade-offs and decisions",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Personas are actionable instructions, not character descriptions. An agent"
                " receiving this persona knows exactly how it changes their approach,"
                " priorities, and decision-making — which trade-offs to favor, which"
                " approaches to prefer, what to optimize for."
            ),
            category="standard",
            anti_patterns=[
                "personas that read like character bios (age, background, personality) with no operational guidance",
                "'you are a senior architect' with no indication of which architectural values to prioritize",
                "personas that describe attitude ('meticulous', 'creative') without saying what to do differently",
            ],
            score_anchors={
                "3": "Personas are character descriptions — an agent would not know how to change their output",
                "5": "Personas imply a perspective but the agent must infer how it changes decisions",
                "7": "Actionable but some directives are vague enough to be interpreted multiple ways",
                "9": "Agent could read the persona and immediately know which trade-offs to make differently",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "The persona set collectively covers the task's decision space — the major"
                " reasonable approaches, value trade-offs, or methodological choices are"
                " represented. An expert reviewing the set would not say 'you're missing"
                " the obvious perspective that would...'"
            ),
            category="standard",
            anti_patterns=[
                "all personas cluster around the same approach from slightly different angles",
                "missing the obvious contrarian perspective (the 'keep it simple' voice when everyone builds complexity)",
                "no persona that represents the end-user or consumer perspective when the task has one",
                "all perspectives favor the same side of a genuine trade-off",
            ],
            score_anchors={
                "3": "Personas cluster in one quadrant of the decision space — major approaches unrepresented",
                "5": "Reasonable spread but a major perspective is obviously absent",
                "7": "Good coverage with one important trade-off dimension unrepresented",
                "9": "An expert would say 'yes, these are the perspectives I'd want in the room'",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "Personas are vivid enough to resist homogenization under peer pressure."
                " The perspective is strongly stated so that even after seeing other agents'"
                " answers, the core viewpoint remains distinguishable. Weak personas wash"
                " out after one round of collaboration."
            ),
            category="primary",
            anti_patterns=[
                "personas whose core viewpoint is easily abandoned when they see strong counterarguments",
                "perspectives stated as mild preferences rather than convictions",
                "wishy-washy hedging language ('might consider', 'could potentially') instead of strong positions",
            ],
            score_anchors={
                "3": "Personas would converge to the same answer after one round of seeing peer work",
                "5": "Initial outputs differ but perspectives blur after seeing other agents' answers",
                "7": "Core viewpoints survive collaboration but edges soften toward consensus",
                "9": "Each perspective remains clearly distinguishable even after multiple rounds of revision",
            },
        ),
    ],
    # ── decomposition ────────────────────────────────────────────────────
    "decomposition": [
        GeneratedCriterion(
            id="E1",
            text=(
                "Subtasks are collectively exhaustive — completing all of them fully"
                " produces the complete output with nothing falling through the cracks."
                " The seams between subtasks are where work gets lost: integration steps,"
                " cross-cutting concerns (error handling, styling, testing), and the 'glue'"
                " that connects independently-built parts must be explicitly assigned."
            ),
            category="primary",
            anti_patterns=[
                "missing integration or assembly step — all parts built but nobody responsible for combining them",
                "cross-cutting concerns (error handling, logging, styling, testing) not assigned to any subtask",
                "the 'glue code' between subtasks is nobody's job",
                "each subtask produces output in isolation but nobody verifies they connect",
            ],
            score_anchors={
                "3": "Completing all subtasks would produce at most 60% of the required output — major gaps between seams",
                "5": "Most of the task covered but significant integration or polish work falls between cracks",
                "7": "Nearly complete coverage but one cross-cutting concern is orphaned",
                "9": "Clear mapping from every aspect of the original task to exactly one subtask, including integration",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Subtasks are loosely coupled — each can be executed independently without"
                " blocking on intermediate results from other subtasks. Where dependencies"
                " exist, they are explicit with specified interfaces, not discovered at"
                " execution time when an agent realizes they need something from a peer."
            ),
            category="standard",
            anti_patterns=[
                "subtask B cannot start until subtask A produces an unspecified intermediate artifact",
                "agents discover at execution time that they need information from a peer's work",
                "serial chain of dependencies that could have been parallelized with better scoping",
                "implicit shared state that subtask descriptions don't acknowledge",
            ],
            score_anchors={
                "3": "Most subtasks require intermediate results from others with no specification of what",
                "5": "Dependencies exist and are stated but are unnecessarily tight — could be parallelized",
                "7": "Dependencies are minimal and explicit, with most subtasks independently executable",
                "9": "Each subtask can be given to an agent with no knowledge of other subtasks and produce useful output",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Subtask scoping is balanced — no subtask is trivially small while another"
                " carries the bulk of the real complexity. Imbalanced decomposition wastes"
                " agents on trivial work while bottlenecking on the one subtask that"
                " contains everything hard."
            ),
            category="standard",
            anti_patterns=[
                "one subtask is 'write the entire backend' while another is 'choose a color palette'",
                "the 'hard part' is concentrated in one subtask while others are mechanical",
                "a subtask that would take minutes alongside one that would take hours",
            ],
            score_anchors={
                "3": "Wildly uneven — one subtask contains 70%+ of the real work",
                "5": "Some imbalance but no subtask is trivially small or overwhelmingly large",
                "7": "Reasonably balanced with minor size differences",
                "9": "Each subtask represents a comparable quantum of meaningful work",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "Each subtask description is self-contained — an agent can read it and know"
                " exactly what to produce, what quality means for this piece, and where the"
                " boundaries are, without reading other subtask descriptions or the original"
                " prompt. Ambiguous terms are defined, not assumed."
            ),
            category="standard",
            anti_patterns=[
                "subtask says 'complete the remaining sections' without listing them",
                "references context from the original prompt that isn't included in the description",
                "uses ambiguous terms ('make it look good') that require reading other subtasks for calibration",
                "'see above' or 'as described in the main task' as a substitute for specification",
            ],
            score_anchors={
                "3": "Subtasks are one-line labels requiring the original prompt to understand",
                "5": "Subtasks are described but key decisions or quality criteria are left implicit",
                "7": "Mostly self-contained but a couple reference 'the approach described above'",
                "9": "Each description could be given to a new agent with zero context and they'd know what to produce",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "The decomposition strategy exploits the task's natural structure — creative"
                " tasks split along conceptual or thematic boundaries, technical tasks along"
                " component or service boundaries, analytical tasks along dimension boundaries."
                " The decomposition reveals insight about the task, not just a mechanical split."
            ),
            category="standard",
            anti_patterns=[
                "splitting a creative task by arbitrary page or section numbers rather than themes",
                "splitting a technical task by workflow phases (plan, implement, test) rather than components",
                "using the same decomposition strategy regardless of task type",
                "mechanical division (first half / second half) that ignores natural seams",
            ],
            score_anchors={
                "3": "Decomposition strategy is mismatched to task type — e.g., splitting creative work into mechanical phases",
                "5": "Strategy is reasonable but generic — could apply to any task, not informed by this one's structure",
                "7": "Strategy matches task type with good reasoning about where to split",
                "9": "Strategy exploits the specific structure of THIS task in a way a domain expert would recognize as insightful",
            },
        ),
    ],
    # ── evaluation ───────────────────────────────────────────────────────
    "evaluation": [
        GeneratedCriterion(
            id="E1",
            text=("Each criterion is specific to the actual task — not generic advice that" " applies to any output. A criterion that could be copy-pasted to an" " unrelated task is too vague."),
            category="standard",
            anti_patterns=[
                "criteria like 'well-written', 'correct', or 'complete' that apply to any output",
                "every criterion could be used for either a poem or a database schema unchanged",
                "no reference to the specific domain, output type, or failure modes of the actual task",
            ],
            score_anchors={
                "3": "All criteria are generic — 'clear', 'correct', 'complete' — applicable to anything",
                "5": "Criteria reference the task domain but could apply to any task within that domain",
                "7": "Most criteria are task-specific but one or two are generic quality checks",
                "9": "Every criterion clearly arises from THIS task's specific requirements and failure modes",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Criteria are evaluable — an agent can determine pass/fail by examining the"
                ' output, not by making subjective judgments about intent. "Addresses edge'
                ' cases" is vague; "handles empty input, null values, and boundary'
                ' conditions" is evaluable.'
            ),
            category="standard",
            anti_patterns=[
                "criteria requiring judgment about 'quality' without defining what quality means",
                "pass/fail depends on the evaluator's personal taste rather than observable properties",
                "criterion text that two evaluators would interpret differently",
            ],
            score_anchors={
                "3": "Criteria are subjective opinions — different evaluators would reach different conclusions",
                "5": "Criteria have a testable core but significant ambiguity in edge cases",
                "7": "Most criteria can be evaluated objectively with occasional judgment calls",
                "9": "Every criterion has a clear pass/fail test based on observable output properties",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Criteria push on dimensions where the model is weakest by default, not"
                " where it is already competent. Models already produce structurally correct,"
                " functional output by default — criteria that only check for correctness or"
                " completeness will pass on the first draft and add no iterative value."
                " At least one criterion must target a dimension where default model output"
                " is predictably mediocre: originality, distinctive voice, visual identity,"
                " architectural elegance, or domain-specific depth. The PRIMARY criterion"
                " should be the one the model needs to hear most."
            ),
            category="primary",
            anti_patterns=[
                "all criteria check for completeness and correctness — the first draft would pass them all",
                "no criterion that the model would struggle with on the first attempt",
                "criteria set that adds no iterative value because the baseline already passes",
                "avoiding the hard quality dimensions (originality, voice, craft) in favor of easy structural checks",
            ],
            score_anchors={
                "3": "Every criterion is a structural or correctness check — the first draft passes all of them",
                "5": "One criterion is aspirational but the rest are easily satisfied by default model output",
                "7": "Criteria push on genuine quality dimensions but miss the single most important one for this task",
                "9": "The PRIMARY criterion names exactly the dimension where default model behavior is weakest for this task",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "Each criterion takes a position and names anti-patterns — it defines what"
                " good looks like AND what bad looks like for this specific task. A criterion"
                ' that says "uses vivid imagery" is a dimension label; one that says "uses'
                ' imagery that surprises — stock metaphors score poorly" is a quality'
                " definition. Every criterion should include concrete anti-patterns that"
                " identify how this task type typically goes wrong."
            ),
            category="standard",
            anti_patterns=[
                "criteria that name dimensions without defining quality ('has good structure')",
                "no mention of specific failure modes for the task type",
                "criteria that score presence/absence rather than quality level",
            ],
            score_anchors={
                "3": "Criteria are dimension labels only — 'uses imagery', 'has structure', 'is clear'",
                "5": "Criteria define what good looks like but don't name specific failure modes",
                "7": "Most criteria take positions and name anti-patterns, but one or two are still vague labels",
                "9": "Every criterion is an opinionated quality definition with concrete anti-patterns",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "Criteria do not conflict with each other or create impossible trade-offs."
                " Meeting one criterion should not require violating another. Where genuine"
                " tensions exist, the criteria acknowledge the trade-off explicitly and"
                " indicate which side to favor."
            ),
            category="standard",
            anti_patterns=[
                "one criterion demands brevity while another demands comprehensive coverage without acknowledging the tension",
                "criteria that individually make sense but jointly are impossible to satisfy",
                "'be creative' alongside 'follow the template exactly' with no priority guidance",
            ],
            score_anchors={
                "3": "Multiple criteria directly conflict — satisfying one requires violating another",
                "5": "No direct conflicts but implicit tensions that would confuse an evaluator",
                "7": "Criteria are compatible with genuine tensions explicitly acknowledged",
                "9": "Criteria are non-overlapping and mutually reinforcing — the set feels designed as a whole",
            },
        ),
    ],
    # ── prompt ───────────────────────────────────────────────────────────
    "prompt": [
        GeneratedCriterion(
            id="E1",
            text=(
                "The prompt achieves its functional goal — an agent receiving this prompt"
                " cold, with no prior context, would produce the intended type of output"
                " without needing to ask clarifying questions. The prompt contains enough"
                " context that a capable model can start working immediately."
            ),
            category="standard",
            anti_patterns=[
                "prompt assumes context the model doesn't have ('finish the implementation')",
                "prompt describes what the output should be about but not what it should look like",
                "an agent would need to ask 3+ clarifying questions before starting",
            ],
            score_anchors={
                "3": "Agent would produce the wrong type of output entirely — goal is unclear or missing",
                "5": "Agent would produce roughly the right type but miss key requirements or constraints",
                "7": "Agent would produce good output but might misinterpret one or two important details",
                "9": "Hand this to a capable model cold and get back exactly what you need",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "The prompt scopes the output precisely — it constrains enough to prevent"
                " unhelpful variations while leaving room for quality approaches. Scope"
                " failures go both ways: prompts so open that 10 agents produce 10 different"
                " output types, and prompts so rigid that they eliminate the best solutions."
            ),
            category="standard",
            anti_patterns=[
                "prompt so open-ended that 10 agents would produce 10 completely different output types",
                "prompt specifies font size, color, and word count but not the actual goal",
                "constraints that eliminate the best approaches to the problem",
                "no output format or structure guidance for tasks where format matters",
            ],
            score_anchors={
                "3": "Either wildly unconstrained or suffocatingly rigid — output is unpredictable either way",
                "5": "Reasonable scope but either too loose on critical dimensions or too tight on unimportant ones",
                "7": "Well-scoped with minor over- or under-specification on one dimension",
                "9": "Constrains exactly the right things — all outputs would be useful, but approaches can vary",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Critical requirements are explicit and prominent, not implied or buried."
                " The prompt does not depend on shared context, cultural assumptions, or"
                " 'obvious' intentions. Requirements that would make the user say 'I"
                " assumed you'd know that' are exactly the ones that must be stated."
            ),
            category="standard",
            anti_patterns=[
                "assumes the model knows which 'the project' or 'the user' refers to",
                "uses domain jargon without definition when the model may not share that context",
                "critical formatting or output requirements mentioned once in a subordinate clause",
                "implicit constraints that feel 'obvious' to the author but aren't to the model",
            ],
            score_anchors={
                "3": "Multiple critical requirements are implicit — model must guess what the author really wants",
                "5": "Requirements are present but some are ambiguous or buried in context",
                "7": "All important requirements explicit, but one or two assume shared context",
                "9": "Every requirement is stated explicitly and prominently — nothing left to assumption",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "The prompt is structured for parseability — key instructions are prominent,"
                " not buried in paragraphs. An agent skimming the prompt would still catch"
                " the critical constraints. Visual hierarchy (headings, bullets, emphasis)"
                " reflects importance hierarchy."
            ),
            category="standard",
            anti_patterns=[
                "critical constraints buried in paragraph 4 of a 5-paragraph narrative",
                "key requirements mentioned once in a subordinate clause",
                "no visual hierarchy — everything is one unbroken wall of text",
                "important instructions after a long preamble that a model might skip",
            ],
            score_anchors={
                "3": "Wall of text with no structure — critical instructions buried and easy to miss",
                "5": "Some structure but important constraints not visually prominent",
                "7": "Good structure with key instructions prominent, minor hierarchy issues",
                "9": "An agent skimming the prompt would catch every critical constraint",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "The prompt anticipates how the model will predictably fail on this task"
                " type and includes explicit guardrails. Every task type has known failure"
                " modes — analysis prompts that get summarization instead, creative prompts"
                " that get generic safe output, code prompts that get working-but-naive"
                " implementations. A good prompt inoculates against these."
            ),
            category="primary",
            anti_patterns=[
                "no guardrails despite the task type having well-known model failure modes",
                "prompt for analysis that doesn't explicitly forbid summarization",
                "prompt for creative work that doesn't address the tendency toward generic safe outputs",
                "no negative examples or explicit rejections of common failure patterns",
            ],
            score_anchors={
                "3": "No awareness of model failure modes — prompt invites the default mediocre response",
                "5": "One guardrail present but the most predictable failure mode is unaddressed",
                "7": "Major failure modes addressed but one or two common pitfalls not guarded against",
                "9": "Every predictable failure mode for this task type has an explicit guardrail or negative example",
            },
        ),
    ],
    # ── analysis ─────────────────────────────────────────────────────────
    "analysis": [
        GeneratedCriterion(
            id="E1",
            text=(
                "The analysis identifies concrete, specific findings — not vague"
                " observations. Each finding points to a specific location, pattern, or"
                " data point in the source material. 'Performance could be improved' is"
                " not a finding; 'agent 3 exceeded the tool-call budget on 4 of 7 runs"
                " due to retry loops in the search tool' is."
            ),
            category="standard",
            anti_patterns=[
                "findings like 'performance could be improved' without specifying where or how",
                "observations that restate the data in different words rather than interpreting it",
                "'some issues were found' without enumeration or specifics",
            ],
            score_anchors={
                "3": "Findings are vague summaries — 'there were problems' — with no specifics",
                "5": "Findings name areas of concern but lack specific data points or locations",
                "7": "Most findings point to specific evidence, one or two are still vague",
                "9": "Every finding cites a specific location, metric, or data point from the source material",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Findings are supported by evidence from the actual data, not inferred from"
                ' assumptions about what "usually" happens. Claims include references to'
                " specific log entries, metrics, or examples. The analysis distinguishes"
                " what the data shows from what the analyst infers."
            ),
            category="standard",
            anti_patterns=[
                "conclusions drawn from 'best practices' rather than observed data",
                "claims about patterns without citing which data points exhibit them",
                "'likely caused by X' without evidence that X actually occurred",
                "treating correlation as causation without acknowledging the gap",
            ],
            score_anchors={
                "3": "Claims are asserted without evidence — reads like speculation",
                "5": "Some evidence cited but key claims rest on assumptions not data",
                "7": "Most claims well-evidenced with one or two relying on reasonable inference",
                "9": "Every significant claim cites specific evidence and distinguishes observation from inference",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "The analysis distinguishes symptoms from root causes and traces the"
                ' causal chain. "Agent 2 was slow" is a symptom; "agent 2 hit rate limits'
                ' due to tool call volume from retry loops in the search tool" is a root'
                " cause. Surface-level observations without causal investigation waste the"
                " reader's time."
            ),
            category="primary",
            anti_patterns=[
                "findings that only describe observable symptoms without investigating cause",
                "root causes asserted without a causal chain from the evidence",
                "every finding stays at the surface level of 'X happened' without asking why",
                "blaming proximate causes when the real issue is structural",
            ],
            score_anchors={
                "3": "Every finding is a symptom description — no investigation of why things happened",
                "5": "Some causal reasoning but stops at the first plausible explanation",
                "7": "Root causes identified for major findings with clear causal chains",
                "9": "Every significant finding traces symptoms to root causes with evidence for the causal chain",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "Actionable recommendations follow from findings. Each significant finding"
                " includes a concrete suggestion for what to change — specific enough that"
                " someone could implement it without further investigation."
            ),
            category="standard",
            anti_patterns=[
                "recommendations like 'improve error handling' without specifying where or how",
                "suggestions that are true but not actionable ('use better models')",
                "analysis that identifies problems perfectly but offers no path forward",
            ],
            score_anchors={
                "3": "No recommendations, or only platitudes ('improve quality')",
                "5": "Recommendations exist but are too vague to act on without further investigation",
                "7": "Most recommendations are concrete and actionable with one or two that are vague",
                "9": "Every recommendation is specific enough to implement — names what, where, and how",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "The analysis surfaces patterns and structural issues across the dataset,"
                " not just individual anomalies reported chronologically. Individual events"
                " are connected into themes — recurring behaviors, systematic biases, or"
                " architectural issues that explain multiple observations at once."
            ),
            category="standard",
            anti_patterns=[
                "each finding treated in isolation with no cross-referencing or synthesis",
                "analysis reports individual events chronologically without identifying themes",
                "structural or systemic issues invisible because each instance is discussed separately",
                "missing the forest for the trees — many specific findings but no unifying insight",
            ],
            score_anchors={
                "3": "Chronological event log — no synthesis or pattern identification",
                "5": "Some grouping of findings but patterns are stated, not demonstrated",
                "7": "Major patterns identified and connected to specific instances",
                "9": "Structural insights that explain multiple observations at once — the reader gains a mental model",
            },
        ),
    ],
    # ── planning ─────────────────────────────────────────────────────────
    # Consolidated from 9 to 7: E1+E2+E6 merged into structural soundness (E1).
    "planning": [
        GeneratedCriterion(
            id="E1",
            text=(
                "The plan is structurally sound: it captures the user's outcome and"
                " constraints without scope drift, the task graph has valid dependencies"
                " and coherent ordering, and sequencing demonstrates risk management —"
                " high-risk or foundational tasks come first, quality gates are placed"
                " where they most reduce rework."
            ),
            category="standard",
            anti_patterns=[
                "plan that addresses a goal adjacent to but not exactly what was requested",
                "contradictory or circular dependencies in the task graph",
                "high-risk tasks scheduled after work that depends on them",
                "no quality gates — everything runs to completion before any validation",
            ],
            score_anchors={
                "3": "Scope drift from the goal, broken dependencies, or illogical ordering",
                "5": "Captures the goal but sequencing is naive — no risk awareness, linear execution",
                "7": "Sound structure with thoughtful sequencing, minor dependency or ordering issues",
                "9": "Tight scope, valid graph, risk-aware ordering with quality gates at the right points",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Tasks describe both what to produce AND how to approach it — the method,"
                " key decisions, and constraints that guide execution. 'Create the hero"
                " section' is insufficient; 'restructure the hero section: move value"
                " proposition above the fold, use existing brand palette, add a single"
                " prominent CTA' tells the executor what to actually do."
            ),
            category="standard",
            anti_patterns=[
                "tasks that name a deliverable without describing the approach",
                "generic instructions that work for any project ('implement the feature')",
                "missing key decisions that the executor would need to make on their own",
                "'create X' without specifying which decisions have already been made vs. left open",
            ],
            score_anchors={
                "3": "Tasks are deliverable labels — executor must infer all creative and technical direction",
                "5": "Tasks describe the what but leave key how-decisions unspecified",
                "7": "Most tasks include approach guidance but a few lack specificity on key decisions",
                "9": "Each task is actionable without requiring the executor to infer creative or technical direction",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Each task has verification guidance matched to its type. Verification"
                " may be deterministic (run tests, validate responses, check file structure)"
                " or qualitative (render and assess visual quality, evaluate tone). Plans"
                " must NOT force numeric thresholds on inherently qualitative work — 'visually"
                " inspect the rendered page for layout balance' is valid verification."
            ),
            category="standard",
            anti_patterns=[
                "no verification at all — tasks end with 'implement X' and have no success criteria",
                "forcing '95% test coverage' on creative or design tasks",
                "generic 'test thoroughly' without specifying what to test or check",
                "verification that doesn't match the task type (numeric checks on qualitative work)",
            ],
            score_anchors={
                "3": "No verification guidance — tasks are open-ended with no success criteria",
                "5": "Some tasks have verification but it's generic ('test it') or mismatched to type",
                "7": "Most tasks have appropriate verification, one or two are generic",
                "9": "Every task has verification guidance matched to its type — deterministic or qualitative as appropriate",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "Technology and tooling choices are explicit — frameworks, libraries,"
                " APIs, and tools are named. Where tasks connect or produce artifacts"
                " consumed by other tasks, interface contracts are specified: data shapes,"
                " file conventions, API signatures, or shared types."
            ),
            category="standard",
            anti_patterns=[
                "technology choices left for the executor to guess ('use an appropriate framework')",
                "tasks that produce output consumed by later tasks with no interface specification",
                "implicit assumptions about file formats, data shapes, or API contracts",
            ],
            score_anchors={
                "3": "No technology specified — executor must choose frameworks, tools, and formats",
                "5": "Major technologies named but interfaces between tasks are unspecified",
                "7": "Technologies explicit with most interfaces specified, a few assumed",
                "9": "All technology choices and inter-task interfaces are explicit and consistent",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "The plan demonstrates strategic depth — major decisions (architecture,"
                " creative direction, structure, approach) are deliberate and justified"
                " with rationale tied to the actual problem context, not just 'best"
                " practice' or 'modern trend.' If the project name could be swapped out"
                " and the plan reused unchanged, it lacks the specificity that produces"
                " excellent results."
            ),
            category="primary",
            anti_patterns=[
                "generic plan that could apply to any project in the same domain",
                "decisions justified by 'best practice' or 'industry standard' rather than problem-specific reasoning",
                "no documented rationale for major architectural or creative decisions",
                "assumptions and trade-offs left implicit rather than explicitly stated",
            ],
            score_anchors={
                "3": "Plan is a generic template — swap the project name and it works unchanged",
                "5": "Plan references the specific project but decisions are still generic best-practice",
                "7": "Most decisions are justified with problem-specific reasoning, a few are generic",
                "9": "Every major decision has rationale tied to THIS project's specific context and constraints",
            },
        ),
        GeneratedCriterion(
            id="E6",
            text=(
                "Iterations prefer tightening existing tasks over adding new ones."
                " New tasks are justified when filling genuine gaps, but unjustified"
                " growth indicates sprawl. Descriptions, verification, and"
                " dependencies should improve in precision across rounds."
            ),
            category="standard",
            anti_patterns=[
                "each iteration adds tasks without improving existing ones",
                "plan grows in scope rather than in precision",
                "new tasks that overlap with or duplicate existing ones",
                "verification and descriptions remain vague despite multiple iterations",
            ],
            score_anchors={
                "3": "Iterations add scope without improving precision — plan sprawls",
                "5": "Some tightening but also unjustified new tasks",
                "7": "Iterations mostly tighten existing tasks with justified additions",
                "9": "Each iteration sharpens precision — the plan gets tighter, not wider",
            },
        ),
        GeneratedCriterion(
            id="E7",
            text=(
                "Tasks are classified as deterministic or exploratory with appropriate"
                " specification depth. Deterministic tasks have exact steps and interface"
                " contracts. Exploratory tasks have success criteria and constraints"
                " instead of implementation steps, giving the executor freedom to iterate."
                " The plan includes evaluation checkpoints after exploratory chunks."
            ),
            category="standard",
            anti_patterns=[
                "exploratory tasks over-specified with exact steps that may not work",
                "deterministic tasks under-specified as if they need creative judgment",
                "no evaluation checkpoints after high-risk or exploratory chunks",
                "treating all tasks identically regardless of their certainty level",
            ],
            score_anchors={
                "3": "All tasks have the same specification depth regardless of type",
                "5": "Some distinction between task types but specification depth doesn't match",
                "7": "Task types distinguished with appropriate specification, checkpoints present but sparse",
                "9": "Clear deterministic/exploratory classification with matched specification depth and evaluation checkpoints",
            },
        ),
    ],
    # ── spec ─────────────────────────────────────────────────────────────
    # Consolidated from 7 to 6: E4 simplified to focus on prioritization.
    "spec": [
        GeneratedCriterion(
            id="E1",
            text=(
                "Each requirement describes a single, testable behavior or property"
                " with enough precision that a developer can implement without guessing"
                " intent. Requirements that leave room for interpretation on critical"
                " details produce implementations that miss the mark."
            ),
            category="standard",
            anti_patterns=[
                "compound requirements that combine multiple behaviors in one statement",
                "vague language like 'should be fast' or 'user-friendly' without measurable criteria",
                "requirements that describe goals rather than observable behaviors",
                "'the system should handle errors gracefully' without specifying which errors or what gracefully means",
            ],
            score_anchors={
                "3": "Requirements are vague goals — a developer would need to ask 'what does this actually mean?'",
                "5": "Requirements have clear intent but critical details are left to interpretation",
                "7": "Most requirements are precise and testable with minor ambiguity on edge cases",
                "9": "Every requirement is a single, testable behavior — a developer can implement without clarification",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "Each requirement has concrete acceptance criteria: specific conditions,"
                " inputs, expected outputs, or observable behaviors that prove the"
                " requirement is met. 'Works correctly' is not acceptance criteria;"
                " 'given input X, produces output Y within Z ms' is."
            ),
            category="standard",
            anti_patterns=[
                "acceptance criteria that restate the requirement in different words",
                "'works as expected' without defining what 'expected' means",
                "missing acceptance criteria on requirements where pass/fail is ambiguous",
            ],
            score_anchors={
                "3": "No acceptance criteria, or criteria that restate requirements as 'it should work'",
                "5": "Some acceptance criteria but vague on pass/fail boundaries",
                "7": "Most requirements have concrete acceptance criteria, a few are vague",
                "9": "Every requirement has specific, verifiable acceptance criteria with clear pass/fail boundaries",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "Scope boundaries are explicit — what is in scope and what is deliberately"
                " out of scope are both stated. The spec does not silently omit aspects"
                " the user would expect to be covered. Unstated boundaries cause scope"
                " creep during implementation."
            ),
            category="standard",
            anti_patterns=[
                "no out-of-scope section — implementer must guess where the boundaries are",
                "scope is implied by what's listed rather than explicitly bounded",
                "aspects the user would naturally expect are neither in-scope nor out-of-scope",
            ],
            score_anchors={
                "3": "No scope boundaries — implementer would reasonably build things that aren't wanted",
                "5": "In-scope is clear but out-of-scope is not stated — ambiguous edges",
                "7": "Both in-scope and out-of-scope stated with one or two ambiguous boundaries",
                "9": "Scope is fully explicit — an implementer knows exactly what to build and what to skip",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "Requirements are prioritized and internally consistent — the ordering"
                " reflects genuine implementation dependencies and user-facing importance."
                " No two requirements contradict each other or create impossible trade-offs"
                " without explicit acknowledgment."
            ),
            category="standard",
            anti_patterns=[
                "requirements that contradict each other without acknowledging the tension",
                "flat priority — everything is 'must-have' with no indication of what to cut if needed",
                "ordering that doesn't reflect implementation dependencies",
            ],
            score_anchors={
                "3": "Requirements contradict each other or have no priority — everything is 'critical'",
                "5": "No conflicts but priority is flat or ordering doesn't reflect dependencies",
                "7": "Prioritized and consistent with minor ordering issues",
                "9": "Clear priority tiers, no conflicts, ordering reflects real dependencies and importance",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "The spec demonstrates strategic depth — the chosen design direction,"
                " system architecture, and interaction model are deliberate and justified"
                " with rationale tied to the actual problem context and users. If the"
                " project name could be swapped out and the spec reused unchanged, it"
                " lacks the specificity that produces excellent results."
            ),
            category="primary",
            anti_patterns=[
                "generic spec that could apply to any project in the same category",
                "design decisions justified by 'industry standard' rather than problem-specific reasoning",
                "no rationale for architectural choices — they appear arbitrary",
                "spec reads like a template with project-specific nouns inserted",
            ],
            score_anchors={
                "3": "Spec is a template — swap the project name and it works for anything in the same category",
                "5": "References the specific project but decisions are still generic best-practice",
                "7": "Most decisions have problem-specific rationale, a few are generic",
                "9": "Every design decision is justified by THIS project's specific context, users, and constraints",
            },
        ),
        GeneratedCriterion(
            id="E6",
            text=(
                "Requirements anticipate edge cases, error states, and boundary conditions"
                " relevant to the domain. The spec covers not just the happy path but the"
                " realistic failure modes and unusual inputs that will occur in practice."
            ),
            category="standard",
            anti_patterns=[
                "only the happy path is specified — no error handling, empty states, or boundaries",
                "edge cases mentioned generically ('handle errors') without specifying which ones",
                "missing the domain-specific failure modes that practitioners would immediately identify",
            ],
            score_anchors={
                "3": "Only the happy path — no mention of errors, empty states, or boundary conditions",
                "5": "Some edge cases mentioned but the most important domain-specific ones are missing",
                "7": "Major edge cases and error states covered, a few domain-specific scenarios missing",
                "9": "A domain expert would say 'you've thought of the tricky cases' — comprehensive coverage",
            },
        ),
    ],
    # ── round_evaluator ──────────────────────────────────────────────────
    "round_evaluator": [
        GeneratedCriterion(
            id="E1",
            text=(
                "The evaluator packet fully follows the round_evaluator contract."
                " Required sections are present, the output stays critique-only, and"
                " it does not drift into checklist payload drafting, parent workflow"
                " tool instructions, or terminal outcome recommendations."
            ),
            category="standard",
            anti_patterns=[
                "evaluator starts writing the improved answer instead of critiquing the current one",
                "packet includes tool-call instructions or checklist payload formatting",
                "evaluator recommends 'stop iterating' or 'this is good enough' (terminal outcome decisions)",
                "missing required sections from the contract",
            ],
            score_anchors={
                "3": "Packet violates the contract — includes answer drafting, tool instructions, or terminal recommendations",
                "5": "Required sections present but evaluator drifts into implementation advice in places",
                "7": "Contract followed with minor boundary violations (e.g., hints at terminal outcome)",
                "9": "Pure critique — every section follows the contract, no role confusion",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=(
                "criteria_interpretation is rigorous for every active criterion."
                " It explains what the criterion truly demands, what excellent work"
                " would look like, and which false positives or shallow passes might"
                " otherwise slip through."
            ),
            category="standard",
            anti_patterns=[
                "restating criterion text verbatim instead of interpreting what it demands",
                "shallow interpretation that misses the criterion's deeper implication",
                "no mention of false positives — ways output could appear to pass while actually failing",
            ],
            score_anchors={
                "3": "Criteria restated verbatim — no interpretation of what they actually demand",
                "5": "Some interpretation but misses subtle implications or false-positive risks",
                "7": "Rigorous interpretation for most criteria with clear false-positive awareness",
                "9": "Every criterion deeply interpreted — what it demands, what excellence looks like, what could slip through",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=(
                "criterion_findings are evidence-grounded and criterion-specific."
                " They cite concrete details from the candidate answers, identify"
                " hidden risks, and clearly separate weak spots from source-answer"
                " strengths worth carrying forward."
            ),
            category="primary",
            anti_patterns=[
                "vague assessments ('this could be better') without citing specific evidence from the answers",
                "findings that apply to any answer rather than citing specific details from these candidates",
                "no distinction between strengths to preserve and weaknesses to fix",
                "hidden risks not identified — only surface-level observations",
            ],
            score_anchors={
                "3": "Generic assessments — 'could be better', 'needs work' — without citing specific evidence",
                "5": "Some evidence cited but findings are shallow and miss hidden risks",
                "7": "Most findings cite specific evidence with clear strength/weakness separation",
                "9": "Every finding cites concrete details from the answers, identifies hidden risks, and separates preserve from fix",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=(
                "cross_answer_synthesis and preserve guidance are decisive and lossless."
                " The packet makes clear which answer is strongest on which dimension,"
                " what no answer gets right yet, and what strengths must not regress"
                " in the next revision."
            ),
            category="standard",
            anti_patterns=[
                "synthesis that just averages opinions rather than identifying which answer excels where",
                "preserve guidance that is too vague to prevent regression of existing strengths",
                "'all answers have room for improvement' without specifics about what each does best",
            ],
            score_anchors={
                "3": "No synthesis — findings are per-criterion without cross-answer comparison",
                "5": "Some comparison but vague about which answer excels where",
                "7": "Clear per-dimension winner identification with mostly specific preserve guidance",
                "9": "Decisive: which answer wins each dimension, what's unsolved, what must not regress — all specific",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "improvement_spec is actionable, prioritized, and concrete enough that"
                " the parent can implement it with minimal reinterpretation. It describes"
                " what to change and how to change it, not just restates the problem."
            ),
            category="standard",
            anti_patterns=[
                "improvement spec that restates findings without saying what to do about them",
                "'make it better' without specifying what 'better' means concretely",
                "unprioritized list where everything is equally important",
                "instructions so vague the parent must re-diagnose the problem to act on them",
            ],
            score_anchors={
                "3": "Improvement spec restates problems — parent must figure out what to change",
                "5": "Direction is clear but specifics are missing — parent must fill in the how",
                "7": "Actionable and prioritized with most changes specified concretely",
                "9": "Parent can execute the improvement spec with minimal reinterpretation — what, where, and how",
            },
        ),
        GeneratedCriterion(
            id="E6",
            text=(
                "verification_plan and evidence_gaps name what still needs to be checked,"
                " what evidence is missing, and how to close those gaps — not generic"
                " 'test more' guidance but specific checks tied to identified risks."
            ),
            category="standard",
            anti_patterns=[
                "generic 'test more thoroughly' without specifying what to test",
                "verification plan that doesn't connect to the specific risks identified in findings",
                "no evidence gaps identified — assumes the evaluation was complete",
            ],
            score_anchors={
                "3": "No verification plan, or only 'test it more'",
                "5": "Some specific checks but not connected to identified risks or evidence gaps",
                "7": "Verification plan names specific checks tied to findings, minor gaps in coverage",
                "9": "Every identified risk has a specific verification check and missing evidence is catalogued",
            },
        ),
        GeneratedCriterion(
            id="E7",
            text=(
                "unexplored_approaches includes at least one grounded, non-obvious"
                " direction that could beat every current answer rather than merely"
                " patching the current weaknesses. The approach should be specific enough"
                " to act on, not just 'try a different strategy.'"
            ),
            category="standard",
            anti_patterns=[
                "unexplored approaches that are just reworded versions of current strategies",
                "'try a different approach' without specifying what approach",
                "approaches that are obviously worse than current candidates",
                "no unexplored approaches section at all",
            ],
            score_anchors={
                "3": "No unexplored approaches, or only vague suggestions ('try something different')",
                "5": "An approach is suggested but it's obvious or just a variant of existing strategies",
                "7": "A genuinely different approach is suggested with enough specificity to attempt",
                "9": "A non-obvious, grounded approach that could leapfrog current answers — specific enough to act on immediately",
            },
        ),
    ],
}

# Public constant for validation (used by config_validator and tests)
VALID_CRITERIA_PRESETS: frozenset[str] = frozenset(_CRITERIA_PRESETS.keys())


def criteria_from_inline(inline_list: list[dict[str, str]]) -> list[GeneratedCriterion]:
    """Convert inline criteria dicts to GeneratedCriterion objects.

    Accepts 'text' as the primary key, with 'description' and 'name' as fallbacks.

    Args:
        inline_list: List of dicts with 'text' (or 'description'/'name') and 'category' keys.

    Returns:
        List of GeneratedCriterion with E1..EN IDs.

    Raises:
        ValueError: If a criterion has no text content (no 'text', 'description', or 'name' key).
    """
    criteria: list[GeneratedCriterion] = []
    for i, item in enumerate(inline_list):
        # Accept common aliases: description, name -> text
        text = item.get("text") or item.get("description") or item.get("name")
        if not text:
            raise ValueError(
                f"Criterion {i + 1} is missing required 'text' field. " f'Expected format: {{"text": "...", "category": "primary|standard|stretch"}}. ' f"Got keys: {list(item.keys())}",
            )
        verify_by = str(item.get("verify_by") or "").strip() or None
        raw_cat = str(item.get("category", "standard")).strip().lower()
        # Map legacy category values
        if raw_cat in ("must", "core"):
            cat = "standard"
        elif raw_cat == "primary":
            cat = "primary"
        elif raw_cat in ("could", "stretch"):
            cat = "stretch"
        else:
            cat = "standard"
        raw_anti = item.get("anti_patterns")
        anti = raw_anti if isinstance(raw_anti, list) else None
        raw_anchors = item.get("score_anchors")
        anchors = raw_anchors if isinstance(raw_anchors, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_anchors.items()) else None
        criteria.append(
            GeneratedCriterion(
                id=f"E{i + 1}",
                text=text,
                category=cat,
                verify_by=verify_by,
                anti_patterns=anti,
                score_anchors=anchors,
            ),
        )
    return criteria


def build_decomposition_execution_criteria(subtask: str) -> list[GeneratedCriterion]:
    """Build parameterized checklist criteria for executing one decomposition subtask."""
    scope = " ".join((subtask or "").split())
    if len(scope) > 140:
        scope = scope[:137].rstrip() + "..."
    if not scope:
        scope = "your assigned subtask"

    return [
        GeneratedCriterion(
            id="E1",
            text=(f"The current work substantially completes and improves the owned scope" f" for this subtask: {scope}"),
            category="standard",
            anti_patterns=[
                "only addressing the easy parts of the subtask while leaving the hard parts untouched",
                "superficial changes that don't advance the subtask toward completion",
                "declaring the subtask done when significant gaps remain",
            ],
            score_anchors={
                "3": "Work addresses less than half the subtask scope — major deliverables missing",
                "5": "Core deliverables present but several significant aspects are incomplete or shallow",
                "7": "Subtask substantially complete with minor gaps or rough edges",
                "9": "Subtask fully complete — every aspect of the owned scope addressed and improved",
            },
        ),
        GeneratedCriterion(
            id="E2",
            text=("Relevant peer work that touches this subtask is incorporated cleanly" " where needed — interfaces, contracts, shared assets, or adjacent" " integration boundaries."),
            category="standard",
            anti_patterns=[
                "ignoring peer work that overlaps with this subtask's boundaries",
                "duplicating work a peer has already completed instead of building on it",
                "breaking interfaces or contracts that peer subtasks depend on",
            ],
            score_anchors={
                "3": "Peer work ignored — output conflicts with or duplicates adjacent subtask results",
                "5": "Aware of peer work but integration is rough — seams visible at boundaries",
                "7": "Peer work incorporated cleanly at most boundaries with minor integration issues",
                "9": "Seamless integration — peer work and this subtask's output connect as if planned together",
            },
        ),
        GeneratedCriterion(
            id="E3",
            text=("Changes stay within the owned scope except for necessary adjacent" " integration. The agent does not take over unrelated work owned by" " other subtasks."),
            category="standard",
            anti_patterns=[
                "rewriting code or content that belongs to another subtask's scope",
                "scope creep into adjacent areas that makes peer work harder",
                "refactoring shared infrastructure in ways that break other subtasks",
            ],
            score_anchors={
                "3": "Significant changes outside owned scope — stepping on peers' territory",
                "5": "Mostly within scope but some unnecessary changes to adjacent areas",
                "7": "Within scope with only justified adjacent integration touches",
                "9": "Precisely scoped — every change is within owned scope or is necessary integration",
            },
        ),
        GeneratedCriterion(
            id="E4",
            text=("The current work does not introduce regressions in the owned area or" " shared contracts it depends on. Validation evidence is strong enough" " to support that claim."),
            category="standard",
            anti_patterns=[
                "fixing one thing while breaking another in the same area",
                "no validation evidence — regression-free is asserted but not demonstrated",
                "changes to shared contracts without verifying dependent code still works",
            ],
            score_anchors={
                "3": "Introduces clear regressions — previously working aspects are now broken",
                "5": "No obvious regressions but validation evidence is thin or absent",
                "7": "No regressions with reasonable validation evidence for the main paths",
                "9": "No regressions with thorough validation — shared contracts and edge cases verified",
            },
        ),
        GeneratedCriterion(
            id="E5",
            text=(
                "This revision is a meaningful improvement to the owned subtask — it"
                " advances quality or completeness, not just reformats, renames, or"
                " makes superficial edits that don't change the substance."
            ),
            category="standard",
            anti_patterns=[
                "reformatting or renaming without substantive changes",
                "moving code around without improving it",
                "adding comments or documentation when the deliverable itself needs work",
                "busy-work changes that look like progress but don't advance the subtask",
            ],
            score_anchors={
                "3": "Changes are cosmetic — reformatting, renaming, or trivial edits with no substance",
                "5": "Some meaningful improvement but mixed with significant churn",
                "7": "Clearly meaningful improvement with minimal churn",
                "9": "Every change advances the subtask's quality or completeness — no wasted effort",
            },
        ),
    ]


def get_criteria_for_preset(preset: str) -> list[GeneratedCriterion]:
    """Return domain-specific criteria for a named preset.

    Args:
        preset: One of the known preset names.

    Returns:
        List of GeneratedCriterion with E1..E5 IDs.

    Raises:
        ValueError: If preset name is not recognized.
    """
    if preset not in _CRITERIA_PRESETS:
        valid = ", ".join(sorted(_CRITERIA_PRESETS.keys()))
        raise ValueError(
            f"Unknown criteria preset: '{preset}'. Valid presets: {valid}",
        )

    return list(_CRITERIA_PRESETS[preset])


def get_default_criteria(has_changedoc: bool = False) -> list[GeneratedCriterion]:
    """Return static default evaluation criteria.

    These are used when generation is disabled or fails. They are concrete,
    GEPA-inspired defaults that work for any task type: requirements fidelity,
    multi-level correctness, per-part depth (primary), and intentional craft.

    The ``has_changedoc`` flag is retained for call-site compatibility but
    does not alter the fallback defaults.

    Args:
        has_changedoc: Retained for compatibility with existing call sites.

    Returns:
        List of GeneratedCriterion with E-prefix IDs.
    """
    return list(_DEFAULT_CRITERIA)


def _parse_criteria_response(
    response: str,
    min_criteria: int = 4,
    max_criteria: int = 7,
) -> tuple[list[GeneratedCriterion] | None, str | None]:
    """Parse LLM response into GeneratedCriterion objects.

    Tries to extract JSON from the response using multiple strategies:
    1. Direct JSON parse
    2. Extract from markdown code blocks
    3. Find JSON object by braces

    Returns (criteria, aspiration) tuple. Both may be None if parsing fails.
    """
    json_str = response.strip()

    data = _try_parse_json(json_str)

    # Strategy 2: Extract from markdown code blocks
    if data is None and "```" in json_str:
        if "```json" in json_str:
            start = json_str.find("```json") + 7
            end = json_str.find("```", start)
            if end > start:
                data = _try_parse_json(json_str[start:end].strip())
        if data is None:
            start = json_str.find("```") + 3
            end = json_str.find("```", start)
            if end > start:
                data = _try_parse_json(json_str[start:end].strip())

    # Strategy 3: Find JSON by braces
    if data is None:
        criteria_start = json_str.find('{"criteria"')
        if criteria_start >= 0:
            brace_count = 0
            json_end = -1
            for i, char in enumerate(json_str[criteria_start:]):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = criteria_start + i + 1
                        break
            if json_end > criteria_start:
                data = _try_parse_json(json_str[criteria_start:json_end])

    if data is None or "criteria" not in data:
        logger.warning("Failed to parse criteria response")
        return None, None

    try:
        aspiration = data.get("aspiration") if isinstance(data.get("aspiration"), str) else None

        raw_criteria = data["criteria"]
        if not isinstance(raw_criteria, list):
            logger.warning("criteria field is not a list")
            return None, None

        # Validate count
        if len(raw_criteria) < min_criteria:
            logger.warning(
                f"Too few criteria: {len(raw_criteria)} < {min_criteria}",
            )
            return None, None
        if len(raw_criteria) > max_criteria:
            logger.warning(
                f"Too many criteria: {len(raw_criteria)} > {max_criteria}",
            )
            return None, None

        # Parse into GeneratedCriterion objects with opinionated category values.
        criteria = []
        primary_count = 0
        for i, item in enumerate(raw_criteria):
            text = item.get("text", "")
            verify_by = item.get("verify_by") or None
            if verify_by and not isinstance(verify_by, str):
                verify_by = None
            # Extract category with legacy mapping
            raw_cat = str(item.get("category", "standard")).strip().lower()
            if raw_cat in ("must", "core"):
                cat = "standard"
            elif raw_cat == "primary":
                cat = "primary"
                primary_count += 1
            elif raw_cat in ("could", "stretch"):
                cat = "stretch"
            else:
                cat = "standard"
            # Extract anti-patterns
            raw_anti = item.get("anti_patterns")
            anti = raw_anti if isinstance(raw_anti, list) and all(isinstance(a, str) for a in raw_anti) else None
            # Extract score anchors — must be a dict with string keys and string values
            raw_anchors = item.get("score_anchors")
            anchors = raw_anchors if isinstance(raw_anchors, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_anchors.items()) else None
            criteria.append(
                GeneratedCriterion(
                    id=f"E{i + 1}",
                    text=text,
                    category=cat,
                    verify_by=verify_by,
                    anti_patterns=anti,
                    score_anchors=anchors,
                ),
            )

        if primary_count > 1:
            logger.warning(
                f"[CriteriaParser] {primary_count} criteria marked 'primary', expected at most 1. Keeping first.",
            )
            seen_primary = False
            for c in criteria:
                if c.category == "primary":
                    if seen_primary:
                        c.category = "standard"
                    seen_primary = True

        return criteria, aspiration

    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Failed to extract criteria from parsed data: {e}")
        return None, None


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Attempt to parse JSON, returning None on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def parse_evolution_response(
    response: str,
    current_criteria: list["GeneratedCriterion"],
    min_criteria: int = 4,
    max_criteria: int = 7,
) -> tuple[list["GeneratedCriterion"] | None, str | None, bool]:
    """Parse a criteria evolution synthesizer response.

    Uses the same multi-strategy JSON extraction as ``_parse_criteria_response``.
    Handles the ``{"status": "UNCHANGED"}`` sentinel, merges unchanged criteria
    from *current_criteria* with any evolved criteria, and re-assigns E1..EN IDs.

    Returns:
        (evolved_criteria, evolution_summary, is_unchanged)
        - If *is_unchanged* is True, criteria and summary are None.
        - On parse failure, returns (None, None, False).
    """
    json_str = response.strip()
    data = _try_parse_json(json_str)

    if data is None and "```" in json_str:
        for fence in ("```json", "```"):
            start = json_str.find(fence) + len(fence)
            end = json_str.find("```", start)
            if end > start:
                data = _try_parse_json(json_str[start:end].strip())
                if data is not None:
                    break

    if data is None:
        for search_key in ('{"status"', '{"evolved_criteria"', '{"unchanged_ids"'):
            idx = json_str.find(search_key)
            if idx >= 0:
                brace_count = 0
                json_end = -1
                for i, ch in enumerate(json_str[idx:]):
                    if ch == "{":
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = idx + i + 1
                            break
                if json_end > idx:
                    data = _try_parse_json(json_str[idx:json_end])
                    if data is not None:
                        break

    if data is None:
        logger.warning("[parse_evolution_response] Failed to extract JSON")
        return None, None, False

    # Sentinel: synthesizer decided no evolution needed
    if data.get("status") == "UNCHANGED":
        return None, None, True

    raw_evolved = data.get("evolved_criteria")
    if not isinstance(raw_evolved, list):
        logger.warning("[parse_evolution_response] No evolved_criteria list in response")
        return None, None, False

    evolution_summary: str | None = data.get("evolution_summary") or data.get("analysis") or None

    # Collect all criteria: evolved first (preserving order), then unchanged in
    # original order if they weren't already covered
    evolved_by_id: dict[str, dict[str, Any]] = {}
    for item in raw_evolved:
        cid = item.get("id", "")
        evolved_by_id[cid] = item

    merged: list["GeneratedCriterion"] = []

    # Walk original order, replacing evolved criteria and keeping unchanged ones
    for c in current_criteria:
        if c.id in evolved_by_id:
            item = evolved_by_id[c.id]
            raw_cat = str(item.get("category", "standard")).strip().lower()
            if raw_cat in ("must", "core", "should"):
                cat = "standard"
            elif raw_cat == "primary":
                cat = "primary"
            elif raw_cat in ("could", "stretch"):
                cat = "stretch"
            else:
                cat = "standard"
            raw_anti = item.get("anti_patterns")
            anti = raw_anti if isinstance(raw_anti, list) and all(isinstance(a, str) for a in raw_anti) else None
            raw_anchors = item.get("score_anchors")
            anchors = raw_anchors if isinstance(raw_anchors, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_anchors.items()) else None
            merged.append(
                GeneratedCriterion(
                    id=c.id,
                    text=item.get("text", c.text),
                    category=cat,
                    verify_by=item.get("verify_by") or c.verify_by,
                    anti_patterns=anti,
                    score_anchors=anchors,
                ),
            )
        else:
            # Keep unchanged
            merged.append(c)

    # Append any newly added criteria (id not in current_criteria)
    existing_ids = {c.id for c in current_criteria}
    for item in raw_evolved:
        cid = item.get("id", "")
        if cid not in existing_ids:
            raw_cat = str(item.get("category", "standard")).strip().lower()
            if raw_cat in ("must", "core", "should"):
                cat = "standard"
            elif raw_cat == "primary":
                cat = "primary"
            elif raw_cat in ("could", "stretch"):
                cat = "stretch"
            else:
                cat = "standard"
            raw_anti = item.get("anti_patterns")
            anti = raw_anti if isinstance(raw_anti, list) and all(isinstance(a, str) for a in raw_anti) else None
            raw_anchors = item.get("score_anchors")
            anchors = raw_anchors if isinstance(raw_anchors, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_anchors.items()) else None
            merged.append(
                GeneratedCriterion(
                    id=cid,
                    text=item.get("text", ""),
                    category=cat,
                    verify_by=item.get("verify_by"),
                    anti_patterns=anti,
                    score_anchors=anchors,
                ),
            )

    if not merged:
        logger.warning("[parse_evolution_response] No criteria after merge")
        return None, None, False

    # Use the current criteria count as the lower bound for evolution merges
    # (caller may pass 3 criteria even though normal generation requires 4+)
    effective_min = min(min_criteria, len(current_criteria)) if current_criteria else min_criteria
    if len(merged) < effective_min or len(merged) > max_criteria:
        logger.warning(
            "[parse_evolution_response] Criteria count %d out of bounds [%d, %d]",
            len(merged),
            effective_min,
            max_criteria,
        )
        # Clamp silently if slightly over; hard-fail if too few
        if len(merged) > max_criteria:
            merged = merged[:max_criteria]
        if len(merged) < effective_min:
            return None, None, False

    # Enforce at most one primary
    primary_count = sum(1 for c in merged if c.category == "primary")
    if primary_count > 1:
        seen_primary = False
        for c in merged:
            if c.category == "primary":
                if seen_primary:
                    c.category = "standard"
                else:
                    seen_primary = True

    # Re-assign IDs E1..EN to maintain consistent ordering
    for i, c in enumerate(merged):
        c.id = f"E{i + 1}"

    return merged, evolution_summary, False


class EvaluationCriteriaGenerator:
    """Generates task-specific evaluation criteria via subagent coordination.

    When enabled, spawns a pre-collaboration subagent run to generate criteria
    specific to the task. Falls back to static defaults on failure.
    """

    def __init__(self):
        self.last_generation_source = "unknown"
        self.last_aspiration: str | None = None

    def _build_generation_prompt(
        self,
        task: str,
        has_changedoc: bool,
        min_criteria: int = 4,
        max_criteria: int = 7,
        has_planning_spec_context: bool = False,
    ) -> str:
        """Build the prompt for criteria generation.

        Args:
            task: The user's task description
            has_changedoc: Whether changedoc mode is active
            min_criteria: Minimum number of criteria
            max_criteria: Maximum number of criteria
            has_planning_spec_context: Whether planning/spec context is mounted
                and should be explicitly referenced by prompt guidance.

        Returns:
            The formatted prompt string
        """
        # Changedoc traceability is handled during final presentation,
        # not as an evaluation criterion.  When it was a criterion, agents
        # burned iterations just improving the changedoc instead of the
        # actual deliverable.
        changedoc_instruction = ""

        planning_context_section = ""
        if has_planning_spec_context:
            planning_context_section = """

## Planning/Spec Context Alignment
Read the mounted planning/spec context before generating criteria and align with \
it so goals, personas, and deliverable expectations stay coherent. Treat planning/spec \
files as read-only references — do not modify them.
"""

        # Prompt design informed by:
        # https://www.anthropic.com/engineering/harness-design-long-running-apps
        # Key insight: criteria shape what agents produce, not just how they're scored.
        # Opinionated criteria with anti-patterns and aspiration levels drive quality
        # leaps; generic dimension labels produce generic work.
        return f"""You are generating evaluation criteria for a multi-agent AI system.

## Task Being Evaluated
{task}
{planning_context_section}

## Your Goal
Generate {min_criteria}-{max_criteria} **opinionated** evaluation criteria that define \
what excellent work looks like for THIS task. Each criterion is not just a dimension \
to score — it is a quality principle that shapes how agents approach the work. \
A strong criterion takes a position on what "good" means and explicitly rejects \
common ways outputs go wrong.

## Step 1: Deep Investigation (REQUIRED — do this BEFORE writing criteria)

Before generating any criteria, you MUST conduct a structured investigation of \
what excellence looks like for this specific task. Do not skip this. Generic criteria \
produce generic outputs — the investigation is what makes criteria genuinely specific.

Answer each of the following questions in your thinking. Be concrete and specific \
to THIS task, not generic:

1. **What does excellent output look like for this task type?** Think of the best \
examples you know in this domain. What specifically makes them excellent? Not "it's \
well-designed" — what observable properties distinguish excellent from merely competent?

2. **Where do AI models typically fail on this type of task?** Think about the specific \
ways default model behavior produces mediocre results. What patterns do AI outputs \
exhibit that human experts would immediately recognize as machine-generated or \
uninspired? These become your anti-patterns.

3. **What would a domain expert notice first?** If someone deeply knowledgeable in this \
domain reviewed the output, what would they praise in an excellent version? What \
would make them wince in a mediocre one? What distinguishes "clearly knows the domain" \
from "surface-level understanding"?

4. **What separates "adequate" from "remarkable" here?** Adequate meets requirements. \
Remarkable makes someone stop and pay attention. What specific qualities create that \
gap for THIS task? This should inform your aspiration level and your PRIMARY criterion.

5. **What are the task-specific failure modes?** Not generic problems like "unclear writing" \
but the specific ways THIS kind of output goes wrong. For a recipe website: bland stock \
photography, missing cooking times, generic "season to taste" instructions. For a data \
visualization: misleading axis scales, chartjunk, color palettes that fail for \
colorblindness. Be THIS specific.

Your investigation findings should directly inform every criterion you generate. If a \
criterion could apply equally to any task, it is too generic — ground it in your \
investigation.

## Step 2: Aspiration Level

Based on your investigation, identify the aspiration level for this task in 1-2 phrases. \
What would genuinely excellent output look like? Not "correct and complete" — that \
is the floor. What would make someone say "this is remarkably good"? \
Examples: "publishable in a literary journal", "a senior engineer would merge this \
without changes", "a designer would screenshot this for their portfolio", "an expert \
in the field would learn something from reading this."

Your aspiration level appears in the output JSON and should inform every criterion.

## What Correctness Means

Correctness is not just "the file exists and opens." A correct output works as \
the user actually experiences it:

- **Structural correctness**: right form, can be used (file opens, code runs)
- **Content correctness**: says/computes right things (accurate, complete)
- **Experiential correctness**: behaves correctly in primary use environment \
  (text renders without overflow, visuals display as intended, interactions work)

An output that passes structural checks but fails experiential ones is a *wrong* \
output, not a mediocre one. Correctness criteria must cover all three dimensions.

Correctness is separate from **quality/craft**: a correct output can still be mediocre.

## What Makes Criteria Opinionated

A good criterion does three things:

1. **Takes a position on what "good" means** — not just "is it present?" but \
"does it achieve X quality?" with X being a specific, directional standard.

BAD (dimension label): "Uses vivid imagery."
GOOD (quality definition): "Uses imagery that surprises — that makes the reader \
see something they have seen before in a way they have not. Stock metaphors \
(heart = love, darkness = sadness) or AI-typical purple-prose descriptors \
score poorly."

BAD (dimension label): "Visual design quality."
GOOD (quality definition): "Design coherence: Does the design feel like it was \
authored by someone with a point of view, or assembled from components? Evidence \
of custom decisions — intentional spacing rhythms, a color system that creates mood, \
typography choices that reinforce hierarchy — scores highly. Unmodified component \
library defaults or generic AI aesthetics score poorly."

2. **Names specific anti-patterns to penalize** — what does bad work in this \
dimension look like? Not abstract badness, but the specific ways THIS task type \
typically goes wrong. Include these as an `anti_patterns` list in the JSON.

Examples of good anti-patterns:
- Code: "god functions, swallowed exceptions, any-typed escape hatches"
- Writing: "topic-sentence-then-three-examples structure, hedging qualifiers, \
  conclusions that summarize rather than advance"
- Design: "unmodified library defaults, centered-everything layouts, purple \
  gradients over white cards"
- Data: "cherry-picked examples, conclusions stated before evidence examined"

3. **Marks ONE criterion as "primary"** — the dimension where default model \
behavior is weakest and where improvement matters most. For creative tasks, \
this is usually originality or voice. For technical tasks, architecture or error \
handling. For design, visual distinctiveness. The primary criterion is where you \
push hardest. Set its `category` to `"primary"`.

## Requirements
1. Generate between {min_criteria} and {max_criteria} criteria
2. Each criterion must be specific to THIS task, not generic
3. Each criterion should be scoreable on a 1-10 scale with evidence
4. **Exactly ONE criterion must be `"primary"`** — the most impactful quality \
dimension for this task. All others are `"standard"` (must-pass) or `"stretch"` \
(nice-to-have).
5. **Every criterion must include `anti_patterns`** — 2-4 specific failure modes
6. **Criteria must cover distinct dimensions** — content, experience, craft, etc.
7. **For rendered/experienced artifacts**: include a dedicated rendering \
correctness criterion (no visual defects, broken interactions, etc.)
8. **Per-part quality**: include at least one criterion assessing whether EACH \
significant part independently meets a quality bar, not just the average.
{changedoc_instruction}
## Examples

For a task "Create an SVG of a pelican riding a bicycle":
- **[PRIMARY]** "Riding conviction: The composition must sell the fiction that \
this pelican is actually riding — weight distribution, contact points, and body \
angle create physical plausibility. A pelican floating above a bicycle or \
statically posed with no sense of motion fails."
  anti_patterns: ["character and vehicle as separate non-interacting elements", \
"static T-pose on seat", "missing pedal/handlebar engagement"]
  score_anchors: {{"3": "Pelican and bicycle are separate shapes placed near each \
other with no interaction", "5": "Pelican is on the bicycle but looks pasted on — \
no weight, no motion, stiff posture", "7": "Believable riding pose with contact \
points, but motion feels frozen rather than dynamic", "9": "The pelican's weight \
shifts into the pedals, body leans into a turn — you believe it's actually riding"}}
- "Pelican accuracy: Immediately recognizable as a pelican from silhouette \
alone — beak with throat pouch, proportional body, correct wing structure. A \
generic bird with a long beak is not a pelican."
  anti_patterns: ["cartoon-simplified shapes that lose species identity", \
"anatomically impossible joint positions"]
  score_anchors: {{"3": "Generic bird shape — could be any long-beaked species", \
"5": "Has a pouch-like beak but body proportions are wrong for a pelican", \
"7": "Clearly a pelican but some anatomical details simplified or incorrect", \
"9": "Immediately recognizable as a pelican from silhouette alone"}}

For a task "Write a poem about love":
- **[PRIMARY]** "Earned emotion: The poem makes the reader feel something through \
specific imagery and situation, not through stating feelings. Every emotional beat \
grounded in something concrete enough to see, hear, or touch."
  anti_patterns: ["abstract declarations ('my heart aches')", \
"greeting-card resolution", "emotional escalation without corresponding specificity"]
  score_anchors: {{"3": "States emotions directly — 'I feel so much love' — with no \
grounding image", "5": "Has some imagery but defaults to stock metaphors (heart, \
fire, stars) rather than specific observations", "7": "Most emotional beats anchored \
in concrete images, but 1-2 lines slip into abstraction", "9": "Every feeling earned \
through specific, surprising imagery — reader feels before they understand why"}}
- "Surprise and originality: At least one moment the reader could not have predicted. \
Resistance to the gravitational pull of cliche on the subject of love."
  anti_patterns: ["heart/fire/ocean/stars as primary metaphors", \
"list-of-beautiful-things structure", "ending that restates the opening sentiment"]
  score_anchors: {{"3": "Every image and turn is predictable — reads like a greeting \
card", "5": "Competent but nothing you haven't read before", "7": "One genuinely \
surprising moment but the rest follows expected patterns", "9": "Multiple moments of \
genuine surprise — approaches the subject from an angle you didn't expect"}}

Criteria name a quality axis with an opinion — they do NOT prescribe specific \
quantities, thresholds, or implementation choices.

BAD (prescriptive): "The website contains at least 4 pages"
GOOD (evaluative): "Topic coverage: all major aspects addressed with meaningful depth"

BAD (whole-output only): "The output shows intentional design choices"
GOOD (per-part): "Per-section quality: each significant section independently \
demonstrates craft — no section is carried by the strength of others. Evaluate the \
weakest section, not the average."

## Step 3: Generate Criteria with Score Anchors

## Output Format
Return JSON with this structure:
{{
    "aspiration": "[1-2 phrase quality ceiling for this task]",
    "criteria": [
        {{
            "text": "[Aspect]: [opinionated quality definition].",
            "category": "primary",
            "anti_patterns": ["specific failure mode 1", "specific failure mode 2"],
            "verify_by": "evidence gathering instructions if needed",
            "score_anchors": {{
                "3": "[What a 3/10 looks like for THIS criterion on THIS task — concrete, observable]",
                "5": "[What a 5/10 looks like — the 'adequate but uninspired' level]",
                "7": "[What a 7/10 looks like — good with specific nameable gaps]",
                "9": "[What a 9/10 looks like — a professional would be impressed]"
            }}
        }},
        {{
            "text": "[Aspect]: [opinionated quality definition].",
            "category": "standard",
            "anti_patterns": ["failure mode 1", "failure mode 2"],
            "score_anchors": {{
                "3": "[Concrete description of poor performance on this dimension]",
                "5": "[Concrete description of adequate performance]",
                "7": "[Concrete description of good performance]",
                "9": "[Concrete description of excellent performance]"
            }}
        }}
    ]
}}

**`score_anchors` field**: REQUIRED for every criterion. Each criterion must include \
concrete descriptions of what scores 3, 5, 7, and 9 look like for THAT criterion \
on THIS specific task. These anchors calibrate evaluators by grounding abstract \
numbers in observable output characteristics. Without anchors, all scores drift to \
7-8 regardless of actual quality.

Rules for score anchors:
- Each anchor must be specific to THIS task, not generic (bad: "poor quality"; \
good: "uses only stock imagery with no custom illustrations")
- Anchors must be observable — describe what you would SEE, not what you would infer
- The gap between adjacent levels should be clear — a reader should be able to \
distinguish a 5 from a 7 by reading the anchors
- The 9 anchor should match your aspiration level for this dimension

**`verify_by` field**: Required whenever the criterion involves experiential correctness \
or craft that cannot be assessed by reading the source alone. Describe WHAT EVIDENCE to \
gather and WHAT TO CHECK — not which specific application or GUI to use. The evaluator \
will choose the best available tool (rendering, screenshots, browser automation, code \
execution, computer use, etc.) based on their capabilities.

State the full scope (all pages, all slides, full playback — not a sample) and list \
the specific defects or properties to look for.

- Rendered output (slides, pages, images): render ALL pages/slides to images and inspect \
  each for specific defects (e.g. text overflow, clipped elements, unreadable font sizes \
  below Npt, element collisions, blank content areas)
- Interactive output (web apps, forms): test all navigation links, form submissions, \
  button actions, and interactive state changes — list what each interaction should do
- Motion/animation: capture and review full animation playback — list expected motion \
  behavior and timing
- Audio/video: listen to or watch the complete output — list what to assess (clarity, \
  pacing, content accuracy)
- Executable code: run with representative inputs and check outputs against expected results

Do NOT name specific desktop applications (e.g. "open in PowerPoint", "view in Finder"). \
Do NOT describe GUI-specific actions (e.g. "hover to see cursor change", "right-click and \
select"). Instead describe the observable property to verify and let the evaluator choose \
the method.

Omit only when the criterion can be fully assessed by reading the output text or \
inspecting the source file structure.

Write the JSON to a file called `criteria.json` in your workspace.
Generate evaluation criteria now for the task above."""

    async def generate_criteria_via_subagent(
        self,
        task: str,
        agent_configs: list[dict[str, Any]],
        has_changedoc: bool,
        parent_workspace: str,
        log_directory: str | None,
        orchestrator_id: str,
        min_criteria: int = 4,
        max_criteria: int = 7,
        on_subagent_started: Callable | None = None,
        voting_sensitivity: str | None = None,
        voting_threshold: int | None = None,
        has_planning_spec_context: bool = False,
        fast_iteration_mode: bool = False,
    ) -> list[GeneratedCriterion]:
        """Generate criteria via a subagent run.

        Args:
            task: The user's task
            agent_configs: Parent agent configs to inherit models from
            has_changedoc: Whether changedoc mode is active
            parent_workspace: Path to parent workspace
            log_directory: Path to log directory
            orchestrator_id: Parent orchestrator ID
            min_criteria: Minimum criteria count
            max_criteria: Maximum criteria count
            on_subagent_started: Callback when subagent starts
            voting_sensitivity: Optional voting sensitivity to pass through to
                the pre-collaboration subagent coordination config.
            voting_threshold: Optional voting threshold to pass through to
                the pre-collaboration subagent coordination config.
            has_planning_spec_context: Whether planning/spec context is mounted
                and should be explicitly referenced by prompt guidance.

        Returns:
            List of GeneratedCriterion objects
        """
        logger.info("Generating evaluation criteria via subagent")

        # Build workspace
        criteria_workspace = os.path.join(parent_workspace, ".criteria_generation")
        try:
            os.makedirs(criteria_workspace, exist_ok=True)
            context_md = os.path.join(criteria_workspace, "CONTEXT.md")
            with open(context_md, "w", encoding="utf-8") as f:
                f.write(
                    "# Evaluation Criteria Generation\n\n" f"Task:\n{task}\n\n" "Goal: Generate task-specific evaluation criteria in criteria.json.\n",
                )
        except Exception as e:
            logger.warning(f"Failed to prepare criteria workspace: {e}")
            criteria_workspace = parent_workspace

        try:
            from massgen.subagent.manager import SubagentManager
            from massgen.subagent.models import SubagentOrchestratorConfig

            # Simplified agent configs (no tools, pure LLM reasoning)
            simplified = []
            for i, config in enumerate(agent_configs):
                backend = config.get("backend", {})
                backend_cfg: dict = {
                    "type": backend.get("type", "openai"),
                    "model": backend.get("model"),
                    "enable_mcp_command_line": False,
                    "enable_code_based_tools": False,
                    # Without command-line MCP execution, keep file-operation MCPs available.
                    "exclude_file_operation_mcps": False,
                }
                if backend.get("base_url"):
                    backend_cfg["base_url"] = backend["base_url"]
                simplified.append(
                    {
                        "id": config.get("id", f"criteria_agent_{i}"),
                        "backend": backend_cfg,
                    },
                )

            coordination = {
                "enable_subagents": False,
                "broadcast": False,
                "checklist_criteria_preset": "evaluation",
            }
            if voting_sensitivity:
                coordination["voting_sensitivity"] = voting_sensitivity
            if voting_threshold is not None:
                coordination["voting_threshold"] = voting_threshold
            if fast_iteration_mode:
                coordination["fast_iteration_mode"] = True

            subagent_config = SubagentOrchestratorConfig(
                enabled=True,
                agents=simplified,
                coordination=coordination,
            )
            from massgen.precollab_utils import build_subagent_parent_context_paths

            parent_context_paths = build_subagent_parent_context_paths(
                parent_workspace=parent_workspace,
                agent_configs=agent_configs,
            )

            manager = SubagentManager(
                parent_workspace=criteria_workspace,
                parent_agent_id="criteria_generator",
                orchestrator_id=orchestrator_id,
                parent_agent_configs=simplified,
                max_concurrent=1,
                default_timeout=300,
                subagent_orchestrator_config=subagent_config,
                log_directory=log_directory,
                parent_context_paths=parent_context_paths,
            )

            prompt = self._build_generation_prompt(
                task,
                has_changedoc,
                min_criteria,
                max_criteria,
                has_planning_spec_context=has_planning_spec_context,
            )

            def _status_callback(subagent_id: str) -> Any | None:
                try:
                    return manager.get_subagent_display_data(subagent_id)
                except Exception:
                    return None

            if on_subagent_started:
                try:
                    subagent_log_path = None
                    if log_directory:
                        subagent_log_path = str(
                            Path(log_directory) / "subagents" / "criteria_generation",
                        )
                    on_subagent_started(
                        "criteria_generation",
                        prompt,
                        300,
                        _status_callback,
                        subagent_log_path,
                    )
                except Exception:
                    pass

            result = await manager.spawn_subagent(
                task=prompt,
                subagent_id="criteria_generation",
                timeout_seconds=300,
            )

            # Try to find criteria.json in output
            if log_directory:
                criteria = self._find_criteria_json(
                    log_directory,
                    min_criteria,
                    max_criteria,
                )
                if criteria:
                    self.last_generation_source = "subagent"
                    logger.info(
                        f"Loaded {len(criteria)} criteria from criteria.json",
                    )
                    return criteria

            # Try parsing from answer text
            if result.answer:
                criteria, aspiration = _parse_criteria_response(
                    result.answer,
                    min_criteria,
                    max_criteria,
                )
                if criteria:
                    self.last_generation_source = "subagent"
                    self.last_aspiration = aspiration
                    logger.info(
                        f"Parsed {len(criteria)} criteria from answer (aspiration: {aspiration})",
                    )
                    return criteria

            logger.warning("No valid criteria output found, using defaults")
            self.last_generation_source = "fallback"
            return get_default_criteria(has_changedoc=has_changedoc)

        except Exception as e:
            logger.error(f"Failed to generate criteria via subagent: {e}")
            self.last_generation_source = "fallback"
            return get_default_criteria(has_changedoc=has_changedoc)

    def _find_criteria_json(
        self,
        log_directory: str,
        min_criteria: int,
        max_criteria: int,
    ) -> list[GeneratedCriterion] | None:
        """Search for criteria.json in subagent logs."""
        from massgen.precollab_utils import find_precollab_artifact

        criteria_file = find_precollab_artifact(
            log_directory,
            "criteria_generation",
            "criteria.json",
        )
        if criteria_file is None:
            return None

        try:
            content = criteria_file.read_text()
            criteria, aspiration = _parse_criteria_response(
                content,
                min_criteria,
                max_criteria,
            )
            if criteria:
                self.last_aspiration = aspiration
                return criteria
        except Exception as e:
            logger.debug(f"Failed to parse {criteria_file}: {e}")

        return None
