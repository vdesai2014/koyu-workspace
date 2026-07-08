from __future__ import annotations

from ..io import StoreError
from ..models import LocalManifest, LocalRun
from . import manifests, runs
from .projects import StoreCtx


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def list_run_manifests(ctx: StoreCtx, run_id: str) -> list[LocalManifest]:
    run = runs.get_run(ctx, run_id)
    records: list[LocalManifest] = []
    missing: list[str] = []
    for manifest_id in run.manifest_ids:
        try:
            records.append(manifests.get_manifest(ctx, manifest_id))
        except StoreError:
            missing.append(manifest_id)
    if missing:
        raise StoreError(f"Run {run_id} references missing local manifests: {', '.join(missing)}", "NOT_FOUND")
    records.sort(key=lambda manifest: (manifest.updated_at, manifest.id), reverse=True)
    return records


def list_manifest_runs(ctx: StoreCtx, manifest_id: str) -> list[LocalRun]:
    manifest = manifests.get_manifest(ctx, manifest_id)
    records: list[LocalRun] = []
    missing: list[str] = []
    for run_id in manifest.run_ids:
        try:
            records.append(runs.get_run(ctx, run_id))
        except StoreError:
            missing.append(run_id)
    if missing:
        raise StoreError(f"Manifest {manifest_id} references missing local runs: {', '.join(missing)}", "NOT_FOUND")
    records.sort(key=lambda run: (run.created_at, run.id), reverse=True)
    return records


def add_run_manifest(ctx: StoreCtx, run_id: str, manifest_id: str) -> dict[str, str]:
    run = runs.get_run(ctx, run_id)
    manifest = manifests.get_manifest(ctx, manifest_id)

    if manifest_id not in run.manifest_ids:
        runs.update_run(ctx, run_id, manifest_ids=_dedupe([*run.manifest_ids, manifest_id]))
    if run_id not in manifest.run_ids:
        manifests.update_manifest(ctx, manifest_id, run_ids=_dedupe([*manifest.run_ids, run_id]))

    return {"run_id": run_id, "manifest_id": manifest_id}


def remove_run_manifest(ctx: StoreCtx, run_id: str, manifest_id: str) -> None:
    run = runs.get_run(ctx, run_id)
    manifest = manifests.get_manifest(ctx, manifest_id)

    if manifest_id in run.manifest_ids:
        runs.update_run(
            ctx,
            run_id,
            manifest_ids=[value for value in run.manifest_ids if value != manifest_id],
        )
    if run_id in manifest.run_ids:
        manifests.update_manifest(
            ctx,
            manifest_id,
            run_ids=[value for value in manifest.run_ids if value != run_id],
        )
