from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ...ids import validate_id
from ...io import StoreError
from ...sync import SyncError, pull_manifest_from_cloud, sync_manifest_to_cloud
from ...store import manifests, run_manifests
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["manifests"])


class ManifestCreateBody(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    type: str
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False
    fps: int | None = None
    encoding: dict = Field(default_factory=dict)
    features: dict = Field(default_factory=dict)
    success_rate: float | None = None
    rated_episodes: int = 0

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str | None) -> str | None:
        return validate_id("manifest", v) if v is not None else None


class ManifestPatchBody(BaseModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None
    fps: int | None = None
    encoding: dict | None = None
    features: dict | None = None
    success_rate: float | None = None
    rated_episodes: int | None = None


class ManifestEpisodeIds(BaseModel):
    episode_ids: list[str]


class ManifestRunBody(BaseModel):
    run_id: str

    @field_validator("run_id")
    @classmethod
    def _check_run_id(cls, v: str) -> str:
        return validate_id("run", v)


class ManifestSyncBody(BaseModel):
    cloud_api_base: str | None = None
    bearer_token: str | None = None


def _raise(e: StoreError):
    status = {"NOT_FOUND": 404, "CONFLICT": 409}.get(e.code, 400)
    raise HTTPException(status_code=status, detail=str(e))


def _parse_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        updated_at, entity_id = cursor.split("|", 1)
        return datetime.fromisoformat(updated_at.replace("Z", "+00:00")), entity_id
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _make_cursor(updated_at: datetime, entity_id: str) -> str:
    return f"{updated_at.isoformat()}|{entity_id}"


def _manifest_summary(manifest) -> dict:
    return {
        **manifest.model_dump(exclude={"episode_ids"}),
        "owner_user_id": "local",
        "owner_username": "local",
        "episode_count": len(manifest.episode_ids),
    }


def _episode_summary(episode) -> dict:
    return {
        "id": episode.id,
        "length": episode.length,
        "task": episode.task,
        "task_description": episode.task_description,
        "collection_mode": episode.collection_mode,
        "source_project_id": episode.source_project_id,
        "source_run_id": episode.source_run_id,
        "source_checkpoint": episode.source_checkpoint,
        "policy_name": episode.policy_name,
        "reward": episode.reward,
        "features": episode.features,
        "size_bytes": episode.size_bytes,
        "created_at": episode.created_at,
    }


def _run_link_summary(run) -> dict:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "parent_id": run.parent_id,
        "name": run.name,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@router.post("/manifests", status_code=201)
def create_manifest(body: ManifestCreateBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        manifest = manifests.create_manifest(ctx, manifest_id=body.id, **body.model_dump(exclude={"id"}))
        return _manifest_summary(manifest)
    except StoreError as e:
        _raise(e)


@router.get("/manifests")
def list_manifests(
    scope: str | None = None,
    owner: str | None = None,
    is_public: bool | None = None,
    tags: str | None = None,
    type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    ctx: StoreCtx = Depends(get_ctx),
):
    del scope, owner
    records = manifests.list_manifests(ctx)
    if is_public is not None:
        records = [manifest for manifest in records if manifest.is_public == is_public]
    if type is not None:
        records = [manifest for manifest in records if manifest.type == type]
    if tags:
        required = {tag.strip().lower() for tag in tags.split(",") if tag.strip()}
        records = [manifest for manifest in records if required.issubset({tag.lower() for tag in manifest.tags})]
    total_count = len(records)
    if cursor:
        updated_at, manifest_id = _parse_cursor(cursor)
        records = [manifest for manifest in records if (manifest.updated_at, manifest.id) < (updated_at, manifest_id)]
    next_cursor = None
    if len(records) > limit:
        tail = records[limit - 1]
        next_cursor = _make_cursor(tail.updated_at, tail.id)
        records = records[:limit]
    return {
        "manifests": [_manifest_summary(manifest) for manifest in records],
        "next_cursor": next_cursor,
        "total_count": total_count,
    }


@router.get("/manifests/{manifest_id}")
def get_manifest(manifest_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return _manifest_summary(manifests.get_manifest(ctx, manifest_id))
    except StoreError as e:
        _raise(e)


@router.patch("/manifests/{manifest_id}")
def patch_manifest(manifest_id: str, body: ManifestPatchBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return _manifest_summary(manifests.update_manifest(ctx, manifest_id, **body.model_dump(exclude_none=True)))
    except StoreError as e:
        _raise(e)


@router.delete("/manifests/{manifest_id}", status_code=204)
def delete_manifest(manifest_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        manifests.delete_manifest(ctx, manifest_id)
    except StoreError as e:
        _raise(e)


@router.get("/manifests/{manifest_id}/runs")
def list_manifest_runs(manifest_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"runs": [_run_link_summary(run) for run in run_manifests.list_manifest_runs(ctx, manifest_id)]}
    except StoreError as e:
        _raise(e)


@router.post("/manifests/{manifest_id}/runs", status_code=201)
def add_manifest_run(manifest_id: str, body: ManifestRunBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return run_manifests.add_run_manifest(ctx, body.run_id, manifest_id)
    except StoreError as e:
        _raise(e)


@router.delete("/manifests/{manifest_id}/runs/{run_id}", status_code=204)
def remove_manifest_run(manifest_id: str, run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        try:
            validate_id("run", run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run_manifests.remove_run_manifest(ctx, run_id, manifest_id)
    except StoreError as e:
        _raise(e)


@router.post("/manifests/{manifest_id}/episodes/add")
def add_manifest_episodes(manifest_id: str, body: ManifestEpisodeIds, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return manifests.add_manifest_episodes(ctx, manifest_id, body.episode_ids)
    except StoreError as e:
        _raise(e)


@router.post("/manifests/{manifest_id}/episodes/remove")
def remove_manifest_episodes(manifest_id: str, body: ManifestEpisodeIds, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return manifests.remove_manifest_episodes(ctx, manifest_id, body.episode_ids)
    except StoreError as e:
        _raise(e)


@router.get("/manifests/{manifest_id}/episodes")
def list_manifest_episodes(
    manifest_id: str,
    task: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    ctx: StoreCtx = Depends(get_ctx),
):
    try:
        episodes = manifests.list_manifest_episodes(ctx, manifest_id)
        if task is not None:
            episodes = [episode for episode in episodes if episode.task == task]
        if cursor:
            created_at, episode_id = _parse_cursor(cursor)
            episodes = [episode for episode in episodes if (episode.created_at, episode.id) > (created_at, episode_id)]
        next_cursor = None
        if len(episodes) > limit:
            tail = episodes[limit - 1]
            next_cursor = _make_cursor(tail.created_at, tail.id)
            episodes = episodes[:limit]
        return {"episodes": [_episode_summary(episode) for episode in episodes], "next_cursor": next_cursor}
    except StoreError as e:
        _raise(e)


@router.post("/manifests/{manifest_id}/episodes/batch-get")
def batch_get_manifest_episodes(
    manifest_id: str,
    body: ManifestEpisodeIds,
    request: Request,
    ctx: StoreCtx = Depends(get_ctx),
):
    try:
        manifest = manifests.get_manifest(ctx, manifest_id)
        if not body.episode_ids:
            return {"episodes": []}
        manifest_episode_ids = set(manifest.episode_ids)
        missing = [episode_id for episode_id in body.episode_ids if episode_id not in manifest_episode_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Episodes not found in manifest: {', '.join(missing)}")
        episodes = []
        for episode in manifests.list_manifest_episodes(ctx, manifest_id):
            if episode.id not in body.episode_ids:
                continue
            files = {
                path: {
                    "url": str(request.url_for("get_episode_file_content", episode_id=episode.id)) + f"?path={quote(path)}",
                    "size": int(meta.get("size", 0)),
                }
                for path, meta in (episode.files or {}).items()
            }
            episodes.append({
                "id": episode.id,
                "length": episode.length,
                "task": episode.task,
                "task_description": episode.task_description,
                "collection_mode": episode.collection_mode,
                "source_project_id": episode.source_project_id,
                "source_run_id": episode.source_run_id,
                "source_checkpoint": episode.source_checkpoint,
                "policy_name": episode.policy_name,
                "reward": episode.reward,
                "features": episode.features,
                "files": files,
                "created_at": episode.created_at,
            })
        return {"episodes": episodes}
    except StoreError as e:
        _raise(e)


@router.get("/episodes/{episode_id}/files/content", name="get_episode_file_content")
def get_episode_file_content(episode_id: str, path: str, ctx: StoreCtx = Depends(get_ctx)):
    from ...store import episodes

    try:
        return FileResponse(episodes.get_episode_file_path(ctx, episode_id, path))
    except StoreError as e:
        _raise(e)


@router.post("/manifests/{manifest_id}/sync")
def sync_manifest(manifest_id: str, body: ManifestSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return sync_manifest_to_cloud(
            ctx,
            manifest_id,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/manifests/{manifest_id}/pull")
def pull_manifest(manifest_id: str, body: ManifestSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return pull_manifest_from_cloud(
            ctx,
            manifest_id,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
