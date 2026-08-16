"""Global pipeline definition.

Node definitions ship with the package and are identical for every repo.
Per-repo state lives in pipeline.yaml and is handled by state.py.
"""

from dataclasses import dataclass

PHASES: tuple[str, ...] = ("problem", "analysis", "design", "code")

FLAGS: tuple[str, ...] = ("has_db", "has_ui", "has_state", "multi_service")

ALWAYS = "always"
FLAG = "flag"
ON_DEMAND = "on_demand"


@dataclass(frozen=True)
class NodeDef:
    id: str
    title: str
    phase: str
    deps: tuple[str, ...] = ()
    activation: str = ALWAYS
    flag: str | None = None
    renders: str = "markdown"
    filename: str = ""


NODES: tuple[NodeDef, ...] = (
    NodeDef(
        id="problem-statement",
        title="Problem statement",
        phase="problem",
        renders="markdown",
        filename="01-problem.md",
    ),
    NodeDef(
        id="functional-requirements",
        title="Functional requirements",
        phase="analysis",
        deps=("problem-statement",),
        renders="markdown",
        filename="02-requirements.md",
    ),
    NodeDef(
        id="use-case-diagram",
        title="Use case diagram",
        phase="analysis",
        deps=("functional-requirements",),
        renders="mermaid_flow",
        filename="03-use-case-diagram.md",
    ),
    NodeDef(
        id="use-case-descriptions",
        title="Use case descriptions",
        phase="analysis",
        deps=("functional-requirements", "use-case-diagram"),
        renders="markdown",
        filename="04-use-case-descriptions.md",
    ),
    NodeDef(
        id="domain-model",
        title="Domain model",
        phase="analysis",
        deps=("problem-statement", "functional-requirements"),
        renders="mermaid_class",
        filename="glossary.md",
    ),
    NodeDef(
        id="test-cases",
        title="Test cases",
        phase="analysis",
        deps=("use-case-descriptions",),
        renders="markdown",
        filename="05-test-cases.md",
    ),
    NodeDef(
        id="activity-diagram",
        title="Activity diagram",
        phase="analysis",
        deps=("use-case-descriptions",),
        activation=ON_DEMAND,
        renders="mermaid_flow",
        filename="activity-{slug}.md",
    ),
    NodeDef(
        id="architecture",
        title="Architecture",
        phase="design",
        deps=("functional-requirements", "domain-model"),
        renders="markdown",
        filename="06-architecture.md",
    ),
    NodeDef(
        id="er-model",
        title="ER / relational model",
        phase="design",
        deps=("domain-model",),
        activation=FLAG,
        flag="has_db",
        renders="mermaid_er",
        filename="07-er-model.md",
    ),
    NodeDef(
        id="state-machine",
        title="State machine",
        phase="design",
        deps=("domain-model",),
        activation=FLAG,
        flag="has_state",
        renders="mermaid_state",
        filename="08-state-machine.md",
    ),
    NodeDef(
        id="deployment",
        title="Deployment",
        phase="design",
        deps=("architecture",),
        activation=FLAG,
        flag="multi_service",
        renders="mermaid_flow",
        filename="09-deployment.md",
    ),
    NodeDef(
        id="sequence-diagram",
        title="Sequence diagram",
        phase="design",
        deps=("use-case-descriptions", "architecture"),
        activation=ON_DEMAND,
        renders="mermaid_sequence",
        filename="sequence-{slug}.md",
    ),
)

_BY_ID = {node.id: node for node in NODES}


def all_nodes() -> tuple[NodeDef, ...]:
    return NODES


def get_node(node_id: str) -> NodeDef:
    return _BY_ID[node_id]


def active_nodes(
    flags: dict[str, bool],
    on_demand: tuple[str, ...] = (),
) -> tuple[NodeDef, ...]:
    """Nodes that apply to this project, in pipeline order.

    Nodes that do not apply are omitted entirely rather than marked
    inactive - the caller should never render them.
    """
    result = []
    for node in NODES:
        if node.activation == ALWAYS:
            result.append(node)
        elif node.activation == FLAG and flags.get(node.flag or "", False):
            result.append(node)
        elif node.activation == ON_DEMAND and node.id in on_demand:
            result.append(node)
    return tuple(result)
