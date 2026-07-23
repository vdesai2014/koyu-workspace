from __future__ import annotations
"""Sync execution.

This module applies a previously built plan in ordered phases. Remote changes go
through CloudPortal. Cloud-sourced clone/pull support that needs local skeleton
creation goes through store APIs, not ad hoc filesystem writes.
"""

from pathlib import Path, PurePosixPath

from ..ids import generate_id
from ..io import StoreError
from ..store import episodes, manifests, projects, run_manifests, runs
from ..store.projects import StoreCtx
from .cloud_portal import CloudPortal, CloudSyncConfig
from .models import SyncPlan, SyncResult
from .progress import NoopSyncProgressReporter, SyncProgressReporter


class SyncExecError(Exception):
    pass


def _safe_download_path(base_dir: Path, relative_path: str, *, entity_type: str) -> Path:
    rel = PurePosixPath(relative_path)
    if not relative_path or rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise SyncExecError(f"Invalid {entity_type} file path from cloud: {relative_path!r}")

    base = base_dir.resolve()
    target = (base / Path(*rel.parts)).resolve()
    if base not in target.parents:
        raise SyncExecError(f"Cloud {entity_type} file path escapes local store root: {relative_path!r}")
    return target


def _ensure_clone_id_remaps(plan: SyncPlan) -> dict[str, dict[str, str]]:
    """Mint execution-time clone IDs if the plan is structural.

    `/sync/plan` intentionally does not mint concrete clone IDs. Direct
    execution builds that same structural plan, then this boundary function
    assigns the authoritative local IDs used for store creation and path
    rewrites.
    """
    if plan.id_remaps.get("projects") and plan.id_remaps.get("runs") is not None:
        return plan.id_remaps

    if plan.scope.project is None:
        raise SyncExecError("Clone execution requires a project in scope")

    run_ids = [run.id for run in plan.scope.runs]
    remaps = {
        "projects": {plan.scope.project.id: generate_id("proj")},
        "runs": {run_id: generate_id("run") for run_id in run_ids},
    }
    plan.id_remaps = remaps
    return remaps


def execute_sync_plan(
    ctx: StoreCtx,
    plan: SyncPlan,
    config: CloudSyncConfig | None = None,
    *,
    progress_reporter: SyncProgressReporter | None = None,
) -> SyncResult:
    """Execute the currently supported sync flow."""
    reporter = progress_reporter or NoopSyncProgressReporter()
    if plan.request.operation == "push":
        if plan.request.entity_type not in {"project", "run", "manifest"}:
            raise SyncExecError(f"Execution currently supports project/run/manifest push only, got {plan.request.entity_type}")
        if config is None:
            raise SyncExecError("Push execution requires cloud config")
        return _execute_push_plan(ctx, plan, config, reporter)
    if plan.request.operation == "clone":
        if plan.request.entity_type != "project":
            raise SyncExecError(f"Execution currently supports project clone only, got {plan.request.entity_type}")
        if config is None:
            raise SyncExecError("Clone execution requires cloud config")
        return _execute_clone_plan(ctx, plan, config, reporter)
    if plan.request.operation == "pull":
        if plan.request.entity_type not in {"project", "run", "manifest"}:
            raise SyncExecError(f"Execution currently supports project/run/manifest pull only, got {plan.request.entity_type}")
        if config is None:
            raise SyncExecError("Pull execution requires cloud config")
        return _execute_pull_plan(ctx, plan, config, reporter)
    raise SyncExecError(f"Unsupported sync operation for now: {plan.request.operation}")


