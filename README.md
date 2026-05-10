# cursor-chat-history

> A **SKILL.md** plus a **`uv run --script`** helper to **back up**, **list**, and **inspect** Cursor IDE **agent transcript** JSONL under **`~/.cursor/projects/.../agent-transcripts/`** — gzip mirrors that preserve the tree, optional line-size histograms, and user-message extraction. This is **not** Codex CLI session rollouts (`rollout-*.jsonl`); see [codex-chat-history](https://github.com/simbo1905/codex-chat-history) for that.

## TL;DR

Jump to [Install](#install), or fetch **SKILL.md** alone:

```bash
mkdir -p ~/.cursor/skills/cursor_chat_history && \
  curl -fsSL https://raw.githubusercontent.com/simbo1905/cursor-chat-history/main/cursor_chat_history/SKILL.md \
  -o ~/.cursor/skills/cursor_chat_history/SKILL.md
```

---

## What lives on disk

Cursor stores append-only **transcript** JSONL files under each project, typically:

```text
~/.cursor/projects/<project-id>/agent-transcripts/<uuid>.jsonl
```

(or similar layouts where the path segment **`agent-transcripts`** appears).

**Defaults (overridable; see [`cursor_chat_history/SKILL.md`](cursor_chat_history/SKILL.md)):**

- **`$CURSOR_PROJECTS_ROOT`** — discovery root; if unset, **`$CURSOR_AGENT_TRANSCRIPTS_ROOT`**, then **`~/.cursor/projects`**.
- **`$CURSOR_TRANSCRIPTS_BACKUP_ROOT`** — default destination for **`backup`** (gzip mirror): **`~/icloud/.cursor/projects`**.

Bundled in **`cursor_chat_history/`**:

| File | Role |
|------|------|
| **`SKILL.md`** | Skill instructions for agents |
| **`cursor_chat_history.py`** | `backup`, `list`, `profile`, `bounds`, `user-messages` (Python 3.13.x via PEP 723) |
| **`line_histogram.awk`** | Optional histograms / line slices for huge JSONL |

**Repo (canonical):** [github.com/simbo1905/cursor-chat-history](https://github.com/simbo1905/cursor-chat-history)  
**Gist (same three files):** [gist.github.com/simbo1905/a023ec8cec4610f3f6f8878be95a4e49](https://gist.github.com/simbo1905/a023ec8cec4610f3f6f8878be95a4e49)

## Install

**Cursor / personal skills dir (example):**

```bash
mkdir -p ~/.cursor/skills
git clone https://github.com/simbo1905/cursor-chat-history.git ~/.cursor/skills/cursor_chat_history
```

**Codex CLI / Claude Code:** same layout works under `~/.codex/skills` or `~/.claude/skills` if you want the same skill tree there.

Then:

```bash
chmod +x ~/.cursor/skills/cursor_chat_history/cursor_chat_history/cursor_chat_history.py
~/.cursor/skills/cursor_chat_history/cursor_chat_history/cursor_chat_history.py --help
```

## Smoke test (non-destructive)

Only **reads** `~/.cursor/projects` (or **`--src`**). Writes to a **temp** tree.

```bash
PY=/path/to/cursor_chat_history/cursor_chat_history/cursor_chat_history.py
DEST=$(mktemp -d)
uv run --script "$PY" backup --dry-run --dest "$DEST"
uv run --script "$PY" backup --dest "$DEST"
uv run --script "$PY" backup --dest "$DEST"   # expect: 0 new agent-transcript gzip writes (skip by mtime)
# Optional integrity (pick one source JSONL under agent-transcripts):
# R=$(find "$HOME/.cursor/projects" -path '*/agent-transcripts/*.jsonl' -type f -print -quit)
# REL=${R#"$HOME/.cursor/projects/"}
# gunzip -c "$DEST/$REL.gz" | diff -q - "$R" && echo OK
rm -rf "$DEST"
```

## Release checklist

1. On **`main`**, run the smoke test when `~/.cursor/projects` exists; optionally **`gunzip -c` … `diff`** one transcript **`.jsonl`** as above.
2. **Tag** if you want a named snapshot: **`git tag v0.x.y && git push origin v0.x.y`** (optional for a skill repo).
3. **Sync the public gist** from **`cursor_chat_history/`** on **`main`**:

   ```bash
   D=cursor_chat_history
   GIST=a023ec8cec4610f3f6f8878be95a4e49
   gh gist edit "$GIST" --filename SKILL.md "$D/SKILL.md"
   gh gist edit "$GIST" --filename line_histogram.awk "$D/line_histogram.awk"
   gh gist edit "$GIST" --filename cursor_chat_history.py "$D/cursor_chat_history.py"
   gh api -X PATCH "gists/$GIST" \
     -f description='Cursor Chat History: SKILL + cursor_chat_history.py + line_histogram.awk (mirrors https://github.com/simbo1905/cursor-chat-history)'
   ```

4. Refresh **README** / **SKILL.md** if behavior or defaults changed.

## Copyright

Skill text and tooling © 2026 LiveMore Capital [livemorecapital.com](https://www.livemorecapital.com) (where not otherwise noted).
