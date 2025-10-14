Case Studies
============

Real-world MassGen case studies demonstrating multi-agent collaboration on complex tasks.

.. note::

   These case studies are based on actual MassGen sessions with real session logs and outcomes.
   This page is auto-generated from the `docs/case_studies/ directory <https://github.com/Leezekun/MassGen/tree/main/docs/case_studies>`_.

Overview
--------

Each case study includes:

* **Problem description** - The task or question given to agents
* **Configuration used** - YAML config and CLI command
* **Agent collaboration** - How agents worked together
* **Final outcome** - Results and quality assessment
* **Session logs** - Actual coordination history and voting patterns

**Total Case Studies**: 13

Research and Analysis
---------------------

MassGen  Berkeley Agentic AI Summit Summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `berkeley-conference-talks.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/berkeley-conference-talks.md>`_

MassGen  AI News Synthesis - Cross-Verification and Content Aggregation Excellence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `diverse_ai_news.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/diverse_ai_news.md>`_

MassGen  Grok-4 HLE Benchmark Cost Analysis - Unanimous Expert Consensus
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `grok_hle_cost.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/grok_hle_cost.md>`_


Travel and Recommendations
--------------------------

MassGen  Stockholm Travel Guide - Extended Intelligence Sharing and Comprehensive Convergence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `stockholm_travel_guide.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/stockholm_travel_guide.md>`_


Creative Writing
----------------

MassGen  Collaborative Creative Writing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `collaborative_creative_writing.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/collaborative_creative_writing.md>`_


Technical Analysis
------------------

MassGen  Comprehensive Algorithm Enumeration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `fibonacci_number_algorithms.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/fibonacci_number_algorithms.md>`_


Release Features
----------------

Feature case studies organized by release version (newest first).

MassGen v0.0.25: Multi-Turn Filesystem Support with Persistent Context
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `multi-turn-filesystem-support.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/multi-turn-filesystem-support.md>`_

MassGen v0.0.16: Unified Filesystem Support with MCP Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Configuration:**

.. code-block:: bash

   agents:
     - id: "gemini_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-pro"

     - id: "claude_code"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-20250514"
         cwd: "claude_code_workspace"

   orchestrator:
       snapshot_storage: "snapshots"  # Directory to store workspace snapshots
       agent_temporary_workspace: "temp_workspaces"  # Directory for temporary agent workspaces

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Case Study:** `unified-filesystem-mcp-integration.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/unified-filesystem-mcp-integration.md>`_

MassGen v0.0.15: Gemini MCP Notion Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `gemini-mcp-notion-integration.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/gemini-mcp-notion-integration.md>`_

MassGen v0.0.12-0.0.14: Enhanced Logging and Workspace Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `claude-code-workspace-management.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/claude-code-workspace-management.md>`_

MassGen  Advanced Filesystem with User Context Path Support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `user-context-path-support-with-copy-mcp.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/user-context-path-support-with-copy-mcp.md>`_


Problem Solving
---------------

MassGen  Super Intelligence Approaches
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `SuperIntelligence.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/SuperIntelligence.md>`_

MassGen  IMO 2025 AI Winners
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Case Study:** `imo_2025_winner.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/imo_2025_winner.md>`_


Running Your Own Case Studies
------------------------------

To create your own case studies:

1. Run MassGen with interesting tasks
2. Save session logs and outputs
3. Use the `case-study-template.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/case-study-template.md>`_
4. Submit a pull request to ``docs/case_studies/``

See :doc:`../user_guide/logging` for details on accessing session logs.

Contributing
------------

We welcome new case studies! To contribute:

* Follow the case study template
* Include configuration and session logs
* Provide clear highlights and insights
* See `Contributing Guidelines <https://github.com/Leezekun/MassGen/blob/main/CONTRIBUTING.md>`_

See Also
--------

* :doc:`../user_guide/multi_turn_mode` - Interactive sessions
* :doc:`../user_guide/logging` - Understanding session logs
* :doc:`../user_guide/mcp_integration` - External tool integration
