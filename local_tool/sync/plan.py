from __future__ import annotations
"""Pure-ish sync planning.

This module resolves scope and chooses actions, but does not perform network IO
or local store mutations. Future cloud-sourced clone/pull flows that need local
skeleton creation should go through store APIs rather than direct file writes.
"""

from ..io import StoreError
from ..models import LocalEpisode, LocalManifest, LocalProject, LocalRun
from ..store import episodes, manifests, projects, runs
from ..store.projects import StoreCtx
from .cloud_portal import CloudPortal, SyncPortalError, resolve_cloud_sync_config
from .ignore import filter_project_paths, filter_run_paths
from .models import FileAction, LinkAction, MetadataAction, SyncPlan, SyncRequest, SyncScope


class SyncPlanError(Exception):
    pass


def build_sync_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Build a sync plan for the requested operation/entity."""
    if request.operation == "push":
        if request.entity_type == "project":
            return _build_project_push_plan(ctx, request)
        if request.entity_type == "run":
            return _build_run_push_plan(ctx, request)
        if request.entity_type == "manifest":
            return _build_manifest_push_plan(ctx, request)
        raise SyncPlanError(f"Unsupported sync entity type: {request.entity_type}")

    if request.operation == "clone":
        if request.entity_type != "project":
            raise SyncPlanError(f"Unsupported clone entity type for now: {request.entity_type}")
        if request.include_manifests:
            raise SyncPlanError("Clone does not support include_manifests")
        return _build_project_clone_plan(request)

    if request.operation == "pull":
        if request.entity_type == "project":
            return _build_project_pull_plan(ctx, request)
        if request.entity_type == "run":
            return _build_run_pull_plan(ctx, request)
        if request.entity_type == "manifest":
            return _build_manifest_pull_plan(ctx, request)
        raise SyncPlanError(f"Unsupported pull entity type for now: {request.entity_type}")

    raise SyncPlanError(f"Unsupported sync operation for now: {request.operation}")


def _build_project_push_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Project push includes the project plus all runs; manifests are opt-in."""
    project = projects.get_project(ctx, request.entity_id)
    local_runs_unsorted = runs.list_runs(ctx, project.id)
    local_runs = sorted(local_runs_unsorted, key=lambda run: (_run_depth(run, local_runs_unsorted), run.created_at, run.id))
    linked_manifests, warnings = _collect_linked_manifests(ctx, local_runs) if request.include_manifests else ([], [])
    scope = SyncScope(
        root_entity_type="project",
        root_entity_id=project.id,
        project=project,
        runs=local_runs,
        manifests=linked_manifests,
        episodes=[episode for manifest in linked_manifests for episode in manifests.list_manifest_episodes(ctx, manifest.id)],
        warnings=list(warnings),
    )
    return _plan_push(ctx, scope, request)


def _build_run_push_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Run push includes project skeleton and ancestor chain by default."""
    root_run = runs.get_run(ctx, request.entity_id)
    project = projects.get_project(ctx, root_run.project_id)
    all_runs = runs.list_runs(ctx, project.id)
    by_id = {run.id: run for run in all_runs}
    selected_ids: list[str] = []

    current = root_run.id
    lineage: list[str] = []
    while current is not None:
        lineage.append(current)
        current = by_id.get(current).parent_id if by_id.get(current) else None
    selected_ids.extend(reversed(lineage))

    if request.include_descendants:
        for run in all_runs:
            if _is_descendant(run, root_run.id, by_id):
                selected_ids.append(run.id)

    deduped_ids = list(dict.fromkeys(selected_ids))
    selected_runs = [by_id[run_id] for run_id in deduped_ids]
    linked_manifests, warnings = _collect_linked_manifests(ctx, selected_runs) if request.include_manifests else ([], [])
    scope = SyncScope(
        root_entity_type="run",
        root_entity_id=root_run.id,
        project=project,
        runs=selected_runs,
        manifests=linked_manifests,
        episodes=[episode for manifest in linked_manifests for episode in manifests.list_manifest_episodes(ctx, manifest.id)],
        warnings=list(warnings),
    )
    return _plan_push(ctx, scope, request)


def _build_manifest_push_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Manifest push scopes to the manifest and its episode payloads."""
    manifest = manifests.get_manifest(ctx, request.entity_id)
    scope = SyncScope(
        root_entity_type="manifest",
        root_entity_id=manifest.id,
        manifests=[manifest],
        episodes=manifests.list_manifest_episodes(ctx, manifest.id),
    )
    return _plan_push(ctx, scope, request)


