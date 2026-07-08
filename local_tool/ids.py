from __future__ import annotations

import re
from uuid import uuid4


_ID_PREFIXES = {
    "project": "proj",
    "run": "run",
    "manifest": "mf",
    "episode": "ep",
}

_ID_SUFFIX_RE = re.compile(r"^[0-9a-f]{32}$")


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def short_id(value: str) -> str:
    return value.split("_", 1)[-1][:8]


def validate_id(kind: str, value: str) -> str:
    """Raise ValueError unless `value` matches the canonical id shape for `kind`.

    Canonical shape: `{prefix}_{32 lowercase hex chars}`, matching the output
    of `generate_id(prefix)`. Guards against bare UUIDs or malformed
    client-supplied ids from reaching the store and later tripping the cloud
    API's stricter validation.
    """
    expected = _ID_PREFIXES.get(kind)
    if expected is None:
        raise ValueError(f"unknown id kind: {kind!r}")
    prefix_sep = f"{expected}_"
    if not isinstance(value, str) or not value.startswith(prefix_sep):
        raise ValueError(f"id must start with {prefix_sep!r}, got {value!r}")
    suffix = value[len(prefix_sep):]
    if not _ID_SUFFIX_RE.match(suffix):
        raise ValueError(f"id suffix must be 32 lowercase hex chars, got {suffix!r}")
    return value

