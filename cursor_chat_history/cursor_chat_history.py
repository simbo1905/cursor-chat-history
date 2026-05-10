#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13.0,<3.14"
# dependencies = []
# ///
"""Cursor IDE agent transcripts under ~/.cursor/projects: backup, list, profile, bounds, user-messages."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PATH_RE = re.compile(r"(/[A-Za-z0-9._/@+~-]+)+")


def _projects_discovery_root() -> Path:
    raw = os.environ.get("CURSOR_PROJECTS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    raw = os.environ.get("CURSOR_AGENT_TRANSCRIPTS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".cursor" / "projects").expanduser().resolve()


def _default_backup_root() -> Path:
    env = os.environ.get("CURSOR_TRANSCRIPTS_BACKUP_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "icloud" / ".cursor" / "projects").expanduser().resolve()


def _read_gzip_mtime(path: Path) -> int | None:
    data = path.read_bytes()[:10]
    if len(data) < 10 or data[0:2] != b"\x1f\x8b":
        return None
    return int.from_bytes(data[4:8], "little")


def _should_skip_jsonl(src: Path, dst_gz: Path) -> bool:
    if not dst_gz.is_file():
        return False
    want = int(src.stat().st_mtime)
    got = _read_gzip_mtime(dst_gz)
    return got == want


def _path_is_agent_transcript_jsonl(path: Path) -> bool:
    return path.suffix == ".jsonl" and "agent-transcripts" in path.parts


def _iter_transcript_jsonl(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*.jsonl"):
        if "agent-transcripts" in p.parts:
            out.append(p)
    return sorted(out)


def _mtime_cutoff_seconds(since: str) -> float | None:
    since = since.strip().lower()
    if since in ("", "all", "*"):
        return None
    now = time.time()
    if since.endswith("d"):
        days = float(since[:-1] or "0")
        return now - days * 86400.0
    if since.endswith("h"):
        hours = float(since[:-1] or "0")
        return now - hours * 3600.0
    raise SystemExit(f"invalid --since {since!r}; use e.g. 1d or 48h")


def _event_timestamp(obj: dict) -> str | None:
    for key in ("timestamp", "created_at", "ts"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def cmd_backup(args: argparse.Namespace) -> None:
    src_root: Path = args.src.expanduser().resolve()
    dst_root: Path = args.dst.expanduser().resolve()
    if not src_root.is_dir():
        print(f"error: source directory missing: {src_root}", file=sys.stderr)
        sys.exit(1)

    n_gz = 0
    n_other = 0
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src_root)
        dst = dst_root / rel
        if _path_is_agent_transcript_jsonl(path):
            dst_gz = dst.with_suffix(path.suffix + ".gz")
            if not args.force and _should_skip_jsonl(path, dst_gz):
                continue
            n_gz += 1
            if args.dry_run:
                print(f"gz  {path} -> {dst_gz}")
                continue
            dst_gz.parent.mkdir(parents=True, exist_ok=True)
            mtime = int(path.stat().st_mtime)
            with path.open("rb") as raw:
                with gzip.GzipFile(
                    filename=str(dst_gz),
                    mode="wb",
                    compresslevel=9,
                    mtime=mtime,
                ) as gz:
                    shutil.copyfileobj(raw, gz)
            try:
                os.utime(dst_gz, (mtime, mtime))
            except OSError:
                pass
        else:
            n_other += 1
            if args.dry_run:
                print(f"cp  {path} -> {dst}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)

    verb = "would write" if args.dry_run else "wrote"
    print(
        f"{verb} {n_gz} agent-transcript gzip file(s), "
        f"{n_other} other file(s) -> {dst_root}",
    )


def cmd_list(args: argparse.Namespace) -> None:
    root: Path = args.src.expanduser().resolve()
    cutoff = _mtime_cutoff_seconds(args.since)
    paths = _iter_transcript_jsonl(root)
    for p in paths:
        if cutoff is not None and p.stat().st_mtime < cutoff:
            continue
        print(p)


def cmd_profile(args: argparse.Namespace) -> None:
    root: Path = args.src.expanduser().resolve()
    awk: Path | None = args.awk.expanduser().resolve() if args.awk else None
    if awk and not awk.is_file():
        print(f"error: awk script not found: {awk}", file=sys.stderr)
        sys.exit(1)

    cutoff = _mtime_cutoff_seconds(args.since)
    for path in _iter_transcript_jsonl(root):
        if cutoff is not None and path.stat().st_mtime < cutoff:
            continue
        print(f"=== {path} ===")
        if awk:
            subprocess.run(
                ["awk", "-f", str(awk), str(path)],
                check=False,
            )
        else:
            nbytes = path.stat().st_size
            nlines = 0
            with path.open("rb") as bf:
                for _ in bf:
                    nlines += 1
            print(f"(no --awk) size={nbytes} bytes lines={nlines}")


def _first_last_timestamps(path: Path) -> tuple[str | None, str | None]:
    first_ts: str | None = None
    last_ts: str | None = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            ts = _event_timestamp(obj)
            if ts is not None:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
    return first_ts, last_ts


def cmd_bounds(args: argparse.Namespace) -> None:
    root: Path = args.src.expanduser().resolve()
    cutoff = _mtime_cutoff_seconds(args.since)
    if args.glob:
        seen: list[Path] = []
        for g in args.glob:
            seen.extend(root.glob(g))
        paths = sorted(
            {
                p.resolve()
                for p in seen
                if p.is_file() and _path_is_agent_transcript_jsonl(p.resolve())
            },
        )
    else:
        paths = _iter_transcript_jsonl(root)
    for path in paths:
        if cutoff is not None and path.stat().st_mtime < cutoff:
            continue
        first_ts, last_ts = _first_last_timestamps(path)
        print(path)
        print(f"  FIRST: {first_ts}")
        print(f"  LAST:  {last_ts}")


def _redact(text: str) -> str:
    text = PATH_RE.sub("<PATH>", text)
    text = re.sub(r"/Users/[^/\s]+", "/Users/<USER>", text)
    text = re.sub(r"/home/[^/\s]+", "/home/<USER>", text)
    return text


def _is_user_event(obj: dict) -> bool:
    role = obj.get("role")
    if role == "user":
        return True
    if role == "human":
        return True
    return obj.get("type") == "human"


def cmd_user_messages(args: argparse.Namespace) -> None:
    path: Path = args.file.expanduser().resolve()
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        sys.exit(1)

    n = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if not _is_user_event(obj):
                continue
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        t = item.get("text")
                        if isinstance(t, str) and t:
                            n += 1
                            print(f"[MSG {n}]: {_redact(t)}")
            elif isinstance(content, str) and content:
                n += 1
                print(f"[MSG {n}]: {_redact(content)}")
    if n == 0:
        print("(no user role messages with text content found)", file=sys.stderr)


def main() -> None:
    src_help = (
        "Projects / tree root (default: $CURSOR_PROJECTS_ROOT, "
        "else $CURSOR_AGENT_TRANSCRIPTS_ROOT, else ~/.cursor/projects)"
    )
    parser = argparse.ArgumentParser(
        description=(
            "Cursor agent transcripts: backup (gzip mirror), list, profile, bounds, user-messages."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_b = sub.add_parser(
        "backup",
        help="Gzip mirror of tree; agent-transcripts *.jsonl compressed; default dest from env",
    )
    p_b.add_argument("--src", type=Path, default=_projects_discovery_root(), help=src_help)
    p_b.add_argument(
        "--dst",
        "--dest",
        type=Path,
        default=None,
        dest="dst",
        help=(
            "Backup root (default: $CURSOR_TRANSCRIPTS_BACKUP_ROOT "
            "or ~/icloud/.cursor/projects)"
        ),
    )
    p_b.add_argument("-n", "--dry-run", action="store_true")
    p_b.add_argument("-f", "--force", action="store_true")
    p_b.set_defaults(func=cmd_backup)

    p_l = sub.add_parser("list", help="List agent-transcript JSONL paths under --src")
    p_l.add_argument("--src", type=Path, default=_projects_discovery_root(), help=src_help)
    p_l.add_argument("--since", default="all", help="e.g. 1d, 48h, or all")
    p_l.set_defaults(func=cmd_list)

    p_p = sub.add_parser("profile", help="Profile each transcript (optional awk)")
    p_p.add_argument("--src", type=Path, default=_projects_discovery_root(), help=src_help)
    p_p.add_argument(
        "--awk",
        type=Path,
        default=None,
        help="Path to line_histogram.awk (beside this script in the repo)",
    )
    p_p.add_argument("--since", default="all")
    p_p.set_defaults(func=cmd_profile)

    p_x = sub.add_parser("bounds", help="First and last JSON timestamp per transcript")
    p_x.add_argument("--src", type=Path, default=_projects_discovery_root(), help=src_help)
    p_x.add_argument(
        "--glob",
        action="append",
        help="Optional glob(s) relative to --src (repeatable); default all transcripts",
    )
    p_x.add_argument("--since", default="all")
    p_x.set_defaults(func=cmd_bounds)

    p_u = sub.add_parser(
        "user-messages",
        help="Extract user text from one transcript (role user / human)",
    )
    p_u.add_argument("file", type=Path)
    p_u.set_defaults(func=cmd_user_messages)

    args = parser.parse_args()
    if args.cmd == "backup" and args.dst is None:
        args.dst = _default_backup_root()
    args.func(args)


if __name__ == "__main__":
    main()
