from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..models import LocalEpisode, LocalManifest, LocalProject, LocalRun

SyncOperation = Literal["push", "pull", "clone"]
SyncEntityType = Literal["project", "run", "manifest"]
SyncTransferEntityType = Literal["project", "run", "episode"]


@dataclass(frozen=True)
class SyncRequest:
    operation: SyncOperation
    entity_type: SyncEntityType
    entity_id: str
    include_manifests: bool = False
    include_descendants: bool = False
    dry_run: bool = False
    cloud_api_base: str | None = None
    bearer_token: str | None = None


@dataclass
class SyncScope:
    root_entity_type: SyncEntityType
    root_entity_id: str
    project: LocalProject | None = None
    runs: list[LocalRun] = field(default_factory=list)
    manifests: list[LocalManifest] = field(default_factory=list)
    episodes: list[LocalEpisode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetadataAction:
    operation: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FileAction:
    operation: str
    entity_type: SyncTransferEntityType
    entity_id: str
    path: str
    size: int
    source_entity_id: str | None = None
    source_path: str | None = None


@dataclass(frozen=True)
class LinkAction:
    operation: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncPlan:
    request: SyncRequest
    scope: SyncScope
    metadata_actions: list[MetadataAction] = field(default_factory=list)
    file_actions: list[FileAction] = field(default_factory=list)
    link_actions: list[LinkAction] = field(default_factory=list)
    id_remaps: dict[str, dict[str, str]] = field(default_factory=dict)
    required_id_remaps: dict[str, list[str]] = field(default_factory=dict)
    ignored_file_paths: dict[str, list[str]] = field(default_factory=dict)
    ignore_patterns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "operation": self.request.operation,
            "entity_type": self.request.entity_type,
            "entity_id": self.request.entity_id,
            "scope": {
                "project_id": self.scope.project.id if self.scope.project else None,
                "run_ids": [run.id for run in self.scope.runs],
                "manifest_ids": [manifest.id for manifest in self.scope.manifests],
                "episode_ids": [episode.id for episode in self.scope.episodes],
            },
            "planned": {
                "metadata_actions": len(self.metadata_actions),
                "file_actions": len(self.file_actions),
                "link_actions": len(self.link_actions),
                "ignored_files": sum(len(paths) for paths in self.ignored_file_paths.values()),
            },
            "ignore_patterns": list(self.ignore_patterns),
            "id_remaps": self.id_remaps,
            "required_id_remaps": self.required_id_remaps,
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "metadata_actions": [
                {
                    "operation": action.operation,
                    "entity_type": action.entity_type,
                    "entity_id": action.entity_id,
                    "payload": action.payload,
                }
                for action in self.metadata_actions
            ],
            "file_actions": [
                {
                    "operation": action.operation,
                    "entity_type": action.entity_type,
                    "entity_id": action.entity_id,
                    "path": action.path,
                    "size": action.size,
                    "source_entity_id": action.source_entity_id,
                    "source_path": action.source_path,
                }
                for action in self.file_actions
            ],
            "link_actions": [
                {
                    "operation": action.operation,
                    "entity_type": action.entity_type,
                    "entity_id": action.entity_id,
                    "payload": action.payload,
                }
                for action in self.link_actions
            ],
            "ignored_file_paths": self.ignored_file_paths,
        }


@dataclass
class SyncResult:
    success: bool
    request: SyncRequest
    plan: SyncPlan
    created: dict[str, int]
    patched: dict[str, int]
    uploaded: dict[str, int]
    copied: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    progress: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "success": self.success,
            "request": {
                "operation": self.request.operation,
                "entity_type": self.request.entity_type,
                "entity_id": self.request.entity_id,
                "include_manifests": self.request.include_manifests,
                "include_descendants": self.request.include_descendants,
                "dry_run": self.request.dry_run,
            },
            "scope": self.plan.summary()["scope"],
            "planned": self.plan.summary()["planned"],
            "id_remaps": self.plan.id_remaps,
            "created": self.created,
            "patched": self.patched,
            "uploaded": self.uploaded,
            "copied": self.copied,
            "warnings": self.warnings,
            "errors": self.errors,
            "events": self.events,
        }
        if self.progress is not None:
            payload["progress"] = self.progress
        return payload
