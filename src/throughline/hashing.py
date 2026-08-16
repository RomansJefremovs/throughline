"""Upstream content hashing.

Staleness is computed here and reported on request. It is deliberately
never surfaced as a count or a warning - see status.py.
"""

import hashlib
from pathlib import Path

from . import nodes as nodes_module
from .artifacts import read_artifact
from .state import PipelineState, node_state

MISSING = "missing"


def content_hash(text: str) -> str:
    normalised = text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def current_upstream_hashes(repo: Path, node_id: str) -> dict[str, str]:
    node = nodes_module.get_node(node_id)
    result: dict[str, str] = {}
    for dep in node.deps:
        text = read_artifact(repo, dep)
        result[dep] = MISSING if text is None else content_hash(text)
    return result


def stale_deps(repo: Path, node_id: str, state: PipelineState) -> list[str]:
    recorded = node_state(state, node_id).upstream_hashes
    if not recorded:
        return []
    current = current_upstream_hashes(repo, node_id)
    return [dep for dep, value in current.items() if recorded.get(dep) != value]


def is_stale(repo: Path, node_id: str, state: PipelineState) -> bool:
    return bool(stale_deps(repo, node_id, state))


def stamp(repo: Path, node_id: str, state: PipelineState) -> None:
    """Record the upstream hashes as of now. Caller is responsible for saving."""
    node_state(state, node_id).upstream_hashes = current_upstream_hashes(repo, node_id)
