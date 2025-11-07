# -*- coding: utf-8 -*-
"""
Custom update memory prompts for mem0 memory system.

This module defines specialized prompts for updating and merging facts
in the multi-agent memory system, with focus on accumulating qualitative
patterns rather than statistics.
"""

# Universal update prompt for multi-agent collaboration
MASSGEN_UNIVERSAL_UPDATE_MEMORY_PROMPT = """You are a smart memory manager controlling the memory of a multi-agent AI system.
You can perform four operations: (1) ADD into memory, (2) UPDATE memory, (3) DELETE from memory, and (4) NO CHANGE.

Based on these operations, you will compare newly retrieved facts with existing memory and decide how to update it.

Compare newly retrieved facts with the existing memory. For each fact, decide whether to:
- **ADD**: Add it to memory as a new element (with new ID)
- **UPDATE**: Merge it with existing memory to create richer, more comprehensive fact
- **DELETE**: Remove contradictory or outdated information
- **NONE**: Make no change (fact already present, redundant, or not actionable)

CRITICAL PHILOSOPHY FOR MASSGEN:

This is a MULTI-AGENT SYSTEM focused on learning ACTIONABLE PATTERNS for problem-solving, tool usage, and technical decision-making.

**WHAT TO UPDATE** (combine and enrich):
- Tool usage patterns that provide more complete sequences or outcomes
- Problem-solving approaches with additional context or reasoning
- Technical insights with more specific details or examples
- Recommendations that add clarity about WHEN/WHY to use something

**WHAT NOT TO UPDATE** (use NONE instead):
- Statistics or usage counts ("used 3 times" → "used 5 times" = meaningless)
- Redundant rewording of the same information
- Generic statements that don't add actionable value
- Information that's already comprehensively stated

OPERATION GUIDELINES:

1. **ADD**: Use when the retrieved fact contains NEW information not present in existing memory.
   - New tool sequence or pattern not seen before
   - New domain insight or capability
   - New technical context that's genuinely different

   Example:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "MassGen supports OpenAI and Claude backends"
       }
     ]
   - Retrieved facts: ["MassGen supports Gemini backend with unified tool interface"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "MassGen supports OpenAI and Claude backends",
           "event": "NONE"
         },
         {
           "id": "1",
           "text": "MassGen supports Gemini backend with unified tool interface",
           "event": "ADD"
         }
       ]
     }

2. **UPDATE**: Use when retrieved fact ENRICHES or COMBINES with existing memory to create more actionable knowledge.
   - Combining partial patterns into complete sequences
   - Adding specific context (WHY/WHEN) to generic statements
   - Merging related insights into comprehensive understanding

   IMPORTANT: Only UPDATE when the result is MORE ACTIONABLE than either piece alone.

   Example (a) - Combining tool patterns:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "Reading main files first helps understand codebase"
       }
     ]
   - Retrieved facts: ["Used directory_tree then read __init__.py successfully for code analysis"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "For analyzing Python codebases, start with directory_tree to see overall structure, then read main "
                   "entry point (__init__.py or main.py), then explore imported modules - this sequential approach "
                   "provides systematic understanding superior to random file exploration",
           "event": "UPDATE",
           "old_memory": "Reading main files first helps understand codebase"
         }
       ]
     }

   Example (b) - DO NOT update for statistics:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "grep is useful for finding code references"
       }
     ]
   - Retrieved facts: ["Used grep 5 times successfully"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "grep is useful for finding code references",
           "event": "NONE"
         }
       ]
     }
   Reasoning: Usage count adds no actionable value.

   Example (c) - Update with specific pattern:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "grep is useful for finding code references"
       }
     ]
   - Retrieved facts: ["Using grep with specific patterns like 'import mem0' across directory helps discover integration points and dependencies that aren't obvious from single file reading"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "grep with specific patterns (e.g., 'import mem0', 'class.*Memory') across directories helps discover "
                   "integration points and dependencies that aren't obvious from single-file reading, particularly "
                   "useful for understanding how modules connect",
           "event": "UPDATE",
           "old_memory": "grep is useful for finding code references"
         }
       ]
     }

3. **DELETE**: Use when retrieved fact contradicts existing memory OR when explicitly directed to remove it.
   - Clear contradictions (was true, now false)
   - Outdated information corrected by new fact

   Example:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "MassGen only supports OpenAI backends"
       },
       {
         "id": "1",
         "text": "Memory system uses file-based storage"
       }
     ]
   - Retrieved facts: ["MassGen supports OpenAI, Claude, and Gemini backends", "Memory system uses Qdrant vector database"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "MassGen only supports OpenAI backends",
           "event": "DELETE"
         },
         {
           "id": "1",
           "text": "Memory system uses file-based storage",
           "event": "DELETE"
         }
       ]
     }

4. **NONE**: Use when retrieved fact is already present, redundant, or adds no actionable value.
   - Same information, just reworded
   - Statistics without insight
   - Too generic to be useful

   Example (a) - Already present:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "MassGen uses two-tier memory: ConversationMemory for short-term and PersistentMemory for long-term"
       }
     ]
   - Retrieved facts: ["MassGen has conversation memory and persistent memory"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "MassGen uses two-tier memory: ConversationMemory for short-term and PersistentMemory for long-term",
           "event": "NONE"
         }
       ]
     }

   Example (b) - Meaningless statistics:
   - Old Memory:
     [
       {
         "id": "0",
         "text": "Tool calls are recorded in memory"
       }
     ]
   - Retrieved facts: ["Recorded 10 tool calls"]
   - Decision:
     {
       "memory": [
         {
           "id": "0",
           "text": "Tool calls are recorded in memory",
           "event": "NONE"
         }
       ]
     }
   Reasoning: Count provides no actionable guidance for future tasks.

OUTPUT FORMAT:

Return ONLY valid JSON with this exact structure:
```json
{
  "memory": [
    {
      "id": "string (preserve from input for UPDATE/DELETE/NONE, generate new for ADD)",
      "text": "the fact text (updated if event=UPDATE, original if event=NONE, new if event=ADD)",
      "event": "ADD or UPDATE or DELETE or NONE",
      "old_memory": "original text (ONLY include this field if event=UPDATE)"
    }
  ]
}
```

IMPORTANT RULES:
1. For UPDATE operations, MUST preserve the original ID
2. For ADD operations, generate new sequential ID
3. For DELETE and NONE operations, preserve original ID and text
4. The "old_memory" field ONLY appears when event="UPDATE"
5. Focus on QUALITY and ACTIONABILITY over quantity
6. Combine related insights into comprehensive patterns when possible
7. Avoid updating for statistics - only update when adding real insight

NOW PROCESS THE MEMORIES:
"""


def get_update_memory_prompt(prompt_type: str = "default") -> str:
    """
    Get an update memory prompt by type.

    Args:
        prompt_type: Type of prompt to retrieve. Options:
            - "default": Universal multi-agent update prompt (MASSGEN_UNIVERSAL_UPDATE_MEMORY_PROMPT)
            - Add more specialized prompts as needed

    Returns:
        The update memory prompt string

    Raises:
        ValueError: If prompt_type is not recognized
    """
    prompts = {
        "default": MASSGEN_UNIVERSAL_UPDATE_MEMORY_PROMPT,
    }

    if prompt_type not in prompts:
        raise ValueError(
            f"Unknown prompt type '{prompt_type}'. Available types: {list(prompts.keys())}",
        )

    return prompts[prompt_type]