def _execute_push_plan(ctx: StoreCtx, plan: SyncPlan, config: CloudSyncConfig, reporter: SyncProgressReporter) -> SyncResult:
    created = {"projects": 0, "runs": 0, "manifests": 0, "episodes": 0}
    patched = {"projects": 0, "runs": 0, "manifests": 0, "run_manifest_links": 0}
    uploaded = {"project_files": 0, "run_files": 0, "episode_files": 0}
    copied: dict[str, int] = {}
    warnings = list(plan.warnings)
    events: list[str] = [
        f"plan scope project={plan.scope.project.id if plan.scope.project else None} runs={len(plan.scope.runs)} manifests={len(plan.scope.manifests)} episodes={len(plan.scope.episodes)}",
        f"plan actions metadata={len(plan.metadata_actions)} files={len(plan.file_actions)} links={len(plan.link_actions)}",
    ]

    with CloudPortal(config) as portal:
        project = plan.scope.project
        if plan.request.entity_type in {"project", "run"} and project is None:
            raise SyncExecError("Project push requires a project in scope")

        if project is not None:
            events.append(f"metadata ensure project {project.id}")
            if portal.ensure_project(project):
                created["projects"] += 1
            reporter.event("metadata", "done", "ensure project", operation="ensure_remote", entity_type="project", entity_id=project.id)
            events.append(f"metadata patch project {project.id}")
            portal.patch_project(project)
            patched["projects"] += 1
            reporter.event("metadata", "done", "patch project", operation="patch_remote", entity_type="project", entity_id=project.id)

            if plan.request.entity_type == "project":
                events.append(f"files upload project {project.id}")
                allowed_project_paths = {
                    action.path
                    for action in plan.file_actions
                    if action.entity_type == "project" and action.entity_id == project.id
                }
                uploaded["project_files"] += portal.sync_entity_files(
                    files={
                        path: meta
                        for path, meta in projects.project_file_records(ctx, project.id).items()
                        if path in allowed_project_paths
                    },
                    absolute_path_for=lambda relative_path: projects.get_project_file_path(ctx, project.id, relative_path),
                    upload_path=f"/api/projects/{project.id}/files/upload",
                    commit_path=f"/api/projects/{project.id}/files/commit",
                    on_file_event=lambda status, path, size, project_id=project.id: reporter.event(
                        "file",
                        status,
                        f"upload project {path}",
                        operation="upload",
                        entity_type="project",
                        entity_id=project_id,
                        path=path,
                        size=size,
                    ),
                )

            for run in plan.scope.runs:
                events.append(f"metadata ensure run {run.id}")
                if portal.ensure_run(run):
                    created["runs"] += 1
                reporter.event("metadata", "done", "ensure run", operation="ensure_remote", entity_type="run", entity_id=run.id)
                events.append(f"metadata patch run {run.id}")
                portal.patch_run(run)
                patched["runs"] += 1
                reporter.event("metadata", "done", "patch run", operation="patch_remote", entity_type="run", entity_id=run.id)
                events.append(f"files upload run {run.id}")
                allowed_run_paths = {
                    action.path
                    for action in plan.file_actions
                    if action.entity_type == "run" and action.entity_id == run.id
                }
                uploaded["run_files"] += portal.sync_entity_files(
                    files={
                        path: meta
                        for path, meta in runs.run_file_records(ctx, run.id).items()
                        if path in allowed_run_paths
                    },
                    absolute_path_for=lambda relative_path, run_id=run.id: runs.get_run_file_path(ctx, run_id, relative_path),
                    upload_path=f"/api/runs/{run.id}/files/upload",
                    commit_path=f"/api/runs/{run.id}/files/commit",
                    on_file_event=lambda status, path, size, run_id=run.id: reporter.event(
                        "file",
                        status,
                        f"upload run {path}",
                        operation="upload",
                        entity_type="run",
                        entity_id=run_id,
                        path=path,
                        size=size,
                    ),
                )

        for manifest in plan.scope.manifests:
            events.append(f"metadata ensure manifest {manifest.id}")
            if portal.ensure_manifest(manifest):
                created["manifests"] += 1
            reporter.event("metadata", "done", "ensure manifest", operation="ensure_remote", entity_type="manifest", entity_id=manifest.id)
            events.append(f"metadata patch manifest {manifest.id}")
            portal.patch_manifest(manifest)
            patched["manifests"] += 1
            reporter.event("metadata", "done", "patch manifest", operation="patch_remote", entity_type="manifest", entity_id=manifest.id)

            episode_result = _sync_manifest_episodes(ctx, portal, manifest.id, events, reporter)
            created["episodes"] += episode_result["created_episodes"]
            uploaded["episode_files"] += episode_result["uploaded_files"]

        for action in plan.link_actions:
            if action.operation != "attach_run_manifest":
                continue
            manifest_id = action.payload.get("manifest_id")
            if not manifest_id:
                continue
            events.append(f"links attach run {action.entity_id} manifest {manifest_id}")
            portal.add_run_manifest(action.entity_id, manifest_id)
            patched["run_manifest_links"] += 1
            reporter.event(
                "link",
                "done",
                "attach run manifest",
                operation="attach_run_manifest",
                entity_type="run",
                entity_id=action.entity_id,
                manifest_id=manifest_id,
            )

    return SyncResult(
        success=True,
        request=plan.request,
        plan=plan,
        created=created,
        patched=patched,
        uploaded=uploaded,
        copied=copied,
        warnings=warnings,
        events=events,
    )


