=================================================
MassGen: Multi-Agent Scaling System for GenAI
=================================================

.. raw:: html

   <img src="_static/images/logo.png" width="360" alt="MassGen Logo" class="theme-image-light">
   <img src="_static/images/logo-dark.png" width="360" alt="MassGen Logo" class="theme-image-dark">

.. raw:: html

   <p align="center">
     <a href="https://pypi.org/project/massgen/">
       <img src="https://img.shields.io/pypi/v/massgen?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9" alt="PyPI">
     </a>
     <a href="https://github.com/Leezekun/MassGen">
       <img src="https://img.shields.io/github/stars/Leezekun/MassGen?style=flat-square&logo=github&color=181717&logoColor=white" alt="GitHub Stars">
     </a>
     <a href="https://www.python.org/downloads/">
       <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
     </a>
     <a href="https://github.com/Leezekun/MassGen/blob/main/LICENSE">
       <img src="https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square" alt="License">
     </a>
   </p>

   <p align="center">
     <a href="https://x.massgen.ai">
       <img src="https://img.shields.io/badge/FOLLOW%20ON%20X-000000?style=for-the-badge&logo=x&logoColor=white" alt="Follow on X">
     </a>
     <a href="https://www.linkedin.com/company/massgen-ai">
       <img src="https://img.shields.io/badge/FOLLOW%20ON%20LINKEDIN-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="Follow on LinkedIn">
     </a>
     <a href="https://discord.massgen.ai">
       <img src="https://img.shields.io/badge/JOIN%20OUR%20DISCORD-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join our Discord">
     </a>
   </p>

|

.. raw:: html

   <a href="https://www.youtube.com/watch?v=Dp2oldJJImw" style="display: block; text-align: center;">
     <img src="_static/images/readme.gif" width="800" alt="MassGen Demo - Multi-agent collaboration in action (4x speed)" class="theme-image-light">
     <img src="_static/images/readme.gif" width="800" alt="MassGen Demo - Multi-agent collaboration in action (4x speed)" class="theme-image-dark">
   </a>

What is MassGen?
----------------

MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns a task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution to deliver a comprehensive and high-quality result.

**How It Works:**

* **Work in Parallel** - Multiple agents tackle the problem simultaneously, each bringing unique capabilities
* **See Recent Answers** - At each step, agents view the most recent answers from other agents
* **Decide Next Action** - Each agent chooses to provide a new answer or vote for an existing answer
* **Share Workspaces** - When agents provide answers, their workspace is captured so others can review their work
* **Natural Consensus** - Coordination continues until all agents vote, then the agent with most votes presents the final answer

MassGen is a cutting-edge multi-agent framework that coordinates AI agents through **redundancy and iterative refinement**. Agents tackle the full problem, observe and build on each other's work across cycles of refinement and restarts, then vote — and the best collectively validated answer wins. This lays the groundwork for principled multi-agent scaling and self-improvement.

.. raw:: html

   <div style="text-align: center; margin: 20px 0;">
     <a href="case_studies/index.html" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); transition: transform 0.2s, box-shadow 0.2s;">
       🎨 View Interactive Case Studies →
     </a>
   </div>

See visual comparisons between MassGen and single-agent solutions, highlighting how MassGen unifies different agentic approaches for better outcomes.

.. raw:: html

   <div style="text-align: center; margin: 20px 0;">
     <a href="user_guide/skills.html" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: #1a1a2e; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 4px 15px rgba(67, 233, 123, 0.4); transition: transform 0.2s, box-shadow 0.2s;">
       &#129520; Install the MassGen Skill for Your AI Agent &rarr;
     </a>
   </div>

Use MassGen from Claude Code, Codex, Copilot, Cursor, and other AI coding agents.

.. note::

   **For AI agents and crawlers:** This site publishes a curated `llms.txt <llms.txt>`_ index following the `llmstxt.org spec <https://llmstxt.org>`_, plus a concatenated `llms-full.txt <llms-full.txt>`_ dump of the user guide and reference docs.


