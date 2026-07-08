from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...io import StoreError
from ...store import episodes, manifests
from ...store.projects import StoreCtx
from ..deps import get_ctx

router = APIRouter(tags=["episodes"])


class EpisodePatchBody(BaseModel):
    reward: float | None = None
    task: str | None = None
    task_description: str | None = None


def _raise(e: StoreError):
    status = {"NOT_FOUND": 404, "CONFLICT": 409}.get(e.code, 400)
    raise HTTPException(status_code=status, detail=str(e))


def _episode_summary(episode) -> dict:
    return {
        "id": episode.id,
        "length": episode.length,
        "task": episode.task,
        "task_description": episode.task_description,
        "collection_mode": episode.collection_mode,
        "source_project_id": episode.source_project_id,
        "source_run_id": episode.source_run_id,
        "source_checkpoint": episode.source_checkpoint,
        "policy_name": episode.policy_name,
        "reward": episode.reward,
        "features": episode.features,
        "size_bytes": episode.size_bytes,
        "manifest_ids": episode.manifest_ids,
        "created_at": episode.created_at,
    }


def _recompute_manifest_rollup(ctx: StoreCtx, manifest_id: str) -> None:
    manifest = manifests.get_manifest(ctx, manifest_id)
    linked = manifests.list_manifest_episodes(ctx, manifest_id)
    rated = [episode.reward for episode in linked if episode.reward is not None]
    success_rate = (sum(rated) / len(rated)) if rated else None
    manifests.update_manifest(
        ctx,
        manifest_id,
        success_rate=success_rate,
        rated_episodes=len(rated),
    )


@router.patch("/episodes/{episode_id}")
def patch_episode(episode_id: str, body: EpisodePatchBody, ctx: StoreCtx = Depends(get_ctx)):
    updates = body.model_dump(exclude_unset=True)
    try:
        episode = episodes.update_episode(ctx, episode_id, **updates)
        touched_reward = "reward" in updates
        if touched_reward:
            for manifest_id in episode.manifest_ids:
                _recompute_manifest_rollup(ctx, manifest_id)
        return _episode_summary(episode)
    except StoreError as e:
        _raise(e)
