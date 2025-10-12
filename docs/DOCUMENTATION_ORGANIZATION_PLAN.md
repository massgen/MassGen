# Documentation Organization Plan

**Status:** 📋 Planning
**Created:** October 2025

## Current Issues

### 1. **Out-of-Sync Files**
- `CONTRIBUTING.md` (373 lines, comprehensive) ≠ `docs/source/development/contributing.rst` (62 lines, stale)
- `ROADMAP_v0.0.30.md` (217 lines, active) ≠ `docs/source/development/roadmap.rst` (67 lines, outdated)
- `CHANGELOG.md` (missing) ≠ `docs/source/changelog.rst` (71 lines, stale)

### 2. **Confusing ADR vs RFC Usage**
- **ADRs** = Architecture Decision Records (decisions already made)
- **RFCs** = Request for Comments (proposals for future features)
- **Problem:** Unclear when to use which, adds complexity

### 3. **Missing Documentation Contribution Guidelines**
Contributors don't know:
- When to add to existing user guide vs create new guide
- Where to document changes
- When to write ADRs vs RFCs vs design docs

### 4. **Roadmap Organization**
Current roadmap lacks:
- Clear short-term goals (addressing immediate issues)
- Long-term vision
- GitHub issue tracking integration

---

## Proposed Solutions

### Solution 1: Single Source of Truth Pattern

**Principle:** Markdown (.md) files in root are source of truth, .rst files in docs/ reference them.

**Implementation:**
```
Root Files (Source of Truth):
- CONTRIBUTING.md
- CHANGELOG.md
- ROADMAP.md (rename from ROADMAP_v0.0.30.md)

Sphinx Files (Reference/Include):
- docs/source/development/contributing.rst → includes CONTRIBUTING.md
- docs/source/changelog.rst → includes CHANGELOG.md
- docs/source/development/roadmap.rst → includes ROADMAP.md
```

**Benefits:**
- ✅ GitHub shows nice .md files in root
- ✅ Sphinx can include .md files via MyST parser
- ✅ Contributors edit one file only
- ✅ No more sync issues

### Solution 2: Simplify ADR vs RFC Decision

**Current Confusion:**
- ADRs document past decisions
- RFCs propose future features
- Design docs exist in various places
- Case studies demonstrate features

**Simplified Approach:**

#### When to Use ADRs (Architecture Decision Records)
**Use for:** Important technical decisions that impact the architecture

**Examples:**
- Choosing PyTorch over TensorFlow
- Multi-agent parallel architecture vs sequential
- Sphinx vs MkDocs for documentation

**Format:** `docs/source/decisions/NNNN-title.rst`

#### When to Use RFCs (Request for Comments)
**Use for:** Proposing *large, complex* features that need community discussion

**Examples:**
- New distributed orchestration system
- Visual workflow designer
- Enterprise permission system

**Format:** `docs/source/rfcs/NNNN-title.rst`

#### When to Use Design Docs
**Use for:** Feature implementation details that don't need community RFC process

**Examples:**
- Multi-turn filesystem design
- Gemini MCP integration design
- File deletion and context files

**Format:** `docs/dev_notes/feature_name_design.md`

#### When to Use Case Studies
**Use for:** Demonstrating completed features with real-world usage

**Examples:**
- Claude Code workspace management
- Unified filesystem MCP integration
- User context path support

**Format:** `docs/case_studies/feature_name.md`

**Decision Tree:**
```
Is it a PAST architectural decision?
├─ Yes → ADR (docs/source/decisions/)
└─ No → Is it a PROPOSED large feature needing community input?
    ├─ Yes → RFC (docs/source/rfcs/)
    └─ No → Is it implementation details?
        ├─ Yes → Design Doc (docs/dev_notes/)
        └─ No → Is it demonstrating a completed feature?
            ├─ Yes → Case Study (docs/case_studies/)
            └─ No → Maybe just a GitHub issue or PR description?
```

### Solution 3: Documentation Contribution Guidelines

Add to `CONTRIBUTING.md`:

