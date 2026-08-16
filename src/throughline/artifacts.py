"""Artifact files on disk.

Every artifact is plain markdown that opens with its title and a
one-sentence summary, so the pipeline can be re-entered without reading
the body.
"""

from pathlib import Path

from . import nodes as nodes_module
from .state import project_dir

MERMAID_KINDS: dict[str, str] = {
    "mermaid_flow": "flowchart TD",
    "mermaid_class": "classDiagram",
    "mermaid_er": "erDiagram",
    "mermaid_state": "stateDiagram-v2",
    "mermaid_sequence": "sequenceDiagram",
}


def artifact_path(repo: Path, node_id: str, slug: str | None = None) -> Path:
    node = nodes_module.get_node(node_id)
    filename = node.filename
    if "{slug}" in filename:
        if not slug:
            raise ValueError(f"node {node_id} requires a slug")
        filename = filename.replace("{slug}", slug)
    elif slug:
        raise ValueError(f"node {node_id} does not take a slug")
    return project_dir(repo) / filename


def read_artifact(repo: Path, node_id: str, slug: str | None = None) -> str | None:
    path = artifact_path(repo, node_id, slug)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_artifact(
    repo: Path,
    node_id: str,
    body: str,
    summary: str,
    slug: str | None = None,
) -> Path:
    node = nodes_module.get_node(node_id)
    path = artifact_path(repo, node_id, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"# {node.title}\n\n> {summary.strip()}\n\n{body.strip()}\n"
    # LF on every platform. A browser textarea hands back LF whatever it
    # was given, so writing CRLF here would make the first save through
    # the app rewrite every line - a diff the user never made.
    path.write_bytes(text.encode("utf-8"))
    return path


def summary_of(text: str) -> str:
    """The blockquote directly under the heading, or an empty string.

    A blockquote that appears after body text is a normal quotation, not
    the summary, so only the leading run counts.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            continue
        if stripped.startswith(">"):
            return stripped.lstrip("> ").strip()
        return ""
    return ""
