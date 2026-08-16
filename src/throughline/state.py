"""Per-repo pipeline state, persisted as docs/project/pipeline.yaml.

This module owns the only machine-written file in the target repo.
Everything else the pipeline produces is hand-editable markdown.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import nodes as nodes_module

PROJECT_DIR = "docs/project"
STATE_FILENAME = "pipeline.yaml"
VERSION = 1

EMPTY = "empty"
DRAFTED = "drafted"
IN_PROGRESS = "in_progress"
CURRENT = "current"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class NodeState:
    status: str = EMPTY
    answers: dict[str, str] = field(default_factory=dict)
    upstream_hashes: dict[str, str] = field(default_factory=dict)
    updated: str | None = None


@dataclass
class PipelineState:
    version: int = VERSION
    project: str = ""
    created: str = ""
    flags: dict[str, bool] = field(default_factory=dict)
    on_demand: dict[str, list[str]] = field(default_factory=dict)
    nodes: dict[str, NodeState] = field(default_factory=dict)
    last_note: str = ""
    last_node: str | None = None


def project_dir(repo: Path) -> Path:
    return Path(repo) / PROJECT_DIR


def state_path(repo: Path) -> Path:
    return project_dir(repo) / STATE_FILENAME


def exists(repo: Path) -> bool:
    return state_path(repo).is_file()


def init(repo: Path, project: str, flags: dict[str, bool]) -> PipelineState:
    resolved = {name: bool(flags.get(name, False)) for name in nodes_module.FLAGS}
    result = PipelineState(
        version=VERSION,
        project=project,
        created=utcnow(),
        flags=resolved,
    )
    for node in nodes_module.active_nodes(resolved):
        result.nodes[node.id] = NodeState()
    save(repo, result)
    return result


def save(repo: Path, state: PipelineState) -> None:
    payload = {
        "version": state.version,
        "project": state.project,
        "created": state.created,
        "flags": state.flags,
        "on_demand": state.on_demand,
        "last_node": state.last_node,
        "last_note": state.last_note,
        "nodes": {
            node_id: {
                "status": entry.status,
                "answers": entry.answers,
                "upstream_hashes": entry.upstream_hashes,
                "updated": entry.updated,
            }
            for node_id, entry in state.nodes.items()
        },
    }
    path = state_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _migrate_status(entry: dict) -> str:
    """Read a node's status, upgrading the old confirmed boolean.

    Files written before `drafted` existed encoded the same distinction as
    status `current` with `confirmed: False` - a document Claude wrote and
    nobody has read. That is exactly what drafted means.
    """
    status = entry.get("status", EMPTY)
    if status == CURRENT and entry.get("confirmed") is False:
        return DRAFTED
    return status


def load(repo: Path) -> PipelineState:
    path = state_path(repo)
    if not path.is_file():
        raise FileNotFoundError(f"no pipeline at {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = PipelineState(
        version=payload.get("version", VERSION),
        project=payload.get("project", ""),
        created=payload.get("created", ""),
        flags=payload.get("flags") or {},
        on_demand=payload.get("on_demand") or {},
        last_note=payload.get("last_note") or "",
        last_node=payload.get("last_node"),
    )
    for node_id, entry in (payload.get("nodes") or {}).items():
        entry = entry or {}
        result.nodes[node_id] = NodeState(
            status=_migrate_status(entry),
            answers=entry.get("answers") or {},
            upstream_hashes=entry.get("upstream_hashes") or {},
            updated=entry.get("updated"),
        )
    return result


def node_state(state: PipelineState, node_id: str) -> NodeState:
    if node_id not in state.nodes:
        state.nodes[node_id] = NodeState()
    return state.nodes[node_id]


def _mid_interview_note(node_id: str, answered: int) -> str:
    """The left-off line for a node that is partway through.

    Written on every answer, so a session that dies mid-interview leaves
    a note describing this node rather than the last one that finished.
    """
    try:
        title = nodes_module.get_node(node_id).title
    except KeyError:
        title = node_id
    word = "answer" if answered == 1 else "answers"
    return f"Mid-interview on {title} - {answered} {word} saved."


def record_answer(
    repo: Path,
    node_id: str,
    question_id: str,
    answer: str,
) -> PipelineState:
    """Persist a single answer straight away.

    Answers are never batched to the end of an interview - an interrupted
    node must lose nothing.
    """
    state = load(repo)
    entry = node_state(state, node_id)
    entry.answers[question_id] = answer
    entry.updated = utcnow()
    if entry.status == EMPTY:
        entry.status = IN_PROGRESS
    state.last_node = node_id
    state.last_note = _mid_interview_note(node_id, len(entry.answers))
    save(repo, state)
    return state


def set_note(repo: Path, node_id: str, note: str) -> PipelineState:
    state = load(repo)
    state.last_note = note
    state.last_node = node_id
    save(repo, state)
    return state