```markdown
## 📚 Documentation Guidelines

### When Implementing a New Feature

#### 1. Choose Where to Document

**Add to existing user guide when:**
- Feature extends existing functionality
- Natural fit in current documentation structure
- Small enhancement (< 200 words)

**Create new user guide when:**
- Feature is a major new capability
- Deserves its own page (> 500 words)
- Introduces new concepts

**Examples:**
- "Add new backend" → Add to `user_guide/backends.rst`
- "Multi-turn mode" → New file `user_guide/multi_turn_mode.rst`

#### 2. Document Your Implementation

**For every feature, update:**
1. ✅ User Guide (how to use it)
2. ✅ Configuration docs (if config changes)
3. ✅ API reference (if API changes)
4. ✅ Example/tutorial (if significant feature)
5. ✅ CHANGELOG.md (what changed)

**Optionally create:**
- Design doc (`docs/dev_notes/`) for complex implementation details
- ADR (`docs/source/decisions/`) if major architectural choice made
- Case study (`docs/case_studies/`) to demonstrate real-world usage

#### 3. Design Documentation Decision Guide

Use this flowchart:

**Before starting implementation:**
- Large, controversial feature? → Write RFC, get community feedback
- Significant architectural choice? → Plan to write ADR after decision

**During implementation:**
- Complex design needing documentation? → Create design doc in `docs/dev_notes/`

**After implementation:**
- Made important architectural decision? → Write ADR in `docs/source/decisions/`
- Want to demonstrate real-world usage? → Create case study in `docs/case_studies/`

**Always:**
- Update user guide, API docs, CHANGELOG.md
```

### Solution 4: Organized Roadmap Structure

**New structure for ROADMAP.md:**

```markdown
# MassGen Roadmap

## 🎯 Current Release: v0.0.30

### Short-Term Goals (Next 2-4 weeks)

**Addressing Immediate Issues:**
- [ ] Fix Claude Code backend reliability (#123)
- [ ] Resolve configuration bugs (#145)
- [ ] Improve error handling (#156)

**Required Features:**
- [ ] Multimodal support for Claude backend
- [ ] Multimodal support for Chat Completions backend

### Medium-Term Goals (1-2 months)

**Optional Enhancements:**
- [ ] AG2 group chat integration
- [ ] Tool registration refactoring

### Long-Term Vision (3-6 months)

**Major Capabilities:**
- Visual workflow designer
- Enterprise features
- Advanced memory management
- Distributed orchestration

## 📊 Track-Specific Roadmaps

See detailed roadmaps:
- [Multimodal Track](docs/source/tracks/multimodal/roadmap.md)
- [Memory Track](docs/source/tracks/memory/roadmap.md)
- [Coding Agent Track](docs/source/tracks/coding-agent/roadmap.md)
- [Web UI Track](docs/source/tracks/web-ui/roadmap.md)

## 🔗 Integration with GitHub Issues

- Short-term goals linked to GitHub issues
- Track progress via project boards
- Community can see what's being worked on
```

---

## Implementation Steps

### Step 1: Add Documentation Guidelines to CONTRIBUTING.md
- Add "Documentation Guidelines" section
- Include decision tree for when to use ADRs/RFCs/design docs
- Explain when to add to existing vs create new guide

### Step 2: Create CHANGELOG.md
- Extract changes from `docs/source/changelog.rst`
- Add recent releases from `docs/releases/`
- Follow Keep a Changelog format

### Step 3: Update ROADMAP.md
- Rename `ROADMAP_v0.0.30.md` → `ROADMAP.md`
- Restructure with short-term, medium-term, long-term sections
- Link to GitHub issues for short-term goals
- Reference track-specific roadmaps

### Step 4: Update Sphinx .rst Files to Include .md
- `contributing.rst` → include/reference CONTRIBUTING.md
- `changelog.rst` → include/reference CHANGELOG.md
- `roadmap.rst` → include/reference ROADMAP.md

### Step 5: Create Documentation Decision Guide
- One-page visual guide: "When to Write What"
- Simple flowchart
- Save as `docs/DOCUMENTATION_DECISION_GUIDE.md`

### Step 6: Update Documentation Validation
- Add check: .rst files must sync with .md source files
- Warn if .md and .rst content diverges

---

## Benefits of This Approach

### Reduced Complexity
- ✅ Clear decision tree (no more "should I write ADR or RFC?")
- ✅ Single source of truth for key docs
- ✅ Fewer files to maintain

### Better Contributor Experience
- ✅ Know exactly where to document changes
- ✅ Clear guidelines in CONTRIBUTING.md
- ✅ Examples of when to use each doc type

### Improved Organization
- ✅ Short-term vs long-term roadmap clarity
- ✅ Integration with GitHub issues
- ✅ Track-specific roadmaps linked from main roadmap

### Easier Maintenance
- ✅ Edit CONTRIBUTING.md once, Sphinx includes it
- ✅ Edit CHANGELOG.md once, Sphinx includes it
- ✅ No more out-of-sync documentation

---

## Success Criteria

- [ ] CONTRIBUTING.md has comprehensive documentation guidelines
- [ ] Clear decision guide for ADRs vs RFCs vs design docs
- [ ] CHANGELOG.md created and synced with changelog.rst
- [ ] ROADMAP.md organized with short/medium/long-term goals
- [ ] All .rst files reference .md source files (no duplication)
- [ ] Documentation contribution is clear and simple (not confusing!)

---

**Next Steps:** Get user approval, then implement!
