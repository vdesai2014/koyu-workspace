from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from ..io import write_json_atomic
from .models import SyncPlan, SyncRequest

TERMINAL_SYNC_JOB_STATUSES = {"succeeded", "failed"}


def _now() -> float:
    return time.time()


def _request_dict(request: SyncRequest) -> dict[str, Any]:
    return {
        "operation": request.operation,
        "entity_type": request.entity_type,
        "entity_id": request.entity_id,
        "include_manifests": request.include_manifests,
        "include_descendants": request.include_descendants,
        "dry_run": request.dry_run,
    }


def _job_id() -> str:
    return f"sync_{uuid.uuid4().hex}"


def sync_jobs_dir(home: Path) -> Path:
    return home / ".koyu" / "run" / "sync"


def validate_sync_job_id(job_id: str) -> str:
    if not job_id.startswith("sync_"):
        raise ValueError("sync job_id must start with sync_")
    suffix = job_id[len("sync_"):]
    if not suffix or any(ch not in "0123456789abcdef" for ch in suffix):
        raise ValueError("sync job_id must be sync_<hex>")
    return job_id


def read_sync_job(home: Path, job_id: str) -> dict[str, Any] | None:
    job_id = validate_sync_job_id(job_id)
    path = sync_jobs_dir(home) / f"{job_id}.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except (FileNotFoundError, OSError, ValueError):
        return None


def list_sync_jobs(home: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    job_dir = sync_jobs_dir(home)
    if not job_dir.is_dir():
        return jobs
    for path in sorted(job_dir.glob("sync_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                jobs.append(payload)
        except (OSError, ValueError):
            continue
        if len(jobs) >= limit:
            break
    return jobs


def delete_sync_job(home: Path, job_id: str) -> Literal["deleted", "not_found", "not_terminal"]:
    job_id = validate_sync_job_id(job_id)
    payload = read_sync_job(home, job_id)
    if payload is None:
        return "not_found"
    if payload.get("status") not in TERMINAL_SYNC_JOB_STATUSES:
        return "not_terminal"
    path = sync_jobs_dir(home) / f"{job_id}.json"
    try:
        path.unlink()
    except FileNotFoundError:
        return "not_found"
    return "deleted"


class SyncProgressReporter:
    """Best-effort side channel for sync observability.

    Implementations must not raise into the sync engine. Progress is never a
    correctness input; it only records what planning/execution observed.
    """

    job_id: str | None = None
    path: Path | None = None

    def planning(self) -> None:
        pass

    def planned(self, plan: SyncPlan) -> None:
        pass

    def execution_started(self) -> None:
        pass

    def event(self, phase: str, status: str, message: str | None = None, **data: Any) -> None:
        pass

    def finish(self, result: dict[str, Any]) -> None:
        pass

    def fail(self, error: BaseException | str) -> None:
        pass

    def ref(self) -> dict[str, Any] | None:
        return None


class NoopSyncProgressReporter(SyncProgressReporter):
    pass


class FileSyncProgressReporter(SyncProgressReporter):
    def __init__(
        self,
        *,
        home: Path,
        request: SyncRequest,
        job_id: str | None = None,
        max_events: int = 300,
    ):
        self.home = home
        self.job_id = validate_sync_job_id(job_id) if job_id else _job_id()
        self.path = sync_jobs_dir(home) / f"{self.job_id}.json"
        self.max_events = max_events
        now = _now()
        self._payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": "created",
            "request": _request_dict(request),
            "created_at": now,
            "updated_at": now,
            "plan": None,
            "execute": {
                "started_at": None,
                "updated_at": None,
                "events": [],
                "counters": {
                    "metadata_done": 0,
                    "files_done": 0,
                    "bytes_done": 0,
                    "associations_done": 0,
                },
            },
            "result": None,
            "error": None,
        }
        self._write()

    def planning(self) -> None:
        self._payload["status"] = "planning"
        self._touch()
        self._write()

    def planned(self, plan: SyncPlan) -> None:
        summary = plan.summary()
        file_bytes = sum(max(0, int(action.size)) for action in plan.file_actions)
        self._payload["plan"] = {
            "created_at": _now(),
            "summary": {
                **summary["planned"],
                "file_bytes": file_bytes,
            },
            "scope": summary["scope"],
            "warnings": summary["warnings"],
            "id_remaps": summary["id_remaps"],
            "required_id_remaps": summary["required_id_remaps"],
        }
        self._payload["status"] = "planned"
        self._touch()
        self._write()

    def execution_started(self) -> None:
        now = _now()
        self._payload["status"] = "running"
        self._payload["execute"]["started_at"] = self._payload["execute"]["started_at"] or now
        self._payload["execute"]["updated_at"] = now
        self._touch(now)
        self._write()

    def event(self, phase: str, status: str, message: str | None = None, **data: Any) -> None:
        entry = {
            "t": _now(),
            "phase": phase,
            "status": status,
        }
        if message:
            entry["message"] = message
        entry.update(data)
        events = self._payload["execute"]["events"]
        events.append(entry)
        if len(events) > self.max_events:
            del events[: len(events) - self.max_events]
        if status in {"done", "skipped"}:
            counters = self._payload["execute"]["counters"]
            if phase == "metadata":
                counters["metadata_done"] += 1
            elif phase == "file":
                counters["files_done"] += 1
                counters["bytes_done"] += max(0, int(data.get("size") or 0))
            elif phase == "link":
                counters["associations_done"] += 1
        now = entry["t"]
        self._payload["execute"]["updated_at"] = now
        self._touch(now)
        self._write()

    def finish(self, result: dict[str, Any]) -> None:
        self._payload["status"] = "succeeded"
        self._payload["result"] = result
        self._payload["error"] = None
        self._touch()
        self._write()

    def fail(self, error: BaseException | str) -> None:
        self._payload["status"] = "failed"
        self._payload["error"] = str(error)
        self._touch()
        self._write()

    def ref(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "path": str(self.path),
        }

    def _touch(self, now: float | None = None) -> None:
        self._payload["updated_at"] = _now() if now is None else now

    def _write(self) -> None:
        try:
            write_json_atomic(self.path, self._payload)
        except Exception:
            # Progress is observability only; never fail sync because the
            # side-channel cannot be written.
            pass
