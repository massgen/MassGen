Code Execution
===============

MassGen provides powerful command-line execution capabilities through MCP (Model Context Protocol), enabling agents to run bash commands, install packages, execute scripts, and more - all with multiple layers of security.

Quick Start
-----------

**Enable code execution for a single agent:**

.. code-block:: yaml

   agent:
     backend:
       type: "openai"
       model: "gpt-5-mini"
       cwd: "workspace"
       enable_mcp_command_line: true  # Enables code execution

**Run with code execution:**

.. code-block:: bash

   massgen "Write a Python script to analyze data.csv and create a report"

Execution Modes
---------------

MassGen supports two execution modes:

Local Mode (Default)
~~~~~~~~~~~~~~~~~~~~

Commands execute directly on your host system with pattern-based security:

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "local"  # Default

**Best for:** Development, trusted code, fast execution

Docker Mode
~~~~~~~~~~~

Commands execute inside isolated Docker containers:

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"

**Best for:** Production, untrusted code, high security requirements

See :ref:`docker-mode-setup` for setup instructions.

Code Execution vs Backend Built-in Tools
-----------------------------------------

MassGen provides **two ways** for agents to execute code:

1. **Backend Built-in Code Execution**
2. **MCP-based Code Execution** (Universal)

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Feature
     - Backend Built-in
     - MCP Code Execution
   * - **Availability**
     - Backend-specific (OpenAI, Claude Code)
     - Universal (all backends)
   * - **Configuration**
     - Automatic with supported backends
     - ``enable_mcp_command_line: true``
   * - **Execution Environment**
     - Backend provider's sandbox
     - Your environment (local/Docker)
   * - **Persistence**
     - Ephemeral (resets between sessions)
     - Persistent (packages stay installed)
   * - **File System Access**
     - Limited to backend's environment
     - Full access to workspace
   * - **Package Installation**
     - Backend-managed
     - You control (pip, npm, etc.)
   * - **Network Access**
     - Provider-controlled
     - Configurable (local: full, Docker: none/bridge/host)
   * - **Use Case**
     - Quick calculations, simple scripts
     - Complex workflows, persistent environments

**You can use both simultaneously!** The agent will choose the most appropriate tool for each task.

Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Enable MCP code execution with minimal setup:

.. code-block:: yaml

   agent:
     backend:
       type: "openai"
       model: "gpt-5-mini"
       cwd: "workspace"
       enable_mcp_command_line: true

Advanced Configuration
~~~~~~~~~~~~~~~~~~~~~~

Full configuration with Docker mode and security:

.. code-block:: yaml

   agent:
     backend:
       type: "claude"
       model: "claude-sonnet-4"
       cwd: "workspace"

       # Enable MCP code execution
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"  # or "local"

       # Docker-specific settings (if using docker mode)
       command_line_docker_image: "massgen/mcp-runtime:latest"
       command_line_docker_memory_limit: "2g"
       command_line_docker_cpu_limit: 4.0
       command_line_docker_network_mode: "none"  # "none", "bridge", or "host"

       # Command filtering (optional)
       command_line_whitelist_patterns: ["pip install.*", "python .*"]
       command_line_blacklist_patterns: ["rm -rf /", "sudo .*"]

Configuration Parameters
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Parameter
     - Default
     - Description
   * - ``enable_mcp_command_line``
     - ``false``
     - Enable MCP-based code execution
   * - ``command_line_execution_mode``
     - ``"local"``
     - Execution mode: ``"local"`` or ``"docker"``
   * - ``command_line_docker_image``
     - ``"massgen/mcp-runtime:latest"``
     - Docker image for container execution
   * - ``command_line_docker_memory_limit``
     - None
     - Memory limit (e.g., ``"2g"``, ``"512m"``)
   * - ``command_line_docker_cpu_limit``
     - None
     - CPU cores limit (e.g., ``2.0``, ``4.0``)
   * - ``command_line_docker_network_mode``
     - ``"none"``
     - Network mode: ``"none"``, ``"bridge"``, or ``"host"``
   * - ``command_line_whitelist_patterns``
     - None
     - Regex patterns for allowed commands
   * - ``command_line_blacklist_patterns``
     - None
     - Regex patterns for blocked commands

.. _docker-mode-setup:

Docker Mode Setup
-----------------

Prerequisites
~~~~~~~~~~~~~

