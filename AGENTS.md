# AGENTS.md - Personal Knowledge Base Schema

> Adapted from [Andrej Karpathy's LLM Knowledge Base](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) architecture.
> Instead of ingesting external articles, this system compiles knowledge from your own AI conversations.

## The Compiler Analogy

```
daily/          = source code    (your conversations - the raw material)
LLM             = compiler       (extracts and organizes knowledge)
knowledge/      = executable     (structured, queryable knowledge base)
lint            = test suite     (health checks for consistency)
queries         = runtime        (using the knowledge)
```

You don't manually organize your knowledge. You have conversations, and the LLM handles the synthesis, cross-referencing, and maintenance.

---

## Architecture

### Layer 1: `daily/` - Conversation Logs (Immutable Source)

Daily logs capture what happened in your AI coding sessions. These are the "raw sources" - append-only, never edited after the fact.

```
daily/
├── 2026-04-01.md
├── 2026-04-02.md
├── ...
```

Each file follows this format:

```markdown
# Daily Log: YYYY-MM-DD

## Sessions

### Session (HH:MM) - Brief Title

**Context:** What the user was working on.

**Key Exchanges:**
- User asked about X, assistant explained Y
- Decided to use Z approach because...
- Discovered that W doesn't work when...

**Decisions Made:**
- Chose library X over Y because...
- Architecture: went with pattern Z

**Lessons Learned:**
- Always do X before Y to avoid...
- The gotcha with Z is that...

**Action Items:**
- [ ] Follow up on X
- [ ] Refactor Y when time permits
```

### Layer 2: `knowledge/` - Compiled Knowledge (LLM-Owned)

The LLM owns this directory entirely. Humans read it but rarely edit it directly.

```
knowledge/
├── index.md              # Master catalog - every article with one-line summary
├── log.md                # Append-only chronological build log
├── concepts/             # Atomic knowledge articles
├── connections/          # Cross-cutting insights linking 2+ concepts
└── qa/                   # Filed query answers (compounding knowledge)
```

### Layer 3: This File (AGENTS.md)

The schema that tells the LLM how to compile and maintain the knowledge base. This is the "compiler specification."

---

## Structural Files

### `knowledge/index.md` - Master Catalog

A table listing every knowledge article. This is the primary retrieval mechanism - the LLM reads this FIRST when answering any query, then selects relevant articles to read in full.

Format:

```markdown
# Knowledge Base Index

| Article | Summary | Compiled From | Updated |
|---------|---------|---------------|---------|
| [[concepts/supabase-auth]] | Row-level security patterns and JWT gotchas | daily/2026-04-02.md | 2026-04-02 |
| [[connections/auth-and-webhooks]] | Token verification patterns shared across Supabase auth and Stripe webhooks | daily/2026-04-02.md, daily/2026-04-04.md | 2026-04-04 |
```

### `knowledge/log.md` - Build Log

Append-only chronological record of every compile, query, and lint operation.

Format:

```markdown
# Build Log

## [2026-04-01T14:30:00] compile | Daily Log 2026-04-01
- Source: daily/2026-04-01.md
- Articles created: [[concepts/nextjs-project-structure]], [[concepts/tailwind-setup]]
- Articles updated: (none)

## [2026-04-02T09:00:00] query | "How do I handle auth redirects?"
- Consulted: [[concepts/supabase-auth]], [[concepts/nextjs-middleware]]
- Filed to: [[qa/auth-redirect-handling]]
```

---

## Article Formats

### Concept Articles (`knowledge/concepts/`)

One article per atomic piece of knowledge. These are facts, patterns, decisions, preferences, and lessons extracted from your conversations.

```markdown
---
title: "Concept Name"
aliases: [alternate-name, abbreviation]
tags: [domain, topic]
sources:
  - "daily/2026-04-01.md"
  - "daily/2026-04-03.md"
created: 2026-04-01
updated: 2026-04-03
---

# Concept Name

[2-4 sentence core explanation]

## Key Points

- [Bullet points, each self-contained]

## Details

[Deeper explanation, encyclopedia-style paragraphs]

## Related Concepts

- [[concepts/related-concept]] - How it connects

## Sources

- [[daily/2026-04-01.md]] - Initial discovery during project setup
- [[daily/2026-04-03.md]] - Updated after debugging session
```

### Connection Articles (`knowledge/connections/`)

Cross-cutting synthesis linking 2+ concepts. Created when a conversation reveals a non-obvious relationship.

```markdown
---
title: "Connection: X and Y"
connects:
  - "concepts/concept-x"
  - "concepts/concept-y"
sources:
  - "daily/2026-04-04.md"
created: 2026-04-04
updated: 2026-04-04
---

# Connection: X and Y

## The Connection

[What links these concepts]

## Key Insight

[The non-obvious relationship discovered]

## Evidence

[Specific examples from conversations]

## Related Concepts

- [[concepts/concept-x]]
- [[concepts/concept-y]]
```

### Q&A Articles (`knowledge/qa/`)

Filed answers from queries. Every complex question answered by the system can be permanently stored, making future queries smarter.

```markdown
---
title: "Q: Original Question"
question: "The exact question asked"
consulted:
  - "concepts/article-1"
  - "concepts/article-2"
filed: 2026-04-05
---

# Q: Original Question

## Answer

[The synthesized answer with [[wikilinks]] to sources]

## Sources Consulted

- [[concepts/article-1]] - Relevant because...
- [[concepts/article-2]] - Provided context on...

## Follow-Up Questions

- What about edge case X?
- How does this change if Y?
```

---

## Core Operations

### 1. Compile (daily/ -> knowledge/)

When processing a daily log:

1. Read the daily log file
2. Read `knowledge/index.md` to understand current knowledge state
3. Read existing articles that may need updating
4. For each piece of knowledge found in the log:
   - If an existing concept article covers this topic: UPDATE it with new information, add the daily log as a source
   - If it's a new topic: CREATE a new `concepts/` article
5. If the log reveals a non-obvious connection between 2+ existing concepts: CREATE a `connections/` article
6. UPDATE `knowledge/index.md` with new/modified entries
7. APPEND to `knowledge/log.md`

**Important guidelines:**
- A single daily log may touch 3-10 knowledge articles
- Prefer updating existing articles over creating near-duplicates
- Use Obsidian-style `[[wikilinks]]` with full relative paths from knowledge/
- Write in encyclopedia style - factual, concise, self-contained
- Every article must have YAML frontmatter
- Every article must link back to its source daily logs

### 2. Query (Ask the Knowledge Base)

1. Read `knowledge/index.md` (the master catalog)
2. Based on the question, identify 3-10 relevant articles from the index
3. Read those articles in full
4. Synthesize an answer with `[[wikilink]]` citations
5. If `--file-back` is specified: create a `knowledge/qa/` article and update index.md and log.md

**Why this works without RAG:** At personal knowledge base scale (50-500 articles), the LLM reading a structured index outperforms cosine similarity. The LLM understands what the question is really asking and selects pages accordingly. Embeddings find similar words; the LLM finds relevant concepts.

### 3. Lint (Health Checks)

Seven checks, run periodically:

1. **Broken links** - `[[wikilinks]]` pointing to non-existent articles
2. **Orphan pages** - Articles with zero inbound links from other articles
3. **Orphan sources** - Daily logs that haven't been compiled yet
4. **Stale articles** - Source daily log changed since article was last compiled
5. **Contradictions** - Conflicting claims across articles (requires LLM judgment)
6. **Missing backlinks** - A links to B but B doesn't link back to A
7. **Sparse articles** - Below 200 words, likely incomplete

Output: a markdown report with severity levels (error, warning, suggestion).

---

## Conventions

- **Wikilinks:** Use Obsidian-style `[[path/to/article]]` without `.md` extension
- **Writing style:** Encyclopedia-style, factual, third-person where appropriate
- **Dates:** ISO 8601 (YYYY-MM-DD for dates, full ISO for timestamps in log.md)
- **File naming:** lowercase, hyphens for spaces (e.g., `supabase-row-level-security.md`)
- **Frontmatter:** Every article must have YAML frontmatter with at minimum: title, sources, created, updated
- **Sources:** Always link back to the daily log(s) that contributed to an article

---

## Full Project Structure

```
ai-wiki-knowledge/
|-- .claude/
|   |-- settings.json                # Claude Code hook configuration
|-- .codex/
|   |-- hooks.json                   # Codex CLI hook configuration
|-- .opencode/
|   |-- plugins/
|   |   |-- knowledge-base.ts        # OpenCode plugin (TypeScript)
|   |-- package.json                 # Empty, for future deps
|-- .cursor/
|   |-- hooks.json                   # Cursor IDE/CLI hook configuration
|-- .gitignore                       # Excludes runtime state, temp files, caches
|-- AGENTS.md                        # This file - schema + full technical reference
|-- README.md                        # Concise overview + quick start
|-- pyproject.toml                   # Dependencies (at root so hooks can find it)
|-- daily/                           # "Source code" - conversation logs (immutable)
|-- knowledge/                       # "Executable" - compiled knowledge (LLM-owned)
|   |-- index.md                     #   Master catalog - THE retrieval mechanism
|   |-- log.md                       #   Append-only build log
|   |-- concepts/                    #   Atomic knowledge articles
|   |-- connections/                 #   Cross-cutting insights linking 2+ concepts
|   |-- qa/                          #   Filed query answers (compounding knowledge)
|-- scripts/                         # CLI tools
|   |-- compile.py                   #   Compile daily logs -> knowledge articles
|   |-- query.py                     #   Ask questions (index-guided, no RAG)
|   |-- lint.py                      #   7 health checks
|   |-- flush.py                     #   Extract memories from conversations (background)
|   |-- check-deps.py                #   Cross-platform dependency checker
|   |-- config.py                    #   Path constants
|   |-- utils.py                     #   Shared helpers
|-- hooks/
|   |-- claude/                      # Claude Code hooks
|   |   |-- session-start.py         #   Injects knowledge into every session
|   |   |-- session-end.py           #   Extracts conversation -> daily log
|   |   |-- pre-compact.py           #   Safety net: captures context before compaction
|   |-- codex/                       # Codex CLI hooks
|   |   |-- session-start.py         #   Injects knowledge into every session
|   |   |-- stop.py                  #   Extracts conversation -> daily log (Stop event)
|   |-- opencode/                    # OpenCode CLI/TUI hooks
|   |   |-- session-start.py         #   Injects knowledge into every session
|   |   |-- stop.py                  #   Extracts conversation -> daily log
|   |-- cursor/                      # Cursor IDE/CLI hooks
|       |-- session-start.py         #   Injects knowledge into every session
|       |-- session-end.py           #   Extracts conversation -> daily log
|       |-- pre-compact.py           #   Safety net: captures context before compaction
|-- reports/                         # Lint reports (gitignored)
```

---

## Hook System (Automatic Capture)

Hooks are configured in `.claude/settings.json` (Claude Code) or `.codex/hooks.json` (Codex CLI) and fire automatically when you use the respective agent in this project.

### Claude Code Hook Configuration

`.claude/settings.json` format:

```json
{
  "hooks": {
    "SessionStart": [{ "matcher": "", "hooks": [{ "type": "command", "command": "uv run python hooks/claude/session-start.py", "timeout": 15 }] }],
    "PreCompact": [{ "matcher": "", "hooks": [{ "type": "command", "command": "uv run python hooks/claude/pre-compact.py", "timeout": 10 }] }],
    "SessionEnd": [{ "matcher": "", "hooks": [{ "type": "command", "command": "uv run python hooks/claude/session-end.py", "timeout": 10 }] }]
  }
}
```

Commands use simple relative paths from the project root. Empty `matcher` catches all events.

### Codex CLI Hook Configuration

`.codex/hooks.json` format:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume",
      "hooks": [{
        "type": "command",
        "command": "uv run python hooks/codex/session-start.py",
        "statusMessage": "Loading knowledge base context"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "uv run python hooks/codex/stop.py",
        "timeout": 30
      }]
    }]
  }
}
```

**Required:** Enable hooks in your `~/.codex/config.toml`:
```toml
[features]
codex_hooks = true
```

Codex discovers hooks from `.codex/hooks.json` next to active config layers. Commands run with the session cwd as their working directory.

### Hook Details

#### Claude Code Hooks

**`session-start.py`** (SessionStart)
- Pure local I/O, no API calls, runs in under 1 second
- Reads `knowledge/index.md` and the most recent daily log
- Outputs JSON to stdout: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`
- Claude sees the knowledge base index at the start of every session
- Max context: 20,000 characters

