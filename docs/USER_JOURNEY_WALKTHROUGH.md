# User Journey Walkthrough

**Purpose:** This document walks through different user personas and how they navigate MassGen documentation to accomplish their goals.

**Date:** October 2025

---

## 🎭 User Personas

1. **New Contributor** - First-time contributor wanting to add a feature
2. **Feature Implementer** - Developer adding a major new capability
3. **Bug Fixer** - Developer fixing an existing issue
4. **Documentation Writer** - Technical writer improving docs

---

## Journey 1: New Contributor - Adding a New Backend

### Persona: Sarah
**Background:** Python developer, familiar with AI APIs, first time contributing to MassGen
**Goal:** Add support for Mistral AI backend

### Journey Steps

#### 1. Discovery Phase
**Sarah visits the GitHub repository**

```
📍 Starting Point: README.md
```

**What Sarah sees:**
- Clear project description with GIF demo
- Table of Contents showing "Contributing" section
- Quick Start guide showing existing backends

**Sarah's thought:** *"I can see they support OpenAI, Claude, Gemini... I want to add Mistral. Where do I start?"*

**Action:** Clicks on "Contributing" link

---

#### 2. Understanding Contribution Process
**Sarah reads CONTRIBUTING.md**

```
📍 Current Location: CONTRIBUTING.md
```

**What Sarah finds (in order):**
1. **Development Setup** section
   - Fork, clone, create branch instructions
   - `uv` setup commands
   - Pre-commit hooks

2. **Scroll down to "Documentation Guidelines"** section
   - Visual decision tree showing what docs to write
   - Quick reference table
   - Common scenarios including "I'm adding a new backend"

**Sarah's discovery:**
```
Scenario 1: "I'm adding a new backend (e.g., Mistral AI)"

What to write:
1. ✅ Update docs/source/user_guide/backends.rst
2. ✅ Update CHANGELOG.md
3. ✅ Add example config: massgen/configs/providers/mistral.yaml

Optional:
- 🏗️ Design doc if integration was complex
```

**Sarah's thought:** *"Perfect! This is exactly what I need. Only 3 required docs, and they show me exactly where they go."*

---

#### 3. Implementation Phase
**Sarah starts coding**

```
📍 Current Location: massgen/backends/
```

**Sarah's process:**
1. Looks at existing `claude.py` and `gemini.py` for reference
2. Creates `mistral.py` following the same pattern
3. Adds Mistral API client integration
4. Tests locally

**Question arises:** *"Should I write a design doc about how I integrated this?"*

**Sarah checks the decision tree:**
```
Is the implementation complex?
└─ No → Don't need design doc
```

**Sarah's thought:** *"The integration was straightforward, just followed the existing pattern. I'll skip the design doc."*

---

#### 4. Documentation Phase
**Sarah documents her work**

```
📍 Task 1: Update user_guide/backends.rst
```

**Sarah opens** `docs/source/user_guide/backends.rst`

**What she sees:**
- Existing backend table with columns: Backend, Models, Tools, MCP Support
- Setup instructions for each backend
- Configuration examples

**Sarah adds:**
```rst
Mistral AI
----------

**Supported Models:**
- Mistral Large 2
- Mistral Nemo
- Codestral

**Setup:**

.. code-block:: bash

   # Add to .env
   MISTRAL_API_KEY=your_key_here

**Configuration:**

.. code-block:: yaml

   agents:
     - id: "mistral-agent"
       backend:
         type: "chatcompletion"
         model: "mistral-large-2"
         base_url: "https://api.mistral.ai/v1"
         api_key: "${MISTRAL_API_KEY}"
```

---

```
📍 Task 2: Update CHANGELOG.md
```

**Sarah opens** `CHANGELOG.md` and sees the format:

```markdown
## [Unreleased]

### Added
- **Mistral AI Backend Support**: New backend for Mistral AI models
  - Chat Completions API integration
  - Support for Mistral Large 2, Nemo, and Codestral
  - Configuration examples in configs/providers/mistral.yaml
```

---

```
📍 Task 3: Create example config
```

**Sarah creates** `massgen/configs/providers/mistral.yaml`:

```yaml
agents:
  - id: "mistral-agent"
    backend:
      type: "chatcompletion"
      model: "mistral-large-2"
      base_url: "https://api.mistral.ai/v1"
      api_key: "${MISTRAL_API_KEY}"
    system_message: "You are a helpful assistant powered by Mistral AI."
```

---

#### 5. Validation Phase
**Sarah validates her documentation**

```bash
# Sarah runs the doc checks
make docs-check
```

**Output:**
```
✅ All links are valid!
✅ No significant duplication detected!
✅ All documentation checks passed!
```

**Sarah's thought:** *"Great! Everything validates. No broken links, no duplication."*

---

#### 6. Submission Phase
**Sarah creates a Pull Request**

