---
name: file_search
description: This skill should be used when agents need to search codebases for text patterns or structural code patterns. Provides fast search using ripgrep for text and ast-grep for syntax-aware code search.
license: MIT
---

# File Search Skill

Search code efficiently using ripgrep for text patterns and ast-grep for structural code patterns.

## Purpose

The file_search skill provides access to two powerful search tools pre-installed in MassGen environments:

1. **ripgrep (rg)**: Ultra-fast text search with regex support for finding strings, patterns, and text matches
2. **ast-grep (sg)**: Syntax-aware structural search for finding code patterns based on abstract syntax trees

Use these tools to understand codebases, find usage patterns, analyze impact of changes, and locate specific code constructs. Both tools are significantly faster than traditional `grep` or `find` commands.

## When to Use This Skill

Use the file_search skill when:

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

## How to Use

### Ripgrep (rg)

Ripgrep is a line-oriented search tool that recursively searches directories for a regex pattern.

**Basic Usage:**
```bash
# Search for a pattern in all files
rg "function.*login"

# Search in specific file types
rg "TODO" --type py
rg "console.log" --type js

# Case-insensitive search
rg -i "password"

# Show line numbers and context
rg -n -C 3 "error"

# Search only filenames
rg --files | rg "test"
```

**Advanced Usage:**
```bash
# Search with multiple patterns
rg "auth|login|session"

# Exclude directories
rg "secret" --glob '!node_modules'

# Search for whole words only
rg -w "user"

# Show only files with matches
rg -l "deprecated"

# Count matches per file
rg "TODO" --count

# Replace preview (doesn't modify files)
rg "old_function" -r "new_function"
```

### AST-Grep (sg)

AST-grep searches code based on abstract syntax tree patterns, making it ideal for finding specific code structures.

**Basic Usage:**
```bash
# Find function definitions
sg --pattern 'function $NAME() { $$$ }'

# Find class declarations
sg --pattern 'class $NAME { $$$ }'

# Find import statements
sg --pattern 'import $X from $Y'

# Language-specific search
sg --pattern 'def $FUNC($$$):' --lang python
```

**Advanced Usage:**
```bash
# Find async functions
sg --pattern 'async function $NAME($$$) { $$$ }'

# Find React components
sg --pattern 'const $NAME = () => { $$$ }' --lang tsx

# Find specific method calls
sg --pattern '$OBJ.map($$$)' --lang js

# Rewrite code (preview mode)
sg --pattern 'console.log($$$)' --rewrite 'logger.info($$$)'
```

## Common Patterns

### Finding Security Issues

```bash
# Find hardcoded credentials
rg -i "password\s*=\s*['\"]" --type py

# Find SQL queries (potential injection)
rg "execute\(.*\+.*\)" --type py

# Find eval usage
rg "\beval\(" --type js
```

### Finding TODOs and FIXMEs

```bash
# Find all TODOs
rg "TODO|FIXME|XXX|HACK"

# Find TODOs with author
rg "TODO\(@\w+\)"

# Find critical issues only
rg "FIXME|CRITICAL|URGENT"
```

### Finding Code Patterns

```bash
# Find all class definitions
sg --pattern 'class $NAME { $$$ }'

# Find all async/await usage
rg "async|await" --type js

# Find error handling
sg --pattern 'try { $$$ } catch ($E) { $$$ }'

# Find API endpoints
rg "@app\.(get|post|put|delete)" --type py
```

### Analyzing Dependencies

```bash
# Find all imports from a module
rg "from requests import"

# Find all requires
rg "require\(['\"]" --type js

# Find unused imports (approximate)
rg "^import.*from" --type py | while read import; do
  module=$(echo $import | sed 's/.*from //' | tr -d "';")
  rg -q "$module" || echo "Possibly unused: $import"
done
```

### Code Refactoring

```bash
# Find old API usage
rg "\.get_user\(" --type py

# Find deprecated methods
rg "@deprecated" -A 5

# Find duplicated code
rg "def.*process.*data" --type py
```

## File Type Filters

