from __future__ import annotations

from pathlib import Path

from .ids import short_id
from .io import StoreError


def workspace_root(home: Path) -> Path:
    return home / "workspace"


def projects_root(home: Path) -> Path:
    return workspace_root(home)


def manifests_root(home: Path) -> Path:
    return workspace_root(home) / "manifests"


def episodes_root(home: Path) -> Path:
    return workspace_root(home) / "episodes"


def folder_name(name: str, entity_id: str) -> str:
    return f"{safe_component(name, 'entity name')}__{safe_component(short_id(entity_id), 'id suffix')}"


def safe_component(value: str, label: str = "path component") -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise StoreError(f"Invalid {label}: {value!r}", "CONFLICT")
    return value


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
    return root / safe_component(episode_id, "episode id")


def episode_json(path: Path) -> Path:
    return path / "episode.json"
