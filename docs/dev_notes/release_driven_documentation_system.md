# MassGen Release-Driven Documentation System

**Date:** 2024-10-08
**Author:** @ncrispin
**Status:** Design Document

---

## Overview

This document describes a comprehensive release-driven documentation system for MassGen where:
- **Each release has its own documentation**
- **Every release includes a case study demonstrating self-evolution**
- **README auto-updates from release docs**
- **Changes flow automatically through the system**
- **Mix of automation scripts + Claude Code subagents**

---

## The Complete Flow

```
New Release v0.0.X
    ↓
1. PR merged with new features
    ↓
2. INTERACTIVE: Create case study (demonstrates self-evolution)
    ├─ Analyze PR changes
    ├─ Choose example that shows self-improvement
    ├─ Create config and recording guide
    ├─ Test feature (may find bugs)
    ├─ Fix issues discovered
    ├─ Record and edit video
    └─ Write complete case study
    ↓
3. Create release documentation
    ├─ Link to case study
    ├─ Auto-detect: new models, configs
    ├─ Document improvements found during case study
    └─ Extract git commits for changelog
    ↓
4. Update README automatically
    ├─ README "Latest Features" ← current release
    ├─ README "Previous Achievements" ← last N releases
    └─ Move old "Latest Features" → massgen/configs/README.md
    ↓
5. Update Roadmap from track pages
    ↓
6. Commit all changes
```

---

## Self-Evolution Integration

### The Hierarchy

```
Level 0: Self-Evolve MassGen from market insights
    ↓
├─ Level 1: Fix bugs (SWEbench-style)
├─ Level 2: Update new features
├─ Level 3: Case study release ← FOCUS OF THIS SYSTEM
├─ Level 4: Market analysis
├─ Level 5: Submit PR
└─ Level 6: Self-Review PR
```

**Every release demonstrates Level 3: Case Study Release**

Each case study must:
- Validate the new feature through real usage
- Demonstrate how it helps MassGen improve itself
- Discover and document limitations/improvements
- Link to the self-evolution hierarchy

---

## Directory Structure

```
docs/
├── releases/
│   ├── index.md                        # All releases with summaries
│   ├── v0.0.29/
│   │   ├── release-notes.md            # Main release documentation
│   │   ├── case-study.md               # Case study for this release
│   │   ├── improvements.md             # Issues found during case study
│   │   ├── RECORDING_GUIDE.md          # Step-by-step for user
│   │   └── video-script.md             # Captions and script
│   ├── v0.0.28/
│   │   └── [same structure]
│   └── ...
├── case_studies/                       # Legacy location (also copy here)
│   ├── v0.0.29-mcp-planning-mode.md
│   ├── README.md                       # Index of all case studies
│   └── ...
├── features/                           # Detailed feature documentation
│   ├── mcp-planning-mode.md
│   ├── filesystem-operations.md
│   ├── multimodal-support.md
│   └── ...
├── _includes/                          # Content copied to README
│   ├── installation.md
│   ├── latest-features.md             # Auto-generated from latest release
│   ├── filesystem-operations.md       # Abbreviated from features/
│   └── ...
```

---

## Release Documentation Template

**File:** `docs/releases/v0.0.X/release-notes.md`