How Does MassGen Compare?
-------------------------

MassGen sits in a different design space than typical multi-agent frameworks. The core differentiator across the board is *parallel attempts with voting and consensus* — agents tackle the same task in parallel, observe each other, and converge on a winner — backed by tools, code execution, filesystem integration, and active development.

- :doc:`MassGen vs LLM Council <reference/comparisons>` — dynamic voting / consensus vs a fixed 3-stage pipeline (responses → ranking → chairman synthesis).
- :doc:`MassGen vs CrewAI <reference/comparisons/crewai>` — parallel refinement on one task vs role-based decomposition into sub-tasks.
- :doc:`MassGen vs LangGraph <reference/comparisons/langgraph>` — a pre-built parallel + voting protocol vs a low-level graph runtime you author yourself.
- :doc:`MassGen vs AutoGen / AG2 <reference/comparisons/autogen>` — parallel attempts with collective validation vs conversation-based multi-agent message passing.


Quick Start
-----------

.. tabs::

   .. tab:: CLI

      .. code-block:: bash

         pip install uv        # if needed
         uv venv && source .venv/bin/activate
         uv pip install massgen
         uv run massgen        # Setup wizard, then ask your first question

      Rich terminal UI with real-time streaming, multi-turn conversations, and YAML configuration.

   .. tab:: WebUI

      .. code-block:: bash

         pip install uv        # if needed
         uv venv && source .venv/bin/activate
         uv pip install massgen
         uv run massgen --web  # Open http://localhost:8000

      Browser-based UI with real-time agent streaming, vote visualization, and workspace browsing.

   .. tab:: LiteLLM

      .. code-block:: python

         from dotenv import load_dotenv
         load_dotenv()  # Load OPENROUTER_API_KEY from .env

         import litellm
         from massgen import register_with_litellm

         register_with_litellm()
         response = litellm.completion(
             model="massgen/build",
             messages=[{"role": "user", "content": "Your question"}],
             optional_params={"models": ["openrouter/openai/gpt-5", "openrouter/anthropic/claude-sonnet-4.5"]}
         )
         print(response.choices[0].message.content)

      Standard OpenAI-compatible interface for seamless integration with existing applications.

:doc:`quickstart/installation` · :doc:`quickstart/running-massgen` · :doc:`quickstart/configuration`

Video Tutorials
---------------

.. raw:: html

   <div style="text-align: center; margin: 20px 0;">
     <a href="https://www.youtube.com/watch?v=JMCnQL615Ek" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 10px 20px; background: #ff0000; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 1em; box-shadow: 0 2px 10px rgba(255, 0, 0, 0.3);">
       ▶️ Getting Started
     </a>
   </div>

Learn how to install, configure, and run your first multi-agent collaboration with MassGen.

.. raw:: html

   <div style="text-align: center; margin: 20px 0;">
     <a href="https://www.youtube.com/watch?v=Dfz3D460EDs" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 10px 20px; background: #ff0000; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 1em; box-shadow: 0 2px 10px rgba(255, 0, 0, 0.3);">
       ▶️ Develop on MassGen
     </a>
   </div>

Explore how to build custom agents and tools with MassGen.

Key Features
------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🤝 Cross-Model Synergy

      Use Claude, Gemini, GPT, Grok together - each agent can use a different model.

   .. grid-item-card:: ⚡ Parallel Coordination

      Multiple agents work simultaneously with voting and consensus detection.

   .. grid-item-card:: 🛠️ Tools & MCP

      Model Context Protocol for web search, code execution, file operations, and custom tools.

   .. grid-item-card:: 🐍 Python & LiteLLM

      Full async Python API and LiteLLM integration for seamless application embedding.

   .. grid-item-card:: 📊 Live Visualization

      Real-time terminal display showing agents' working processes and coordination.

   .. grid-item-card:: 💬 Multi-Turn Sessions

      Interactive conversations with context preservation across turns.

   .. grid-item-card:: 🔗 Framework Interoperability

      Integrate external frameworks (AG2, LangGraph, AgentScope, OpenAI, SmolAgent) as tools.

   .. grid-item-card:: 📁 Project Integration

      Work directly with your codebase using context paths with granular read/write permissions.