def _sync_manifest_episodes(
    ctx: StoreCtx,
    portal: CloudPortal,
    manifest_id: str,
    events: list[str],
    reporter: SyncProgressReporter,
) -> dict[str, int]:
    """Upload manifest episodes and attach them to the remote manifest."""
    manifest = manifests.get_manifest(ctx, manifest_id)
    local_episodes = manifests.list_manifest_episodes(ctx, manifest_id)
    if not local_episodes:
        reporter.event(
            "link",
            "done",
            "attach manifest episodes",
            operation="attach_manifest_episodes",
            entity_type="manifest",
            entity_id=manifest.id,
            episode_count=0,
        )
        return {"created_episodes": 0, "uploaded_files": 0}

    events.append(f"episodes plan manifest {manifest_id} count={len(local_episodes)}")
    upload_response = portal.plan_episode_upload(
        [
            {
                "id": episode.id,
                "length": episode.length,
                "recorded_at": episode.recorded_at.isoformat(),
                "record_hz": episode.record_hz,
                "task": episode.task or manifest.type,
                "task_description": episode.task_description,
                "collection_mode": episode.collection_mode,
                "source_project_id": episode.source_project_id,
                "source_run_id": episode.source_run_id,
                "source_checkpoint": episode.source_checkpoint,
                "policy_name": episode.policy_name,
                "reward": episode.reward,
                "features": episode.features,
                "files": {
                    path: {
                        "blake3": meta["blake3"],
                        "size": int(meta["size"]),
                    }
                    for path, meta in episode.files.items()
                },
            }
            for episode in local_episodes
        ]
    )
    if upload_response.get("errors"):
        raise SyncExecError(f"Episode upload planning failed for manifest {manifest_id}: {upload_response['errors']}")

    uploaded_files = 0
    pending_upload_ids: list[str] = []
    planned_upload_paths = {
        (episode_id, relative_path)
        for episode_id, entry in upload_response.get("new", {}).items()
        for relative_path in entry.get("files", {})
    }
    for episode in local_episodes:
        for relative_path, meta in episode.files.items():
            if (episode.id, relative_path) in planned_upload_paths:
                continue
            reporter.event(
                "file",
                "skipped",
                f"upload episode {relative_path}",
                operation="upload",
                entity_type="episode",
                entity_id=episode.id,
                path=relative_path,
                size=int(meta.get("size", 0)),
            )
    for episode_id, entry in upload_response.get("new", {}).items():
        for relative_path, plan in entry.get("files", {}).items():
            absolute_path = episodes.get_episode_file_path(ctx, episode_id, relative_path)
            size = int(absolute_path.stat().st_size)
            reporter.event(
                "file",
                "started",
                f"upload episode {relative_path}",
                operation="upload",
                entity_type="episode",
                entity_id=episode_id,
                path=relative_path,
                size=size,
            )
            portal._upload_file_to_presigned_target(absolute_path, plan)
            reporter.event(
                "file",
                "done",
                f"upload episode {relative_path}",
                operation="upload",
                entity_type="episode",
                entity_id=episode_id,
                path=relative_path,
                size=size,
            )
            uploaded_files += 1
            events.append(f"episodes upload {episode_id}:{relative_path}")
        pending_upload_ids.extend(entry.get("pending_upload_ids", []))

    portal.commit_episode_uploads(pending_upload_ids)
    portal.add_manifest_episodes(manifest.id, [episode.id for episode in local_episodes])
    reporter.event("link", "done", "attach manifest episodes", operation="attach_manifest_episodes", entity_type="manifest", entity_id=manifest.id)
    events.append(f"episodes attach manifest {manifest.id}")
    return {
        "created_episodes": len(upload_response.get("new", {})),
        "uploaded_files": uploaded_files,
    }


