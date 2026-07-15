import json

import pytest

from local_tool.paths import episode_dir, episodes_root
from local_tool.io import StoreError
from local_tool.store.episodes import create_episode, get_episode
from local_tool.store.ingest import sweep
from local_tool.store.manifests import list_manifests
from local_tool.store.projects import StoreCtx, create_project


def _sidecar(capture_id, manifest="teleop-cubes", mode="teleop", **over):
    sidecar = {
        "schema_version": 1,
        "capture_id": capture_id,
        "recorded_at": "2026-06-10T12:00:00+00:00",
        "length": 3,
        "fps": 29.7,
        "record_hz": 30.0,
        "task": "pick",
        "requested_manifest": manifest,
        "collection_mode": mode,
        "features": {"action": {"dtype": "float32", "shape": [7]}},
        "encoding": {"video_codec": "libx264"},
    }
    sidecar.update(over)
    return {key: value for key, value in sidecar.items() if value is not None}


def _bundle(outbox, capture_id="a" * 32, **over):
    bundle = outbox / f"20260610T120000__teleop-cubes__{capture_id[:8]}"
    (bundle / "videos").mkdir(parents=True)
    (bundle / "data.parquet").write_bytes(b"not-really-parquet")
    (bundle / "videos" / "top.mp4").write_bytes(b"not-really-mp4")
    (bundle / "episode.json").write_text(json.dumps(_sidecar(capture_id, **over)))
    return bundle


@pytest.fixture
def ws(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outbox = tmp_path / "data-recordings"
    outbox.mkdir()
    return StoreCtx(home=home), outbox


def test_sweep_ingests_bundle(ws):
    ctx, outbox = ws
    _bundle(outbox)
    (result,) = sweep(ctx, outbox)

    assert result.episode_id == "ep_" + "a" * 32      # derived from capture_id
    assert list(outbox.iterdir()) == []               # bundle left the outbox

    dest = episode_dir(episodes_root(ctx.home), result.episode_id)
    assert (dest / "data.parquet").is_file()
    assert (dest / "videos" / "top.mp4").is_file()
    assert (dest / "capture.json").is_file()          # original sidecar preserved

    episode = get_episode(ctx, result.episode_id)
    assert episode.length == 3 and episode.task == "pick" and episode.collection_mode == "teleop"
    assert set(episode.files) == {"data.parquet", "videos/top.mp4", "capture.json"}
    assert all(meta["blake3"] for meta in episode.files.values())
    assert episode.size_bytes > 0

    (manifest,) = list_manifests(ctx)
    assert manifest.name == "teleop-cubes" and manifest.type == "teleop" and manifest.fps == 30
    assert manifest.episode_ids == [result.episode_id]
    assert episode.manifest_ids == [manifest.id]


def test_reingesting_same_capture_is_rejected(ws):
    ctx, outbox = ws
    _bundle(outbox)
    sweep(ctx, outbox)
    duplicate = _bundle(outbox)                       # same capture_id arrives again

    assert sweep(ctx, outbox) == []
    assert duplicate.is_dir()                         # stays in the outbox for a human
    (manifest,) = list_manifests(ctx)
    assert len(manifest.episode_ids) == 1


def test_second_episode_joins_existing_manifest(ws):
    ctx, outbox = ws
    _bundle(outbox, capture_id="a" * 32)
    _bundle(outbox, capture_id="b" * 32)

    assert len(sweep(ctx, outbox)) == 2
    (manifest,) = list_manifests(ctx)
    assert len(manifest.episode_ids) == 2


def test_unfiled_bundle_ingests_without_manifest(ws):
    ctx, outbox = ws
    _bundle(outbox, manifest=None, mode=None)
    (result,) = sweep(ctx, outbox)

    assert result.manifest_id is None
    assert get_episode(ctx, result.episode_id).manifest_ids == []
    assert list_manifests(ctx) == []


def test_named_manifest_without_type_stays_in_outbox(ws):
    ctx, outbox = ws
    bundle = _bundle(outbox, mode=None)               # name but no collection_mode

    assert sweep(ctx, outbox) == []                   # creating a manifest needs a type
    assert bundle.is_dir() and (bundle / "episode.json").is_file()


def test_sweep_skips_inflight_foreign_and_unsupported(ws):
    ctx, outbox = ws
    (outbox / ".tmp-abc").mkdir()                                  # recorder mid-write
    (outbox / "not-a-bundle").mkdir()                              # no episode.json
    bad = _bundle(outbox, capture_id="c" * 32, schema_version=99)  # future schema
    malformed = _bundle(outbox, capture_id="Z" * 32)               # id that can't shape a store path

    assert sweep(ctx, outbox) == []
    assert (outbox / ".tmp-abc").is_dir()
    assert (outbox / "not-a-bundle").is_dir()
    assert bad.is_dir()
    assert malformed.is_dir()


@pytest.mark.parametrize("name", ["../escaped", "/tmp/escaped", ".", "bad/name", "bad\\name"])
def test_project_names_cannot_shape_paths(ws, name):
    ctx, _ = ws

    with pytest.raises(StoreError, match="Invalid entity name"):
        create_project(ctx, name=name)


def test_episode_ids_cannot_shape_paths(ws):
    ctx, _ = ws

    with pytest.raises(StoreError, match="Invalid episode id"):
        create_episode(ctx, episode_id="../escaped", length=1)
