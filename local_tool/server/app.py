from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import get_ctx, init_store
from .routes import episodes, manifests, projects, runs, sync


def _state_file_path(home: Path) -> Path:
    return home / ".koyu" / "run" / "local_tool.json"


def _write_state_file(home: Path) -> Path | None:
    """Atomically write .koyu/run/local_tool.json with pid/port/url/started_at.

    CLI reads this to discover local_tool's actual listening port.
    Env vars LOCAL_TOOL_HOST/PORT should be set by whoever launches
    uvicorn (typically `koyu up`); otherwise falls back to 127.0.0.1:8000
    with a printed warning.
    """
    host = os.environ.get("LOCAL_TOOL_HOST", "127.0.0.1")
    port_raw = os.environ.get("LOCAL_TOOL_PORT")
    if port_raw is None:
        print(
            "[local_tool] WARNING: LOCAL_TOOL_PORT unset; state file "
            "will claim port 8000 (set this env var at launch to match your "
            "--port flag)"
        )
    try:
        port = int(port_raw) if port_raw else 8000
    except ValueError:
        print(f"[local_tool] WARNING: invalid LOCAL_TOOL_PORT={port_raw!r}; using 8000")
        port = 8000

    path = _state_file_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}",
        "home": str(home),
        "started_at": time.time(),
    }
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx = init_store()
    print(f"[local_tool] home={ctx.home}")
    state_path = _write_state_file(ctx.home)
    if state_path is not None:
        print(f"[local_tool] state: {state_path}")
    try:
        yield
    finally:
        if state_path is not None:
            try:
                state_path.unlink(missing_ok=True)
            except OSError:
                pass


app = FastAPI(title="Koyu Local Tool", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(manifests.router, prefix="/api")
app.include_router(episodes.router, prefix="/api")
app.include_router(sync.router, prefix="/api")


@app.get("/api/health")
def health():
    ctx = get_ctx()
    return {
        "status": "ok",
        "service": "koyu-local-tool",
        "pid": os.getpid(),
        "home": str(ctx.home),
    }
