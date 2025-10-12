# Documentation Quick Start Guide

**🎯 Quick Answer:** For most features, you only need to update **User Guide + CHANGELOG.md**

This visual guide helps you decide what documentation to write when contributing to MassGen.

---

## 📊 Visual Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│                  I'm implementing a feature                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │  ALWAYS write these (Required):      │
         │  ✅ User Guide (or update existing)  │
         │  ✅ CHANGELOG.md entry               │
         │  ✅ Config docs (if config changes)  │
         │  ✅ Examples (if significant)        │
         └──────────────────┬───────────────────┘
                            │
                            ▼
              Is the implementation complex?
                     (Multiple approaches,
                   tricky design decisions)
                            │
                   ┌────────┴────────┐
                   │                 │
                  YES               NO
                   │                 │
                   ▼                 │
         ┌──────────────────┐       │
         │  Write Design    │       │
         │  Doc in          │       │
         │  dev_notes/      │       │
         └──────┬───────────┘       │
                │                   │
                ▼                   ▼
    Did you make an important    Want to showcase
    architectural decision?      the feature?
    (Affects future dev)              │
                │              ┌──────┴───────┐
         ┌──────┴───────┐     │              │
        YES            NO     YES            NO
         │              │      │              │
         ▼              │      ▼              │
   ┌──────────┐        │  ┌────────────┐    │
   │ Write    │        │  │ Write Case │    │
   │ ADR in   │        │  │ Study in   │    │
   │ decisions/│       │  │ case_      │    │
   └──────────┘        │  │ studies/   │    │
                       │  └────────────┘    │
                       │                    │
                       └────────┬───────────┘
                                │
                                ▼
                           ✅ Done!
