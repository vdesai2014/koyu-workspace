from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ...io import StoreError
from ...sync import SyncError, execute_sync, plan_sync
from ...sync.models import SyncRequest
from ...sync.progress import FileSyncProgressReporter, delete_sync_job, list_sync_jobs, read_sync_job
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["sync"])


class SyncPlanBody(BaseModel):
    operation: str
    entity_type: str
    entity_id: str
    include_manifests: bool = False
    include_descendants: bool = False
    cloud_api_base: str | None = None
    bearer_token: str | None = None
    progress: bool = False


class SyncExecuteBody(SyncPlanBody):
    pass


def _raise_store_error(e: StoreError):
    status = {"NOT_FOUND": 404, "CONFLICT": 409}.get(e.code, 400)
    raise HTTPException(status_code=status, detail=str(e))


@router.post("/sync/plan")
def get_sync_plan(body: SyncPlanBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        plan = plan_sync(
            ctx,
            operation=body.operation,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            include_manifests=body.include_manifests,
            include_descendants=body.include_descendants,
            cloud_api_base=body.cloud_api_base,
            bearer_token=body.bearer_token,
        )
        return plan.to_dict()
    except StoreError as e:
        _raise_store_error(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync/execute")
def execute_sync_route(body: SyncExecuteBody, ctx: StoreCtx = Depends(get_ctx)):
    try:
        reporter = None
        if body.progress:
            request = _request_from_body(body)
            reporter = FileSyncProgressReporter(home=ctx.home, request=request)
        return execute_sync(
            ctx,
            operation=body.operation,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            include_manifests=body.include_manifests,
            include_descendants=body.include_descendants,
            cloud_api_base=body.cloud_api_base,
            bearer_token=body.bearer_token,
            progress_reporter=reporter,
        )
    except StoreError as e:
        _raise_store_error(e)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _request_from_body(body: SyncPlanBody) -> SyncRequest:
    return SyncRequest(
        operation=body.operation,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        include_manifests=body.include_manifests,
        include_descendants=body.include_descendants,
        cloud_api_base=body.cloud_api_base,
        bearer_token=body.bearer_token,
    )


def _run_sync_job(ctx: StoreCtx, body: SyncExecuteBody, reporter: FileSyncProgressReporter) -> None:
    try:
        execute_sync(
            ctx,
            operation=body.operation,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            include_manifests=body.include_manifests,
            include_descendants=body.include_descendants,
            cloud_api_base=body.cloud_api_base,
            bearer_token=body.bearer_token,
            progress_reporter=reporter,
        )
    except Exception as exc:
        reporter.fail(exc)


@router.post("/sync/jobs")
def start_sync_job(body: SyncExecuteBody, background_tasks: BackgroundTasks, ctx: StoreCtx = Depends(get_ctx)):
    request = _request_from_body(body)
    reporter = FileSyncProgressReporter(home=ctx.home, request=request)
    background_tasks.add_task(_run_sync_job, ctx, body, reporter)
    return {
        "job_id": reporter.job_id,
        "path": str(reporter.path),
        "status_url": f"/api/sync/jobs/{reporter.job_id}",
    }


@router.get("/sync/jobs")
def list_sync_job_route(limit: int = 50, ctx: StoreCtx = Depends(get_ctx)):
    return {"jobs": list_sync_jobs(ctx.home, limit=max(1, min(limit, 200)))}


@router.get("/sync/jobs/{job_id}")
def get_sync_job_route(job_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        payload = read_sync_job(ctx.home, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if payload is None:
        raise HTTPException(status_code=404, detail="sync job not found")
    return payload


@router.delete("/sync/jobs/{job_id}", status_code=204)
def delete_sync_job_route(job_id: str, ctx: StoreCtx = Depends(get_ctx)):
    try:
        result = delete_sync_job(ctx.home, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result == "not_found":
        raise HTTPException(status_code=404, detail="sync job not found")
    if result == "not_terminal":
        raise HTTPException(status_code=409, detail="Only succeeded or failed sync jobs can be deleted.")
    return None