def _build_project_clone_plan(request: SyncRequest) -> SyncPlan:
    """Clone a cloud project into a new local project with remapped local IDs."""
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=request.cloud_api_base,
            bearer_token=request.bearer_token,
            require_token=False,
        )
        with CloudPortal(config) as portal:
            source_project_raw = portal.fetch_project(request.entity_id)
            source_runs_list = portal.list_project_runs(request.entity_id)
            source_run_details = {
                item["id"]: portal.fetch_run(item["id"])
                for item in source_runs_list
            }
    except SyncPortalError as exc:
        raise SyncPlanError(str(exc)) from exc

    source_project = LocalProject.model_validate(
        {
            "id": source_project_raw["id"],
            "name": source_project_raw["name"],
            "description": source_project_raw.get("description"),
            "tags": source_project_raw.get("tags", []),
            "is_public": bool(source_project_raw.get("is_public", False)),
            "cloned_source_project_id": source_project_raw.get("cloned_source_project_id"),
            "created_at": source_project_raw.get("created_at"),
            "updated_at": source_project_raw.get("updated_at"),
        }
    )
    source_runs = [
        LocalRun.model_validate(
            {
                "id": item["id"],
                "project_id": item["project_id"],
                "parent_id": item.get("parent_id"),
                "name": item["name"],
                "manifest_ids": [],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )
        for item in source_runs_list
    ]
    source_runs = sorted(source_runs, key=lambda run: (_run_depth(run, source_runs), run.created_at, run.id))

    plan = SyncPlan(
        request=request,
        scope=SyncScope(
            root_entity_type="project",
            root_entity_id=source_project.id,
            project=source_project,
            runs=source_runs,
        ),
    )
    plan.required_id_remaps = {
        "projects": [source_project.id],
        "runs": [run.id for run in source_runs],
    }
    plan.metadata_actions.append(
        MetadataAction(
            "create_local_clone",
            "project",
            source_project.id,
            {
                "source_project_id": source_project.id,
                "name": source_project.name,
                "description": source_project.description,
                "tags": list(source_project.tags),
                "is_public": bool(source_project.is_public),
                "cloned_source_project_id": source_project.id,
                "created_at": source_project.created_at.isoformat(),
                "updated_at": source_project.updated_at.isoformat(),
            },
        )
    )

    source_project_files = source_project_raw.get("files", {}) or {}
    for path, meta in sorted(source_project_files.items()):
        plan.file_actions.append(
            FileAction(
                "copy",
                "project",
                source_project.id,
                path,
                int(meta.get("size", 0)),
                source_entity_id=source_project.id,
                source_path=path,
            )
        )

    for run in source_runs:
        source_run_raw = source_run_details[run.id]
        plan.metadata_actions.append(
            MetadataAction(
                "create_local_clone",
                "run",
                run.id,
                {
                    "source_run_id": run.id,
                    "project_id": source_project.id,
                    "parent_id": run.parent_id,
                    "name": run.name,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                },
            )
        )
        for path, meta in sorted((source_run_raw.get("files") or {}).items()):
            plan.file_actions.append(
                FileAction(
                    "copy",
                    "run",
                    run.id,
                    path,
                    int(meta.get("size", 0)),
                    source_entity_id=run.id,
                    source_path=path,
                )
            )

    return plan


def _build_project_pull_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Pull a cloud project into the local store, preserving project/run IDs."""
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=request.cloud_api_base,
            bearer_token=request.bearer_token,
            require_token=False,
        )
        with CloudPortal(config) as portal:
            source_project_raw = portal.fetch_project(request.entity_id)
            source_runs_list = portal.list_project_runs(request.entity_id)
            source_run_details = {
                item["id"]: portal.fetch_run(item["id"])
                for item in source_runs_list
            }
    except SyncPortalError as exc:
        raise SyncPlanError(str(exc)) from exc

    source_project = LocalProject.model_validate(
        {
            "id": source_project_raw["id"],
            "name": source_project_raw["name"],
            "description": source_project_raw.get("description"),
            "tags": source_project_raw.get("tags", []),
            "is_public": bool(source_project_raw.get("is_public", False)),
            "cloned_source_project_id": source_project_raw.get("cloned_source_project_id"),
            "created_at": source_project_raw.get("created_at"),
            "updated_at": source_project_raw.get("updated_at"),
        }
    )
    source_runs = [
        _cloud_run_from_payload(source_run_details[item["id"]], include_manifests=request.include_manifests)
        for item in source_runs_list
    ]
    source_runs = sorted(source_runs, key=lambda run: (_run_depth(run, source_runs), run.created_at, run.id))
    linked_manifests, linked_episodes, link_warnings = _collect_cloud_link_scope(request=request, source_runs=source_runs, source_run_details=source_run_details)

    plan = SyncPlan(
        request=request,
        scope=SyncScope(
            root_entity_type="project",
            root_entity_id=source_project.id,
            project=source_project,
            runs=source_runs,
            manifests=linked_manifests,
            episodes=linked_episodes,
        ),
        warnings=list(link_warnings),
    )

    try:
        projects.get_project(ctx, source_project.id)
        project_op = "update_local"
    except StoreError:
        project_op = "create_local"
    plan.metadata_actions.append(
        MetadataAction(
            project_op,
            "project",
            source_project.id,
            {
                "name": source_project.name,
                "description": source_project.description,
                "tags": list(source_project.tags),
                "is_public": bool(source_project.is_public),
                "cloned_source_project_id": source_project.cloned_source_project_id,
                "created_at": source_project.created_at.isoformat(),
                "updated_at": source_project.updated_at.isoformat(),
            },
        )
    )

    for path, meta in sorted((source_project_raw.get("files") or {}).items()):
        plan.file_actions.append(
            FileAction(
                "download",
                "project",
                source_project.id,
                path,
                int(meta.get("size", 0)),
                source_entity_id=source_project.id,
                source_path=path,
            )
        )

    for run in source_runs:
        try:
            runs.get_run(ctx, run.id)
            run_op = "update_local"
        except StoreError:
            run_op = "create_local"
        plan.metadata_actions.append(
            MetadataAction(
                run_op,
                "run",
                run.id,
                {
                    "project_id": run.project_id,
                    "parent_id": run.parent_id,
                    "name": run.name,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                    **({"manifest_ids": list(run.manifest_ids)} if request.include_manifests else {}),
                },
            )
        )
        source_run_raw = source_run_details[run.id]
        if source_run_raw.get("manifest_ids") and not request.include_manifests:
            plan.warnings.append(
                f"Run {run.id} has cloud manifests that are omitted from pull because include_manifests is disabled."
            )
        for path, meta in sorted((source_run_raw.get("files") or {}).items()):
            plan.file_actions.append(
                FileAction(
                    "download",
                    "run",
                    run.id,
                    path,
                    int(meta.get("size", 0)),
                    source_entity_id=run.id,
                    source_path=path,
                )
            )

    _append_pull_linked_manifest_actions(ctx, plan)

    return plan


def _build_run_pull_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Pull a cloud run plus its project files and ancestor chain into the local store."""
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=request.cloud_api_base,
            bearer_token=request.bearer_token,
            require_token=False,
        )
        with CloudPortal(config) as portal:
            root_run_raw = portal.fetch_run(request.entity_id)
            source_project_raw = portal.fetch_project(root_run_raw["project_id"])
            source_runs_list = portal.list_project_runs(root_run_raw["project_id"])
            source_run_details = {
                item["id"]: portal.fetch_run(item["id"])
                for item in source_runs_list
            }
    except SyncPortalError as exc:
        raise SyncPlanError(str(exc)) from exc

    source_project = LocalProject.model_validate(
        {
            "id": source_project_raw["id"],
            "name": source_project_raw["name"],
            "description": source_project_raw.get("description"),
            "tags": source_project_raw.get("tags", []),
            "is_public": bool(source_project_raw.get("is_public", False)),
            "cloned_source_project_id": source_project_raw.get("cloned_source_project_id"),
            "created_at": source_project_raw.get("created_at"),
            "updated_at": source_project_raw.get("updated_at"),
        }
    )
    all_runs = [
        _cloud_run_from_payload(source_run_details[item["id"]], include_manifests=request.include_manifests)
        for item in source_runs_list
    ]
    by_id = {run.id: run for run in all_runs}
    root_run = by_id.get(request.entity_id)
    if root_run is None:
        raise SyncPlanError(f"Cloud run {request.entity_id} was not returned in project listing")

    selected_ids: list[str] = []
    current = root_run.id
    lineage: list[str] = []
    while current is not None:
        lineage.append(current)
        current = by_id.get(current).parent_id if by_id.get(current) else None
    selected_ids.extend(reversed(lineage))

    if request.include_descendants:
        for run in all_runs:
            if _is_descendant(run, root_run.id, by_id):
                selected_ids.append(run.id)

    selected_runs = [by_id[run_id] for run_id in dict.fromkeys(selected_ids)]
    selected_runs = sorted(selected_runs, key=lambda run: (_run_depth(run, all_runs), run.created_at, run.id))
    linked_manifests, linked_episodes, link_warnings = _collect_cloud_link_scope(
        request=request,
        source_runs=selected_runs,
        source_run_details=source_run_details,
    )

    plan = SyncPlan(
        request=request,
        scope=SyncScope(
            root_entity_type="run",
            root_entity_id=root_run.id,
            project=source_project,
            runs=selected_runs,
            manifests=linked_manifests,
            episodes=linked_episodes,
        ),
        warnings=list(link_warnings),
    )

    try:
        projects.get_project(ctx, source_project.id)
        project_op = "update_local"
    except StoreError:
        project_op = "create_local"
    plan.metadata_actions.append(
        MetadataAction(
            project_op,
            "project",
            source_project.id,
            {
                "name": source_project.name,
                "description": source_project.description,
                "tags": list(source_project.tags),
                "is_public": bool(source_project.is_public),
                "cloned_source_project_id": source_project.cloned_source_project_id,
                "created_at": source_project.created_at.isoformat(),
                "updated_at": source_project.updated_at.isoformat(),
            },
        )
    )

    for path, meta in sorted((source_project_raw.get("files") or {}).items()):
        plan.file_actions.append(
            FileAction(
                "download",
                "project",
                source_project.id,
                path,
                int(meta.get("size", 0)),
                source_entity_id=source_project.id,
                source_path=path,
            )
        )

    for run in selected_runs:
        try:
            runs.get_run(ctx, run.id)
            run_op = "update_local"
        except StoreError:
            run_op = "create_local"
        plan.metadata_actions.append(
            MetadataAction(
                run_op,
                "run",
                run.id,
                {
                    "project_id": run.project_id,
                    "parent_id": run.parent_id,
                    "name": run.name,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                    **({"manifest_ids": list(run.manifest_ids)} if request.include_manifests else {}),
                },
            )
        )
        source_run_raw = source_run_details[run.id]
        if source_run_raw.get("manifest_ids") and not request.include_manifests:
            plan.warnings.append(
                f"Run {run.id} has cloud manifests that are omitted from pull because include_manifests is disabled."
            )
        for path, meta in sorted((source_run_raw.get("files") or {}).items()):
            plan.file_actions.append(
                FileAction(
                    "download",
                    "run",
                    run.id,
                    path,
                    int(meta.get("size", 0)),
                    source_entity_id=run.id,
                    source_path=path,
                )
            )

    _append_pull_linked_manifest_actions(ctx, plan)

    return plan


