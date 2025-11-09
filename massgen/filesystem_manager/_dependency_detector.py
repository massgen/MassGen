# -*- coding: utf-8 -*-
"""
Dependency Detector for MassGen Docker Environments

Detects and handles automatic dependency installation for cloned repositories.
Supports Python, Node.js, and system-level package managers.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DependencyDetector:
    """
    Detects dependency files in a workspace and generates installation commands.

    Supports:
    - Python: requirements.txt, pyproject.toml, setup.py, Pipfile
    - Node.js: package.json, package-lock.json, yarn.lock
    - System: apt-packages.txt (for Debian/Ubuntu)
    """

    # Python dependency files (in priority order)
    PYTHON_DEP_FILES = [
        ("requirements.txt", "pip install -r requirements.txt"),
        ("pyproject.toml", "pip install -e ."),
        ("setup.py", "pip install -e ."),
        ("Pipfile", "pip install pipenv && pipenv install"),
    ]

    # Node.js dependency files (in priority order)
    NODEJS_DEP_FILES = [
        ("package.json", "npm install"),
        ("yarn.lock", "yarn install"),
    ]

    # System package files
    SYSTEM_DEP_FILES = [
        ("apt-packages.txt", "xargs sudo apt-get install -y <"),
    ]

    def __init__(self, workspace_path: Path):
        """
        Initialize dependency detector.

        Args:
            workspace_path: Path to the workspace to scan
        """
        self.workspace_path = Path(workspace_path).resolve()

    def detect_python_dependencies(self) -> List[Tuple[str, str, str]]:
        """
        Detect Python dependency files.

        Returns:
            List of tuples (file_name, file_path, install_command)
        """
        found_deps = []

        for dep_file, install_cmd in self.PYTHON_DEP_FILES:
            file_path = self.workspace_path / dep_file
            if file_path.exists():
                found_deps.append((dep_file, str(file_path), install_cmd))
                logger.debug(f"🐍 [DependencyDetector] Found Python dependency file: {dep_file}")

        return found_deps

    def detect_nodejs_dependencies(self) -> List[Tuple[str, str, str]]:
        """
        Detect Node.js dependency files.

        Returns:
            List of tuples (file_name, file_path, install_command)
        """
        found_deps = []

        # Special handling: only use yarn if yarn.lock exists, otherwise use npm
        has_yarn_lock = (self.workspace_path / "yarn.lock").exists()
        has_package_json = (self.workspace_path / "package.json").exists()

        if has_package_json:
            if has_yarn_lock:
                found_deps.append(("yarn.lock", str(self.workspace_path / "yarn.lock"), "yarn install"))
                logger.debug("📦 [DependencyDetector] Found Node.js dependency file: yarn.lock")
            else:
                found_deps.append(("package.json", str(self.workspace_path / "package.json"), "npm install"))
                logger.debug("📦 [DependencyDetector] Found Node.js dependency file: package.json")

        return found_deps

    def detect_system_dependencies(self, enable_sudo: bool = False) -> List[Tuple[str, str, str]]:
        """
        Detect system dependency files.

        Args:
            enable_sudo: Whether sudo is available in the container

        Returns:
            List of tuples (file_name, file_path, install_command)
        """
        if not enable_sudo:
            logger.debug("⚙️ [DependencyDetector] Skipping system dependencies (sudo not enabled)")
            return []

        found_deps = []

        for dep_file, install_cmd in self.SYSTEM_DEP_FILES:
            file_path = self.workspace_path / dep_file
            if file_path.exists():
                found_deps.append((dep_file, str(file_path), install_cmd))
                logger.debug(f"⚙️ [DependencyDetector] Found system dependency file: {dep_file}")

        return found_deps

    def detect_all_dependencies(
        self,
        enable_sudo: bool = False,
        python_only: bool = False,
    ) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        Detect all dependency files in the workspace.

        Args:
            enable_sudo: Whether sudo is available in the container
            python_only: Only detect Python dependencies

        Returns:
            Dictionary with keys: 'python', 'nodejs', 'system'
            Each value is a list of tuples (file_name, file_path, install_command)
        """
        results = {
            "python": [],
            "nodejs": [],
            "system": [],
        }

        # Always detect Python dependencies
        results["python"] = self.detect_python_dependencies()

        if not python_only:
            # Detect Node.js dependencies
            results["nodejs"] = self.detect_nodejs_dependencies()

            # Detect system dependencies if sudo is available
            results["system"] = self.detect_system_dependencies(enable_sudo=enable_sudo)

        # Log summary
        total_found = sum(len(deps) for deps in results.values())
        if total_found > 0:
            logger.info(f"📋 [DependencyDetector] Found {total_found} dependency file(s) in {self.workspace_path.name}")
            for dep_type, deps in results.items():
                if deps:
                    for file_name, _, _ in deps:
                        logger.info(f"    {dep_type}: {file_name}")
        else:
            logger.debug(f"📋 [DependencyDetector] No dependency files found in {self.workspace_path.name}")

        return results

    def generate_install_commands(
        self,
        dependencies: Dict[str, List[Tuple[str, str, str]]],
        working_dir: Optional[str] = None,
    ) -> List[str]:
        """
        Generate installation commands from detected dependencies.

        Args:
            dependencies: Output from detect_all_dependencies()
            working_dir: Optional working directory for commands

        Returns:
            List of shell commands to install dependencies
        """
        commands = []

        # Add cd command if working directory specified
        cd_prefix = f"cd {working_dir} && " if working_dir else ""

        # System dependencies first (need to be installed before Python/Node packages might need them)
        for _, _, install_cmd in dependencies.get("system", []):
            commands.append(cd_prefix + install_cmd)

        # Python dependencies
        for _, _, install_cmd in dependencies.get("python", []):
            commands.append(cd_prefix + install_cmd)

        # Node.js dependencies
        for _, _, install_cmd in dependencies.get("nodejs", []):
            commands.append(cd_prefix + install_cmd)

        return commands

    def should_auto_install(
        self,
        auto_install_deps: bool = False,
        auto_install_on_clone: bool = False,
        is_newly_cloned: bool = False,
    ) -> bool:
        """
        Determine if dependencies should be automatically installed.

        Args:
            auto_install_deps: Global auto-install setting
            auto_install_on_clone: Auto-install only for newly cloned repos
            is_newly_cloned: Whether this workspace was just cloned

        Returns:
            True if dependencies should be auto-installed
        """
        if auto_install_deps:
            return True

        if auto_install_on_clone and is_newly_cloned:
            return True

        return False
