"""CLI: python -m local_tool ingest [--outbox PATH] [--home PATH]

Defaults: outbox = $KOYU_RUNTIME_DIR/data-recordings, home = $KOYU_HOME
(the same home the store and server use; the workspace lives at <home>/workspace).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .store.ingest import sweep
from .store.projects import StoreCtx


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="local_tool")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="sweep the runtime outbox into the workspace store")
    runtime_dir = os.environ.get("KOYU_RUNTIME_DIR")
    ingest.add_argument("--outbox", type=Path,
                        default=Path(runtime_dir) / "data-recordings" if runtime_dir else None,
                        help="runtime outbox directory (default: $KOYU_RUNTIME_DIR/data-recordings)")
    ingest.add_argument("--home", type=Path,
                        default=os.environ.get("KOYU_HOME"),
                        help="store home directory (default: $KOYU_HOME)")
    args = parser.parse_args(argv)

    if args.outbox is None:
        parser.error("--outbox required (or set KOYU_RUNTIME_DIR)")
    if args.home is None:
        parser.error("--home required (or set KOYU_HOME)")

    results = sweep(StoreCtx(home=args.home), args.outbox)
    for r in results:
        print(f"[ingest] {r.bundle} -> {r.episode_id} ({r.manifest_id or 'unfiled'})")
    print(f"[ingest] {len(results)} episode(s) ingested")


if __name__ == "__main__":
    main()
