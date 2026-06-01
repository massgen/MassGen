"""Collaborator classes extracted from :mod:`massgen.orchestrator`.

Each collaborator owns a cohesive cluster of behavior that used to live as
methods on :class:`massgen.orchestrator.Orchestrator`. The orchestrator
composes these collaborators and keeps thin delegator methods so every
existing call site (internal and external) continues to work unchanged.
"""

from .active_coordination_cleanup import ActiveCoordinationCleanup
from .agent_orchestration_setup import AgentOrchestrationSetup
from .answer_limit_gate import AnswerLimitGate
from .answer_text_normalizer import AnswerTextNormalizer
from .bootstrap_criteria_engine import BootstrapCriteriaEngine
from .broadcast_tool_initializer import BroadcastToolInitializer
from .changedoc_coordinator import ChangedocCoordinator
from .checklist_gate_manager import ChecklistGateManager
from .checkpoint_coordinator import CheckpointCoordinator
from .context_path_write_tracker import ContextPathWriteTracker
from .criteria_evolution_runner import CriteriaEvolutionRunner
from .docker_diagnostics import DockerDiagnostics
from .dspy_paraphrase_coordinator import DspyParaphraseCoordinator
from .evaluation_criteria_generator import EvaluationCriteriaGeneratorCollaborator
from .evaluator_result_extractor import EvaluatorResultExtractor
from .fairness_gate import FairnessGate
from .final_presentation_runner import FinalPresentationRunner
from .final_result_reporter import FinalResultReporter
from .isolated_change_reviewer import IsolatedChangeReviewer
from .metrics_reporter import MetricsReporter
from .midstream_injection_hook_installer import MidStreamInjectionHookInstaller
from .nlip_routing_initializer import NlipRoutingInitializer
from .orchestrator_timeout_calculator import OrchestratorTimeoutCalculator
from .peer_answer_visibility_tracker import PeerAnswerVisibilityTracker
from .persona_injector import PersonaInjector
from .planning_tool_injector import PlanningToolInjector
from .post_evaluation_runner import PostEvaluationRunner
from .pre_collab_helpers import PreCollabHelpers
from .previous_log_restorer import PreviousLogRestorer
from .prompt_improver_collaborator import PromptImproverCollaborator
from .question_irreversibility_analyzer import QuestionIrreversibilityAnalyzer
from .rate_limit_controller import RateLimitController
from .round_evaluator_gate_config import RoundEvaluatorGateConfig
from .round_evaluator_runner import RoundEvaluatorRunner
from .round_start_context_queue import RoundStartContextQueue
from .run_mode_strategy_resolver import RunModeStrategyResolver
from .runtime_input_delivery import RuntimeInputDelivery
from .skills_config_validator import SkillsConfigValidator
from .snapshot_manager import SnapshotManager
from .subagent_lifecycle_coordinator import SubagentLifecycleCoordinator
from .subagent_tool_injector import SubagentToolInjector
from .trace_analyzer_runner import TraceAnalyzerRunner
from .workspace_lifecycle_manager import WorkspaceLifecycleManager
from .workspace_modal_presenter import WorkspaceModalPresenter

__all__ = [
    "ActiveCoordinationCleanup",
    "AgentOrchestrationSetup",
    "AnswerLimitGate",
    "ChangedocCoordinator",
    "ChecklistGateManager",
    "CheckpointCoordinator",
    "FairnessGate",
    "MetricsReporter",
    "PlanningToolInjector",
    "PostEvaluationRunner",
    "PreviousLogRestorer",
    "SkillsConfigValidator",
    "SnapshotManager",
    "SubagentLifecycleCoordinator",
    "SubagentToolInjector",
    "NlipRoutingInitializer",
    "RunModeStrategyResolver",
    "RuntimeInputDelivery",
    "ContextPathWriteTracker",
    "RoundEvaluatorGateConfig",
    "RoundEvaluatorRunner",
    "RoundStartContextQueue",
    "DockerDiagnostics",
    "DspyParaphraseCoordinator",
    "AnswerTextNormalizer",
    "OrchestratorTimeoutCalculator",
    "WorkspaceModalPresenter",
    "FinalPresentationRunner",
    "FinalResultReporter",
    "IsolatedChangeReviewer",
    "WorkspaceLifecycleManager",
    "BroadcastToolInitializer",
    "BootstrapCriteriaEngine",
    "PeerAnswerVisibilityTracker",
    "PersonaInjector",
    "MidStreamInjectionHookInstaller",
    "TraceAnalyzerRunner",
    "CriteriaEvolutionRunner",
    "EvaluationCriteriaGeneratorCollaborator",
    "EvaluatorResultExtractor",
    "QuestionIrreversibilityAnalyzer",
    "RateLimitController",
    "PromptImproverCollaborator",
    "PreCollabHelpers",
]
