# ADR-0004: Case-Driven Development Methodology

**Status:** Accepted
**Date:** 2024-10-08 (decision made ~2024-06, documented retroactively)
**Deciders:** @Leezekun, core team
**Technical Story:** Development methodology and release philosophy

## Context and Problem Statement

Software projects, especially in AI/ML, can suffer from feature creep or build capabilities that don't address real user needs. How should MassGen prioritize development and measure progress?

**Key questions:**
- How do we identify which features to build?
- How do we validate that features actually improve the system?
- How do we communicate improvements to users?
- How do we maintain quality while iterating quickly?

## Considered Options

1. **Feature-Driven** - Build features based on roadmap/ideas, release when ready
2. **Issue-Driven** - Build whatever users request most in issues
3. **Benchmark-Driven** - Optimize for performance on standard benchmarks
4. **Case-Driven (Chosen)** - Each release tied to specific use case demonstrations
5. **Experiment-Driven** - Continuous A/B testing of features

## Decision

We chose **Case-Driven Development**.

### Core Methodology

**Each release is tied to a case study that:**
1. Identifies a real-world problem MassGen can't solve well
2. Documents the failure modes and why current version falls short
3. Designs new features to address those specific gaps
4. Implements and validates the features
5. Demonstrates measurable improvements on that case
6. Documents the process from problem to solution

**Case Study Structure:**
- **Planning Phase**: Define problem, baseline performance, desired features
- **Testing Phase**: Implement features, record demos, compare results
- **Evaluation & Analysis**: Document improvements and learnings

**Release Philosophy:**
- Each version (v0.0.X) has an associated case study
- Features are motivated by concrete use cases, not abstract capabilities
- Improvements are demonstrated, not just claimed
- Users can reproduce case studies to validate improvements

### Rationale

- **User-focused**: Features solve real problems, not hypothetical ones
- **Measurable**: Can objectively assess if new version is better
- **Communicable**: Case studies show exactly what improved and why
- **Quality gate**: Features must demonstrably work before release
- **Educational**: Case studies serve as both documentation and examples
- **Reproducible**: Users can validate claims by running same cases
- **Honest**: Acknowledges limitations and failure modes explicitly

## Consequences

### Positive

- **Clear value proposition**: Each release has tangible improvements
- **Better prioritization**: Focus on high-impact features first
- **Built-in documentation**: Case studies document features as they're built
- **Quality assurance**: Features must work well enough for case study
- **User trust**: Demonstrated improvements build credibility
- **Examples for users**: Case studies show how to use features
- **Feedback loop**: Real use cases reveal next areas for improvement
- **Marketing material**: Case studies are shareable, compelling content

### Negative

- **More work per release**: Requires careful case study preparation
- **Slower releases**: Can't ship features until case study validates them
- **Bias toward demonstrable features**: Harder to justify infrastructure work
- **Higher bar**: Features must work well enough for public demonstration
- **Resource intensive**: Good case studies require time to create

### Neutral

- Need discipline to maintain case study quality
- Requires good case study template and tooling
- Balance needed between polish and velocity

## Implementation Notes

**Process:**
1. Identify promising use case where MassGen struggles
2. Create case study issue using template
3. Document baseline behavior and failure modes
4. Design features to address gaps (may involve RFC for major changes)
5. Implement features
6. Record demonstrations showing improvements
7. Write complete case study with before/after comparison
8. Release new version with case study
9. Archive case study in `docs/case_studies/`

**Case Study Template:**
- `docs/case_studies/case-study-template.md` defines structure
- Planning Phase: Problem, baseline, success criteria
- Testing Phase: Implementation, new features, demo recording
- Evaluation: Results analysis, conclusion

**Claude Code Integration:**
- `case-study-writer` agent assists with case study creation
- Helps propose examples, validate implementations
- Generates final case study documentation

**Examples:**
- Stockholm travel guide (multi-agent collaboration)
- Collaborative creative writing (intelligence sharing)
- IMO math competition (reasoning and consensus)
- Fibonacci algorithms (code generation and verification)

## Validation

Success metrics:
- ✅ Each release has associated case study
- ✅ Case studies demonstrate measurable improvements
- ✅ Users can reproduce case study results
- ✅ Case studies serve as effective documentation
- ✅ Community contributions often include case study proposals

**Impact:**
- ~19 case studies created demonstrating various capabilities
- Clear progression of features from v0.0.1 to current
- Case studies frequently referenced in discussions
- Drives feature prioritization effectively

## Related Decisions

- Builds on multi-agent architecture (ADR-0003)
- Informed by research on effective software development
- May evolve to include:
  - Automated case study validation in CI
  - Benchmark suite derived from case studies
  - Community-contributed case study library

## Long-term Vision

Case-driven development positions MassGen for:
- **Self-evolution**: Case studies become tests for autonomous improvement
- **Continuous validation**: Regression testing via historical cases
- **User-driven development**: Community can propose cases for features they need
- **Transparent progress**: Visible improvement trajectory over time

The case study methodology creates a virtuous cycle:
1. Real problems → Features
2. Features → Improvements
3. Improvements → Case studies
4. Case studies → User trust & new problem discovery

---

*This methodology has proven highly effective, with case studies serving triple duty as quality gates, documentation, and marketing material. The discipline of demonstrating improvements forces focus on what actually matters.*

*Last updated: 2024-10-08 by @ncrispin*
