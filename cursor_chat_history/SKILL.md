---
name: cursor-chat-history
description: Backup, search, and inspect Cursor IDE agent transcript JSONL under ~/.cursor/projects/**/agent-transcripts/. Use for gzip mirrors to sync storage (e.g. iCloud), listing transcripts by mtime, profiling large JSONL before reading, bounding sessions by JSON timestamps (timestamp, created_at, ts), or extracting user-authored messages with jq or the bundled PEP 723 script. Not Codex CLI rollouts.
---

# Cursor Chat History

## What this covers

**Cursor IDE** stores **agent transcripts** as append-only JSONL. Typical layout:

```text
$CURSOR_PROJECTS_ROOT/<project-id>/agent-transcripts/<uuid>.jsonl
```

**Discovery root** (for `list`, `profile`, `bounds`, and default `backup --src`):

1. **`$CURSOR_PROJECTS_ROOT`** if set  
2. Else **`$CURSOR_AGENT_TRANSCRIPTS_ROOT`** if set  
3. Else **`~/.cursor/projects`**

The script collects only paths where the path contains the segment **`agent-transcripts`** and the file ends with **`.jsonl`**.

Each line is usually a JSON object with chat/event fields. User-authored content commonly has **`"role": "user"`** (sometimes **`human`**) and **`message.content`** items like **`{"type": "text", "text": "..."}`**.

**This skill is not** about **Codex CLI** session rollouts (`rollout-*.jsonl` under `$CODEX_HOME/sessions`). For that, use **`codex_chat_history`**.

## When to use it

- **Backup / mirror** the projects tree (gzip for transcript JSONL only; **`copy2`** for other files) to a cloud-synced folder.
- **Search or recover** what the user said: extract user lines, then `rg` / filter by topic.
- **Inspect** large files safely: histogram or line-slice before loading whole files into context.
- **Bound by time**: first/last `timestamp` / `created_at` / `ts` per file, or filesystem mtime with `--since`.

## Environment variables

All paths support **`~`** expansion. Use **absolute** paths when clarity matters.

| Variable | Purpose | If unset |
|----------|---------|----------|
| **`CURSOR_PROJECTS_ROOT`** | Preferred tree root for discovery | see fallbacks below |
| **`CURSOR_AGENT_TRANSCRIPTS_ROOT`** | Alternate tree root if `PROJECTS` unset | —              |
| (default) | | **`~/.cursor/projects`** |
| **`CURSOR_TRANSCRIPTS_BACKUP_ROOT`** | Default destination root for **`backup`** | **`~/icloud/.cursor/projects`** |

**CLI overrides:** subcommands accept **`--src`**; **`backup`** also accepts **`--dst`** or **`--dest`**, which wins over env defaults for that run.

## Bundled tools (this folder)

| File | Role |
|------|------|
| **`cursor_chat_history.py`** | PEP 723 **`uv run --script`** helper (`requires-python = ">=3.13.0,<3.14"`, `dependencies = []`): **`backup`**, **`list`**, **`profile`**, **`bounds`**, **`user-messages`**. |
| **`line_histogram.awk`** | Optional: line-size histogram or extract specific line(s) from huge JSONL before parsing. |

```sh
chmod +x cursor_chat_history.py
./cursor_chat_history.py --help
```

**Profile** with histogram (from repo, gist, or clone):

```sh
./cursor_chat_history.py profile --awk ./line_histogram.awk --since 1d
```

**Backup** (default destination = `$CURSOR_TRANSCRIPTS_BACKUP_ROOT` or `~/icloud/.cursor/projects`):

```sh
./cursor_chat_history.py backup --dry-run
./cursor_chat_history.py backup --dest "$HOME/icloud/.cursor/projects"
```

Incremental behavior: existing **`.jsonl.gz`** targets are skipped when the embedded gzip **mtime** matches the source file’s mtime (unless **`--force`**).

## Core rule (agents)

Do not read giant transcript files linearly.

1. Profile transcript files (`profile` or `awk -f ./line_histogram.awk`).
2. Bound the relevant time window (`bounds` or small scripts).
3. Extract only user-authored messages (`user-messages` or **`jq`**).
4. Redact sensitive local details.
5. Search the extracted messages for the requested topic.
6. Summarize with quoted evidence.

Use **`./line_histogram.awk`** or **`profile --awk ./line_histogram.awk`**. Verified patterns:

