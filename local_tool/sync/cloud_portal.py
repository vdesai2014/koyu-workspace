from __future__ import annotations
"""Thin cloud API wrapper for sync.

This module owns auth and request/response handling for the current cloud API.
It should remain a transport adapter, not a sync policy layer.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


class SyncPortalError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _response_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("detail") or payload.get("error")
    except Exception:
        pass
    return response.text or None


@dataclass(frozen=True)
class CloudSyncConfig:
    api_base: str
    bearer_token: str | None = None


class CloudPortal:
    def __init__(self, config: CloudSyncConfig):
        self.config = config
        self._api_client: httpx.Client | None = None
        self._upload_client: httpx.Client | None = None

    def __enter__(self) -> "CloudPortal":
        headers = {"Authorization": f"Bearer {self.config.bearer_token}"} if self.config.bearer_token else {}
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=120.0, pool=120.0)
        self._api_client = httpx.Client(
            base_url=self.config.api_base,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        self._upload_client = httpx.Client(timeout=timeout, follow_redirects=True)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._upload_client is not None:
            self._upload_client.close()
        if self._api_client is not None:
            self._api_client.close()

    def ensure_project(self, project) -> bool:
        return self._request_create_or_existing_by_id(
            "POST",
            "/api/projects",
            existing_path=f"/api/projects/{project.id}",
            entity_type="project",
            entity_id=project.id,
            entity_name=project.name,
            json={
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "tags": project.tags,
                "is_public": project.is_public,
                "cloned_source_project_id": project.cloned_source_project_id,
            },
        )

    def patch_project(self, project) -> None:
        self._request_json(
            "PATCH",
            f"/api/projects/{project.id}",
            json={
                "name": project.name,
                "description": project.description,
                "tags": project.tags,
                "is_public": project.is_public,
                "cloned_source_project_id": project.cloned_source_project_id,
            },
        )

    def ensure_run(self, run) -> bool:
        return self._request_allow_conflict(
            "POST",
            f"/api/projects/{run.project_id}/runs",
            json={
                "id": run.id,
                "name": run.name,
                "parent_id": run.parent_id,
            },
        )

    def patch_run(self, run) -> None:
        self._request_json(
            "PATCH",
            f"/api/runs/{run.id}",
            json={
                "name": run.name,
                "parent_id": run.parent_id,
            },
        )

    def ensure_manifest(self, manifest) -> bool:
        return self._request_create_or_existing_by_id(
            "POST",
            "/api/manifests",
            existing_path=f"/api/manifests/{manifest.id}",
            entity_type="manifest",
            entity_id=manifest.id,
            entity_name=manifest.name,
            json={
                "id": manifest.id,
                "name": manifest.name,
                "description": manifest.description,
                "type": manifest.type,
                "tags": manifest.tags,
                "is_public": manifest.is_public,
                "fps": manifest.fps,
                "encoding": manifest.encoding,
                "features": manifest.features,
                "success_rate": manifest.success_rate,
                "rated_episodes": manifest.rated_episodes,
            },
        )

    def patch_manifest(self, manifest) -> None:
        self._request_json(
            "PATCH",
            f"/api/manifests/{manifest.id}",
            json={
                "name": manifest.name,
                "description": manifest.description,
                "tags": manifest.tags,
                "is_public": manifest.is_public,
                "fps": manifest.fps,
                "encoding": manifest.encoding,
                "features": manifest.features,
                "success_rate": manifest.success_rate,
                "rated_episodes": manifest.rated_episodes,
            },
        )

    def add_run_manifest(self, run_id: str, manifest_id: str) -> None:
        self._request_json(
            "POST",
            f"/api/runs/{run_id}/manifests",
            json={"manifest_id": manifest_id},
            expected=(200, 201),
        )

    def list_run_manifests(self, run_id: str) -> list[dict[str, Any]]:
        response = self._request_json("GET", f"/api/runs/{run_id}/manifests")
        return response.get("manifests", [])

    def list_manifest_runs(self, manifest_id: str) -> list[dict[str, Any]]:
        response = self._request_json("GET", f"/api/manifests/{manifest_id}/runs")
        return response.get("runs", [])

    def sync_entity_files(
        self,
        *,
        files: dict[str, dict],
        absolute_path_for,
        upload_path: str,
        commit_path: str,
        on_file_event=None,
    ) -> int:
        if not files:
            return 0
        upload_response = self._request_json(
            "POST",
            upload_path,
            json={
                "files": {
                    path: {
                        "blake3": meta["blake3"],
                        "size": int(meta["size"]),
                    }
                    for path, meta in files.items()
                }
            },
        )
        uploaded_count = 0
        to_upload = upload_response.get("to_upload", {})
        if on_file_event is not None:
            for relative_path, meta in files.items():
                if relative_path not in to_upload:
                    on_file_event("skipped", relative_path, int(meta.get("size", 0)))
        for relative_path, plan in to_upload.items():
            if on_file_event is not None:
                on_file_event("started", relative_path, int(files.get(relative_path, {}).get("size", 0)))
            self._upload_file_to_presigned_target(absolute_path_for(relative_path), plan)
            if on_file_event is not None:
                on_file_event("done", relative_path, int(files.get(relative_path, {}).get("size", 0)))
            uploaded_count += 1
        pending_upload_ids = upload_response.get("pending_upload_ids", [])
        if pending_upload_ids:
            self._request_json("POST", commit_path, json={"pending_upload_ids": pending_upload_ids})
        return uploaded_count

    def plan_episode_upload(self, episodes_payload: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request_json("POST", "/api/episodes/upload", json={"episodes": episodes_payload})

    def commit_episode_uploads(self, pending_upload_ids: list[str]) -> None:
        if pending_upload_ids:
            self._request_json("POST", "/api/episodes/commit", json={"pending_upload_ids": pending_upload_ids})

    def add_manifest_episodes(self, manifest_id: str, episode_ids: list[str]) -> None:
        self._request_json(
            "POST",
            f"/api/manifests/{manifest_id}/episodes/add",
            json={"episode_ids": episode_ids, "source_manifest_id": None},
        )

    def fetch_project(self, project_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/projects/{project_id}")

    def list_project_runs(self, project_id: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            path = f"/api/projects/{project_id}/runs"
            if cursor:
                path = f"{path}?cursor={quote(cursor, safe='')}"
            response = self._request_json("GET", path)
            runs.extend(response.get("runs", []))
            cursor = response.get("next_cursor")
            if not cursor:
                return runs

    def fetch_run(self, run_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/runs/{run_id}")

    def fetch_manifest(self, manifest_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/manifests/{manifest_id}")

    def list_manifest_episodes(self, manifest_id: str) -> list[dict[str, Any]]:
        episodes: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            path = f"/api/manifests/{manifest_id}/episodes"
            if cursor:
                path = f"{path}?cursor={quote(cursor, safe='')}"
            response = self._request_json("GET", path)
            episodes.extend(response.get("episodes", []))
            cursor = response.get("next_cursor")
            if not cursor:
                return episodes

    def manifest_episode_batch_get(self, manifest_id: str, episode_ids: list[str]) -> list[dict[str, Any]]:
        response = self._request_json(
            "POST",
            f"/api/manifests/{manifest_id}/episodes/batch-get",
            json={"episode_ids": episode_ids},
        )
        return response.get("episodes", [])

    def project_download_urls(self, project_id: str, paths: list[str]) -> dict[str, str]:
        response = self._request_json("POST", f"/api/projects/{project_id}/files/download", json={"paths": paths})
        return response.get("urls", {})

    def run_download_urls(self, run_id: str, paths: list[str]) -> dict[str, str]:
        response = self._request_json("POST", f"/api/runs/{run_id}/files/download", json={"paths": paths})
        return response.get("urls", {})

    def download_bytes(self, url: str) -> bytes:
        try:
            response = self._require_upload_client().get(url)
        except httpx.RequestError as exc:
            raise SyncPortalError(f"GET {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise SyncPortalError(f"GET {url} failed with {response.status_code}")
        return response.content

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        try:
            response = self._require_api_client().request(method, path, json=json)
        except httpx.RequestError as exc:
            raise SyncPortalError(f"{method} {path} failed: {exc}") from exc
        if response.status_code not in expected:
            detail = None
            try:
                payload = response.json()
                detail = payload.get("detail") or payload.get("error")
            except Exception:
                detail = response.text
            raise SyncPortalError(
                f"{method} {path} failed with {response.status_code}: {detail or 'request failed'}",
                status_code=response.status_code,
            )
        if response.status_code == 204:
            return {}
        return response.json()

    def _request_allow_conflict(self, method: str, path: str, *, json: dict) -> bool:
        try:
            response = self._require_api_client().request(method, path, json=json)
        except httpx.RequestError as exc:
            raise SyncPortalError(f"{method} {path} failed: {exc}") from exc
        if response.status_code == 409:
            return False
        if response.status_code not in (200, 201):
            detail = None
            try:
                payload = response.json()
                detail = payload.get("detail") or payload.get("error")
            except Exception:
                detail = response.text
            raise SyncPortalError(
                f"{method} {path} failed with {response.status_code}: {detail or 'request failed'}",
                status_code=response.status_code,
            )
        return response.status_code == 201

    def _request_create_or_existing_by_id(
        self,
        method: str,
        path: str,
        *,
        existing_path: str,
        entity_type: str,
        entity_id: str,
        entity_name: str,
        json: dict,
    ) -> bool:
        """Create an entity, distinguishing ID-exists from name collision.

        Cloud create endpoints return 409 for either duplicate ID or duplicate
        owner/name. Only duplicate ID means this local entity already exists
        remotely. A duplicate name with a different ID must be surfaced clearly;
        otherwise the later PATCH by local ID fails with a misleading 404.
        """
        try:
            response = self._require_api_client().request(method, path, json=json)
        except httpx.RequestError as exc:
            raise SyncPortalError(f"{method} {path} failed: {exc}") from exc

        if response.status_code in (200, 201):
            return response.status_code == 201

        detail = _response_detail(response)
        if response.status_code == 409:
            try:
                existing = self._require_api_client().get(existing_path)
            except httpx.RequestError as exc:
                raise SyncPortalError(f"GET {existing_path} failed after create conflict: {exc}") from exc
            if existing.status_code == 200:
                return False
            if existing.status_code == 404:
                raise SyncPortalError(
                    f"Cloud {entity_type} create conflicted, but {entity_id} does not exist remotely. "
                    f"A different cloud {entity_type} likely already uses the name {entity_name!r}. "
                    f"Rename the local {entity_type} or rename/delete the cloud one, then sync again. "
                    f"Cloud said: {detail or 'conflict'}"
                )
            existing_detail = _response_detail(existing)
            raise SyncPortalError(
                f"GET {existing_path} failed after create conflict with {existing.status_code}: "
                f"{existing_detail or 'request failed'}"
            )

        raise SyncPortalError(f"{method} {path} failed with {response.status_code}: {detail or 'request failed'}")

    def _upload_file_to_presigned_target(self, absolute_path: Path, plan: dict[str, Any]) -> None:
        client = self._require_upload_client()
        if plan.get("multipart"):
            part_size = int(plan["part_size"])
            with absolute_path.open("rb") as handle:
                for index, part in enumerate(plan.get("parts", [])):
                    url = part["url"] if isinstance(part, dict) else str(part)
                    headers = _stringify_headers(part.get("headers", {}) if isinstance(part, dict) else {})
                    chunk = handle.read(part_size)
                    if index == 0 and not chunk:
                        raise SyncPortalError(f"Multipart upload has no content for {absolute_path}")
                    response = client.put(url, headers=headers, content=chunk)
                    if response.status_code >= 400:
                        raise SyncPortalError(f"Multipart upload failed for {absolute_path} part {index + 1}")
        else:
            headers = _stringify_headers(plan.get("headers", {}))
            with absolute_path.open("rb") as handle:
                response = client.put(plan["url"], headers=headers, content=handle.read())
            if response.status_code >= 400:
                raise SyncPortalError(f"Upload failed for {absolute_path}")

    def _require_api_client(self) -> httpx.Client:
        if self._api_client is None:
            raise SyncPortalError("CloudPortal API client is not open")
        return self._api_client

    def _require_upload_client(self) -> httpx.Client:
        if self._upload_client is None:
            raise SyncPortalError("CloudPortal upload client is not open")
        return self._upload_client


def _load_stored_credentials() -> dict[str, Any]:
    """Look up a local credentials file as a last-resort fallback.

    Resolution order:
      1. $KOYU_CREDENTIALS_PATH (explicit override)
      2. .koyu/credentials.json next to the repo root
    File shape: {"cloud_bearer_token": "...", "cloud_api_base": "..." | null}.
    Silently returns {} on any read/parse error so missing or malformed
    credentials never crash the sync path — env vars still win.
    """
    candidates: list[Path] = []
    env_path = os.environ.get("KOYU_CREDENTIALS_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(".koyu") / "credentials.json")
    for path in candidates:
        try:
            if not path.exists():
                continue
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                return raw
        except Exception:
            continue
    return {}


def resolve_cloud_sync_config(
    *,
    cloud_api_base: str | None,
    bearer_token: str | None,
    require_token: bool = True,
) -> CloudSyncConfig:
    stored = _load_stored_credentials()
    api_base = (
        cloud_api_base
        or os.environ.get("CLOUD_API_BASE")
        or os.environ.get("CLOUD_BASE_URL")
        or stored.get("cloud_api_base")
        or "https://koyu.dev"
    ).rstrip("/")
    token = (
        bearer_token
        or os.environ.get("CLOUD_TOKEN")
        or os.environ.get("CLOUD_BEARER_TOKEN")
        or os.environ.get("CLOUD_PAT")
        or stored.get("cloud_bearer_token")
    )
    if require_token and not token:
        raise SyncPortalError("Missing cloud bearer token. Set CLOUD_TOKEN or provide bearer_token.")
    return CloudSyncConfig(api_base=api_base, bearer_token=token)


def _stringify_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}
