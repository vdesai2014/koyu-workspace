"""Outbox ingestion: sweep the runtime's data-recordings/ outbox and file each
episode bundle into the store.

The runtime/workspace boundary is the bundle format itself — a directory of
data files plus an episode.json sidecar, committed by the recorder with an
atomic rename. A directory in the outbox not prefixed ".tmp-" is a complete,
immutable bundle. This module is the only place the workspace knows the outbox
exists; neither side imports the other's code.

Per bundle: read the sidecar, derive the episode id from its capture_id,
resolve the requested manifest (creating it on first use; no manifest in the
sidecar = unfiled, ingested without a manifest link), preserve the sidecar as
capture.json, move the bundle into the store's episode directory, write the
store's episode.json (file hashes, sizes), and link the manifest.

NOTE: ingestion is not crash-safe. The per-bundle steps (rename sidecar, move
bundle, write store metadata) are not atomic as a group: a crash partway
through can leave an episode dir in the store without episode.json, or a
bundle in the outbox whose sidecar was already renamed to capture.json —
neither is repaired by re-running the sweep. Accepted for now; recovery is
manual, and capture.json preserves everything needed to re-file by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shutil import move

from pydantic import BaseModel, ConfigDict, Field

from ..ids import validate_id
from ..io import StoreError
from ..models import RecordingContext
from ..paths import episode_dir, episodes_root
from .episodes import create_episode
from .manifests import add_manifest_episodes, list_manifest_episodes, update_manifest
from .projects import StoreCtx, ensure_store_roots
from .recording import ensure_manifest_for_recording
from .run_manifests import add_run_manifest

SUPPORTED_SCHEMA_VERSIONS = {1}


class Sidecar(BaseModel):
    """The runtime's episode.json contract, as read by the workspace. Tolerant
    of unknown fields so a runtime ahead of us doesn't break ingestion."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int
    capture_id: str
    recorded_at: datetime
    length: int
    fps: float
    record_hz: float | None = None
    features: dict = Field(default_factory=dict)
    encoding: dict = Field(default_factory=dict)
    reward: float | None = None      # verdict merged at capture (runtime AGENTS.md)
    task: str | None = None
    task_description: str | None = None
    requested_manifest: str | None = None    # manifest NAME — the filing intent
    manifest_id: str | None = None           # carried only when already known
    collection_mode: str | None = None       # = manifest type (teleop | eval | ...)
    source_project_id: str | None = None
    source_run_id: str | None = None
    source_checkpoint: str | None = None
    policy_name: str | None = None


@dataclass(frozen=True)
class Ingested:
    episode_id: str
    manifest_id: str | None      # None = unfiled
    bundle: str                  # outbox dirname, for logging


def sweep(ctx: StoreCtx, outbox: Path) -> list[Ingested]:
    """Ingest every complete bundle in the outbox. In-flight (.tmp-*) dirs are
    skipped; a bundle that fails stays in the outbox and doesn't stop the sweep."""
    ensure_store_roots(ctx)
    results: list[Ingested] = []
    if not outbox.is_dir():
        return results
    for bundle in sorted(path for path in outbox.iterdir() if path.is_dir()):
        if bundle.name.startswith(".tmp-"):
            continue
        if not (bundle / "episode.json").is_file():
            print(f"[ingest] skipping {bundle.name}: no episode.json", flush=True)
            continue
        try:
            results.append(ingest_bundle(ctx, bundle))
        except Exception as exc:
            print(f"[ingest] failed {bundle.name}: {exc}", flush=True)
    return results


def ingest_bundle(ctx: StoreCtx, bundle: Path) -> Ingested:
    sidecar = Sidecar.model_validate_json((bundle / "episode.json").read_text())
    if sidecar.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise StoreError(f"unsupported sidecar schema_version: {sidecar.schema_version}", "CONFLICT")

    episode_id = f"ep_{sidecar.capture_id}"        # same bundle always yields the same id
    validate_id("episode", episode_id)             # a malformed capture_id must not shape a store path
    dest = episode_dir(episodes_root(ctx.home), episode_id)
    if dest.exists():
        raise StoreError(f"episode already in store: {episode_id}", "CONFLICT")

    manifest_id = _resolve_manifest(ctx, sidecar)

    (bundle / "episode.json").rename(bundle / "capture.json")   # capture record rides along, untouched
    move(str(bundle), str(dest))

    create_episode(
        ctx,
        episode_id=episode_id,
        length=sidecar.length,
        recorded_at=sidecar.recorded_at,
        record_hz=sidecar.record_hz,
        task=sidecar.task,
        task_description=sidecar.task_description,
        features=sidecar.features,
        collection_mode=sidecar.collection_mode,
        source_project_id=sidecar.source_project_id,
        source_run_id=sidecar.source_run_id,
        source_checkpoint=sidecar.source_checkpoint,
        policy_name=sidecar.policy_name,
        reward=sidecar.reward,
    )
    if manifest_id is not None:
        add_manifest_episodes(ctx, manifest_id, [episode_id])
        _refresh_rollup(ctx, manifest_id)
        _link_source_run(ctx, manifest_id, sidecar.source_run_id)
    return Ingested(episode_id=episode_id, manifest_id=manifest_id, bundle=bundle.name)


def _link_source_run(ctx: StoreCtx, manifest_id: str, run_id: str | None) -> None:
    """Provenance closes the loop: an eval manifest links to the run whose
    checkpoint produced its episodes, so the run's page shows its eval results.
    The run id is carried opaquely from recording-context provenance and may
    not exist in this store (foreign or deleted run) — skip loudly, not fatally."""
    if not run_id:
        return
    try:
        add_run_manifest(ctx, run_id, manifest_id)
    except StoreError as exc:
        print(f"[ingest] source-run link skipped ({run_id}): {exc}", flush=True)


def _refresh_rollup(ctx: StoreCtx, manifest_id: str) -> None:
    """Roll capture-time verdicts up into the manifest, same math as the rating
    PATCH route — an eval manifest shows its success rate as episodes arrive,
    not only after a manual re-rating."""
    linked = list_manifest_episodes(ctx, manifest_id)
    rated = [episode.reward for episode in linked if episode.reward is not None]
    if rated:
        update_manifest(ctx, manifest_id,
                        success_rate=sum(rated) / len(rated),
                        rated_episodes=len(rated))


def _resolve_manifest(ctx: StoreCtx, sidecar: Sidecar) -> str | None:
    """Resolve the sidecar's filing intent to a manifest id, creating the
    manifest on first use. No requested manifest = unfiled = None. Provenance
    ids (source_run_id etc.) are carried opaquely, not validated here."""
    if not sidecar.requested_manifest and not sidecar.manifest_id:
        return None
    resolved = ensure_manifest_for_recording(ctx, RecordingContext(
        manifest_id=sidecar.manifest_id,
        manifest_name=sidecar.requested_manifest,
        manifest_type=sidecar.collection_mode,
        fps=round(sidecar.record_hz) if sidecar.record_hz else None,
    ))
    return resolved.manifest_id
