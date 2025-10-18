Do you have advice for managing a large open source coding project? Are there certain ways to organize roadmaps, manage indpeendnet dev temas, etc. Both advice from you and the web? Also, from a broad business side of things too: people that are especially good successful bosses with good feedback? e.g., jensen huang

I'd be happy to help you research best practices for managing large open source projects, along with insights from successful leaders like Jensen Huang. Before I dive into the research, let me clarify a few things to make sure I give you the most useful information:

Project scale and maturity: Are you working on an established project with existing contributors, or starting something new? And roughly how many active contributors are involved?
Your role: Are you the primary maintainer/BDFL, part of a core team, or managing this from a company/foundation perspective?
Specific challenges: Are there particular pain points you're facing right now (e.g., contributor retention, decision-making bottlenecks, release management, community conflicts)?
I am working on https://github.com/Leezekun/MassGen. we have about 3-5 separate subdirections we're going into, as well as general goals. i am a co-leader for development, managing everyone. The pain points right now are just a bit lack of communication -- id like places where people can give specific updates on their side. right now we have a google doc specifying the current release and some design docs, but everythign is just still messy

Perfect, this gives me great context! I'll do some comprehensive research on managing open source projects like yours, including best practices for communication structures, roadmap organization, and leadership insights from people like Jensen Huang.

Let me dig into:

Effective communication platforms and workflows for distributed open source teams
How successful projects manage multiple development tracks
Roadmap and release planning strategies
Leadership principles from Jensen Huang and other successful technical leaders
Specific tools and patterns for keeping messy projects organized
Starting my research now!


Open source project management
favicon
favicon
favicon
Research complete
•
784 sources
•
1h 42m
Managing Multi-Track Open Source Projects: A Practical Guide for MassGen
Document
Right now, we have 30min daily sync meetings where we go around all devs. We also release 3x a week, often with as little as one new feature. These are fixed by my boss.

I'm thinking we can be more centered around our documentation: we are in the middle of developing documentation like MkDocs, which I think we can build our development around? Can the ADR be done here? And i think we can also do GitHub projects, so more information on how to set that up would be great. But I am wondering: where does each team keep its current progress and goals?

Looking at your constraints, I can see some tensions between what your boss has mandated (daily 30min syncs, 3x weekly releases) and what would typically work best for a multi-track project. Let me address your situation practically and answer your specific questions.

The reality check on your current setup
Daily 30-minute syncs going around all devs is a red flag. If you have 5 developers, that's 6 minutes per person including transitions—barely enough to say anything meaningful. If you have more people, it's even worse. This is exactly the anti-pattern that successful projects avoid. However, since your boss has fixed this, you need to work within it for now.

Three releases per week with single features is extremely high-frequency and likely creates more overhead than value unless you have full automation. Most successful projects release every 4-8 weeks for exactly this reason—releases require coordination, testing, documentation updates, and communication. But again, if this is mandated, you'll need to adapt.

Here's how to make the best of your constraints while moving toward better practices:

Restructuring your daily syncs to be productive
Since you're stuck with the 30-minute daily meeting, restructure it dramatically:

Option 1: Async-first daily standup (recommended)

Install a standup bot like Geekbot in Slack/Discord
Each morning at 9am (or whenever), bot asks three questions: "What did you ship yesterday?" "What are you working on today?" "Any blockers?"
Everyone responds in writing (takes 2-3 minutes)
All responses visible in dedicated channel—everyone can read async
Use the 30-minute meeting ONLY for blockers and decisions that need synchronous discussion
If there are no blockers, cancel that day's meeting
This respects your boss's mandate while making it actually useful. The written responses create a permanent record (unlike verbal updates that vanish). Most days you'll have no blockers and can skip the meeting.

Option 2: Rotate focus in the daily sync If your boss insists on the full meeting every day, rotate which track gets deep dive:

Monday: Data Infrastructure track deep dive (15 min), others quick updates (3 min total)
Tuesday: Model Development track deep dive, others quick updates
Wednesday: Generation Pipeline track deep dive, others quick updates
Thursday: Cross-track dependencies and blockers
Friday: Demo day—someone shows working progress for 15 min, quick retro on the week
This way each track gets meaningful discussion time weekly instead of superficial daily updates.

Making 3x weekly releases work
Three releases weekly is actually manageable IF you automate everything and make releases boring:

Automate the entire release process:

yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags:
      - 'v*'
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build package
        run: python -m build
      - name: Run tests
        run: pytest
      - name: Generate changelog
        run: git-cliff --latest > CHANGELOG.md
      - name: Create GitHub Release
        uses: actions/create-release@v1
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          body_path: CHANGELOG.md
      - name: Publish to PyPI
        run: twine upload dist/*
Use semantic versioning for your 3x weekly cadence:

Major releases (v2.0.0): Breaking changes, rare
Minor releases (v2.1.0): New features, maybe weekly
Patch releases (v2.1.1, v2.1.2): Bug fixes, could be 3x weekly
The key: make releases automatic and low-overhead. When someone merges a PR tagged with "ready-for-release", it automatically creates a release that night. No manual coordination needed.

Centering development around MkDocs documentation
Yes, absolutely center your workflow around documentation! This is exactly what GitLab does and it works brilliantly. Here's the structure:

Your MkDocs setup should become your single source of truth
docs/
├── index.md                          # Project overview, getting started
├── architecture/
│   ├── overview.md                   # System architecture diagram
│   ├── data-pipeline.md              # Data Infrastructure track's domain
│   ├── models.md                     # Model Development track's domain
│   ├── generation.md                 # Generation Pipeline track's domain
│   └── evaluation.md                 # Evaluation track's domain
├── decisions/                        # ADRs live here
│   ├── index.md                      # List of all ADRs with status
│   ├── 0001-use-pytorch.md
│   ├── 0002-data-format-hdf5.md
│   ├── 0003-transformer-architecture.md
│   └── template.md
├── rfcs/                             # Design proposals
│   ├── index.md                      # Active and completed RFCs
│   ├── 0001-multimodal-generation.md
│   └── template.md
├── guides/
│   ├── contributing.md
│   ├── running-experiments.md
│   ├── adding-new-models.md
│   └── data-preprocessing.md
├── tracks/                           # Each track's coordination space
│   ├── data-infrastructure/
│   │   ├── index.md                  # Track charter and overview
│   │   ├── current-sprint.md        # This week's priorities
│   │   ├── roadmap.md                # Next 2-3 months
│   │   └── meeting-notes/            # Weekly meeting notes
│   │       └── 2025-09-29.md
│   ├── model-development/
│   │   ├── index.md
│   │   ├── current-sprint.md
│   │   ├── roadmap.md
│   │   ├── experiments.md            # Log of experiments
│   │   └── meeting-notes/
│   ├── generation-pipeline/
│   │   └── [same structure]
│   └── evaluation/
│       └── [same structure]
├── api/                              # Auto-generated API docs
└── changelog.md                      # Auto-generated from commits
Configure MkDocs with useful plugins:

yaml
# mkdocs.yml
site_name: MassGen Documentation
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - search.suggest
    - search.highlight
    - content.tabs.link
    - content.code.annotate
  palette:
    - scheme: default
      primary: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search
  - git-revision-date-localized:  # Shows when page was last updated
      enable_creation_date: true
  - git-committers:               # Shows who contributed to each page
      repository: username/massgen
  - macros                        # Allows variables and includes
  - autolinks                     # Auto-links to other pages

markdown_extensions:
  - admonition                    # Callout boxes
  - pymdownx.details              # Collapsible sections
  - pymdownx.superfences          # Code blocks with syntax highlighting
  - pymdownx.tabbed:              # Tabs
      alternate_style: true
  - pymdownx.tasklist:            # Task lists
      custom_checkbox: true
  - attr_list                     # Add attributes to markdown
  - md_in_html                    # HTML in markdown
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Architecture:
    - Overview: architecture/overview.md
    - Data Pipeline: architecture/data-pipeline.md
    - Models: architecture/models.md
    - Generation: architecture/generation.md
    - Evaluation: architecture/evaluation.md
  - Development Tracks:
    - Data Infrastructure: tracks/data-infrastructure/index.md
    - Model Development: tracks/model-development/index.md
    - Generation Pipeline: tracks/generation-pipeline/index.md
    - Evaluation: tracks/evaluation/index.md
  - Decision Records:
    - All ADRs: decisions/index.md
  - RFCs:
    - Active RFCs: rfcs/index.md
  - Guides:
    - Contributing: guides/contributing.md
    - Running Experiments: guides/running-experiments.md
    - Adding Models: guides/adding-new-models.md
  - API Reference: api/
  - Changelog: changelog.md
YES, ADRs live in your MkDocs documentation
ADR template at docs/decisions/template.md:

markdown
# ADR-XXXX: [Short Title]

**Status:** [Proposed | Accepted | Rejected | Superseded | Deprecated]
**Date:** 2025-09-29
**Deciders:** [List of people involved in decision]
**Technical Story:** [Optional: link to GitHub issue/PR]

## Context and Problem Statement

What is the problem we're trying to solve? What constraints exist? Include relevant background information.

## Considered Options

1. Option A - Brief description
2. Option B - Brief description
3. Option C - Brief description

## Decision

We chose Option [X] because [reasoning].

## Consequences

### Positive
- Benefit 1
- Benefit 2

### Negative
- Tradeoff 1
- Tradeoff 2

### Neutral
- Thing that changes but isn't clearly better/worse

## Implementation Notes

- Step 1 to implement this decision
- Step 2
- Link to relevant PRs or issues

## Related Decisions

- ADR-XXXX: [Related decision]
- Supersedes ADR-YYYY

---
*Last updated: 2025-09-29 by [Your Name]*
The docs/decisions/index.md becomes your decision log:

markdown
# Architecture Decision Records

This page lists all architectural decisions for MassGen.

## What is an ADR?

An ADR captures an important architectural decision along with its context and consequences. See the [template](template.md) for details.

## Status Definitions

- **Proposed**: Under discussion, not yet decided
- **Accepted**: Decision made and being implemented
- **Rejected**: Decision was considered but not chosen
- **Superseded**: Replaced by a later decision
- **Deprecated**: No longer relevant

## Active Decisions

| ADR | Title | Status | Date | Track |
|-----|-------|--------|------|-------|
| [0003](0003-transformer-architecture.md) | Use Transformer architecture for generation | Accepted | 2025-09-28 | Model Dev |
| [0004](0004-async-data-loading.md) | Implement async data loading pipeline | Proposed | 2025-09-29 | Data Infra |

## Completed Decisions

| ADR | Title | Status | Date | Track |
|-----|-------|--------|------|-------|
| [0001](0001-use-pytorch.md) | Use PyTorch as ML framework | Accepted | 2025-09-01 | Model Dev |
| [0002](0002-data-format-hdf5.md) | Store training data in HDF5 format | Accepted | 2025-09-15 | Data Infra |

## Superseded/Deprecated

| ADR | Title | Status | Superseded By | Date |
|-----|-------|--------|---------------|------|
| None yet | | | | |
Making ADRs searchable and discoverable is the killer feature. Someone asks "Why did we choose PyTorch?" You link to ADR-0001 in your docs site. Six months from now when a new contributor questions the data format, you link to ADR-0002. This prevents endless re-litigation of decisions.

Where each track keeps current progress and goals
This is the key question! Each track needs three layers of coordination:

Layer 1: Track charter (permanent, rarely changes)
Lives at docs/tracks/[track-name]/index.md:

markdown
# Data Infrastructure Track

## Charter

**Mission:** Provide reliable, efficient, and scalable data infrastructure for training and evaluation.

**Scope:**
- Data loading and preprocessing pipelines
- Data format standards and schemas
- Dataset versioning and management
- Data augmentation strategies
- Storage and caching optimization

**Out of Scope:**
- Model architectures (Model Development track)
- Evaluation metrics (Evaluation track)
- Generation APIs (Generation Pipeline track)

**Team Leads:**
- Primary: @username1
- Secondary: @username2

**Communication:**
- Channel: #track-data-infrastructure
- Weekly sync: Tuesdays 2pm PT
- GitHub label: `track/data-infra`

**Decision Making:**
- Track leads have authority on technical decisions within scope
- Cross-track impacts require RFC process
- All discussions default to public

## How to Contribute

1. Join #track-data-infrastructure channel
2. Attend Tuesday syncs as observer
3. Pick up issues labeled `track/data-infra` and `good-first-issue`
4. After 2-3 merged PRs, ask lead to add you as formal member

## Key Repositories

- Main: `/src/data/` in massgen repo
- Related: preprocessing scripts, dataset configs

## Tech Stack

- Data loading: PyTorch DataLoader
- Storage: HDF5 for large datasets, JSON for metadata
- Processing: NumPy, Pandas
Layer 2: Current sprint/week (updates weekly)
Lives at docs/tracks/[track-name]/current-sprint.md:

markdown
# Data Infrastructure - Current Sprint

**Sprint:** Week of 2025-09-29
**Focus:** Implement async data loading for 2x throughput

## This Week's Priorities

### P0 (Must complete this week)
1. **Async DataLoader Implementation** (@username1)
   - Status: In progress (70% complete)
   - PR: #234
   - Blocker: None
   - Expected completion: Friday

2. **HDF5 Performance Testing** (@username2)
   - Status: Completed Monday
   - Results: 30% faster reads with chunking optimization
   - Documentation: Updated in ADR-0002

### P1 (Should complete if time)
3. **Data Augmentation Pipeline** (@username3)
   - Status: Design phase
   - RFC: #12 (needs review from Model Dev track)
   - Blocker: Waiting on model input requirements

### P2 (Nice to have)
4. **Dataset Version Control** (@username4)
   - Status: Not started
   - Will likely roll to next week

## Dependencies on Other Tracks

- **Waiting on Model Dev:** Input shape requirements for RFC #12
- **Blocking Generation Pipeline:** PR #234 must merge before they can test new API

## Blockers

None currently

## Experiments This Week

- Experiment 43: Async loading with 4 workers vs 8 workers
  - Hypothesis: 8 workers will saturate GPU better
  - Status: Running, results expected Wednesday
  - Tracked in: #experiments channel

## Decisions Made This Week

- **Monday:** Chose HDF5 chunking strategy (see ADR-0002 update)
- **Wednesday:** [To be filled in]

## Metrics

- Data loading throughput: 450 samples/sec → 620 samples/sec (target: 800)
- Pipeline latency: 12ms → 8ms (target: 5ms)

---
*Updated: 2025-09-29 by @username1*
*Next update: 2025-10-06*
The magic: this document is THE agenda for your Tuesday track meeting. You spend 15 minutes reviewing it, updating statuses, discussing blockers. Then you commit the updated version. Meeting notes become the updated document itself.

Layer 3: Roadmap (updates monthly or quarterly)
Lives at docs/tracks/[track-name]/roadmap.md:

markdown
# Data Infrastructure Roadmap

**Last updated:** 2025-09-29

## Current Focus (Next 4 weeks)

**Theme:** Performance optimization and async processing

### October 2025
- ✅ Completed: HDF5 format migration
- 🚧 In Progress: Async data loading implementation
- 📋 Planned: Data augmentation pipeline redesign
- 📋 Planned: Distributed data loading for multi-GPU

### November 2025
- Dataset versioning system
- Automatic data quality checks
- Integration with external datasets (ImageNet, COCO)

## Medium-Term Goals (3-6 months)

- **Streaming data pipeline:** Support datasets too large for memory
- **Smart caching:** Predictive caching based on training patterns
- **Cross-dataset experiments:** Easy switching between datasets

## Long-Term Vision (6+ months)

- **Real-time data augmentation:** On-GPU augmentation during training
- **Federated data loading:** Support distributed datasets across machines
- **Automatic format conversion:** Seamlessly handle multiple input formats

## Completed Milestones

- ✅ 2025-09: HDF5 format adoption (ADR-0002)
- ✅ 2025-08: PyTorch DataLoader standardization
- ✅ 2025-07: Initial data pipeline architecture

## Dependencies and Risks

**Dependencies:**
- Model Dev track needs to define input requirements for augmentation pipeline

**Risks:**
- Performance targets may require hardware upgrades
- External dataset licenses unclear for some sources

---
*Next roadmap review: 2025-10-31*
GitHub Projects integration
GitHub Projects is where you coordinate ACROSS tracks, not within them. Each track maintains their detailed progress in their MkDocs pages (current-sprint.md), but GitHub Projects gives you the cross-project view.

Setting up GitHub Projects

favicon
Failed to fetch https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/quickstart-for-projects
Step-by-step GitHub Projects setup:

Go to your repository → Projects tab → New Project
Choose "Board" template initially (you can add other views later)
Name it "MassGen Development"
Create custom fields (click ⚙️ Settings in project view):
Track (Single select): Data Infrastructure, Model Development, Generation Pipeline, Evaluation, Cross-cutting
Priority (Single select): P0 Critical, P1 High, P2 Medium, P3 Low
Size (Single select): XS (hours), S (1-2 days), M (3-5 days), L (1-2 weeks), XL (2+ weeks)
Sprint (Iteration field): Set to 1-week sprints
Status (automatically created): Backlog, Todo, In Progress, In Review, Done
Create multiple views for different perspectives: View 1: Board by Track (default view)
Group by: Track
Shows each track as a column with their issues
Good for daily standup—what's each team working on?
View 2: Current Sprint
Filter: Sprint = "Current"
Group by: Status
Shows everything in this week's sprint regardless of track
Good for understanding overall progress
View 3: Priority Backlog
Filter: Status = "Backlog" or "Todo"
Sort by: Priority (descending)
Shows what needs to be picked up next
Good for sprint planning
View 4: Roadmap (Timeline)
Layout: Roadmap
Shows issues on timeline by their date ranges
Good for seeing how tracks' work overlaps
Link issues to the project:
Any issue you create can be added to the project
Set the Track, Priority, Size, Sprint fields
Issues automatically appear in appropriate views
Example workflow:

Monday morning:

Each dev checks "Board by Track" view to see their track's column
Updates issue statuses (Todo → In Progress → In Review)
Adds new issues for work starting this week
Tags issues with current sprint
Daily standup (if you can't skip it):

Open "Board by Track" view on shared screen
Go through each track column quickly
Anyone with blockers explains and moves their issue to "Blocked" status
Update takes 5 minutes instead of 30
Friday afternoon:

Switch to "Current Sprint" view
See what got done this week (anything in "Done")
Move unfinished work to next sprint or back to backlog
Plan next week's priorities
Connecting GitHub Projects to your MkDocs workflow
The key integration: reference GitHub issues in your docs, reference docs in your issues.

In docs/tracks/data-infrastructure/current-sprint.md:

markdown
## This Week's Priorities

### P0 (Must complete this week)
1. **Async DataLoader Implementation** - [#234](https://github.com/username/massgen/issues/234)
   - Assigned: @username1
   - Status: In Progress
   - See [ADR-0005](../../decisions/0005-async-loading.md) for design rationale
In GitHub issue #234:

markdown
## Implementation Plan

Following the design in [ADR-0005: Async Data Loading](https://username.github.io/massgen/decisions/0005-async-loading/)

### Tasks
- [x] Refactor DataLoader base class
- [ ] Add async worker pool
- [ ] Performance testing

### Documentation
- Update: docs/tracks/data-infrastructure/current-sprint.md when complete
- Update: docs/guides/running-experiments.md with new async usage
Automation: Use GitHub Actions to keep things in sync

yaml
# .github/workflows/docs-check.yml
name: Documentation Check
on: [pull_request]

jobs:
  check-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Check for ADR reference
        if: contains(github.event.pull_request.labels.*.name, 'needs-adr')
        run: |
          # Check if PR description links to an ADR
          if ! grep -q "ADR-" <<< "${{ github.event.pull_request.body }}"; then
            echo "::error::PR labeled 'needs-adr' but no ADR reference found"
            exit 1
          fi

      - name: Check docs updated
        run: |
          # If code changed, check if docs also changed
          if git diff --name-only origin/main | grep -q "^src/"; then
            if ! git diff --name-only origin/main | grep -q "^docs/"; then
              echo "::warning::Code changes detected but no docs updated"
            fi
          fi

      - name: Build docs
        run: |
          pip install mkdocs-material mkdocs-git-revision-date-localized-plugin
          mkdocs build --strict
Practical daily/weekly workflow with your setup
Daily (with your mandated 30min meeting):

9:00am - Standup bot posts in Slack:

"What did you complete yesterday?"
"What are you working on today?"
"Any blockers?"
Everyone responds in writing (takes 2-3 minutes). Responses visible to all.

9:30am - 30min daily sync meeting:

If NO blockers reported → Meeting cancelled (only happens 1-2x/week probably)
If blockers exist → Meet to resolve them only
Don't go around the room reading what people already wrote
Focus entirely on: blockers, cross-team dependencies, urgent decisions
After meeting:

Update GitHub Project issue statuses based on discussion
If any decisions were made, immediately capture in ADR (if architectural) or meeting notes
Weekly (per track):

Tuesday 2pm - Data Infrastructure sync (30 min):

Open docs/tracks/data-infrastructure/current-sprint.md
Review each P0 item: still on track? Any issues?
Review dependencies: still waiting on Model Dev? Should we escalate?
Review experiments: any results that change our approach?
Make decisions: commit them immediately to ADRs if significant
Update the current-sprint.md document itself as you go
Commit the updated document at end of meeting (it IS the meeting notes)
Same pattern for each track on their designated day.

Bi-weekly (all tracks):

Every other Thursday - Cross-team coordination (60 min):

Open GitHub Projects "Board by Track" view
Each track gives 5-minute update (not details, just themes):
What shipped since last time
What's coming in next 2 weeks
What dependencies exist on other tracks
Identify conflicts and dependencies
Make cross-cutting decisions that need multiple tracks
30 minutes remaining for deep dive on 1-2 critical cross-track issues
Monthly:

First Monday of month - Roadmap review (60 min):

Each track presents updated roadmap
Discuss strategic priorities for next quarter
Reallocate resources if needed
Update docs/tracks/*/roadmap.md files
Specific answers to your questions
"Can ADR be done in MkDocs?"
Yes! As shown above, /docs/decisions/ contains all your ADRs. They're versioned in git, searchable via MkDocs search, and automatically deployed when you push to main. This is superior to separate tools because ADRs live where developers already look—your documentation.

"Where does each team keep its current progress and goals?"
Three places working together:

MkDocs current-sprint.md - Detailed weekly progress, updated weekly, IS the meeting agenda/notes
MkDocs roadmap.md - Strategic direction, updated monthly
GitHub Projects - Cross-team coordination view, updated daily as issues progress
The pattern: detailed tracking in MkDocs (owned by each track), coordination view in GitHub Projects (shared across all tracks).

"More information on how to set up GitHub Projects?"
See the step-by-step above. Key insight: Projects is a VIEW on your issues, not a separate system. Create issues normally, add them to project, set custom fields, and appropriate views automatically filter/organize them.

The transition plan for your team
You can't change everything overnight, especially with constraints from your boss. Here's how to transition gradually:

Week 1: Documentation foundation

