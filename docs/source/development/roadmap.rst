MassGen Roadmap
===============

.. note::

   **Primary Source:** This page includes content from the root `ROADMAP.md <https://github.com/Leezekun/MassGen/blob/main/ROADMAP.md>`_ file, which is the authoritative source for all development plans.

MassGen's roadmap is organized by timeframe to provide clarity on priorities:

- **Short-Term** (2-4 weeks): Critical fixes and required features
- **Medium-Term** (1-2 months): Optional enhancements
- **Long-Term** (3-6 months): Strategic vision and enterprise features

Quick Overview
--------------

**Current Version:** v0.0.29

**Next Release:** v0.0.30

**Focus:** Backend stability and multimodal feature parity

Short-Term Priorities (v0.0.30)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Backend Issues & Organization** (REQUIRED)
   - Fix Claude Code backend reliability
   - Improve configuration discoverability
   - Enhance error handling

2. **Multimodal Support Extension** (REQUIRED)
   - Image support for Claude backend
   - Image support for Chat Completions backend
   - Cross-provider compatibility

Medium-Term Goals
~~~~~~~~~~~~~~~~~

3. **AG2 Group Chat Integration** (OPTIONAL)
   - Multi-agent group conversations
   - Group chat orchestration

4. **Tool Registration Refactoring** (OPTIONAL)
   - Simplified tool creation
   - Plugin-based extensions

5. **Context Window Management**
   - Session compression
   - Enhanced summarization

Long-Term Vision
~~~~~~~~~~~~~~~~

- Visual Workflow Designer
- Enterprise Features (RBAC, audit logs, analytics)
- Additional Framework Adapters (LangChain, CrewAI)
- Complete Multimodal Support (audio, video)
- Advanced Coding Agent
- Real-Time Collaboration
- Distributed Orchestration

---

Full Roadmap
------------

.. include:: ../../../ROADMAP.md
   :parser: myst_parser.sphinx_

Track-Specific Roadmaps
-----------------------

For detailed feature-specific plans, see the track roadmaps (available in the repository):

- Multimodal Track (``docs/source/tracks/multimodal/roadmap.md``) - Multimodal capabilities
- Memory Track (``docs/source/tracks/memory/roadmap.md``) - Memory and context management
- Coding Agent Track (``docs/source/tracks/coding-agent/roadmap.md``) - Coding assistance features
- Web UI Track (``docs/source/tracks/web-ui/roadmap.md``) - Web interface development
- AgentAdapter Backends Track (``docs/source/tracks/agentadapter-backends/roadmap.md``) - Framework integrations
- Irreversible Actions Track (``docs/source/tracks/irreversible-actions/roadmap.md``) - Safety mechanisms

Contributing
------------

Want to contribute to the roadmap? Here's how:

**For v0.0.30 (Short-Term):**

1. Check GitHub issues tagged with ``v0.0.30`` milestone
2. Focus on REQUIRED tasks first (backend fixes, multimodal support)
3. See :doc:`contributing` for development setup

**For Future Releases:**

1. Open an issue to discuss your proposal
2. Consider writing an RFC for large features (see :doc:`../rfcs/index`)
3. Follow the case-driven development methodology (see ADR-0004)

GitHub Integration
------------------

* `GitHub Issues <https://github.com/Leezekun/MassGen/issues>`_ - Report bugs and request features
* `Project Boards <https://github.com/Leezekun/MassGen/projects>`_ - Track progress
* `Milestones <https://github.com/Leezekun/MassGen/milestones>`_ - View release planning

See Also
--------

* :doc:`contributing` - Contribution guidelines with documentation requirements
* :doc:`../decisions/index` - Architecture decisions (ADRs)
* :doc:`../rfcs/index` - Feature proposals (RFCs)
* :doc:`../changelog` - Complete release history

---

*Last synced with ROADMAP.md: October 2025*
