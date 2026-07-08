from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from ...ids import validate_id
from ...io import StoreError
from ...sync import SyncError, pull_run_from_cloud, sync_run_to_cloud
from ...store import run_manifests, runs
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["runs"])


class RunCreateBody(BaseModel):
    id: str | None = None
    name: str
    parent_id: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str | None) -> str | None:
        return validate_id("run", v) if v is not None else None

    @field_validator("parent_id")
    @classmethod
    def _check_parent_id(cls, v: str | None) -> str | None:
        return validate_id("run", v) if v is not None else None


class RunPatchBody(BaseModel):
    name: str | None = None
    parent_id: str | None = None


class RunManifestBody(BaseModel):
    manifest_id: str

    @field_validator("manifest_id")
    @classmethod
    def _check_manifest_id(cls, v: str) -> str:
        return validate_id("manifest", v)


class ReadmeBody(BaseModel):
    content: str


class FileDownloadBody(BaseModel):
    paths: list[str]


class RunSyncBody(BaseModel):
    include_manifests: bool = False
    include_descendants: bool = False
    cloud_api_base: str | None = None
    bearer_token: str | None = None


def _raise(e: StoreError):
    status = {"NOT_FOUND": 404, "CONFLICT": 409}.get(e.code, 400)
    raise HTTPException(status_code=status, detail=str(e))


def _run_summary(run) -> dict:
    return {
        **run.model_dump(),
    }


def _manifest_link_summary(manifest) -> dict:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "description": manifest.description,
        "type": manifest.type,
        "tags": manifest.tags,
        "is_public": manifest.is_public,
        "fps": manifest.fps,
        "episode_count": len(manifest.episode_ids),
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
    }


@router.post("/projects/{project_id}/runs", status_code=201)
def create_run(project_id: str, body: RunCreateBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        run = runs.create_run(
            ctx,
            project_id=project_id,
            name=body.name,
            parent_id=body.parent_id,
            run_id=body.id,
        )
        return {
            **_run_summary(run),
            "has_readme": runs.run_has_readme(ctx, run.id),
            "file_count": runs.run_file_count(ctx, run.id),
        }
    except StoreError as e:
        _raise(e)


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"runs": [_run_summary(run) for run in runs.list_runs(ctx, project_id)], "next_cursor": None}
    except StoreError as e:
        _raise(e)


@router.get("/runs/{run_id}")
def get_run(run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        run = runs.get_run(ctx, run_id)
        return {
            **_run_summary(run),
            "has_readme": runs.run_has_readme(ctx, run_id),
            "file_count": runs.run_file_count(ctx, run_id),
        }
    except StoreError as e:
        _raise(e)


@router.patch("/runs/{run_id}")
def patch_run(run_id: str, body: RunPatchBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        payload = body.model_dump(exclude_none=True)
        if "parent_id" in body.model_fields_set:
            payload["parent_id"] = body.parent_id
        run = runs.update_run(ctx, run_id, **payload)
        return {
            **_run_summary(run),
            "has_readme": runs.run_has_readme(ctx, run_id),
            "file_count": runs.run_file_count(ctx, run_id),
        }
    except StoreError as e:
        _raise(e)


@router.get("/runs/{run_id}/manifests")
def list_run_manifests(run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"manifests": [_manifest_link_summary(manifest) for manifest in run_manifests.list_run_manifests(ctx, run_id)]}
    except StoreError as e:
        _raise(e)


@router.post("/runs/{run_id}/manifests", status_code=201)
def add_run_manifest(run_id: str, body: RunManifestBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return run_manifests.add_run_manifest(ctx, run_id, body.manifest_id)
    except StoreError as e:
        _raise(e)


@router.delete("/runs/{run_id}/manifests/{manifest_id}", status_code=204)
def remove_run_manifest(run_id: str, manifest_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        try:
            validate_id("manifest", manifest_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run_manifests.remove_run_manifest(ctx, run_id, manifest_id)
    except StoreError as e:
        _raise(e)


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        runs.delete_run(ctx, run_id)
    except StoreError as e:
        _raise(e)


@router.get("/runs/{run_id}/files")
def list_run_files(run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"files": runs.run_file_listing(ctx, run_id)}
    except StoreError as e:
        _raise(e)


@router.post("/runs/{run_id}/files/download")
def download_run_files(body: FileDownloadBody, run_id: str, request: Request, ctx: StoreCtx = Depends(get_ctx)):
    try:
        urls: dict[str, str] = {}
        for path in body.paths:
            runs.get_run_file_path(ctx, run_id, path)
            urls[path] = str(request.url_for("get_run_file_content", run_id=run_id)) + f"?path={quote(path)}"
        return {"urls": urls}
    except StoreError as e:
        _raise(e)


@router.get("/runs/{run_id}/files/content", name="get_run_file_content")
def get_run_file_content(run_id: str, path: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return FileResponse(runs.get_run_file_path(ctx, run_id, path))
    except StoreError as e:
        _raise(e)


@router.get("/runs/{run_id}/readme")
def get_run_readme(run_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"content": runs.get_run_readme(ctx, run_id)}
    except StoreError as e:
        _raise(e)


@router.put("/runs/{run_id}/readme")
def put_run_readme(run_id: str, body: ReadmeBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        runs.put_run_readme(ctx, run_id, body.content)
        return {"content": body.content}
    except StoreError as e:
        _raise(e)


@router.post("/runs/{run_id}/sync")
def sync_run(run_id: str, body: RunSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return sync_run_to_cloud(
            ctx,
            run_id,
            include_manifests=body.include_manifests if body else False,
            include_descendants=body.include_descendants if body else False,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/pull")
def pull_run(run_id: str, body: RunSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return pull_run_from_cloud(
            ctx,
            run_id,
            include_manifests=body.include_manifests if body else False,
            include_descendants=body.include_descendants if body else False,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