```

---

## 🎨 Quick Visual Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENTATION TYPES                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📖 USER GUIDE                          [ALWAYS REQUIRED]       │
│  ├─ Where: docs/source/user_guide/                             │
│  ├─ When: Every feature                                        │
│  └─ Example: Adding new backend → update backends.rst          │
│                                                                 │
│  📝 CHANGELOG.md                        [ALWAYS REQUIRED]       │
│  ├─ Where: Root directory                                      │
│  ├─ When: Every PR                                             │
│  └─ Example: "### Added - New Gemini multimodal support"       │
│                                                                 │
│  ⚙️  CONFIG DOCS                         [IF CONFIG CHANGES]    │
│  ├─ Where: docs/source/quickstart/configuration.rst            │
│  ├─ When: New YAML options                                     │
│  └─ Example: New coordination config → add YAML example        │
│                                                                 │
│  💡 EXAMPLES                            [IF SIGNIFICANT]        │
│  ├─ Where: docs/source/examples/                               │
│  ├─ When: Feature needs demonstration                          │
│  └─ Example: New MCP integration → show working config         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    OPTIONAL DOCUMENTATION                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🏗️  DESIGN DOC                         [COMPLEX ONLY]          │
│  ├─ Where: docs/dev_notes/                                     │
│  ├─ When: Complex implementation needing explanation           │
│  └─ Example: multi_turn_filesystem_design.md                   │
│                                                                 │
│  📋 ADR (Architecture Decision Record) [MAJOR DECISIONS]       │
│  ├─ Where: docs/source/decisions/                              │
│  ├─ When: Important architectural choice made                  │
│  └─ Example: 0003-multi-agent-architecture.rst                 │
│                                                                 │
│  💬 RFC (Request for Comments)          [LARGE PROPOSALS]      │
│  ├─ Where: docs/source/rfcs/                                   │
│  ├─ When: BEFORE implementing large feature                    │
│  └─ Example: Proposing visual workflow designer                │
│                                                                 │
│  🎯 CASE STUDY                          [SHOWCASE]             │
│  ├─ Where: docs/case_studies/                                  │
│  ├─ When: Want to demonstrate real-world usage                 │
│  └─ Example: claude-code-workspace-management.md               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Common Scenarios

### Scenario 1: "I'm adding a new backend (e.g., Mistral AI)"

**What to write:**
1. ✅ Update `docs/source/user_guide/backends.rst`
   - Add Mistral to the backend table
   - Add setup instructions
   - Add example configuration

2. ✅ Update `CHANGELOG.md`
   ```markdown
   ### Added
   - **Mistral AI Backend Support**: New backend for Mistral AI models
     - Chat Completions API integration
     - Configuration examples in configs/providers/mistral.yaml
   ```

3. ✅ Add example config: `massgen/configs/providers/mistral.yaml`

**Optional:**
- 🏗️ Design doc if integration was complex
- 🎯 Case study to showcase Mistral-specific features

---

### Scenario 2: "I'm fixing a bug in Claude Code backend"

**What to write:**
1. ✅ Update `CHANGELOG.md`
   ```markdown
   ### Fixed
   - **Claude Code Backend**: Resolved streaming stability issues
     - Fixed connection timeout handling
     - Improved error recovery
   ```

**That's it!** Bug fixes usually don't need user guide updates unless behavior changes.

---

### Scenario 3: "I'm implementing a major new feature (e.g., Audio Support)"

**What to write:**
1. ✅ Create `docs/source/user_guide/audio_processing.rst`
   - How to use audio features
   - Configuration options
   - Examples

2. ✅ Update `CHANGELOG.md`
   ```markdown
   ### Added
   - **Audio Processing**: Complete audio understanding and generation
     - Speech-to-text for all major backends
     - Text-to-speech capabilities
     - Audio format conversion
   ```

3. ✅ Add examples: `docs/source/examples/audio_examples.rst`

4. ✅ Update `docs/source/quickstart/configuration.rst` with audio config

**Optional (but recommended for major features):**
- 🏗️ Design doc: `docs/dev_notes/audio_processing_design.md`
- 📋 ADR: `docs/source/decisions/0005-audio-backend-choice.rst` (if you chose a specific audio library)
- 🎯 Case study: `docs/case_studies/audio-transcription-workflow.md`

**Consider for discussion:**
- 💬 RFC: Write BEFORE implementing if you want community feedback on the design

---

### Scenario 4: "I want to propose a new feature (Visual Workflow Designer)"

**What to write:**
1. ✅ Create RFC: `docs/source/rfcs/0001-visual-workflow-designer.rst`
   - Motivation and use cases
   - Proposed design
   - Alternatives considered
   - Open questions for community

2. Open GitHub Discussion or PR for feedback

3. **THEN** implement after getting consensus

---

## 🎯 The 90% Rule

**90% of contributions only need:**
- ✅ User guide update
- ✅ CHANGELOG.md entry
- ✅ (Maybe) Config docs
- ✅ (Maybe) Example

**Only 10% need:**
- Design docs (complex implementations)
- ADRs (major architectural decisions)
- RFCs (large proposals needing feedback)
- Case studies (showcase real-world usage)

---

## ✅ Checklist Before Submitting PR

```
□ Updated relevant user guide (or created new one)
□ Added entry to CHANGELOG.md
□ Updated config docs (if config changed)
□ Added example (if significant feature)
□ Ran `make docs-check` (no broken links or duplication)
□ Previewed docs locally with `make docs-serve`

Optional (only if applicable):
□ Wrote design doc (if complex)
□ Wrote ADR (if architectural decision)
□ Wrote case study (if showcasing feature)
```

---

## 🔗 Full Documentation Guidelines

For comprehensive guidelines including:
- Detailed decision trees
- Quality standards
- Testing procedures
- Deployment information

See: [CONTRIBUTING.md](../CONTRIBUTING.md#-documentation-guidelines)

---

## 📚 Quick Links

- **Main Docs**: [docs/source/](source/)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Roadmap**: [ROADMAP.md](../ROADMAP.md)
- **Changelog**: [CHANGELOG.md](../CHANGELOG.md)
- **Deployment Guide**: [DOCUMENTATION_DEPLOYMENT.md](DOCUMENTATION_DEPLOYMENT.md)

---

**Questions?** Ask in `#massgen` on Discord or open a GitHub Discussion!

**Last Updated:** October 2025
