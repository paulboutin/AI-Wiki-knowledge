"""
Install AI-Wiki-knowledge into an existing project.

This script copies the knowledge base infrastructure into the target project
without overwriting existing files. It handles:
- Merging .gitignore entries
- Merging pyproject.toml dependencies
- Creating hook directories and configs
- Installing scripts and hooks
- Preserving existing AGENTS.md (appends or creates backup)

Usage:
    # Install from this repo into the parent directory
    uv run python scripts/install.py

    # Install into a specific project directory
    uv run python scripts/install.py /path/to/project

    # Dry run - show what would happen without making changes
    uv run python scripts/install.py --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# This script's directory
INSTALLER_DIR = Path(__file__).resolve().parent
SOURCE_DIR = INSTALLER_DIR.parent  # The AI-Wiki-knowledge repo root

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_status(icon: str, message: str, color: str = GREEN) -> None:
    print(f"  {color}{icon}{RESET} {message}")


def merge_gitignore(target: Path, source: Path, dry_run: bool = False) -> None:
    """Append AI-Wiki-knowledge entries to existing .gitignore."""
    source_content = source.read_text(encoding="utf-8")

    # Extract our entries (everything under the AI-Wiki-knowledge comment markers)
    our_entries = []
    in_section = False
    for line in source_content.splitlines():
        if "AI-Wiki-knowledge" in line or line.startswith("# Python") or line.startswith("# Runtime state") or line.startswith("# Generated content") or line.startswith("# Reports") or line.startswith("# uv lock") or line.startswith("# Claude Code local") or line.startswith("# Codex local") or line.startswith("# OpenCode local") or line.startswith("# Cursor local") or line.startswith("# OS files") or line.startswith(".obsidian/"):
            in_section = True
        if in_section:
            our_entries.append(line)
        if in_section and line == "" and our_entries and our_entries[-1] == "":
            # End of a section
            pass

    # Simpler approach: just use the full source content as reference
    our_patterns = [
        "__pycache__/",
        "*.pyc",
        ".venv/",
        "scripts/state.json",
        "scripts/last-flush.json",
        "scripts/flush.log",
        "scripts/compile.log",
        "scripts/session-flush-*",
        "scripts/flush-context-*",
        "daily/",
        "knowledge/",
        "reports/",
        "scripts/uv.lock",
        ".claude/settings.local.json",
        ".codex/config.local.toml",
        ".opencode/config.local.json",
        ".cursor/hooks.local.json",
        "scripts/.compile.lock",
        ".DS_Store",
        "Thumbs.db",
        ".obsidian/",
    ]

    if not target.exists():
        if not dry_run:
            target.write_text(source_content, encoding="utf-8")
        print_status("✓", f"Created .gitignore")
        return

    existing_content = target.read_text(encoding="utf-8")
    existing_lines = set(existing_content.splitlines())

    # Find patterns that aren't already in the file
    missing = []
    for pattern in our_patterns:
        if pattern not in existing_lines:
            missing.append(pattern)

    if not missing:
        print_status("✓", ".gitignore already up to date")
        return

    if dry_run:
        print_status("→", f"Would add {len(missing)} entries to .gitignore:")
        for m in missing[:5]:
            print(f"      + {m}")
        if len(missing) > 5:
            print(f"      ... and {len(missing) - 5} more")
        return

    # Append missing entries
    append_content = "\n\n# AI-Wiki-knowledge (auto-added by install.py)\n"
    append_content += "\n".join(f"# {m}" if m.startswith("#") or m.startswith(".") or "/" in m else m for m in missing)
    append_content += "\n"

    with open(target, "a", encoding="utf-8") as f:
        f.write(append_content)

    print_status("✓", f"Added {len(missing)} entries to .gitignore")


def merge_pyproject(target: Path, source: Path, dry_run: bool = False) -> None:
    """Add our dependencies to existing pyproject.toml."""
    source_content = source.read_text(encoding="utf-8")

    if not target.exists():
        if not dry_run:
            target.write_text(source_content, encoding="utf-8")
        print_status("✓", "Created pyproject.toml")
        return

    existing = target.read_text(encoding="utf-8")

    # Check if our dependencies are already present
    our_deps = ["claude-agent-sdk", "python-dotenv", "tzdata"]
    missing = [dep for dep in our_deps if dep not in existing]

    if not missing:
        print_status("✓", "pyproject.toml already has required dependencies")
        return

    if dry_run:
        print_status("→", f"Would add dependencies to pyproject.toml: {', '.join(missing)}")
        return

    # Try to add dependencies to the [project] dependencies section
    if "dependencies" in existing and "[" in existing:
        # Find the dependencies array and add our deps
        lines = existing.splitlines()
        new_lines = []
        in_deps = False
        added = False

        for line in lines:
            new_lines.append(line)
            if "dependencies" in line and "[" in line:
                in_deps = True
            if in_deps and "]" in line and not added:
                # Add our deps before the closing bracket
                indent = "    "
                for dep in missing:
                    # Find the version from source
                    for src_line in source_content.splitlines():
                        if dep in src_line:
                            new_lines.append(f"{indent}\"{dep.strip()}\",")
                            added = True
                            break
                in_deps = False
            if in_deps and "]" in line:
                in_deps = False

        if not added:
            # Fallback: append a comment
            new_lines.append("")
            new_lines.append("# AI-Wiki-knowledge dependencies (add these manually):")
            for dep in missing:
                new_lines.append(f"#   {dep}")

        target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print_status("✓", f"Added dependencies to pyproject.toml: {', '.join(missing)}")
    else:
        # Can't safely merge - tell the user
        print_status("!", f"Could not auto-merge dependencies. Please add: {', '.join(missing)}", YELLOW)


def copy_dir_if_not_exists(source: Path, target: Path, dry_run: bool = False) -> None:
    """Copy a directory only if it doesn't exist at the target."""
    if target.exists():
        print_status("✓", f"{target.relative_to(target.parent)}/ already exists, skipping")
        return

    if dry_run:
        print_status("→", f"Would create {target.relative_to(target.parent)}/")
        return

    shutil.copytree(source, target)
    print_status("✓", f"Created {target.relative_to(target.parent)}/")


