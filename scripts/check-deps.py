"""
Cross-platform dependency checker for AI-Wiki-knowledge.

Checks that all required tools are installed and prints install instructions
per platform if anything is missing. Also checks OpenCode version for hook support.

Usage:
    uv run python scripts/check-deps.py
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Minimum versions
MIN_PYTHON = (3, 12)
MIN_OPENCODE_HOOKS = "0.2.0"  # Version where session.start/stopping hooks were added

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def check_python() -> bool:
    """Check Python version >= 3.12."""
    major, minor = sys.version_info[:2]
    if (major, minor) >= MIN_PYTHON:
        print(f"  {GREEN}✓{RESET} Python {major}.{minor}.{sys.version_info.micro}")
        return True
    else:
        print(f"  {RED}✗{RESET} Python {major}.{minor} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")
        return False


def check_uv() -> bool:
    """Check if uv is installed."""
    if shutil.which("uv"):
        try:
            result = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
            version = result.stdout.strip()
            print(f"  {GREEN}✓{RESET} uv {version}")
            return True
        except subprocess.CalledProcessError:
            print(f"  {GREEN}✓{RESET} uv (version unknown)")
            return True
    else:
        print(f"  {RED}✗{RESET} uv (not found)")
        return False


def check_bun() -> bool:
    """Check if Bun is installed (required for OpenCode plugins)."""
    if shutil.which("bun"):
        try:
            result = subprocess.run(["bun", "--version"], capture_output=True, text=True, check=True)
            version = result.stdout.strip()
            print(f"  {GREEN}✓{RESET} bun {version}")
            return True
        except subprocess.CalledProcessError:
            print(f"  {GREEN}✓{RESET} bun (version unknown)")
            return True
    else:
        print(f"  {RED}✗{RESET} bun (not found)")
        return False


def check_opencode() -> tuple[bool, str | None]:
    """Check if OpenCode is installed and supports session hooks."""
    if not shutil.which("opencode"):
        print(f"  {YELLOW}⚠{RESET} opencode (not installed)")
        return False, None

    try:
        result = subprocess.run(
            ["opencode", "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        version = result.stdout.strip().lstrip("v")
        print(f"  {GREEN}✓{RESET} opencode {version}")

        # Check if version supports session hooks
        if _version_gte(version, MIN_OPENCODE_HOOKS):
            print(f"  {GREEN}✓{RESET} Session hooks supported")
            return True, version
        else:
            print(f"  {YELLOW}⚠{RESET} Session hooks require OpenCode {MIN_OPENCODE_HOOKS}+")
            print(f"    Your version ({version}) may not support session.start/stopping hooks.")
            print(f"    The tool.execute.after fallback will still work.")
            return False, version

    except subprocess.CalledProcessError:
        print(f"  {YELLOW}⚠{RESET} opencode (version check failed)")
        return False, None
    except subprocess.TimeoutExpired:
        print(f"  {YELLOW}⚠{RESET} opencode (version check timed out)")
        return False, None


def _version_gte(version: str, min_version: str) -> bool:
    """Compare semver strings. Returns True if version >= min_version."""
    def parse(v: str) -> tuple[int, ...]:
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts) or (0,)

    return parse(version) >= parse(min_version)


def print_install_instructions(missing: list[str]) -> None:
    """Print per-platform install instructions for missing dependencies."""
    system = platform.system()

    print(f"\n{BOLD}Install instructions for your platform ({system}):{RESET}\n")

    install_cmds = {
        "python": {
            "Darwin": "brew install python@3.12",
            "Linux": "sudo apt install python3.12  # Debian/Ubuntu\nsudo dnf install python3.12  # Fedora",
            "Windows": "winget install Python.Python.3.12  # or download from python.org",
        },
        "uv": {
            "Darwin": "brew install uv  # or: curl -LsSf https://astral.sh/uv/install.sh | sh",
            "Linux": "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "Windows": "winget install --id=astral-sh.uv -e  # or: pip install uv",
        },
        "bun": {
            "Darwin": "brew install oven-sh/bun/bun  # or: curl -fsSL https://bun.sh/install | bash",
            "Linux": "curl -fsSL https://bun.sh/install | bash",
            "Windows": "npm install -g bun  # or: powershell -c \"irm bun.sh/install.ps1|iex\"",
        },
        "opencode": {
            "Darwin": "brew install opencode  # or: curl -fsSL https://opencode.ai/install | bash",
            "Linux": "curl -fsSL https://opencode.ai/install | bash",
            "Windows": "npm install -g opencode  # or download from opencode.ai",
        },
    }

    for dep in missing:
        dep_name = dep.replace("opencode-hooks", "opencode")
        if dep_name in install_cmds:
            print(f"{BOLD}{dep_name}{RESET}:")
            cmd = install_cmds[dep_name].get(system, install_cmds[dep_name].get("Linux"))
            if cmd:
                print(f"  {cmd}")
            print()


def main() -> None:
    print(f"\n{BOLD}AI-Wiki-knowledge Dependency Check{RESET}\n")

    all_ok = True
    missing = []

    # Check Python
    print(f"{BOLD}Python{RESET} (>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}):")
    if not check_python():
        all_ok = False
        missing.append("python")

    # Check uv
    print(f"\n{BOLD}uv{RESET} (package manager):")
    if not check_uv():
        all_ok = False
        missing.append("uv")

    # Check bun
    print(f"\n{BOLD}bun{RESET} (OpenCode plugin runtime):")
    if not check_bun():
        all_ok = False
        missing.append("bun")

    # Check OpenCode
    print(f"\n{BOLD}opencode{RESET} (CLI):")
    opencode_ok, version = check_opencode()
    if not opencode_ok and version is None:
        missing.append("opencode")

    # Summary
    print(f"\n{'─' * 50}")
    if all_ok:
        print(f"{GREEN}{BOLD}All dependencies satisfied!{RESET}")
        print(f"\nYou're ready to use AI-Wiki-knowledge with Claude Code, Codex, and OpenCode.")
    else:
        print(f"{RED}{BOLD}Missing dependencies:{RESET}")
        print_install_instructions(missing)
        sys.exit(1)


if __name__ == "__main__":
    main()
