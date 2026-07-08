from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from blake3 import blake3

from ..catalog import load_catalog, rebuild_catalog, resolve_entity_path, save_catalog
from ..ids import generate_id
from ..io import StoreError, normalize_temporal_kwargs, read_model, remove_path, write_model, write_text_atomic
from ..models import LocalProject, utc_now
from ..paths import episodes_root, folder_name, manifests_root, project_json, project_readme, projects_root, runs_root


@dataclass(frozen=True)
class StoreCtx:
    home: Path


def ensure_store_roots(ctx: StoreCtx) -> None:
    projects_root(ctx.home).mkdir(parents=True, exist_ok=True)
    manifests_root(ctx.home).mkdir(parents=True, exist_ok=True)
    episodes_root(ctx.home).mkdir(parents=True, exist_ok=True)


def list_projects(ctx: StoreCtx, *, newest_first: bool = True) -> list[LocalProject]:
    ensure_store_roots(ctx)
    root = projects_root(ctx.home)
    projects: list[LocalProject] = []
    for project_dir in sorted(root.iterdir()):
        if project_dir.name in {"manifests", "episodes"}:
            continue
        pj = project_json(project_dir)
        if project_dir.is_dir() and pj.exists():
            try:
                projects.append(read_model(pj, LocalProject))
            except Exception:
                continue
    projects.sort(key=lambda project: (project.updated_at, project.id), reverse=newest_first)
    return projects


def create_project(
    ctx: StoreCtx,
    *,
    name: str,
    description: str | None = None,
    tags: list[str] | None = None,
    is_public: bool = False,
    cloned_source_project_id: str | None = None,
    project_id: str | None = None,
    created_at=None,
    updated_at=None,
) -> LocalProject:
    ensure_store_roots(ctx)
    payload = normalize_temporal_kwargs(
        {
            "id": project_id or generate_id("proj"),
            "name": name,
            "description": description,
            "tags": tags or [],
            "is_public": is_public,
            "cloned_source_project_id": cloned_source_project_id,
            "created_at": created_at or utc_now(),
            "updated_at": updated_at or utc_now(),
        }
    )
    if payload["cloned_source_project_id"] == payload["id"]:
        raise StoreError("Project cannot be cloned from itself", "CONFLICT")
    project = LocalProject(**payload)
    try:
        get_project(ctx, project.id)
    except StoreError as exc:
        if exc.code != "NOT_FOUND":
            raise
    else:
        raise StoreError(f"Project already exists: {project.id}", "CONFLICT")

    project_dir = projects_root(ctx.home) / folder_name(project.name, project.id)
    if project_dir.exists():
        raise StoreError(f"Project path already exists: {project_dir.name}", "CONFLICT")
    project_dir.mkdir(parents=True, exist_ok=True)
    runs_root(project_dir).mkdir(parents=True, exist_ok=True)
    write_model(project_json(project_dir), project)
    catalog = load_catalog(ctx.home)
    catalog["projects"][project.id] = str(project_dir.relative_to(ctx.home))
    save_catalog(ctx.home, catalog)
    return project


def _validate_project_path(path: Path, project_id: str) -> bool:
    try:
        return path.is_dir() and read_model(project_json(path), LocalProject).id == project_id
    except Exception:
        return False


def get_project_dir(ctx: StoreCtx, project_id: str) -> Path:
    return resolve_entity_path(
        ctx.home,
        "projects",
        project_id,
        validator=_validate_project_path,
    )


def get_project(ctx: StoreCtx, project_id: str) -> LocalProject:
    return read_model(project_json(get_project_dir(ctx, project_id)), LocalProject)


def update_project(ctx: StoreCtx, project_id: str, **updates) -> LocalProject:
    project_dir = get_project_dir(ctx, project_id)
    project = get_project(ctx, project_id)
    # Nullable fields callers are allowed to explicitly clear via PATCH.
    nullable_fields = {"description", "cloned_source_project_id"}
    clean = {
        key: value
        for key, value in updates.items()
        if value is not None or key in nullable_fields
    }
    if not clean:
        raise StoreError("No fields to update", "CONFLICT")
    if clean.get("cloned_source_project_id") == project.id:
        raise StoreError("Project cannot be cloned from itself", "CONFLICT")
    clean.setdefault("updated_at", utc_now())
    clean = normalize_temporal_kwargs(clean)
    updated = project.model_copy(update=clean)
    if updated.name != project.name:
        new_dir = projects_root(ctx.home) / folder_name(updated.name, updated.id)
        project_dir.rename(new_dir)
        project_dir = new_dir
    write_model(project_json(project_dir), updated)
    rebuild_catalog(ctx.home)
    return updated


def delete_project(ctx: StoreCtx, project_id: str) -> None:
    project_dir = get_project_dir(ctx, project_id)
    from . import manifests, runs

    for run in runs.list_runs(ctx, project_id):
        for manifest_id in run.manifest_ids:
            try:
                manifest = manifests.get_manifest(ctx, manifest_id)
            except StoreError:
                continue
            if run.id in manifest.run_ids:
                manifests.update_manifest(
                    ctx,
                    manifest_id,
                    run_ids=[value for value in manifest.run_ids if value != run.id],
                )
    remove_path(project_dir)
    rebuild_catalog(ctx.home)


def _iter_project_files(ctx: StoreCtx, project_id: str):
    project_dir = get_project_dir(ctx, project_id)
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "project.json":
            continue
        if "runs" in path.relative_to(project_dir).parts:
            continue
        yield project_dir, path


def list_project_files(ctx: StoreCtx, project_id: str) -> list[dict]:
    files: list[dict] = []
    for project_dir, path in _iter_project_files(ctx, project_id):
        rel = path.relative_to(project_dir)
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


def project_file_listing(ctx: StoreCtx, project_id: str) -> dict[str, dict]:
    listing: dict[str, dict] = {}
    for project_dir, path in _iter_project_files(ctx, project_id):
        rel = path.relative_to(project_dir)
        stat = path.stat()
        listing[str(rel)] = {
            "size": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "is_readme": rel.name == "README.md",
        }
    return listing


def project_file_records(ctx: StoreCtx, project_id: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for project_dir, path in _iter_project_files(ctx, project_id):
        rel = path.relative_to(project_dir)
        stat = path.stat()
        records[str(rel)] = {
            "blake3": blake3(path.read_bytes()).hexdigest(),
            "size": stat.st_size,
            "r2_key": "",
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    return records


def project_has_readme(ctx: StoreCtx, project_id: str) -> bool:
    return project_readme(get_project_dir(ctx, project_id)).exists()


def project_file_count(ctx: StoreCtx, project_id: str) -> int:
    return len(list_project_files(ctx, project_id))


def get_project_file_path(ctx: StoreCtx, project_id: str, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise StoreError(f"Invalid project file path: {relative_path}", "CONFLICT")
    project_dir = get_project_dir(ctx, project_id)
    path = (project_dir / relative_path).resolve()
    if not path.is_file() or project_dir.resolve() not in path.parents:
        raise StoreError(f"Project file not found: {relative_path}", "NOT_FOUND")
    rel = path.relative_to(project_dir)
    if rel.name == "project.json" or "runs" in rel.parts:
        raise StoreError(f"Project file not found: {relative_path}", "NOT_FOUND")
    return path


def get_project_readme(ctx: StoreCtx, project_id: str) -> str:
    path = project_readme(get_project_dir(ctx, project_id))
    return path.read_text() if path.exists() else ""


def put_project_readme(ctx: StoreCtx, project_id: str, content: str) -> None:
    path = project_readme(get_project_dir(ctx, project_id))
    write_text_atomic(path, content)
