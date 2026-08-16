"""Dependency-scoped context for a single node.

A node reads its declared dependencies and the glossary, never the whole
repo. This is the token budget, and it is why re-entering a project stays
cheap.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import nodes as nodes_module
from .artifacts import read_artifact

GLOSSARY_NODE = "domain-model"


@dataclass
class Document:
    node_id: str
    title: str
    text: str


@dataclass
class Context:
    node_id: str
    documents: list[Document] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return sum(len(d.text.splitlines()) for d in self.documents)


def assemble(repo: Path, node_id: str) -> Context:
    node = nodes_module.get_node(node_id)
    wanted = list(node.deps)
    if node_id != GLOSSARY_NODE and GLOSSARY_NODE not in wanted:
        wanted.append(GLOSSARY_NODE)

    ctx = Context(node_id=node_id)
    for dep in wanted:
        text = read_artifact(repo, dep)
        if text is None:
            if dep in node.deps:
                ctx.missing.append(dep)
            continue
        ctx.documents.append(
            Document(
                node_id=dep,
                title=nodes_module.get_node(dep).title,
                text=text,
            )
        )
    return ctx


def render(ctx: Context) -> str:
    node = nodes_module.get_node(ctx.node_id)
    parts = [f"# Context for {node.title}", ""]
    if not ctx.documents and not ctx.missing:
        parts.append("This node has no upstream dependencies.")
        return "\n".join(parts) + "\n"
    for doc in ctx.documents:
        parts.append(f"## {doc.title}")
        parts.append("")
        parts.append(doc.text.strip())
        parts.append("")
    for dep in ctx.missing:
        title = nodes_module.get_node(dep).title
        parts.append(f"## {title}")
        parts.append("")
        parts.append("This dependency is not written yet.")
        parts.append("")
    return "\n".join(parts)
