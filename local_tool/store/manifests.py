from __future__ import annotations

from pathlib import Path

from ..catalog import rebuild_catalog, resolve_entity_path
from ..ids import generate_id
from ..io import StoreError, normalize_temporal_kwargs, read_model, remove_path, write_model
from ..models import LocalEpisode, LocalManifest, utc_now
from ..paths import episode_json, episodes_root, manifest_json, manifest_path, manifests_root
from .episodes import get_episode, update_episode
from .projects import StoreCtx, ensure_store_roots


def _validate_manifest_path(path: Path, manifest_id: str) -> bool:
    try:
        return path.is_file() and read_model(path, LocalManifest).id == manifest_id
    except Exception:
        return False


def get_manifest_path(ctx: StoreCtx, manifest_id: str) -> Path:
    ensure_store_roots(ctx)
    return resolve_entity_path(ctx.home, "manifests", manifest_id, validator=_validate_manifest_path)


def get_manifest(ctx: StoreCtx, manifest_id: str) -> LocalManifest:
    return read_model(get_manifest_path(ctx, manifest_id), LocalManifest)


def _resolve_manifest_episodes(ctx: StoreCtx, manifest: LocalManifest) -> list[LocalEpisode]:
    episodes: list[LocalEpisode] = []
    missing: list[str] = []
    for episode_id in manifest.episode_ids:
        try:
            episodes.append(get_episode(ctx, episode_id))
        except StoreError:
            missing.append(episode_id)
    if missing:
        raise StoreError(
            f"Manifest {manifest.id} references missing local episodes: {', '.join(missing)}",
            "NOT_FOUND",
        )
    episodes.sort(key=lambda episode: (episode.created_at, episode.id))
    return episodes


def list_manifests(ctx: StoreCtx) -> list[LocalManifest]:
    ensure_store_roots(ctx)
    manifests: list[LocalManifest] = []
    for entry in sorted(manifests_root(ctx.home).rglob("*.json")):
        try:
            manifests.append(read_model(entry, LocalManifest))
        except Exception:
            continue
    manifests.sort(key=lambda manifest: (manifest.updated_at, manifest.id), reverse=True)
    return manifests


def _ensure_unique_manifest_name(ctx: StoreCtx, name: str, *, exclude_id: str | None = None) -> None:
    for manifest in list_manifests(ctx):
        if manifest.id != exclude_id and manifest.name == name:
            raise StoreError(f"Manifest name already exists: {name}", "CONFLICT")


def create_manifest(
    ctx: StoreCtx,
    *,
    name: str,
    type: str,
    description: str | None = None,
    tags: list[str] | None = None,
    is_public: bool = False,
    fps: int | None = None,
    encoding: dict | None = None,
    features: dict | None = None,
    run_ids: list[str] | None = None,
    success_rate: float | None = None,
    rated_episodes: int = 0,
    episode_ids: list[str] | None = None,
    manifest_id: str | None = None,
    created_at=None,
    updated_at=None,
) -> LocalManifest:
    ensure_store_roots(ctx)
    _ensure_unique_manifest_name(ctx, name, exclude_id=manifest_id)
    if manifest_id is not None:
        try:
            get_manifest(ctx, manifest_id)
        except StoreError:
            pass
        else:
            raise StoreError(f"Manifest already exists: {manifest_id}", "CONFLICT")

    payload = normalize_temporal_kwargs(
        {
            "id": manifest_id or generate_id("mf"),
            "name": name,
            "description": description,
            "type": type,
            "tags": tags or [],
            "is_public": is_public,
            "fps": fps,
            "encoding": encoding or {},
            "features": features or {},
            "episode_ids": episode_ids or [],
            "run_ids": list(dict.fromkeys(run_ids or [])),
            "success_rate": success_rate,
            "rated_episodes": rated_episodes,
            "created_at": created_at or utc_now(),
            "updated_at": updated_at or utc_now(),
        }
    )
    manifest = LocalManifest(**payload)
    write_model(manifest_path(manifests_root(ctx.home), manifest.name, manifest.id), manifest)
    rebuild_catalog(ctx.home)
    return manifest


