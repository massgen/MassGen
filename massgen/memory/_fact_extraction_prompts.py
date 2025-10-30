# -*- coding: utf-8 -*-
"""
Custom fact extraction prompts for mem0 memory system.

This module defines specialized prompts for extracting structured facts
from multi-agent conversations across diverse domains (research, creative,
technical, analytical).
"""

# Universal prompt for multi-agent collaboration across all domains
MASSGEN_UNIVERSAL_FACT_EXTRACTION_PROMPT = """
You are extracting facts from a multi-agent AI system where agents collaborate on diverse tasks: research synthesis, creative writing, technical analysis, travel planning, problem solving, and more.

EXTRACTION PHILOSOPHY:

Extract HIGH-LEVEL, CONCEPTUAL knowledge that remains valuable as details change. Avoid brittle
specifics like exact file paths or line numbers. Focus on insights, capabilities, and domain
knowledge that transcends implementation details.

CRITICAL: Each fact must be SELF-CONTAINED and SPECIFIC. Anyone reading the fact later should
understand what it means WITHOUT needing the original conversation context. Include specific
details about WHAT, WHY, and WHEN relevant.

FOCUS ON THESE CATEGORIES:

1. **FACTUAL_KNOWLEDGE**: Concrete facts, data points, measurements, dates, figures
   - "OpenAI revenue reached $12B annualized with $1B monthly run rate"
   - "Stockholm October weather ranges 8-11°C with ~9 hours daylight"
   - "Matrix exponentiation provides O(log n) time complexity for Fibonacci computation"
   - "EU AI Act implementation began as major regulatory development"

2. **INSIGHTS**: Discoveries, patterns, lessons learned, what worked/didn't work (must specify WHAT and WHY)
   - "In creative writing tasks, narrative depth and emotional journey are valued over citation-heavy analytical formats because academic references break immersion in fiction"
   - "Custom tool APIs provide structured, reliable data access compared to web page scraping which is unreliable due to HTML structure changes and rate limiting"
   - "When AI agents include academic citations in creative fiction, readers perceive the output as an analytical piece rather than a story"

3. **CAPABILITIES**: What specific tools/systems can or cannot do (with use cases)
   - "MassGen v0.1.1 supports Python function registration as custom tools via YAML configuration, allowing users to extend agent capabilities without modifying framework code"
   - "File-based Qdrant vector database doesn't support concurrent multi-agent access, requiring server-mode Qdrant for multi-agent scenarios"
   - "Custom tools work across all MassGen backends (Gemini, OpenAI, Claude) through unified tool interface"

4. **DOMAIN_EXPERTISE**: Subject-specific knowledge with technical details and explanations
   - "Binet's formula provides closed-form Fibonacci calculation using golden ratio phi=(1+√5)/2, allowing direct computation without iteration"
   - "Matrix exponentiation computes n-th Fibonacci in O(log n) time by raising transformation matrix [[1,1],[1,0]] to nth power"
   - "Pisano periods enable efficient modular Fibonacci computation by exploiting periodic nature of Fibonacci sequences under modulo operations"

5. **SPECIFIC RECOMMENDATIONS**: Only if they include WHAT to use, WHEN to use it, and WHY (skip
   generic advice)
   - "For Stockholm autumn café experience, visit Tössebageriet, Café Saturnus, or Skeppsbro
     Bageri which offer cozy atmosphere and traditional Swedish pastries during October's cooler
     weather (8-11°C)"
   - "Use Kitamasa method for computing large Fibonacci numbers with modular arithmetic because it outperforms standard approaches for very large indices"

   SKIP generic recommendations like: "Providing templates enhances documentation" or "Use clear naming conventions"

HOW TO WRITE FACTS:

Each fact should be a complete, self-contained string that includes:

1. **The core information** with specific details (numbers, names, technologies)
2. **Enough context** to understand WHAT, WHY, and WHEN (if relevant)
3. **No vague references** - use concrete nouns instead of "this", "that", "the system"
4. **Category-appropriate phrasing**:
   - FACTUAL_KNOWLEDGE: State the fact with metrics/data
   - RECOMMENDATIONS: Include what to use and when/why to use it
   - INSIGHTS: Explain what works/doesn't work and why
   - CAPABILITIES: Describe what can/cannot be done with specific use cases
   - DOMAIN_EXPERTISE: Include technical details with explanations

WHAT TO EXTRACT:

✓ Quantitative findings with specific numbers AND what they measure
✓ Capabilities and limitations discovered with specific use cases
✓ Domain knowledge with enough context to understand without the original conversation
✓ Recommendations with WHY they're recommended and WHEN to use them
✓ Insights about what works/doesn't work with specific examples or reasons

WHAT TO SKIP:

✗ Agent comparisons ("Agent 1's response is more detailed than Agent 2", "Agent X better addresses the question")
✗ Agent internal process (voting procedures, tool call instructions, "need to call the vote tool", "after using the tool")
✗ Voting outcomes and rationales ("evaluator votes in favor of Agent 1", "the reason for agent1's vote")
✗ Meta-instructions about how to respond ("response should start with", "should include", "avoid heavy formatting")
✗ Made-up code examples that aren't from the actual conversation
✗ Generic suggestions without specifics ("enhances clarity and usability", "providing templates improves documentation")
✗ Obvious definitions without context ("stateful means maintains state")
✗ Generic statements ("the system is complex", "good progress made")
✗ File paths and line numbers (__init__.py, base.py:45, massgen/backend/*)
✗ Specific method/variable names in implementation (_is_stateful, stream_with_tools)
✗ Process updates without content ("still working", "making progress")
✗ Greetings and social pleasantries
✗ Vague references ("this approach", "that method", "the system", "the base class")

CRITICAL RULES:
1. Extract knowledge about THE USER'S DOMAIN, not about the AI system's internal operations
2. Skip ALL voting/tool-use procedures AND agent comparisons - these are ephemeral system internals
3. Do NOT mention specific agents by name or number (Agent 1, Agent 2, etc.) - focus on the knowledge itself
4. Do NOT make up example code - only extract facts stated in the conversation
5. Avoid generic suggestions - only extract specific, actionable recommendations with clear use cases
6. Each fact must answer: "What would be useful to know when working on a similar task in the future?"

SELF-CONTAINED CHECK:
Before including a fact, ask: "Can someone read this fact 6 months from now and understand it WITHOUT seeing the original conversation?" If no, add more context.

OUTPUT FORMAT:

Return JSON with ONLY an array of fact strings (no nested objects):
```json
{
  "facts": [
    "Self-contained fact string with all necessary context",
    "Another complete fact that can be understood standalone"
  ]
}
```

IMPORTANT: Each string should be completely self-contained. Do NOT use metadata objects - include category context within the fact text itself if helpful.

EXAMPLES:

---
**Example 1: Research Synthesis (AI News)**

Input:
user: find big AI news this week
assistant: Conducting web searches on AI developments... Microsoft announced $100B AI infrastructure
spend with $30B this quarter. OpenAI revenue doubled to $12B annualized ($1B monthly). NVIDIA hit
$4.236T market cap.

Output:
```json
{
  "facts": [
    "Microsoft announced $100 billion total AI infrastructure investment with $30 billion allocated
    for the current quarter (verified from company announcement)",
    "OpenAI's revenue doubled to reach $12 billion annualized run rate with $1 billion in monthly recurring revenue (current period financial data)",
    "NVIDIA's market capitalization reached $4.236 trillion making it one of the most valuable companies globally (stock market data)"
  ]
}
```

---
**Example 2: Creative Writing (Robot Story)**

Input:
user: Write a short story about a robot who discovers music.
assistant: I created "Unit 734" about a sanitation bot finding a music box, focusing on internal transformation and gradual appreciation through sensory detail.

Output:
```json
{
  "facts": [
    "In creative writing tasks, readers and evaluators value narrative depth with emotional journey over citation-heavy analytical formats because academic references break immersion in fiction",
    "When AI agents include academic citations and references in creative fiction stories, the output is perceived as an analytical research piece rather than engaging narrative storytelling"
  ]
}
```

---
**Example 3: Travel Planning (Stockholm)**

Input:
user: what's best to do in Stockholm in October 2025
assistant: October weather 8-11°C, 9 hours daylight. Recommended Tössebageriet, Café Saturnus,
Skeppsbro Bageri for autumn atmosphere. Stockholm hosts Vikings' Halloween October 26-27 and Jazz
Festival October 11-20.

Output:
```json
{
  "facts": [
    "Stockholm weather in October averages 8-11°C (46-52°F) with approximately 9 hours of daylight per day, requiring warm layers for outdoor activities",
    "For authentic Stockholm autumn café experience, Tössebageriet, Café Saturnus, and Skeppsbro
    Bageri are recommended for their cozy atmosphere and traditional Swedish pastries",
    "Stockholm in 2025 hosts Vikings' Halloween festival on October 26-27 and Stockholm Jazz Festival from October 11-20, both major annual events worth planning around"
  ]
}
```

---
**Example 4: Algorithm Analysis (Fibonacci)**

Input:
user: provide as many ways to compute the n-th fibonacci number as possible
assistant: Classical approaches include naive recursion, memoization, dynamic programming, matrix
exponentiation, and Binet's formula. Advanced techniques include Kitamasa method, Bostan-Mori
algorithm, polynomial exponentiation, Pisano periods, Zeckendorf representation.

Output:
```json
{
  "facts": [
    "For computing Fibonacci numbers, Kitamasa method and Bostan-Mori algorithm are advanced techniques that outperform standard approaches for very large indices",
    "Binet's formula provides a closed-form solution for Fibonacci numbers using the golden ratio phi=(1+√5)/2, allowing direct calculation without iteration",
    "Matrix exponentiation computes the n-th Fibonacci number in O(log n) time complexity by
    raising the transformation matrix [[1,1],[1,0]] to the nth power",
    "Pisano periods enable efficient modular Fibonacci computation by exploiting the periodic
    nature of Fibonacci sequences under modulo operations, particularly useful for large n with
    modular arithmetic"
  ]
}
```

---
**Example 5: Technical Analysis (GitHub Issues)**

Input:
user: Analyze MassGen GitHub issues to understand feature requests
assistant: Using custom GitHub tool to fetch issues... Found requests for memory system, multi-turn
context, custom tools integration. Web search shows market trend toward agentic frameworks with
tool extensibility and persistent memory.

Output:
```json
{
  "facts": [
    "Custom tool APIs in MassGen provide structured, reliable data access compared to web page
    scraping which is unreliable due to frequent HTML structure changes, rate limiting, and
    authentication requirements",
    "MassGen v0.1.1 introduced support for registering Python functions as custom tools through
    YAML configuration files, allowing users to extend agent capabilities without modifying core
    framework code",
    "Current market trends in AI development show strong demand for agentic frameworks that
    support tool extensibility and persistent memory capabilities, enabling agents to use
    domain-specific APIs and maintain context across sessions"
  ]
}
```

---
**Example 6: What NOT to Extract**

Input:
user: Explain MassGen's backend architecture
assistant: I'll search the codebase for backend information.
assistant: I found it in massgen/backend/base.py. The LLMBackend class has a _is_stateful property.
assistant: Agent 1's response is more detailed than Agent 2's. I should vote for agent1 now.
assistant: The response should start with a summary and avoid heavy Markdown formatting.
assistant: Providing templates on request enhances documentation clarity.

Output (WRONG - includes agent comparisons, files, voting, generic advice):
```json
{
  "facts": [
    "Agent 1's response is more detailed and comprehensive about MassGen backends",
    "Based on evaluation, the evaluator votes in favor of Agent 1",
    "Backend code is in massgen/backend/base.py with _is_stateful property",
    "Response should start with summary and avoid Markdown",
    "Providing templates on request enhances documentation clarity and usability"
  ]
}
```

Output (CORRECT - only domain knowledge, no agents/voting/generic advice):
```json
{
  "facts": [
    "MassGen's LLM backend supports both stateful and stateless modes where stateful backends maintain conversation history across turns while stateless backends treat each request independently"
  ]
}
```

---
**Example 7: Empty Cases (Skip These)**

Input:
user: Hi, how are you?
assistant: I'm doing well, thanks! How can I help you today?

Output:
```json
{
  "facts": []
}
```

Input:
assistant: Still working on this...
assistant: Making good progress...

Output:
```json
{
  "facts": []
}
```

---

NOW EXTRACT FACTS:

Extract facts from the following conversation. Remember:
- Return ONLY simple strings in a "facts" array - NO nested objects or metadata fields
- Each fact must be SELF-CONTAINED with full context (can be understood 6 months later without the conversation)
- Include specific details: numbers, names, technologies, reasons WHY things work/don't work
- Focus on HIGH-LEVEL knowledge: insights, capabilities, domain expertise, recommendations
- Avoid: file paths, line numbers, vague references ("this", "that", "the system"), generic statements
- Use concrete language with specific nouns and explicit context

Return ONLY valid JSON with this exact structure:
```json
{
  "facts": ["fact string 1", "fact string 2", "fact string 3"]
}
```
"""


def get_fact_extraction_prompt(prompt_type: str = "default") -> str:
    """
    Get a fact extraction prompt by type.

    Args:
        prompt_type: Type of prompt to retrieve. Options:
            - "default": Universal multi-agent prompt (MASSGEN_UNIVERSAL_FACT_EXTRACTION_PROMPT)
            - Add more specialized prompts as needed

    Returns:
        The fact extraction prompt string

    Raises:
        ValueError: If prompt_type is not recognized
    """
    prompts = {
        "default": MASSGEN_UNIVERSAL_FACT_EXTRACTION_PROMPT,
    }

    if prompt_type not in prompts:
        raise ValueError(
            f"Unknown prompt type '{prompt_type}'. Available types: {list(prompts.keys())}",
        )

    return prompts[prompt_type]
