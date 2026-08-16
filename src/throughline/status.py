"""The status view.

Two rules hold this module together, both from the spec: exactly one next
action is ever offered, and nothing here reports outstanding work as a
count, a badge, or a warning.
"""

from dataclasses import dataclass, field

from . import nodes as nodes_module
from .state import CURRENT, DRAFTED, EMPTY, IN_PROGRESS, PipelineState, node_state

NO_NOTE = "Nothing yet - this is the first session."


@dataclass
class PhaseProgress:
    phase: str
    filled: int
    total: int


@dataclass
class Status:
    project: str = ""
    where_you_left_off: str = NO_NOTE
    next_node: str | None = None
    next_title: str = ""
    answered: list[str] = field(default_factory=list)
    phases: list[PhaseProgress] = field(default_factory=list)


def _active(state: PipelineState) -> tuple:
    on_demand = tuple(state.on_demand.keys())
    return nodes_module.active_nodes(state.flags, on_demand)


def next_node(state: PipelineState) -> str | None:
    """One next node, in this priority order.

    An in-progress node comes first so an interrupted interview resumes.
    Then a drafted node, so what Claude wrote gets read before anything is
    built on top of it. Then the first empty node in pipeline order.
    """
    for wanted in (IN_PROGRESS, DRAFTED, EMPTY):
        for node in _active(state):
            if node_state(state, node.id).status == wanted:
                return node.id
    return None


def progress(state: PipelineState) -> list[PhaseProgress]:
    active = _active(state)
    result = []
    for phase in nodes_module.PHASES:
        in_phase = [n for n in active if n.phase == phase]
        if not in_phase:
            continue
        filled = sum(
            1 for n in in_phase if node_state(state, n.id).status == CURRENT
        )
        result.append(PhaseProgress(phase=phase, filled=filled, total=len(in_phase)))
    return result


def compute(state: PipelineState) -> Status:
    chosen = next_node(state)
    return Status(
        project=state.project,
        where_you_left_off=state.last_note or NO_NOTE,
        next_node=chosen,
        next_title=nodes_module.get_node(chosen).title if chosen else "",
        answered=list(node_state(state, chosen).answers) if chosen else [],
        phases=progress(state),
    )


def render_text(status: Status) -> str:
    lines = [status.project or "(unnamed project)", ""]
    lines.append("Where you left off")
    lines.append(f"  {status.where_you_left_off}")
    lines.append("")
    if status.next_node:
        lines.append(f"Next: {status.next_title}")
        if status.answered:
            already = ", ".join(status.answered)
            lines.append(f"  already answered: {already}")
    else:
        lines.append("Nothing waiting. The pipeline is complete.")
    lines.append("")
    for phase in status.phases:
        bar = "#" * phase.filled + "." * (phase.total - phase.filled)
        lines.append(f"  {phase.phase:<10} {bar}")
    return "\n".join(lines) + "\n"
