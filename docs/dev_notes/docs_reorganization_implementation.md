# MassGen Documentation Reorganization - Implementation Guide

**Date:** 2024-10-08
**Status:** Phase 1 Complete - Foundation Established

## Overview

This document tracks the implementation of the comprehensive documentation reorganization plan for MassGen. The goal is to create an "everything lives in the docs" approach that reduces communication barriers, enhances progress tracking, and leverages automation.

---

## ✅ Phase 1: Foundation (COMPLETED)

### Directory Structure Created

```
docs/
├── source/                          # Existing Sphinx docs
│   ├── architecture/                # NEW - Technical deep dives
│   ├── decisions/                   # NEW - ADRs (4 initial ADRs created)
│   │   ├── index.rst
│   │   ├── 0001-use-sphinx.md
│   │   ├── 0002-pytorch-framework.md
│   │   ├── 0003-multi-agent-architecture.md
│   │   └── 0004-case-driven-development.md
│   ├── rfcs/                        # NEW - Design proposals
│   │   └── index.rst
│   ├── tracks/                      # NEW - Team coordination
│   │   ├── data/
│   │   ├── models/
│   │   ├── generation/
│   │   └── evaluation/
│   └── guides/                      # NEW - Feature how-tos
├── _includes/                       # NEW - Reusable content snippets
│   ├── README.md
│   ├── installation.md
│   └── api-configuration.md
├── _templates/                      # NEW - Documentation templates
│   ├── adr-template.md
│   ├── rfc-template.md
│   ├── track-charter-template.md
│   ├── track-current-work-template.md
│   └── track-roadmap-template.md
└── case_studies/                    # Existing
```

### Scripts Created

```
scripts/
├── generate_readme.py              # README auto-generation from includes
└── extract_models.py               # Auto-extract supported models
```

### Initial ADRs Written

Four foundational Architecture Decision Records documenting key past decisions:

1. **ADR-0001: Use Sphinx for Documentation**
   - Documents choice of Sphinx over alternatives
   - Explains rationale and tradeoffs
   - Location: `docs/source/decisions/0001-use-sphinx.md`

2. **ADR-0002: Use PyTorch as ML Framework**
   - Documents ML framework choice
   - Explains ecosystem alignment
   - Location: `docs/source/decisions/0002-pytorch-framework.md`

3. **ADR-0003: Multi-Agent Collaborative Architecture**
   - Documents core architectural approach
   - Explains parallel processing and convergence
   - Location: `docs/source/decisions/0003-multi-agent-architecture.md`

4. **ADR-0004: Case-Driven Development Methodology**
   - Documents development methodology
   - Explains why each release has case study
   - Location: `docs/source/decisions/0004-case-driven-development.md`

### Templates Created

Five comprehensive templates for various documentation needs:

1. **ADR Template** (`docs/_templates/adr-template.md`)
   - Structure for documenting architectural decisions
   - Includes sections for context, options, consequences
   - Validation criteria and related decisions

2. **RFC Template** (`docs/_templates/rfc-template.md`)
   - Structure for design proposals
   - Detailed design, alternatives, implementation plan
   - Testing strategy and migration path

3. **Track Charter Template** (`docs/_templates/track-charter-template.md`)
   - Defines track mission, scope, ownership
   - Decision-making process
   - Dependencies and metrics

4. **Track Current Work Template** (`docs/_templates/track-current-work-template.md`)
   - Weekly priorities (P0, P1, P2)
   - Dependencies and blockers
   - Decisions made and metrics

5. **Track Roadmap Template** (`docs/_templates/track-roadmap-template.md`)
   - Current focus (4-6 weeks)
   - Medium-term goals (3-6 months)
   - Long-term vision (6+ months)
   - Risks and dependencies

---

## 🚧 Phase 2: Automation (IN PROGRESS)

### Next Steps

#### 2.1 README Auto-Generation Setup

**Tasks:**
1. Test `scripts/generate_readme.py`:
   ```bash
   python scripts/generate_readme.py --dry-run
   ```

2. Add markers to README.md (or create README.template.md):
   ```markdown
   ## Installation
   {{INSTALLATION}}

   ## API Configuration
   {{API_CONFIGURATION}}
   ```

3. Run generation:
   ```bash
   python scripts/generate_readme.py
   ```

4. Verify README updates correctly

#### 2.2 Model Extraction Enhancement

**Tasks:**
1. Test `scripts/extract_models.py`:
   ```bash
   python scripts/extract_models.py
   ```

2. Refine extraction logic based on actual backend structure

3. Integrate into documentation build

#### 2.3 GitHub Actions Integration

**Tasks:**
1. Create `.github/workflows/auto-docs.yml`
2. Add validation checks for documentation
3. Auto-generate README on docs changes
4. Integrate with existing docs workflow

---

