from __future__ import annotations
"""Ignore filtering for sync planning.

Ignore rules are a sync concern, not a store concern. They narrow local
project/run file actions during push planning and execution, but do not apply to
episode payloads or cloud pull behavior.
"""

from dataclasses import dataclass, field
from fnmatch import fnmatch

from ..store import projects, runs
from ..store.projects import StoreCtx

DEFAULT_IGNORE_PATTERNS = [
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
    ".git/",
    ".koyuignore",
]


@dataclass(frozen=True)
class IgnoreDecision:
    included: set[str]
    ignored: set[str]
    patterns: list[str] = field(default_factory=list)


def load_project_ignore_patterns(ctx: StoreCtx, project_id: str) -> list[str]:
    project_dir = projects.get_project_dir(ctx, project_id)
    ignore_path = project_dir / ".koyuignore"
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    if ignore_path.exists():
        for line in ignore_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            patterns.append(stripped)
    return patterns


def filter_project_paths(ctx: StoreCtx, project_id: str, paths: set[str]) -> IgnoreDecision:
    return _filter_paths(paths, load_project_ignore_patterns(ctx, project_id))


def filter_run_paths(ctx: StoreCtx, run_id: str, paths: set[str]) -> IgnoreDecision:
    run = runs.get_run(ctx, run_id)
    return _filter_paths(paths, load_project_ignore_patterns(ctx, run.project_id))


def _filter_paths(paths: set[str], patterns: list[str]) -> IgnoreDecision:
    included: set[str] = set()
    ignored: set[str] = set()
    for path in paths:
        if _is_ignored(path, patterns):
            ignored.add(path)
        else:
            included.add(path)
    return IgnoreDecision(included=included, ignored=ignored, patterns=patterns)


def _is_ignored(path: str, patterns: list[str]) -> bool:
    normalized = path.strip("/")
    parts = normalized.split("/")
    for pattern in patterns:
        candidate = pattern.strip()
        if not candidate:
            continue
        if candidate.endswith("/"):
            prefix = candidate.rstrip("/")
            if prefix in parts:
                return True
            if normalized.startswith(f"{prefix}/"):
                return True
            continue
        if "/" in candidate and fnmatch(normalized, candidate):
            return True
        if fnmatch(normalized, candidate):
            return True
        if any(fnmatch(part, candidate) for part in parts):
            return True
    return False