def update_manifest(ctx: StoreCtx, manifest_id: str, **updates) -> LocalManifest:
    path = get_manifest_path(ctx, manifest_id)
    manifest = get_manifest(ctx, manifest_id)
    # Nullable fields callers are allowed to explicitly clear. Without this
    # allowlist, _recompute_manifest_rollup's `success_rate=None` silently
    # drops and the manifest sticks at a stale rollup forever.
    nullable_fields = {"description", "fps", "success_rate"}
    clean = {
        key: value
        for key, value in updates.items()
        if value is not None or key in nullable_fields
    }
    if not clean:
        raise StoreError("No fields to update", "CONFLICT")
    if "name" in clean and clean["name"] != manifest.name:
        _ensure_unique_manifest_name(ctx, clean["name"], exclude_id=manifest_id)
    if "run_ids" in clean:
        clean["run_ids"] = list(dict.fromkeys(clean["run_ids"]))
    clean.setdefault("updated_at", utc_now())
    clean = normalize_temporal_kwargs(clean)
    updated = manifest.model_copy(update=clean)
    if updated.name != manifest.name:
        new_path = manifest_path(manifests_root(ctx.home), updated.name, updated.id)
        path.rename(new_path)
        path = new_path
    write_model(path, updated)
    rebuild_catalog(ctx.home)
    return updated


def delete_manifest(ctx: StoreCtx, manifest_id: str) -> None:
    manifest = get_manifest(ctx, manifest_id)
    from . import runs

    for run_id in manifest.run_ids:
        try:
            run = runs.get_run(ctx, run_id)
        except StoreError:
            continue
        if manifest_id in run.manifest_ids:
            runs.update_run(
                ctx,
                run_id,
                manifest_ids=[value for value in run.manifest_ids if value != manifest_id],
            )
    for episode_id in manifest.episode_ids:
        episode = get_episode(ctx, episode_id)
        manifest_ids = [value for value in episode.manifest_ids if value != manifest_id]
        update_episode(ctx, episode_id, manifest_ids=manifest_ids)
    remove_path(get_manifest_path(ctx, manifest_id))
    rebuild_catalog(ctx.home)


def add_manifest_episodes(ctx: StoreCtx, manifest_id: str, episode_ids: list[str]) -> dict[str, int | dict[str, str]]:
    manifest = get_manifest(ctx, manifest_id)
    added = 0
    already_linked = 0
    errors: dict[str, str] = {}
    current = list(manifest.episode_ids)
    for episode_id in episode_ids:
        if episode_id in current:
            already_linked += 1
            continue
        try:
            episode = get_episode(ctx, episode_id)
        except StoreError as exc:
            errors[episode_id] = str(exc)
            continue
        current.append(episode_id)
        manifest_ids = list(episode.manifest_ids)
        if manifest_id not in manifest_ids:
            manifest_ids.append(manifest_id)
            update_episode(ctx, episode_id, manifest_ids=manifest_ids)
        added += 1
    update_manifest(ctx, manifest_id, episode_ids=current)
    return {"added": added, "already_linked": already_linked, "errors": errors}


def remove_manifest_episodes(ctx: StoreCtx, manifest_id: str, episode_ids: list[str]) -> dict[str, int]:
    manifest = get_manifest(ctx, manifest_id)
    current = [episode_id for episode_id in manifest.episode_ids if episode_id not in set(episode_ids)]
    removed = len(manifest.episode_ids) - len(current)
    for episode_id in episode_ids:
        try:
            episode = get_episode(ctx, episode_id)
        except StoreError:
            continue
        update_episode(ctx, episode_id, manifest_ids=[value for value in episode.manifest_ids if value != manifest_id])
    update_manifest(ctx, manifest_id, episode_ids=current)
    return {"removed": removed}


def list_manifest_episodes(ctx: StoreCtx, manifest_id: str) -> list[LocalEpisode]:
    manifest = get_manifest(ctx, manifest_id)
    return _resolve_manifest_episodes(ctx, manifest)
