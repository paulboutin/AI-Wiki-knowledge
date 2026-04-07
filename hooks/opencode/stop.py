"""
Stop hook for OpenCode - captures conversation transcript for memory extraction.

When an OpenCode session ends, the TypeScript plugin spawns this script with the
session ID. It locates the JSONL transcript, extracts conversation context, and
spawns flush.py as a background process to extract knowledge into the daily log.

Transcript location: ~/.local/share/opencode/{sessionID}.jsonl

This script does NO API calls - only local file I/O for speed (<10s).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "daily"
SCRIPTS_DIR = ROOT / "scripts"
STATE_DIR = SCRIPTS_DIR

# Transcript storage locations
if sys.platform == "win32":
    TRANSCRIPT_DIR = Path(os.environ.get("USERPROFILE", "")) / ".local" / "share" / "opencode"
else:
    TRANSCRIPT_DIR = Path.home() / ".local" / "share" / "opencode"

logging.basicConfig(
    filename=str(SCRIPTS_DIR / "flush.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [opencode-stop] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

MAX_TURNS = 30
MAX_CONTEXT_CHARS = 15_000
MIN_TURNS_TO_FLUSH = 1


def find_transcript(session_id: str) -> Path | None:
    """Locate the JSONL transcript for a given session ID."""
    # Direct pattern: {sessionID}.jsonl
    direct = TRANSCRIPT_DIR / f"{session_id}.jsonl"
    if direct.exists():
        return direct

    # Project-specific: <project-slug>/storage/{sessionID}.jsonl
    for project_dir in TRANSCRIPT_DIR.iterdir():
        if project_dir.is_dir():
            storage = project_dir / "storage" / f"{session_id}.jsonl"
            if storage.exists():
                return storage

    # Global: global/storage/{sessionID}.jsonl
    global_storage = TRANSCRIPT_DIR / "global" / "storage" / f"{session_id}.jsonl"
    if global_storage.exists():
        return global_storage

    return None


def extract_conversation_context(transcript_path: Path) -> tuple[str, int]:
    """Read JSONL transcript and extract last ~N conversation turns as markdown."""
    turns: list[str] = []

    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # OpenCode format: messages nested under 'message' key
            msg = entry.get("message", {})
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role = entry.get("role", "")
                content = entry.get("content", "")

            if role not in ("user", "assistant"):
                continue

            # Content can be string or list of blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)

            if isinstance(content, str) and content.strip():
                label = "User" if role == "user" else "Assistant"
                turns.append(f"**{label}:** {content.strip()}\n")

    recent = turns[-MAX_TURNS:]
    context = "\n".join(recent)

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
        boundary = context.find("\n**")
        if boundary > 0:
            context = context[boundary + 1 :]

    return context, len(recent)


def main() -> None:
    # Recursion guard
    if os.environ.get("CLAUDE_INVOKED_BY"):
        sys.exit(0)

    # Accept session_id as command line argument
    if len(sys.argv) < 2:
        logging.error("No session_id provided")
        return

    session_id = sys.argv[1]
    logging.info("OpenCode Stop fired: session=%s", session_id)

    transcript_path = find_transcript(session_id)
    if transcript_path is None:
        logging.info("SKIP: transcript not found for session %s", session_id)
        return

    try:
        context, turn_count = extract_conversation_context(transcript_path)
    except Exception as e:
        logging.error("Context extraction failed: %s", e)
        return

    if not context.strip():
        logging.info("SKIP: empty context")
        return

    if turn_count < MIN_TURNS_TO_FLUSH:
        logging.info("SKIP: only %d turns (min %d)", turn_count, MIN_TURNS_TO_FLUSH)
        return

    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    context_file = STATE_DIR / f"session-flush-{session_id}-{timestamp}.md"
    context_file.write_text(context, encoding="utf-8")

    flush_script = SCRIPTS_DIR / "flush.py"

    cmd = [
        "uv",
        "run",
        "--directory",
        str(ROOT),
        "python",
        str(flush_script),
        str(context_file),
        session_id,
    ]

    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env = os.environ.copy()
    env["CLAUDE_INVOKED_BY"] = "memory_flush"

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            env=env,
        )
        logging.info("Spawned flush.py for session %s (%d turns, %d chars)", session_id, turn_count, len(context))
    except Exception as e:
        logging.error("Failed to spawn flush.py: %s", e)


if __name__ == "__main__":
    main()
