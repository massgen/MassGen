# MassGen Case Study Template

MassGen is focused on **case-driven development**. New features should be discovered and reflected through performance improvements grounded in real-world use cases.

**Importantly, each new version of MassGen will be associated with a case study detailed in this way.**

Use this template to detail the "why" behind development changes. Once a new version is created, a corresponding case study in this format will be produced that explains the motivation behind the new features, the new features themselves, and the corresponding improvements that result.

## 🤝 Contributing
To guide future versions of MassGen, we encourage **anyone** to submit an issue using the corresponding `case-study` issue template based on the "PLANNING PHASE" section found in this template.

Then, this issue will be resolved by a PR (use the link in the issue template), describing new features and with a link to a full case study doc. This can happen in multiple ways: 1) the development team will try to address the issue, scheduling it for a further release, or 2) you can contribute yourself, as in the [CONTRIBUTING.md](../../CONTRIBUTING.md).

Regardless, please make sure you join [our Discord](https://discord.com/invite/VVrT2rQaz5) to discuss your changes and get more involved with MassGen.

The more case studies we have, the more we can improve the features according to real use-cases and the better MassGen will be!

---

# Table of Contents

- [📋 PLANNING PHASE](#planning-phase)
  - [📝 Evaluation Design](#evaluation-design)
    - [Prompt](#prompt)
    - [Baseline Config](#baseline-config)
    - [Baseline Command](#baseline-command)
  - [🔧 Evaluation Analysis](#evaluation-analysis)
    - [Results & Failure Modes](#results--failure-modes)
    - [Success Criteria](#success-criteria)
  - [🎯 Desired Features](#desired-features)
- [🚀 TESTING PHASE](#testing-phase)
  - [📦 Implementation Details](#implementation-details)
    - [Version](#version)
    - [New Features](#new-features)
    - [New Config](#new-config)
    - [Command](#command)
  - [🤖 Agents](#agents)
  - [🎥 Demo](#demo)
- [📊 EVALUATION & ANALYSIS](#evaluation-analysis)
  - [Results](#results)
    - [The Collaborative Process](#the-collaborative-process)
    - [The Voting Pattern](#the-voting-pattern)
    - [The Final Answer](#the-final-answer)
    - [Anything Else](#anything-else)
  - [🎯 Conclusion](#conclusion)
- [📌 Status Tracker](#status-tracker)

---

<h1 id="planning-phase">📋 PLANNING PHASE</h1>

*Complete this section before implementation*

<h2 id="evaluation-design">📝 Evaluation Design</h2>

### Prompt
The prompt should be a specific task that is driving the development of the new desired features. It should be clear that the new features are used when the prompt is answered. This need not be the original prompt you were using when you thought of the new set of desired features; instead, it should be carefully chosen such that it is relatively simple, clear, and unambiguous to allow for better evaluation.

### Baseline Config
Provide the yaml file or link to the yaml file that describes the configuration file for the baseline.

### Baseline Command
Place the command here that describes how to test MassGen on the baseline version:

```bash
massgen --config @examples/xxx "<prompt>"
```

<h2 id="evaluation-analysis">🔧 Evaluation Analysis</h2>

### Results & Failure Modes
Explain the results of running your command with the current version of MassGen, then how and why MassGen fails to perform well. Include both general details and specifics. If there is auxiliary information such as code or external artifacts that explain why it fails, include detailed descriptions, snippets, and/or screenshots here.

### Success Criteria
Define success for this case study. Given we have outputs from two different versions of MassGen, how would we know the new version of MassGen is more successful? This will likely be based not only on the prompt, but also on how MassGen behaved when answering the prompt.

<h2 id="desired-features">🎯 Desired Features</h2>

Describe the desired features we need to implement in MassGen to complete this case study well. This is an important step, as it will drive development of the new version. Thinking of new features to develop will often go hand-in-hand with trying out various targeted prompts and analyzing their outputs in detail.


---

<h1 id="testing-phase">🚀 TESTING PHASE</h1>

*Complete this section after implementation*

<h2 id="implementation-details">📦 Implementation Details</h2>

### Version
Place the version or branch of MassGen here with the new features.

<h3 id="new-features">✨ New Features</h2>

Describe the new features that were implemented to improve MassGen to perform better on the case study.

### New Config
Provide the yaml file or link to the yaml file that describes how to run the configuration file for the new version.

*Note that this may be the same as the baseline config or not depending on what the new features look like. If it is the same, delete this section.*

### Command
Place the command here that describes how to test MassGen on the new version:

```bash
massgen --config @examples/xxx "<prompt>"
```

*Note that this may be the same as the baseline command or not depending on what the new features look like. If it is the same, delete this section.*

<h2 id="agents">🤖 Agents</h2>

Describe the agents used and any relevant information about them.
- **Agent 1**: ...
- **Agent 2**: ...
- **Agent 3**: ...

<h2 id="demo">🎥 Demo</h2>

Each case study should be accompanied by a recording demonstrating the new functionalities obtained by running MassGen with the described command.

[![MassGen Case Study](link)](link)

---

<h1 id="evaluation-analysis">📊 EVALUATION & ANALYSIS</h1>

## Results
Given the success criteria described above, how does the new version of MassGen perform relative to the old one? Describe in specific terms and address each portion of the MassGen orchestration pipeline, highlighting different areas as applicable. It is important here to directly connect the results to the new features.

Like with baseline analysis, be specific enough such that it is clear to anyone reading this why the new version is better. If there is auxiliary information such as code or external artifacts, include detailed descriptions, snippets, and/or screenshots here.

Below are important aspects to consider describing:

### The Collaborative Process
How do agents generate new answers? Did our new features change any aspects of this?

### The Voting Pattern
How do agents vote? Did our new features change any aspects of this?

### The Final Answer
How is the final answer created? Did our new features change any aspects of this?

### Anything Else
Highlight anything else that our new features may have impacted, if applicable.

*Note: If MassGen performs similarly to the baseline, we likely need to 1) change or improve the implementation of the desired features, or 2) change the prompt used in the case study to something simpler, easier to evaluate, or better representative of the changes.*

<h2 id="conclusion">🎯 Conclusion</h2>

Explain why the new features resulted in an improvement in performance after they were implemented. Also discuss the broader implications of the new features and what they can enable.

---

<h3 id="status-tracker">📌 Status Tracker</h3>

- [ ] Planning phase completed
- [ ] Features implemented
- [ ] Testing completed
- [ ] Demo recorded
- [ ] Results analyzed
- [ ] Case study reviewed
