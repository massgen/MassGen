---
name: serena
description: This skill provides symbol-level code understanding and navigation using Language Server Protocol (LSP). Enables IDE-like capabilities for finding symbols, tracking references, and making precise code edits at the symbol level.
license: MIT
---

# Serena: Symbol-Level Code Understanding

Navigate and manipulate code at the symbol level using IDE-like semantic analysis powered by Language Server Protocol (LSP).

## Purpose

The serena skill provides access to Serena, a coding agent toolkit that transforms text-based LLMs into symbol-aware code agents. Unlike traditional text search (ripgrep) or structural search (ast-grep), Serena understands code semantics through LSP integration.

**Key capabilities:**

1. **Symbol Discovery**: Find classes, functions, variables, and types by name across 30+ languages
2. **Reference Tracking**: Discover all locations where a symbol is referenced or used
3. **Precise Editing**: Insert code at specific symbol locations with surgical precision

Serena operates at the **symbol level** rather than the text or syntax level, providing true IDE-like understanding of code structure, scope, and relationships.

## When to Use This Skill

Use the serena skill when you need symbol-level code understanding:

**Code Navigation:**
- Finding where a class, function, or variable is defined
- Discovering all places where a symbol is used (call sites, imports, references)
- Understanding code dependencies and relationships
- Tracing execution flow through function calls

**Code Understanding:**
- Analyzing impact of changes to a function or class
- Understanding inheritance hierarchies and type relationships
- Identifying dead code (symbols never referenced)
- Mapping API usage patterns across a codebase

**Code Refactoring:**
- Renaming symbols while tracking all usage locations
- Adding methods or fields to specific classes
- Inserting error handling after specific function calls
- Modifying all call sites of a deprecated function

**Choose serena over file_search (ripgrep/ast-grep) when:**
- You need to understand symbol semantics (not just text patterns)
- You want to track references across files and modules
- You need precise insertion points based on code structure
- You're working with complex, multi-file codebases

**Still use file_search when:**
- Searching for text patterns, comments, or strings
- Finding todos, security issues, or documentation
- You need faster, simpler pattern matching
- Symbol-level precision isn't required

## Prerequisites

Serena is available via `uvx` - no installation required!

**Usage (Docker and Local):**
```bash
# Use uvx to run serena on-demand (no permanent installation)
uvx --from git+https://github.com/oraios/serena serena --help

# This works in both Docker mode (uv pre-installed) and local mode (install uv first)
```

**First-time local setup (if uv not installed):**
```bash
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Then use uvx as shown above
```

**Language Server Requirements:**

Serena uses LSP servers for semantic analysis. Most common languages are supported out-of-the-box:
- Python (pyright, jedi)
- JavaScript/TypeScript (typescript-language-server)
- Rust (rust-analyzer)
- Go (gopls)
- Java (jdtls)
- C/C++ (clangd)

