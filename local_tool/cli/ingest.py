"""koyu ingest — sweep a runtime outbox into the workspace store.

Runs against the store directly (a sweep is local, idempotent per bundle,
and useful before any server exists). The Datasets page's Ingest button is
the same sweep through the server's /api/ingest route.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..store.ingest import sweep
from ..store.projects import StoreCtx
from .common import die, resolve_home


def run(args) -> int:
    home = resolve_home(args.home)
    outbox = args.outbox
    if outbox is None:
        runtime_dir = os.environ.get("KOYU_RUNTIME_DIR")
        if not runtime_dir:
            die("no outbox: pass --outbox or set KOYU_RUNTIME_DIR")
        outbox = Path(runtime_dir) / "data-recordings"

    results = sweep(StoreCtx(home=home), Path(outbox))
    for r in results:
        print(f"[ingest] {r.bundle} -> {r.episode_id} ({r.manifest_id or 'unfiled'})")
    print(f"[ingest] {len(results)} episode(s) ingested")
    return 0
