from __future__ import annotations
"""Public sync entrypoints.

This package is the sync engine surface used by both HTTP routes and any future
CLI entrypoints. The engine itself should remain callable directly from Python;
the FastAPI backend is only one transport for invoking it.
"""

from typing import Any

from ..store.projects import StoreCtx
from .cloud_portal import SyncPortalError, resolve_cloud_sync_config
from .exec import SyncExecError, execute_sync_plan
from .models import SyncPlan, SyncRequest
from .plan import SyncPlanError, build_sync_plan
from .progress import NoopSyncProgressReporter, SyncProgressReporter


class SyncError(Exception):
    pass


def plan_sync(
    ctx: StoreCtx,
    *,
    operation: str,
    entity_type: str,
    entity_id: str,
    include_manifests: bool = False,
    include_descendants: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> SyncPlan:
    """Build a concrete sync plan without performing side effects."""
    try:
        request = SyncRequest(
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            include_manifests=include_manifests,
            include_descendants=include_descendants,
            cloud_api_base=cloud_api_base,
            bearer_token=bearer_token,
        )
        return build_sync_plan(ctx, request)
    except (SyncPlanError, ValueError) as exc:
        raise SyncError(str(exc)) from exc


def sync_project_to_cloud(
    ctx: StoreCtx,
    project_id: str,
    *,
    include_manifests: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Execute the current project push flow against cloud.

    Execution support is intentionally narrower than planning support today:
    only project push is wired end-to-end.
    """
    plan = plan_sync(
        ctx,
        operation="push",
        entity_type="project",
        entity_id=project_id,
        include_manifests=include_manifests,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=cloud_api_base or plan.request.cloud_api_base,
            bearer_token=bearer_token or plan.request.bearer_token,
        )
        return execute_sync_plan(ctx, plan, config).to_dict()
    except (SyncPortalError, SyncExecError) as exc:
        raise SyncError(str(exc)) from exc


def sync_run_to_cloud(
    ctx: StoreCtx,
    run_id: str,
    *,
    include_manifests: bool = False,
    include_descendants: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Execute run push using resolved project skeleton + ancestor-chain scope."""
    plan = plan_sync(
        ctx,
        operation="push",
        entity_type="run",
        entity_id=run_id,
        include_manifests=include_manifests,
        include_descendants=include_descendants,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=cloud_api_base or plan.request.cloud_api_base,
            bearer_token=bearer_token or plan.request.bearer_token,
        )
        return execute_sync_plan(ctx, plan, config).to_dict()
    except (SyncPortalError, SyncExecError) as exc:
        raise SyncError(str(exc)) from exc


def pull_run_from_cloud(
    ctx: StoreCtx,
    run_id: str,
    *,
    include_manifests: bool = False,
    include_descendants: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Pull a cloud run into the local store, including project files and ancestors."""
    return execute_sync(
        ctx,
        operation="pull",
        entity_type="run",
        entity_id=run_id,
        include_manifests=include_manifests,
        include_descendants=include_descendants,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )


def sync_manifest_to_cloud(
    ctx: StoreCtx,
    manifest_id: str,
    *,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Execute standalone manifest push using the existing manifest episode flow."""
    plan = plan_sync(
        ctx,
        operation="push",
        entity_type="manifest",
        entity_id=manifest_id,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=cloud_api_base or plan.request.cloud_api_base,
            bearer_token=bearer_token or plan.request.bearer_token,
        )
        return execute_sync_plan(ctx, plan, config).to_dict()
    except (SyncPortalError, SyncExecError) as exc:
        raise SyncError(str(exc)) from exc


def pull_manifest_from_cloud(
    ctx: StoreCtx,
    manifest_id: str,
    *,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Pull a cloud manifest into the local store, preserving manifest/episode IDs."""
    return execute_sync(
        ctx,
        operation="pull",
        entity_type="manifest",
        entity_id=manifest_id,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )


def execute_sync(
    ctx: StoreCtx,
    *,
    operation: str,
    entity_type: str,
    entity_id: str,
    include_manifests: bool = False,
    include_descendants: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
    progress_reporter: SyncProgressReporter | None = None,
) -> dict[str, Any]:
    """Execute a supported sync workflow directly from a request-like payload."""
    reporter = progress_reporter or NoopSyncProgressReporter()
    try:
        reporter.planning()
        plan = plan_sync(
            ctx,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            include_manifests=include_manifests,
            include_descendants=include_descendants,
            cloud_api_base=cloud_api_base,
            bearer_token=bearer_token,
        )
        reporter.planned(plan)
        config = resolve_cloud_sync_config(
            cloud_api_base=cloud_api_base or plan.request.cloud_api_base,
            bearer_token=bearer_token or plan.request.bearer_token,
            require_token=operation == "push",
        )
        reporter.execution_started()
        result = execute_sync_plan(ctx, plan, config, progress_reporter=reporter)
        result.progress = reporter.ref()
        payload = result.to_dict()
        reporter.finish(payload)
        return payload
    except (SyncPortalError, SyncExecError) as exc:
        reporter.fail(exc)
        raise SyncError(str(exc)) from exc
    except SyncError as exc:
        reporter.fail(exc)
        raise
    except Exception as exc:
        reporter.fail(exc)
        raise


def pull_project_from_cloud(
    ctx: StoreCtx,
    project_id: str,
    *,
    include_manifests: bool = False,
    cloud_api_base: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Pull a cloud project into the local store, preserving IDs."""
    return execute_sync(
        ctx,
        operation="pull",
        entity_type="project",
        entity_id=project_id,
        include_manifests=include_manifests,
        cloud_api_base=cloud_api_base,
        bearer_token=bearer_token,
    )
