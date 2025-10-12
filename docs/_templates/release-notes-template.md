# Release v{VERSION}

**Release Date:** {DATE}

**Release Type:** {TYPE} (Major | Minor | Patch | Hotfix)

**Self-Evolution Level:** Level 3 - Case Study Release

---

## Summary

<!-- Brief 2-3 sentence overview of this release -->

{SUMMARY}

---

## New Features

### {FEATURE_NAME}

**Purpose:** {FEATURE_PURPOSE}

**Implementation:** {FEATURE_DETAILS}

**Usage Example:**
```python
{FEATURE_EXAMPLE}
```

**Documentation:** See [Feature Guide](../../features/{FEATURE_SLUG}.md)

---

## Improvements

### {IMPROVEMENT_AREA}

- {IMPROVEMENT_DETAIL_1}
- {IMPROVEMENT_DETAIL_2}

---

## Bug Fixes

### {BUG_CATEGORY}

- **Fixed:** {BUG_DESCRIPTION}
  - **Issue:** #{ISSUE_NUMBER}
  - **Impact:** {BUG_IMPACT}
  - **Solution:** {BUG_FIX_DETAILS}

---

## Breaking Changes

<!-- Remove this section if no breaking changes -->

### {BREAKING_CHANGE_AREA}

**What changed:** {CHANGE_DESCRIPTION}

**Migration path:**
```python
# Old way
{OLD_CODE}

# New way
{NEW_CODE}
```

---

## Case Study

This release includes a comprehensive case study demonstrating MassGen's self-evolution capabilities.

**Case Study:** [View Case Study](case-study.md)

**Key Findings:**
- {FINDING_1}
- {FINDING_2}
- {FINDING_3}

**Improvements Discovered:**
- {IMPROVEMENT_1}
- {IMPROVEMENT_2}

---

## Configuration Changes

### New Configuration Options

```yaml
{NEW_CONFIG_OPTIONS}
```

### Updated Configuration Options

```yaml
{UPDATED_CONFIG_OPTIONS}
```

---

## Model Support

### New Models Added

| Backend | Model ID | Description |
|---------|----------|-------------|
| {BACKEND} | {MODEL_ID} | {DESCRIPTION} |

### Updated Models

| Backend | Model ID | Changes |
|---------|----------|---------|
| {BACKEND} | {MODEL_ID} | {CHANGES} |

---

## Performance Improvements

- {PERFORMANCE_1}
- {PERFORMANCE_2}

---

## Documentation Updates

- {DOC_UPDATE_1}
- {DOC_UPDATE_2}

---

## Dependencies

### Added
- {DEPENDENCY_1}

### Updated
- {DEPENDENCY_2}

### Removed
- {DEPENDENCY_3}

---

## Known Issues

<!-- Remove this section if no known issues -->

- {KNOWN_ISSUE_1}
  - **Workaround:** {WORKAROUND_1}

---

## Contributors

Thanks to all contributors who helped with this release:

- @{CONTRIBUTOR_1}
- @{CONTRIBUTOR_2}

---

## Links

- **Pull Request:** #{PR_NUMBER}
- **Case Study:** [case-study.md](case-study.md)
- **Improvements Log:** [improvements.md](improvements.md)
- **Video Demo:** [Video](video/)
- **Feature Documentation:** [docs/features/](../../features/)

---

## Installation

```bash
pip install --upgrade massgen=={VERSION}
```

Or with uv:
```bash
uv pip install --upgrade massgen=={VERSION}
```

---

## Next Release Preview

**Planned for v{NEXT_VERSION}:**
- {NEXT_FEATURE_1}
- {NEXT_FEATURE_2}

See [Roadmap](../../source/tracks/roadmap.md) for more details.
