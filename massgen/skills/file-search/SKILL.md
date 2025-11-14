---
name: file-search
description: This skill should be used when agents need to search codebases for text patterns or structural code patterns. Provides fast search using ripgrep for text and ast-grep for syntax-aware code search.
license: MIT
---

# File Search Skill

Search code efficiently using ripgrep for text patterns and ast-grep for structural code patterns.

## Purpose

The file-search skill provides access to two powerful search tools pre-installed in MassGen environments:

1. **ripgrep (rg)**: Ultra-fast text search with regex support for finding strings, patterns, and text matches
2. **ast-grep (sg)**: Syntax-aware structural search for finding code patterns based on abstract syntax trees

Use these tools to understand codebases, find usage patterns, analyze impact of changes, and locate specific code constructs. Both tools are significantly faster than traditional `grep` or `find` commands.

## When to Use This Skill

Use the file-search skill when:

- Understanding a new codebase (finding entry points, key classes)
- Finding all usages of a function, class, or variable before refactoring
- Locating specific code patterns (error handling, API calls, etc.)
- Searching for security issues (hardcoded credentials, SQL queries, eval usage)
- Analyzing dependencies and imports
- Finding TODOs, FIXMEs, or code comments

Choose **ripgrep** for:
- Text-based searches (strings, comments, variable names)
- Fast, simple pattern matching across many files
- When the exact code structure doesn't matter

Choose **ast-grep** for:
- Structural code searches (function signatures, class definitions)
- Syntax-aware matching (understanding code semantics)
- Complex refactoring (finding specific code patterns)

## Invoking Search Tools

In MassGen, use the `execute_command` tool to run ripgrep and ast-grep:

```python
# Using ripgrep
execute_command("rg 'pattern' --type py src/")

# Using ast-grep
execute_command("sg --pattern 'class $NAME { $$$ }' --lang python")
```

Both tools are pre-installed in MassGen Docker containers and available via shell execution.

## Targeting Your Searches

**CRITICAL**: Always start with targeted, narrow searches to avoid overwhelming results. Getting thousands of matches makes analysis impossible and wastes tokens.

These strategies apply to **both ripgrep and ast-grep**.

### Scope-Limiting Strategies

Apply these strategies from the start to target searches effectively:

1. **Specify File Types/Languages**: Always filter by language
   ```bash
   # Ripgrep
   rg "function" --type py --type js

   # AST-grep
   sg --pattern 'function $NAME($$$) { $$$ }' --lang js
   ```

2. **Target Specific Directories**: Search in likely locations first
   ```bash
   # Ripgrep
   rg "LoginService" src/services/

   # AST-grep
   sg --pattern 'class LoginService { $$$ }' src/services/
   ```

3. **Use Specific Patterns**: Make patterns as specific as possible
   ```bash
   # Ripgrep: BAD - too broad
   rg "user"
   # Ripgrep: GOOD - more specific
   rg "class.*User.*Service" --type py

   # AST-grep: BAD - too broad
   sg --pattern '$X'
   # AST-grep: GOOD - more specific
   sg --pattern 'class $NAME extends UserService { $$$ }' --lang js
   ```

4. **Limit Result Count**: Use head to cap results
   ```bash
   # Ripgrep
   rg "import" --type py | head -20
   rg "TODO" --count

   # AST-grep
   sg --pattern 'import $X from $Y' --lang js | head -20
   ```

### Progressive Search Refinement

When exploring unfamiliar code, use this workflow:

**Ripgrep example:**
```bash
# Step 1: Count matches to assess scope
rg "pattern" --count --type py

# Step 2: If too many results, add more filters
rg "pattern" --type py src/ --glob '!tests'

# Step 3: Show limited results to inspect
rg "pattern" --type py src/ | head -30

# Step 4: Once confirmed, get full results or target further
rg "pattern" --type py src/specific_module/
```

**AST-grep example:**
```bash
# Step 1: Assess scope with broad structural pattern
sg --pattern 'function $NAME($$$) { $$$ }' --lang js | head -10

# Step 2: If too many results, narrow to specific directory
sg --pattern 'function $NAME($$$) { $$$ }' --lang js src/

# Step 3: Make pattern more specific
sg --pattern 'async function $NAME($$$) { $$$ }' --lang js src/

# Step 4: Target exact location
sg --pattern 'async function $NAME($$$) { $$$ }' --lang js src/services/
```

