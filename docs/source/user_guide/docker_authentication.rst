Docker Authentication & Environment Setup
===========================================

This guide explains how to configure authentication and environment setup for MassGen's Docker code execution mode.

Overview
--------

When using Docker for code execution, you may need to:

- Clone private repositories using SSH keys
- Authenticate with GitHub CLI (``gh``)
- Install private packages from npm, PyPI, or other registries
- Pass API tokens and credentials to your containerized environment
- Automatically install dependencies from cloned repositories

MassGen provides comprehensive support for all these use cases through opt-in configuration parameters.

.. warning::
   All credential mounting features are **opt-in** for security. You must explicitly enable each feature you need in your configuration.

Environment Variables
---------------------

Three Ways to Pass Environment Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen supports three methods for passing environment variables to Docker containers:

1. **From .env File (Recommended)**

   Create a ``.env`` file with your credentials:

   .. code-block:: bash

      # .env
      GITHUB_TOKEN=ghp_your_token_here
      GH_TOKEN=ghp_your_token_here
      NPM_TOKEN=npm_your_token_here
      ANTHROPIC_API_KEY=sk-ant-your_key_here

   Configure MassGen to load this file:

   .. code-block:: yaml

      agent:
        backend:
          enable_mcp_command_line: true
          command_line_execution_mode: "docker"
          command_line_docker_env_file_path: ".env"

2. **Pass Specific Variables**

   Pass only specific environment variables from your host:

   .. code-block:: yaml

      agent:
        backend:
          enable_mcp_command_line: true
          command_line_execution_mode: "docker"
          command_line_docker_pass_env_vars:
            - "GITHUB_TOKEN"
            - "NPM_TOKEN"
            - "ANTHROPIC_API_KEY"

3. **Pass All Environment Variables (Dangerous)**

   .. warning::
      This option passes **all** your host environment variables to the container. Only use this if you fully understand the security implications.

   .. code-block:: yaml

      agent:
        backend:
          enable_mcp_command_line: true
          command_line_execution_mode: "docker"
          command_line_docker_pass_all_env: true

Credential File Mounting
-------------------------

SSH Keys for Git
~~~~~~~~~~~~~~~~

Mount your SSH keys to clone private repositories via SSH:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_mount_ssh_keys: true

This mounts ``~/.ssh`` as **read-only** at ``/home/massgen/.ssh`` inside the container.

**Example Usage:**

.. code-block:: bash

   # Agent can now clone private repos via SSH
   git clone git@github.com:yourorg/private-repo.git

Git Configuration
~~~~~~~~~~~~~~~~~

Mount your ``.gitconfig`` for user name, email, and other git settings:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_mount_git_config: true

This mounts ``~/.gitconfig`` as **read-only** at ``/home/massgen/.gitconfig``.

npm Configuration
~~~~~~~~~~~~~~~~~

Mount your ``.npmrc`` for private npm packages:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_mount_npm_config: true

This mounts ``~/.npmrc`` as **read-only** at ``/home/massgen/.npmrc``.

**Example .npmrc:**

.. code-block:: ini

   //registry.npmjs.org/:_authToken=${NPM_TOKEN}
   @yourorg:registry=https://npm.pkg.github.com/

PyPI Configuration
~~~~~~~~~~~~~~~~~~

Mount your ``.pypirc`` for private PyPI packages:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_mount_pypi_config: true

This mounts ``~/.pypirc`` as **read-only** at ``/home/massgen/.pypirc``.

**Example .pypirc:**

.. code-block:: ini

   [distutils]
   index-servers =
       pypi
       private

   [pypi]
   username = __token__
   password = pypi-your_token_here

   [private]
   repository = https://your-private-pypi.com
   username = youruser
   password = yourpass

Custom Volume Mounts
~~~~~~~~~~~~~~~~~~~~

Mount additional files or directories:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_additional_mounts:
         "/path/on/host/credentials.json":
           bind: "/home/massgen/.config/gcloud/credentials.json"
           mode: "ro"
         "/path/on/host/.aws":
           bind: "/home/massgen/.aws"
           mode: "ro"

GitHub CLI Authentication
-------------------------

Basic Setup
~~~~~~~~~~~

GitHub CLI (``gh``) is pre-installed in MassGen Docker images (v0.1.8+).

To authenticate, pass your GitHub token via environment variables:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_pass_env_vars:
         - "GITHUB_TOKEN"  # or GH_TOKEN

Then in your orchestration, the agent can use ``gh`` commands:

.. code-block:: bash

   # Create a PR
   gh pr create --title "Feature" --body "Description"

   # Clone a private repo
   gh repo clone yourorg/private-repo

   # View issues
   gh issue list

Complete GitHub Workflow Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a complete config for working with GitHub repositories:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_network_mode: "bridge"  # Enable network access
       command_line_docker_mount_ssh_keys: true     # For git SSH operations
       command_line_docker_mount_git_config: true   # For git user config
       command_line_docker_pass_env_vars:
         - "GITHUB_TOKEN"                            # For gh CLI
       command_line_docker_auto_install_deps: true  # Auto-install dependencies

**What this enables:**

- Clone repos via SSH: ``git clone git@github.com:user/repo.git``
- Clone repos via HTTPS: ``gh repo clone user/repo``
- Create pull requests: ``gh pr create``
- Push commits with your git identity
- Automatically install dependencies from ``requirements.txt``, ``package.json``, etc.

Automatic Dependency Installation
----------------------------------

Auto-Detect and Install Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen can automatically detect and install dependencies when agents work with repositories:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_auto_install_deps: true

**Supported dependency files:**

- Python: ``requirements.txt``, ``pyproject.toml``, ``setup.py``, ``Pipfile``
- Node.js: ``package.json``, ``yarn.lock``
- System: ``apt-packages.txt`` (requires sudo mode)

Auto-Install Only on Clone
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you only want dependencies installed for newly cloned repos:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_auto_install_on_clone: true

.. note::
   This requires integration with the git clone detection mechanism. Currently, auto-install runs when containers are created. Full clone detection coming in a future release.

Installation Process
~~~~~~~~~~~~~~~~~~~~

When dependencies are detected, MassGen:

1. Scans the workspace for dependency files
2. Generates appropriate installation commands
3. Executes them in order (system → Python → Node.js)
4. Logs success/failure for each installation
5. Continues container setup even if some installations fail

**Example log output:**

.. code-block:: text

   📋 [Docker] Found 2 dependency file(s) in myproject
       python: requirements.txt
       nodejs: package.json
   📦 [Docker] Auto-installing 2 dependency file(s) for agent agent_a
       Running: cd /workspace/myproject && pip install -r requirements.txt
   ✅ [Docker] Successfully installed dependencies from command
       Running: cd /workspace/myproject && npm install
   ✅ [Docker] Successfully installed dependencies from command
   ✅ [Docker] All dependencies installed successfully

Security Considerations
-----------------------

Read-Only Mounts
~~~~~~~~~~~~~~~~

All credential files are mounted as **read-only** by default to prevent accidental modification or deletion of your credentials from within the container.

Container Isolation
~~~~~~~~~~~~~~~~~~~

Docker containers provide strong isolation from your host system:

- Containers cannot access files outside their mounted volumes
- Network access is configurable (default: ``none`` - no network)
- Resource limits prevent runaway processes
- Sudo access (if enabled) only affects the container, not your host

Credential Leakage Prevention
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Best practices:**

1. **Use .env files** instead of hardcoding credentials in configs
2. **Add .env to .gitignore** to prevent committing credentials
3. **Use specific variable passing** instead of ``pass_all_env``
4. **Limit mounted credentials** to only what's needed
5. **Use network isolation** (``network_mode: none``) unless network access is required

Troubleshooting
---------------

SSH Key Permissions
~~~~~~~~~~~~~~~~~~~

If git SSH operations fail, ensure your SSH key has correct permissions:

.. code-block:: bash

   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/id_rsa
   chmod 644 ~/.ssh/id_rsa.pub ~/.ssh/known_hosts

GitHub Token Not Working
~~~~~~~~~~~~~~~~~~~~~~~~~

Ensure your token has the required scopes:

- ``repo`` - Full access to repositories
- ``workflow`` - Update GitHub Action workflows (if needed)
- ``read:org`` - Read org data (if accessing org repos)

Check token is being passed correctly:

.. code-block:: bash

   # Inside container (for debugging)
   echo $GITHUB_TOKEN

Environment Variables Not Loaded
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Common issues:

1. **Wrong path**: Ensure ``command_line_docker_env_file_path`` points to correct file
2. **File format**: Ensure ``.env`` uses ``KEY=VALUE`` format (no ``export``)
3. **Quotes**: Remove quotes around values in ``.env`` or use matching quotes (``KEY="value"`` or ``KEY='value'``)

Dependencies Not Installing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check the logs for installation failures:

- **Python**: Ensure ``pip`` has access to required packages
- **Node.js**: Ensure ``npm`` registry is accessible
- **System**: Ensure sudo mode is enabled for ``apt-packages.txt``

