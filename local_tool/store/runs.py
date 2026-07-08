from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from blake3 import blake3

from ..catalog import rebuild_catalog, resolve_entity_path
from ..ids import generate_id
from ..io import StoreError, normalize_temporal_kwargs, read_model, remove_path, write_model, write_text_atomic
from ..models import LocalRun, utc_now
from ..paths import folder_name, project_json, run_json, run_readme, runs_root
from .projects import StoreCtx, get_project, get_project_dir


def _validate_run_path(path: Path, run_id: str) -> bool:
    try:
        return path.is_dir() and read_model(run_json(path), LocalRun).id == run_id
    except Exception:
        return False


def get_run_dir(ctx: StoreCtx, run_id: str) -> Path:
    return resolve_entity_path(ctx.home, "runs", run_id, validator=_validate_run_path)


def get_run(ctx: StoreCtx, run_id: str) -> LocalRun:
    return read_model(run_json(get_run_dir(ctx, run_id)), LocalRun)


def _list_runs_under(parent_dir: Path) -> list[LocalRun]:
    results: list[LocalRun] = []
    nested = runs_root(parent_dir)
    if not nested.exists():
        return results
    for run_dir in sorted(nested.iterdir()):
        rj = run_json(run_dir)
        if run_dir.is_dir() and rj.exists():
            try:
                run = read_model(rj, LocalRun)
            except Exception:
                continue
            results.append(run)
            results.extend(_list_runs_under(run_dir))
    return results


def list_runs(ctx: StoreCtx, project_id: str) -> list[LocalRun]:
    project_dir = get_project_dir(ctx, project_id)
    return _list_runs_under(project_dir)


def create_run(
    ctx: StoreCtx,
    *,
    project_id: str,
    name: str,
    parent_id: str | None = None,
    manifest_ids: list[str] | None = None,
    run_id: str | None = None,
    created_at=None,
    updated_at=None,
) -> LocalRun:
    get_project(ctx, project_id)
    parent_dir = get_project_dir(ctx, project_id) if parent_id is None else get_run_dir(ctx, parent_id)
    if parent_id is not None:
        parent = get_run(ctx, parent_id)
        if parent.project_id != project_id:
            raise StoreError("Parent run must belong to same project", "CONFLICT")
    payload = normalize_temporal_kwargs(
        {
            "id": run_id or generate_id("run"),
            "project_id": project_id,
            "parent_id": parent_id,
            "name": name,
            "manifest_ids": list(dict.fromkeys(manifest_ids or [])),
            "created_at": created_at or utc_now(),
            "updated_at": updated_at or utc_now(),
        }
    )
    run = LocalRun(**payload)
    try:
        get_run(ctx, run.id)
    except StoreError as exc:
        if exc.code != "NOT_FOUND":
            raise
    else:
        raise StoreError(f"Run already exists: {run.id}", "CONFLICT")

    run_dir = runs_root(parent_dir) / folder_name(run.name, run.id)
    if run_dir.exists():
        raise StoreError(f"Run path already exists: {run_dir.name}", "CONFLICT")
    run_dir.mkdir(parents=True, exist_ok=True)
    runs_root(run_dir).mkdir(parents=True, exist_ok=True)
    write_model(run_json(run_dir), run)
    rebuild_catalog(ctx.home)
    return run


def _would_create_cycle(ctx: StoreCtx, run_id: str, parent_id: str | None) -> bool:
    current = parent_id
    while current is not None:
        if current == run_id:
            return True
        current = get_run(ctx, current).parent_id
    return False


