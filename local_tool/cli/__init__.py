"""The workspace's verbs, dispatch-only (ported from the original os/cli).

    ingest      sweep a runtime outbox into the store (direct)
    clone       clone a cloud project (code + runs + weights) into the store
    sync-push   push a local entity (project/run/manifest) to the cloud
    sync-pull   pull a cloud entity into the local store

All four plug into the `koyu` umbrella via the koyu.plugins entry-point
group; `python -m local_tool <verb>` works identically. Sync verbs talk to
the running workspace server (the store's single writer); `koyu clone` is
anonymous for public projects, sync-push always needs KOYU_TOKEN.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _add_home(p: argparse.ArgumentParser) -> None:
    p.add_argument("--home", type=Path, default=None,
                   help="workspace home (default: $KOYU_HOME)")


def _add_cloud(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api", default=None, help="cloud API base (default: koyu.dev)")
    p.add_argument("--token", default=None,
                   help="bearer token (default: $KOYU_TOKEN)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="koyu", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="sweep the runtime outbox into the workspace store")
    p.add_argument("--outbox", type=Path, default=None,
                   help="outbox directory (default: $KOYU_RUNTIME_DIR/data-recordings)")
    _add_home(p)

    p = sub.add_parser("clone", help="clone a cloud project (code + runs + weights) into the store")
    p.add_argument("ref", help="proj_<32hex> or a koyu.dev URL containing it")
    p.add_argument("--output", help="write full sync result JSON to this path")
    p.add_argument("--json", action="store_true", help="print full sync result JSON")
    _add_home(p)
    _add_cloud(p)

    for verb, help_text in (("sync-push", "push a local entity to the cloud"),
                            ("sync-pull", "pull a cloud entity into the local store")):
        p = sub.add_parser(verb, help=help_text)
        p.add_argument("entity_type", choices=("project", "run", "manifest"))
        p.add_argument("entity_id")
        p.add_argument("--include-manifests", action="store_true")
        p.add_argument("--include-descendants", action="store_true")
        p.add_argument("--output", help="write full sync result JSON to this path")
        p.add_argument("--json", action="store_true", help="print full sync result JSON")
        _add_home(p)
        _add_cloud(p)

    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        from . import ingest
        return ingest.run(args)
    from . import sync_cmd
    return sync_cmd.run(args)
