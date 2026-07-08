from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from blake3 import blake3

from ..catalog import rebuild_catalog, resolve_entity_path
from ..ids import generate_id
from ..io import StoreError, normalize_temporal_kwargs, read_model, write_model
from ..models import LocalEpisode, utc_now
from ..paths import episode_dir, episode_json, episodes_root
from .projects import StoreCtx, ensure_store_roots


def _validate_episode_path(path: Path, episode_id: str) -> bool:
    try:
        return path.is_dir() and read_model(episode_json(path), LocalEpisode).id == episode_id
    except Exception:
        return False


def get_episode_dir(ctx: StoreCtx, episode_id: str) -> Path:
    ensure_store_roots(ctx)
    return resolve_entity_path(ctx.home, "episodes", episode_id, validator=_validate_episode_path)


def get_episode(ctx: StoreCtx, episode_id: str) -> LocalEpisode:
    return read_model(episode_json(get_episode_dir(ctx, episode_id)), LocalEpisode)


def _scan_episode_files(root: Path) -> tuple[dict[str, dict], int]:
    files: dict[str, dict] = {}
    size_bytes = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == "episode.json":
            continue
        stat = path.stat()
        size_bytes += stat.st_size
        files[str(rel)] = {
            "blake3": blake3(path.read_bytes()).hexdigest(),
            "size": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    return files, size_bytes


def create_episode(
    ctx: StoreCtx,
    *,
    length: int,
    task: str | None = None,
    task_description: str | None = None,
    features: dict | None = None,
    collection_mode: str | None = None,
    source_project_id: str | None = None,
    source_run_id: str | None = None,
    source_checkpoint: str | None = None,
    policy_name: str | None = None,
    reward: float | None = None,
    files: dict | None = None,
    size_bytes: int | None = None,
    episode_id: str | None = None,
    created_at=None,
) -> LocalEpisode:
    ensure_store_roots(ctx)
    payload = normalize_temporal_kwargs(
        {
            "id": episode_id or generate_id("ep"),
            "length": length,
            "task": task,
            "task_description": task_description,
            "features": features or {},
            "files": files or {},
            "size_bytes": size_bytes or 0,
            "manifest_ids": [],
            "collection_mode": collection_mode,
            "source_project_id": source_project_id,
            "source_run_id": source_run_id,
            "source_checkpoint": source_checkpoint,
            "policy_name": policy_name,
            "reward": reward,
            "created_at": created_at or utc_now(),
        }
    )
    episode = LocalEpisode(**payload)
    root = episode_dir(episodes_root(ctx.home), episode.id)
    root.mkdir(parents=True, exist_ok=True)
    if not episode.files or not episode.size_bytes:
        scanned_files, scanned_size = _scan_episode_files(root)
        episode = episode.model_copy(update={
            "files": episode.files or scanned_files,
            "size_bytes": episode.size_bytes or scanned_size,
        })
    write_model(episode_json(root), episode)
    rebuild_catalog(ctx.home)
    return episode


def refresh_episode_metadata(ctx: StoreCtx, episode_id: str) -> LocalEpisode:
    root = get_episode_dir(ctx, episode_id)
    episode = get_episode(ctx, episode_id)
    files, size_bytes = _scan_episode_files(root)
    refreshed = episode.model_copy(update={"files": files, "size_bytes": size_bytes})
    write_model(episode_json(root), refreshed)
    rebuild_catalog(ctx.home)
    return refreshed


def update_episode(ctx: StoreCtx, episode_id: str, **updates) -> LocalEpisode:
    episode = get_episode(ctx, episode_id)
    # Nullable fields the PATCH route is allowed to unset (e.g. reward -> null
    # when a user un-rates an episode). The bare `is not None` filter used
    # elsewhere would silently drop the null.
    nullable_fields = {"reward", "task", "task_description"}
    clean = {
        key: value
        for key, value in updates.items()
        if value is not None or key in nullable_fields
    }
    if not clean:
        raise StoreError("No fields to update", "CONFLICT")
    clean = normalize_temporal_kwargs(clean)
    updated = episode.model_copy(update=clean)
    write_model(episode_json(get_episode_dir(ctx, episode_id)), updated)
    rebuild_catalog(ctx.home)
    return updated


def get_episode_file_path(ctx: StoreCtx, episode_id: str, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise StoreError(f"Invalid episode file path: {relative_path}", "CONFLICT")
    root = get_episode_dir(ctx, episode_id)
    path = (root / relative_path).resolve()
    if not path.is_file() or root.resolve() not in path.parents:
        raise StoreError(f"Episode file not found: {relative_path}", "NOT_FOUND")
    if path.name == "episode.json":
        raise StoreError(f"Episode file not found: {relative_path}", "NOT_FOUND")
    return path