- `./line_histogram.awk <file>`
- `./line_histogram.awk -v mode=extract -v line=450 <file>`
- `./line_histogram.awk -v mode=extract -v start=100 -v end=200 <file>`

## Search and extract (workflows)

### 1) Resolve the discovery root

```sh
echo "${CURSOR_PROJECTS_ROOT:-${CURSOR_AGENT_TRANSCRIPTS_ROOT:-$HOME/.cursor/projects}}"
```

### 2) Profile before brute-force reading

```sh
./cursor_chat_history.py profile --awk ./line_histogram.awk
```

Or shell loop:

```sh
find "${CURSOR_PROJECTS_ROOT:-$HOME/.cursor/projects}" -path '*/agent-transcripts/*.jsonl' -type f | sort \
  | while read -r f; do
      echo "=== $f ==="
      awk -f ./line_histogram.awk "$f"
    done
```

### 3) Bound time per file

```sh
./cursor_chat_history.py bounds
```

### 4) Extract user-authored text

With **`jq`**:

```sh
jq -r '
  select(.role == "user" or .role == "human" or .type == "human")
  | .message.content[]?
  | select(.type == "text")
  | .text
' "$TRANSCRIPT"
```

With the script (path redaction similar to **`codex_chat_history`**):

```sh
./cursor_chat_history.py user-messages "$TRANSCRIPT"
```

### 5) Redact before share

Replace host-specific paths and usernames in anything you copy out (`<PATH>`, `<USER>` placeholders).

### 6) Assistant / tool usage (optional)

```sh
jq -r '
  select(.role == "assistant")
  | .message.content[]?
  | select(.type == "tool_use")
  | .name
' "$TRANSCRIPT"
```

### 7) Compaction / recap text

```sh
rg -n -i 'summary|compaction|previous conversation summary|compressed history' "$TRANSCRIPT"
```

## Topic forensic search (multi-step)

Use when the user asks for a **forensic reconstruction** of what they said about a topic across a time window (not a single grep).

1. **Extract user messages with timestamps** — parse timestamp-like fields from user lines only; sort; write JSONL with `iso_key`, `display_ts`, `text`, `transcript_hint` (redact absolute paths in published artifacts).
2. **Profile huge JSONL first** — `./line_histogram.awk` or `profile --awk`.
3. **Overlapping chunks for review** — split ordered messages into chunks of **N** with overlap **O**; record chunk index and ts range; mark chunks relevant / not relevant to the topic.
4. **Strict per-message filter** — programmatic keyword filter to reduce noise after chunk review.
5. **Dedupe and verbatim timeline** — dedupe on `(iso_key, full text)`; emit markdown with redacted `/home/...` → `/home/<USER>` in shared copies.
6. **Deliverables** — `extract_meta.json`, `user_messages_<window>.jsonl`, `chunk_manifest.json`, `verbatim_topic_messages.txt` or `FORENSIC_REPORT_*.md`, summary table.

## Anti-patterns

Do not:

- read the whole transcript end to end without narrowing first
- answer from memory when the transcript is available
- mix assistant statements into "what the user said"
- publish local usernames or absolute local paths
- confuse this with **Codex** `rollout-*.jsonl` tooling

## Completion standard

You are done when:

- the in-scope transcripts are identified from timestamps
- the user-only extract exists
- the relevant topic excerpts exist
- the summary cites evidence rather than recollection

## Retention

Cursor does not guarantee transcript retention forever; backups and pruning are operator concerns.

## Canonical source and releases

- **Repository:** https://github.com/simbo1905/cursor_chat_history  
- **Public gist** (mirrors this folder’s three files): https://gist.github.com/simbo1905/a023ec8cec4610f3f6f8878be95a4e49  

Portable bundle: download **SKILL.md**, **cursor_chat_history.py**, and **line_histogram.awk** from the gist or repo; use **`awk -f ./line_histogram.awk`** when not inside another project tree.

Further reading on the histogram tool: https://dev.to/simbo1905/line-histogram-the-file-profiler-you-didnt-know-you-needed-38oi

For smoke tests, **`git tag`**, and **gist** sync commands, see the **Release checklist** in the repo root **README.md**.

## Copyright

Skill text and tooling © 2026 LiveMore Capital https://www.livemorecapital.com (where not otherwise noted).