```markdown
# MassGen v0.0.X Release

**Release Date:** YYYY-MM-DD
**Theme:** [Short theme description]
**Case Study:** [Case Study Link](./case-study.md)
**Video Demo:** [YouTube Link]

---

## Summary

[2-3 paragraph summary - this goes to README]

---

## Case Study: Self-Evolution Demonstration

This release demonstrates MassGen's self-evolution capability through **Level 3: Case Study Release**.

**Challenge:** [What problem did we solve?]

**Approach:** [How did we use MassGen to validate the feature?]

**Results:**
- ✅ [Success 1]
- ✅ [Success 2]
- ⚠️ **Discovered limitation:** [What we found]
- 📝 **Created issue #XXX** for future enhancement

**Key Insight:** [What we learned from the case study]

**Full Case Study:** [Link](./case-study.md)

---

## New Features

### Feature 1: [Name]

**Description:** [What it does]

**Motivation:** [Why we built it]

**Self-Evolution Aspect:** [How this helps MassGen improve itself]

**Configuration:**
```yaml
# Example config
```

**Quick Start:**
```bash
# Command to try it
```

**Documentation:** [Link to docs/features/X.md]

**Related:**
- Case Study: [Link](./case-study.md)
- ADR: [Link if applicable]
- Issue: [Link]

### Feature 2: [Name]
...

---

## New Models

[Auto-detected from backends/]

- **Provider X**: model-a, model-b, model-c
- **Provider Y**: model-d, model-e

---

## New Configuration Files

[Auto-detected from massgen/configs/]

### By Category

**Tools:**
- `tools/mcp/new_config.yaml` - Description
- `tools/filesystem/new_config2.yaml` - Description

**Teams:**
- `teams/research/new_team.yaml` - Description

---

## Improvements Discovered During Case Study

During case study creation, we discovered:

1. **[Limitation/Bug]**
   - **Impact:** [High/Medium/Low]
   - **Tracked in:** Issue #XXX
   - **Planned for:** vX.X.X

This demonstrates the value of thorough case studies - they validate features AND reveal improvements.

---

## Breaking Changes

[If any]

- **Change 1:** What changed, how to migrate
- **Change 2:** What changed, how to migrate

---

## Bug Fixes

- Fix #123: Description
- Fix #456: Description

---

## Performance Improvements

- Improvement 1: Impact
- Improvement 2: Impact

---

## Documentation Updates

- Updated: [Doc 1]
- Added: [Doc 2]
- Improved: [Doc 3]

---

## Contributors

Thanks to all contributors to this release:
- @contributor1
- @contributor2

---

## Next Release Preview

Looking ahead to v0.0.X+1:
- Planned feature 1 (from case study insights)
- Planned feature 2
```

---

## Case Study Template

**File:** `docs/releases/v0.0.X/case-study.md`

Uses the existing case study template from `docs/case_studies/case-study-template.md` but adds:

```markdown
## Self-Evolution Context

**Self-Evolution Level:** Level 3 - Case Study Release

**Self-Improvement Demonstrated:**
- How MassGen validated its own features
- How MassGen discovered its own limitations
- How MassGen documented itself
- How MassGen improved through the feedback loop

**Connection to Self-Evolution Hierarchy:**
- **Current Level (Level 3):** Case study creation and validation
- **Enables Level 4:** Insights from this case study inform market analysis
- **Progression:** This release sets up for [next capability]

---

[Rest of case study following existing template]
```

---

## Interactive Case Study Creation Workflow

### Step 1: Initialize (Automated)

```bash
python scripts/init_case_study.py v0.0.29 --pr 123
```

Creates:
- `docs/releases/v0.0.29/` directory
- Fetches PR changes
- Extracts new features
- Prepares for agent interaction

### Step 2: Propose Examples (Interactive)

```bash
claude
> "Create case study for v0.0.29 from PR #123"
```

**Agent Proposes:**
```
I've analyzed PR #123. Here are 3 case study options:

Option 1: MassGen Plans Social Media Campaign
- Feature: MCP Planning Mode
- Self-evolution: Safe coordination of destructive actions
- Example: "Plan Twitter campaign about v0.0.29"

Option 2: MassGen Refactors Its Own Codebase
- Feature: Read-before-delete + planning
- Self-evolution: Safe self-modification
- Example: "Refactor massgen/utils.py"

Option 3: MassGen Documents Itself
- Feature: Filesystem operations with planning
- Self-evolution: Self-documentation
- Example: "Create release notes from git history"

Which demonstrates the new features best?
```

### Step 3: Create Config & Guide (Agent)

**Human:** "Option 2 - refactoring"

**Agent creates:**
1. Configuration file: `massgen/configs/tools/planning/v0.0.29_self_refactoring.yaml`
2. Recording guide: `docs/releases/v0.0.29/RECORDING_GUIDE.md`