def _build_manifest_pull_plan(ctx: StoreCtx, request: SyncRequest) -> SyncPlan:
    """Pull a cloud manifest and its episodes into the local store, preserving IDs."""
    try:
        config = resolve_cloud_sync_config(
            cloud_api_base=request.cloud_api_base,
            bearer_token=request.bearer_token,
            require_token=False,
        )
        with CloudPortal(config) as portal:
            source_manifest_raw = portal.fetch_manifest(request.entity_id)
            episode_summaries = portal.list_manifest_episodes(request.entity_id)
            episode_ids = [episode["id"] for episode in episode_summaries]
            episode_details = portal.manifest_episode_batch_get(request.entity_id, episode_ids) if episode_ids else []
    except SyncPortalError as exc:
        raise SyncPlanError(str(exc)) from exc

    source_manifest = _cloud_manifest_from_payload(source_manifest_raw, episode_ids)
    source_episodes = [_cloud_episode_from_payload(item, source_manifest.id) for item in episode_details]

    plan = SyncPlan(
        request=request,
        scope=SyncScope(
            root_entity_type="manifest",
            root_entity_id=source_manifest.id,
            manifests=[source_manifest],
            episodes=source_episodes,
        ),
    )

    _append_pull_linked_manifest_actions(ctx, plan)
    return plan


