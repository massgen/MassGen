# New Features v0.0.14

## Claude Code Answer Version Logging

### Feature Overview
A new logging capability has been added to automatically save every version of answers provided by Claude Code. This feature ensures comprehensive tracking and preservation of all generated answers from Claude Code Agent, enabling better traceability and version control.

### Storage Structure
Answer versions are organized in the following directory hierarchy:

```
massgen_logs/
└── log_{timestamp}/
    └── claude_code_agent_id/
        └── {answer_generation_timestamp}/
            └── files_included_in_generated_answer
```

#### Directory Structure Explanation
- `log_{timestamp}`: Main log directory identified by session timestamp
- `claude_code_agent_id`: Unique identifier directory for Claude Code Agent
- `{answer_generation_timestamp}`: Timestamp directory for each answer version, recording the generation time
- `files_included_in_generated_answer`: All relevant files contained in that version of the answer

### Important Note
The final answer continues to be stored in each Claude Code Agent's workspace as before. The logging feature provides additional versioning capability without affecting the existing workflow.

### Key Benefits
1. **Version Tracking**: Track the evolution of each answer through multiple iterations
2. **Historical Recovery**: Access and restore previous answer versions when needed
3. **Comparative Analysis**: Easily compare differences between different versions
4. **Complete Audit Trail**: Maintain full generation history for debugging and optimization
5. **Non-Intrusive**: Works alongside existing workspace storage without disruption

### Use Cases
- Reviewing historical Claude Code generation records
- Restoring to a specific answer version
- Analyzing and comparing answer quality across versions
- Debugging and optimizing the generation workflow
- Maintaining compliance and audit requirements

---

# Known Issue: More Reasonable Claude Code Agent Context Sharing Design

## Background
Currently, whether an agent can access a different working directory is determined implicitly through **prompt control**. This creates two main limitations:

1. **Over-reliance on prompt engineering** – Permissions are not enforced at a system level, only by how we phrase the prompt.  
2. **Lack of fine-grained control** – We cannot explicitly restrict or grant access to specific directories or resources on a per-agent basis.  

Ideally, each agent should have **explicit access control policies**, ensuring that sensitive or irrelevant contexts are not shared unless intended.

## Problem
- **Security risk**: Agents may accidentally access or reason about information they should not see.  
- **Context leakage**: Without clear boundaries, data from one workspace may flow into another.  
- **Poor scalability**: As more agents are added, maintaining access rules only via prompt instructions becomes fragile and error-prone.  

## Proposed Solution

### A. Explicit Access Control Layer
- Define per-agent **permissions** (e.g., `read/write/no-access`) for each working directory or resource.  
- Enforce these permissions at the orchestration layer, rather than only via prompt text.  

### B. Context-Aware Sharing Contracts
- Each agent declares **what context it needs** (e.g., "requires read-only access to directory X for build files").  
- The coordinator validates these requests against predefined permissions before granting access.  

### C. Configurable Policy
- Support a **policy file** or configuration (e.g., YAML/JSON) that defines which agent can access which resources.  
- Example:  
  ```yaml
  agents:
    claude-code:
      access:
        /workspace/projectA: read
        /workspace/projectB: none
    gpt-analysis:
      access:
        /workspace/projectA: read
        /workspace/projectB: write
  ```

### D. Prompt Simplification
- Once enforced at the system level, prompts can be simplified (no need to redundantly remind agents not to access certain directories).
- Reduces prompt length and minimizes risk of "prompt jailbreaking."