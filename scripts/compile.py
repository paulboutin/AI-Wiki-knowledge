"""
Compile daily conversation logs into structured knowledge articles.

This is the "LLM compiler" - it reads daily logs (source code) and produces
organized knowledge articles (the executable).

In team mode (when knowledge/ is tracked in git), this script handles:
- git pull --rebase before compilation
- LLM-based deduplication against existing concepts
- Contributor attribution from git user.name
- git commit + push with retry on conflict
- File locking to prevent concurrent compilation

Usage:
    uv run python compile.py                    # compile new/changed logs only
    uv run python compile.py --all              # force recompile everything
    uv run python compile.py --file daily/2026-04-01.md  # compile a specific log
    uv run python compile.py --dry-run          # show what would be compiled
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from config import AGENTS_FILE, CONCEPTS_DIR, CONNECTIONS_DIR, DAILY_DIR, KNOWLEDGE_DIR, now_iso
from utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    read_wiki_index,
    save_state,
    get_contributor,
    acquire_lock,
    release_lock,
    is_git_repo,
    git_pull_rebase,
    git_commit_and_push,
)

# ── Paths for the LLM to use ──────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


async def find_similar_concept(index_content: str, new_title: str, new_summary: str) -> str | None:
    """Use LLM to check if a similar concept already exists in the knowledge base.

    Returns the wikilink path of the matching article, or None if no match.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    prompt = f"""You are a deduplication assistant. Given an existing knowledge base index
and a new concept, determine if any existing article already covers this topic.

## Knowledge Base Index

{index_content}

## New Concept

Title: {new_title}
Summary: {new_summary}

## Your Task

Does any existing article in the index already cover this topic? Consider:
- Exact title matches
- Alias matches
- Semantic similarity (e.g., "auth patterns" vs "authentication flow")

If a match exists, respond with ONLY the wikilink path (e.g., "concepts/supabase-auth").
If no match exists, respond with ONLY: NONE

Do not explain your reasoning. Just the path or NONE."""

    response = ""
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                allowed_tools=[],
                max_turns=1,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response += block.text
            elif isinstance(message, ResultMessage):
                pass
    except Exception as e:
        logger.error("Dedup check failed: %s", e)
        return None

    response = response.strip()
    if response.upper() == "NONE" or not response:
        return None

    # Clean up the response - extract just the path
    response = response.strip("[]\"'")
    if response.startswith("[[") and response.endswith("]]"):
        response = response[2:-2]

    # Validate it looks like a valid path
    if "/" in response or "\\" in response:
        return response

    return None


async def compile_daily_log(log_path: Path, state: dict) -> float:
    """Compile a single daily log into knowledge articles.

    Returns the API cost of the compilation.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    log_content = log_path.read_text(encoding="utf-8")
    schema = AGENTS_FILE.read_text(encoding="utf-8")
    wiki_index = read_wiki_index()

    # Read existing articles for context
    existing_articles_context = ""
    existing = {}
    for article_path in list_wiki_articles():
        rel = article_path.relative_to(KNOWLEDGE_DIR)
        existing[str(rel)] = article_path.read_text(encoding="utf-8")

    if existing:
        parts = []
        for rel_path, content in existing.items():
            parts.append(f"### {rel_path}\n```markdown\n{content}\n```")
        existing_articles_context = "\n\n".join(parts)

    timestamp = now_iso()

    contributor = get_contributor()

    prompt = f"""You are a knowledge compiler. Your job is to read a daily conversation log
and extract knowledge into structured wiki articles.

## Schema (AGENTS.md)

{schema}

## Current Wiki Index

{wiki_index}

## Existing Wiki Articles

{existing_articles_context if existing_articles_context else "(No existing articles yet)"}

## Daily Log to Compile

**File:** {log_path.name}
**Contributor:** {contributor}

{log_content}

## Your Task

Read the daily log above and compile it into wiki articles following the schema exactly.

### Rules:

1. **Extract key concepts** - Identify 3-7 distinct concepts worth their own article
2. **Create concept articles** in `knowledge/concepts/` - One .md file per concept
   - Use the exact article format from AGENTS.md (YAML frontmatter + sections)
   - Include `sources:` in frontmatter pointing to the daily log file
   - Include `contributors:` in frontmatter with ["{contributor}"]
   - Use `[[concepts/slug]]` wikilinks to link to related concepts
   - Write in encyclopedia style - neutral, comprehensive
3. **Create connection articles** in `knowledge/connections/` if this log reveals non-obvious
   relationships between 2+ existing concepts
4. **Update existing articles** if this log adds new information to concepts already in the wiki
   - Read the existing article, add the new information, add the source to frontmatter
   - Add "{contributor}" to the `contributors:` list in frontmatter if not already present
   - Add the daily log as a new source in frontmatter