def _plan_push(ctx: StoreCtx, scope: SyncScope, request: SyncRequest) -> SyncPlan:
    """Translate resolved scope into additive push actions."""
    plan = SyncPlan(request=request, scope=scope, warnings=list(scope.warnings))

    if scope.project:
        plan.metadata_actions.extend(
            [
                MetadataAction("ensure_remote", "project", scope.project.id),
                MetadataAction("patch_remote", "project", scope.project.id),
            ]
        )
        if request.entity_type == "project":
            project_listing = projects.project_file_listing(ctx, scope.project.id)
            project_decision = filter_project_paths(ctx, scope.project.id, set(project_listing))
            plan.ignore_patterns = list(project_decision.patterns)
            if project_decision.ignored:
                plan.ignored_file_paths[f"project:{scope.project.id}"] = sorted(project_decision.ignored)
            for path in sorted(project_decision.included):
                meta = project_listing[path]
                plan.file_actions.append(FileAction("upload", "project", scope.project.id, path, int(meta["size"])))
        else:
            plan.ignore_patterns = list(filter_project_paths(ctx, scope.project.id, set()).patterns)

    for run in scope.runs:
        run_listing = runs.run_file_listing(ctx, run.id)
        run_decision = filter_run_paths(ctx, run.id, set(run_listing))
        if run_decision.ignored:
            plan.ignored_file_paths[f"run:{run.id}"] = sorted(run_decision.ignored)
        plan.metadata_actions.extend(
            [
                MetadataAction("ensure_remote", "run", run.id, {"project_id": run.project_id}),
                MetadataAction("patch_remote", "run", run.id),
            ]
        )
        for path in sorted(run_decision.included):
            meta = run_listing[path]
            plan.file_actions.append(FileAction("upload", "run", run.id, path, int(meta["size"])))

    synced_manifest_ids = {manifest.id for manifest in scope.manifests}
    for manifest in scope.manifests:
        manifest_episodes = manifests.list_manifest_episodes(ctx, manifest.id)
        plan.metadata_actions.extend(
            [
                MetadataAction("ensure_remote", "manifest", manifest.id),
                MetadataAction("patch_remote", "manifest", manifest.id),
            ]
        )
        for episode in manifest_episodes:
            for path, meta in episode.files.items():
                plan.file_actions.append(FileAction("upload", "episode", episode.id, path, int(meta["size"])))
        plan.link_actions.append(
            LinkAction(
                "attach_manifest_episodes",
                "manifest",
                manifest.id,
                {"episode_ids": [episode.id for episode in manifest_episodes]},
            )
        )

    linked_pairs: set[tuple[str, str]] = set()
    for run in scope.runs:
        linked_manifest_ids = set(run.manifest_ids)
        if not linked_manifest_ids:
            continue
        if linked_manifest_ids and not linked_manifest_ids.issubset(synced_manifest_ids):
            plan.warnings.append(
                f"Run {run.id} has manifests that are out of scope; those associations will be omitted."
            )
        for manifest_id in sorted(linked_manifest_ids.intersection(synced_manifest_ids)):
            linked_pairs.add((run.id, manifest_id))

    scoped_run_ids = {run.id for run in scope.runs}
    for manifest in scope.manifests:
        for run_id in manifest.run_ids:
            if run_id in scoped_run_ids:
                linked_pairs.add((run_id, manifest.id))

    for run_id, manifest_id in sorted(linked_pairs):
        plan.link_actions.append(
            LinkAction(
                "attach_run_manifest",
                "run",
                run_id,
                {"manifest_id": manifest_id},
            )
        )

    return plan