1. **Docker installed and running:**

   .. code-block:: bash

      docker --version  # Should show Docker Engine >= 28.0.0
      docker ps         # Should connect without errors

   Recommended: Docker Engine 28.0.0+ (`release notes <https://docs.docker.com/engine/release-notes/28/>`_)

2. **Python docker library:**

   .. code-block:: bash

      # Install via optional dependency group
      uv pip install -e ".[docker]"

      # Or install directly
      pip install docker>=7.0.0

Build Docker Image
~~~~~~~~~~~~~~~~~~

From the repository root:

.. code-block:: bash

   bash massgen/docker/build.sh

This builds ``massgen/mcp-runtime:latest`` (~400-500MB).

Enable Docker Mode
~~~~~~~~~~~~~~~~~~

Simple configuration:

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"

That's it! The container will be created automatically when orchestration starts.

How It Works
~~~~~~~~~~~~

**Container Lifecycle:**

1. **Orchestration Start** → Creates persistent container ``massgen-{agent_id}``
2. **Agent Turns** → Commands execute via ``docker exec``
3. **Orchestration End** → Container stopped and removed

**Key Features:**

* **Persistent Containers:** One container per agent for entire orchestration
* **State Persistence:** Packages and files persist across turns
* **Path Transparency:** Paths mounted at same locations as host
* **MCP Server on Host:** Server runs on host, creates Docker client to execute commands

**Volume Mounts:**

* **Workspace:** Read-write access to agent's workspace
* **Context Paths:** Read-only or read-write based on configuration
* **Temp Workspace:** Read-only access to other agents' outputs

Security Features
-----------------

Multi-Layer Security
~~~~~~~~~~~~~~~~~~~~

MassGen implements multiple security layers for code execution:

1. **AG2-Inspired Command Sanitization**

   Blocks dangerous patterns:

   * ``rm -rf /``
   * ``sudo`` commands
   * ``chmod 777``
   * And more...

2. **Command Filtering**

   Whitelist/blacklist regex patterns:

   .. code-block:: yaml

      command_line_whitelist_patterns: ["pip install.*", "python .*"]
      command_line_blacklist_patterns: ["rm -rf.*", "sudo.*"]

3. **Docker Container Isolation** (Docker mode only)

   * Filesystem isolation (only mounted volumes accessible)
   * Network isolation (default: no network)
   * Resource limits (memory, CPU)
   * Process isolation (non-root user)

4. **PathPermissionManager Hooks**

   Validates file operations against context path permissions

5. **Timeout Enforcement**

   Commands timeout after configured duration

Local vs Docker Comparison
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Aspect
     - Local Mode
     - Docker Mode
   * - **Setup**
     - None required
     - Docker + image build
   * - **Performance**
     - Fast (direct execution)
     - Slight overhead (~100-200ms)
   * - **Isolation**
     - Pattern-based (circumventable)
     - Container-based (strong)
   * - **Network**
     - Full host network
     - Configurable (none/bridge/host)
   * - **Resource Limits**
     - OS-level only
     - Docker-enforced
   * - **Security**
     - Medium
     - High
   * - **Best For**
     - Development, trusted code
     - Production, untrusted code

Usage Examples
--------------

Example 1: Python Development
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       type: "claude"
       model: "claude-sonnet-4"
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"

.. code-block:: bash

   massgen "Write and test a sorting algorithm"

**What happens:**

1. Agent writes ``sort.py``
2. Agent runs ``pip install pytest``
3. Agent writes tests in ``test_sort.py``
4. Agent runs ``pytest``
5. All isolated in Docker container!

Example 2: With Resource Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_memory_limit: "1g"
       command_line_docker_cpu_limit: 1.0
       command_line_docker_network_mode: "none"

Good for untrusted or resource-intensive tasks.

Example 3: With Network Access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_network_mode: "bridge"

.. code-block:: bash

   massgen "Fetch data from an API and analyze it"

Agent can make HTTP requests from inside container.

Example 4: Multi-Agent with Different Modes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "developer"
       backend:
         type: "openai"
         model: "gpt-5-mini"
         cwd: "workspace1"
         enable_mcp_command_line: true
         command_line_execution_mode: "local"  # Fast for development

     - id: "tester"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         cwd: "workspace2"
         enable_mcp_command_line: true
         command_line_execution_mode: "docker"  # Isolated for testing

Docker Image Details
--------------------

Base Image: massgen/mcp-runtime:latest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Contents:**

