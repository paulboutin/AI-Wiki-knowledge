"""Shared utilities for the personal knowledge base."""

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from config import (
    CONCEPTS_DIR,
    CONNECTIONS_DIR,
    DAILY_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    QA_DIR,
    SCRIPTS_DIR,
    STATE_FILE,
)


# ── State management ──────────────────────────────────────────────────

def load_state() -> dict:
    """Load persistent state from state.json."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def save_state(state: dict) -> None:
    """Save state to state.json."""
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── File hashing ──────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    """SHA-256 hash of a file (first 16 hex chars)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ── Slug / naming ─────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ── Wikilink helpers ──────────────────────────────────────────────────

def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilinks]] from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def wiki_article_exists(link: str) -> bool:
    """Check if a wikilinked article exists on disk."""
    path = KNOWLEDGE_DIR / f"{link}.md"
    return path.exists()


# ── Wiki content helpers ──────────────────────────────────────────────

def read_wiki_index() -> str:
    """Read the knowledge base index file."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---------|---------|---------------|---------|"


def read_all_wiki_content() -> str:
    """Read index + all wiki articles into a single string for context."""
    parts = [f"## INDEX\n\n{read_wiki_index()}"]

    for subdir in [CONCEPTS_DIR, CONNECTIONS_DIR, QA_DIR]:
        if not subdir.exists():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            rel = md_file.relative_to(KNOWLEDGE_DIR)
            content = md_file.read_text(encoding="utf-8")
            parts.append(f"## {rel}\n\n{content}")

    return "\n\n---\n\n".join(parts)


def list_wiki_articles() -> list[Path]:
    """List all wiki article files."""
    articles = []
    for subdir in [CONCEPTS_DIR, CONNECTIONS_DIR, QA_DIR]:
        if subdir.exists():
            articles.extend(sorted(subdir.glob("*.md")))
    return articles


def list_raw_files() -> list[Path]:
    """List all daily log files."""
    if not DAILY_DIR.exists():
        return []
    return sorted(DAILY_DIR.glob("*.md"))


# ── Index helpers ─────────────────────────────────────────────────────

def count_inbound_links(target: str, exclude_file: Path | None = None) -> int:
    """Count how many wiki articles link to a given target."""
    count = 0
    for article in list_wiki_articles():
        if article == exclude_file:
            continue
        content = article.read_text(encoding="utf-8")
        if f"[[{target}]]" in content:
            count += 1
    return count


def get_article_word_count(path: Path) -> int:
    """Count words in an article, excluding YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:]
    return len(content.split())


def build_index_entry(rel_path: str, summary: str, sources: str, updated: str) -> str:
    """Build a single index table row."""
    link = rel_path.replace(".md", "")
    return f"| [[{link}]] | {summary} | {sources} | {updated} |"


# ── Team / Collaboration ──────────────────────────────────────────────

LOCK_FILE = SCRIPTS_DIR / ".compile.lock"
LOCK_TIMEOUT = 120  # seconds before a lock is considered stale


def get_contributor() -> str:
    """Get the current git user.name for attribution."""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        name = result.stdout.strip()
        return name if name else "anonymous"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "anonymous"


def acquire_lock(timeout: int = LOCK_TIMEOUT) -> bool:
    """Acquire compilation lock using atomic file creation.

    Returns True if lock acquired, False if already held.
    Cleans up stale locks older than timeout seconds.
    """
    if LOCK_FILE.exists():
        # Check for stale lock
        try:
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age > timeout:
                LOCK_FILE.unlink(missing_ok=True)
            else:
                return False
        except OSError:
            return False

    try:
        LOCK_FILE.write_text(
            json.dumps({"pid": os.getpid(), "acquired_at": time.time()}),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def release_lock() -> None:
    """Release compilation lock."""
    LOCK_FILE.unlink(missing_ok=True)


def is_git_repo(path: Path | None = None) -> bool:
    """Check if the given path (or project root) is inside a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, check=True, timeout=5,
            cwd=str(path) if path else str(ROOT_DIR),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def git_pull_rebase(path: Path | None = None) -> bool:
    """Run git pull --rebase. Returns True on success."""
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase", "--autostash"],
            capture_output=True, text=True, check=True, timeout=60,
            cwd=str(path) if path else str(ROOT_DIR),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        import logging
        logging.error("git pull --rebase failed: %s", e)
        return False


def git_commit_and_push(message: str, path: Path | None = None, max_retries: int = 3) -> bool:
    """Add knowledge/, commit, and push with retry on conflict.

    Returns True if push succeeded.
    """
    cwd = str(path) if path else str(ROOT_DIR)

    for attempt in range(max_retries):
        try:
            # Stage knowledge/
            subprocess.run(
                ["git", "add", "knowledge/"],
                capture_output=True, text=True, check=True, timeout=30,
                cwd=cwd,
            )

            # Commit (may be no-op if nothing changed)
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True, timeout=30,
                cwd=cwd,
            )
            if result.returncode != 0 and "nothing to commit" in result.stdout:
                return True  # nothing changed, consider success

            # Push
            result = subprocess.run(
                ["git", "push"],
                capture_output=True, text=True, timeout=60,
                cwd=cwd,
            )
            if result.returncode == 0:
                return True

            # Push failed - pull and retry
            if attempt < max_retries - 1:
                import logging
                logging.warning("Push failed (attempt %d/%d), pulling and retrying", attempt + 1, max_retries)
                git_pull_rebase(path)
                time.sleep(1)
            else:
                import logging
                logging.error("Push failed after %d attempts: %s", max_retries, result.stderr)
                return False

        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            import logging
            logging.error("git commit/push error: %s", e)
            if attempt < max_retries - 1:
                git_pull_rebase(path)
                time.sleep(1)
            else:
                return False

    return False
