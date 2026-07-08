from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from ...ids import validate_id
from ...io import StoreError
from ...sync import SyncError, pull_project_from_cloud, sync_project_to_cloud
from ...store import projects, runs
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["projects"])


class ProjectCreateBody(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    tags: list[str] | None = None
    is_public: bool = False
    cloned_source_project_id: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str | None) -> str | None:
        return validate_id("project", v) if v is not None else None

    @field_validator("cloned_source_project_id")
    @classmethod
    def _check_cloned_source_project_id(cls, v: str | None) -> str | None:
        return validate_id("project", v) if v is not None else None


class ProjectPatchBody(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None
    cloned_source_project_id: str | None = None

    @field_validator("cloned_source_project_id")
    @classmethod
    def _check_cloned_source_project_id(cls, v: str | None) -> str | None:
        return validate_id("project", v) if v is not None else None


class ReadmeBody(BaseModel):
    content: str


class FileDownloadBody(BaseModel):
    paths: list[str]


class ProjectSyncBody(BaseModel):
    include_manifests: bool = False
    cloud_api_base: str | None = None
    bearer_token: str | None = None


def _raise(e: StoreError):
    status = {"NOT_FOUND": 404, "CONFLICT": 409}.get(e.code, 400)
    raise HTTPException(status_code=status, detail=str(e))


def _project_summary(project) -> dict:
    return {
        **project.model_dump(),
        "owner_user_id": "local",
        "owner_username": "local",
    }


@router.get("/projects")
def list_projects(
    scope: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    tags: str | None = None,
    order: str | None = None,
    ctx: StoreCtx = Depends(get_ctx),
):
    del scope
    if order not in {None, "newest", "oldest"}:
        raise HTTPException(status_code=400, detail="Invalid order")
    records = projects.list_projects(ctx, newest_first=order != "oldest")
    if tags:
        required = {tag.strip().lower() for tag in tags.split(",") if tag.strip()}
        records = [project for project in records if required.issubset({tag.lower() for tag in project.tags})]
    total_count = len(records)

    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cursor")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Invalid cursor")

    page = records[offset:offset + limit] if limit is not None else records[offset:]
    next_offset = offset + len(page)
    next_cursor = str(next_offset) if limit is not None and next_offset < total_count else None

    return {
        "projects": [_project_summary(project) for project in page],
        "next_cursor": next_cursor,
        "total_count": total_count,
    }


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreateBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        project = projects.create_project(
            ctx,
            name=body.name,
            description=body.description,
            tags=body.tags,
            is_public=body.is_public,
            cloned_source_project_id=body.cloned_source_project_id,
            project_id=body.id,
        )
        return {
            **_project_summary(project),
            "has_readme": projects.project_has_readme(ctx, project.id),
            "file_count": projects.project_file_count(ctx, project.id),
        }
    except StoreError as e:
        _raise(e)


@router.get("/projects/{project_id}")
def get_project(project_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        project = projects.get_project(ctx, project_id)
        return {
            **_project_summary(project),
            "has_readme": projects.project_has_readme(ctx, project_id),
            "file_count": projects.project_file_count(ctx, project_id),
        }
    except StoreError as e:
        _raise(e)


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatchBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        updates = body.model_dump(exclude_none=True)
        if "cloned_source_project_id" in body.model_fields_set:
            updates["cloned_source_project_id"] = body.cloned_source_project_id
        project = projects.update_project(ctx, project_id, **updates)
        return {
            **_project_summary(project),
            "has_readme": projects.project_has_readme(ctx, project_id),
            "file_count": projects.project_file_count(ctx, project_id),
        }
    except StoreError as e:
        _raise(e)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        projects.delete_project(ctx, project_id)
    except StoreError as e:
        _raise(e)


@router.get("/projects/{project_id}/files")
def list_project_files(project_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"files": projects.project_file_listing(ctx, project_id)}
    except StoreError as e:
        _raise(e)


@router.post("/projects/{project_id}/files/download")
def download_project_files(body: FileDownloadBody, project_id: str, request: Request, ctx: StoreCtx = Depends(get_ctx)):
    try:
        urls: dict[str, str] = {}
        for path in body.paths:
            projects.get_project_file_path(ctx, project_id, path)
            urls[path] = str(request.url_for("get_project_file_content", project_id=project_id)) + f"?path={quote(path)}"
        return {"urls": urls}
    except StoreError as e:
        _raise(e)


@router.get("/projects/{project_id}/files/content", name="get_project_file_content")
def get_project_file_content(project_id: str, path: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return FileResponse(projects.get_project_file_path(ctx, project_id, path))
    except StoreError as e:
        _raise(e)


@router.get("/projects/{project_id}/readme")
def get_project_readme(project_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return {"content": projects.get_project_readme(ctx, project_id)}
    except StoreError as e:
        _raise(e)


@router.put("/projects/{project_id}/readme")
def put_project_readme(project_id: str, body: ReadmeBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        projects.put_project_readme(ctx, project_id, body.content)
        return {"content": body.content}
    except StoreError as e:
        _raise(e)


@router.post("/projects/{project_id}/sync")
def sync_project(project_id: str, body: ProjectSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return sync_project_to_cloud(
            ctx,
            project_id,
            include_manifests=body.include_manifests if body else False,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/pull")
def pull_project(project_id: str, body: ProjectSyncBody | None = None, ctx: StoreCtx = Depends(get_ctx)):
    try:
        return pull_project_from_cloud(
            ctx,
            project_id,
            include_manifests=body.include_manifests if body else False,
            cloud_api_base=body.cloud_api_base if body else None,
            bearer_token=body.bearer_token if body else None,
        )
    except StoreError as e:
        _raise(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
