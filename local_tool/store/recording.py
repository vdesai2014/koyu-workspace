from __future__ import annotations

from ..io import StoreError
from ..models import RecordingContext, utc_now
from .manifests import create_manifest, get_manifest, list_manifests
from .projects import StoreCtx
from .runs import get_run


def ensure_manifest_for_recording(ctx: StoreCtx, recording: RecordingContext) -> RecordingContext:
    manifest_type = recording.manifest_type
    if recording.source_run_id:
        get_run(ctx, recording.source_run_id)

    manifest = None
    if recording.manifest_id:
        try:
            manifest = get_manifest(ctx, recording.manifest_id)
        except StoreError as exc:
            if exc.code != "NOT_FOUND":
                raise
            if not recording.manifest_name or not manifest_type:
                raise StoreError(
                    "Creating a manifest with a fixed manifest_id requires manifest_name and manifest_type",
                    "CONFLICT",
                ) from exc
            manifest = create_manifest(
                ctx,
                manifest_id=recording.manifest_id,
                name=recording.manifest_name,
                type=manifest_type,
                fps=recording.fps,
            )
    elif recording.manifest_name:
        manifest = next((item for item in list_manifests(ctx) if item.name == recording.manifest_name), None)
        if manifest is None:
            if not manifest_type:
                raise StoreError("Creating a new manifest requires manifest_type", "CONFLICT")
            manifest = create_manifest(
                ctx,
                name=recording.manifest_name,
                type=manifest_type,
                fps=recording.fps,
            )
    else:
        raise StoreError("Recording context must include manifest_id or manifest_name", "CONFLICT")

    assert manifest is not None

    if manifest_type and manifest.type != manifest_type:
        raise StoreError(
            f"Manifest {manifest.id} has type '{manifest.type}', not '{manifest_type}'",
            "CONFLICT",
        )

    if recording.manifest_name and manifest.name != recording.manifest_name:
        raise StoreError(
            f"Manifest {manifest.id} has name '{manifest.name}', not '{recording.manifest_name}'",
            "CONFLICT",
        )

    return RecordingContext(
        manifest_id=manifest.id,
        manifest_name=manifest.name,
        manifest_type=manifest.type,
        task=recording.task,
        task_description=recording.task_description,
        source_project_id=recording.source_project_id,
        source_run_id=recording.source_run_id,
        source_checkpoint=recording.source_checkpoint,
        policy_name=recording.policy_name,
        fps=recording.fps if recording.fps is not None else manifest.fps,
        updated_at=utc_now(),
        updated_by=recording.updated_by,
    )