**Agent asks:** "Review the config. Should I proceed with recording guide?"

### Step 4: Recording (Human)

Human follows `RECORDING_GUIDE.md`:
1. Sets up test environment
2. Runs example while recording
3. Captures logs
4. Shares results with agent

### Step 5: Analysis & Issue Discovery (Interactive)

**Human:** "Here's the video and logs. Found issue: agents not reading files before refactoring"

**Agent analyzes:**
```
Found Issue: Read-before-delete doesn't cover refactoring

Should I:
1. Document as known limitation
2. Create issue for future
3. Try to fix now and re-run

Which approach?
```

**Human:** "Create issue and document limitation"

### Step 6: Video Editing (Agent-Assisted)

**Agent:** "Share video file. I'll create captions and editing instructions"

Produces:
- Caption file (SRT format)
- Video script with timestamps
- ffmpeg editing commands OR upload instructions

### Step 7: Write Complete Case Study (Agent)

Agent writes:
- `docs/releases/v0.0.29/case-study.md`
- `docs/case_studies/v0.0.29-mcp-planning-mode.md` (copy)
- Updates `docs/case_studies/README.md`

---

## Automation Scripts

### 1. Case Study Initializer

**File:** `scripts/init_case_study.py`

```python
#!/usr/bin/env python3
"""
Initialize case study creation for a release.

Usage:
    python scripts/init_case_study.py v0.0.29 --pr 123
    python scripts/init_case_study.py v0.0.29 --branch feature-branch
"""

# Creates:
# - docs/releases/v0.0.29/ directory
# - Fetches PR/branch changes
# - Extracts features from commits
# - Prepares summary for agent
```

### 2. Release Document Generator

**File:** `scripts/generate_release_doc.py`

```python
#!/usr/bin/env python3
"""
Generate release documentation template.

Usage:
    python scripts/generate_release_doc.py v0.0.29
    python scripts/generate_release_doc.py v0.0.29 --auto-detect
"""

# What it does:
# - Creates docs/releases/v0.0.29/release-notes.md from template
# - Auto-detects new models (compares to previous release tag)
# - Auto-detects new configs (git diff)
# - Extracts git commit messages for changelog
# - Finds linked issues/PRs
# - Links to case study
```

### 3. Model Detector

**File:** `scripts/detect_new_models.py`

```python
#!/usr/bin/env python3
"""
Detect new models added since last release.

Usage:
    python scripts/detect_new_models.py v0.0.28 v0.0.29
"""

# What it does:
# - Compares backends/ between two git tags
# - Finds new model identifiers
# - Updates "Supported Built-in Tools by Backend" table
# - Generates markdown for new models section
```

### 4. Config Detector

**File:** `scripts/detect_new_configs.py`

```python
#!/usr/bin/env python3
"""
Detect new configuration files since last release.

Usage:
    python scripts/detect_new_configs.py v0.0.28 v0.0.29
"""

# What it does:
# - Finds new .yaml files in massgen/configs/
# - Categorizes by directory (tools, teams, providers, etc.)
# - Extracts description from config file comments
# - Generates organized markdown list
```

### 5. README Release Updater

**File:** `scripts/update_readme_from_release.py`

```python
#!/usr/bin/env python3
"""
Update README.md from latest release documentation.

Usage:
    python scripts/update_readme_from_release.py v0.0.29
"""

# What it does:
# - Extracts summary from docs/releases/v0.0.29/release-notes.md
# - Updates README "Latest Features" section
# - Moves previous "Latest Features" to "Previous Achievements"
# - Archives old achievements to massgen/configs/README.md
# - Updates model tables
# - Updates configuration file lists
```

### 6. Case Study Validator

**File:** `scripts/validate_case_study.py`

```python
#!/usr/bin/env python3
"""
Validate case study completeness.

Usage:
    python scripts/validate_case_study.py v0.0.29
"""

# Checks:
# - Case study markdown exists
# - Video link works (or placeholder)
# - Config file exists and is valid YAML
# - All required sections complete
# - Links to issues/ADRs are valid
# - Self-evolution section included
```

