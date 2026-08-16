"""Two-sided artifacts, and the gaps between the sides.

A project node can describe two things: what is true today, and what
should be true. The convention is two top-level sections, `# Current` and
`# Target`, which is what the first real run produced by hand before
anything here existed.

**A gap is a reading, not a thing.** It is the difference between the two
sides, computed from the artifact whenever someone asks, and never stored.

Storing gaps would give them a lifecycle. A lifecycle needs closing.
Closing needs a list of what is still open - which is the tracker this
tool exists not to be. One real run produced a dozen gaps in an afternoon;
as stored objects that is a backlog greeting you the next morning.

So they are recomputed every time, and nothing becomes work until someone
says so.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from . import artifacts
from . import nodes as nodes_module
from . import state as state_module
from . import tasks as tasks_module

CURRENT_HEADING = "current"
TARGET_HEADING = "target"

# A side heading is the word alone, or the word then a separator then a
# description - real artifacts write `# Target - single VPS, split
# images`. Requiring the separator is what keeps `# Current state of the
# target audience` from being read as a side.
_SIDE = re.compile(r"^(current|target)(?:\s*[-–—:]\s*.*)?$", re.IGNORECASE)


def _side_of(heading: str) -> str | None:
    match = _SIDE.match(heading.strip())
    return match.group(1).lower() if match else None


@dataclass(frozen=True)
class Sides:
    preamble: str = ""
    current: str = ""
    target: str = ""


@dataclass(frozen=True)
class Gap:
    node: str
    title: str
    text: str


def _sections(text: str) -> list[tuple[str, str]]:
    """Split on top-level headings, keeping the leading text."""
    parts: list[tuple[str, list[str]]] = [("", [])]
    for line in text.split("\n"):
        heading = re.match(r"^#\s+(.*)$", line)
        if heading:
            parts.append((heading.group(1).strip(), []))
        else:
            parts[-1][1].append(line)
    return [(name, "\n".join(body).strip()) for name, body in parts]


def split_sides(text: str) -> Sides:
    """Separate an artifact into preamble, current and target.

    An artifact with no `# Target` section is one-sided, and everything
    after the title is its current side. That is the normal case: the
    target side is a per-repo switch, and most repos leave it off.
    """
    preamble = []
    current = ""
    target = ""
    seen_side = False

    for index, (name, body) in enumerate(_sections(text)):
        side = _side_of(name)
        if side == TARGET_HEADING:
            target = body
            seen_side = True
        elif side == CURRENT_HEADING:
            current = body
            seen_side = True
        elif index <= 1 and not seen_side:
            # The artifact's own title, and any prose before either side.
            preamble.append(body)
        elif not seen_side:
            preamble.append(f"# {name}\n\n{body}" if name else body)
        else:
            # A trailing section after both sides belongs to neither.
            preamble.append(f"# {name}\n\n{body}" if name else body)

    if not seen_side:
        current = "\n\n".join(p for p in preamble if p).strip()
        preamble = []

    return Sides(
        preamble="\n\n".join(p for p in preamble if p).strip(),
        current=current,
        target=target,
    )


def from_text(node_id: str, text: str) -> list[Gap]:
    """Every subsection of the target side is one gap.

    Mechanical on purpose. Nothing here judges which differences matter -
    that judgement is the user's, and it happens at promotion.
    """
    target = split_sides(text).target
    if not target:
        return []

    found: list[Gap] = []
    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        # Prose before the first subsection is framing, not a gap. Real
        # target sections open with a sentence of context, and counting
        # that as an untitled gap puts a blank row in the list.
        if title is None:
            return
        found.append(Gap(node=node_id, title=title, text="\n".join(body).strip()))

    for line in target.split("\n"):
        heading = re.match(r"^##\s+(.*)$", line)
        if heading:
            flush()
            title = heading.group(1).strip()
            body = []
        else:
            body.append(line)
    flush()

    # No subsections at all: the whole target side is the one difference.
    if not found:
        return [Gap(node=node_id, title="", text=target.strip())]

    return [g for g in found if g.text or g.title]


def for_node(repo: Path, node_id: str) -> list[Gap]:
    path = artifacts.artifact_path(repo, node_id)
    if not path.is_file():
        return []
    return from_text(node_id, path.read_text(encoding="utf-8"))


def for_repo(repo: Path) -> list[Gap]:
    """Every gap in the project, recomputed from the artifacts.

    Reading gaps creates nothing and changes nothing.
    """
    loaded = state_module.load(repo)
    active = nodes_module.active_nodes(loaded.flags, tuple(loaded.on_demand.keys()))
    found: list[Gap] = []
    for node in active:
        found.extend(for_node(repo, node.id))
    return found


def promote(repo: Path, gap: Gap) -> str:
    """Turn one gap into a task. Only ever when asked.

    The task inherits the artifact it came from, so `understand` is
    already answered - the target side already said what is wanted - and
    the flow starts at `analyze`.
    """
    node = nodes_module.get_node(gap.node)
    title = gap.title or f"{node.title}: target"
    slug = tasks_module.create(
        repo,
        title,
        origin="gap",
        reference=f"{gap.node} / {gap.title}" if gap.title else gap.node,
    )
    body = (
        f"Promoted from the target side of **{node.title}**.\n\n"
        f"{gap.text}\n"
    )
    tasks_module.write(
        repo,
        slug,
        "understand",
        body,
        f"What the {node.title} artifact says should be true, and is not yet.",
    )
    return slug
