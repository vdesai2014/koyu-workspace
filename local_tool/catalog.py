from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path

from .io import StoreError
from .models import LocalEpisode, LocalManifest, LocalProject, LocalRun
from .paths import episode_json, episodes_root, manifest_json, manifests_root, project_json, projects_root, run_json, runs_root


CATALOG_KEYS = ("projects", "runs", "manifests", "episodes")


def catalog_path(home: Path) -> Path:
    return home / "catalog.json"


def catalog_lock_path(home: Path) -> Path:
    return home / "catalog.json.lock"


@contextmanager
def _catalog_lock(home: Path, exclusive: bool):
    path = catalog_lock_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def empty_catalog() -> dict[str, dict[str, str]]:
    return {key: {} for key in CATALOG_KEYS}


def load_catalog(home: Path) -> dict[str, dict[str, str]]:
    with _catalog_lock(home, exclusive=False):
        path = catalog_path(home)
        if not path.exists():
            return empty_catalog()
        raw = json.loads(path.read_text())
        data = empty_catalog()
        for key in CATALOG_KEYS:
            data[key] = dict(raw.get(key, {}))
        return data


def save_catalog(home: Path, catalog: dict[str, dict[str, str]]) -> None:
    with _catalog_lock(home, exclusive=True):
        path = catalog_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(catalog, indent=2))
        tmp.replace(path)


def rebuild_catalog(home: Path) -> dict[str, dict[str, str]]:
    catalog = empty_catalog()
    root = projects_root(home)
    if root.exists():
        for project_dir in sorted(root.iterdir()):
            if project_dir.name in {"manifests", "episodes"}:
                continue
            pj = project_json(project_dir)
            if project_dir.is_dir() and pj.exists():
                try:
                    project = LocalProject.model_validate_json(pj.read_text())
                except Exception:
                    continue
                catalog["projects"][project.id] = str(project_dir.relative_to(home))
                _scan_runs(home, project_dir, catalog)
    _scan_manifests(home, catalog)
    _scan_episodes(home, catalog)
    save_catalog(home, catalog)
    return catalog


def _scan_runs(home: Path, parent_dir: Path, catalog: dict[str, dict[str, str]]) -> None:
    nested = runs_root(parent_dir)
    if not nested.exists():
        return
    for run_dir in sorted(nested.iterdir()):
        rj = run_json(run_dir)
        if run_dir.is_dir() and rj.exists():
            try:
                run = LocalRun.model_validate_json(rj.read_text())
            except Exception:
                continue
            catalog["runs"][run.id] = str(run_dir.relative_to(home))
            _scan_runs(home, run_dir, catalog)


def _scan_manifests(home: Path, catalog: dict[str, dict[str, str]]) -> None:
    root = manifests_root(home)
    if not root.exists():
        return
    for entry in sorted(root.rglob("*.json")):
        if not entry.is_file():
            continue
        try:
            manifest = LocalManifest.model_validate_json(entry.read_text())
        except Exception:
            continue
        catalog["manifests"][manifest.id] = str(entry.relative_to(home))


def _scan_episodes(home: Path, catalog: dict[str, dict[str, str]]) -> None:
    root = episodes_root(home)
    if not root.exists():
        return
    for episode_dir in sorted(root.iterdir()):
        ej = episode_json(episode_dir)
        if not episode_dir.is_dir() or not ej.exists():
            continue
        try:
            episode = LocalEpisode.model_validate_json(ej.read_text())
        except Exception:
            continue
        catalog["episodes"][episode.id] = str(episode_dir.relative_to(home))


def resolve_entity_path(
    home: Path,
    entity_type: str,
    entity_id: str,
    *,
    validator,
) -> Path:
    catalog = load_catalog(home)
    rel = catalog.get(entity_type, {}).get(entity_id)
    if rel:
        candidate = home / rel
        if validator(candidate, entity_id):
            return candidate
    catalog = rebuild_catalog(home)
    rel = catalog.get(entity_type, {}).get(entity_id)
    if rel:
        candidate = home / rel
        if validator(candidate, entity_id):
            return candidate
    raise StoreError(f"{entity_type[:-1].title()} not found: {entity_id}", "NOT_FOUND")