def _collect_linked_manifests(ctx: StoreCtx, local_runs: list) -> tuple[list, list[str]]:
    manifest_ids: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for run in local_runs:
        for manifest_id in run.manifest_ids:
            if manifest_id in seen:
                continue
            seen.add(manifest_id)
            manifest_ids.append(manifest_id)
    records = []
    for manifest_id in manifest_ids:
        try:
            records.append(manifests.get_manifest(ctx, manifest_id))
        except StoreError as exc:
            warnings.append(f"Missing local manifest {manifest_id}: {exc}")
    return records, warnings


def _cloud_run_from_payload(payload: dict, *, include_manifests: bool) -> LocalRun:
    return LocalRun.model_validate(
        {
            "id": payload["id"],
            "project_id": payload["project_id"],
            "parent_id": payload.get("parent_id"),
            "name": payload["name"],
            "manifest_ids": payload.get("manifest_ids", []) if include_manifests else [],
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
    )


def _collect_cloud_link_scope(
    *,
    request: SyncRequest,
    source_runs: list[LocalRun],
    source_run_details: dict[str, dict],
) -> tuple[list[LocalManifest], list[LocalEpisode], list[str]]:
    if not request.include_manifests:
        return [], [], []

    config = resolve_cloud_sync_config(
        cloud_api_base=request.cloud_api_base,
        bearer_token=request.bearer_token,
        require_token=False,
    )
    warnings: list[str] = []
    try:
        with CloudPortal(config) as portal:
            manifest_ids: list[str] = []
            seen_manifest_ids: set[str] = set()
            for run in source_runs:
                for manifest_id in source_run_details[run.id].get("manifest_ids", []) or []:
                    if not manifest_id or manifest_id in seen_manifest_ids:
                        continue
                    seen_manifest_ids.add(manifest_id)
                    manifest_ids.append(manifest_id)

            linked_manifests: list[LocalManifest] = []
            linked_episodes_by_id: dict[str, LocalEpisode] = {}
            for manifest_id in manifest_ids:
                try:
                    manifest_raw = portal.fetch_manifest(manifest_id)
                    episode_summaries = portal.list_manifest_episodes(manifest_id)
                    episode_ids = [episode["id"] for episode in episode_summaries]
                    linked_manifests.append(_cloud_manifest_from_payload(manifest_raw, episode_ids))
                    for episode_payload in portal.manifest_episode_batch_get(manifest_id, episode_ids) if episode_ids else []:
                        episode = _cloud_episode_from_payload(episode_payload, manifest_id)
                        existing = linked_episodes_by_id.get(episode.id)
                        if existing is None:
                            linked_episodes_by_id[episode.id] = episode
                        elif manifest_id not in existing.manifest_ids:
                            linked_episodes_by_id[episode.id] = existing.model_copy(
                                update={"manifest_ids": [*existing.manifest_ids, manifest_id]}
                            )
                except SyncPortalError as exc:
                    # A linked manifest the caller cannot read (private + not shared)
                    # is incidental scope, not the pull target — skip it with a
                    # warning instead of aborting the whole pull. Transport/server
                    # failures (no status, 5xx) still abort.
                    if exc.status_code in (401, 403, 404):
                        warnings.append(
                            f"Skipped linked manifest {manifest_id}: not accessible "
                            f"(cloud returned {exc.status_code}); omitted from this pull."
                        )
                        continue
                    raise
            return linked_manifests, list(linked_episodes_by_id.values()), warnings
    except SyncPortalError as exc:
        raise SyncPlanError(str(exc)) from exc


def _cloud_manifest_from_payload(payload: dict, episode_ids: list[str]) -> LocalManifest:
    return LocalManifest.model_validate(
        {
            "id": payload["id"],
            "name": payload["name"],
            "description": payload.get("description"),
            "type": payload["type"],
            "tags": payload.get("tags", []),
            "is_public": bool(payload.get("is_public", False)),
            "fps": payload.get("fps"),
            "encoding": payload.get("encoding", {}),
            "features": payload.get("features", {}),
            "episode_ids": episode_ids,
            "run_ids": payload.get("run_ids", []),
            "success_rate": payload.get("success_rate"),
            "rated_episodes": payload.get("rated_episodes", 0),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
    )


def _cloud_episode_from_payload(payload: dict, manifest_id: str) -> LocalEpisode:
    files = payload.get("files", {}) or {}
    episode_payload = {
        "id": payload["id"],
        "length": payload["length"],
        "task": payload.get("task"),
        "task_description": payload.get("task_description"),
        "features": payload.get("features", {}),
        "files": {
            path: {
                "size": int(meta.get("size", 0)),
                "updated_at": None,
                "blake3": "",
            }
            for path, meta in files.items()
        },
        "size_bytes": sum(int(meta.get("size", 0)) for meta in files.values()),
        "manifest_ids": [manifest_id],
        "collection_mode": payload.get("collection_mode"),
        "source_project_id": payload.get("source_project_id"),
        "source_run_id": payload.get("source_run_id"),
        "source_checkpoint": payload.get("source_checkpoint"),
        "policy_name": payload.get("policy_name"),
        "reward": payload.get("reward"),
    }
    if payload.get("created_at") is not None:
        episode_payload["created_at"] = payload["created_at"]
    return LocalEpisode.model_validate(episode_payload)


def _append_pull_linked_manifest_actions(ctx: StoreCtx, plan: SyncPlan) -> None:
    for manifest in plan.scope.manifests:
        try:
            manifests.get_manifest(ctx, manifest.id)
            operation = "update_local"
        except StoreError:
            operation = "create_local"
        plan.metadata_actions.append(
            MetadataAction(
                operation,
                "manifest",
                manifest.id,
                {
                    "name": manifest.name,
                    "description": manifest.description,
                    "type": manifest.type,
                    "tags": list(manifest.tags),
                    "is_public": bool(manifest.is_public),
                    "fps": manifest.fps,
                    "encoding": dict(manifest.encoding),
                    "features": dict(manifest.features),
                    "episode_ids": list(manifest.episode_ids),
                    "run_ids": list(manifest.run_ids),
                    "success_rate": manifest.success_rate,
                    "rated_episodes": manifest.rated_episodes,
                    "created_at": manifest.created_at.isoformat(),
                    "updated_at": manifest.updated_at.isoformat(),
                },
            )
        )

    seen_episode_ids: set[str] = set()
    for episode in plan.scope.episodes:
        if episode.id in seen_episode_ids:
            continue
        seen_episode_ids.add(episode.id)
        try:
            episodes.get_episode(ctx, episode.id)
            operation = "update_local"
        except StoreError:
            operation = "create_local"
        plan.metadata_actions.append(
            MetadataAction(
                operation,
                "episode",
                episode.id,
                {
                    "length": episode.length,
                    "task": episode.task,
                    "task_description": episode.task_description,
                    "features": dict(episode.features),
                    "files": dict(episode.files),
                    "size_bytes": episode.size_bytes,
                    "manifest_ids": list(episode.manifest_ids),
                    "collection_mode": episode.collection_mode,
                    "source_project_id": episode.source_project_id,
                    "source_run_id": episode.source_run_id,
                    "source_checkpoint": episode.source_checkpoint,
                    "policy_name": episode.policy_name,
                    "reward": episode.reward,
                    "created_at": episode.created_at.isoformat(),
                },
            )
        )
        for path, meta in sorted(episode.files.items()):
            plan.file_actions.append(
                FileAction(
                    "download",
                    "episode",
                    episode.id,
                    path,
                    int(meta.get("size", 0)),
                    source_entity_id=episode.id,
                    source_path=path,
                )
            )

    linked_episode_ids_by_manifest: dict[str, list[str]] = {}
    for episode in plan.scope.episodes:
        for manifest_id in episode.manifest_ids:
            linked_episode_ids_by_manifest.setdefault(manifest_id, [])
            if episode.id not in linked_episode_ids_by_manifest[manifest_id]:
                linked_episode_ids_by_manifest[manifest_id].append(episode.id)
    for manifest_id, episode_ids in linked_episode_ids_by_manifest.items():
        plan.link_actions.append(
            LinkAction(
                "attach_manifest_episodes_local",
                "manifest",
                manifest_id,
                {"episode_ids": episode_ids},
            )
        )


def _run_depth(run, all_runs: list) -> int:
    by_id = {item.id: item for item in all_runs}
    depth = 0
    current = run.parent_id
    while current is not None:
        parent = by_id.get(current)
        if parent is None:
            break
        depth += 1
        current = parent.parent_id
    return depth


def _is_descendant(run, ancestor_id: str, by_id: dict[str, object]) -> bool:
    current = run.parent_id
    while current is not None:
        if current == ancestor_id:
            return True
        current_run = by_id.get(current)
        current = current_run.parent_id if current_run is not None else None
    return False