## 📋 Phase 3: Team Coordination (PLANNED)

### 3.1 Populate Track Pages

For each track (data, models, generation, evaluation):

1. Copy templates from `docs/_templates/` to `docs/source/tracks/[track-name]/`
2. Fill in charter with actual information
3. Create initial current-work.md with current priorities
4. Create roadmap.md with known plans

### 3.2 GitHub Projects Setup

**Tasks:**
1. Create project board at https://github.com/Leezekun/MassGen/projects
2. Add custom fields:
   - Track (single select): data, models, generation, evaluation
   - Priority (single select): P0, P1, P2, P3
   - Size (single select): XS, S, M, L, XL
   - Sprint (iteration): Weekly sprints
3. Create views:
   - Board by Track
   - Current Sprint
   - Roadmap (timeline)
4. Configure automation to add new issues to project

### 3.3 Developer Workflow Guide

**Tasks:**
1. Create `docs/source/development/workflow-guide.md`
2. Document:
   - How to pick up work
   - When to write ADRs/RFCs
   - How to document features
   - How to use Claude Code subagents
   - Communication standards
3. Add to Sphinx documentation

---

## 🤖 Phase 4: Claude Code Enhancement (PLANNED)

### 4.1 Review Existing Subagents

Current agents in `.claude/agents/`:
- `case-study-writer.md` - Comprehensive, well-designed ✅
- `senior-code-reviewer.md` - Existing ✅

### 4.2 Create New Subagents

**Agents to add:**

1. **announcement-writer.md**
   - Generate release announcements
   - Pull from changelog and case studies
   - Format for different platforms (Discord, Twitter, blog)

2. **technical-editor.md**
   - Review and improve documentation
   - Check for clarity, completeness, accuracy
   - Suggest improvements

3. **tutorial-creator.md**
   - Create step-by-step tutorials
   - From feature specs to complete guides
   - Include examples and troubleshooting

4. **adr-writer.md** (Optional)
   - Help draft ADRs from decisions
   - Ensure all sections are complete
   - Suggest related ADRs

### 4.3 Document Subagent Workflows

Create `docs/source/development/subagent-workflows.md`:
- How to use each subagent
- Example invocations
- Best practices
- When to use vs manual creation

---

## 📊 Phase 5: Sphinx Integration (PLANNED)

### 5.1 Update Sphinx Configuration

Update `docs/source/conf.py` to:
- Include new sections in navigation
- Configure MyST parser for Markdown ADRs
- Add any needed extensions

### 5.2 Update Index Pages

Update `docs/source/index.rst` to link to:
- Architecture section
- Decisions (ADRs)
- RFCs
- Track coordination pages
- Guides

### 5.3 Navigation Improvements

Ensure easy navigation between:
- User-facing docs
- Developer coordination docs
- Architectural decisions
- Case studies

---

## 🎯 Quick Wins (Do First)

These provide immediate value with minimal effort:

### 1. Test README Generation (5 min)
```bash
python scripts/generate_readme.py --dry-run
```

### 2. Review ADRs (10 min)
Read the four initial ADRs in `docs/source/decisions/` and verify accuracy.

### 3. Add ADR Section to Sphinx (15 min)
Update `docs/source/index.rst` to include link to ADRs:
```rst
.. toctree::
   :caption: Documentation

   decisions/index
```

### 4. Test Model Extraction (5 min)
```bash
python scripts/extract_models.py
```

### 5. Create One Track Page (30 min)
Pick one track (e.g., data) and fill in the charter template with real information.

---

## 🚀 Immediate Actions for Team

### For Project Lead (@ncrispin)

1. **Review Phase 1 work** - Verify directory structure and templates meet needs
2. **Test automation scripts** - Run README generation and model extraction
3. **Define tracks** - Confirm tracks (data, models, generation, evaluation) or adjust
4. **Assign track leads** - Identify who owns each track
5. **Schedule kickoff** - Brief team on new documentation structure

### For Track Leads (Once Assigned)

1. **Read templates** - Familiarize with charter, current-work, roadmap templates
2. **Fill in charter** - Use `docs/_templates/track-charter-template.md` to create your track's charter
3. **Create current work** - Document current priorities in `current-work.md`
4. **Draft roadmap** - Create initial roadmap for next 3-6 months

### For All Developers

1. **Read ADRs** - Understand key architectural decisions in `docs/source/decisions/`
2. **Bookmark templates** - Know where to find ADR/RFC templates when needed
3. **Review workflow guide** - Once created, understand when to write ADRs vs RFCs

---

## 📖 Documentation Standards

### When to Write an ADR

Write an ADR when making decisions about:
- Framework or library choices
- Data format or storage decisions
- API design approaches
- Architecture patterns
- Testing strategies
- Deployment approaches

**Test:** Will someone in 6 months ask "why did we do it this way?" → Write ADR

