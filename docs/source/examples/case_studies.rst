Case Studies
============

Real-world MassGen case studies demonstrating multi-agent collaboration on complex tasks.

.. note::

   These case studies are based on actual MassGen sessions with real session logs and outcomes.

Overview
--------

Each case study includes:

* **Problem description** - The task or question given to agents
* **Configuration used** - YAML config and CLI command
* **Agent collaboration** - How agents worked together
* **Final outcome** - Results and quality assessment
* **Session logs** - Actual coordination history and voting patterns

Contributing Your Own
----------------------

.. toctree::
   :maxdepth: 1
   :titlesonly:

   case_studies/case-study-template

Release Features
----------------

Feature case studies organized by release version (newest first).

.. toctree::
   :maxdepth: 1
   :titlesonly:

   case_studies/multi-turn-persistent-memory
   case_studies/multimodal-case-study-video-analysis
   case_studies/github-issue-market-analysis
   case_studies/universal-code-execution-mcp
   case_studies/mcp-planning-mode
   case_studies/ag2-framework-integration
   case_studies/multi-turn-filesystem-support
   case_studies/user-context-path-support-with-copy-mcp
   case_studies/unified-filesystem-mcp-integration
   case_studies/gemini-mcp-notion-integration
   case_studies/claude-code-workspace-management
   case_studies/SuperIntelligence
   case_studies/fibonacci_number_algorithms
   case_studies/berkeley-conference-talks
   case_studies/diverse_ai_news
   case_studies/grok_hle_cost
   case_studies/stockholm_travel_guide
   case_studies/collaborative_creative_writing
   case_studies/imo_2025_winner

Contributing Case Studies
-------------------------

We welcome community contributions! To create your own case study:

1. Run MassGen with interesting tasks
2. Save session logs and outputs
3. Follow the :doc:`case study template <case_studies/case-study-template>`
4. Submit a pull request

See :doc:`../user_guide/logging` for details on accessing session logs and the `Contributing Guidelines <https://github.com/Leezekun/MassGen/blob/main/CONTRIBUTING.md>`_ for submission instructions.


See Also
--------

* :doc:`../user_guide/multi_turn_mode` - Interactive sessions
* :doc:`../user_guide/logging` - Understanding session logs
* :doc:`../user_guide/mcp_integration` - External tool integration
