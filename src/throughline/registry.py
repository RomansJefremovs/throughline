"""The list of projects the app knows about.

This is the only state that lives outside a repository, and it is
deliberately the smallest possible thing: a list of paths, one per line,
hand-editable. It is a bookmark list, not a database.

Losing this file costs you the sidebar and no content whatsoever - every
project is fully described by its own `docs/project/`, and re-adding a
folder restores it completely. Anything richer than paths would be an
index, and an index is the one thing that can disagree with the files.
"""

import os
from pathlib import Path

from . import state as state_module
from . import status as status_module

REGISTRY_FILENAME = "projects.txt"


def home() -> Path:
    override = os.environ.get("THROUGHLINE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".throughline"


def registry_path() -> Path:
    return home() / REGISTRY_FILENAME


def projects() -> list[Path]:
    """Every tracked path, including ones that are not there right now.

    A folder that has gone missing is not the same as one you forgot.
    Dropping an unmounted drive's repo silently would look exactly like
    data loss, so the path stays and is reported as missing instead.
    """
    path = registry_path()
    if not path.is_file():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        resolved = Path(line).resolve()
        if resolved not in result:
            result.append(resolved)
    return result


def _write(paths: list[Path]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{p}\n" for p in paths)
    path.write_text(body, encoding="utf-8")


def add(repo: Path) -> list[Path]:
    resolved = Path(repo).resolve()
    current = projects()
    if resolved not in current:
        current.append(resolved)
        _write(current)
    return current


def remove(repo: Path) -> list[Path]:
    resolved = Path(repo).resolve()
    current = [p for p in projects() if p != resolved]
    _write(current)
    return current


def describe(repo: Path) -> dict:
    """One project, as much as can be said without opening an artifact.

    Never returns a count of anything outstanding. The overview shows what
    is alive, not what is owed.
    """
    resolved = Path(repo).resolve()
    result = {
        "path": str(resolved),
        "name": resolved.name,
        "missing": not resolved.is_dir(),
        "tracked": False,
        "project": "",
        "next": None,
        "next_title": "",
        "note": "",
        "phases": [],
    }
    if result["missing"] or not state_module.exists(resolved):
        return result

    loaded = state_module.load(resolved)
    computed = status_module.compute(loaded)
    result["tracked"] = True
    result["project"] = computed.project
    result["next"] = computed.next_node
    result["next_title"] = computed.next_title
    result["note"] = computed.where_you_left_off
    result["phases"] = [
        {"phase": p.phase, "filled": p.filled, "total": p.total}
        for p in computed.phases
    ]
    return result


def _touched_at(repo: Path) -> float | None:
    path = state_module.state_path(repo)
    if not path.is_file():
        return None
    return path.stat().st_mtime


def last_worked() -> Path | None:
    """The project the app opens on.

    The front door must contain no decisions, so this answers "which
    project" without asking. Most recently touched wins, measured by the
    state file itself so a hand edit counts too.
    """
    best = None
    best_at = None
    for repo in projects():
        touched = _touched_at(repo)
        if touched is None:
            continue
        if best_at is None or touched > best_at:
            best, best_at = repo, touched
    return best
