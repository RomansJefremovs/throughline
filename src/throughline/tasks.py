"""Task pipelines: many per repo, four nodes each.

The project pipeline answers what a system is. A task answers one thing
you are changing. Most real work is the second kind - fixing a bug in
someone else's repo - and running twelve nodes to do it is how a tool
goes unused.

Tasks live beside the project they belong to, in `docs/project/tasks/`,
one folder per task named by date and slug so the list sorts itself
without a database.

A task carries its own status rather than deriving it from its nodes.
That is the one field in this design that resembles a ticket status, and
it buys the one thing derivation cannot express: a task deliberately
walked away from. Without it a dead task competes for the single
next-action slot forever, and that slot is the product's core promise.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from . import nodes as nodes_module
from .state import NodeState, PROJECT_DIR, utcnow

TASKS_DIRNAME = "tasks"
TASK_FILENAME = "task.yaml"

OPEN = "open"
IN_PROGRESS = "in_progress"
DONE = "done"
ABANDONED = "abandoned"

LIVE = (OPEN, IN_PROGRESS)


@dataclass
class Task:
    slug: str = ""
    title: str = ""
    created: str = ""
    status: str = OPEN
    origin: str = "ticket"
    reference: str = ""
    nodes: dict[str, NodeState] = field(default_factory=dict)
    updated: str | None = None


def tasks_dir(repo: Path) -> Path:
    return Path(repo) / PROJECT_DIR / TASKS_DIRNAME


def task_dir(repo: Path, slug: str) -> Path:
    return tasks_dir(repo) / slug


def task_path(repo: Path, slug: str) -> Path:
    return task_dir(repo, slug) / TASK_FILENAME


def artifact_path(repo: Path, slug: str, node_id: str) -> Path:
    return task_dir(repo, slug) / nodes_module.get_task_node(node_id).filename


def make_slug(title: str, today: str | None = None) -> str:
    """Date first, so the folder listing is chronological on its own."""
    day = today or date.today().isoformat()
    words = re.sub(r"[^a-z0-9]+", "-", title.lower().replace("'", "")).strip("-")
    return f"{day}-{words}" if words else day


def create(
    repo: Path,
    title: str,
    origin: str = "ticket",
    reference: str = "",
    today: str | None = None,
) -> str:
    base = make_slug(title, today)
    slug = base
    attempt = 2
    while task_dir(repo, slug).exists():
        slug = f"{base}-{attempt}"
        attempt += 1

    task = Task(
        slug=slug,
        title=title,
        created=utcnow(),
        status=OPEN,
        origin=origin,
        reference=reference,
        nodes={node.id: NodeState() for node in nodes_module.TASK_NODES},
    )
    save(repo, task)
    return slug


def save(repo: Path, task: Task) -> None:
    payload = {
        "slug": task.slug,
        "title": task.title,
        "created": task.created,
        "status": task.status,
        "origin": task.origin,
        "reference": task.reference,
        "updated": task.updated,
        "nodes": {
            node_id: {
                "status": entry.status,
                "answers": entry.answers,
                "upstream_hashes": entry.upstream_hashes,
                "updated": entry.updated,
            }
            for node_id, entry in task.nodes.items()
        },
    }
    path = task_path(repo, task.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")
    )


def load(repo: Path, slug: str) -> Task:
    path = task_path(repo, slug)
    if not path.is_file():
        raise FileNotFoundError(f"no task at {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    task = Task(
        slug=payload.get("slug", slug),
        title=payload.get("title", ""),
        created=payload.get("created", ""),
        status=payload.get("status", OPEN),
        origin=payload.get("origin", "ticket"),
        reference=payload.get("reference") or "",
        updated=payload.get("updated"),
    )
    for node in nodes_module.TASK_NODES:
        entry = (payload.get("nodes") or {}).get(node.id) or {}
        task.nodes[node.id] = NodeState(
            status=entry.get("status", "empty"),
            answers=entry.get("answers") or {},
            upstream_hashes=entry.get("upstream_hashes") or {},
            updated=entry.get("updated"),
        )
    return task


def all_tasks(repo: Path) -> list[Task]:
    """Newest first. The list exists; it never greets anyone."""
    root = tasks_dir(repo)
    if not root.is_dir():
        return []
    found = []
    for folder in root.iterdir():
        if (folder / TASK_FILENAME).is_file():
            found.append(load(repo, folder.name))
    return sorted(found, key=lambda t: t.slug, reverse=True)


def next_node(task: Task) -> str | None:
    """The first node without a written artifact, in order."""
    for node in nodes_module.TASK_NODES:
        if task.nodes[node.id].status != "current":
            return node.id
    return None


def _touch(repo: Path, task: Task, node_id: str) -> None:
    """Mark progress, and refresh the project's left-off line.

    The note has to move for task work as well as project work. Without
    it a session that dies mid-task comes back describing whatever the
    project pipeline was doing last week - the same resume bug, arriving
    through the other pipeline kind.
    """
    task.updated = utcnow()
    if task.status == OPEN:
        task.status = IN_PROGRESS

    from . import state as state_module

    title = nodes_module.get_task_node(node_id).title
    state = state_module.load(repo)
    state.last_note = f"On task '{task.title}' - {title}."
    state_module.save(repo, state)


def record_answer(
    repo: Path,
    slug: str,
    node_id: str,
    question_id: str,
    answer: str,
) -> Task:
    task = load(repo, slug)
    entry = task.nodes[node_id]
    entry.answers[question_id] = answer
    entry.updated = utcnow()
    if entry.status == "empty":
        entry.status = "in_progress"
    _touch(repo, task, node_id)
    save(repo, task)
    return task


def write(
    repo: Path,
    slug: str,
    node_id: str,
    body: str,
    summary: str,
) -> Path:
    node = nodes_module.get_task_node(node_id)
    task = load(repo, slug)
    path = artifact_path(repo, slug, node_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"# {node.title}\n\n> {summary.strip()}\n\n{body.strip()}\n"
    path.write_bytes(text.encode("utf-8"))

    task.nodes[node_id].status = "current"
    task.nodes[node_id].updated = utcnow()
    _touch(repo, task, node_id)
    # Done is reached by finishing the work, never by declaring it.
    if next_node(task) is None:
        task.status = DONE
    save(repo, task)
    return path


def abandon(repo: Path, slug: str) -> Task:
    task = load(repo, slug)
    task.status = ABANDONED
    task.updated = utcnow()
    save(repo, task)
    return task


def reopen(repo: Path, slug: str) -> Task:
    """Abandoning is always reversible - it is not a decision to defend."""
    task = load(repo, slug)
    task.status = DONE if next_node(task) is None else IN_PROGRESS
    task.updated = utcnow()
    save(repo, task)
    return task


def live_task(repo: Path) -> Task | None:
    """The one task that may claim the next-action slot.

    In progress beats merely open, and both beat nothing. Finished and
    abandoned tasks are invisible here by construction, which is the
    whole reason status is stored rather than derived.
    """
    candidates = [t for t in all_tasks(repo) if t.status in LIVE]
    if not candidates:
        return None
    started = [t for t in candidates if t.status == IN_PROGRESS]
    pool = started or candidates
    return max(pool, key=lambda t: (t.updated or "", t.slug))