def _execute_clone_plan(ctx: StoreCtx, plan: SyncPlan, config: CloudSyncConfig, reporter: SyncProgressReporter) -> SyncResult:
    created = {"projects": 0, "runs": 0, "manifests": 0, "episodes": 0}
    patched = {"projects": 0, "runs": 0, "manifests": 0, "run_manifest_links": 0}
    uploaded = {"project_files": 0, "run_files": 0, "episode_files": 0}
    copied = {"project_files": 0, "run_files": 0}
    warnings = list(plan.warnings)
    events: list[str] = [
        f"plan scope project={plan.scope.project.id if plan.scope.project else None} runs={len(plan.scope.runs)}",
        f"plan actions metadata={len(plan.metadata_actions)} files={len(plan.file_actions)} links={len(plan.link_actions)}",
    ]

    project_action = next(
        (action for action in plan.metadata_actions if action.operation == "create_local_clone" and action.entity_type == "project"),
        None,
    )
    if project_action is None:
        raise SyncExecError("Clone execution requires a project clone action")
    id_remaps = _ensure_clone_id_remaps(plan)
    project_remaps = id_remaps.get("projects", {})
    run_remaps = id_remaps.get("runs", {})
    source_project_id = project_action.payload.get("source_project_id") or project_action.entity_id
    target_project_id = project_remaps.get(source_project_id)
    if target_project_id is None:
        raise SyncExecError(f"Missing clone project remap for {source_project_id}")

    target_project = projects.create_project(
        ctx,
        name=project_action.payload["name"],
        description=project_action.payload.get("description"),
        tags=project_action.payload.get("tags"),
        is_public=bool(project_action.payload.get("is_public", False)),
        cloned_source_project_id=project_action.payload.get("cloned_source_project_id") or source_project_id,
        project_id=target_project_id,
        created_at=project_action.payload.get("created_at"),
        updated_at=project_action.payload.get("updated_at"),
    )
    created["projects"] += 1
    reporter.event("metadata", "done", "create local project", operation="create_local_clone", entity_type="project", entity_id=target_project.id)
    events.append(f"local create project {target_project.id}")

    run_actions = [
        action
        for action in plan.metadata_actions
        if action.operation == "create_local_clone" and action.entity_type == "run"
    ]
    for action in run_actions:
        source_run_id = action.payload.get("source_run_id") or action.entity_id
        target_run_id = run_remaps.get(source_run_id)
        if target_run_id is None:
            raise SyncExecError(f"Missing clone run remap for {source_run_id}")
        source_parent_id = action.payload.get("parent_id")
        target_parent_id = run_remaps.get(source_parent_id) if source_parent_id is not None else None
        cloned_run = runs.create_run(
            ctx,
            project_id=target_project_id,
            name=action.payload["name"],
            parent_id=target_parent_id,
            run_id=target_run_id,
            created_at=action.payload.get("created_at"),
            updated_at=action.payload.get("updated_at"),
        )
        created["runs"] += 1
        reporter.event("metadata", "done", "create local run", operation="create_local_clone", entity_type="run", entity_id=cloned_run.id)
        events.append(f"local create run {cloned_run.id}")

    with CloudPortal(config) as portal:
        project_paths = sorted({
            action.source_path
            for action in plan.file_actions
            if action.entity_type == "project" and action.source_path
        })
        project_urls = (
            portal.project_download_urls(plan.scope.project.id, project_paths)
            if plan.scope.project is not None and project_paths
            else {}
        )
        run_urls: dict[str, dict[str, str]] = {}
        for run in plan.scope.runs:
            run_paths = sorted({
                action.source_path
                for action in plan.file_actions
                if action.entity_type == "run" and action.source_entity_id == run.id and action.source_path
            })
            if run_paths:
                run_urls[run.id] = portal.run_download_urls(run.id, run_paths)

        for action in plan.file_actions:
            if action.operation != "copy" or action.source_path is None or action.source_entity_id is None:
                continue
            if action.entity_type == "project":
                url = project_urls[action.source_path]
                target_entity_id = project_remaps.get(action.source_entity_id)
                if target_entity_id is None:
                    raise SyncExecError(f"Missing clone project remap for {action.source_entity_id}")
                target_path = _safe_download_path(
                    projects.get_project_dir(ctx, target_entity_id),
                    action.path,
                    entity_type="project",
                )
                copied["project_files"] += 1
            elif action.entity_type == "run":
                url = run_urls[action.source_entity_id][action.source_path]
                target_entity_id = run_remaps.get(action.source_entity_id)
                if target_entity_id is None:
                    raise SyncExecError(f"Missing clone run remap for {action.source_entity_id}")
                target_path = _safe_download_path(
                    runs.get_run_dir(ctx, target_entity_id),
                    action.path,
                    entity_type="run",
                )
                copied["run_files"] += 1
            else:
                raise SyncExecError(f"Unsupported clone file entity type: {action.entity_type}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            reporter.event(
                "file",
                "started",
                f"copy {action.entity_type} {action.path}",
                operation="copy",
                entity_type=action.entity_type,
                entity_id=target_entity_id,
                source_entity_id=action.source_entity_id,
                path=action.path,
                source_path=action.source_path,
                size=action.size,
            )
            target_path.write_bytes(portal.download_bytes(url))
            reporter.event(
                "file",
                "done",
                f"copy {action.entity_type} {action.path}",
                operation="copy",
                entity_type=action.entity_type,
                entity_id=target_entity_id,
                source_entity_id=action.source_entity_id,
                path=action.path,
                source_path=action.source_path,
                size=action.size,
            )
            events.append(
                f"local copy {action.entity_type} {action.source_entity_id}:{action.source_path} -> {target_entity_id}:{action.path}"
            )

    return SyncResult(
        success=True,
        request=plan.request,
        plan=plan,
        created=created,
        patched=patched,
        uploaded=uploaded,
        copied=copied,
        warnings=warnings,
        events=events,
    )


