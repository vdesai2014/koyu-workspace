"""Shared plumbing for the workspace CLI: home resolution, server discovery.

The workspace server is the store's single writer while it runs, so sync
verbs go through its HTTP API rather than driving the engine directly. The
server's address is discovered from the state file it writes at startup
(<home>/.koyu/run/local_tool.json) — the file exists iff a server owns the
store.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def die(message: str) -> "None":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def resolve_home(explicit: Path | None) -> Path:
    home = explicit or os.environ.get("KOYU_HOME")
    if not home:
        die("no workspace home: pass --home or set KOYU_HOME")
    return Path(home).resolve()


def server_url(home: Path) -> str:
    state = home / ".koyu" / "run" / "local_tool.json"
    try:
        payload = json.loads(state.read_text())
        return payload["url"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        die(f"no workspace server running for {home} (no state file at {state}).\n"
            "  start it first:  uvicorn local_tool.server.app:app  (with KOYU_HOME set)")


def progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def fmt_bytes(value) -> str:
    n = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"