**`session-end.py`** (SessionEnd)
- Reads hook input from stdin (JSON with `session_id`, `transcript_path`, `cwd`)
- Extracts conversation context from JSONL transcript
- Spawns `flush.py` as a fully detached background process
- Recursion guard: exits immediately if `CLAUDE_INVOKED_BY` env var is set

**`pre-compact.py`** (PreCompact)
- Same architecture as session-end.py
- Fires before Claude Code auto-compacts the context window
- Guards against empty `transcript_path` (known Claude Code bug #13668)
- Critical for long sessions: captures context before summarization discards it

**Why both PreCompact and SessionEnd?** Long-running sessions may trigger multiple auto-compactions before you close the session. Without PreCompact, intermediate context is lost to summarization before SessionEnd ever fires.

#### Codex CLI Hooks

**`session-start.py`** (SessionStart)
- Same logic as the Claude Code version
- Outputs JSON with `additionalContext` for Codex's SessionStart event
- Matcher filters on `startup|resume` source values

**`stop.py`** (Stop)
- Codex's equivalent to SessionEnd - fires when the session ends
- Reads JSON from stdin (session_id, transcript_path, cwd, hook_event_name, model)
- Extracts conversation context from JSONL transcript
- Spawns `flush.py` as a background process with `CLAUDE_INVOKED_BY` env var set
- Returns without continuing the session (lets it end normally)

**No PreCompact equivalent in Codex:** Codex does not have a pre-compaction event. Long-running Codex sessions may lose intermediate context to auto-compaction before the Stop hook fires. For critical sessions, run `compile.py` manually before the session ends.

#### OpenCode CLI/TUI Hooks

OpenCode uses a TypeScript plugin system (`.opencode/plugins/knowledge-base.ts`) instead of JSON-configured hooks. The plugin auto-discovers from the `.opencode/plugins/` directory — no config file needed.

**Plugin architecture:**
- Written in TypeScript, runs on Bun (OpenCode's plugin runtime)
- Uses `Bun.spawn()` to call Python hook scripts in `hooks/opencode/`
- All hook calls have timeout protection (10s for session.start, 30s for stop hooks)
- Session end detection has a fallback via `tool.execute.after`

**`session-start.py`** (session.start)
- Same logic as Claude/Codex versions
- Outputs JSON: `{"hookEventName": "SessionStart", "additionalContext": "..."}`
- Plugin injects context as `additionalInstructions` in the session input
- 10-second timeout wrapper in the plugin

**`stop.py`** (session.stopping - primary)
- Same architecture as Codex stop hook
- Receives session_id as command line argument from the plugin
- Locates transcript at `~/.local/share/opencode/{sessionID}.jsonl`
- Also checks project-specific (`<project-slug>/storage/`) and global (`global/storage/`) paths
- Extracts conversation context, spawns `flush.py` as detached background process
- 30-second timeout wrapper in the plugin

**`tool.execute.after`** (fallback)
- Fires after every tool execution
- Detects session-ending patterns: `exit`, `quit`, `end_session`, `close` tool calls
- Checks `scripts/last-flush.json` for deduplication before spawning stop.py
- Ensures memory capture even on older OpenCode versions without session.stopping

**No PreCompact equivalent in OpenCode:** Same limitation as Codex.

**Web version not supported:** OpenCode hooks only work with the CLI/TUI version. The web version runs on a remote server and does not support local plugins.

**Dependency requirements:**
- **Python 3.12+** — for hook scripts
- **uv** — Python package manager (runs hook scripts)
- **bun** — JavaScript runtime (required by OpenCode for plugins)
- **OpenCode 0.2.0+** — for session.start and session.stopping hooks (tool.execute.after fallback works on older versions)

Run `uv run python scripts/check-deps.py` to verify all dependencies are installed.

#### Cursor IDE/CLI Hooks

Cursor uses a JSON-configured hook system nearly identical to Claude Code's. Config lives in `.cursor/hooks.json` with a `version: 1` schema.

**`.cursor/hooks.json` format:**
```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [{ "command": "uv run python hooks/cursor/session-start.py" }],
    "preCompact": [{ "command": "uv run python hooks/cursor/pre-compact.py" }],
    "sessionEnd": [{ "command": "uv run python hooks/cursor/session-end.py" }]
  }
}
```

Hook events use **camelCase** (not PascalCase like Claude Code).

**`session-start.py`** (sessionStart)
- Same logic as Claude/Codex versions
- Output format adapted for Cursor: `{ "additional_context": "...", "env": {} }`
- Cursor injects this as additional context in the conversation's initial system prompt
- Also accepts `session_id` and `is_background_agent` fields from stdin

**`session-end.py`** (sessionEnd)
- Same architecture as Claude Code version
- Reads `transcript_path` from stdin JSON (same field name)
- Also receives `session_id`, `reason`, `duration_ms`, `final_status` from stdin
- Extracts conversation context, spawns `flush.py` as background process
- Fire-and-forget — no output expected

**`pre-compact.py`** (preCompact)
- Same architecture as Claude Code version
- Receives `trigger`, `context_usage_percent`, `context_tokens`, `message_count` from stdin
- Output: `{ "user_message": "Context compacted — memory captured." }`
- Critical for long sessions: captures context before summarization discards it

**Cursor-specific features:**
- `CURSOR_TRANSCRIPT_PATH` env variable also provides the transcript path
- `CURSOR_PROJECT_DIR` env variable provides the workspace root
- `CLAUDE_PROJECT_DIR` alias also set for compatibility
- Hooks run from the **project root** — relative paths work as expected
- Auto-reloads `hooks.json` on save

**Third-party skills compatibility:** Cursor can run Claude Code hooks directly when "Third-party skills" is enabled in Settings → Features. This is an alternative to the native Cursor hooks but the native approach is cleaner.

### Background Flush Process (`flush.py`)

Spawned by Claude, Codex, and OpenCode hooks as a fully detached background process:
- **Windows:** `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` flags
- **Mac/Linux:** `start_new_session=True` (Claude/Codex) or `child.unref()` (OpenCode)

This ensures flush.py survives after the hook process exits.

**What flush.py does:**
1. Sets `CLAUDE_INVOKED_BY=memory_flush` and `CODEX_INVOKED_BY=memory_flush` env vars (prevents recursive hook firing)
2. Reads the pre-extracted conversation context from the temp `.md` file
3. Skips if context is empty or if same session was flushed within 60 seconds (deduplication)
4. Calls Claude Agent SDK (`query()` with `allowed_tools=[]`, `max_turns=2`)
5. Claude decides what's worth saving - returns structured bullet points or `FLUSH_OK`
6. Appends result to `daily/YYYY-MM-DD.md`
7. Cleans up temp context file
8. **End-of-day auto-compilation:** If it's past 6 PM local time (`COMPILE_AFTER_HOUR = 18`) and today's daily log has changed since its last compilation (hash comparison against `state.json`), spawns `compile.py` as another detached background process. This means compilation happens automatically once a day without needing a cron job or manual trigger.

### JSONL Transcript Format

All three platforms store conversations as `.jsonl` files. Messages are nested under a `message` key:

```python
entry = json.loads(line)
msg = entry.get("message", {})
role = msg.get("role", "")     # "user" or "assistant"
content = msg.get("content", "")  # string or list of content blocks
```

Content can be a string or a list of blocks (`{"type": "text", "text": "..."}` dicts).

**Transcript locations by platform:**
- **Claude Code:** Provided via `transcript_path` in hook stdin
- **Codex CLI:** Provided via `transcript_path` in hook stdin
- **OpenCode:** `~/.local/share/opencode/{sessionID}.jsonl` (or project-specific/global subdirectories)
- **Cursor:** Provided via `transcript_path` in hook stdin + `CURSOR_TRANSCRIPT_PATH` env var

### Platform Comparison

| Aspect | Claude Code | Codex CLI | OpenCode CLI/TUI | Cursor IDE/CLI |
|--------|-------------|-----------|------------------|----------------|
| Session start | SessionStart | SessionStart | session.start | sessionStart |
| Session end | SessionEnd | Stop | session.stopping | sessionEnd |
| Pre-compaction | PreCompact | Not available | Not available | preCompact |
| Fallback | N/A | N/A | tool.execute.after | N/A |
| Config file | `.claude/settings.json` | `.codex/hooks.json` + `config.toml` flag | `.opencode/plugins/` (auto-discover) | `.cursor/hooks.json` |
| Hook input | JSON on stdin | JSON on stdin | Plugin context object | JSON on stdin |
| Hook output | JSON on stdout | JSON on stdout | additionalInstructions | JSON on stdout |
| Transcript | JSONL format | JSONL format | JSONL format | JSONL format |
| Feature flag | None (always on) | `codex_hooks = true` in config.toml | None (auto-discover) | None (always on) |
| Runtime | Python | Python | TypeScript (Bun) → Python | Python |
| Web support | N/A | N/A | No (CLI/TUI only) | IDE + CLI |

---

## Script Details

### compile.py - The Compiler

Uses the Claude Agent SDK's async streaming `query()`:

```python
async for message in query(
    prompt=compile_prompt,
    options=ClaudeAgentOptions(
        cwd=str(ROOT_DIR),
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
        permission_mode="acceptEdits",
        max_turns=30,
    ),
):
```

- Builds a prompt with: AGENTS.md schema, current index, all existing articles, and the daily log
- Claude reads the daily log, decides what concepts to extract, and writes files directly
- `permission_mode="acceptEdits"` auto-approves all file operations
- Incremental: tracks SHA-256 hashes of daily logs in `state.json`, skips unchanged files
- Cost: ~$0.45-0.65 per daily log (increases as KB grows)

**CLI:**
```bash
uv run python scripts/compile.py              # compile new/changed only
uv run python scripts/compile.py --all        # force recompile everything
uv run python scripts/compile.py --file daily/2026-04-01.md
uv run python scripts/compile.py --dry-run
```

### query.py - Index-Guided Retrieval

Loads the entire knowledge base into context (index + all articles). No RAG.

At personal KB scale (50-500 articles), the LLM reading a structured index outperforms vector similarity. The LLM understands what you're really asking; cosine similarity just finds similar words.

**CLI:**
```bash
uv run python scripts/query.py "What auth patterns do I use?"
uv run python scripts/query.py "What's my error handling strategy?" --file-back
```

With `--file-back`, creates a Q&A article in `knowledge/qa/` and updates the index and log. This is the compounding loop - every question makes the KB smarter.

### lint.py - Health Checks

Seven checks:

| Check | Type | Catches |
|-------|------|---------|
| Broken links | Structural | `[[wikilinks]]` to non-existent articles |
| Orphan pages | Structural | Articles with zero inbound links |
| Orphan sources | Structural | Daily logs not yet compiled |
| Stale articles | Structural | Source logs changed since compilation |
| Missing backlinks | Structural | A links to B but B doesn't link back |
| Sparse articles | Structural | Under 200 words |
| Contradictions | LLM | Conflicting claims across articles |

**CLI:**
```bash
uv run python scripts/lint.py                    # all checks
uv run python scripts/lint.py --structural-only  # skip LLM check (free)
```

Reports saved to `reports/lint-YYYY-MM-DD.md`.

---

## State Tracking

`scripts/state.json` tracks:
- `ingested` - map of daily log filenames to SHA-256 hashes, compilation timestamps, and costs
- `query_count` - total queries run
- `last_lint` - timestamp of most recent lint
- `total_cost` - cumulative API cost

`scripts/last-flush.json` tracks flush deduplication (session_id + timestamp).

Both are gitignored and regenerated automatically.

---

## Dependencies

### Python (all platforms)

`pyproject.toml` (at project root):
- `claude-agent-sdk>=0.1.29` - Claude Agent SDK for LLM calls with tool use
- `python-dotenv>=1.0.0` - Environment variable management
- `tzdata>=2024.1` - Timezone data
- Python 3.12+, managed by [uv](https://docs.astral.sh/uv/)

No API key needed - uses Claude Code's built-in credentials at `~/.claude/.credentials.json`.

### OpenCode (additional)

- **bun** - JavaScript runtime for OpenCode plugins
- **OpenCode 0.2.0+** - for session.start and session.stopping hooks (fallback works on older)

Run `uv run python scripts/check-deps.py` to verify all dependencies are installed.

### Team / Collaboration Mode

The knowledge base supports multi-developer teams. When `knowledge/` is tracked in a git repo, `compile.py` automatically enters team mode.

**How it works:**

1. **Daily logs are personal** — `daily/` is gitignored, each developer's conversations stay local
2. **Knowledge is shared** — `knowledge/` is tracked in git, compiled articles are available to everyone
3. **Auto-sync on compile** — `compile.py` runs `git pull --rebase` before compiling and `git commit + push` after
4. **File locking** — prevents concurrent compilation on the same machine via `scripts/.compile.lock`
5. **Push retry** — if two developers push simultaneously, the loser pulls and retries (up to 3 times)
6. **LLM deduplication** — before creating a new concept, the LLM checks if a similar article already exists and merges instead
7. **Contributor attribution** — every article tracks contributors via `git config user.name`

**Git sync flow:**
```
compile.py:
  1. acquire_lock()          # prevent concurrent local compilation
  2. git pull --rebase       # get latest shared knowledge
  3. compile daily/ → knowledge/
  4. git add knowledge/
  5. git commit -m "compile: update from {contributor}"
  6. git push                # retry on conflict (up to 3x)
  7. release_lock()
```

**Article frontmatter with contributors:**
```yaml
---
title: "Supabase Auth Patterns"
contributors: ["alice", "bob"]
sources:
  - "daily/2026-04-06.md (alice)"
  - "daily/2026-04-07.md (bob)"
---
```

**Deduplication:** The `find_similar_concept()` function uses the Claude Agent SDK to compare new concepts against the existing `knowledge/index.md`. It checks for exact title matches, alias matches, and semantic similarity. If a match is found, the compiler updates the existing article instead of creating a duplicate.

**Solo mode:** If `knowledge/` is not in a git repo, `compile.py` skips all git operations and works locally as before.

### New Developer Onboarding

When a developer joins a project that already has AI-Wiki-knowledge set up:

**What happens on `git pull`:**
- `knowledge/` comes with all previously compiled articles — the new dev immediately has access to the team's accumulated knowledge
- Hook configs (`.claude/`, `.cursor/`, `.codex/`, `.opencode/`) are already in place
- Scripts are ready to run

**What gets created locally (gitignored):**
- `daily/` — personal conversation logs, created on first session
- `scripts/state.json` — personal compilation state
- `scripts/last-flush.json` — personal flush dedup state

**First session flow for a new dev:**
1. They open their AI coding tool in the project
2. `sessionStart` hook fires → injects the existing `knowledge/index.md` into context
3. They now have the team's full knowledge base at the start of their first session
4. When their session ends, `sessionEnd` hook fires → captures their conversation → `daily/`
5. Next `compile.py` run → their daily log gets compiled → `knowledge/` updated → pushed to shared repo

**No manual setup required.** The system is fully self-configuring from the repo state.

---

## Costs

| Operation | Cost |
|-----------|------|
| Compile one daily log | $0.45-0.65 |
| Query (no file-back) | ~$0.15-0.25 |
| Query (with file-back) | ~$0.25-0.40 |
| Full lint (with contradictions) | ~$0.15-0.25 |
| Structural lint only | $0.00 |
| Memory flush (per session) | ~$0.02-0.05 |

---

## Customization

### Additional Article Types

Add directories like `people/`, `projects/`, `tools/` to `knowledge/`. Define the article format in this file (AGENTS.md) and update `utils.py`'s `list_wiki_articles()` to include them.

### Obsidian Integration

The knowledge base is pure markdown with `[[wikilinks]]` - works natively in Obsidian. Point a vault at `knowledge/` for graph view, backlinks, and search.

### Scaling Beyond Index-Guided Retrieval

At ~2,000+ articles / ~2M+ tokens, the index becomes too large for the context window. At that point, add hybrid RAG (keyword + semantic search) as a retrieval layer before the LLM. See Karpathy's recommendation of `qmd` by Tobi Lutke for search at scale.