### 7. Release Packager

**File:** `scripts/package_release.py`

```python
#!/usr/bin/env python3
"""
Package complete release documentation.

Usage:
    python scripts/package_release.py v0.0.29
"""

# Does:
# 1. Validates case study
# 2. Generates release notes
# 3. Updates README
# 4. Archives old features to massgen/configs/README.md
# 5. Updates release index
# 6. Creates git commit (or shows commands)
```

### 8. Roadmap Generator

**File:** `scripts/generate_roadmap.py`

```python
#!/usr/bin/env python3
"""
Generate roadmap from track pages.

Usage:
    python scripts/generate_roadmap.py
"""

# What it does:
# - Reads all docs/source/tracks/*/roadmap.md
# - Aggregates into project-level roadmap
# - Updates README roadmap section
# - Creates docs/ROADMAP.md
```

---

## Claude Code Subagents

### 1. Enhanced case-study-writer

**File:** `.claude/agents/case-study-writer.md`

**Enhancements:**
- **Self-Evolution Focus:** Every case study must demonstrate self-improvement
- **Interactive Process:** Multi-step workflow with human feedback
- **Issue Discovery:** Document problems found during case study creation
- **Video Coordination:** Guide video editing or provide instructions
- **Release Integration:** Link case study to release documentation

**New Workflow Sections:**
1. Analyze PR and propose 2-3 examples focused on self-evolution
2. Create configuration file after human selects example
3. Create comprehensive RECORDING_GUIDE.md
4. Analyze results and discover issues
5. Coordinate video editing
6. Write complete case study with self-evolution context

### 2. New: video-editor Agent

**File:** `.claude/agents/video-editor.md`

```markdown
---
name: video-editor
description: Edit and caption videos for MassGen case studies
tools: Bash, Read, Write, Grep
model: sonnet
---

You assist with video editing for case studies:

1. **Analyze Logs:** Read case study logs to identify key moments
2. **Create Captions:** Generate SRT subtitle file with explanations
3. **Video Script:** Create timestamped script of what happens when
4. **Editing Commands:** Provide ffmpeg commands for editing OR
5. **Upload Guide:** Instructions for uploading to YouTube with metadata

**Caption Style:**
- Technical but accessible
- Explain what's happening at key moments
- Highlight when new features are demonstrated
- Note when issues are discovered

**Output Files:**
- `video-captions.srt` - Subtitle file
- `video-script.md` - Timestamped script
- `video-editing.sh` - ffmpeg commands (optional)
- `upload-instructions.md` - YouTube upload guide
```

### 3. New: release-doc-writer Agent

**File:** `.claude/agents/release-doc-writer.md`

```markdown
---
name: release-doc-writer
description: Create comprehensive release documentation from PR and case study
tools: Bash, Read, Write, Grep, WebFetch
model: sonnet
---

You create complete release documentation:

1. **Analyze Changes:** Run git log, read PR description
2. **Extract Features:** Identify new features, improvements, fixes
3. **Link Case Study:** Reference case study findings
4. **Detect Models:** Call scripts/detect_new_models.py
5. **Detect Configs:** Call scripts/detect_new_configs.py
6. **Write Release Notes:** Complete docs/releases/vX.X.X/release-notes.md
7. **Identify Breaking Changes:** Highlight incompatibilities
8. **Document Discoveries:** Include issues found during case study

**Self-Evolution Integration:**
Always include section documenting how case study demonstrated self-improvement.
```

### 4. New: readme-updater Agent

**File:** `.claude/agents/readme-updater.md`

```markdown
---
name: readme-updater
description: Update README from release documentation
tools: Read, Edit, Write
model: sonnet
---

You update README.md from release documentation:

1. **Read Release Doc:** Extract summary and key features
2. **Update Latest Features:** Replace current with new release
3. **Archive Previous:** Move old to "Previous Achievements"
4. **Update Tables:** Model list, configuration examples
5. **Update Links:** Ensure all links point to correct versions
6. **Archive Old:** Move >2 releases old to massgen/configs/README.md
7. **Verify Consistency:** Check all version references match

**Important:** Maintain README format and structure exactly.
```