def _execute_pull_plan(ctx: StoreCtx, plan: SyncPlan, config: CloudSyncConfig, reporter: SyncProgressReporter) -> SyncResult:
    created = {"projects": 0, "runs": 0, "manifests": 0, "episodes": 0}
    patched = {"projects": 0, "runs": 0, "manifests": 0, "run_manifest_links": 0}
    uploaded = {"project_files": 0, "run_files": 0, "episode_files": 0}
    copied = {"project_files": 0, "run_files": 0, "episode_files": 0}
    warnings = list(plan.warnings)
    events: list[str] = [
        f"plan scope project={plan.scope.project.id if plan.scope.project else None} runs={len(plan.scope.runs)}",
        f"plan actions metadata={len(plan.metadata_actions)} files={len(plan.file_actions)} links={len(plan.link_actions)}",
    ]

    project_action = next((action for action in plan.metadata_actions if action.entity_type == "project"), None)
    if plan.request.entity_type in {"project", "run"}:
        if project_action is None or plan.scope.project is None:
            raise SyncExecError("Pull execution requires a project action and project scope")

        if project_action.operation == "create_local":
            projects.create_project(
                ctx,
                name=project_action.payload["name"],
                description=project_action.payload.get("description"),
                tags=project_action.payload.get("tags"),
                is_public=bool(project_action.payload.get("is_public", False)),
                cloned_source_project_id=project_action.payload.get("cloned_source_project_id"),
                project_id=project_action.entity_id,
                created_at=project_action.payload.get("created_at"),
                updated_at=project_action.payload.get("updated_at"),
            )
            created["projects"] += 1
            reporter.event("metadata", "done", "create local project", operation="create_local", entity_type="project", entity_id=project_action.entity_id)
            events.append(f"local create project {project_action.entity_id}")
        else:
            projects.update_project(
                ctx,
                project_action.entity_id,
                name=project_action.payload.get("name"),
                description=project_action.payload.get("description"),
                tags=project_action.payload.get("tags"),
                is_public=project_action.payload.get("is_public"),
                cloned_source_project_id=project_action.payload.get("cloned_source_project_id"),
                created_at=project_action.payload.get("created_at"),
                updated_at=project_action.payload.get("updated_at"),
            )
            patched["projects"] += 1
            reporter.event("metadata", "done", "update local project", operation="update_local", entity_type="project", entity_id=project_action.entity_id)
            events.append(f"local update project {project_action.entity_id}")

    run_actions = [
        action
        for action in plan.metadata_actions
        if action.entity_type == "run"
    ]
    for action in run_actions:
        if action.operation == "create_local":
            runs.create_run(
                ctx,
                project_id=action.payload["project_id"],
                name=action.payload["name"],
                parent_id=action.payload.get("parent_id"),
                manifest_ids=action.payload.get("manifest_ids"),
                run_id=action.entity_id,
                created_at=action.payload.get("created_at"),
                updated_at=action.payload.get("updated_at"),
            )
            created["runs"] += 1
            reporter.event("metadata", "done", "create local run", operation="create_local", entity_type="run", entity_id=action.entity_id)
            events.append(f"local create run {action.entity_id}")
        else:
            run_updates = {
                "name": action.payload.get("name"),
                "parent_id": action.payload.get("parent_id"),
                "updated_at": action.payload.get("updated_at"),
            }
            if "manifest_ids" in action.payload:
                run_updates["manifest_ids"] = action.payload["manifest_ids"]
            runs.update_run(ctx, action.entity_id, **run_updates)
            patched["runs"] += 1
            reporter.event("metadata", "done", "update local run", operation="update_local", entity_type="run", entity_id=action.entity_id)
            events.append(f"local update run {action.entity_id}")

    manifest_actions = [action for action in plan.metadata_actions if action.entity_type == "manifest"]
    for action in manifest_actions:
        if action.operation == "create_local":
            manifests.create_manifest(
                ctx,
                name=action.payload["name"],
                type=action.payload["type"],
                description=action.payload.get("description"),
                tags=action.payload.get("tags"),
                is_public=bool(action.payload.get("is_public", False)),
                fps=action.payload.get("fps"),
                encoding=action.payload.get("encoding"),
                features=action.payload.get("features"),
                episode_ids=action.payload.get("episode_ids"),
                run_ids=action.payload.get("run_ids"),
                success_rate=action.payload.get("success_rate"),
                rated_episodes=action.payload.get("rated_episodes", 0),
                manifest_id=action.entity_id,
                created_at=action.payload.get("created_at"),
                updated_at=action.payload.get("updated_at"),
            )
            created["manifests"] += 1
            reporter.event("metadata", "done", "create local manifest", operation="create_local", entity_type="manifest", entity_id=action.entity_id)
            events.append(f"local create manifest {action.entity_id}")
        else:
            manifest_updates = {
                "name": action.payload.get("name"),
                "description": action.payload.get("description"),
                "type": action.payload.get("type"),
                "tags": action.payload.get("tags"),
                "is_public": action.payload.get("is_public"),
                "fps": action.payload.get("fps"),
                "encoding": action.payload.get("encoding"),
                "features": action.payload.get("features"),
                "run_ids": action.payload.get("run_ids"),
                "success_rate": action.payload.get("success_rate"),
                "rated_episodes": action.payload.get("rated_episodes"),
                "updated_at": action.payload.get("updated_at"),
            }
            manifests.update_manifest(ctx, action.entity_id, **manifest_updates)
            patched["manifests"] += 1
            reporter.event("metadata", "done", "update local manifest", operation="update_local", entity_type="manifest", entity_id=action.entity_id)
            events.append(f"local update manifest {action.entity_id}")

        for run_id in action.payload.get("run_ids", []) or []:
            try:
                run_manifests.add_run_manifest(ctx, run_id, action.entity_id)
            except StoreError:
                continue
            patched["run_manifest_links"] += 1
            reporter.event(
                "link",
                "done",
                "attach local run manifest",
                operation="attach_run_manifest_local",
                entity_type="run",
                entity_id=run_id,
                manifest_id=action.entity_id,
            )

    episode_actions = [action for action in plan.metadata_actions if action.entity_type == "episode"]
    for action in episode_actions:
        if action.operation == "create_local":
            episodes.create_episode(
                ctx,
                length=action.payload["length"],
                recorded_at=action.payload["recorded_at"],
                record_hz=action.payload.get("record_hz"),
                task=action.payload.get("task"),
                task_description=action.payload.get("task_description"),
                features=action.payload.get("features"),
                collection_mode=action.payload.get("collection_mode"),
                source_project_id=action.payload.get("source_project_id"),
                source_run_id=action.payload.get("source_run_id"),
                source_checkpoint=action.payload.get("source_checkpoint"),
                policy_name=action.payload.get("policy_name"),
                reward=action.payload.get("reward"),
                files=action.payload.get("files"),
                size_bytes=action.payload.get("size_bytes"),
                episode_id=action.entity_id,
            )
            created["episodes"] += 1
            reporter.event("metadata", "done", "create local episode", operation="create_local", entity_type="episode", entity_id=action.entity_id)
            events.append(f"local create episode {action.entity_id}")
        else:
            episode_updates = {
                "length": action.payload.get("length"),
                "recorded_at": action.payload.get("recorded_at"),
                "record_hz": action.payload.get("record_hz"),
                "task": action.payload.get("task"),
                "task_description": action.payload.get("task_description"),
                "features": action.payload.get("features"),
                "files": action.payload.get("files"),
                "size_bytes": action.payload.get("size_bytes"),
                "collection_mode": action.payload.get("collection_mode"),
                "source_project_id": action.payload.get("source_project_id"),
                "source_run_id": action.payload.get("source_run_id"),
                "source_checkpoint": action.payload.get("source_checkpoint"),
                "policy_name": action.payload.get("policy_name"),
                "reward": action.payload.get("reward"),
            }
            episodes.update_episode(ctx, action.entity_id, **episode_updates)
            reporter.event("metadata", "done", "update local episode", operation="update_local", entity_type="episode", entity_id=action.entity_id)
            events.append(f"local update episode {action.entity_id}")

    with CloudPortal(config) as portal:
        project_paths = sorted({
            action.source_path
            for action in plan.file_actions
            if action.entity_type == "project" and action.source_path
        })
        project_urls = (
            portal.project_download_urls(plan.scope.project.id, project_paths)
            if project_paths
            and plan.scope.project is not None
            else {}
        )
        run_urls: dict[str, dict[str, str]] = {}
        for run in plan.scope.runs:
            run_paths = sorted({
                action.source_path
                for action in plan.file_actions
                if action.entity_type == "run" and action.source_entity_id == run.id and action.source_path
            })
            if run_paths:
                run_urls[run.id] = portal.run_download_urls(run.id, run_paths)
        episode_urls: dict[str, dict[str, str]] = {}
        episodes_by_manifest: dict[str, list[str]] = {}
        for episode in plan.scope.episodes:
            for manifest_id in episode.manifest_ids:
                episodes_by_manifest.setdefault(manifest_id, [])
                if episode.id not in episodes_by_manifest[manifest_id]:
                    episodes_by_manifest[manifest_id].append(episode.id)
        for manifest in plan.scope.manifests:
            episode_details = portal.manifest_episode_batch_get(
                manifest.id,
                episodes_by_manifest.get(manifest.id, []),
            ) if episodes_by_manifest.get(manifest.id) else []
            for episode_detail in episode_details:
                episode_urls[episode_detail["id"]] = {
                    path: meta["url"]
                    for path, meta in (episode_detail.get("files") or {}).items()
                }

        for action in plan.file_actions:
            if action.operation != "download" or action.source_path is None or action.source_entity_id is None:
                continue
            if action.entity_type == "project":
                url = project_urls[action.source_path]
                target_path = _safe_download_path(
                    projects.get_project_dir(ctx, action.entity_id),
                    action.path,
                    entity_type="project",
                )
                copied["project_files"] += 1
            elif action.entity_type == "run":
                url = run_urls[action.source_entity_id][action.source_path]
                target_path = _safe_download_path(
                    runs.get_run_dir(ctx, action.entity_id),
                    action.path,
                    entity_type="run",
                )
                copied["run_files"] += 1
            elif action.entity_type == "episode":
                url = episode_urls[action.source_entity_id][action.source_path]
                target_path = _safe_download_path(
                    episodes.get_episode_dir(ctx, action.entity_id),
                    action.path,
                    entity_type="episode",
                )
                copied["episode_files"] += 1
            else:
                raise SyncExecError(f"Unsupported pull file entity type: {action.entity_type}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            reporter.event(
                "file",
                "started",
                f"download {action.entity_type} {action.path}",
                operation="download",
                entity_type=action.entity_type,
                entity_id=action.entity_id,
                source_entity_id=action.source_entity_id,
                path=action.path,
                source_path=action.source_path,
                size=action.size,
            )
            target_path.write_bytes(portal.download_bytes(url))
            reporter.event(
                "file",
                "done",
                f"download {action.entity_type} {action.path}",
                operation="download",
                entity_type=action.entity_type,
                entity_id=action.entity_id,
                source_entity_id=action.source_entity_id,
                path=action.path,
                source_path=action.source_path,
                size=action.size,
            )
            events.append(
                f"local download {action.entity_type} {action.source_entity_id}:{action.source_path} -> {action.entity_id}:{action.path}"
            )

    for action in plan.link_actions:
        if action.operation != "attach_manifest_episodes_local":
            continue
        manifests.add_manifest_episodes(ctx, action.entity_id, action.payload.get("episode_ids", []))
        reporter.event("link", "done", "attach manifest episodes local", operation=action.operation, entity_type=action.entity_type, entity_id=action.entity_id)
        events.append(f"local attach manifest {action.entity_id} episodes={len(action.payload.get('episode_ids', []))}")

    return SyncResult(
        success=True,
        request=plan.request,
        plan=plan,
        created=created,
        patched=patched,
        uploaded=uploaded,
        copied=copied,
        warnings=warnings,
        events=events,
    )