Enable debug logging:

.. code-block:: yaml

   orchestrator:
     logging:
       level: DEBUG

Bringing Your Own Docker Image
-------------------------------

You can use custom Docker images instead of the default MassGen images. This is useful when you need specific tools, libraries, or configurations.

Basic Custom Image
~~~~~~~~~~~~~~~~~~

Simply specify your image in the configuration:

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_image: "your-username/your-custom-image:tag"

Creating a Custom Image
~~~~~~~~~~~~~~~~~~~~~~~~

**Option 1: Extend MassGen Base Image**

Create a ``Dockerfile`` that extends the MassGen image:

.. code-block:: dockerfile

   # Start from MassGen base
   FROM massgen/mcp-runtime:latest

   # Add your custom packages
   RUN pip install --no-cache-dir \\
       tensorflow>=2.13.0 \\
       scikit-learn>=1.3.0 \\
       jupyter>=1.0.0

   # Install additional system packages
   RUN apt-get update && apt-get install -y --no-install-recommends \\
       vim \\
       htop \\
       && rm -rf /var/lib/apt/lists/*

   # Copy custom configuration files
   COPY my-config.json /home/massgen/.config/

Build and use:

.. code-block:: bash

   # Build your custom image
   docker build -t my-massgen-image:v1 .

   # Use in configuration
   command_line_docker_image: "my-massgen-image:v1"

**Option 2: Build from Scratch**

Create a completely custom image (must match MassGen's expected structure):

.. code-block:: dockerfile

   FROM python:3.11-slim

   # Install base requirements
   RUN apt-get update && apt-get install -y --no-install-recommends \\
       git curl ca-certificates build-essential \\
       && rm -rf /var/lib/apt/lists/*

   # Install Node.js (if needed)
   RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \\
       && apt-get install -y --no-install-recommends nodejs \\
       && rm -rf /var/lib/apt/lists/*

   # Create massgen user (UID 1000)
   RUN useradd -m -u 1000 -s /bin/bash massgen

   # Install your packages
   RUN pip install --no-cache-dir \\
       requests numpy pandas pytest

   # Create required directories
   RUN mkdir -p /workspace /context /temp_workspaces
   RUN chown -R massgen:massgen /workspace /context /temp_workspaces

   USER massgen
   WORKDIR /workspace

   CMD ["tail", "-f", "/dev/null"]

**Key Requirements for Custom Images:**

1. **User**: Must have a ``massgen`` user with UID 1000
2. **Directories**: Must create ``/workspace``, ``/context``, ``/temp_workspaces``
3. **Permissions**: ``massgen`` user must own the directories
4. **CMD**: Should be ``tail -f /dev/null`` or equivalent to keep container running

Pre-install vs Custom Images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**When to use preinstall packages**:

.. code-block:: yaml

   command_line_docker_preinstall_python:
     - "requests>=2.31.0"

- Quick testing and iteration
- Different package sets per configuration
- Don't want to rebuild Docker images

**When to use custom images**:

.. code-block:: dockerfile

   RUN pip install requests>=2.31.0

- Same packages needed across all runs
- Complex system dependencies
- Want faster container startup (no install time)
- Sharing images across team

**Best practice**: Use custom images for stable base dependencies, use preinstall for frequently changing packages.

Complete Configuration Examples
--------------------------------

Example 1: Minimal GitHub CLI Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_network_mode: "bridge"
       command_line_docker_pass_env_vars:
         - "GITHUB_TOKEN"

Example 2: Full GitHub Development Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_enable_sudo: true
       command_line_docker_network_mode: "bridge"
       command_line_docker_memory_limit: "4g"
       command_line_docker_cpu_limit: 2.0
       command_line_docker_env_file_path: ".env"
       command_line_docker_mount_ssh_keys: true
       command_line_docker_mount_git_config: true
       command_line_docker_auto_install_deps: true

Example 3: Private Package Development
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agent:
     backend:
       enable_mcp_command_line: true
       command_line_execution_mode: "docker"
       command_line_docker_network_mode: "bridge"
       command_line_docker_mount_npm_config: true
       command_line_docker_mount_pypi_config: true
       command_line_docker_pass_env_vars:
         - "NPM_TOKEN"
       command_line_docker_auto_install_deps: true

Further Reading
---------------

- :doc:`../reference/yaml_schema` - Complete configuration reference
- :doc:`../development/CODE_EXECUTION_DESIGN` - Technical architecture
- :doc:`../quickstart/installation` - Getting started with MassGen
