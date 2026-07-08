from __future__ import annotations

from pathlib import Path

from .ids import short_id


def workspace_root(home: Path) -> Path:
    return home / "workspace"


def projects_root(home: Path) -> Path:
    return workspace_root(home)


def manifests_root(home: Path) -> Path:
    return workspace_root(home) / "manifests"


def episodes_root(home: Path) -> Path:
    return workspace_root(home) / "episodes"


def folder_name(name: str, entity_id: str) -> str:
    return f"{name}__{short_id(entity_id)}"


def parse_folder_name(folder: str) -> tuple[str, str]:
    if "__" in folder:
        return tuple(folder.rsplit("__", 1))
    return folder, ""


def project_json(path: Path) -> Path:
    return path / "project.json"


def run_json(path: Path) -> Path:
    return path / "run.json"


def runs_root(entity_dir: Path) -> Path:
    return entity_dir / "runs"


def project_readme(path: Path) -> Path:
    return path / "README.md"


def run_readme(path: Path) -> Path:
    return path / "README.md"


def manifest_json(path: Path) -> Path:
    if str(path).endswith(".json"):
        return path
    return Path(f"{path}.json")


def manifest_path(root: Path, name: str, manifest_id: str) -> Path:
    return manifest_json(root / folder_name(name, manifest_id))


def episode_dir(root: Path, episode_id: str) -> Path:
    return root / episode_id


def episode_json(path: Path) -> Path:
    return path / "episode.json"