---

## Content Organization

### What Lives Where

| Content Type | Source | Copied To |
|--------------|--------|-----------|
| **Installation** | `docs/_includes/installation.md` | README.md |
| **Latest Features** | `docs/releases/v0.0.X/release-notes.md` → `docs/_includes/latest-features.md` | README.md |
| **Filesystem Ops** | `docs/features/filesystem-operations.md` → `docs/_includes/filesystem-ops.md` | README.md |
| **MCP Integration** | `docs/features/mcp-integration.md` → `docs/_includes/mcp-integration.md` | README.md |
| **Case Studies** | `docs/releases/v0.0.X/case-study.md` | `docs/case_studies/` (copy) |
| **Model List** | Auto-generated from backends | README.md + `docs/source/user_guide/models.rst` |
| **Config Examples** | `massgen/configs/` with inline docs | README.md (quick start) + full docs |
| **Roadmap** | `docs/source/tracks/*/roadmap.md` → aggregated | README.md + `docs/ROADMAP.md` |

### Single Source of Truth

**Feature Documentation:**
- **Full docs:** `docs/features/[feature-name].md`
- **README snippet:** `docs/_includes/[feature-name].md` (abbreviated)
- **Process:** Write full, then auto-generate or manually create snippet

**Release Information:**
- **Full release doc:** `docs/releases/v0.0.X/release-notes.md`
- **README summary:** Extracted automatically
- **Config README archive:** After 2 releases, moved to `massgen/configs/README.md`

**Case Studies:**
- **Primary:** `docs/releases/v0.0.X/case-study.md`
- **Copy:** `docs/case_studies/vX.X.X-feature-name.md`
- **Index:** `docs/case_studies/README.md`

---

## Complete Release Workflow

### Before Release

**Developer tasks:**
1. Develop features in PR
2. Update track `current-work.md` with progress
3. Write ADR if architectural changes
4. Merge PR

### Release Preparation (Interactive, ~2-3 hours total)

```bash
# ===== PHASE 1: CASE STUDY CREATION (Interactive) =====

# Step 1: Initialize (30 seconds)
python scripts/init_case_study.py v0.0.29 --pr 123

# Step 2: Interactive case study creation (1-2 hours)
claude
> "Create case study for v0.0.29 from PR #123"

# Agent proposes examples → you choose
# Agent creates config + recording guide
# You record video (15-30 min)
# You share results
# Agent analyzes, finds issues, documents
# Agent coordinates video editing
# Agent writes complete case study

# Step 3: Validate case study (30 seconds)
python scripts/validate_case_study.py v0.0.29

# ===== PHASE 2: RELEASE DOCUMENTATION (Mostly Automated) =====

# Step 4: Generate release doc (1 minute)
python scripts/generate_release_doc.py v0.0.29 --auto-detect

# Or use agent for more comprehensive:
claude
> "Complete release documentation for v0.0.29"

# Step 5: Update README (1 minute)
python scripts/update_readme_from_release.py v0.0.29

# Step 6: Update roadmap (optional, 1 minute)
python scripts/generate_roadmap.py

# Step 7: Package everything (1 minute)
python scripts/package_release.py v0.0.29

# Step 8: Review and commit
git diff
git add docs/ README.md massgen/configs/README.md .claude/
git commit -m "docs: v0.0.29 release with case study"
```

### After Release

1. Video uploads to YouTube
2. Update case study with video link
3. Announce on Discord/Twitter
4. Monitor for feedback
5. Create issues for improvements found during case study

---

## Examples

### Example Release Notes (with Case Study)

**File:** `docs/releases/v0.0.29/release-notes.md`

