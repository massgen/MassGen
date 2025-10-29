Validating Configurations
=========================

MassGen includes a built-in configuration validator that helps you catch errors before running your agents. The validator checks for:

- **Schema correctness**: Required fields, valid types, and correct structure
- **Backend compatibility**: Ensures requested features are supported by the backend
- **Best practices**: Warns about potential issues or suboptimal configurations

Validation Methods
------------------

Standalone Validation Command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Validate a configuration file without running it:

.. code-block:: bash

   # Basic validation
   massgen --validate config.yaml

   # Strict mode (treat warnings as errors)
   massgen --validate config.yaml --strict

   # JSON output for scripts/CI
   massgen --validate config.yaml --json

The validator will exit with code 0 if the config is valid, or 1 if errors are found (or warnings in strict mode).

Automatic Validation
~~~~~~~~~~~~~~~~~~~~

By default, MassGen automatically validates configurations when you run commands:

.. code-block:: bash

   # Validation happens automatically
   massgen --config config.yaml "What is machine learning?"

**Error behavior**: If errors are found, MassGen will display them and exit before running agents.

**Warning behavior**: Warnings are displayed but don't block execution (unless ``--strict-validation`` is used).

**Disabling validation**: Use ``--skip-validation`` to bypass validation:

.. code-block:: bash

   massgen --config config.yaml --skip-validation "Your question"

Validation Flags
~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Flag
     - Description
   * - ``--validate <file>``
     - Validate a config file without running it
   * - ``--strict``
     - Treat warnings as errors (use with ``--validate``)
   * - ``--json``
     - Output validation results in JSON format
   * - ``--skip-validation``
     - Skip automatic validation when loading configs
   * - ``--strict-validation``
     - Treat warnings as errors during automatic validation

What Gets Validated
-------------------

Required Fields
~~~~~~~~~~~~~~~

The validator ensures all required fields are present:

.. code-block:: yaml

   # ✅ Valid - has all required fields
   agents:
     - id: "agent-1"          # Required
       backend:               # Required
         type: "openai"       # Required
         model: "gpt-4o"      # Required

   # ❌ Invalid - missing required fields
   agents:
     - backend:
         type: "openai"
         # Missing: id, model

Field Types
~~~~~~~~~~~

All fields must have the correct type:

.. code-block:: yaml

   # ❌ Invalid types
   agents:
     - id: 123                    # Should be string
       backend:
         type: "openai"
         model: "gpt-4o"
         enable_web_search: "yes" # Should be boolean (true/false)

Backend Capabilities
~~~~~~~~~~~~~~~~~~~~

The validator checks that backends support requested features:

.. code-block:: yaml

   # ❌ Invalid - lmstudio doesn't support web_search
   agents:
     - id: "agent-1"
       backend:
         type: "lmstudio"
         model: "custom"
         enable_web_search: true  # Error: not supported

   # ✅ Valid - openai supports web_search
   agents:
     - id: "agent-1"
       backend:
         type: "openai"
         model: "gpt-4o"
         enable_web_search: true

Enum Values
~~~~~~~~~~~

Fields with limited valid values are validated:

.. code-block:: yaml

   # ❌ Invalid display_type
   ui:
     display_type: "fancy"  # Must be: rich_terminal, simple

   # ❌ Invalid permission_mode
   agents:
     - id: "agent-1"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-5-20250929"
         permission_mode: "auto"  # Must be: approve, reject, prompt

Duplicate Agent IDs
~~~~~~~~~~~~~~~~~~~

Each agent must have a unique ID:

.. code-block:: yaml

   # ❌ Invalid - duplicate IDs
   agents:
     - id: "agent-1"
       backend: {...}
     - id: "agent-1"        # Error: duplicate ID
       backend: {...}

V1 Config Detection
~~~~~~~~~~~~~~~~~~~

The validator rejects legacy V1 configs with a helpful migration message:

.. code-block:: yaml

   # ❌ V1 config (no longer supported)
   models: ["gpt-4o", "claude-3-opus"]
   num_agents: 2

   # Error: V1 config format detected.
   # Suggestion: Migrate to V2 config format.

Warnings
--------

The validator generates warnings for potential issues that don't prevent execution:

Multi-Agent Without Orchestrator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # ⚠️ Warning: Consider adding orchestrator config
   agents:
     - id: "agent-1"
       backend: {...}
     - id: "agent-2"
       backend: {...}
   # Missing: orchestrator section

Conflicting Tool Filters
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # ⚠️ Warning: Using both filters can be confusing
   agents:
     - id: "agent-1"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-5-20250929"
         allowed_tools: ["Read", "Write"]
         exclude_tools: ["Bash"]  # Prefer one approach

Programmatic Usage
------------------

You can use the validator in Python code:

.. code-block:: python

   from massgen.config_validator import ConfigValidator

   # Validate a config file
   validator = ConfigValidator()
   result = validator.validate_config_file("config.yaml")

   if result.has_errors():
       print(result.format_errors())
       exit(1)

   if result.has_warnings():
       print(result.format_warnings())

   # Validate a config dict
   config = {
       "agent": {
           "id": "test",
           "backend": {"type": "openai", "model": "gpt-4o"}
       }
   }
   result = validator.validate_config(config)

   # Get results as dict (for JSON serialization)
   result_dict = result.to_dict()
   # {
   #   "valid": True,
   #   "error_count": 0,
   #   "warning_count": 0,
   #   "errors": [],
   #   "warnings": []
   # }

CI/CD Integration
-----------------

Use the validator in CI pipelines to catch config errors:

.. code-block:: bash

   #!/bin/bash
   # validate_configs.sh

   EXIT_CODE=0

   for config in configs/*.yaml; do
       echo "Validating $config..."
       if ! massgen --validate "$config" --strict --json > "${config}.validation.json"; then
           echo "❌ Validation failed: $config"
           EXIT_CODE=1
       fi
   done

   exit $EXIT_CODE

GitHub Actions Example:

.. code-block:: yaml

   name: Validate Configs
   on: [push, pull_request]

   jobs:
     validate:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - uses: actions/setup-python@v4
           with:
             python-version: '3.11'
         - name: Install MassGen
           run: pip install massgen
         - name: Validate all configs
           run: |
             for config in configs/*.yaml; do
               massgen --validate "$config" --strict
             done

Best Practices
--------------

1. **Validate before committing**: Run ``massgen --validate`` on config files before committing them to version control.

2. **Use strict mode in CI**: Set ``--strict`` in CI/CD to catch warnings early.

3. **Check JSON output**: Parse ``--json`` output in scripts for programmatic error handling.

4. **Don't skip validation**: Avoid ``--skip-validation`` unless debugging validator issues.

5. **Fix warnings**: While non-blocking, warnings often indicate configuration issues worth addressing.

Error Messages
--------------

The validator provides clear error messages with suggestions:

.. code-block:: text

   🔴 Configuration Errors Found:

   ❌ [agents[0].backend.type] Unknown backend type: 'gpt'
      💡 Suggestion: Use one of: openai, claude, gemini, grok, ...

   ❌ [agents[0]] Agent missing required field 'id'
      💡 Suggestion: Add 'id: "agent-name"'

Each error shows:

- **Location**: Which part of the config has the error (e.g., ``agents[0].backend.type``)
- **Message**: What's wrong
- **Suggestion**: How to fix it

Common Errors and Fixes
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Error
     - Fix
   * - ``Unknown backend type``
     - Use a valid backend: openai, claude, gemini, etc.
   * - ``Agent missing required field 'id'``
     - Add ``id: "agent-name"`` to each agent
   * - ``Backend missing required field 'model'``
     - Add ``model: "model-name"`` to backend
   * - ``Backend does not support web_search``
     - Remove ``enable_web_search`` or use a different backend
   * - ``Duplicate agent ID``
     - Ensure each agent has a unique ID
   * - ``Invalid permission_mode``
     - Use: approve, reject, or prompt
   * - ``V1 config format detected``
     - Migrate to V2 format (see :doc:`../reference/yaml_schema`)

See Also
--------

- :doc:`../reference/yaml_schema` - Complete configuration schema reference
- :doc:`../reference/configuration_examples` - Example configurations
- :doc:`../quickstart/configuration` - Getting started with configs
