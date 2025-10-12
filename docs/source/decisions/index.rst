Architecture Decision Records
============================

An Architecture Decision Record (ADR) captures an important architectural decision made along with its context and consequences.

Why ADRs?
---------

* **Context preservation**: Understand why decisions were made 6 months from now
* **Avoid re-litigation**: Don't endlessly debate already-decided questions
* **Onboarding**: New contributors can quickly understand project rationale
* **Transparency**: All stakeholders see the decision-making process

How to Write an ADR
-------------------

Use the `template <../_templates/adr-template.md>`_ to document significant technical decisions:

* Framework choices
* Architecture patterns
* Data format decisions
* API design approaches
* Testing strategies

Status Definitions
------------------

* **Proposed**: Under discussion, not yet decided
* **Accepted**: Decision made and being implemented
* **Rejected**: Decision was considered but not chosen
* **Superseded**: Replaced by a later decision
* **Deprecated**: No longer relevant

All Decision Records
--------------------

Active Decisions
~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 10 40 15 35

   * - ADR
     - Title
     - Date
     - Summary
   * - :doc:`0001-use-sphinx`
     - Use Sphinx for project documentation
     - 2024-10
     - Sphinx chosen for documentation system
   * - :doc:`0002-pytorch-framework`
     - Use PyTorch as ML framework
     - 2024-06
     - PyTorch selected over TensorFlow
   * - :doc:`0003-multi-agent-architecture`
     - Multi-agent collaborative architecture
     - 2024-06
     - Core architecture decision for agent collaboration
   * - :doc:`0004-case-driven-development`
     - Case-driven development methodology
     - 2024-06
     - Each release tied to case study demonstrating improvements

Proposed
~~~~~~~~

None currently

Superseded/Deprecated
~~~~~~~~~~~~~~~~~~~~~

None yet

.. toctree::
   :maxdepth: 1
   :caption: Architecture Decision Records
   :hidden:

   0001-use-sphinx
   0002-pytorch-framework
   0003-multi-agent-architecture
   0004-case-driven-development