### When You Get Too Many Results

If a search returns hundreds of matches (applies to both `rg` and `sg`):

1. **Add file type/language filters**: `--type py` (rg) or `--lang python` (sg)
2. **Narrow directory scope**: Search `src/` instead of `.`
3. **Make pattern more specific**: Add context around the pattern
4. **Use word boundaries**: `-w` flag for whole words only (rg)
5. **Pipe to head**: Limit output with `| head -50`
6. **Exclude test files**: `--glob '!*test*'` (rg) or avoid test directories (sg)

**Example of refinement:**
```bash
# Step 1: Too broad (10,000+ matches)
rg "error"

# Step 2: Add file type (1,000 matches)
rg "error" --type py

# Step 3: Add directory scope (200 matches)
rg "error" --type py src/

# Step 4: Make pattern specific (20 matches)
rg "raise.*Error" --type py src/

# Step 5: Target exact location (5 matches)
rg "raise.*Error" --type py src/services/
```

## How to Use

### Ripgrep (rg)

```bash
# Basic text search
rg "pattern" --type py --type js

# Common flags
-i              # Case-insensitive
-w              # Match whole words only
-l              # Show only filenames
-n              # Show line numbers
-C 3            # Show 3 lines of context
--count         # Count matches per file
--glob '!dir'   # Exclude directory

# Examples
rg "function.*login" --type js src/
rg -i "TODO" --count
rg "auth|login|session" --type py
```

### AST-Grep (sg)

```bash
# Structural code search
sg --pattern 'function $NAME($$$) { $$$ }' --lang js

# Metavariables
$VAR     # Matches single AST node
$$$      # Matches zero or more nodes

# Examples
sg --pattern 'class $NAME { $$$ }' --lang python
sg --pattern 'import $X from $Y' --lang js
sg --pattern 'async function $NAME($$$) { $$$ }' src/
```

## Common Search Patterns

```bash
# Security issues
rg -i "password\s*=\s*['\"]" --type py
rg "\beval\(" --type js

# TODOs and comments
rg "TODO|FIXME|HACK"

# Code structures
sg --pattern 'class $NAME { $$$ }' --lang python
sg --pattern 'try { $$$ } catch ($E) { $$$ }' --lang js

# Dependencies
rg "from requests import" --type py
rg "require\(['\"]" --type js

# Refactoring
rg "\.old_method\(" --type py
rg "@deprecated" -A 5
```

## File Type Filters

Common ripgrep file types: `py`, `js`, `ts`, `rust`, `go`, `java`, `c`, `cpp`, `html`, `css`, `json`, `yaml`, `md`

Use `--type-list` to see all available types, or define custom types:
```bash
rg --type-add 'config:*.{yml,yaml,toml,ini}' --type config "pattern"
```

## Performance Tips

See "Targeting Your Searches" section for comprehensive strategies. Key tips:

```bash
# Limit scope to specific directories
rg "pattern" src/

# Filter by file type
rg "pattern" --type py --type js

# Exclude large directories
rg "pattern" --glob '!{node_modules,venv,.git}'

# Use fixed strings (no regex) for speed
rg -F "exact string"

# Count before viewing full results
rg "pattern" --count --type py
```

## Best Practices

1. **Start Narrow, Then Broaden**: Use specific patterns, file types, and directory scope from the start
2. **Count Before Viewing**: Use `--count` or `| head -N` to preview result volume
3. **Always Specify File Types**: Use `--type` (rg) or `--lang` (sg) to filter by language
4. **Exclude Common Noise**: Add `--glob '!{node_modules,venv,.git,dist,build}'` habitually
5. **Combine Tools**: Use `rg` for text patterns, `sg` for structural code patterns
6. **Use Context Strategically**: Add `-C N` for surrounding lines, but be mindful of output volume


## Troubleshooting

- **No matches found**: Check file type filters, try `-i` for case-insensitive, search partial pattern first
- **Too slow**: Exclude directories with `--glob`, limit file types with `--type`, narrow search path
- **AST-grep issues**: Verify `--lang` is correct, try simpler pattern, use `rg` to verify code exists

## Resources

- [Ripgrep docs](https://github.com/BurntSushi/ripgrep)
- [AST-grep docs](https://ast-grep.github.io/)