**PR Checklist from CONTRIBUTING.md:**
```
□ Updated relevant user guide (backends.rst) ✅
□ Added entry to CHANGELOG.md ✅
□ Added example (mistral.yaml) ✅
□ Ran make docs-check ✅
□ Previewed docs locally ✅
```

**Sarah's PR description:**
```markdown
## Add Mistral AI Backend Support

### Changes
- Added Mistral AI backend integration via Chat Completions API
- Updated `docs/source/user_guide/backends.rst` with Mistral documentation
- Added example configuration `configs/providers/mistral.yaml`
- Updated CHANGELOG.md

### Testing
- ✅ Tested with Mistral Large 2
- ✅ Documentation validates (make docs-check)
- ✅ Example config works

### Documentation
All required docs completed per CONTRIBUTING.md guidelines.
```

---

### Journey Outcome

**Total Time:** ~3 hours
- **Coding:** 2 hours
- **Documentation:** 45 minutes
- **Validation:** 15 minutes

**Sarah's Feedback:** *"The documentation guidelines were super clear. I knew exactly what to write and where to put it. The decision tree helped me avoid writing unnecessary docs. The validation tools caught a typo in my link. Overall smooth experience!"*

---

## Journey 2: Feature Implementer - Adding Audio Support

### Persona: Alex
**Background:** Senior ML engineer, experienced with MassGen codebase
**Goal:** Implement audio processing capabilities

### Journey Steps

#### 1. Planning Phase
**Alex wants community input before implementing**

```
📍 Starting Point: CONTRIBUTING.md → Documentation Guidelines
```

**Alex reads:**
```
Scenario 4: "I want to propose a new feature (Visual Workflow Designer)"

What to write:
1. ✅ Create RFC: docs/source/rfcs/0001-visual-workflow-designer.rst
2. Open GitHub Discussion or PR for feedback
3. THEN implement after getting consensus
```

**Alex's action:** Creates RFC

---

```
📍 Current Location: docs/source/rfcs/0001-audio-processing.rst
```

**Alex writes RFC:**
```rst
RFC 0001: Audio Processing Support
===================================

:Author: Alex Chen
:Status: Draft
:Created: 2025-10-09

Context
-------

MassGen currently supports text and image modalities. Audio processing
would enable:
- Speech-to-text transcription
- Text-to-speech generation
- Audio file analysis

Proposed Design
---------------

1. New AudioChunk class in stream_chunk module
2. Backend support for:
   - OpenAI (Whisper API)
   - Google (Speech-to-Text)
3. Audio file I/O utilities

Alternatives Considered
-----------------------

1. Use external audio processing services
   - Pro: Less code to maintain
   - Con: Latency, external dependencies

2. Implement custom audio processing
   - Pro: Full control
   - Con: Complex, reinventing wheel

Decision: Use provider APIs where available, implement wrappers

Open Questions
--------------

- Which audio formats to support?
- How to handle large audio files?
- Streaming vs batch processing?
```

**Alex's action:** Creates PR with RFC for community discussion

---

#### 2. Implementation Phase (after RFC approval)
**Alex implements the feature over 2 weeks**

```
📍 Implementation Complete
```

**Complex design decisions made:**
- Custom AudioChunk architecture
- Provider API abstraction layer
- File format conversion utilities

**Alex's thought:** *"This was complex. I should write a design doc."*

---

#### 3. Documentation Phase
**Alex consults the decision tree**

```
Is the implementation complex?
└─ Yes → Write Design Doc

Made important architectural decision?
└─ Yes → Write ADR
```

**Alex creates:**

1. **Design Doc** → `docs/dev_notes/audio_processing_design.md`
2. **ADR** → `docs/source/decisions/0005-audio-provider-apis.rst`
3. **User Guide** → `docs/source/user_guide/audio_processing.rst`
4. **Examples** → `docs/source/examples/audio_examples.rst`
5. **Config Docs** → Updates `configuration.rst`
6. **CHANGELOG.md** → Major feature entry

**Total docs:** 6 files (1 design doc, 1 ADR, 4 required docs)

---

### Journey Outcome

**Total Time:** ~2.5 weeks
- **Planning (RFC):** 1 day
- **Implementation:** 10 days
- **Documentation:** 2 days
- **Testing & Review:** 2 days

**Alex's Feedback:** *"The RFC process was great for getting early feedback. The documentation guidelines helped me structure my docs. I knew exactly when to write ADRs vs design docs. The decision tree prevented analysis paralysis."*

---

## Journey 3: Bug Fixer - Fixing Claude Code Backend

### Persona: Jordan
**Background:** DevOps engineer, familiar with MassGen deployment
**Goal:** Fix streaming stability issues in Claude Code backend

### Journey Steps

#### 1. Bug Discovery
**Jordan notices errors in production logs**

```
📍 Starting Point: GitHub Issues
```

**Jordan creates issue:** "Claude Code backend disconnects during long operations"

---

#### 2. Fix Implementation
**Jordan debugs and fixes the issue**

```
📍 Current Location: massgen/backends/claude_code.py
```

