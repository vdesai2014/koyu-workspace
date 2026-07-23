from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StoreError(Exception):
    def __init__(self, message: str, code: str = "STORE_ERROR"):
        super().__init__(message)
        self.code = code


def normalize_temporal_kwargs(kwargs: dict) -> dict:
    normalized = dict(kwargs)
    for field in ("created_at", "updated_at", "recorded_at"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return normalized


def read_model(path: Path, model_type: type[T]) -> T:
    if not path.exists():
        raise StoreError(f"Not found: {path}", "NOT_FOUND")
    raw = json.loads(path.read_text())
    return model_type.model_validate(raw)


def write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2))
    tmp.replace(path)


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write with a mkstemp-unique temp name, so concurrent writers
    to the same path can't clobber each other's temp file (unlike the fixed
    .tmp suffix above). Came over from the old os/core/supervision.py."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def remove_path(path: Path) -> None:
    if path.is_dir():
        for child in sorted(path.iterdir(), reverse=True):
            remove_path(child)
        path.rmdir()
    elif path.exists():
        path.unlink()
