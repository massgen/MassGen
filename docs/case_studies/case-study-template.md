# MassGen Case Study Template

MassGen is focused on **case-driven development**. New features should be discovered and reflected through performance improvements grounded in real-world use cases. 

Use this template to detail new features and prompts that can be combined into a case study and targeted for future release.

**Each new version of MassGen will be associated with a case study detailed in this way.**

---

# 📋 PLANNING PHASE
*Complete this section before implementation*

## 📝 Evaluation Design

### Prompt
The prompt should be a specific task that is driving the development of the new desired features. It should be clear that the new features are used when the prompt is answered. This need not be the original prompt you were using when you thought of the new set of desired features; instead, it should be carefully chosen such that it is relatively simple, clear, and unambiguous to allow for better evaluation.

### Baseline Config
Provide the yaml file or link to the yaml file that describes the configuration file for the baseline.

### Baseline Command
Place the command here that describes how to test MassGen on the baseline version:

```bash
uv run python -m massgen.cli --config massgen/configs/xxx.yaml "<prompt>"
```

## 🔧 Evaluation Analysis

### Current Failure Modes
Explain how and why this case study fails in the current version of MassGen. Include both general details and specifics. If there is auxiliary information such as code or external artifacts, include detailed descriptions, snippets, and/or screenshots here.

### Success Criteria
Define success for this case study. Given we have outputs from two different versions of MassGen, how would we know the new version of MassGen is more successful? This will likely be based not only on the prompt, but also on how MassGen behaved when answering the prompt.

## 🎯 Desired Features
Describe the desired features we need to implement in MassGen to complete this case study well. This is an important step, as it will drive development of the new version. Thinking of new features to develop will often go hand-in-hand with trying out various targeted prompts and analyzing their outputs in detail.


---

# 🚀 TESTING PHASE
*Complete this section after implementation*

## 📦 Implementation Details

### Version
Place the version or branch of MassGen here with the new features.

### New Config
Provide the yaml file or link to the yaml file that describes how to run the configuration file for the new version. 

*Note that this may be the same as the baseline config or not depending on what the new features look like. If it is the same, delete this section.*

### Command
Place the command here that describes how to test MassGen on the new version:

```bash
uv run python -m massgen.cli --config massgen/configs/xxx.yaml "<prompt>"
```

*Note that this may be the same as the baseline command or not depending on what the new features look like. If it is the same, delete this section.*

## 🤖 Agents
Describe the agents used and any relevant information about them.
- **Agent 1**: ...
- **Agent 2**: ... 
- **Agent 3**: ...

## 🎥 Demo
Each case study should be accompanied by a recording demonstrating the new functionalities obtained by running MassGen with the described command.

[![MassGen Case Study](link)](link)

---

# 📊 EVALUATION & ANALYSIS

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

## 🎯 Conclusion
Explain why the new features resulted in an improvement in performance after they were implemented. Also discuss the broader implications of the new features and what they can enable.

---

### 📌 Status Tracker
- [ ] Planning phase completed
- [ ] Features implemented
- [ ] Testing completed
- [ ] Demo recorded
- [ ] Results analyzed
- [ ] Case study reviewed