Recent Releases
---------------

**v0.1.96 (June 10, 2026)** - OS-Level Agent Sandboxing

Adds a real OS-level execution sandbox for agents via Anthropic's `sandbox-runtime <https://github.com/anthropic-experimental/sandbox-runtime>`_ (``srt``: bubblewrap on Linux, Seatbelt on macOS) and hardens the application-layer permission hook against file-tool escapes. Defense in depth by design: the OS layer (``SrtManager``) and the app layer (``PathPermissionManager``) derive from the *same* path policy and both stay active — SRT closes the shell escape hatch, the hardened hook closes file-tool escapes. One-knob opt-in (``command_line_execution_mode: srt``), default-off. Read confinement defaults to ``confined`` (denies ``$HOME``, allows workspace + context), network is deny-all by default, native-sandbox backends (Codex ``--full-auto``, Claude Code) degrade ``srt``→``local``, and subagents inherit the parent's SRT settings.

**v0.1.95 (June 8, 2026)** - Steering Improvements

Extends mid-stream injection into a programmatic, headless capability and upgrades it to true interrupt-and-resume for the CLI backends. A file inbox (``--inbox-dir``) lets ``--automation`` and any UI-less caller drop human guidance into a streaming agent through the same chokepoint the TUI/WebUI use; Codex and Antigravity now interrupt the in-flight turn and resume (``codex exec resume`` / ``agy --continue``) instead of waiting for a round boundary. Adds MCP-server-hook payload IPC for Antigravity (codex parity), wires the Antigravity ``--model`` flag, and fixes ``--inbox-dir`` for resumed sessions plus ``expires_at``-guarded steering carryforward.

**v0.1.94 (June 5, 2026)** - Parallelism Hardening (Engineering Health)

Strengthens the orchestrator's parallel execution: moves the snapshot copy off the event loop so agents keep streaming concurrently — backed by immutable versioned snapshots that keep the off-loop copy safe — and closes latent concurrency races (lost peer-answer revisions, lost background-subagent results, leaked trace tasks, cancel-without-await teardown). Also unifies the mid-stream injection paths and surfaces worktree-isolation degradation. No per-backend functionality changes.

**v0.1.93 (June 3, 2026)** - CLI Package Decomposition & Pydantic Config Migration

Splits the monolithic ``cli.py`` into a focused ``massgen/cli/`` package, migrates the configuration classes to pydantic dataclasses with ``Literal``-typed modes validated at construction, removes ~8.7k lines of dead legacy code, and hardens the test-signal and type-checking tooling (coverage gate, no-assert guard, ``uv.lock`` enforcement, and an incremental mypy ratchet). Internal-quality release with no runtime behavior changes.

**v0.1.92 (June 1, 2026)** - Orchestrator Collaborator Refactor & Parallel Search MCP

Refactors the monolithic orchestrator into 49 lazy collaborators with stable delegator call sites, splits focused Textual display helpers into sibling modules, adds characterization coverage for extraction seams, and introduces a Parallel Web Search MCP registry entry plus runnable example config.

**v0.1.91 (May 27, 2026)** - Config Reliability & Hook Safety

Hardens release-critical YAML configuration paths with centralized coordination, timeout, and orchestrator runtime parsing; strict unknown-key validation for typo detection; checklist runtime control wiring; and safer Gemini/Codex native hook path permission precedence.

**v0.1.90 (May 25, 2026)** - Discriminative Criteria Refinements & Checklist Calibration

Improves checklist-gated refinement quality with discriminative-power pruning, per-criterion feedback carried into the next round, position-bias counterbalancing, deterministic tie-breaking, a unified checklist gate on a single 0-10 scale, shared score parsing utilities, and fast-iteration config updates.

**v0.1.89 (May 22, 2026)** - Antigravity CLI Full Integration & Hardening