def copy_file_if_not_exists(source: Path, target: Path, dry_run: bool = False) -> None:
    """Copy a file only if it doesn't exist at the target."""
    if target.exists():
        print_status("✓", f"{target.relative_to(target.parent)} already exists, skipping")
        return

    if dry_run:
        print_status("→", f"Would create {target.relative_to(target.parent)}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print_status("✓", f"Created {target.relative_to(target.parent)}")


def handle_agents_md(source: Path, target: Path, dry_run: bool = False) -> None:
    """Handle AGENTS.md - the file most likely to conflict."""
    if not target.exists():
        if not dry_run:
            shutil.copy2(source, target)
        print_status("✓", "Created AGENTS.md")
        return

    # File exists - check if it's already our AGENTS.md
    source_content = source.read_text(encoding="utf-8")
    target_content = target.read_text(encoding="utf-8")

    if source_content == target_content:
        print_status("✓", "AGENTS.md is already up to date")
        return

    # Different file - create backup and offer guidance
    backup = target.with_suffix(".md.ai-wiki-backup")

    if dry_run:
        print_status("→", "AGENTS.md already exists with different content")
        print_status("→", f"Would create backup at {backup.name}")
        print_status("→", "Would append AI-Wiki-knowledge section to existing AGENTS.md")
        return

    # Create backup
    shutil.copy2(target, backup)
    print_status("✓", f"Backed up existing AGENTS.md to {backup.name}")

    # Append our content
    append_section = """

---

<!-- AI-Wiki-knowledge schema (appended by install.py) -->
<!-- See full docs at: https://github.com/paulboutin/AI-Wiki-knowledge -->

"""
    append_section += source_content

    with open(target, "a", encoding="utf-8") as f:
        f.write(append_section)

    print_status("✓", "Appended AI-Wiki-knowledge schema to AGENTS.md")
    print_status("!", "Review the appended content and merge manually if needed", YELLOW)


def handle_license(source: Path, target: Path, dry_run: bool = False) -> None:
    """Handle LICENSE - only create if project has no license."""
    if target.exists():
        print_status("✓", "LICENSE already exists, skipping")
        return

    if dry_run:
        print_status("→", "Would create LICENSE (MIT)")
        return

    shutil.copy2(source, target)
    print_status("✓", "Created LICENSE (MIT)")


def main():
    parser = argparse.ArgumentParser(
        description="Install AI-Wiki-knowledge into an existing project"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="..",
        help="Target project directory (default: parent directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be installed without making changes",
    )
    args = parser.parse_args()

    target = Path(args.target).resolve()

    if not target.exists():
        print(f"{RED}Error:{RESET} Target directory does not exist: {target}")
        sys.exit(1)

    print(f"\n{BOLD}AI-Wiki-knowledge Installer{RESET}")
    print(f"Target: {target}\n")

    if args.dry_run:
        print(f"{YELLOW}DRY RUN - no changes will be made{RESET}\n")

    # 1. .gitignore - merge entries
    print(f"{BOLD}.gitignore{RESET}")
    merge_gitignore(target / ".gitignore", SOURCE_DIR / ".gitignore", args.dry_run)

    # 2. pyproject.toml - merge dependencies
    print(f"\n{BOLD}pyproject.toml{RESET}")
    merge_pyproject(target / "pyproject.toml", SOURCE_DIR / "pyproject.toml", args.dry_run)

    # 3. AGENTS.md - handle carefully
    print(f"\n{BOLD}AGENTS.md{RESET}")
    handle_agents_md(SOURCE_DIR / "AGENTS.md", target / "AGENTS.md", args.dry_run)

    # 4. LICENSE - only if missing
    print(f"\n{BOLD}LICENSE{RESET}")
    handle_license(SOURCE_DIR / "LICENSE", target / "LICENSE", args.dry_run)

    # 5. Directories - create if missing
    print(f"\n{BOLD}Directories{RESET}")
    for dir_name in ["hooks", "scripts", "daily", "knowledge/concepts", "knowledge/connections", "knowledge/qa", "reports", "docs"]:
        source_dir = SOURCE_DIR / dir_name
        target_dir = target / dir_name
        if source_dir.exists():
            copy_dir_if_not_exists(source_dir, target_dir, args.dry_run)

    # 6. Hook configs
    print(f"\n{BOLD}Hook Configs{RESET}")
    for config_dir in [".claude", ".codex", ".cursor", ".opencode"]:
        source_config = SOURCE_DIR / config_dir
        target_config = target / config_dir
        if source_config.exists():
            copy_dir_if_not_exists(source_config, target_config, args.dry_run)

    # 7. Scripts
    print(f"\n{BOLD}Scripts{RESET}")
    for script in (SOURCE_DIR / "scripts").glob("*.py"):
        copy_file_if_not_exists(script, target / "scripts" / script.name, args.dry_run)

    # 8. uv.lock
    print(f"\n{BOLD}Dependencies{RESET}")
    if not (target / "uv.lock").exists():
        if args.dry_run:
            print_status("→", "Would run 'uv sync' to install dependencies")
        else:
            print_status("!", "Run 'uv sync' to install Python dependencies", YELLOW)
    else:
        print_status("✓", "uv.lock exists - run 'uv sync' to update dependencies")

    # Summary
    print(f"\n{'─' * 50}")
    if args.dry_run:
        print(f"{YELLOW}Dry run complete. Run without --dry-run to install.{RESET}")
    else:
        print(f"{GREEN}{BOLD}Installation complete!{RESET}")
        print(f"\nNext steps:")
        print(f"  1. Run 'uv sync' to install dependencies")
        print(f"  2. Start using your AI coding tool - hooks activate automatically")
        print(f"  3. Run 'uv run python scripts/query.py \"what do I know?\"' to test")


if __name__ == "__main__":
    main()
