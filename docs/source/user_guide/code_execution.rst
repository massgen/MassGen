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

Docker Credentials & Package Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Docker mode supports comprehensive credential management and package preinstallation through two nested configuration dictionaries: ``command_line_docker_credentials`` and ``command_line_docker_packages``.

Credential Management
"""""""""""""""""""""

**1. Mount Credential Files**

Mount credential files from your host into the container (all mounted read-only):

.. code-block:: yaml

   command_line_docker_credentials:
     mount:
       - "ssh_keys"     # ~/.ssh → /home/massgen/.ssh
       - "git_config"   # ~/.gitconfig → /home/massgen/.gitconfig
       - "gh_config"    # ~/.config/gh → /home/massgen/.config/gh
       - "npm_config"   # ~/.npmrc → /home/massgen/.npmrc
       - "pypi_config"  # ~/.pypirc → /home/massgen/.pypirc

**Available mount types:**

- ``ssh_keys`` - Clone private repos via SSH (``git clone git@github.com:org/repo.git``)
- ``git_config`` - Git user name/email for commits
- ``gh_config`` - GitHub CLI authentication (use if you've run ``gh auth login``)
- ``npm_config`` - Private npm package authentication
- ``pypi_config`` - Private PyPI package authentication

**2. Pass Environment Variables**

Three methods to pass environment variables:

.. code-block:: yaml

   # Option 1: From .env file (recommended for multiple secrets)
   command_line_docker_credentials:
     env_file: ".env"

   # Option 2: Specific variables from host
   command_line_docker_credentials:
     env_vars:
       - "GITHUB_TOKEN"
       - "NPM_TOKEN"
       - "ANTHROPIC_API_KEY"

   # Option 3: All environment variables (dangerous, use with caution)
   command_line_docker_credentials:
     pass_all_env: true

**3. Custom Volume Mounts**

Mount additional files or directories:

.. code-block:: yaml

   command_line_docker_credentials:
     additional_mounts:
       "/path/on/host/.aws":
         bind: "/home/massgen/.aws"
         mode: "ro"

GitHub CLI Authentication
"""""""""""""""""""""""""

GitHub CLI (``gh``) is pre-installed in MassGen Docker images. Two authentication methods:

**Method 1: Use Existing Login** (recommended if you've run ``gh auth login``):

.. code-block:: yaml

   command_line_docker_credentials:
     mount:
       - "gh_config"  # Mounts ~/.config/gh with your credentials

**Method 2: Pass Token**:

.. code-block:: yaml

   command_line_docker_credentials:
     env_vars:
       - "GITHUB_TOKEN"  # Set: export GITHUB_TOKEN=ghp_your_token

**For HTTPS git clones**, also add the token so git can authenticate:

.. code-block:: yaml

   command_line_docker_credentials:
     mount: ["gh_config", "ssh_keys", "git_config"]
     env_vars: ["GITHUB_TOKEN"]  # Enables both gh CLI and HTTPS git

Agents can then use ``gh`` commands:

.. code-block:: bash

   gh auth status
   gh api user
   gh repo clone user/repo
   gh issue list
   gh pr list

Package Preinstall
""""""""""""""""""

Specify base packages to pre-install in every container. These install when the container is created, before agents start working:

.. code-block:: yaml

   command_line_docker_packages:
     preinstall:
       python:
         - "requests>=2.31.0"
         - "numpy>=1.24.0"
         - "pytest>=7.0.0"
       npm:
         - "typescript"
         - "@types/node"
       system:
         - "vim"
         - "htop"

**Installation order**: System packages → Python packages → npm packages (all with sudo if enabled).

**When to use**:

- Consistent base environment across all runs
- Different package sets per configuration
- Quick iteration without rebuilding Docker images

**Requirements**:

- npm/system packages require: ``command_line_docker_enable_sudo: true``
- All packages require: ``command_line_docker_network_mode: "bridge"``

Custom Docker Images
""""""""""""""""""""

For stable dependencies or complex environments, create a custom Docker image:

.. code-block:: yaml

   command_line_docker_image: "your-username/custom-image:tag"

**Example custom Dockerfile** (see ``massgen/docker/Dockerfile.custom-example``):

.. code-block:: dockerfile

   FROM massgen/mcp-runtime:latest
   RUN pip install --no-cache-dir scikit-learn matplotlib seaborn
   RUN apt-get update && apt-get install -y vim htop && rm -rf /var/lib/apt/lists/*

Build and use:

.. code-block:: bash

   docker build -t my-custom-image:v1 -f Dockerfile.custom .

**Key requirements for custom images:**

1. Must have ``massgen`` user with UID 1000
2. Must create ``/workspace``, ``/context``, ``/temp_workspaces`` directories
3. Must set appropriate permissions
4. CMD should keep container running (``tail -f /dev/null``)

Complete Example Configurations
""""""""""""""""""""""""""""""""

**Minimal GitHub access:**

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_network_mode: "bridge"
       command_line_docker_credentials:
         env_vars: ["GITHUB_TOKEN"]

**Full development setup:**

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_enable_sudo: true
       command_line_docker_network_mode: "bridge"
       command_line_docker_memory_limit: "4g"

       command_line_docker_credentials:
         env_file: ".env"
         mount: ["ssh_keys", "git_config"]

       command_line_docker_packages:
         preinstall:
           python: ["pytest", "requests", "numpy"]
           npm: ["typescript"]

**Security best practices:**

- Use ``.env`` files for credentials (add to ``.gitignore``)
- Mount only needed credentials (opt-in by default)
- Use ``command_line_docker_network_mode: "none"`` unless network is required
- All credential files are mounted **read-only**
- Use command filtering (``blocked_commands``) for additional safety

**Example configs:** See ``massgen/configs/tools/code-execution/`` for 8+ ready-to-run examples.

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
   * - ``command_line_docker_enable_sudo``
     - ``false``
     - Enable sudo in containers (⚠️ less secure, see docs)
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

Sudo Variant (Runtime Package Installation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The sudo variant allows agents to install system packages at runtime inside their Docker container.

**IMPORTANT: Build the image before first use:**

.. code-block:: bash

   bash massgen/docker/build.sh --sudo

This builds ``massgen/mcp-runtime-sudo:latest`` with sudo access locally. (This image is not available on Docker Hub - you must build it yourself.)

**Enable in config:**

.. code-block:: yaml

   agent:
     backend:
       cwd: "workspace"
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_enable_sudo: true  # Automatically uses sudo image

**What agents can do with sudo:**

.. code-block:: bash

   # Install system packages at runtime
   sudo apt-get update && sudo apt-get install -y ffmpeg

   # Install additional Python packages
   sudo pip install tensorflow

**Is this safe?**

**YES**, because Docker container isolation is the primary security boundary:

**Container is fully isolated from your host:**

- Sudo inside container ≠ sudo on your computer
- Agent can only access mounted volumes (workspace, context paths)
- Cannot access your host filesystem outside mounts
- Cannot affect host processes or system configuration
- Docker namespaces/cgroups provide strong isolation

**What sudo can and cannot do:**

- ✅ Can: Install packages inside the container (apt, pip, npm)
- ✅ Can: Modify container system configuration
- ✅ Can: Read/write mounted workspace (same as without sudo)
- ❌ Cannot: Access your host filesystem outside mounts
- ❌ Cannot: Affect your host system
- ❌ Cannot: Break out of the container (unless Docker vulnerability exists)

**Theoretical risks (extremely rare):**

- Container escape vulnerabilities (CVEs in Docker/kernel) are very rare and quickly patched
- Sudo increases attack surface slightly if escape exists
- Still requires exploit code, not just malicious intent

**When to use sudo variant vs custom images:**

.. list-table::
   :header-rows: 1
   :widths: 20 30 25 25

   * - Approach
     - Use When
     - Performance
     - Security
   * - **Sudo variant**
     - Need flexibility, unknown packages, prototyping
     - Slower (runtime install)
     - Good (container isolated)
   * - **Custom image**
     - Know packages, production use
     - Fast (pre-installed)
     - Best (minimal attack surface)

**Custom image example (recommended for production):**

.. code-block:: dockerfile

   FROM massgen/mcp-runtime:latest
   USER root
   RUN apt-get update && apt-get install -y ffmpeg postgresql-client
   USER massgen

Build: ``docker build -t my-runtime:latest .``

Use: ``command_line_docker_image: "my-runtime:latest"``

**Bottom line:** The sudo variant is safe for most use cases because Docker container isolation is strong. Custom images are preferred for production because they're faster and have a smaller attack surface, but sudo is fine for development and prototyping.

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

Background Shell Execution
---------------------------

**NEW:** MassGen supports running commands in the background without blocking, enabling parallel execution and long-running processes.

What is Background Execution?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Background execution allows agents to:

* Start long-running processes (training, servers, simulations)
* Run multiple experiments in parallel
* Monitor processes without blocking
* Continue working while tasks execute

**Available Tools:**

When ``enable_mcp_command_line: true`` is set, agents automatically get these tools:

* ``start_background_shell(command, work_dir)`` - Start command in background, returns shell_id
* ``get_background_shell_output(shell_id)`` - Retrieve stdout/stderr from background process
* ``get_background_shell_status(shell_id)`` - Check if running/stopped/failed
* ``kill_background_shell(shell_id)`` - Terminate a background process
* ``list_background_shells()`` - List all active background processes

Example: Parallel Experiments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       type: "openai"
       model: "gpt-5-mini"
       cwd: "workspace"
       enable_mcp_command_line: true
     system_message: |
       You can run multiple experiments in parallel using background shell tools.
       Use start_background_shell() to launch tasks, then monitor with
       list_background_shells() and collect results when complete.

**Agent workflow:**

.. code-block:: python

   # Start 3 experiments in parallel
   exp1 = start_background_shell("python experiment_a.py")
   exp2 = start_background_shell("python experiment_b.py")
   exp3 = start_background_shell("python experiment_c.py")

   # Monitor until all complete
   while True:
       shells = list_background_shells()
       running = [s for s in shells["shells"] if s["status"] == "running"]
       if len(running) == 0:
           break

   # Collect results
   result1 = get_background_shell_output(exp1["shell_id"])
   result2 = get_background_shell_output(exp2["shell_id"])
   result3 = get_background_shell_output(exp3["shell_id"])

Example: Server Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Start web server in background
   server = start_background_shell("uvicorn app:main --port 8000")

   # Server runs while agent does other work...

   # Run integration tests
   test_result = execute_command("pytest tests/integration/")

   # Cleanup: stop server
   kill_background_shell(server["shell_id"])

Example: Long-Running Tasks with Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Start training job
   training = start_background_shell("python train.py --epochs 100")

   # Monitor progress periodically
   while True:
       status = get_background_shell_status(training["shell_id"])

       if status["status"] != "running":
           break

       # Check progress from output
       output = get_background_shell_output(training["shell_id"])
       # Look for "Epoch X/100" in output...

   # Training complete
   final_output = get_background_shell_output(training["shell_id"])

Key Features
~~~~~~~~~~~~

* **Non-blocking:** Continue work while processes run
* **Parallel execution:** Run multiple tasks simultaneously (default limit: 10 concurrent)
* **Memory-safe:** Ring buffer captures last 10,000 lines (prevents OOM on infinite output)
* **Auto-cleanup:** All background processes killed on MassGen exit
* **Thread-safe:** Safe for concurrent access from multiple agents
* **Same security:** Background shells use same sanitization as foreground ``execute_command``

Demo Configuration
~~~~~~~~~~~~~~~~~~

See ``massgen/configs/tools/code-execution/background_shell_demo.yaml`` for a complete example showing parallel vs sequential execution strategies.

Best Practices
--------------

1. **Use Docker mode for untrusted or production workloads**
2. **Set resource limits** to prevent abuse
3. **Use network_mode="none"** unless network is required
4. **Build custom images** for frequently used packages (faster)
5. **Monitor container logs** for debugging
6. **Test in local mode first** for faster iteration
7. **Use command filtering** to restrict dangerous operations
8. **Use background shells for parallel tasks** - Run multiple experiments concurrently
9. **Monitor background processes** - Use ``get_background_shell_status()`` to check progress
10. **Cleanup background shells** - Kill when done or let auto-cleanup handle it

Configuration Examples
----------------------

See ``massgen/configs/tools/code-execution/`` for example configurations:

* ``basic_command_execution.yaml`` - Minimal code execution setup
* ``code_execution_use_case_simple.yaml`` - Simple use case example
* ``command_filtering_whitelist.yaml`` - Whitelist filtering example
* ``command_filtering_blacklist.yaml`` - Blacklist filtering example
* ``docker_simple.yaml`` - Minimal Docker setup
* ``docker_with_resource_limits.yaml`` - Memory/CPU limits with network
* ``docker_multi_agent.yaml`` - Multi-agent with Docker isolation
* ``docker_verification.yaml`` - Verify Docker isolation works
* ``background_shell_demo.yaml`` - **NEW:** Parallel execution with background shells

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
* **NEW:** Background Execution Design: ``docs/dev_notes/background_shell_execution_design.md``
* Docker README: ``massgen/docker/README.md``
* Build Script: ``massgen/docker/build.sh``