```markdown
# MassGen v0.0.29 Release

**Release Date:** 2024-10-08
**Theme:** MCP Planning Mode & Enhanced Safety
**Case Study:** [MCP Planning Mode Case Study](./case-study.md)
**Video Demo:** https://youtu.be/jLrMMEIr118

---

## Summary

Version 0.0.29 introduces **MCP Planning Mode**, a new coordination strategy that enables agents to plan tool usage without execution during collaboration. This prevents irreversible actions and provides safer multi-agent collaboration.

Key improvements include read-before-delete enforcement for file operations, enhanced MCP tool filtering with multi-level control, and extended planning mode support to Gemini backend. The release includes 7 new configuration files demonstrating planning mode across different MCP servers.

This release focuses on safety and control, ensuring agents collaborate effectively while maintaining strict guardrails around potentially destructive operations.

---

## Case Study: Self-Evolution Demonstration

This release demonstrates MassGen's self-evolution capability through **Level 3: Case Study Release**.

**Challenge:** Validate that planning mode prevents dangerous operations while allowing safe collaboration.

**Approach:** MassGen refactored its own codebase using planning mode with 5 agents collaborating on `massgen/utils.py`.

**Results:**
- ✅ Successfully demonstrated planning mode preventing premature execution
- ✅ Read-before-delete enforcement prevented unsafe operations
- ✅ Multiple agents safely proposed refactoring without conflicts
- ⚠️ **Discovered limitation:** Need read-before-modify enforcement for refactoring
- 📝 **Created issue #XXX** for future enhancement

**Key Insight:** Case study creation revealed that our safety enforcement was too narrow (delete-only). This led to expanding the concept to "read-before-modify" in future work.

**Full Case Study:** [MCP Planning Mode Case Study](./case-study.md)

---

## New Features

### Feature 1: MCP Planning Mode

**Description:** During coordination, agents plan tool usage without execution. Only the winning agent executes tools in final phase.

**Motivation:** Prevent multiple agents from executing irreversible actions (e.g., all agents tweeting, all agents deleting files).

**Self-Evolution Aspect:** Enables MassGen to safely use destructive tools during self-modification tasks.

**Configuration:**
```yaml
coordination:
  enable_planning_mode: true  # Enable planning mode
```

**Quick Start:**
```bash
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a comprehensive project structure with documentation"
```

**Documentation:** [MCP Planning Mode Guide](../../features/mcp-planning-mode.md)

**Related:**
- Case Study: [MCP Planning Mode](./case-study.md)
- ADR: ADR-00XX (to be written)
- Issue: #XXX (discovered during case study)

---

[Rest of release notes...]

---

## Improvements Discovered During Case Study

During case study creation, we discovered:

1. **Limitation: Read-before-delete doesn't cover refactoring operations**
   - **Impact:** Medium - agents can suggest refactoring without reading original code
   - **Root Cause:** FileOperationTracker only tracks delete operations
   - **Tracked in:** Issue #XXX
   - **Planned for:** v0.0.30
   - **Solution:** Extend to read-before-modify enforcement

2. **Enhancement: Better logging of planning decisions**
   - **Impact:** Low - would help debug planning mode
   - **Tracked in:** Issue #YYY
   - **Planned for:** v0.0.31

This demonstrates the value of thorough case studies - they validate features AND reveal improvements.
```

### Example README Archive

**File:** `massgen/configs/README.md` (at bottom)

```markdown
## Release History & Examples

### v0.0.29 (October 8, 2024)
**Theme:** MCP Planning Mode & Enhanced Safety

**Key Features:**
- MCP Planning Mode for safer coordination
- File Operation Safety with read-before-delete
- Enhanced Tool Filtering

**Case Study:**
- [MCP Planning Mode Case Study](../../docs/releases/v0.0.29/case-study.md)
- Demonstrated self-evolution through safe self-modification
- Discovered and documented limitations

**Example Configs:**
- `tools/planning/five_agents_filesystem_mcp_planning_mode.yaml`
- `tools/planning/five_agents_discord_mcp_planning_mode.yaml`

**[Full Release Notes](../../docs/releases/v0.0.29/release-notes.md)**

### v0.0.28 (October 6, 2024)
**Theme:** AG2 Framework Integration

**Key Features:**
- External agent framework integration
- AG2 adapter system
- Code execution environments

**Case Study:**
- [AG2 Integration Case Study](../../docs/releases/v0.0.28/case-study.md)

**[Full Release Notes](../../docs/releases/v0.0.28/release-notes.md)**

---

[Older releases archived here after 2-3 new releases...]
```

