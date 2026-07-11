"""koyu clone / sync-push / sync-pull — CLI wrappers over the sync engine,
via the workspace server (ported from the original os/cli/sync_cmd.py).

The `sync-` prefix exists because plain push/pull belong to koyu-cli's core
(raw file transfer). These verbs are different animals: identity-bearing
entity sync between the local store and the cloud.

Progress: the server runs the sync as a background job and journals it;
we poll and print. Falls back to one blocking execute call if the jobs
endpoint is unavailable.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from .common import die, fmt_bytes, progress, resolve_home, server_url

_PROJ_RE = re.compile(r"proj_[0-9a-f]{32}")


def _post(url: str, path: str, body: dict, timeout: float):
    try:
        resp = httpx.post(f"{url}{path}", json=body, timeout=timeout)
    except httpx.RequestError as exc:
        die(f"workspace server unreachable at {url}: {exc}")
    return resp


def _detail(resp) -> str:
    try:
        return resp.json().get("detail", resp.text)
    except ValueError:
        return resp.text


def _job_line(job: dict) -> str:
    summary = (job.get("plan") or {}).get("summary") or {}
    counters = (job.get("execute") or {}).get("counters") or {}
    events = (job.get("execute") or {}).get("events") or []
    latest = (events[-1] if events else {}).get("message") or job.get("status")
    total = int(summary.get("file_actions") or 0)
    if total:
        return (f"{job.get('status')} files {int(counters.get('files_done') or 0)}/{total} "
                f"{fmt_bytes(counters.get('bytes_done'))}/{fmt_bytes(summary.get('file_bytes'))} "
                f"— {latest}")
    return f"{job.get('status')} — {latest}"


def _wait_job(url: str, job_id: str, quiet: bool) -> dict:
    last = None
    while True:
        resp = httpx.get(f"{url}/api/sync/jobs/{job_id}", timeout=10.0)
        if resp.status_code >= 400:
            die(f"sync job poll failed ({resp.status_code}): {_detail(resp)}")
        job = resp.json()
        line = _job_line(job)
        if not quiet and line != last:
            progress(line)
            last = line
        if job.get("status") == "succeeded":
            return job.get("result") or {"success": True}
        if job.get("status") == "failed":
            die(f"sync job failed: {job.get('error') or 'unknown error'}")
        time.sleep(1.0)


def run(args) -> int:
    home = resolve_home(args.home)
    url = server_url(home)
    quiet = bool(getattr(args, "json", False))
    token = getattr(args, "token", None) or os.environ.get("KOYU_TOKEN")

    if args.cmd == "clone":
        match = _PROJ_RE.search(args.ref)
        if not match:
            die(f"could not find a proj_<32hex> id in {args.ref!r}")
        body = {"operation": "clone", "entity_type": "project", "entity_id": match.group(0)}
        if not quiet:
            progress(f"cloning {match.group(0)}")
    else:
        op = {"sync-push": "push", "sync-pull": "pull"}[args.cmd]
        body = {
            "operation": op,
            "entity_type": args.entity_type,
            "entity_id": args.entity_id,
            "include_manifests": bool(args.include_manifests),
            "include_descendants": bool(args.include_descendants),
        }
        if not quiet:
            progress(f"{op}ing {args.entity_type} {args.entity_id}")
    if token:
        body["bearer_token"] = token
    if getattr(args, "api", None):
        body["cloud_api_base"] = args.api

    resp = _post(url, "/api/sync/jobs", body, timeout=10.0)
    if resp.status_code == 404:
        if not quiet:
            progress("jobs endpoint unavailable; falling back to blocking execute")
        resp = _post(url, "/api/sync/execute", body, timeout=1800.0)
        if resp.status_code >= 400:
            die(f"sync failed ({resp.status_code}): {_detail(resp)}")
        result = resp.json()
    else:
        if resp.status_code >= 400:
            die(f"sync job failed to start ({resp.status_code}): {_detail(resp)}")
        job_id = resp.json()["job_id"]
        if not quiet:
            progress(f"sync job {job_id}")
        result = _wait_job(url, job_id, quiet)

    if getattr(args, "output", None):
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        if not quiet:
            progress(f"wrote sync result: {out}")
    if quiet:
        print(json.dumps(result, indent=2, default=str))
        return 0

    for key in ("success", "created", "patched", "uploaded", "copied", "id_remaps", "warnings"):
        if result.get(key):
            print(f"{key}: {json.dumps(result[key], default=str)}")
    errors = result.get("errors") or []
    if errors:
        print(f"errors: {json.dumps(errors, default=str)}")
        return 1
    return 0
