Agent Workspaces and Code Isolation
====================================

How agents interact with your project code during MassGen coordination.

write_mode Configuration
-------------------------

The ``write_mode`` option controls how agents interact with your project files::

    orchestrator:
      coordination:
        write_mode: auto   # auto | worktree | isolated | legacy

.. list-table::
   :header-rows: 1

   * - Mode
     - Git repo
     - Non-git directory
   * - ``auto`` (recommended)
     - Git worktree per round
     - Shadow copy with git init
   * - ``worktree``
     - Git worktree per round
     - Error (falls back to shadow)
   * - ``isolated``
     - Shadow copy
     - Shadow copy
   * - ``legacy``
     - Direct writes (no isolation)
     - Direct writes

Per-Round Worktrees
--------------------

Each coordination round, every agent gets a fresh git checkout of your project.
Agents have full read/write access to experiment with the code. Changes during
coordination rounds are tracked on anonymous git branches but not applied to
your project.

Only the final presentation winner's changes go through a review modal
where you approve which files to apply.

**Branch lifecycle:**

- Each agent has exactly one branch alive at a time
- Old branches are deleted when a new round starts for that agent
- Branch names use random suffixes (no agent IDs or round numbers)
- Branches are visible to other agents via ``git branch`` / ``git diff``

Scratch Space
--------------

Inside each worktree, ``.massgen_scratch/`` provides a git-excluded directory
for experiments, evaluation scripts, and notes. Scratch files can import from
the project naturally since they live inside the checkout.

Scratch is archived to ``.scratch_archive/`` in the workspace between rounds,
so it persists in workspace snapshots shared with other agents.

**Key properties:**

- Git-excluded: invisible to ``git status`` and review modals
- Archived between rounds: previous scratch available in workspace
- Shared via snapshots: other agents can see your scratch archive

Agent Statelessness
--------------------

Agents are stateless and anonymous across rounds. Each round is a fresh
invocation with no memory of previous rounds. All cross-agent information
is presented anonymously.

This means:

- Agents don't know which agent they are
- System prompts and branch names don't reveal identity
- Cross-agent answers and workspaces are presented anonymously
- Each round starts fresh from HEAD (no accumulated state): the working tree
  is wiped clean between rounds (only ``.git/`` survives), after the round's
  work is auto-committed to its branch. An agent does not inherit its own
  prior round's leftover files.

.. note::

   The live ``…/agent_<id>/workspace`` symlink reflects only the *current*
   round's in-progress state — not where finished deliverables accumulate.
   A round's output lives in its git branch, in the per-round log snapshots
   (``…/agent_<id>/<timestamp>/workspace/`` and ``turn_*/final/…``), and in
   the shared ``temp_workspaces/`` copies.

Migrating from use_two_tier_workspace
---------------------------------------

``use_two_tier_workspace`` is deprecated. Replace::

    # Old
    coordination:
      use_two_tier_workspace: true

    # New
    coordination:
      write_mode: auto

The new ``write_mode: auto`` provides:

- Git worktree isolation (safe experimentation)
- In-worktree scratch space (replaces ``scratch/`` directory)
- Branch-based cross-agent visibility
- Review modal for final presentation changes