See [Serena documentation](https://oraios.github.io/serena) for full language support and setup.

## Core Operations

### 1. Finding Symbols (`find_symbol`)

Locate where a symbol is **defined** in your codebase.

**Note:** All examples below use the short form `serena <command>`. The full command is:
```bash
uvx --from git+https://github.com/oraios/serena serena <command>
```

```python
# Find a class definition
execute_command("uvx --from git+https://github.com/oraios/serena serena find_symbol --name 'UserService' --type class")

# Find a function definition
execute_command("uvx --from git+https://github.com/oraios/serena serena find_symbol --name 'authenticate' --type function")

# Find a variable definition
execute_command("uvx --from git+https://github.com/oraios/serena serena find_symbol --name 'API_KEY' --type variable")
```

**Use cases:**
- Locating the definition of a class before modifying it
- Finding where a function is implemented
- Understanding where constants are defined
- Tracing type definitions in typed languages

**Output format:**
```
File: src/services/user_service.py
Line: 42
Symbol: UserService (class)
Context: class UserService(BaseService):
```

### 2. Finding References (`find_referencing_symbols`)

Discover **all locations** where a symbol is used, imported, or referenced.

```python
# Find all usages of a class
execute_command("serena find_referencing_symbols --name 'UserService'")

# Find all call sites of a function
execute_command("serena find_referencing_symbols --name 'authenticate'")

# Find all reads/writes of a variable
execute_command("serena find_referencing_symbols --name 'API_KEY'")
```

**Use cases:**
- Impact analysis before refactoring
- Finding all call sites of a function
- Tracking API usage across modules
- Identifying unused symbols (zero references)
- Understanding data flow and dependencies

**Output format:**
```
Found 12 references to 'authenticate':

1. src/api/routes.py:34
   authenticate(user_credentials)

2. src/middleware/auth.py:18
   from services import authenticate

3. tests/test_auth.py:56
   mock_authenticate = Mock(spec=authenticate)
...
```

### 3. Precise Code Insertion (`insert_after_symbol`)

Insert code at specific symbol locations with surgical precision.

```python
# Add a method to a class
execute_command("""serena insert_after_symbol --name 'UserService' --type class --code '
    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter_by(email=email).first()
'""")

# Insert error handling after a function call
execute_command("""serena insert_after_symbol --name 'database_query' --code '
    if result is None:
        raise DatabaseError("Query returned no results")
'""")

# Add a field to a dataclass
execute_command("""serena insert_after_symbol --name 'User' --type class --code '
    email_verified: bool = False
'""")
```

**Use cases:**
- Adding methods to existing classes
- Inserting validation or error handling
- Adding fields to data structures
- Injecting logging or monitoring code
- Implementing missing functionality

**Safety features:**
- Respects indentation and code formatting
- Maintains syntactic validity
- Positions code correctly within scope
- Preserves existing code structure

## Workflow Patterns

### Pattern 1: Safe Refactoring

When changing a function signature or behavior:

```bash
# Step 1: Find the function definition
serena find_symbol --name 'process_payment' --type function

# Step 2: Find all call sites
serena find_referencing_symbols --name 'process_payment'

# Step 3: Analyze impact (review output)
# [Review all usage locations to understand impact]

# Step 4: Make changes with confidence
# [Update function and all call sites based on findings]
```

### Pattern 2: Adding Functionality

When extending a class with new methods:

```bash
# Step 1: Locate the class
serena find_symbol --name 'PaymentProcessor' --type class

# Step 2: Verify no conflicts
serena find_symbol --name 'process_refund' --type function

# Step 3: Insert new method
serena insert_after_symbol --name 'PaymentProcessor' --type class --code '
    def process_refund(self, payment_id: str, amount: float) -> bool:
        # Implementation here
        pass
'
```

### Pattern 3: Understanding Dependencies

When analyzing code relationships:

```bash
# Step 1: Find class definition
serena find_symbol --name 'DatabaseManager' --type class

# Step 2: Find all usages
serena find_referencing_symbols --name 'DatabaseManager'

# Step 3: For each usage, find what symbols use that code
# [Repeat reference tracking to build dependency graph]
```

### Pattern 4: Dead Code Detection

When identifying unused code:

```bash
# Step 1: Find symbol definition
serena find_symbol --name 'legacy_auth_handler'

# Step 2: Check references
serena find_referencing_symbols --name 'legacy_auth_handler'

# Step 3: If zero references (except definition), mark for removal
# [If output shows only the definition, symbol is unused]
```

## Integration with file_search

Serena and file_search (ripgrep/ast-grep) are **complementary tools**. Use them together:

### When to Combine Tools

**Use ripgrep THEN serena:**
```bash
# 1. Find potential matches with ripgrep (fast, broad)
rg "authenticate" --type py

# 2. Narrow to specific symbol with serena (precise)
serena find_symbol --name 'authenticate' --type function
serena find_referencing_symbols --name 'authenticate'
```

**Use serena THEN ripgrep:**
```bash
# 1. Find symbol definition with serena
serena find_symbol --name 'UserService'

# 2. Search for related patterns with ripgrep
rg "UserService\(" --type py  # Find direct instantiations
rg "class.*UserService" --type py  # Find subclasses
```

### Complementary Strengths

| Task | Best Tool | Why |
|------|-----------|-----|
| Find string literals | ripgrep | Text-based, fast |
| Find TODOs/comments | ripgrep | Text-based |
| Find symbol definition | serena | Symbol-aware |
| Find all references | serena | Semantic understanding |
| Find code patterns | ast-grep | Syntax-aware |
| Insert at symbol | serena | Precise positioning |
| Search across languages | ripgrep | Language-agnostic |
| Understand scope | serena | LSP semantic info |

## Best Practices

### 1. Start with Symbol Discovery

Always locate the symbol definition first:
```bash
# GOOD: Find definition, then references
serena find_symbol --name 'MyClass'
serena find_referencing_symbols --name 'MyClass'

# AVOID: Searching for references without confirming definition exists
```

### 2. Use Specific Symbol Types

Narrow searches with `--type` when possible:
```bash
# GOOD: Specific type reduces ambiguity
serena find_symbol --name 'User' --type class

# LESS PRECISE: May match User function, User variable, etc.
serena find_symbol --name 'User'
```

### 3. Verify Before Inserting

Always find the symbol before inserting code:
```bash
# GOOD: Verify target exists first
serena find_symbol --name 'PaymentService' --type class
# [Review output to confirm correct class]
serena insert_after_symbol --name 'PaymentService' --code '...'

# RISKY: Inserting without verification
serena insert_after_symbol --name 'PaymentService' --code '...'
```

### 4. Review Reference Counts

Check reference output for impact analysis:
```bash
# Find references and assess impact
serena find_referencing_symbols --name 'deprecated_function'
# If 50+ references, plan careful migration
# If 0 references, safe to remove
```

### 5. Combine with git diff

After insertions, verify changes:
```bash
serena insert_after_symbol --name 'MyClass' --code '...'
git diff  # Review actual changes before committing
```

## Supported Languages

Serena supports 30+ languages through LSP integration:

**Tier 1 (Fully tested):**
- Python, JavaScript, TypeScript, Rust, Go, Java, C/C++

**Tier 2 (Community tested):**
- C#, Ruby, PHP, Kotlin, Swift, Scala

**Tier 3 (Experimental):**
- Haskell, Elixir, Clojure, Erlang, Julia, R, and more

For the complete list and setup instructions, see [Serena language support docs](https://oraios.github.io/serena/languages).

## Limitations

### When NOT to Use Serena

1. **Searching text/comments**: Use ripgrep instead
   ```bash
   # WRONG TOOL: Serena doesn't search comments
   serena find_symbol --name "TODO"

   # RIGHT TOOL: Use ripgrep for text
   rg "TODO"
   ```

2. **Generated code**: LSP may not index auto-generated files
   - Use ripgrep for build artifacts, generated code

3. **Very large codebases**: Symbol indexing can be slow
   - Use ripgrep for initial broad searches
   - Use serena for precise follow-up

4. **Dynamic languages without types**: Limited semantic info
   - Python without type hints has reduced precision
   - JavaScript without TypeScript has fewer guarantees

### Known Edge Cases

- **Ambiguous symbols**: Multiple symbols with same name may require manual disambiguation
- **Macro-generated code**: C/C++ macros may confuse LSP
- **Circular dependencies**: May affect reference tracking accuracy
- **Incomplete projects**: Missing dependencies can reduce LSP effectiveness

## Performance Considerations

### Token Efficiency

Serena is designed for **token-efficient code navigation**:

```bash
# Traditional approach (inefficient)
execute_command("cat entire_file.py")  # 1000+ tokens
# [Search for symbol manually in output]

# Serena approach (efficient)
serena find_symbol --name 'MyClass'  # 50 tokens
# [Get precise location immediately]
```

### Speed Characteristics

- **Symbol lookup**: Near-instant (LSP indexed)
- **Reference finding**: Fast (O(log n) with indexing)
- **Code insertion**: Instant (direct file modification)

**Comparison with alternatives:**
- Ripgrep: Faster for text search (no semantic understanding)
- AST-grep: Comparable speed (syntax vs semantic)
- Serena: Slower initial startup (LSP indexing), faster precise queries

## Troubleshooting

### Symbol Not Found

If `find_symbol` returns no results:

1. **Verify symbol exists**: Use ripgrep to confirm
   ```bash
   rg "class MyClass" --type py
   ```

2. **Check language server**: Ensure LSP is configured for the language
   ```bash
   serena status  # Check LSP server status
   ```

3. **Try case variations**: Symbol names are case-sensitive
   ```bash
   serena find_symbol --name 'myclass'  # Try different cases
   ```

4. **Rebuild index**: Force LSP to re-index
   ```bash
   serena reindex  # Rebuild symbol index
   ```

### Too Many References

If `find_referencing_symbols` returns hundreds of results:

1. **Use file_search first**: Narrow scope with ripgrep
   ```bash
   rg "MyClass" src/services/  # Limit to specific directory
   serena find_referencing_symbols --name 'MyClass' --path src/services/
   ```

2. **Filter by reference type**: Focus on specific usage patterns
   ```bash
   # Look for imports only
   rg "from .* import.*MyClass" --type py
   ```

3. **Prioritize recent changes**: Check git history first
   ```bash
   git log --all -p -S 'MyClass' --since="1 week ago"
   ```

### Insertion Failures

If `insert_after_symbol` fails:

1. **Verify symbol exists**: Find it first
2. **Check syntax**: Ensure inserted code is valid
3. **Review indentation**: Match surrounding code style
4. **Test incrementally**: Insert small changes first

## Resources

- [Serena GitHub](https://github.com/oraios/serena)
- [Serena Documentation](https://oraios.github.io/serena)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [Solid-LSP (Serena's foundation)](https://github.com/oraios/solid-lsp)
