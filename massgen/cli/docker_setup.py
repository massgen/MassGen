#!/usr/bin/env python3
"""Docker availability checks and environment setup.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass


# --- cross-module references within the cli package ---
from ._constants import BRIGHT_CYAN, BRIGHT_GREEN, BRIGHT_RED, BRIGHT_YELLOW, RESET


def check_docker_available() -> bool:
    """Check if Docker is installed, running, and MassGen images are available.

    Returns:
        True if Docker is ready with MassGen images, False otherwise
    """
    from massgen.utils.docker_diagnostics import diagnose_docker

    diagnostics = diagnose_docker()
    return diagnostics.is_available


def get_docker_diagnostics():
    """Get detailed Docker diagnostics for error reporting.

    Returns:
        DockerDiagnostics object with full diagnostic information
    """
    from massgen.utils.docker_diagnostics import diagnose_docker

    return diagnose_docker()


def setup_docker() -> None:
    """Pull MassGen Docker executor images from GitHub Container Registry.

    Shows full diagnostics checklist and only offers to pull missing images.
    """
    import subprocess

    import questionary
    from questionary import Style

    from massgen.utils.docker_diagnostics import diagnose_docker

    print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
    print(f"{BRIGHT_CYAN}  🐳  MassGen Docker Setup{RESET}")
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}\n")

    # Run comprehensive diagnostics INCLUDING image check
    print(f"{BRIGHT_CYAN}Checking Docker status...{RESET}\n")
    diagnostics = diagnose_docker(check_images=True)

    # Display full diagnostics checklist
    version_info = f" ({diagnostics.docker_version})" if diagnostics.docker_version else ""
    binary_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.binary_installed else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {binary_status} Docker binary installed{version_info}")

    pip_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.pip_library_installed else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {pip_status} Docker Python library")

    daemon_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.daemon_running else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {daemon_status} Docker daemon running")

    perm_status = f"{BRIGHT_GREEN}✓{RESET}" if diagnostics.has_permissions else f"{BRIGHT_RED}✗{RESET}"
    print(f"  {perm_status} Permissions OK")

    # If not available, show error and resolution steps
    if not diagnostics.is_available:
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return

    # Define available images with metadata
    AVAILABLE_IMAGES = [
        {
            "name": "ghcr.io/massgen/mcp-runtime-sudo:latest",
            "description": "Sudo image (recommended - allows package installation)",
            "default": True,  # Pre-selected by default
        },
        {
            "name": "ghcr.io/massgen/mcp-runtime:latest",
            "description": "Standard image (no sudo access)",
            "default": False,
        },
    ]

    # Show installed images status
    print(f"\n{BRIGHT_CYAN}Installed Images:{RESET}")
    installed_images = []
    missing_images = []
    for img in AVAILABLE_IMAGES:
        img_name = img["name"]
        if diagnostics.images_available.get(img_name, False):
            print(f"  {BRIGHT_GREEN}✓{RESET} {img_name}")
            installed_images.append(img_name)
        else:
            print(f"  {BRIGHT_RED}✗{RESET} {img_name}")
            missing_images.append(img)

    # If all images are installed, we're done
    if not missing_images:
        print(f"\n{BRIGHT_GREEN}✅ All Docker images are already installed!{RESET}\n")
        return

    # Create questionary style matching the rest of the CLI
    custom_style = Style(
        [
            ("qmark", "fg:#00CED1 bold"),
            ("question", "fg:#00CED1 bold"),
            ("answer", "fg:#32CD32 bold"),
            ("pointer", "fg:#00CED1 bold"),
            ("highlighted", "fg:#00CED1 bold"),
            ("selected", "fg:#32CD32"),
            ("separator", "fg:#6C6C6C"),
            ("instruction", "fg:#A9A9A9"),
        ],
    )

    # Only offer to pull MISSING images
    print(f"\n{BRIGHT_CYAN}Pull missing images?{RESET}")
    print(f"{BRIGHT_YELLOW}(Use Space to select/deselect, Enter to confirm){RESET}\n")

    try:
        # Only show missing images in the selection
        choices = [
            questionary.Choice(
                title=f"{img['description']}",
                value=img["name"],
                checked=img["default"],
            )
            for img in missing_images
        ]

        selected_images = questionary.checkbox(
            "",
            choices=choices,
            style=custom_style,
        ).ask()

        if selected_images is None:  # User cancelled (Ctrl+C)
            print(f"\n{BRIGHT_YELLOW}Setup cancelled{RESET}\n")
            return

        if not selected_images:
            print(
                f"\n{BRIGHT_YELLOW}No images selected. Skipping Docker setup.{RESET}\n",
            )
            return

    except (KeyboardInterrupt, EOFError):
        print(f"\n{BRIGHT_YELLOW}Setup cancelled{RESET}\n")
        return

    # Pull images with real-time progress display
    print(f"\n{BRIGHT_CYAN}Pulling {len(selected_images)} image(s)...{RESET}\n")

    success_count = 0
    failed_images = []

    for i, image in enumerate(selected_images, 1):
        print(f"{BRIGHT_CYAN}[{i}/{len(selected_images)}] Pulling {image}...{RESET}\n")

        try:
            # Don't capture output so Docker's progress bars are visible
            result = subprocess.run(
                ["docker", "pull", image],
                timeout=600,  # 10 minutes max per image
            )

            print()  # Add spacing after progress bars

            if result.returncode == 0:
                print(
                    f"{BRIGHT_GREEN}✓ [{i}/{len(selected_images)}] Completed: {image}{RESET}\n",
                )
                success_count += 1
            else:
                print(
                    f"{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Failed: {image}{RESET}\n",
                )
                failed_images.append(image)

        except subprocess.TimeoutExpired:
            print(
                f"\n{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Timed out: {image}{RESET}\n",
            )
            failed_images.append(image)
        except Exception as e:
            print(
                f"\n{BRIGHT_RED}✗ [{i}/{len(selected_images)}] Error: {image} - {e}{RESET}\n",
            )
            failed_images.append(image)

    # Summary
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
    if success_count == len(selected_images):
        print(f"{BRIGHT_GREEN}  ✅ Docker setup complete!{RESET}")
        print(f"{BRIGHT_GREEN}  Successfully pulled {success_count} image(s){RESET}")
        print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
        print(
            f"\n{BRIGHT_CYAN}You can now use Docker execution mode in your configs.{RESET}",
        )
        print(
            f"{BRIGHT_CYAN}Run 'massgen --quickstart' to create a config with Docker enabled.{RESET}\n",
        )
    elif success_count > 0:
        print(
            f"{BRIGHT_YELLOW}  ⚠️  Partial success: {success_count}/{len(selected_images)} images pulled{RESET}",
        )
        print(f"{BRIGHT_YELLOW}{'=' * 60}{RESET}")
        if failed_images:
            print(f"\n{BRIGHT_YELLOW}Failed images:{RESET}")
            for img in failed_images:
                print(f"  - {img}")
        print()
    else:
        print(f"{BRIGHT_RED}  ❌ Docker setup failed{RESET}")
        print(f"{BRIGHT_RED}{'=' * 60}{RESET}")
        print(f"\n{BRIGHT_YELLOW}The images may not be published yet.{RESET}")
        print(f"{BRIGHT_YELLOW}You can build locally instead:{RESET}")
        print("  bash massgen/docker/build.sh --sudo\n")


def setup_computer_use_docker() -> bool:
    """Setup Docker container for Computer Use Agent (CUA) automation.

    Creates a Docker container with:
    - Ubuntu 22.04 with Xfce desktop
    - X11 virtual display (Xvfb) on :99
    - xdotool for GUI automation
    - Firefox and Chromium browsers
    - scrot for screenshots

    This is required for computer_use_docker_example.yaml configs.

    Returns:
        True if setup succeeded, False otherwise
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from massgen.utils.docker_diagnostics import diagnose_docker

    print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
    print(f"{BRIGHT_CYAN}  🖥️  Computer Use Docker Container Setup{RESET}")
    print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}\n")

    # Run comprehensive diagnostics (skip image check since we're setting up)
    print(f"{BRIGHT_CYAN}Checking Docker...{RESET}", end=" ", flush=True)
    diagnostics = diagnose_docker(check_images=False)

    # Check if Docker is ready (binary, pip library, permissions, daemon)
    if not diagnostics.binary_installed or not diagnostics.pip_library_installed:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    if not diagnostics.has_permissions:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    if not diagnostics.daemon_running:
        print(f"{BRIGHT_RED}✗{RESET}")
        print(f"\n{BRIGHT_RED}Error: {diagnostics.error_message}{RESET}")
        print(f"\n{BRIGHT_YELLOW}To fix this:{RESET}")
        for i, step in enumerate(diagnostics.resolution_steps, 1):
            if step.startswith("  "):
                print(f"{BRIGHT_YELLOW}{step}{RESET}")
            else:
                print(f"{BRIGHT_YELLOW}  {i}. {step}{RESET}")
        print()
        return False

    print(f"{BRIGHT_GREEN}✓{RESET}")
    if diagnostics.docker_version:
        print(f"{BRIGHT_CYAN}  Docker version: {diagnostics.docker_version}{RESET}")

    # Check if container already exists
    print(
        f"{BRIGHT_CYAN}Checking for existing container...{RESET}",
        end=" ",
        flush=True,
    )
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=cua-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "cua-container" in result.stdout:
            print(f"{BRIGHT_YELLOW}⚠{RESET}")
            print(f"\n{BRIGHT_YELLOW}Container 'cua-container' already exists{RESET}")

            # Check if it's running
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "name=cua-container",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "cua-container" in result.stdout:
                print(f"{BRIGHT_GREEN}✓ Container is already running{RESET}\n")
                return True
            else:
                print(
                    f"{BRIGHT_CYAN}Starting existing container...{RESET}",
                    end=" ",
                    flush=True,
                )
                result = subprocess.run(
                    ["docker", "start", "cua-container"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    print(f"{BRIGHT_GREEN}✓{RESET}\n")
                    return True
                else:
                    print(f"{BRIGHT_RED}✗{RESET}")
                    print(
                        f"{BRIGHT_YELLOW}Removing broken container and rebuilding...{RESET}",
                    )
                    subprocess.run(
                        ["docker", "rm", "-f", "cua-container"],
                        capture_output=True,
                        timeout=30,
                    )
        else:
            print(f"{BRIGHT_GREEN}✓{RESET}")
    except subprocess.TimeoutExpired:
        print(f"{BRIGHT_RED}✗{RESET}")

    # Create temporary directory for Dockerfile
    print(f"\n{BRIGHT_CYAN}Building Computer Use Docker image...{RESET}")
    print(
        f"{BRIGHT_YELLOW}This will download Ubuntu 22.04 and install desktop environment{RESET}",
    )
    print(
        f"{BRIGHT_YELLOW}Estimated time: 2-5 minutes (depending on internet speed){RESET}\n",
    )

    build_dir = tempfile.mkdtemp(prefix="massgen-cua-")
    dockerfile_path = Path(build_dir) / "Dockerfile"

    # Create Dockerfile (matching setup_docker_cua.sh)
    dockerfile_content = """FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites for adding PPAs
RUN apt-get update && apt-get install -y \\
    software-properties-common \\
    wget \\
    gnupg \\
    && rm -rf /var/lib/apt/lists/*

# Add Mozilla PPA for real Firefox (not snap)
RUN add-apt-repository -y ppa:mozillateam/ppa

# Set up apt preferences to prioritize Mozilla PPA
RUN echo 'Package: *' > /etc/apt/preferences.d/mozilla-firefox && \\
    echo 'Pin: release o=LP-PPA-mozillateam' >> /etc/apt/preferences.d/mozilla-firefox && \\
    echo 'Pin-Priority: 1001' >> /etc/apt/preferences.d/mozilla-firefox

# Install desktop environment and tools
RUN apt-get update && apt-get install -y \\
    xvfb \\
    x11vnc \\
    xfce4 \\
    xfce4-terminal \\
    firefox \\
    chromium-browser \\
    scrot \\
    xdotool \\
    imagemagick \\
    xdg-utils \\
    && rm -rf /var/lib/apt/lists/*

# Set Firefox as the default browser
RUN update-alternatives --set x-www-browser /usr/bin/firefox && \\
    update-alternatives --set gnome-www-browser /usr/bin/firefox && \\
    xdg-settings set default-web-browser firefox.desktop

# Set up X11
ENV DISPLAY=:99

# Start script
RUN echo '#!/bin/bash' > /start.sh && \\
    echo 'Xvfb :99 -screen 0 1280x800x24 &' >> /start.sh && \\
    echo 'sleep 2' >> /start.sh && \\
    echo 'xfce4-session &' >> /start.sh && \\
    echo 'tail -f /dev/null' >> /start.sh && \\
    chmod +x /start.sh

CMD ["/start.sh"]
"""

    try:
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        # Build the image
        print(f"{BRIGHT_CYAN}Step 1/2: Building Docker image 'cua-ubuntu'...{RESET}")
        result = subprocess.run(
            ["docker", "build", "-t", "cua-ubuntu", build_dir],
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            print(f"\n{BRIGHT_RED}❌ Docker build failed{RESET}\n")
            return False

        print(f"\n{BRIGHT_GREEN}✓ Image built successfully{RESET}\n")

        # Remove existing container if it exists
        subprocess.run(
            ["docker", "rm", "-f", "cua-container"],
            capture_output=True,
            timeout=10,
        )

        # Run the container
        print(
            f"{BRIGHT_CYAN}Step 2/2: Starting container 'cua-container'...{RESET}",
            end=" ",
            flush=True,
        )
        result = subprocess.run(
            ["docker", "run", "-d", "--name", "cua-container", "cua-ubuntu"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"{BRIGHT_RED}✗{RESET}")
            print(f"\n{BRIGHT_RED}❌ Failed to start container{RESET}")
            print(f"{BRIGHT_YELLOW}Error: {result.stderr}{RESET}\n")
            return False

        print(f"{BRIGHT_GREEN}✓{RESET}")

        # Wait for container to be ready
        import time

        time.sleep(3)

        # Test the container
        print(f"{BRIGHT_CYAN}Testing container...{RESET}", end=" ", flush=True)
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "DISPLAY=:99",
                "cua-container",
                "xdotool",
                "getmouselocation",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            print(f"{BRIGHT_GREEN}✓{RESET}")
            print(f"\n{BRIGHT_CYAN}{'=' * 60}{RESET}")
            print(f"{BRIGHT_GREEN}  ✅ Computer Use Docker container ready!{RESET}")
            print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
            print(f"\n{BRIGHT_CYAN}Container details:{RESET}")
            print("  Name: cua-container")
            print("  Display: :99")
            print("  Resolution: 1280x800")
            print("  Desktop: Xfce4")
            print("  Browsers: Firefox, Chromium")
            print(f"\n{BRIGHT_CYAN}You can now run computer use examples:{RESET}")
            print(
                '  massgen --config @examples/tools/computer_use_docker_example.yaml "Open Firefox"',
            )
            print(
                '  massgen --config massgen/configs/tools/custom_tools/ui_tars_docker_example.yaml "..."\n',
            )
            return True
        else:
            print(f"{BRIGHT_RED}✗{RESET}")
            print(f"\n{BRIGHT_YELLOW}⚠️  Container created but test failed{RESET}")
            print(
                f"{BRIGHT_YELLOW}Please check container status: docker logs cua-container{RESET}\n",
            )
            return False

    except subprocess.TimeoutExpired:
        print(f"\n{BRIGHT_RED}❌ Setup timed out{RESET}\n")
        return False
    except Exception as e:
        print(f"\n{BRIGHT_RED}❌ Setup failed: {e}{RESET}\n")
        return False
    finally:
        # Cleanup temp directory
        import shutil

        try:
            shutil.rmtree(build_dir)
        except Exception:
            pass
