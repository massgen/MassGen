Project Development Tracks
===========================

Development tracks organize MassGen's work into focused areas of improvement. Each track has a dedicated lead and maintains both a short-term roadmap (for quick weekly updates) and detailed documentation (for architecture and long-term planning).

Track Structure
---------------

Each track maintains two key documents:

**Roadmap** (~50-80 lines)
  Quick updates for project leads. Update weekly in <5 minutes with:

  * Current sprint priorities (P0/P1/P2)
  * Upcoming milestones
  * Recent completions
  * Blocked items
  * Quick notes (this week, next week, decisions needed)

**Details** (~200-300 lines)
  Architecture and long-term planning. Update monthly or when major decisions are made with:

  * Architecture diagrams and structure
  * Long-term vision (3-6 months)
  * Medium-term goals
  * Success metrics
  * Dependencies
  * Decision log

Active Tracks
-------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 50

   * - Track
     - Lead
     - Status
     - Mission
   * - :doc:`multimodal/roadmap`
     - Eric
     - 🟢 Active
     - Enable vision, image generation, video, and audio capabilities across all backends
   * - :doc:`agentadapter-backends/roadmap`
     - Eric
     - 🟢 Active
     - Enable MassGen to work with any LLM provider through consistent, well-tested backend adapters
   * - :doc:`coding-agent/roadmap`
     - Nick
     - 🟢 Active
     - Enable MassGen agents to execute code, manipulate files, and interact with development tools safely
   * - :doc:`web-ui/roadmap`
     - Justin
     - 🟢 Active
     - Provide excellent visual interfaces for observing and interacting with multi-agent coordination
   * - :doc:`irreversible-actions/roadmap`
     - Franklin
     - 🟢 Active
     - Ensure MassGen agents operate safely, preventing irreversible or dangerous actions
   * - :doc:`memory/roadmap`
     - TBD
     - 🟢 Active
     - Enable MassGen agents to maintain context, remember conversations, and learn from past interactions

How to Update Your Track
-------------------------

**Weekly Updates** (Roadmap - <5 minutes)
  1. Move completed items from Current Sprint to Recent Completions
  2. Update Current Sprint with new priorities
  3. Update Quick Notes (This Week / Next Week)
  4. Update milestone table if status changed

**Monthly Updates** (Details - ~30 minutes)
  1. Review and update long-term vision if goals shifted
  2. Update success metrics with actual progress
  3. Add any major architectural decisions to decision log
  4. Update dependencies if new tracks or technologies involved

Contributing to a Track
------------------------

Each track welcomes community contributions! See the track's roadmap for:

* Current priorities and how to help
* Who to contact (track lead)
* Related GitHub labels
* Example configurations and code locations

.. toctree::
   :maxdepth: 3
   :hidden:
   :titlesonly:

   multimodal/index
   agentadapter-backends/index
   coding-agent/index
   web-ui/index
   irreversible-actions/index
   memory/index