**Changes:**
- Added connection timeout handling
- Improved error recovery logic
- Enhanced retry mechanism

**Total changes:** ~50 lines of code

---

#### 3. Documentation Check
**Jordan wonders:** *"Do I need to document this?"*

```
📍 Checks: CONTRIBUTING.md → Documentation Guidelines
```

**Jordan finds:**
```
Scenario 2: "I'm fixing a bug in Claude Code backend"

What to write:
1. ✅ Update CHANGELOG.md

That's it! Bug fixes usually don't need user guide updates
unless behavior changes.
```

**Jordan's thought:** *"Perfect! Just CHANGELOG update needed."*

---

#### 4. Documentation Phase
**Jordan updates CHANGELOG.md**

```markdown
### Fixed
- **Claude Code Backend**: Resolved streaming stability issues
  - Fixed connection timeout handling
  - Improved error recovery with exponential backoff
  - Enhanced retry mechanism for long-running operations
```

**Total time on docs:** 5 minutes

---

#### 5. Validation & Submission
**Jordan validates and submits**

```bash
make docs-check
# ✅ All checks pass

git commit -m "fix: resolve Claude Code streaming stability issues"
```

---

### Journey Outcome

**Total Time:** 4 hours
- **Debugging:** 2 hours
- **Fixing:** 1.5 hours
- **Documentation:** 5 minutes
- **Testing:** 25 minutes

**Jordan's Feedback:** *"I was worried I'd have to write a ton of docs for a bug fix. The guidelines made it clear I only needed a CHANGELOG entry. Saved me time and let me focus on the fix."*

---

## Journey 4: Documentation Writer - Improving Clarity

### Persona: Morgan
**Background:** Technical writer, new to MassGen
**Goal:** Improve installation documentation

### Journey Steps

#### 1. Familiarization
**Morgan reads existing documentation**

```
📍 Starting Point: docs/source/quickstart/installation.rst
```

**Morgan identifies issues:**
- Missing step-by-step for Windows users
- Unclear uv installation process
- No troubleshooting section

---

#### 2. Research Phase
**Morgan checks organization**

```
📍 Checks: docs/DOCUMENTATION_ORGANIZATION_PLAN.md
```

**Morgan learns:**
- installation.rst is in quickstart/ directory
- Should follow single source of truth
- No duplication with README

---

#### 3. Writing Phase
**Morgan improves the documentation**

**Changes:**
- Adds Windows-specific instructions
- Expands uv installation section
- Creates troubleshooting subsection
- Adds screenshots (stored in docs/source/_static/)

---

#### 4. Validation Phase
**Morgan validates changes**

```bash
make docs-check
```

**Result:**
```
❌ Broken link detected!
docs/source/quickstart/installation.rst:
  Link to 'configuration' should be ':doc:`configuration`'
```

**Morgan fixes the link and re-validates:**
```
✅ All documentation checks passed!
```

---

#### 5. Preview Phase
**Morgan previews locally**

```bash
make docs-serve
# Opens http://localhost:8000
```

**Morgan reviews:**
- Link navigation works
- Images display correctly
- Formatting is clean

---

### Journey Outcome

**Total Time:** 3 hours
- **Research:** 30 minutes
- **Writing:** 1.5 hours
- **Validation & fixing:** 30 minutes
- **Preview & polish:** 30 minutes

**Morgan's Feedback:** *"The DOCUMENTATION_QUICK_START.md was super helpful for understanding the structure. The validation tools caught my broken link immediately. Being able to preview locally was crucial for checking formatting."*

---

## Key Insights from User Journeys

### What Works Well

1. **Clear Decision Trees** - Users know exactly what to document
2. **Scenario-Based Examples** - Real use cases match user needs
3. **Validation Tools** - Catch errors before submission
4. **Single Source** - No confusion about where to edit
5. **Quick Reference** - 90% rule helps prioritize

### Common Pain Points Addressed

1. **"Do I need an ADR?"** → Decision tree answers this
2. **"Where do I put this?"** → File locations specified
3. **"Is this duplicated?"** → Automated check prevents it
4. **"Did I break links?"** → Validation catches it
5. **"What's required vs optional?"** → Clearly marked in guides

### Time Saved

| User Type | Without Guidelines | With Guidelines | Time Saved |
|-----------|-------------------|-----------------|------------|
| New Contributor | 5 hours | 3 hours | 40% |
| Feature Implementer | 4 days | 2 days | 50% |
| Bug Fixer | 2 hours | 4 hours | N/A (was over-documenting before) |
| Doc Writer | 4 hours | 3 hours | 25% |

---

## Recommendations for Future Improvements

Based on these journeys:

1. **Add Video Walkthrough** - Screen recording showing the contribution process
2. **Interactive Decision Tool** - Web-based wizard for documentation decisions
3. **Template Snippets** - Pre-filled templates in common editors
4. **Automated PR Checklist** - Bot that comments with relevant checklist

---

**Last Updated:** October 2025
**Next Review:** After v0.0.30 release