### When to Write an RFC

Write an RFC when proposing:
- Features affecting multiple tracks
- Architecturally significant changes
- Features taking >2 weeks to implement
- Changes with multiple viable approaches

**Don't write RFC for:**
- Bug fixes
- Minor improvements
- Internal refactoring

### When to Update Track Pages

**current-work.md:**
- Update weekly (Monday recommended)
- Update during track sync meetings
- Add new P0/P1 items as they come up

**roadmap.md:**
- Review monthly
- Update when priorities shift
- Major revisions quarterly

---

## 🔄 Integration with Existing Workflow

### Current MassGen Workflow

- 3x weekly releases
- Daily standup meetings
- Case studies for each release
- Discord for communication

### Enhanced Workflow

1. **Feature Ideas** → Create issue, optionally RFC for big features
2. **Design Discussion** → RFC reviewed in track or cross-team
3. **Implementation** → Track in GitHub Projects and track current-work.md
4. **Case Study** → Use case-study-writer agent to create comprehensive case study
5. **ADR** (if architectural) → Document decision using ADR template
6. **Release** → Auto-generate announcement, update changelog
7. **Coordination** → Track pages show current state, GitHub Projects shows cross-track view

---

## 📝 Success Metrics

Track these to measure if reorganization is working:

- ✅ **Single source of truth**: Can answer "where is X documented?" easily
- ✅ **README freshness**: README auto-updates within 5 min of docs change
- ✅ **Feature documentation time**: <2 hours from feature complete to docs done
- ✅ **Onboarding time**: New contributors find info without asking
- ✅ **Meeting efficiency**: Track sync meetings <30 min (using current-work.md as agenda)
- ✅ **ADR adoption**: New architectural decisions have ADRs
- ✅ **Case study quality**: Claude Code agent produces publication-ready drafts

---

## 🛠️ Tools and Resources

### Scripts
- `scripts/generate_readme.py` - README auto-generation
- `scripts/extract_models.py` - Model list extraction

### Templates
- `docs/_templates/adr-template.md` - ADR structure
- `docs/_templates/rfc-template.md` - RFC structure
- `docs/_templates/track-*.md` - Track coordination templates

### Claude Code Agents
- `.claude/agents/case-study-writer.md` - Case study creation
- `.claude/agents/senior-code-reviewer.md` - Code review

### External Resources
- [ADR GitHub](https://adr.github.io/) - ADR best practices
- [Conventional Commits](https://www.conventionalcommits.org/) - Commit message format
- [Sphinx Documentation](https://www.sphinx-doc.org/) - Sphinx reference

---

## 🐛 Troubleshooting

### README Generation Not Working

**Issue:** `python scripts/generate_readme.py` produces no changes

**Solution:**
1. Check if markers like `{{INSTALLATION}}` exist in README.md
2. Verify includes exist in `docs/_includes/`
3. Run with `--dry-run` to see what would change

### Model Extraction Incomplete

**Issue:** `extract_models.py` finds fewer models than expected

**Solution:**
1. Check extraction patterns in script match your backend code
2. Update regex patterns based on actual backend structure
3. Add manual overrides if needed

### Sphinx Build Errors

**Issue:** `make html` fails after adding new sections

**Solution:**
1. Verify RST syntax in index files
2. Check that all referenced files exist
3. Ensure conf.py includes necessary extensions
4. Run with `-v` for verbose output

---

## 📅 Timeline Summary

- **Week 1 (COMPLETED)**: Foundation - Structure, templates, initial ADRs
- **Week 2 (CURRENT)**: Automation - README generation, CI/CD integration
- **Week 3**: Team Coordination - Track pages, GitHub Projects, workflow guide
- **Week 4**: Polish - Claude Code enhancements, testing, team training

---

## 🎉 What's Been Accomplished

- ✅ Complete directory structure for organized documentation
- ✅ Five comprehensive templates (ADR, RFC, 3x track)
- ✅ Four initial ADRs documenting key decisions
- ✅ Two automation scripts (README generation, model extraction)
- ✅ Reusable content includes for DRY documentation
- ✅ Foundation for team coordination system
- ✅ Clear plan for next phases

---

## 🤝 Contributing to This Effort

To help with documentation reorganization:

1. **Review Phase 1 work** - Check that structure/templates make sense
2. **Test automation** - Run scripts and report issues
3. **Write your track's charter** - If you're a track lead
4. **Write new ADRs** - Document decisions as you make them
5. **Improve templates** - Suggest enhancements based on usage
6. **Add automation** - Contribute new scripts or improvements

---

## 📞 Questions or Feedback

- **Discord**: #documentation channel
- **Issues**: Label with `documentation`
- **Direct**: @ncrispin

---

*This is a living document. Update as implementation progresses.*

*Last updated: 2024-10-08*