Ripgrep supports many file types out of the box:

```bash
# Common types
--type py      # Python files
--type js      # JavaScript files
--type ts      # TypeScript files
--type rust    # Rust files
--type go      # Go files
--type java    # Java files
--type c       # C files
--type cpp     # C++ files
--type html    # HTML files
--type css     # CSS files
--type json    # JSON files
--type yaml    # YAML files
--type md      # Markdown files

# Custom type definitions
rg --type-add 'config:*.{yml,yaml,toml,ini}' --type config "database"
```

## AST-Grep Pattern Syntax

AST-grep uses metavariables to match code patterns:

- `$VAR` - Matches a single AST node (variable, expression, etc.)
- `$$$` - Matches zero or more AST nodes
- `$$$ ` with space - Matches including whitespace

**Examples:**

```bash
# Match any variable assignment
sg --pattern '$VAR = $VALUE'

# Match any function call
sg --pattern '$FUNC($$$)'

# Match specific method on any object
sg --pattern '$OBJ.getElementById($$$)'

# Match arrow functions
sg --pattern '($$$) => $$$'
```

## Performance Tips

1. **Limit Search Scope**: Search in specific directories instead of entire workspace
   ```bash
   rg "pattern" src/
   ```

2. **Use File Type Filters**: Dramatically speeds up searches
   ```bash
   rg "pattern" --type py --type js
   ```

3. **Exclude Large Directories**: Skip node_modules, .git, etc.
   ```bash
   rg "pattern" --glob '!{node_modules,venv,.git}'
   ```

4. **Use Fixed Strings**: When you don't need regex, use `-F`
   ```bash
   rg -F "exact string"
   ```

## Integration with MassGen

Both ripgrep and ast-grep are pre-installed in MassGen Docker containers. When working with code:

1. **Before Modifying Code**: Use `rg` or `sg` to understand current usage
2. **Finding Examples**: Search for similar code patterns
3. **Impact Analysis**: Find all places a change might affect
4. **Code Review**: Search for potential issues or anti-patterns

## Best Practices

1. **Start Broad, Then Narrow**: Begin with simple patterns, add filters as needed
2. **Use Context**: Add `-C` flag to see surrounding code
3. **Check File Types**: Use `--type-list` to see available file types
4. **Combine Tools**: Use `rg` for text, `sg` for structure
5. **Save Common Searches**: Create shell aliases for frequent patterns

## Example Workflows

### Refactoring a Function

```bash
# 1. Find all usages
rg "old_function_name" --type py

# 2. Find function definition
sg --pattern 'def old_function_name($$$):' --lang python

# 3. Check imports
rg "from.*import.*old_function_name"

# 4. Preview replacement
rg "old_function_name" -r "new_function_name"
```

### Understanding New Codebase

```bash
# 1. Find entry points
rg "if __name__" --type py
rg "function main" --type js

# 2. Find key classes
sg --pattern 'class $NAME { $$$ }'

# 3. Find configuration
rg "config|settings" -i --type py

# 4. Find tests
rg "def test_|it\(" --type py --type js
```

### Security Audit

```bash
# 1. Find authentication code
rg "auth|login|session" -i

# 2. Find database queries
sg --pattern '$DB.execute($$$)'

# 3. Find user input handling
rg "request\.(get|post)" --type py

# 4. Find secrets/credentials
rg -i "password|secret|api.*key"
```

## Troubleshooting

**"No matches found" but you know it exists:**
- Check file type filters
- Try case-insensitive search (`-i`)
- Search for partial pattern first

**Search is too slow:**
- Add `--glob` to exclude large directories
- Use `--type` to limit file types
- Search in specific subdirectory

**AST-grep not finding expected pattern:**
- Check language is correct (`--lang`)
- Try simpler pattern first
- Use `rg` to verify the code exists

## See Also

- `memory` skill - For storing search results
- `tasks` skill - For tracking refactoring tasks
- Ripgrep docs: https://github.com/BurntSushi/ripgrep
- AST-grep docs: https://ast-grep.github.io/