---

## Implementation Priority

### Week 1: Infrastructure
1. Create `docs/releases/` structure
2. Create `docs/features/` structure
3. Update case-study-writer agent with self-evolution focus
4. Create init_case_study.py script
5. Create validate_case_study.py script

### Week 2: Automation
1. Create generate_release_doc.py
2. Create detect_new_models.py
3. Create detect_new_configs.py
4. Create update_readme_from_release.py
5. Create package_release.py

### Week 3: Agents
1. Create video-editor agent
2. Create release-doc-writer agent
3. Create readme-updater agent
4. Test complete workflow

### Week 4: Integration & Example
1. Port v0.0.29 as first full example
2. Run complete workflow for next release
3. Document learnings and refine
4. Train team on new process
5. Create pre-release checklist

---

## Benefits

### For Self-Evolution
- ✅ Every release demonstrates self-improvement
- ✅ Case studies reveal edge cases and limitations
- ✅ Feedback loop: feature → case study → improvements → next feature
- ✅ Builds toward full self-evolution (Levels 1-6)
- ✅ Documents progression through self-evolution hierarchy

### For Documentation
- ✅ Every feature validated through real use
- ✅ Known limitations documented upfront
- ✅ Videos show realistic usage
- ✅ Users have working examples to copy
- ✅ README always current

### For Development
- ✅ Forces thorough testing before release
- ✅ Discovers issues before users do
- ✅ Creates high-quality examples
- ✅ Builds confidence in releases
- ✅ Clear historical record

### For Users
- ✅ Clear "what's new" summaries
- ✅ Working examples with videos
- ✅ Understand limitations before using
- ✅ See MassGen improving itself
- ✅ Easy navigation through releases

### For Project
- ✅ Consistent release documentation
- ✅ Reduced manual work (automation)
- ✅ Professional appearance
- ✅ Better discoverability
- ✅ Demonstrates innovation (self-evolution)

---

## Success Metrics

- ✅ Every release has comprehensive case study
- ✅ Case studies find ≥1 improvement per release
- ✅ Videos demonstrate features working
- ✅ Complete workflow takes <2 hours (excluding recording)
- ✅ Issues discovered during case studies lead to improvements
- ✅ README stays current automatically
- ✅ Users cite case studies as helpful
- ✅ Clear progression through self-evolution levels

---

## Open Questions

1. **Model table format:** How to best represent "Supported Built-in Tools by Backend" table?
   - **Proposal:** Auto-generate from scanning backends/ with script

2. **Feature docs structure:** Flat or categorized `docs/features/`?
   - **Proposal:** Start flat, categorize when >20 files

3. **Archive depth:** How many releases in README "Previous Achievements"?
   - **Proposal:** Last 3 releases in README, rest in configs README

4. **Roadmap source:** Pull from track pages or manual?
   - **Proposal:** Auto-generate from tracks, with manual override section

5. **Video hosting:** YouTube only or also embed in docs?
   - **Proposal:** YouTube primary, embed in docs site

6. **Case study length:** How detailed should they be?
   - **Proposal:** Follow existing template, typically 2-4 pages

---

## Next Steps

1. **Review with team** - Get feedback on this design
2. **Create first scripts** - Start with init_case_study.py
3. **Update case-study-writer** - Add self-evolution focus
4. **Test with v0.0.29** - Port as first example
5. **Iterate** - Refine based on real usage
6. **Document workflow** - Create step-by-step guide
7. **Train team** - Ensure everyone can use the system

---

*This is a living design document. Update as the system evolves.*

*Last updated: 2024-10-08 by @ncrispin*
