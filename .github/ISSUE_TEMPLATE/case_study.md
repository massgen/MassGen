---
name: MassGen Case Study
about: Template for documenting MassGen case studies
title: "[Case Study] "
labels: ["case-study"]
assignees: ""
---

<!-- Use this template to document evaluation case studies for MassGen feature development. Each case study should identify a specific problem, test current performance, and drive implementation of new features. -->

## Context and Motivation
Provide a brief description of what prompted this case study and the high-level problem being addressed.

## 📝 Evaluation Design

### Prompt
<!-- The prompt should be a specific task that is driving the development of the new desired features. It should be clear that the new features are used when the prompt is answered. This need not be the original prompt you were using when you thought of the new set of desired features; instead, it should be carefully chosen such that it is relatively simple, clear, and unambiguous to allow for better evaluation. -->

```
[Insert your evaluation prompt here]
```

### Baseline Config
<!-- Provide the yaml file or link to the yaml file that describes the configuration file for the baseline. -->

```yaml
# Link to config file or paste contents here
```

### Baseline Command
<!-- Place the command here that describes how to test MassGen on the baseline version: -->

```bash
uv run python -m massgen.cli --config massgen/configs/xxx.yaml "<prompt>"
```

## 🔧 Evaluation Analysis

### Results & Failure Modes
Explain the results of running your command with the current version of MassGen, then how and why MassGen fails to perform well. Include both general details and specifics. If there is auxiliary information such as code or external artifacts that explain why it fails, include detailed descriptions, snippets, and/or screenshots here.

### Success Criteria
Define success for this case study. Given we have outputs from two different versions of MassGen, how would we know the new version of MassGen is more successful? This will likely be based not only on the prompt, but also on how MassGen behaved when answering the prompt.

## 🎯 Desired Features
Describe the desired features we need to implement in MassGen to complete this case study well. This is an important step, as it will drive development of the new version. Thinking of new features to develop will often go hand-in-hand with trying out various targeted prompts and analyzing their outputs in detail.

## 🛠️ Implementation Plan
Describe the implementation plan for the desired features. This should include a breakdown of the tasks needed to implement the desired features, as well as an estimate of the time required for each task and any dependencies or potential blockers.

## Submission
[Click here to create PR with the case study template](../../massgen/compare/main...BRANCH-NAME?template=case_study_resolution.md)

*(Replace BRANCH-NAME with your actual branch name)*