def update_run(ctx: StoreCtx, run_id: str, **updates) -> LocalRun:
    run_dir = get_run_dir(ctx, run_id)
    run = get_run(ctx, run_id)
    # Nullable fields callers are allowed to explicitly clear (e.g. setting
    # parent_id=None to promote a run to top-level).
    nullable_fields = {"parent_id"}
    clean = {
        key: value
        for key, value in updates.items()
        if value is not None or key in nullable_fields
    }
    if not clean:
        raise StoreError("No fields to update", "CONFLICT")

    if "manifest_ids" in clean:
        clean["manifest_ids"] = list(dict.fromkeys(clean["manifest_ids"]))

    if "parent_id" in clean and clean["parent_id"] != run.parent_id:
        parent_id = clean["parent_id"]
        if parent_id is not None:
            parent = get_run(ctx, parent_id)
            if parent.project_id != run.project_id:
                raise StoreError("Parent run must belong to same project", "CONFLICT")
            if _would_create_cycle(ctx, run_id, parent_id):
                raise StoreError("Run reparent would create a cycle", "CONFLICT")
        old_parent_dir = get_project_dir(ctx, run.project_id) if run.parent_id is None else get_run_dir(ctx, run.parent_id)
        new_parent_dir = get_project_dir(ctx, run.project_id) if parent_id is None else get_run_dir(ctx, parent_id)
        destination = runs_root(new_parent_dir) / run_dir.name
        if destination.exists():
            raise StoreError("Destination run path already exists", "CONFLICT")
        run_dir.rename(destination)
        run_dir = destination

    clean.setdefault("updated_at", utc_now())
    clean = normalize_temporal_kwargs(clean)
    updated = run.model_copy(update=clean)

    if updated.name != run.name:
        new_dir = run_dir.parent / folder_name(updated.name, updated.id)
        run_dir.rename(new_dir)
        run_dir = new_dir

    write_model(run_json(run_dir), updated)
    rebuild_catalog(ctx.home)
    return updated


def delete_run(ctx: StoreCtx, run_id: str) -> None:
    run_dir = get_run_dir(ctx, run_id)
    run = get_run(ctx, run_id)
    from . import manifests

    for manifest_id in run.manifest_ids:
        try:
            manifest = manifests.get_manifest(ctx, manifest_id)
        except StoreError:
            continue
        if run_id in manifest.run_ids:
            manifests.update_manifest(
                ctx,
                manifest_id,
                run_ids=[value for value in manifest.run_ids if value != run_id],
            )
    remove_path(run_dir)
    rebuild_catalog(ctx.home)


def _iter_run_files(ctx: StoreCtx, run_id: str):
    run_dir = get_run_dir(ctx, run_id)
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "run.json":
            continue
        rel = path.relative_to(run_dir)
        if "runs" in rel.parts:
            continue
        yield run_dir, path


def list_run_files(ctx: StoreCtx, run_id: str) -> list[dict]:
    files: list[dict] = []
    for run_dir, path in _iter_run_files(ctx, run_id):
        rel = path.relative_to(run_dir)
        stat = path.stat()
        files.append(
            {
                "path": str(rel),
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "is_readme": rel.name == "README.md",
            }
        )
    return files


def run_file_listing(ctx: StoreCtx, run_id: str) -> dict[str, dict]:
    listing: dict[str, dict] = {}
    for run_dir, path in _iter_run_files(ctx, run_id):
        rel = path.relative_to(run_dir)
        stat = path.stat()
        listing[str(rel)] = {
            "size": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "is_readme": rel.name == "README.md",
        }
    return listing


def run_file_records(ctx: StoreCtx, run_id: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for run_dir, path in _iter_run_files(ctx, run_id):
        rel = path.relative_to(run_dir)
        stat = path.stat()
        records[str(rel)] = {
            "blake3": blake3(path.read_bytes()).hexdigest(),
            "size": stat.st_size,
            "r2_key": "",
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    return records


def run_has_readme(ctx: StoreCtx, run_id: str) -> bool:
    return run_readme(get_run_dir(ctx, run_id)).exists()


def run_file_count(ctx: StoreCtx, run_id: str) -> int:
    return len(list_run_files(ctx, run_id))


def get_run_file_path(ctx: StoreCtx, run_id: str, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise StoreError(f"Invalid run file path: {relative_path}", "CONFLICT")
    run_dir = get_run_dir(ctx, run_id)
    path = (run_dir / relative_path).resolve()
    if not path.is_file() or run_dir.resolve() not in path.parents:
        raise StoreError(f"Run file not found: {relative_path}", "NOT_FOUND")
    rel = path.relative_to(run_dir)
    if rel.name == "run.json" or "runs" in rel.parts:
        raise StoreError(f"Run file not found: {relative_path}", "NOT_FOUND")
    return path


def get_run_readme(ctx: StoreCtx, run_id: str) -> str:
    path = run_readme(get_run_dir(ctx, run_id))
    return path.read_text() if path.exists() else ""


def put_run_readme(ctx: StoreCtx, run_id: str, content: str) -> None:
    path = run_readme(get_run_dir(ctx, run_id))
    write_text_atomic(path, content)
