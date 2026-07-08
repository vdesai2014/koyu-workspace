from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocalProject(BaseModel):
    id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False
    cloned_source_project_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LocalRun(BaseModel):
    id: str
    project_id: str
    parent_id: str | None = None
    name: str
    manifest_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LocalManifest(BaseModel):
    id: str
    name: str
    description: str | None = None
    type: str
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False
    fps: int | None = None
    encoding: dict = Field(default_factory=dict)
    features: dict = Field(default_factory=dict)
    episode_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    success_rate: float | None = None
    rated_episodes: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LocalEpisode(BaseModel):
    id: str
    length: int
    task: str | None = None
    task_description: str | None = None
    features: dict = Field(default_factory=dict)
    files: dict = Field(default_factory=dict)
    size_bytes: int = 0
    manifest_ids: list[str] = Field(default_factory=list)
    collection_mode: str | None = None
    source_project_id: str | None = None
    source_run_id: str | None = None
    source_checkpoint: str | None = None
    policy_name: str | None = None
    reward: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class RecordingContext(BaseModel):
    manifest_id: str | None = None
    manifest_name: str | None = None
    manifest_type: str | None = None
    task: str | None = None
    task_description: str | None = None
    source_project_id: str | None = None
    source_run_id: str | None = None
    source_checkpoint: str | None = None
    policy_name: str | None = None
    fps: int | None = None
    updated_at: datetime = Field(default_factory=utc_now)
    updated_by: str | None = None
