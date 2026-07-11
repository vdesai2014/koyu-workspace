"""Ingest API: arm an outbox folder, then sweep it on demand.

The armed folder is durable workspace state (<home>/.koyu/ingest.json), not
browser state — the UI, the CLI, and any agent all see the same ingest source.
The sweep itself is the store's existing ingest.sweep(); this route only adds
the where-from. A sweep is synchronous and idempotent per bundle: failures
stay in the outbox and are reported by the pending count.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...store.ingest import sweep
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["ingest"])


def _config_path(home: Path) -> Path:
    return home / ".koyu" / "ingest.json"


def _read_outbox(home: Path) -> Path | None:
    try:
        raw = json.loads(_config_path(home).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    outbox = raw.get("outbox")
    return Path(outbox).expanduser() if outbox else None


def _pending(outbox: Path | None) -> int:
    """Complete bundles waiting in the outbox (.tmp-* in-flight dirs excluded)."""
    if outbox is None or not outbox.is_dir():
        return 0
    return sum(
        1
        for path in outbox.iterdir()
        if path.is_dir() and not path.name.startswith(".tmp-") and (path / "episode.json").is_file()
    )


def _config_payload(outbox: Path | None) -> dict:
    return {
        "outbox": str(outbox) if outbox else None,
        "exists": bool(outbox and outbox.is_dir()),
        "pending": _pending(outbox),
    }


class IngestConfigBody(BaseModel):
    outbox: str


@router.get("/ingest/config")
def get_ingest_config(ctx: StoreCtx = Depends(get_ctx)):
    return _config_payload(_read_outbox(ctx.home))


@router.put("/ingest/config")
def put_ingest_config(body: IngestConfigBody, ctx: StoreCtx = Depends(get_ctx)):
    outbox = body.outbox.strip()
    if not outbox:
        raise HTTPException(status_code=400, detail="outbox path is required")
    path = _config_path(ctx.home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"outbox": outbox}, indent=2) + "\n")
    return _config_payload(Path(outbox).expanduser())


@router.post("/ingest")
def run_ingest(ctx: StoreCtx = Depends(get_ctx)):
    outbox = _read_outbox(ctx.home)
    if outbox is None:
        raise HTTPException(status_code=409, detail="No ingest folder armed — set one first.")
    if not outbox.is_dir():
        raise HTTPException(status_code=409, detail=f"Ingest folder does not exist: {outbox}")
    results = sweep(ctx, outbox)
    return {
        "outbox": str(outbox),
        "count": len(results),
        "ingested": [
            {"episode_id": r.episode_id, "manifest_id": r.manifest_id, "bundle": r.bundle}
            for r in results
        ],
        "pending": _pending(outbox),   # anything left behind failed; sweep logs why
    }