5. **Update knowledge/index.md** - Add new entries to the table
   - Each entry: `| [[path/slug]] | One-line summary | source-file | {timestamp[:10]} |`
6. **Append to knowledge/log.md** - Add a timestamped entry:
   ```
   ## [{timestamp}] compile | {log_path.name}
   - Source: daily/{log_path.name}
   - Contributor: {contributor}
   - Articles created: [[concepts/x]], [[concepts/y]]
   - Articles updated: [[concepts/z]] (if any)
   ```

### File paths:
- Write concept articles to: {CONCEPTS_DIR}
- Write connection articles to: {CONNECTIONS_DIR}
- Update index at: {KNOWLEDGE_DIR / 'index.md'}
- Append log at: {KNOWLEDGE_DIR / 'log.md'}

### Quality standards:
- Every article must have complete YAML frontmatter
- Every article must link to at least 2 other articles via [[wikilinks]]
- Key Points section should have 3-5 bullet points
- Details section should have 2+ paragraphs
- Related Concepts section should have 2+ entries
- Sources section should cite the daily log with specific claims extracted
"""

    cost = 0.0

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                system_prompt={"type": "preset", "preset": "claude_code"},
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
                permission_mode="acceptEdits",
                max_turns=30,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        pass  # compilation output - LLM writes files directly
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
                print(f"  Cost: ${cost:.4f}")
    except Exception as e:
        print(f"  Error: {e}")
        return 0.0

    # Update state
    rel_path = log_path.name
    state.setdefault("ingested", {})[rel_path] = {
        "hash": file_hash(log_path),
        "compiled_at": now_iso(),
        "cost_usd": cost,
    }
    state["total_cost"] = state.get("total_cost", 0.0) + cost
    save_state(state)

    return cost


def _do_compile(args) -> None:
    """Core compilation logic — runs after team-mode setup."""
    state = load_state()

    # Determine which files to compile
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = DAILY_DIR / target.name
        if not target.exists():
            # Try resolving relative to project root
            target = ROOT_DIR / args.file
        if not target.exists():
            print(f"Error: {args.file} not found")
            sys.exit(1)
        to_compile = [target]
    else:
        all_logs = list_raw_files()
        if args.all:
            to_compile = all_logs
        else:
            to_compile = []
            for log_path in all_logs:
                rel = log_path.name
                prev = state.get("ingested", {}).get(rel, {})
                if not prev or prev.get("hash") != file_hash(log_path):
                    to_compile.append(log_path)

    if not to_compile:
        print("Nothing to compile - all daily logs are up to date.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Files to compile ({len(to_compile)}):")
    for f in to_compile:
        print(f"  - {f.name}")

    if args.dry_run:
        return

    # Compile each file sequentially
    total_cost = 0.0
    for i, log_path in enumerate(to_compile, 1):
        print(f"\n[{i}/{len(to_compile)}] Compiling {log_path.name}...")
        cost = asyncio.run(compile_daily_log(log_path, state))
        total_cost += cost
        print(f"  Done.")

    articles = list_wiki_articles()
    print(f"\nCompilation complete. Total cost: ${total_cost:.2f}")
    print(f"Knowledge base: {len(articles)} articles")


def main():
    parser = argparse.ArgumentParser(description="Compile daily logs into knowledge articles")
    parser.add_argument("--all", action="store_true", help="Force recompile all logs")
    parser.add_argument("--file", type=str, help="Compile a specific daily log file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be compiled")
    args = parser.parse_args()

    # ── Team mode: auto-detect git repo and handle sync ────────────────
    team_mode = is_git_repo(ROOT_DIR)

    if team_mode:
        contributor = get_contributor()
        print(f"Team mode enabled (contributor: {contributor})")

        # Acquire lock to prevent concurrent compilation
        if not acquire_lock():
            print("Compilation already in progress on this machine, skipping.")
            return

        try:
            # Pull latest shared knowledge before compiling
            print("Pulling latest knowledge base...")
            if not git_pull_rebase(ROOT_DIR):
                print("Warning: git pull failed, compiling with local state.")

            # Run compilation
            _do_compile(args)

            # Commit and push with retry
            print("Pushing compiled knowledge to shared repo...")
            success = git_commit_and_push(
                f"compile: update from {contributor}",
                path=ROOT_DIR,
            )
            if success:
                print("Knowledge base synced successfully.")
            else:
                print("Warning: push failed — knowledge compiled locally but not synced.")
                print("Run 'git push' manually when ready.")
        finally:
            release_lock()
    else:
        # Solo mode: no git sync needed
        _do_compile(args)


if __name__ == "__main__":
    main()