Set up MkDocs with structure shown above
Create track charter pages (docs/tracks/*/index.md)
Add ADR template and first ADR: "ADR-0001: Use MkDocs as single source of truth"
Deploy docs site (GitHub Pages or Read the Docs)
Week 2: Current sprint tracking

Each track creates their current-sprint.md page
Start updating it before weekly track meetings
Use it AS the meeting agenda
Prove to yourselves that the doc-first approach works
Week 3: GitHub Projects

Set up project with custom fields as described
Migrate current issues/work into project
Add project board view to daily standup
Week 4: Standup bot

Install Geekbot or similar
Start collecting written daily updates
Keep the 30min meeting but start canceling days with no blockers
Show your boss metrics: "We had 2 days this week with no blockers, saving 1 hour of collective meeting time"
Week 5-8: Iterate and optimize

Add more MkDocs plugins (git-revision-date, git-committers)
Set up ADR automation
Refine project views based on usage
Gather feedback and adjust
After 2 months: Make the case to your boss Present data:

"We saved X hours of meeting time by canceling blocked-free standups"
"Our documentation is now central source of truth, onboarding new devs takes half the time"
"Three releases/week works smoothly now that process is automated"
Propose: reduce standups to 3x/week or move fully async
Bosses respond to results. Prove the system works within their constraints first, then use that success to negotiate better constraints.

The core principle: your documentation becomes your workflow, not documentation OF your workflow. Current sprint docs ARE where work is tracked. ADRs ARE where decisions live. Roadmaps ARE your planning. GitHub Projects provides the cross-cutting view. Everything else flows from this.

You're in a challenging situation with high meeting overhead and excessive release cadence, but the documentation-centric approach actually helps MORE in constrained environments because it creates clarity and reduces coordination overhead. Start with the Week 1 actions and iterate from there.

https://github.com/Leezekun/MassGen/pull/179

These are drafts for the doc. I'm thinking of taking leadership and organizing these better. Can you give me some options

Looking at PR #179, I can see you have a solid foundation with MkDocs already set up and several documentation pages drafted. The structure is reasonable but definitely needs organization to become the coordination hub we discussed. Let me give you concrete options for taking leadership here.

Current State Analysis
From the PR, you have:

Basic MkDocs setup with Material theme
Architecture overview drafted
Some component documentation (data loading, model training, generation)
Getting started guide
API reference structure
The good: Foundation is there, Material theme is excellent, clear intent to document architecture.

The gaps: No team coordination structure, no ADRs, no track-specific pages, no current work tracking, documentation feels more like "user manual" than "development coordination hub."

Option 1: Comprehensive Reorganization (Recommended for leadership visibility)
What you do: Propose a significant restructure that transforms the docs into the coordination system we discussed. This is the bold leadership move that shows vision.

Concrete changes to PR #179:

Add new directory structure:
docs/
├── index.md                          # Keep existing, enhance
├── getting-started/                  # User-facing docs
│   ├── installation.md
│   ├── quickstart.md
│   └── tutorials.md
├── architecture/                     # Keep existing
│   ├── overview.md                   # Your current architecture.md
│   ├── data-pipeline.md              # Expand from current sections
│   ├── models.md
│   ├── generation.md
│   └── evaluation.md
├── development/                      # NEW - Developer coordination
│   ├── contributing.md
│   ├── development-setup.md
│   ├── testing.md
│   └── release-process.md
├── decisions/                        # NEW - ADRs
│   ├── index.md
│   ├── 0001-use-mkdocs.md           # Your first ADR!
│   ├── 0002-pytorch-framework.md
│   └── template.md
├── tracks/                           # NEW - Team coordination
│   ├── index.md                      # Overview of track system
│   ├── data-infrastructure/
│   │   ├── index.md                  # Charter
│   │   ├── current-work.md           # Weekly updates
│   │   └── roadmap.md
│   ├── model-development/
│   │   └── [same structure]
│   ├── generation-pipeline/
│   │   └── [same structure]
│   └── evaluation/
│       └── [same structure]
├── api/                              # Keep existing API docs
└── experiments/                      # NEW - Experiment tracking
    ├── index.md
    └── template.md
Update mkdocs.yml navigation:
yaml
nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Quick Start: getting-started/quickstart.md
    - Tutorials: getting-started/tutorials.md
  - Architecture:
    - System Overview: architecture/overview.md
    - Data Pipeline: architecture/data-pipeline.md
    - Model Training: architecture/models.md
    - Generation: architecture/generation.md
    - Evaluation: architecture/evaluation.md
  - Development:
    - Contributing: development/contributing.md
    - Setup: development/development-setup.md
    - Testing: development/testing.md
    - Release Process: development/release-process.md
  - Team Coordination:
    - Overview: tracks/index.md
    - Data Infrastructure: tracks/data-infrastructure/index.md
    - Model Development: tracks/model-development/index.md
    - Generation Pipeline: tracks/generation-pipeline/index.md
    - Evaluation: tracks/evaluation/index.md
  - Architecture Decisions: decisions/index.md
  - Experiments: experiments/index.md
  - API Reference: api/
Write a strong PR description explaining the vision:
markdown
## Documentation Restructure for Team Coordination

### Problem
Our current documentation serves as a user manual but doesn't support our development process. With 3-5 parallel development tracks, we need documentation that:
- Tracks current work and priorities per team
- Records architectural decisions with context
- Provides visibility across tracks
- Serves as single source of truth for coordination

### Solution
Restructure docs to serve dual purpose:
1. **External**: User-facing guides, architecture, API reference
2. **Internal**: Team coordination, decision records, experiment tracking

### Key Additions

**Architecture Decision Records (ADRs)**
- `/docs/decisions/` captures why we made significant technical choices
- Prevents re-litigating past decisions
- Provides context for new contributors
- See ADR-0001 for example

**Track Coordination Pages**
- `/docs/tracks/` gives each development team their coordination space
- `current-work.md` updated weekly with priorities and blockers
- `roadmap.md` shows medium-term direction
- Eliminates "where is this documented?" questions

**Experiment Tracking**
- `/docs/experiments/` logs significant experiments with results
- Preserves institutional knowledge about what was tried
- Links to issues/PRs for full context

### Migration Plan
- Existing content moved to appropriate new locations
- No content deleted, just reorganized
- Can implement gradually: ADRs first, then track pages

### Benefits
- Single source of truth for project state
- Async-first coordination (reduce meeting overhead)
- Better onboarding for new contributors
- Historical context preserved

Addresses issue #[number if there is one]
Pros of this approach:

Shows strategic thinking and leadership
Creates the infrastructure for coordination improvements
Can reference this in discussions with your boss about process improvements
Makes the value immediately visible
Cons:

Larger change, might get pushback
More work upfront
Requires buy-in from other track leads
Option 2: Incremental Leadership (Lower risk, still effective)
What you do: Accept the current PR mostly as-is but immediately add two high-value sections that demonstrate the coordination concept.

Minimal changes to PR #179:

1. Add /docs/decisions/ with your first ADR
Create docs/decisions/0001-use-mkdocs.md:

markdown
# ADR-0001: Use MkDocs for Project Documentation

**Status:** Accepted
**Date:** 2025-09-30
**Deciders:** @Leezekun, [other core contributors]

## Context and Problem Statement

MassGen needs comprehensive documentation that serves both external users and internal developers. We need to track architectural decisions, coordinate across development tracks, and provide API references. The documentation system must be:
- Easy to write and maintain (markdown-based)
- Version controlled alongside code
- Searchable and navigable
- Deployable automatically
- Extensible for future needs

## Considered Options

1. **MkDocs with Material theme** - Python-based static site generator
2. **Sphinx** - Traditional Python documentation tool
3. **Docusaurus** - React-based, modern but requires Node.js
4. **GitBook** - Hosted solution, less control
5. **Wiki (GitHub/GitLab)** - Built-in but limited features

## Decision

We chose **MkDocs with Material theme**.

### Rationale
- Material theme provides excellent UX out of the box (search, navigation, mobile-friendly)
- Python-based aligns with our project stack
- Simpler than Sphinx for non-API documentation
- Large plugin ecosystem (git-revision-date, git-committers, etc.)
- Easy for non-technical contributors to write markdown
- Deploys automatically to GitHub Pages
- Strong community support

## Consequences

### Positive
- Contributors can write docs in familiar markdown
- Version controlled with code - docs and code stay in sync
- Material theme is highly customizable
- Plugin ecosystem addresses most needs (changelog generation, git info, etc.)
- Fast site builds and deploys

### Negative
- Need to maintain mkdocs.yml configuration
- Some plugins may have version compatibility issues
- Python dependency (but already required for project)

### Neutral
- Need to set up GitHub Pages or alternative hosting
- Learning curve for mkdocs-specific features (admonitions, tabs, etc.)

## Implementation

- [x] Basic MkDocs setup with Material theme (PR #179)
- [ ] Configure GitHub Actions for automatic deployment
- [ ] Add key plugins (git-revision-date, search, etc.)
- [ ] Create documentation standards guide

## Related Decisions

None yet (this is our first ADR)

## References

- MkDocs: https://www.mkdocs.org/
- Material theme: https://squidfunk.github.io/mkdocs-material/
- ADR format: https://adr.github.io/
Create docs/decisions/index.md:

markdown
# Architecture Decision Records

An Architecture Decision Record (ADR) captures an important architectural decision made along with its context and consequences.

## Why ADRs?

- **Context preservation**: Understand why decisions were made 6 months from now
- **Avoid re-litigation**: Don't endlessly debate already-decided questions
- **Onboarding**: New contributors can quickly understand project rationale
- **Transparency**: All stakeholders see the decision-making process

## How to Write an ADR

Use the [template](template.md) to document significant technical decisions:
- Framework choices
- Architecture patterns
- Data format decisions
- API design approaches
- Testing strategies

## All Decision Records

### Active

| ADR | Title | Status | Date | Track |
|-----|-------|--------|------|-------|
| [0001](0001-use-mkdocs.md) | Use MkDocs for project documentation | Accepted | 2025-09-30 | Infrastructure |

### Proposed

None currently

### Superseded/Deprecated

None yet
2. Add /docs/development/current-sprint.md
This demonstrates the coordination concept without requiring full track structure yet:

markdown
# Current Development Sprint

**Sprint Period:** Week of 2025-09-30
**Last Updated:** 2025-09-30

This page tracks current development priorities across all teams. Updated weekly.

## High Priority (Must Complete This Week)

### Documentation Foundation
- **Status:** In Progress (PR #179)
- **Owner:** @Leezekun
- **Description:** Establish MkDocs-based documentation structure
- **Blocker:** None
- **Target:** Merge by Friday

### [Other Priority 1 Items]
Add your team's top priorities here...

## Medium Priority (Should Complete)

### [Add items from daily standups]

## Blockers and Dependencies

### Active Blockers
None currently

### Cross-Team Dependencies
- [List any dependencies between teams]

## Completed This Week

- [Items completed get moved here Friday afternoon]

## Next Week's Preview

- [Planning for next sprint happens here]

---

*This document is updated every Monday morning. Add your priorities during your track's weekly sync.*
3. Update the PR description to hint at the bigger vision:
markdown
## Documentation Infrastructure (Foundation)

This PR establishes MkDocs-based documentation for MassGen. This is the first step toward comprehensive documentation that will serve as our coordination hub.

### What's in This PR
- MkDocs setup with Material theme
- Architecture overview
- Getting started guide
- API reference structure
- **NEW**: Architecture Decision Records (ADRs) - starting with ADR-0001
- **NEW**: Current sprint tracking page

### What's Coming Next (Future PRs)
- Track-specific coordination pages
- Experiment tracking
- More ADRs as we document existing decisions
- Automated changelog generation

### How to Review
1. Check that MkDocs builds: `mkdocs serve`
2. Review content accuracy in architecture sections
3. Verify links work correctly
4. Provide feedback on ADR format

The ADR and sprint tracking additions demonstrate how this documentation will evolve beyond just user guides into our development coordination system.
Pros of this approach:

Lower friction, easier to merge
Demonstrates the concept without requiring full buy-in
You can expand incrementally after this merges
Still shows leadership and vision
Cons:

Less comprehensive
Might need to reorganize again later
Benefits are less immediately obvious
Option 3: Collaborative Expansion (Build consensus first)
What you do: Use PR #179 as the conversation starter about coordination improvements.

Approach:

1. Merge PR #179 mostly as-is
Accept the current structure with minor improvements (fix broken links, improve navigation, etc.)

2. Immediately after merge, open an Issue proposing the coordination structure:
markdown
# Issue: Transform Documentation into Development Coordination Hub

## Problem

Our documentation currently serves as a user manual but doesn't support our multi-track development process. Key pain points:

- No clear place to track current work per team
- Architectural decisions exist only in PR comments and meeting notes
- Cross-team dependencies not visible
- New contributors lack context on why past decisions were made
- Meeting time spent repeating information that could be documented

## Proposal

Extend our MkDocs documentation to serve dual purpose:
1. **External-facing**: User guides, architecture, API reference (current)
2. **Internal-facing**: Team coordination, decision records, work tracking (new)

### Specific Additions

**1. Architecture Decision Records (ADRs)**
- Document significant technical decisions with context
- Location: `/docs/decisions/`
- Format: [Show template]
- Examples from other projects: Kubernetes, Rust, etc.

**2. Track Coordination Pages**
- Each development track gets dedicated space
- Location: `/docs/tracks/[track-name]/`
- Contains: charter, current work, roadmap
- Updated weekly by track leads

**3. Experiment Tracking**
- Log significant ML experiments with results
- Location: `/docs/experiments/`
- Links to issues/PRs and W&B/MLflow runs

### Benefits

- **Async coordination**: Reduce meeting overhead by documenting decisions
- **Single source of truth**: Everyone knows where to find information
- **Better onboarding**: New contributors can self-serve context
- **Historical record**: Preserve institutional knowledge
- **Cross-team visibility**: See dependencies and blockers at a glance

### Implementation Plan

Phase 1 (Week 1-2):
- Add ADR template and write first 3-5 ADRs for existing decisions
- Create track directory structure with charters

Phase 2 (Week 3-4):
- Track leads begin using `current-work.md` pages
- Integrate with GitHub Projects for cross-cutting view

Phase 3 (Week 5+):
- Add experiment tracking
- Automate changelog and documentation deployment
- Iterate based on usage

### Request for Feedback

@all-track-leads - Thoughts on this approach?
- Does the track coordination structure make sense for your team?
- What else would make documentation more useful for coordination?
- Willing to co-own this with me?

Related: Research on OS project coordination patterns [link to research you've done]
3. Tag relevant people and start discussion in issue comments
4. Once consensus emerges, implement in phases with separate PRs
Pros of this approach:

Builds team buy-in before major changes
Distributes ownership (other leads co-own their track pages)
Lower risk of rejection
Creates paper trail of reasoning
Cons:

Slower
Might get stuck in endless discussion
Less clear leadership signal
Requires herding cats
Option 4: Stealth Leadership (My personal favorite for your situation)
What you do: Merge PR #179, then immediately start using the expanded structure yourself as an example.

Tactical approach:

1. Merge PR #179 with minimal changes
2. Within 24 hours, open PR #180: "Add ADRs and Track Coordination Example"
Create the full structure we discussed but only populate YOUR track's pages fully:

docs/
├── [existing structure]
├── decisions/                        # NEW
│   ├── index.md
│   ├── 0001-use-mkdocs.md
│   ├── 0002-pytorch-framework.md    # Document obvious past decisions
│   ├── 0003-hdf5-data-format.md
│   └── template.md
└── tracks/                           # NEW
    ├── index.md                      # Explain track system
    ├── [your-track]/                 # Fully populated example
    │   ├── index.md                  # Charter
    │   ├── current-work.md           # This week's actual work
    │   └── roadmap.md                # Real roadmap
    └── [other-tracks]/               # Stub pages with templates
        └── index.md                  # "Template - customize for your track"
The PR description:

markdown
## Add Team Coordination Infrastructure (By Example)

This PR adds infrastructure for development coordination, starting with [Your Track] as a working example.

### What's Added

**Architecture Decision Records**
- Template and first 3 ADRs documenting past decisions
- Prevents re-litigation of choices already made
- See `/docs/decisions/` - I've documented the obvious ones

**Track Coordination Pages**
- New `/docs/tracks/` structure
- I've fully populated [Your Track] as a working example
- Other tracks have template pages ready to customize

### Why This Approach

Rather than proposing this in abstract, I've implemented it for my track so you can:
- See the format in action with real content
- Copy the pattern if it's useful for your track
- Provide feedback based on concrete example
- Adopt gradually without forcing process changes

### How to Use This

**If you're a track lead:**
1. Check out `/docs/tracks/[my-track]/` to see the example
2. If useful, copy the structure for your track
3. Update your `current-work.md` weekly (I'll be doing this Mondays)
4. No obligation - use if helpful, ignore if not

**ADRs:**
- Use the template in `/docs/decisions/template.md`
- Write an ADR when making significant technical decisions
- Link to it when people ask "why did we choose X?"

### The Goal

Reduce coordination overhead by documenting more, meeting less. If this works for my track, others can adopt. If it doesn't, we've learned something with minimal investment.

Feedback welcome!
Why this works:

Lead by example - You're not telling people what to do, you're showing what works
No forcing function - Other teams adopt if/when they see value
Concrete over abstract - Real example beats theoretical proposal
Low friction - PR is additive, doesn't change existing structure
Builds credibility - When your track's coordination improves, others notice
3. Actually use it religiously
Update your track's current-work.md every Monday
Write ADRs for your decisions
Reference them in PRs and discussions
Track your track's work in GitHub Projects
4. Let the results speak
In 2-3 weeks:

Your track's work is more visible
Fewer "what's the status?" questions
Better coordination with other tracks
Others start asking "can we do that for our track?"
5. Then facilitate adoption
When others show interest:

Help them set up their track pages
Share what worked / didn't work for you
Offer to pair on their first ADR
Gradually become the de facto coordination lead
Pros of this approach:

Demonstrates value before asking for buy-in
Low risk (only affects your track initially)
Strong leadership signal (do, don't just talk)
Creates template others can copy
Works around organizational resistance
Cons:

Requires discipline from you to maintain
Benefits take a few weeks to become obvious
Other tracks might never adopt (but then at least YOUR track benefits)
My Recommendation: Option 4 (Stealth Leadership)
Given your constraints (boss controls meetings, 3x weekly releases, you're not sole project lead), Option 4 is the highest ROI:

Merge PR #179 with these minimal additions:
Add docs/decisions/ directory with template
Add docs/tracks/ directory with index explaining the system
Fix any broken links or navigation issues
Immediately follow with PR #180 that:
Writes 3-5 ADRs for obvious past decisions (PyTorch choice, data formats, etc.)
Fully populates YOUR track's coordination pages with real content
Leaves other tracks with stub/template pages
Includes strong PR description explaining the "lead by example" approach
Actually use it for 2-3 weeks:
Update your current-work.md every Monday morning
Write ADRs when your track makes decisions
Reference ADRs and docs in Slack/issues
Track your work in GitHub Projects using the structure
Let others adopt organically:
When they ask questions, link to docs
When they complain about coordination, show them your track's pages
Offer to help them set up their structure
Eventually propose making it project-wide standard
This approach works because:

You're not waiting for permission or consensus
You're not forcing change on others
You're building credibility through results
When you eventually propose broader changes to your boss, you have evidence
Specific Next Steps for PR #179
Since the PR is already open, here's what to do today:

1. Review existing content in PR carefully
Fix any technical inaccuracies
Ensure links work
Check that code examples run
Improve navigation if confusing
2. Add exactly two things before merging:
File: docs/decisions/0001-use-mkdocs.md (Use the content I provided in Option 2 above)

File: docs/decisions/index.md (Use the content I provided in Option 2 above)

3. Update the PR description to:
markdown
## Documentation Foundation (PR #179)

This PR establishes MkDocs-based documentation for MassGen.

### What's Included
- MkDocs with Material theme setup
- Architecture overview
- Getting started guide
- API reference structure
- Architecture Decision Records infrastructure (starting with ADR-0001)

### Next Steps (After Merge)
- Track-specific coordination pages (PR #180, coming soon)
- Additional ADRs documenting existing decisions
- Experiment tracking
- Integration with GitHub Projects

This is the foundation. Coordination features will be added incrementally based on team needs.

### How to Review
```bash
git checkout [branch]
pip install mkdocs-material
mkdocs serve
# Visit http://127.0.0.1:8000
Deployment
Once merged, docs will be automatically deployed to GitHub Pages via GitHub Actions (setup in future PR).


### 4. Get it merged

### 5. Immediately open PR #180 with the full track coordination structure

---

**TL;DR:** Go with Option 4. Merge #179 with ADRs added, immediately follow with #180 showing the full coordination system by example for your track only. Use it religiously for 2-3 weeks. Let the results drive adoption by others. This is how you take leadership without needing authority.
Let's say one track pushes a feature. Where does that go? Is it described somewhere? I'm also just fundamentally confused about adrs. Are they more organized usually?

Great questions! Let me clarify both the feature workflow and ADR organization with concrete examples.

Where does a feature go? (The complete workflow)
Let's trace a real feature from idea to deployment:

Example: "Add multi-GPU data loading support"
Step 1: Idea/Proposal Phase

Someone (let's say from Data Infrastructure track) thinks "we need multi-GPU data loading." Where does it start?

Option A: Small feature (< 1 week, affects only one track)

Create GitHub Issue: "Add multi-GPU data loading"
Label it: track/data-infra, type/feature, priority/p1
Assign to yourself or someone on the track
Add to GitHub Projects board in your track's column
That's it! Just start working.
Option B: Large feature (> 1 week, affects multiple tracks)

Create RFC in /docs/rfcs/0001-multi-gpu-loading.md:
markdown
# RFC-0001: Multi-GPU Data Loading

**Author:** @username
**Date:** 2025-10-01
**Status:** Proposed
**Tracks Affected:** Data Infrastructure, Model Development

## Summary

Add support for distributed data loading across multiple GPUs to improve training throughput.

## Motivation

Current data loading is single-GPU only, becoming a bottleneck as we scale to 8-GPU training. We're seeing GPU utilization drop to 60% because data loading can't keep up.

**Expected impact:**
- 2x faster training on multi-GPU setups
- Better GPU utilization (60% → 90%)
- Enables training larger models

## Detailed Design

### Architecture
- Use PyTorch DistributedDataParallel (DDP)
- Each GPU gets its own DataLoader worker
- Sharding strategy: split dataset by GPU rank

### API Changes
```python
# Before
dataloader = MassGenDataLoader(dataset, batch_size=32)

# After (backward compatible)
dataloader = MassGenDataLoader(
    dataset,
    batch_size=32,
    distributed=True  # New parameter
)
Implementation Plan
Refactor DataLoader to support sharding (Week 1)
Add distributed sampler (Week 2)
Update training scripts (Week 2)
Performance testing and optimization (Week 3)
Alternatives Considered
Alternative 1: Use NVIDIA DALI

Pros: Higher performance
Cons: Extra dependency, CUDA-only, learning curve
Rejected because: PyTorch DDP is good enough and we stay framework-agnostic
Alternative 2: Roll our own distributed loading

Pros: Full control
Cons: Reinventing the wheel, maintenance burden
Rejected because: PyTorch DDP is battle-tested
Drawbacks
Breaking change if users call DataLoader directly without using our training scripts
Requires PyTorch 1.10+ (forces version bump)
Slightly more complex setup for single-GPU users
Unresolved Questions
How do we handle uneven dataset sizes across GPUs?
What's the migration path for existing training jobs?
Do we need special handling for evaluation?
Dependencies
Blocks:

Model Dev track needs this for their 8-GPU experiments
Requires:

Need Model Dev input on API design
Need Generation track to review if this affects inference
Discussion: Please review and comment. Need approval from @model-lead and @generation-lead before starting implementation.


- Open this RFC as a **Pull Request** to the docs
- Comment thread happens on the PR
- Tag affected track leads: @model-lead @generation-lead
- Discuss for ~1 week
- When consensus reached, merge the RFC

**Step 2: Track it during development**

Once approved (or immediately for small features), add to your track's `current-work.md`:
```markdown
# Data Infrastructure - Current Work

**Week of:** 2025-10-01

## In Progress

### Multi-GPU Data Loading (P0)
- **Owner:** @username
- **GitHub Issue:** #245
- **RFC:** [0001-multi-gpu-loading](../rfcs/0001-multi-gpu-loading.md)
- **Status:** Week 1/3 - Refactoring DataLoader base class
- **PR:** #246 (draft)
- **Blockers:** None
- **Dependencies:** Needs API review from Model Dev by Friday

### Progress Details
- ✅ Design approved (see RFC)
- 🚧 DataLoader refactor (60% done)
- ⏳ Distributed sampler (not started)
- ⏳ Training script updates (not started)
And add to GitHub Projects:

Issue #245 in "In Progress" column
Tagged with your current sprint
Custom fields: Priority=P0, Track=Data Infrastructure, Size=L
Step 3: Implementation happens

Developer works on it, updating:

Daily: GitHub issue status (comments on progress)
Daily standup: Written update mentions it
Weekly: Track's current-work.md updated with progress %
As needed: Opens PRs, links them to issue #245
Step 4: Code review and testing

markdown
# Pull Request #246: Add multi-GPU data loading

Implements RFC-0001: Multi-GPU Data Loading

## Changes
- Refactored DataLoader to support distributed sharding
- Added DistributedSampler wrapper
- Updated training scripts with `--distributed` flag
- Added integration tests for 2/4/8 GPU configs

## Testing
- ✅ All existing tests pass
- ✅ New tests for distributed loading (8 added)
- ✅ Manual testing on 8-GPU setup: 2.1x speedup
- ✅ Backward compatibility verified

## Documentation Updates
- Updated: `/docs/guides/training.md` with distributed setup
- Updated: `/docs/architecture/data-pipeline.md` with new architecture
- Added: API docs for DistributedDataLoader

## Breaking Changes
None - fully backward compatible via optional parameter

## Related
- Issue: #245
- RFC: #0001
- Depends on: None
Review happens:

/lgtm from another Data Infrastructure member (technical review)
/approve from Data Infrastructure track lead (ownership approval)
Must pass CI tests
Merges to main
Step 5: It's released

You said you release 3x/week. When the next release happens:

The feature automatically shows up in:

Changelog (auto-generated from commit messages or PR labels)
Release notes on GitHub Releases
Docs site (updated when main branch deploys)
Track's current-work.md updated:

markdown
## Completed This Week

### ✅ Multi-GPU Data Loading
- **Merged:** PR #246 on 2025-10-03
- **Released:** v0.8.2 on 2025-10-04
- **Impact:** 2.1x training speedup on 8-GPU setups
- **Documentation:** Updated training guide
Step 6: Post-release

If the feature required significant architectural decisions during implementation, write an ADR:

markdown
# ADR-0008: Use PyTorch DDP for Distributed Data Loading

**Status:** Accepted
**Date:** 2025-10-03
**Related RFC:** RFC-0001

## Context

We needed multi-GPU data loading. RFC-0001 proposed PyTorch DistributedDataParallel (DDP), but during implementation we discovered additional considerations.

## Decision

Use PyTorch DDP with rank-based sharding strategy.

### Specific Choices Made

1. **Sharding by rank** (not random assignment)
   - Each GPU gets contiguous chunks of dataset
   - Ensures reproducibility with same seed
   - Alternative: random per-epoch shuffling was considered but made debugging hard

2. **Backward compatible API** (optional `distributed=True` parameter)
   - Doesn't break existing code
   - Makes migration easier
   - Alternative: separate DistributedDataLoader class felt like unnecessary complexity

3. **Require PyTorch 1.10+**
   - DDP improvements in 1.10 are significant
   - Forces minimum version bump
   - Acceptable tradeoff for users

## Consequences

### Positive
- 2.1x speedup on 8-GPU training
- GPU utilization improved 60% → 88%
- Zero breaking changes for existing users
- Simple API that doesn't expose DDP complexity

### Negative
- PyTorch version requirement increased
- Single-GPU users pay small abstraction cost (negligible)
- Need to maintain both code paths (distributed and non-distributed)

## Implementation

- Merged in PR #246
- Released in v0.8.2
- Full details in RFC-0001
So to summarize the flow:
Idea
  → Issue created (#245)
  → [If big: RFC written and discussed]
  → Added to track's current-work.md
  → Added to GitHub Projects
  → Implementation (PRs opened, linked to issue)
  → Code review
  → Merge to main
  → Automatic release (next scheduled release)
  → Shows in changelog/release notes
  → Moved to "Completed" in current-work.md
  → [If architecturally significant: ADR written afterward]
Key places feature is described:

GitHub Issue #245 - The "what" and tracking
RFC (if large) - The "why" and "how" proposal
Track's current-work.md - Weekly status updates
GitHub Projects - Cross-team visibility
Pull Request(s) - Implementation details
Documentation - User-facing "how to use"
ADR (if needed) - Architectural "why we chose this"
Changelog/Release Notes - "What shipped when"
ADRs: More organized usually?
You're right to be confused - ADRs ARE simple, but let me clarify what they're for and how they're typically organized:

What ADRs are NOT:
❌ Not feature descriptions (that's GitHub issues)
❌ Not design proposals (that's RFCs)
❌ Not implementation docs (that's code comments/docs)
❌ Not meeting notes
❌ Not TODO lists
What ADRs ARE:
✅ Records of significant architectural decisions
✅ Capture the context (why we needed to decide)
✅ Document the alternatives considered
✅ Explain the rationale (why we chose what we chose)
✅ Note the consequences (tradeoffs)
When to write an ADR:
YES - Write an ADR for:

Framework/library choices ("Use PyTorch not TensorFlow")
Data format decisions ("Store training data as HDF5")
Architecture patterns ("Use microservices not monolith")
API design approaches ("REST API not GraphQL")
Database choices ("PostgreSQL for metadata storage")
Testing strategies ("Integration tests required for all APIs")
Deployment approaches ("Deploy via Docker containers")
Security decisions ("Use JWT for authentication")
NO - Don't write ADR for:

Bug fixes (just fix and PR)
Small refactors (just do it)
Documentation updates (just update)
Dependency version bumps (just update)
Performance optimizations (unless they change architecture)
Individual features (use issues/RFCs)
The test: "Will someone 6 months from now ask 'why did we do it this way?'"

If yes → ADR
If no → Just do it

ADR Organization
You asked "are they more organized usually?" - here's how mature projects organize them:

Simple numbering (most common):

docs/decisions/
├── 0001-use-pytorch.md
├── 0002-hdf5-data-format.md
├── 0003-rest-api-design.md
├── 0004-docker-deployment.md
├── 0005-jwt-authentication.md
└── index.md  (lists all with status)
By category (if you have LOTS of ADRs - 50+):

docs/decisions/
├── infrastructure/
│   ├── 0001-use-pytorch.md
│   ├── 0005-docker-deployment.md
├── data/
│   ├── 0002-hdf5-data-format.md
│   ├── 0008-data-versioning.md
├── api/
│   ├── 0003-rest-api-design.md
│   ├── 0007-api-versioning.md
└── index.md
Most projects (including Kubernetes, Rust) use simple numbering until they have 100+ ADRs, then consider categories.

Better index.md organization
The key is your index.md makes them discoverable:

markdown
# Architecture Decision Records

## Active Decisions (Currently Implemented)

### Infrastructure
| ADR | Title | Date | Summary |
|-----|-------|------|---------|
| [0001](0001-use-pytorch.md) | Use PyTorch as ML framework | 2025-09 | PyTorch chosen over TensorFlow for flexibility and ecosystem |
| [0005](0005-docker-deployment.md) | Deploy via Docker containers | 2025-09 | Containerization for consistency across environments |

### Data Architecture
| ADR | Title | Date | Summary |
|-----|-------|------|---------|
| [0002](0002-hdf5-data-format.md) | Store training data in HDF5 | 2025-09 | HDF5 chosen for large dataset performance |
| [0008](0008-data-versioning.md) | Use DVC for data versioning | 2025-10 | Track dataset versions alongside code |

### API Design
| ADR | Title | Date | Summary |
|-----|-------|------|---------|
| [0003](0003-rest-api-design.md) | REST API for generation service | 2025-09 | REST chosen over GraphQL for simplicity |

## Proposed (Under Discussion)

| ADR | Title | Date | Summary |
|-----|-------|------|---------|
| [0009](0009-multi-cloud-strategy.md) | Multi-cloud deployment strategy | 2025-10 | Proposal to support AWS + GCP |

## Superseded (Historical)

| ADR | Title | Date | Superseded By | Reason |
|-----|-------|------|---------------|--------|
| [0004](0004-mongodb-metadata.md) | Use MongoDB for metadata | 2025-09 | ADR-0011 | Performance issues, moved to PostgreSQL |

## Search by Tag

- **#infrastructure**: 0001, 0005, 0009
- **#data**: 0002, 0008
- **#api**: 0003
- **#security**: 0006, 0007
- **#ml-models**: 0010

## Quick Links

- [Template](template.md) - Use this for new ADRs
- [How to write ADRs](../development/adr-guide.md)
- [All RFCs](../rfcs/index.md) (for design proposals)
Real example: When features and ADRs intersect
Let's trace the multi-GPU feature again with ADR timing:

Timeline:

Sept 25: Idea for multi-GPU loading
Sept 26: Create RFC-0001 (design proposal)
Sept 26-Oct 2: RFC discussion and approval
Oct 2: Start implementation
Oct 2-Oct 15: Development (3 weeks)
Oct 10: During implementation, discover PyTorch 1.10+ required (write ADR-0008)
Oct 15: PR merged
Oct 16: Released in v0.8.2
Notice: ADR written during implementation when you discover the architectural decision.

Alternative timing: Could write ADR after RFC approval (Oct 2) if the decision is clear then.

The rule: Write the ADR when the decision is made, whether that's:

During RFC discussion
During implementation
After the fact (retroactively documenting old decisions)
ADRs vs RFCs - Key difference
RFC = "What should we build?"

Future-looking
Open for discussion
Can be rejected
Design proposal
ADR = "Why did we build it this way?"

Past-looking (or just-decided)
Records decision made
Always accepted (might be superseded later)
Historical record
Example:

RFC-0001: "Let's add multi-GPU loading using PyTorch DDP" → 1 week discussion
ADR-0008: "We decided to use PyTorch DDP for multi-GPU because..." → Documented when decided
Sometimes you write both:

RFC during planning
ADR during/after implementation capturing what actually happened
Sometimes you only write ADR:

For small decisions that don't need RFC discussion
For retroactive documentation of past decisions
Practical example for MassGen
Let's say your project already uses PyTorch (obvious decision). You should retroactively write:

ADR-0001: Use PyTorch as Deep Learning Framework

markdown
# ADR-0001: Use PyTorch as Deep Learning Framework

**Status:** Accepted
**Date:** 2025-09-30 (decision made earlier, documented retroactively)
**Deciders:** @Leezekun, [founding team]

## Context

MassGen requires a deep learning framework for:
- Model development and training
- Data loading and preprocessing
- Distributed training across multiple GPUs
- Production inference

Framework choice is foundational and affects:
- Developer productivity
- Model architecture flexibility
- Deployment options
- Community support and ecosystem

## Considered Options

1. **PyTorch** - Dynamic computation graphs, Pythonic API
2. **TensorFlow** - Google-backed, production-focused, TF Serving
3. **JAX** - NumPy-like API, powerful transformations, newer
4. **MXNet** - AWS-backed, efficient, less community momentum

## Decision

We chose **PyTorch**.

## Consequences

### Positive
- Pythonic and intuitive API → faster development
- Dynamic graphs → easier debugging and experimentation
- Excellent ecosystem (Hugging Face, Lightning, etc.)
- Strong research community → latest models available
- TorchScript for production deployment
- Native distributed training support

### Negative
- Historically weaker production tooling vs TensorFlow (improving)
- Slightly higher memory usage than TensorFlow
- Some enterprise customers prefer TensorFlow

### Neutral
- Need to learn PyTorch conventions vs alternatives
- GPU memory management requires attention

## Related Decisions

- ADR-0008: Use PyTorch DDP for distributed training (builds on this)
- ADR-0012: Use TorchScript for inference (builds on this)

## Notes

This decision was made early in the project (2024) based on team expertise and research focus. It has proven valuable for rapid iteration on new architectures.
That's it! Simple markdown file. No complex organization needed. Just context, alternatives, decision, consequences.

TL;DR Answers
"Where does a feature go?"

GitHub Issue (tracking + what)
RFC if large (design proposal + why)
Track's current-work.md (status updates)
GitHub Projects (coordination view)
Pull Requests (implementation)
Documentation (user guide)
ADR if architecturally significant (decision record)
Changelog (what shipped)
"Are ADRs more organized usually?"

No, they're intentionally simple! Just numbered markdown files (0001, 0002, etc.) with a good index.md for discovery. Only need categories if you have 50+ ADRs. The organization comes from the index, not the file structure.

"When do I write an ADR?"

Ask: "Will someone in 6 months ask 'why did we do it this way?'" → If yes, write ADR. Typically for framework choices, data formats, API designs, architecture patterns. Not for features, bugs, or small refactors.

Does this clear it up? Want me to walk through a specific feature from YOUR project to make it concrete?

Yes I'm asking about the docs site specifically, is there a place to update that for features m

Ah, great question! You're asking: "When we ship a feature, where on the docs site do users learn about it?"

The answer: Multiple places, depending on the audience and type of information. Let me map this out clearly.

Where features are documented on the site
1. Changelog (High-level "what changed")
Location: docs/changelog.md
Audience: Everyone - first place people look
Updated: Automatically or manually with each release

markdown
# Changelog

All notable changes to MassGen will be documented here.

## [0.8.2] - 2025-10-04

### Added
- **Multi-GPU data loading support** - Train on 8 GPUs with 2.1x speedup. Enable with `distributed=True` in DataLoader. [#246](link-to-pr)
- **Async data preprocessing pipeline** - 30% faster data loading via background workers. [#251](link-to-pr)
- New evaluation metrics: CLIP score, FID score for image generation

### Changed
- **BREAKING:** Minimum PyTorch version now 1.10+ (required for distributed training)
- Improved model checkpoint format - now includes optimizer state

### Fixed
- Data augmentation memory leak in batch processing [#248](link-to-pr)
- Generation API timeout with large batch sizes [#253](link-to-pr)

### Performance
- Training throughput: 450 → 620 samples/sec on 8-GPU setup
- Memory usage reduced by 15% in inference mode

## [0.8.1] - 2025-09-30

### Added
- Transformer-based architecture support
- HDF5 data format support for large datasets

...
Key: One-liner per feature with link to details. Users scan this to see "what's new."

2. Feature-specific guide (How to use it)
Location: docs/guides/[feature-name].md or section in existing guide
Audience: Users who want to use the feature
Updated: When feature merges

For the multi-GPU example, you'd update:

File: docs/guides/training.md

markdown
# Training Models

## Basic Training

[existing content...]

## Multi-GPU Training

**New in v0.8.2:** MassGen now supports distributed training across multiple GPUs.

### Quick Start
```python
from massgen.data import MassGenDataLoader
from massgen.training import DistributedTrainer

# Create distributed dataloader
dataloader = MassGenDataLoader(
    dataset,
    batch_size=32,
    distributed=True  # Enable multi-GPU
)

# Train across all available GPUs
trainer = DistributedTrainer(model, dataloader)
trainer.train(epochs=10)
Command Line
bash
# Automatically uses all GPUs
python train.py --distributed

# Specify GPU count
python train.py --distributed --num-gpus 4
Performance
On an 8-GPU setup (NVIDIA A100):

Training throughput: 620 samples/sec (vs 290 single-GPU)
GPU utilization: 88% (vs 60% single-GPU)
Expected speedup: ~2.1x on 8 GPUs, ~1.8x on 4 GPUs
Requirements
PyTorch 1.10 or higher
Multiple CUDA-capable GPUs
Sufficient GPU memory for batch size × num_gpus
Troubleshooting
Out of memory errors:

python
# Reduce per-GPU batch size
dataloader = MassGenDataLoader(
    dataset,
    batch_size=16,  # Smaller batch per GPU
    distributed=True
)
Uneven GPU utilization: Ensure your dataset size is divisible by number of GPUs, or enable drop_last=True:

python
dataloader = MassGenDataLoader(
    dataset,
    batch_size=32,
    distributed=True,
    drop_last=True  # Drop remainder batches
)
See Architecture: Data Pipeline for implementation details.


---

### 3. **Architecture documentation** (Technical deep-dive)

**Location:** `docs/architecture/[component].md`
**Audience:** Contributors, advanced users, people debugging
**Updated:** When architecture changes

**File: `docs/architecture/data-pipeline.md`**
```markdown
# Data Pipeline Architecture

## Overview

[existing content...]

## Distributed Loading

**Added in v0.8.2**

MassGen uses PyTorch's DistributedDataParallel (DDP) for multi-GPU data loading.

### Architecture
┌─────────────────────────────────────────┐
│         MassGenDataLoader               │
│  ┌─────────────────────────────────┐   │
│  │  Distributed Sampler            │   │
│  │  (splits data by GPU rank)      │   │
│  └──────────┬──────────────────────┘   │
│             │                            │
│     ┌───────┴────────┐                  │
│     │                 │                  │
│  ┌──▼───┐   ┌──────▼──┐   ┌────────┐   │
│  │GPU 0 │   │  GPU 1  │   │ GPU N  │   │
│  │Worker│   │ Worker  │   │ Worker │   │
│  └──┬───┘   └────┬────┘   └───┬────┘   │
│     │            │            │         │
│     └────────────┴────────────┘         │
│              Batch Queue                │
└─────────────────────────────────────────┘


### Data Sharding Strategy

Each GPU receives a disjoint subset of the dataset:
- **GPU 0:** samples [0, N/k)
- **GPU 1:** samples [N/k, 2N/k)
- **GPU k-1:** samples [(k-1)N/k, N)

Where N = dataset size, k = number of GPUs.

### Synchronization

Gradients are synchronized across GPUs after each batch using `all_reduce` operation.

### Implementation Details

Key classes:
- `DistributedSampler`: Handles data sharding by rank
- `MultiGPUDataLoader`: Wraps PyTorch DataLoader with DDP
- `DistributedTrainer`: Manages training loop and gradient sync

See [ADR-0008](../decisions/0008-pytorch-ddp.md) for design rationale.
4. API Reference (If it's a public API)
Location: docs/api/data.md (auto-generated or manual)
Audience: Developers integrating MassGen
Updated: Auto-generated from docstrings

markdown
# API Reference: Data Loading

## MassGenDataLoader

::: massgen.data.MassGenDataLoader
    options:
      show_root_heading: true
      show_source: true
If using mkdocstrings plugin, this auto-generates from your Python docstrings:

python
class MassGenDataLoader:
    """High-performance data loader for MassGen.

    Supports single-GPU and distributed multi-GPU training with
    automatic data sharding and batching.

    Args:
        dataset: PyTorch Dataset or path to data files
        batch_size: Samples per batch per GPU
        distributed: Enable multi-GPU distributed loading (default: False)
        num_workers: Background workers for data loading (default: 4)
        drop_last: Drop incomplete final batch (default: False)

    Examples:
        Single-GPU training:
        >>> loader = MassGenDataLoader(dataset, batch_size=32)

        Multi-GPU training:
        >>> loader = MassGenDataLoader(
        ...     dataset,
        ...     batch_size=32,
        ...     distributed=True
        ... )

    New in version 0.8.2:
        Added `distributed` parameter for multi-GPU support.
    """
5. What's New / Release Highlights (Optional but nice)
Location: docs/whats-new.md or section on homepage
Audience: Casual users scanning for cool updates
Updated: Major releases only

markdown
# What's New in MassGen

## Version 0.8 Highlights (October 2025)

### 🚀 Multi-GPU Training
Train models 2x faster on multi-GPU setups! Simply add `distributed=True` to your DataLoader.
```python
loader = MassGenDataLoader(dataset, batch_size=32, distributed=True)
Learn more →

⚡ Performance Improvements
30% faster data loading with async preprocessing
15% lower memory usage in inference
Improved model checkpoint format
🎨 New Features
Transformer architecture support
CLIP and FID evaluation metrics
HDF5 data format for large datasets
Full changelog →

Previous Releases
Version 0.7 (September 2025)
...


---

## The complete flow for documenting a feature

Using multi-GPU as example:

### During Development (PR #246)

**In the PR itself, add:**
```markdown
## Documentation Updates

- [ ] Updated `docs/guides/training.md` with multi-GPU section
- [ ] Updated `docs/architecture/data-pipeline.md` with distributed loading architecture
- [ ] Updated API docstrings in `massgen/data/dataloader.py`
- [ ] Added changelog entry for v0.8.2
Files you actually edit:
docs/guides/training.md - Add "Multi-GPU Training" section (how-to)
docs/architecture/data-pipeline.md - Add "Distributed Loading" section (technical details)
massgen/data/dataloader.py - Update docstrings (API docs auto-generate)
docs/changelog.md - Add entry under "Unreleased" or "[0.8.2]"
On Release Day
Update changelog date:
markdown
   ## [0.8.2] - 2025-10-04  # Change from "Unreleased"
(Optional) Update docs/whats-new.md if it's a major feature
That's it! MkDocs auto-rebuilds and deploys
Organizing your docs/ for features
Here's how successful projects structure it:

docs/
├── index.md                          # Homepage - highlights recent features
├── changelog.md                      # All releases chronologically
├── whats-new.md                      # (Optional) Marketing-style highlights
│
├── getting-started/                  # NEW USER PATH
│   ├── installation.md
│   ├── quickstart.md                 # Mentions new features in examples
│   └── tutorials.md
│
├── guides/                           # HOW-TO GUIDES (task-oriented)
│   ├── training.md                   # ← Multi-GPU section lives here
│   ├── data-loading.md               # ← Async preprocessing section here
│   ├── evaluation.md                 # ← New metrics section here
│   ├── model-deployment.md
│   └── troubleshooting.md
│
├── architecture/                     # TECHNICAL DEEP-DIVES
│   ├── overview.md
│   ├── data-pipeline.md              # ← Distributed loading details here
│   ├── models.md
│   ├── generation.md
│   └── evaluation.md
│
├── api/                              # API REFERENCE (auto-generated)
│   ├── data.md                       # ← Auto-docs for DataLoader
│   ├── models.md
│   ├── training.md
│   └── generation.md
│
├── development/                      # FOR CONTRIBUTORS
│   ├── contributing.md
│   ├── testing.md
│   └── release-process.md
│
├── decisions/                        # HISTORICAL DECISIONS
│   ├── index.md
│   └── 0008-pytorch-ddp.md           # ← Why we chose DDP
│
└── tracks/                           # TEAM COORDINATION
    └── [internal coordination pages]
Where users find features
User journey:

"What's new?" → Read changelog.md
"How do I use multi-GPU?" → Search docs, find guides/training.md#multi-gpu-training
"What are the parameters?" → Check api/data.md for MassGenDataLoader API
"How does it work internally?" → Read architecture/data-pipeline.md#distributed-loading
"Why this approach?" → Check decisions/0008-pytorch-ddp.md for rationale
Automation: Make this easier
Auto-generate changelog from PRs
Option 1: Use conventional commits

If your PR titles follow convention:

feat(data): add multi-GPU data loading support
fix(training): resolve memory leak in data augmentation
perf(inference): reduce memory usage by 15%
Then use git-cliff or release-drafter to auto-generate changelog:

yaml
# .github/workflows/release-drafter.yml
name: Release Drafter
on:
  push:
    branches: [main]
jobs:
  update_release_draft:
    runs-on: ubuntu-latest
    steps:
      - uses: release-drafter/release-drafter@v5
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
Config: .github/release-drafter.yml

yaml
name-template: 'v$RESOLVED_VERSION'
tag-template: 'v$RESOLVED_VERSION'
categories:
  - title: '🚀 Features'
    labels:
      - 'feature'
      - 'enhancement'
  - title: '🐛 Bug Fixes'
    labels:
      - 'bug'
      - 'fix'
  - title: '⚡ Performance'
    labels:
      - 'performance'
  - title: '📚 Documentation'
    labels:
      - 'documentation'
change-template: '- $TITLE (#$NUMBER)'
template: |
  ## What's Changed

  $CHANGES
This auto-drafts release notes from merged PRs!

Auto-deploy docs on merge
yaml
# .github/workflows/docs.yml
name: Deploy Docs
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.x
      - run: pip install mkdocs-material mkdocs-git-revision-date-localized-plugin
      - run: mkdocs gh-deploy --force
Now docs auto-update when PRs merge!

Quick reference card
When you ship a feature, update:

File	What to add	Required?
docs/changelog.md	One-line summary + link to PR	✅ Always
docs/guides/[relevant].md	How-to section with examples	✅ If user-facing
docs/architecture/[component].md	Technical implementation details	⚠️ If complex/architectural
Docstrings in code	API parameter docs	✅ If public API
docs/whats-new.md	Highlight if major	⚠️ Optional
docs/decisions/NNNN-*.md	ADR if architectural choice	⚠️ If significant decision
The minimum for every feature:

✅ Changelog entry
✅ Update relevant guide OR create new guide section
✅ Update docstrings if it's a public API
That's it! Most features need just 2-3 file edits.

Your PR #179 specifically
Looking at your current docs structure, here's what you should add to make features easy to document:

Add to your mkdocs.yml:
yaml
nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started.md
    - Quick Start: quickstart.md
  - User Guides:                      # NEW - where feature how-tos live
    - Training: guides/training.md
    - Data Loading: guides/data.md
    - Generation: guides/generation.md
    - Evaluation: guides/evaluation.md
  - Architecture:
    - Overview: architecture.md
    - [existing sections...]
  - API Reference: api/               # Auto-generated
  - Changelog: changelog.md           # NEW - critical!
Create these new files:
docs/changelog.md:

markdown
# Changelog

All notable changes to MassGen are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Initial MkDocs documentation structure

## [0.7.0] - 2025-09-01

### Added
- Initial release of MassGen
- Basic data loading pipeline
- Transformer-based generation models

[Unreleased]: https://github.com/Leezekun/MassGen/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/Leezekun/MassGen/releases/tag/v0.7.0
docs/guides/training.md:

markdown
# Training Guide

How to train MassGen models for various tasks.

## Basic Training

[Your existing training content...]

## Advanced Topics

### Distributed Training
(Coming soon - add when multi-GPU feature ships)

### Custom Architectures
(Coming soon)
Now when someone ships multi-GPU, they just add a section to guides/training.md and entry to changelog.md. Done!

TL;DR: Features are documented in:

Changelog (one-liner, always)
Guides (how-to use it, if user-facing)
Architecture (deep technical details, if complex)
API docs (auto-generated from docstrings)
Most features = 2-3 file edits. Set up changelog.md and guides/ structure in your PR #179 and you're golden!

I think we should do doc changes that auto populate the readme. Right now we have a structured readme if you wanna look. Eventually id like to automate a bunch of stuff. And please give high level directives as well for how developers may integrate and organize their thoughts in what we discussed


favicon
Fetched GitHub - Leezekun/MassGen: 🚀 MassGen: A Multi-Agent Scaling System Inspired by Grok Heavy and Gemini Deep Think. Discord channel: https://discord.com/invite/VVrT2rQaz5
github.com

Perfect! I can see your README is well-structured and feature-rich. Let me give you both the automation strategy for keeping README in sync with docs, and high-level developer directives for organizing work.

Part 1: Auto-populate README from Docs
Your README has a great structure. The key is to identify which sections should be single-source-of-truth and auto-sync.

Strategy: Use "includes" and automation
Step 1: Identify README sections that should sync

Looking at your README, these sections should auto-populate:

README Section	Source in Docs	Sync Method
Features table	docs/index.md or docs/features.md	Include or script
Installation	docs/getting-started/installation.md	Include
Quick start examples	docs/getting-started/quickstart.md	Include
CLI parameters table	Auto-generate from code	Script
Supported models list	massgen/utils.py	Script
Changelog highlights	docs/changelog.md (latest)	Script
Implementation Option 1: MkDocs Macros (Recommended for you)
Install plugin:

bash
pip install mkdocs-macros-plugin
Update mkdocs.yml:

yaml
plugins:
  - search
  - macros  # Add this

extra:
  readme_sync: true  # Flag to control behavior
Create docs/_includes/ directory with reusable content:

File: docs/_includes/installation.md

markdown
```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
pip install uv
uv venv
source .venv/bin/activate # On macOS/Linux
uv pip install -e .
Create a .env file in the massgen/backends/ directory with your API keys:

bash
# Copy example configuration
cp massgen/backends/.env.example massgen/backends/.env

# Edit with your API keys
OPENAI_API_KEY=sk-your-openai-key-here
XAI_API_KEY=xai-your-xai-key-here
GEMINI_API_KEY=your-gemini-key-here
```

Then in both README.md AND docs/getting-started/installation.md:

In README.md:

markdown
## 🚀 Quick Start

{% include "_includes/installation.md" %}
In docs/getting-started/installation.md:

markdown
# Installation

{% include "_includes/installation.md" %}

## Additional Setup

[More detailed setup information specific to docs...]
Now installation instructions live in ONE place (docs/_includes/installation.md) and sync everywhere!

Implementation Option 2: Python Script (More control)
Create a script that generates parts of README from canonical sources:

File: scripts/generate_readme.py

python
#!/usr/bin/env env python3
"""
Generate README.md from docs sources and code introspection.
"""

import re
from pathlib import Path
from typing import Dict, List
import yaml

# Load configuration
def load_supported_models() -> List[str]:
    """Extract supported models from utils.py"""
    utils_path = Path("massgen/utils.py")
    content = utils_path.read_text()

    # Extract model names (adjust regex based on your code structure)
    models = re.findall(r'"([^"]+)":\s*{[^}]*"provider"', content)
    return sorted(set(models))

def load_cli_parameters() -> List[Dict[str, str]]:
    """Extract CLI parameters from argparse or click decorators"""
    cli_path = Path("cli.py")
    content = cli_path.read_text()

    # Parse CLI arguments (adjust based on your CLI framework)
    params = []
    # Example pattern for argparse: parser.add_argument('--name', help='description')
    pattern = r'--(\w+)[\s\S]*?help=["\']([^"\']+)'

    for match in re.finditer(pattern, content):
        params.append({
            "param": f"--{match.group(1)}",
            "description": match.group(2)
        })

    return params

def load_latest_changelog(num_versions: int = 1) -> str:
    """Extract latest changelog entries"""
    changelog_path = Path("docs/changelog.md")
    content = changelog_path.read_text()

    # Extract first N version sections
    versions = re.findall(r'## \[[\d.]+\].*?\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    return "\n\n".join(versions[:num_versions])

def generate_readme():
    """Generate README from template and sources"""

    template_path = Path("README.template.md")
    readme_path = Path("README.md")

    # Load template
    template = template_path.read_text()

    # Get dynamic content
    models = load_supported_models()
    cli_params = load_cli_parameters()
    changelog = load_latest_changelog(1)

    # Replace markers in template
    replacements = {
        "{{SUPPORTED_MODELS}}": "\n".join(f"- `{m}`" for m in models),
        "{{CLI_PARAMETERS}}": "\n".join(
            f"| `{p['param']}` | {p['description']} |"
            for p in cli_params
        ),
        "{{LATEST_CHANGELOG}}": changelog,
        "{{INSTALLATION}}": Path("docs/_includes/installation.md").read_text(),
        "{{QUICKSTART}}": Path("docs/_includes/quickstart.md").read_text(),
    }

    result = template
    for marker, content in replacements.items():
        result = result.replace(marker, content)

    # Write README
    readme_path.write_text(result)
    print(f"✅ Generated {readme_path}")

if __name__ == "__main__":
    generate_readme()
File: README.template.md (your current README with markers)

markdown
# 🚀 MassGen

[Your intro content...]

## 🚀 Quick Start

{{INSTALLATION}}

## 📊 Supported Models

{{SUPPORTED_MODELS}}

## 🎯 Usage

{{QUICKSTART}}

### CLI Parameters

| Parameter | Description |
|-----------|-------------|
{{CLI_PARAMETERS}}

## 📝 What's New

{{LATEST_CHANGELOG}}

[Rest of your README...]
Run on every commit via pre-commit hook:

File: .pre-commit-config.yaml

yaml
repos:
  - repo: local
    hooks:
      - id: generate-readme
        name: Generate README
        entry: python scripts/generate_readme.py
        language: system
        pass_filenames: false
        stages: [commit]
Or via GitHub Actions:

File: .github/workflows/update-readme.yml

yaml
name: Update README
on:
  push:
    paths:
      - 'docs/**'
      - 'massgen/utils.py'
      - 'cli.py'
    branches: [main]

jobs:
  update-readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Generate README
        run: python scripts/generate_readme.py

      - name: Commit changes
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git diff --quiet && git diff --staged --quiet || (git add README.md && git commit -m "docs: auto-update README from docs [skip ci]")
          git push
Now README auto-updates when docs or code changes!

My Recommendation for MassGen
Use a hybrid approach:

Installation/Quickstart: Keep in docs/_includes/ and use mkdocs-macros to include in both README and docs
CLI parameters: Auto-generate from cli.py using script
Supported models: Auto-generate from massgen/utils.py
Changelog highlights: Auto-extract from docs/changelog.md
Quick win for this week:

Create docs/_includes/installation.md
Move your installation section there
Add {% include "_includes/installation.md" %} to README
Install mkdocs-macros plugin
Test that both render correctly
Part 2: High-Level Developer Directives
Let me give you a mental model and workflow guide for how developers should think about organizing their work with everything we discussed.

The Developer's Mental Model
              ┌─────────────────────────────────────┐
              │     DEVELOPER MENTAL MODEL          │
              └─────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
         ┌────▼─────┐                   ┌────▼─────┐
         │  DOING   │                   │ DECIDING │
         │  (Work)  │                   │(Choices) │
         └────┬─────┘                   └────┬─────┘
              │                               │
    ┌─────────┼─────────┐          ┌─────────┼─────────┐
    │         │         │          │         │         │
┌───▼───┐ ┌──▼───┐ ┌───▼───┐  ┌───▼───┐ ┌──▼───┐ ┌───▼────┐
│Issues │ │ PRs  │ │Track  │  │ RFCs  │ │ ADRs │ │ Docs   │
│(What) │ │(How) │ │Pages  │  │(What  │ │(Why  │ │(Guide  │
│       │ │      │ │(Status│  │ if?)  │ │ did?)│ │ users) │
└───────┘ └──────┘ └───────┘  └───────┘ └──────┘ └────────┘
The Five Core Questions Every Developer Asks
Give them a clear answer for each:

1. "What should I work on?" → Check your track's docs/tracks/[your-track]/current-work.md
→ Look at GitHub Projects filtered by your track
→ Attend weekly track sync

2. "How should I implement this?" → Check existing ADRs for architectural patterns
→ Write RFC if it affects multiple tracks or is architecturally significant
→ Otherwise just start coding

3. "Where do I track progress?" → Update GitHub issue status
→ Comment on progress in issue
→ Track lead updates current-work.md weekly

4. "Who do I need to coordinate with?" → Check RFC/issue for dependencies
→ Post in cross-track channel if blocking others
→ Attend bi-weekly cross-team sync

5. "How do I document this?" → Update relevant guide in docs/guides/
→ Add changelog entry
→ Update docstrings if public API
→ Write ADR if you made significant architectural choice

High-Level Directives (Print and Post)
MassGen Developer Workflow Guide
Document
Quick Start Automation for MassGen
Here's what you can implement this week to start automating:

Week 1: Critical Path
Day 1-2: Set up includes structure

bash
mkdir -p docs/_includes
Create these files:

docs/_includes/installation.md (from current README)
docs/_includes/quickstart.md (from current README)
docs/_includes/features.md (from current README features table)
Install plugin:

bash
pip install mkdocs-macros-plugin
Add to mkdocs.yml:

yaml
plugins:
  - search
  - macros
Update README.md and docs to use includes:

markdown
## Installation

{% include "_includes/installation.md" %}
Day 3-4: Auto-generate model list

Create scripts/generate_model_docs.py:

python
#!/usr/bin/env python3
from pathlib import Path
import re

def extract_models():
    utils = Path("massgen/utils.py").read_text()
    # Adjust regex to match your model registration pattern
    models = re.findall(r'["\']([^"\']+)["\'].*?provider', utils)
    return sorted(set(models))

def update_models_doc():
    models = extract_models()
    content = "# Supported Models\n\n"
    content += "\n".join(f"- `{m}`" for m in models)

    Path("docs/_includes/models.md").write_text(content)
    print(f"✅ Updated models list: {len(models)} models")

if __name__ == "__main__":
    update_models_doc()
Run before commits:

yaml
# .github/workflows/update-docs.yml
name: Update Generated Docs
on: [push, pull_request]
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: python scripts/generate_model_docs.py
      - run: |
          if [[ $(git status --porcelain) ]]; then
            echo "⚠️ Generated docs are out of sync. Run: python scripts/generate_model_docs.py"
            exit 1
          fi
Day 5: Changelog automation

Install:

bash
pip install git-cliff
Create .cliff.toml:

toml
[changelog]
header = "# Changelog\n\n"
body = """
{% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | upper_first }}
    {% for commit in commits %}
        - {{ commit.message | upper_first }} ([{{ commit.id | truncate(length=7, end="") }}]({{ commit.id }}))\
    {% endfor %}
{% endfor %}
"""

[git]
conventional_commits = true
filter_unconventional = true
commit_parsers = [
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    { message = "^perf", group = "Performance" },
    { message = "^doc", group = "Documentation" },
]
Auto-generate changelog:

bash
git cliff --output docs/changelog.md
Add to GitHub Actions to auto-update.

Week 2: GitHub Projects Integration
Set up project with custom fields:

Go to MassGen repo → Projects → New Project
Add custom fields:
Track (single select): Data, Models, Generation, Evaluation, Infrastructure
Priority (single select): P0, P1, P2, P3
Size (single select): XS, S, M, L, XL
Sprint (iteration): Weekly sprints
Create views:
Board by Track (group by Track)
Current Sprint (filter by Sprint = current)
Roadmap (layout: roadmap)
Auto-assign issues to project:

yaml
# .github/workflows/auto-project.yml
name: Add Issues to Project
on:
  issues:
    types: [opened]
jobs:
  add-to-project:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/add-to-project@v0.5.0
        with:
          project-url: https://github.com/users/Leezekun/projects/1
          github-token: ${{ secrets.PAT_TOKEN }}
Week 3: Track Pages Setup
Create track structure:

bash
mkdir -p docs/tracks/{data,models,generation,evaluation}
For each track, create:

index.md (charter - copy template)
current-work.md (this week's work)
roadmap.md (next 3-6 months)
Template for current-work.md:

markdown
# [Track Name] - Current Work

**Week of:** {{ date }}

## This Week's Priorities

### P0 (Must Complete)
1. **[Feature Name]** (@owner)
   - Status: [Not Started/In Progress/Review/Done]
   - PR: #XXX
   - Blockers: None
   - Expected completion: [Day]

### P1 (Should Complete)
...

## Dependencies
- **Waiting on:** [other track] for [thing]
- **Blocking:** [other track] needs [thing]

## Completed This Week
- ✅ [Feature] merged in #XXX

---
*Updated: {{ date }} by @track-lead*
Week 4: ADR and RFC Templates
Create templates:

docs/decisions/template.md:

markdown
# ADR-XXXX: [Title]

**Status:** [Proposed | Accepted | Rejected | Superseded]
**Date:** YYYY-MM-DD
**Deciders:** [@people]

## Context
[What's the problem? Why do we need to decide?]

## Considered Options
1. Option A
2. Option B
3. Option C

## Decision
We chose [X] because [rationale].

## Consequences

### Positive
- Benefit 1

### Negative
- Tradeoff 1

## Implementation
- [Steps or PRs]
docs/rfcs/template.md:

markdown
# RFC-XXXX: [Title]

**Author:** @username
**Date:** YYYY-MM-DD
**Status:** [Proposed | Accepted | Rejected]
**Tracks Affected:** [List]

## Summary
[One paragraph overview]

## Motivation
[Why are we doing this?]

## Detailed Design
[Technical specification]

## Alternatives Considered
[What else did we think about?]

## Drawbacks
[What are the costs?]

## Unresolved Questions
[What needs more discussion?]
Developer Onboarding Checklist
Put this in CONTRIBUTING.md:

markdown
# Contributing to MassGen

## New Developer Onboarding

Welcome! Follow this checklist to get started:

### Week 1: Setup and Orientation
- [ ] Clone repo and run installation from docs
- [ ] Join Discord channel
- [ ] Read this workflow guide: [link to artifact above]
- [ ] Pick your primary track (ask maintainers if unsure)
- [ ] Join your track's channel
- [ ] Read your track's charter: `docs/tracks/[track]/index.md`
- [ ] Attend your track's weekly sync (observer)

### Week 2: First Contribution
- [ ] Pick an issue labeled `good-first-issue`
- [ ] Comment on issue saying you're working on it
- [ ] Read relevant ADRs for context
- [ ] Ask questions in track channel
- [ ] Open your first PR
- [ ] Respond to review feedback
- [ ] Celebrate your first merge! 🎉

### Week 3-4: Integration
- [ ] Attend cross-team sync meeting
- [ ] Start posting weekly "top 5" updates
- [ ] Propose a small improvement (issue or RFC)
- [ ] Review someone else's PR
- [ ] Update documentation for something you learned

### Ongoing
- Post daily standup updates (written)
- Update issues you're working on
- Ask questions publicly (help others learn)
- Write ADRs when making decisions
- Improve docs when you find gaps

## How We Work

[Link to the workflow guide artifact]

## Questions?

Ask in `#general` or your track channel. We're here to help!
TL;DR: Implementation Priority
This week (highest value, lowest effort):

✅ Create docs/_includes/ with installation/quickstart
✅ Install mkdocs-macros and use includes in README + docs
✅ Create scripts/generate_model_docs.py to auto-list models
✅ Set up git-cliff for changelog automation
Next week: 5. Create GitHub Project with custom fields 6. Set up track pages (docs/tracks/) 7. Create ADR/RFC templates

Week 3: 8. Write the Developer Workflow Guide artifact to docs/development/workflow.md 9. Add automation for README generation 10. Set up pre-commit hooks for docs checks

The key insight: Start with manual process that works, then automate. Don't build automation for a process you haven't validated yet.

Want me to generate any of those scripts or configs in full? Or help you think through which track structure makes sense for MassGen specifically?

A couple other things. We use Claude code with subagents. We want these to handle the less formulaic things like creating case studies and announcement texts. Please look online more about this and how to integrate it, as well as how to save it


Claude Code command line tool agentic coding documentation
10 results






















Claude Code sub-agents delegation documentation workflows
10 results






















Claude Code save subagent output artifacts documentation marketing content
10 results





















Perfect! Now I have comprehensive information about Claude Code and subagents. Let me create a detailed guide for integrating this into MassGen's documentation workflow.

Claude Code Subagents for MassGen Documentation
Document
Quick Start Implementation
Here's what you should do this week to get Claude Code subagents working for MassGen:

Day 1: Install and Setup
bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Create directories in MassGen repo
cd MassGen
mkdir -p .claude/agents
mkdir -p .claude/commands
mkdir -p docs/case-studies
mkdir -p docs/blog
mkdir -p docs/social
mkdir -p docs/_reviews

# Update .gitignore
echo ".claude/logs/" >> .gitignore
echo ".claude/cache/" >> .gitignore
echo "docs/_reviews/" >> .gitignore
Day 2: Create First Subagent
Start with case-study-writer (the most valuable for MassGen):

Copy the case-study-writer markdown from the artifact above
Save to .claude/agents/case-study-writer.md
Test it:
bash
claude

> "Use case-study-writer to create a case study from logs/[recent-session]/"
Day 3: Add Other Subagents
Add the other three subagents from the artifact:

announcement-writer.md
technical-editor.md
tutorial-creator.md
Day 4: Create Your First Workflow
Test the complete flow:

bash
> "Create a case study from logs/20250930_142530/"
# case-study-writer creates draft

> "Review it with technical-editor"
# technical-editor provides feedback

> "Apply the feedback and finalize"
# Main Claude makes edits

> "Commit it"
# Creates git commit
Day 5: Document for Your Team
Add to your CONTRIBUTING.md:

markdown
## Creating Content with Claude Code

MassGen uses Claude Code subagents for creative content:

### Case Studies
```bash
claude
> "Create a case study from logs/YYYYMMDD_HHMMSS/"
Release Announcements
bash
> "Create release announcement for vX.Y.Z"
Tutorials
bash
> "Create a tutorial for [feature]"
All subagents are in .claude/agents/. Output goes to docs/.


---

**The key insight:** Claude Code subagents handle the **creative, judgment-based** documentation work that can't be scripted, while your automation handles the **formulaic, structured** content. Together, they give you a complete documentation system that's both efficient and high-quality.

Want me to help you create any specific subagents for other MassGen needs, or help you set up the automation scripts to complement them?