* Base: Python 3.11-slim
* System packages: git, curl, build-essential, Node.js 20.x
* Python packages: pytest, requests, numpy, pandas
* User: non-root (massgen, UID 1000)
* Working directory: /workspace

**Size:** ~400-500MB (compressed)

Custom Images
~~~~~~~~~~~~~

Extend the base image with additional packages:

.. code-block:: dockerfile

   FROM massgen/mcp-runtime:latest

   # Install additional system packages
   USER root
   RUN apt-get update && apt-get install -y --no-install-recommends \
       postgresql-client \
       && rm -rf /var/lib/apt/lists/*

   # Install additional Python packages
   USER massgen
   RUN pip install --no-cache-dir sqlalchemy psycopg2-binary

   WORKDIR /workspace

Build and use:

.. code-block:: bash

   docker build -t my-custom-runtime:latest -f Dockerfile.custom .

.. code-block:: yaml

   command_line_docker_image: "my-custom-runtime:latest"

Troubleshooting
---------------

Docker Not Installed
~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``RuntimeError: Docker Python library not available``

**Solution:**

.. code-block:: bash

   pip install docker>=7.0.0

Failed to Connect to Docker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``RuntimeError: Failed to connect to Docker: ...``

**Possible causes:**

1. Docker daemon not running:

   .. code-block:: bash

      docker ps  # Check if Docker is running

2. Permission issues (Linux):

   .. code-block:: bash

      sudo usermod -aG docker $USER
      # Log out and back in

3. Custom Docker socket:

   .. code-block:: bash

      export DOCKER_HOST=unix:///path/to/docker.sock

Image Not Found
~~~~~~~~~~~~~~~

**Symptom:** ``RuntimeError: Failed to pull Docker image ...``

**Solution:**

.. code-block:: bash

   bash massgen/docker/build.sh

Permission Errors in Container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``Permission denied`` when writing files

**Solution:** Ensure workspace has correct permissions:

.. code-block:: bash

   chmod -R 755 workspace

Performance Issues
~~~~~~~~~~~~~~~~~~

**Solutions:**

1. Increase resource limits:

   .. code-block:: yaml

      command_line_docker_memory_limit: "4g"
      command_line_docker_cpu_limit: 4.0

2. Use custom image with pre-installed packages

3. Check Docker Desktop resource settings

Debugging
---------

Inspect Running Container
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # List containers
   docker ps | grep massgen

   # View logs in real-time
   docker logs -f massgen-{agent_id}

   # Execute interactive shell
   docker exec -it massgen-{agent_id} /bin/bash

Check Resource Usage
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker stats massgen-{agent_id}

Manual Container Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Stop container
   docker stop massgen-{agent_id}

   # Remove container
   docker rm massgen-{agent_id}

   # Clean up all stopped containers
   docker container prune -f

Best Practices
--------------

1. **Use Docker mode for untrusted or production workloads**
2. **Set resource limits** to prevent abuse
3. **Use network_mode="none"** unless network is required
4. **Build custom images** for frequently used packages (faster)
5. **Monitor container logs** for debugging
6. **Test in local mode first** for faster iteration
7. **Use command filtering** to restrict dangerous operations

Configuration Examples
----------------------

See ``massgen/configs/debug/code_execution/`` for example configurations:

* ``basic_command_execution.yaml`` - Minimal code execution setup
* ``code_execution_use_case_simple.yaml`` - Simple use case example
* ``command_filtering_whitelist.yaml`` - Whitelist filtering example
* ``command_filtering_blacklist.yaml`` - Blacklist filtering example
* ``docker_simple.yaml`` - Minimal Docker setup
* ``docker_with_resource_limits.yaml`` - Memory/CPU limits with network
* ``docker_multi_agent.yaml`` - Multi-agent with Docker isolation
* ``docker_verification.yaml`` - Verify Docker isolation works

Next Steps
----------

* :doc:`file_operations` - File system operations and workspace management
* :doc:`mcp_integration` - Additional MCP tools beyond code execution
* :doc:`../reference/supported_models` - Backend capabilities including code execution
* :doc:`../quickstart/running-massgen` - More usage examples

References
----------

* `Docker Documentation <https://docs.docker.com/>`_
* `Docker Python SDK <https://docker-py.readthedocs.io/>`_
* Design Document: ``docs/dev_notes/CODE_EXECUTION_DESIGN.md``
* Docker README: ``massgen/docker/README.md``
* Build Script: ``massgen/docker/build.sh``