Completes the follow-up Antigravity integration pass with workflow-mode parity, early auth and binary health checks, reliable workspace writes via ``--add-dir``, workspace-root ``.antigravitycli/`` anchoring, standalone ``hooks.json`` support with ``enableJsonHooks``, and prompt guardrails that hide subagent affordances when subagents are disabled.

**v0.1.88 (May 20, 2026)** - Antigravity CLI Backend

New ``antigravity_cli`` backend wraps Google's ``agy`` binary as a MassGen backend, with workspace-local ``.antigravity/`` config isolation, Antigravity MCP config translation, native hook adapter support, and runnable configs for single-agent Antigravity and mixed Gemini API + Antigravity fast-iteration runs.

**v0.1.87 (May 15, 2026)** - Documentation: Framework Comparisons & ``llms.txt``

Three new "MassGen vs ..." comparison pages (CrewAI, LangGraph, AutoGen/AG2), a curated ``llms.txt`` index plus a full-corpus ``llms-full.txt`` dump for AI agents and crawlers (per `llmstxt.org <https://llmstxt.org>`_ spec), and a one-line ``refine=False`` fix for the ``bootstrap_subagent`` discriminator.

**v0.1.86 (May 13, 2026)** - ``bootstrap_subagent`` Discriminator + Codex MCP Approval Fix

The critic-driven criteria path is now functional: ``orchestrator.coordination.criteria_mode: bootstrap_subagent`` runs an in-process LLM discriminator between rounds, merges proposed criteria into the accumulator, and augments the next round's checklist automatically. Codex MCP tool calls under ``codex exec`` now get the non-interactive approval bypasses needed for external workflow tools.

**v0.1.85 (May 11, 2026)** - Discriminative Criteria Emergence (``criteria_mode``)

New ``orchestrator.coordination.criteria_mode`` option lets evaluation criteria emerge from observed gaps across rounds instead of being pre-authored. The ``bootstrap_inline`` variant is fully functional on all backends with checklist tool support — agents emit ``proposed_criteria`` alongside ``submit_checklist``, the accumulator dedupes/caps, and the next round's checklist is augmented automatically.

:doc:`Full changelog → <changelog>`

Supported Models
----------------

**Claude** (Anthropic) · **Gemini** (Google) · **GPT** (OpenAI) · **Grok** (xAI) · **Azure OpenAI** · **Groq** · **Together** · **LM Studio** · :doc:`and more... <reference/supported_models>`

Documentation
-------------

.. grid:: 3
   :gutter: 2

   .. grid-item-card:: 🚀 Getting Started

      * :doc:`quickstart/installation`
      * :doc:`quickstart/running-massgen`
      * :doc:`quickstart/configuration`

   .. grid-item-card:: 📖 User Guide

      * :doc:`user_guide/concepts`
      * :doc:`user_guide/skills`
      * :doc:`user_guide/webui`
      * :doc:`user_guide/tools/index`
      * :doc:`user_guide/integration/index`

   .. grid-item-card:: 📚 Reference

      * :doc:`reference/cli`
      * :doc:`reference/python_api`
      * :doc:`reference/yaml_schema`
      * :doc:`examples/basic_examples`

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Getting Started

   quickstart/installation
   quickstart/running-massgen
   quickstart/configuration

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: User Guide

   user_guide/concepts
   user_guide/skills
   user_guide/task_planning
   user_guide/backends
   user_guide/webui
   user_guide/tools/index
   user_guide/files/index
   user_guide/sessions/index
   user_guide/integration/index
   user_guide/advanced/index
   user_guide/validating_configs
   user_guide/logging

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Reference

   reference/python_api
   reference/cli
   reference/yaml_schema
   reference/mcp_server_registry
   reference/configuration_examples
   reference/timeouts
   reference/supported_models
   reference/comparisons
   glossary

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Examples

   examples/case_studies
   examples/basic_examples
   examples/advanced_patterns
   examples/available_configs

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Development

   development/contributing
   development/writing_configs
   development/architecture
   development/roadmap
   changelog
   api/index
