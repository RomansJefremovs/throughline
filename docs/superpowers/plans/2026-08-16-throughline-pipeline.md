# Throughline Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI plus a Claude Code skill pack that maintains an analysis-and-design artifact pipeline inside any repository, driven by short interviews instead of document generation.

**Architecture:** All deterministic work — node definitions, state persistence, dependency-scoped context assembly, upstream hashing, status computation, repo scanning — lives in a small, fully tested Python package invoked as a CLI. All conversational work — asking questions, writing prose, drawing diagrams — lives in skill markdown that shells out to that CLI. The CLI never calls a model; the skill never computes state. Every command accepts `--repo` so the tool operates on a target repository, not on itself.

**Tech Stack:** Python 3.12, PyYAML, pytest, argparse (no CLI framework dependency).

## Global Constraints

- Python 3.12 or later. The development machine has 3.12.10.
- Dependencies limited to `PyYAML` (runtime) and `pytest` (dev). Nothing else.
- Artifact directory is `docs/project/` inside the target repo, relative to the repo root, always visible (never dot-prefixed).
- State file is `docs/project/pipeline.yaml`. It is the only machine-owned file; everything else is hand-editable markdown.
- Node definitions are global (shipped in the package). Node state is per-repo (in `pipeline.yaml`). Never write node definitions into `pipeline.yaml`.
- Answers persist immediately on every single answer, never batched at the end of an interview.
- Staleness is computed and returned by the CLI but never rendered as a count, badge, or warning colour in any status output.
- Status output shows exactly one next node. Never a list of outstanding work.
- All timestamps are UTC ISO-8601 with a `Z` suffix.
- Platform is Windows; all paths must go through `pathlib`, never string concatenation.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, pytest config |
| `src/throughline/nodes.py` | Global node definitions, phases, activation resolution |
| `src/throughline/state.py` | `pipeline.yaml` load/save/init, answer persistence |
| `src/throughline/artifacts.py` | Artifact paths, read/write, summary extraction |
| `src/throughline/hashing.py` | Per-dependency content hashing and staleness |
| `src/throughline/context.py` | Dependency-scoped context assembly for one node |
| `src/throughline/status.py` | Next-node selection and progress computation |
| `src/throughline/scan.py` | Repo reconnaissance and transcript directory location |
| `src/throughline/cli.py` | argparse entrypoint, JSON and text output |
| `skills/throughline/SKILL.md` | Skill entry point, command reference |
| `skills/throughline/questions/*.md` | Per-node question banks |
| `tests/test_*.py` | One test module per source module |

---

### Task 1: Project scaffold and node definitions

**Files:**
- Create: `pyproject.toml`
- Create: `src/throughline/__init__.py`
- Create: `src/throughline/nodes.py`
- Test: `tests/test_nodes.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `PHASES: tuple[str, ...]` — `("problem", "analysis", "design", "code")`
  - `class NodeDef` — frozen dataclass with fields `id: str`, `title: str`, `phase: str`, `deps: tuple[str, ...]`, `activation: str`, `flag: str | None`, `renders: str`, `filename: str`
  - `NODES: tuple[NodeDef, ...]` — the global pipeline in dependency order
  - `all_nodes() -> tuple[NodeDef, ...]`
  - `get_node(node_id: str) -> NodeDef` — raises `KeyError` if unknown
  - `active_nodes(flags: dict[str, bool], on_demand: tuple[str, ...] = ()) -> tuple[NodeDef, ...]`
  - `FLAGS: tuple[str, ...]` — `("has_db", "has_ui", "has_state", "multi_service")`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "throughline"
version = "0.1.0"
description = "Analysis and design artifact pipeline anchored in a repository"
requires-python = ">=3.12"
dependencies = ["PyYAML>=6.0"]

[project.scripts]
throughline = "throughline.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create the empty package marker**

Create `src/throughline/__init__.py` containing exactly:

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_nodes.py`:

```python
import pytest

from throughline import nodes


def test_all_nodes_have_unique_ids():
    ids = [n.id for n in nodes.all_nodes()]
    assert len(ids) == len(set(ids))


def test_every_dependency_refers_to_a_real_node():
    ids = {n.id for n in nodes.all_nodes()}
    for node in nodes.all_nodes():
        for dep in node.deps:
            assert dep in ids, f"{node.id} depends on unknown node {dep}"


def test_dependencies_come_earlier_in_the_tuple():
    seen = set()
    for node in nodes.all_nodes():
        for dep in node.deps:
            assert dep in seen, f"{node.id} depends on {dep} which is defined later"
        seen.add(node.id)


def test_every_phase_is_known():
    for node in nodes.all_nodes():
        assert node.phase in nodes.PHASES


def test_get_node_returns_the_definition():
    assert nodes.get_node("domain-model").title == "Domain model"


def test_get_node_raises_on_unknown_id():
    with pytest.raises(KeyError):
        nodes.get_node("no-such-node")


def test_always_nodes_are_active_with_no_flags():
    active = {n.id for n in nodes.active_nodes({})}
    assert "problem-statement" in active
    assert "domain-model" in active
    assert "architecture" in active


def test_flag_nodes_are_inactive_when_flag_is_false():
    active = {n.id for n in nodes.active_nodes({"has_db": False})}
    assert "er-model" not in active


def test_flag_nodes_are_active_when_flag_is_true():
    active = {n.id for n in nodes.active_nodes({"has_db": True})}
    assert "er-model" in active


def test_missing_flag_is_treated_as_false():
    active = {n.id for n in nodes.active_nodes({})}
    assert "state-machine" not in active


def test_on_demand_nodes_are_inactive_by_default():
    active = {n.id for n in nodes.active_nodes({"has_db": True})}
    assert "activity-diagram" not in active


def test_on_demand_nodes_activate_when_named():
    active = {n.id for n in nodes.active_nodes({}, on_demand=("activity-diagram",))}
    assert "activity-diagram" in active


def test_active_nodes_preserve_pipeline_order():
    active = [n.id for n in nodes.active_nodes({"has_db": True})]
    assert active.index("problem-statement") < active.index("domain-model")
    assert active.index("domain-model") < active.index("er-model")
```

- [ ] **Step 4: Run the test to verify it fails**

```bash
python -m pytest tests/test_nodes.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.nodes'`.

- [ ] **Step 5: Write the implementation**

Create `src/throughline/nodes.py`:

```python
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
```

- [ ] **Step 6: Run the test to verify it passes**

```bash
python -m pytest tests/test_nodes.py -v
```

Expected: 13 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/throughline/__init__.py src/throughline/nodes.py tests/test_nodes.py
git commit -m "feat: add global pipeline node definitions"
```

---

### Task 2: Pipeline state

**Files:**
- Create: `src/throughline/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `throughline.nodes.FLAGS`, `throughline.nodes.active_nodes`
- Produces:
  - `PROJECT_DIR: str` — `"docs/project"`
  - `STATE_FILENAME: str` — `"pipeline.yaml"`
  - `EMPTY: str`, `IN_PROGRESS: str`, `CURRENT: str` — status constants `"empty"`, `"in_progress"`, `"current"`
  - `class NodeState` — dataclass with `status: str`, `confirmed: bool`, `answers: dict[str, str]`, `upstream_hashes: dict[str, str]`, `updated: str | None`
  - `class PipelineState` — dataclass with `version: int`, `project: str`, `created: str`, `flags: dict[str, bool]`, `on_demand: dict[str, list[str]]`, `nodes: dict[str, NodeState]`, `last_note: str`, `last_node: str | None`
  - `state_path(repo: Path) -> Path`
  - `exists(repo: Path) -> bool`
  - `init(repo: Path, project: str, flags: dict[str, bool]) -> PipelineState`
  - `load(repo: Path) -> PipelineState` — raises `FileNotFoundError` if absent
  - `save(repo: Path, state: PipelineState) -> None`
  - `node_state(state: PipelineState, node_id: str) -> NodeState` — creates a default entry if missing
  - `record_answer(repo: Path, node_id: str, question_id: str, answer: str) -> PipelineState` — loads, mutates, saves, returns
  - `set_note(repo: Path, node_id: str, note: str) -> PipelineState`
  - `utcnow() -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_state.py`:

```python
import pytest

from throughline import state


def test_state_path_is_inside_docs_project(tmp_path):
    assert state.state_path(tmp_path) == tmp_path / "docs" / "project" / "pipeline.yaml"


def test_exists_is_false_before_init(tmp_path):
    assert state.exists(tmp_path) is False


def test_init_creates_the_file(tmp_path):
    state.init(tmp_path, "demo", {"has_db": True})
    assert state.exists(tmp_path) is True


def test_init_records_project_and_flags(tmp_path):
    result = state.init(tmp_path, "demo", {"has_db": True})
    assert result.project == "demo"
    assert result.flags["has_db"] is True


def test_init_defaults_unlisted_flags_to_false(tmp_path):
    result = state.init(tmp_path, "demo", {"has_db": True})
    assert result.flags["has_state"] is False
    assert result.flags["multi_service"] is False


def test_init_seeds_every_active_node_as_empty(tmp_path):
    result = state.init(tmp_path, "demo", {})
    assert result.nodes["problem-statement"].status == state.EMPTY
    assert "er-model" not in result.nodes


def test_load_round_trips_everything(tmp_path):
    original = state.init(tmp_path, "demo", {"has_db": True})
    original.nodes["problem-statement"].status = state.CURRENT
    original.nodes["problem-statement"].answers = {"q1": "yes"}
    original.nodes["problem-statement"].upstream_hashes = {"x": "abc"}
    original.last_note = "deciding on covers"
    state.save(tmp_path, original)

    reloaded = state.load(tmp_path)
    assert reloaded.project == "demo"
    assert reloaded.flags["has_db"] is True
    assert reloaded.nodes["problem-statement"].status == state.CURRENT
    assert reloaded.nodes["problem-statement"].answers == {"q1": "yes"}
    assert reloaded.nodes["problem-statement"].upstream_hashes == {"x": "abc"}
    assert reloaded.last_note == "deciding on covers"


def test_load_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        state.load(tmp_path)


def test_node_state_creates_a_default_entry(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    entry = state.node_state(loaded, "sequence-diagram")
    assert entry.status == state.EMPTY
    assert entry.answers == {}


def test_record_answer_persists_immediately(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "a customer-facing tool")

    reloaded = state.load(tmp_path)
    assert reloaded.nodes["problem-statement"].answers["q1"] == "a customer-facing tool"


def test_record_answer_marks_the_node_in_progress(tmp_path):
    state.init(tmp_path, "demo", {})
    result = state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert result.nodes["problem-statement"].status == state.IN_PROGRESS


def test_record_answer_does_not_downgrade_a_current_node(tmp_path):
    state.init(tmp_path, "demo", {})
    loaded = state.load(tmp_path)
    loaded.nodes["problem-statement"].status = state.CURRENT
    state.save(tmp_path, loaded)

    result = state.record_answer(tmp_path, "problem-statement", "q2", "y")
    assert result.nodes["problem-statement"].status == state.CURRENT


def test_record_answer_stamps_updated(tmp_path):
    state.init(tmp_path, "demo", {})
    result = state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert result.nodes["problem-statement"].updated.endswith("Z")


def test_set_note_records_the_memory_jog(tmp_path):
    state.init(tmp_path, "demo", {})
    state.set_note(tmp_path, "domain-model", "deciding whether a cover belongs to a clip")

    reloaded = state.load(tmp_path)
    assert reloaded.last_note == "deciding whether a cover belongs to a clip"
    assert reloaded.last_node == "domain-model"


def test_utcnow_is_iso_with_z(tmp_path):
    assert state.utcnow().endswith("Z")
    assert "T" in state.utcnow()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_state.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.state'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/state.py`:

```python
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
IN_PROGRESS = "in_progress"
CURRENT = "current"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class NodeState:
    status: str = EMPTY
    confirmed: bool = False
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
                "confirmed": entry.confirmed,
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
            status=entry.get("status", EMPTY),
            confirmed=bool(entry.get("confirmed", False)),
            answers=entry.get("answers") or {},
            upstream_hashes=entry.get("upstream_hashes") or {},
            updated=entry.get("updated"),
        )
    return result


def node_state(state: PipelineState, node_id: str) -> NodeState:
    if node_id not in state.nodes:
        state.nodes[node_id] = NodeState()
    return state.nodes[node_id]


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
    save(repo, state)
    return state


def set_note(repo: Path, node_id: str, note: str) -> PipelineState:
    state = load(repo)
    state.last_note = note
    state.last_node = node_id
    save(repo, state)
    return state
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_state.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/state.py tests/test_state.py
git commit -m "feat: add per-repo pipeline state with immediate answer persistence"
```

---

### Task 3: Artifacts

**Files:**
- Create: `src/throughline/artifacts.py`
- Test: `tests/test_artifacts.py`

**Interfaces:**
- Consumes: `throughline.nodes.get_node`, `throughline.state.project_dir`
- Produces:
  - `artifact_path(repo: Path, node_id: str, slug: str | None = None) -> Path`
  - `read_artifact(repo: Path, node_id: str, slug: str | None = None) -> str | None`
  - `write_artifact(repo: Path, node_id: str, body: str, summary: str, slug: str | None = None) -> Path`
  - `summary_of(text: str) -> str` — returns `""` when there is no summary line
  - `MERMAID_KINDS: dict[str, str]` — maps a `renders` value to its mermaid header keyword

- [ ] **Step 1: Write the failing test**

Create `tests/test_artifacts.py`:

```python
import pytest

from throughline import artifacts


def test_artifact_path_uses_the_node_filename(tmp_path):
    path = artifacts.artifact_path(tmp_path, "domain-model")
    assert path == tmp_path / "docs" / "project" / "glossary.md"


def test_artifact_path_substitutes_a_slug(tmp_path):
    path = artifacts.artifact_path(tmp_path, "activity-diagram", slug="posting-flow")
    assert path.name == "activity-posting-flow.md"


def test_artifact_path_requires_a_slug_for_on_demand_nodes(tmp_path):
    with pytest.raises(ValueError):
        artifacts.artifact_path(tmp_path, "activity-diagram")


def test_read_artifact_returns_none_when_absent(tmp_path):
    assert artifacts.read_artifact(tmp_path, "domain-model") is None


def test_write_then_read_round_trips(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body text.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert "Body text." in text


def test_write_artifact_starts_with_the_title(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert text.startswith("# Problem statement\n")


def test_write_artifact_includes_the_summary_as_a_blockquote(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert "> A summary." in text


def test_write_artifact_creates_missing_directories(tmp_path):
    path = artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "S.")
    assert path.is_file()


def test_summary_of_extracts_the_blockquote():
    text = "# Title\n\n> The one-line summary.\n\nBody.\n"
    assert artifacts.summary_of(text) == "The one-line summary."


def test_summary_of_returns_empty_when_absent():
    assert artifacts.summary_of("# Title\n\nBody.\n") == ""


def test_summary_of_ignores_blockquotes_after_body_text():
    text = "# Title\n\nBody first.\n\n> Not the summary.\n"
    assert artifacts.summary_of(text) == ""


def test_mermaid_kinds_cover_every_rendering_node():
    from throughline import nodes

    for node in nodes.all_nodes():
        if node.renders != "markdown":
            assert node.renders in artifacts.MERMAID_KINDS
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_artifacts.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.artifacts'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/artifacts.py`:

```python
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
    path.write_text(text, encoding="utf-8")
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_artifacts.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/artifacts.py tests/test_artifacts.py
git commit -m "feat: add artifact read and write with summary lines"
```

---

### Task 4: Hashing and staleness

**Files:**
- Create: `src/throughline/hashing.py`
- Test: `tests/test_hashing.py`

**Interfaces:**
- Consumes: `throughline.nodes.get_node`, `throughline.artifacts.read_artifact`, `throughline.state.PipelineState`, `throughline.state.node_state`
- Produces:
  - `content_hash(text: str) -> str` — sha256 hex of the normalised text
  - `current_upstream_hashes(repo: Path, node_id: str) -> dict[str, str]`
  - `stale_deps(repo: Path, node_id: str, state: PipelineState) -> list[str]`
  - `is_stale(repo: Path, node_id: str, state: PipelineState) -> bool`
  - `stamp(repo: Path, node_id: str, state: PipelineState) -> None` — mutates state in place, does not save

- [ ] **Step 1: Write the failing test**

Create `tests/test_hashing.py`:

```python
from throughline import artifacts, hashing, state


def test_content_hash_is_stable():
    assert hashing.content_hash("abc") == hashing.content_hash("abc")


def test_content_hash_differs_on_different_content():
    assert hashing.content_hash("abc") != hashing.content_hash("abd")


def test_content_hash_ignores_line_ending_style():
    assert hashing.content_hash("a\r\nb") == hashing.content_hash("a\nb")


def test_content_hash_ignores_trailing_whitespace():
    assert hashing.content_hash("a\n\n") == hashing.content_hash("a")


def test_current_upstream_hashes_covers_every_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    result = hashing.current_upstream_hashes(tmp_path, "domain-model")
    assert set(result) == {"problem-statement", "functional-requirements"}


def test_missing_upstream_artifact_hashes_to_empty_marker(tmp_path):
    result = hashing.current_upstream_hashes(tmp_path, "domain-model")
    assert result["problem-statement"] == hashing.MISSING


def test_a_node_with_no_dependencies_has_no_hashes(tmp_path):
    assert hashing.current_upstream_hashes(tmp_path, "problem-statement") == {}


def test_stale_deps_is_empty_right_after_stamping(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)
    assert hashing.stale_deps(tmp_path, "domain-model", loaded) == []


def test_stale_deps_names_the_changed_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)

    artifacts.write_artifact(tmp_path, "problem-statement", "changed", "s")
    assert hashing.stale_deps(tmp_path, "domain-model", loaded) == ["problem-statement"]


def test_is_stale_is_false_for_a_never_stamped_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert hashing.is_stale(tmp_path, "domain-model", loaded) is False


def test_is_stale_is_true_after_an_upstream_change(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)
    artifacts.write_artifact(tmp_path, "problem-statement", "changed", "s")
    assert hashing.is_stale(tmp_path, "domain-model", loaded) is True


def test_stamp_mutates_state_without_saving(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)

    assert loaded.nodes["domain-model"].upstream_hashes != {}
    assert state.load(tmp_path).nodes["domain-model"].upstream_hashes == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_hashing.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.hashing'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/hashing.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_hashing.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/hashing.py tests/test_hashing.py
git commit -m "feat: add upstream hashing and staleness detection"
```

---

### Task 5: Context assembly

**Files:**
- Create: `src/throughline/context.py`
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `throughline.nodes.get_node`, `throughline.artifacts.read_artifact`
- Produces:
  - `GLOSSARY_NODE: str` — `"domain-model"`
  - `class Document` — dataclass with `node_id: str`, `title: str`, `text: str`
  - `class Context` — dataclass with `node_id: str`, `documents: list[Document]`, `missing: list[str]`; property `line_count: int`
  - `assemble(repo: Path, node_id: str) -> Context`
  - `render(ctx: Context) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_context.py`:

```python
from throughline import artifacts, context


def test_context_loads_only_declared_dependencies(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "test-cases", "T", "s")

    ctx = context.assemble(tmp_path, "domain-model")
    loaded = {d.node_id for d in ctx.documents}
    assert loaded == {"problem-statement", "functional-requirements"}


def test_context_includes_the_glossary_for_downstream_nodes(tmp_path):
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "use-case-diagram", "U", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "use-case-descriptions")
    assert "domain-model" in {d.node_id for d in ctx.documents}


def test_context_does_not_include_the_glossary_in_its_own_node(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "domain-model")
    assert [d.node_id for d in ctx.documents].count("domain-model") == 0


def test_context_does_not_duplicate_a_glossary_that_is_already_a_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "architecture")
    assert [d.node_id for d in ctx.documents].count("domain-model") == 1


def test_context_reports_missing_dependencies(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    ctx = context.assemble(tmp_path, "domain-model")
    assert ctx.missing == ["functional-requirements"]


def test_missing_dependencies_are_not_documents(tmp_path):
    ctx = context.assemble(tmp_path, "domain-model")
    assert ctx.documents == []


def test_line_count_sums_the_loaded_documents(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "a\nb", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "c", "s")
    ctx = context.assemble(tmp_path, "domain-model")
    expected = sum(len(d.text.splitlines()) for d in ctx.documents)
    assert ctx.line_count == expected


def test_render_labels_each_document(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P body", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R body", "s")
    text = context.render(context.assemble(tmp_path, "domain-model"))
    assert "## Problem statement" in text
    assert "P body" in text


def test_render_notes_missing_dependencies(tmp_path):
    text = context.render(context.assemble(tmp_path, "domain-model"))
    assert "not written yet" in text


def test_render_of_a_root_node_is_short(tmp_path):
    text = context.render(context.assemble(tmp_path, "problem-statement"))
    assert "no upstream" in text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_context.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.context'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/context.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_context.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/context.py tests/test_context.py
git commit -m "feat: add dependency-scoped context assembly"
```

---

### Task 6: Status computation

**Files:**
- Create: `src/throughline/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: `throughline.nodes.active_nodes`, `throughline.state.PipelineState`, `throughline.state.node_state`, `throughline.state.CURRENT`
- Produces:
  - `class PhaseProgress` — dataclass with `phase: str`, `filled: int`, `total: int`
  - `class Status` — dataclass with `project: str`, `where_you_left_off: str`, `next_node: str | None`, `next_title: str`, `phases: list[PhaseProgress]`
  - `next_node(state: PipelineState) -> str | None`
  - `progress(state: PipelineState) -> list[PhaseProgress]`
  - `compute(state: PipelineState) -> Status`
  - `render_text(status: Status) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_status.py`:

```python
from throughline import state, status


def test_next_node_is_the_first_empty_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert status.next_node(loaded) == "problem-statement"


def test_next_node_skips_current_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    assert status.next_node(loaded) == "functional-requirements"


def test_next_node_prefers_an_in_progress_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    loaded.nodes["functional-requirements"].status = state.CURRENT
    loaded.nodes["use-case-diagram"].status = state.CURRENT
    loaded.nodes["domain-model"].status = state.IN_PROGRESS
    assert status.next_node(loaded) == "domain-model"


def test_next_node_prefers_unconfirmed_over_empty(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    for node_id in loaded.nodes:
        loaded.nodes[node_id].status = state.CURRENT
        loaded.nodes[node_id].confirmed = True
    loaded.nodes["domain-model"].confirmed = False
    assert status.next_node(loaded) == "domain-model"


def test_next_node_is_none_when_everything_is_done(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    for node_id in loaded.nodes:
        loaded.nodes[node_id].status = state.CURRENT
        loaded.nodes[node_id].confirmed = True
    assert status.next_node(loaded) is None


def test_progress_counts_only_active_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    design = [p for p in status.progress(loaded) if p.phase == "design"][0]
    assert design.total == 1


def test_progress_counts_flag_enabled_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {"has_db": True})
    design = [p for p in status.progress(loaded) if p.phase == "design"][0]
    assert design.total == 2


def test_progress_fills_current_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    problem = [p for p in status.progress(loaded) if p.phase == "problem"][0]
    assert problem.filled == 1


def test_progress_omits_phases_with_no_active_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert "code" not in [p.phase for p in status.progress(loaded)]


def test_compute_carries_the_memory_jog(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.last_note = "deciding whether a cover belongs to a clip"
    result = status.compute(loaded)
    assert result.where_you_left_off == "deciding whether a cover belongs to a clip"


def test_compute_falls_back_when_there_is_no_note(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    result = status.compute(loaded)
    assert result.where_you_left_off == "Nothing yet - this is the first session."


def test_compute_names_the_next_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    result = status.compute(loaded)
    assert result.next_title == "Problem statement"


def test_render_text_shows_one_next_action(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    text = status.render_text(status.compute(loaded))
    assert text.count("Next:") == 1


def test_render_text_never_reports_a_stale_count(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    text = status.render_text(status.compute(loaded)).lower()
    assert "stale" not in text
    assert "overdue" not in text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_status.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.status'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/status.py`:

```python
"""The status view.

Two rules hold this module together, both from the spec: exactly one next
action is ever offered, and nothing here reports outstanding work as a
count, a badge, or a warning.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import nodes as nodes_module
from .state import CURRENT, EMPTY, IN_PROGRESS, PipelineState, node_state

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
    phases: list[PhaseProgress] = field(default_factory=list)


def _active(state: PipelineState) -> tuple:
    on_demand = tuple(state.on_demand.keys())
    return nodes_module.active_nodes(state.flags, on_demand)


def next_node(state: PipelineState) -> str | None:
    """One next node, in this priority order.

    An in-progress node comes first so an interrupted interview resumes.
    Then an inferred-but-unconfirmed node, so bootstrap output gets
    checked before anything is built on top of it. Then the first empty
    node in pipeline order.
    """
    active = _active(state)
    for node in active:
        if node_state(state, node.id).status == IN_PROGRESS:
            return node.id
    for node in active:
        entry = node_state(state, node.id)
        if entry.status == CURRENT and not entry.confirmed:
            return node.id
    for node in active:
        if node_state(state, node.id).status == EMPTY:
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
        phases=progress(state),
    )


def render_text(status: Status) -> str:
    lines = [status.project or "(unnamed project)", ""]
    lines.append("Where you left off")
    lines.append(f"  {status.where_you_left_off}")
    lines.append("")
    if status.next_node:
        lines.append(f"Next: {status.next_title}")
    else:
        lines.append("Nothing waiting. The pipeline is complete.")
    lines.append("")
    for phase in status.phases:
        bar = "#" * phase.filled + "." * (phase.total - phase.filled)
        lines.append(f"  {phase.phase:<10} {bar}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_status.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/status.py tests/test_status.py
git commit -m "feat: add status computation with a single next action"
```

---

### Task 7: Repo scan and transcript location

**Files:**
- Create: `src/throughline/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `encode_repo_path(repo: Path) -> str`
  - `transcripts_dir(repo: Path, home: Path | None = None) -> Path`
  - `transcript_files(repo: Path, home: Path | None = None) -> list[Path]`
  - `class ScanResult` — dataclass with `tree: list[str]`, `readme: str | None`, `claude_md: str | None`, `git_log: list[str]`, `transcripts: list[str]`
  - `file_tree(repo: Path, limit: int = 200) -> list[str]`
  - `git_log(repo: Path, limit: int = 40) -> list[str]`
  - `scan(repo: Path, home: Path | None = None) -> ScanResult`
  - `render(result: ScanResult) -> str`
  - `SKIP_DIRS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan.py`:

```python
from pathlib import Path

from throughline import scan


def test_encode_replaces_each_separator_with_one_dash():
    assert scan.encode_repo_path(Path(r"C:\Dev\UMES")) == "C--Dev-UMES"


def test_encode_handles_a_dot_directory():
    encoded = scan.encode_repo_path(Path(r"C:\Users\roman\.claude"))
    assert encoded == "C--Users-roman--claude"


def test_encode_preserves_internal_dashes():
    assert scan.encode_repo_path(Path(r"C:\Dev\Scissors-Farm")) == "C--Dev-Scissors-Farm"


def test_transcripts_dir_is_under_claude_projects(tmp_path):
    result = scan.transcripts_dir(Path(r"C:\Dev\UMES"), home=tmp_path)
    assert result == tmp_path / ".claude" / "projects" / "C--Dev-UMES"


def test_transcript_files_is_empty_when_the_dir_is_absent(tmp_path):
    assert scan.transcript_files(Path(r"C:\Dev\Nope"), home=tmp_path) == []


def test_transcript_files_finds_jsonl(tmp_path):
    target = tmp_path / ".claude" / "projects" / "C--Dev-UMES"
    target.mkdir(parents=True)
    (target / "a.jsonl").write_text("{}", encoding="utf-8")
    (target / "notes.txt").write_text("x", encoding="utf-8")

    found = scan.transcript_files(Path(r"C:\Dev\UMES"), home=tmp_path)
    assert [p.name for p in found] == ["a.jsonl"]


def test_file_tree_lists_relative_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x", encoding="utf-8")
    tree = scan.file_tree(tmp_path)
    assert "src/main.py" in tree


def test_file_tree_skips_noise_directories(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x", encoding="utf-8")
    tree = scan.file_tree(tmp_path)
    assert tree == ["keep.py"]


def test_file_tree_respects_the_limit(tmp_path):
    for index in range(10):
        (tmp_path / f"f{index}.py").write_text("x", encoding="utf-8")
    assert len(scan.file_tree(tmp_path, limit=4)) == 4


def test_scan_reads_the_readme(tmp_path):
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    assert scan.scan(tmp_path, home=tmp_path).readme == "# Hello"


def test_scan_reads_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("rules", encoding="utf-8")
    assert scan.scan(tmp_path, home=tmp_path).claude_md == "rules"


def test_scan_returns_none_for_absent_files(tmp_path):
    result = scan.scan(tmp_path, home=tmp_path)
    assert result.readme is None
    assert result.claude_md is None


def test_git_log_is_empty_outside_a_repo(tmp_path):
    assert scan.git_log(tmp_path) == []


def test_render_includes_each_section(tmp_path):
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    text = scan.render(scan.scan(tmp_path, home=tmp_path))
    assert "## Files" in text
    assert "## README" in text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_scan.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.scan'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/scan.py`:

```python
"""Bounded reconnaissance of an existing repository.

This module gathers raw material only. Every inference from it is made by
the model, in the skill, never here.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".idea",
        ".vs",
        "target",
        "bin",
        "obj",
    }
)

READ_LIMIT = 8000


def encode_repo_path(repo: Path) -> str:
    """Claude Code's per-project transcript directory name.

    Every character that is not alphanumeric becomes a single dash, so
    C:\\Dev\\UMES becomes C--Dev-UMES.
    """
    text = str(Path(repo))
    return "".join(char if char.isalnum() else "-" for char in text)


def transcripts_dir(repo: Path, home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".claude" / "projects" / encode_repo_path(repo)


def transcript_files(repo: Path, home: Path | None = None) -> list[Path]:
    directory = transcripts_dir(repo, home)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl"))


def file_tree(repo: Path, limit: int = 200) -> list[str]:
    root = Path(repo)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(found) >= limit:
            break
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        found.append(relative.as_posix())
    return found


def git_log(repo: Path, limit: int = 40) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "log", f"-{limit}", "--oneline"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:READ_LIMIT]


@dataclass
class ScanResult:
    tree: list[str] = field(default_factory=list)
    readme: str | None = None
    claude_md: str | None = None
    git_log: list[str] = field(default_factory=list)
    transcripts: list[str] = field(default_factory=list)


def scan(repo: Path, home: Path | None = None) -> ScanResult:
    root = Path(repo)
    return ScanResult(
        tree=file_tree(root),
        readme=_read(root / "README.md"),
        claude_md=_read(root / "CLAUDE.md"),
        git_log=git_log(root),
        transcripts=[str(p) for p in transcript_files(root, home)],
    )


def render(result: ScanResult) -> str:
    parts = ["## Files", ""]
    parts.extend(result.tree or ["(none)"])
    parts.extend(["", "## Recent commits", ""])
    parts.extend(result.git_log or ["(none)"])
    parts.extend(["", "## README", "", result.readme or "(none)"])
    parts.extend(["", "## CLAUDE.md", "", result.claude_md or "(none)"])
    parts.extend(["", "## Session transcripts", ""])
    parts.extend(result.transcripts or ["(none)"])
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_scan.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/scan.py tests/test_scan.py
git commit -m "feat: add bounded repo scan and transcript location"
```

---

### Task 8: CLI

**Files:**
- Create: `src/throughline/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: every module from Tasks 1 to 7
- Produces:
  - `main(argv: list[str] | None = None) -> int`
  - `parse_flags(pairs: list[str]) -> dict[str, bool]`
  - Subcommands: `init`, `nodes`, `context`, `answer`, `write`, `status`, `next`, `stale`, `scan`
  - Every subcommand accepts `--repo PATH` (default `.`) and `--json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
import json

import pytest

from throughline import cli, state


def run(capsys, *args):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out


def test_parse_flags_reads_true():
    assert cli.parse_flags(["has_db=true"]) == {"has_db": True}


def test_parse_flags_reads_false():
    assert cli.parse_flags(["has_db=false"]) == {"has_db": False}


def test_parse_flags_rejects_an_unknown_name():
    with pytest.raises(SystemExit):
        cli.parse_flags(["nonsense=true"])


def test_parse_flags_rejects_a_missing_equals():
    with pytest.raises(SystemExit):
        cli.parse_flags(["has_db"])


def test_init_creates_the_pipeline(tmp_path, capsys):
    code, _ = run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    assert code == 0
    assert state.exists(tmp_path)


def test_init_applies_flags(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo", "--flag", "has_db=true")
    assert state.load(tmp_path).flags["has_db"] is True


def test_init_refuses_to_overwrite(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "init", "--repo", str(tmp_path), "--project", "other")
    assert code == 1
    assert "already" in out


def test_nodes_lists_active_ids(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "nodes", "--repo", str(tmp_path), "--json")
    assert code == 0
    payload = json.loads(out)
    assert "problem-statement" in [n["id"] for n in payload]


def test_nodes_omits_inactive_flag_nodes(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "nodes", "--repo", str(tmp_path), "--json")
    assert "er-model" not in [n["id"] for n in json.loads(out)]


def test_context_reports_line_count(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "context", "domain-model", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["line_count"] == 0


def test_answer_persists(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(capsys, "answer", "problem-statement", "q1", "yes", "--repo", str(tmp_path))
    assert code == 0
    assert state.load(tmp_path).nodes["problem-statement"].answers["q1"] == "yes"


def test_write_marks_the_node_current(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "A summary.",
        "--body", "The body.",
        "--note", "wrote the problem statement",
    )
    assert code == 0
    loaded = state.load(tmp_path)
    assert loaded.nodes["problem-statement"].status == state.CURRENT
    assert loaded.nodes["problem-statement"].confirmed is True
    assert loaded.last_note == "wrote the problem statement"


def test_write_stamps_upstream_hashes(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "functional-requirements", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "domain-model", "--repo", str(tmp_path), "--summary", "s", "--body", "b")

    loaded = state.load(tmp_path)
    assert loaded.nodes["domain-model"].upstream_hashes != {}


def test_status_names_the_next_node(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "status", "--repo", str(tmp_path))
    assert code == 0
    assert "Problem statement" in out


def test_next_prints_only_the_node_id(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "next", "--repo", str(tmp_path))
    assert code == 0
    assert out.strip() == "problem-statement"


def test_stale_reports_nothing_for_a_fresh_node(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "stale", "domain-model", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["stale"] is False


def test_stale_detects_an_upstream_change(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "functional-requirements", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "domain-model", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "different")

    _, out = run(capsys, "stale", "domain-model", "--repo", str(tmp_path), "--json")
    payload = json.loads(out)
    assert payload["stale"] is True
    assert payload["changed"] == ["problem-statement"]


def test_scan_runs_on_an_empty_directory(tmp_path, capsys):
    code, out = run(capsys, "scan", "--repo", str(tmp_path))
    assert code == 0
    assert "## Files" in out


def test_commands_fail_cleanly_without_a_pipeline(tmp_path, capsys):
    code, out = run(capsys, "status", "--repo", str(tmp_path))
    assert code == 1
    assert "no pipeline" in out.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_cli.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'throughline.cli'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/cli.py`:

```python
"""Command line entry point.

The CLI owns every deterministic operation. It never calls a model; the
skill markdown does the talking and shells out to these commands.
"""

import argparse
import json
import sys
from pathlib import Path

from . import artifacts, context, hashing, nodes as nodes_module, scan as scan_module
from . import state as state_module
from . import status as status_module


def parse_flags(pairs: list[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"flag must be name=true or name=false, got {pair!r}")
        name, _, value = pair.partition("=")
        name = name.strip()
        if name not in nodes_module.FLAGS:
            known = ", ".join(nodes_module.FLAGS)
            raise SystemExit(f"unknown flag {name!r}, expected one of: {known}")
        result[name] = value.strip().lower() in {"true", "yes", "1"}
    return result


def _emit(payload, as_json: bool, text: str) -> None:
    print(json.dumps(payload, indent=2) if as_json else text.rstrip("\n"))


def _load(repo: Path):
    try:
        return state_module.load(repo)
    except FileNotFoundError as error:
        print(f"no pipeline here - run `throughline init` first ({error})")
        return None


def cmd_init(args) -> int:
    repo = Path(args.repo)
    if state_module.exists(repo):
        print("a pipeline already exists here; refusing to overwrite it")
        return 1
    flags = parse_flags(args.flag or [])
    result = state_module.init(repo, args.project, flags)
    _emit(
        {"project": result.project, "flags": result.flags},
        args.json,
        f"created {state_module.state_path(repo)}",
    )
    return 0


def cmd_nodes(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    active = nodes_module.active_nodes(loaded.flags, tuple(loaded.on_demand.keys()))
    payload = [
        {
            "id": node.id,
            "title": node.title,
            "phase": node.phase,
            "deps": list(node.deps),
            "renders": node.renders,
            "status": state_module.node_state(loaded, node.id).status,
            "confirmed": state_module.node_state(loaded, node.id).confirmed,
        }
        for node in active
    ]
    text = "\n".join(f"{item['status']:<12} {item['id']}" for item in payload)
    _emit(payload, args.json, text)
    return 0


def cmd_context(args) -> int:
    repo = Path(args.repo)
    ctx = context.assemble(repo, args.node)
    payload = {
        "node": args.node,
        "line_count": ctx.line_count,
        "loaded": [d.node_id for d in ctx.documents],
        "missing": ctx.missing,
        "text": context.render(ctx),
    }
    _emit(payload, args.json, context.render(ctx))
    return 0


def cmd_answer(args) -> int:
    repo = Path(args.repo)
    if not state_module.exists(repo):
        print("no pipeline here - run `throughline init` first")
        return 1
    state_module.record_answer(repo, args.node, args.question, args.answer)
    _emit({"saved": True}, args.json, "saved")
    return 0


def cmd_write(args) -> int:
    repo = Path(args.repo)
    loaded = _load(repo)
    if loaded is None:
        return 1
    path = artifacts.write_artifact(
        repo, args.node, args.body, args.summary, slug=args.slug
    )
    entry = state_module.node_state(loaded, args.node)
    entry.status = state_module.CURRENT
    entry.confirmed = True
    entry.updated = state_module.utcnow()
    hashing.stamp(repo, args.node, loaded)
    loaded.last_node = args.node
    if args.note:
        loaded.last_note = args.note
    state_module.save(repo, loaded)
    _emit({"path": str(path)}, args.json, f"wrote {path}")
    return 0


def cmd_status(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    result = status_module.compute(loaded)
    payload = {
        "project": result.project,
        "where_you_left_off": result.where_you_left_off,
        "next": result.next_node,
        "next_title": result.next_title,
        "phases": [
            {"phase": p.phase, "filled": p.filled, "total": p.total}
            for p in result.phases
        ],
    }
    _emit(payload, args.json, status_module.render_text(result))
    return 0


def cmd_next(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    chosen = status_module.next_node(loaded)
    _emit({"next": chosen}, args.json, chosen or "")
    return 0


def cmd_stale(args) -> int:
    repo = Path(args.repo)
    loaded = _load(repo)
    if loaded is None:
        return 1
    changed = hashing.stale_deps(repo, args.node, loaded)
    payload = {"node": args.node, "stale": bool(changed), "changed": changed}
    text = (
        f"{args.node} was written before {', '.join(changed)} changed"
        if changed
        else f"{args.node} is up to date with its inputs"
    )
    _emit(payload, args.json, text)
    return 0


def cmd_scan(args) -> int:
    result = scan_module.scan(Path(args.repo))
    payload = {
        "tree": result.tree,
        "git_log": result.git_log,
        "readme": result.readme,
        "claude_md": result.claude_md,
        "transcripts": result.transcripts,
    }
    _emit(payload, args.json, scan_module.render(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="throughline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--repo", default=".")
        sub.add_argument("--json", action="store_true")
        sub.set_defaults(handler=handler)
        return sub

    init = add("init", cmd_init, "create the pipeline in a repo")
    init.add_argument("--project", required=True)
    init.add_argument("--flag", action="append")

    add("nodes", cmd_nodes, "list active nodes and their status")

    ctx = add("context", cmd_context, "assemble the context for one node")
    ctx.add_argument("node")

    answer = add("answer", cmd_answer, "persist a single interview answer")
    answer.add_argument("node")
    answer.add_argument("question")
    answer.add_argument("answer")

    write = add("write", cmd_write, "write a node's artifact and mark it current")
    write.add_argument("node")
    write.add_argument("--summary", required=True)
    write.add_argument("--body", required=True)
    write.add_argument("--slug")
    write.add_argument("--note")

    add("status", cmd_status, "where you left off and the one next node")
    add("next", cmd_next, "print the next node id")

    stale = add("stale", cmd_stale, "check one node against its inputs")
    stale.add_argument("node")

    add("scan", cmd_scan, "gather raw material from an existing repo")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.handler(args)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_cli.py -v
```

Expected: 19 passed.

- [ ] **Step 5: Run the whole suite**

```bash
python -m pytest -v
```

Expected: all tests pass, no failures.

- [ ] **Step 6: Commit**

```bash
git add src/throughline/cli.py tests/test_cli.py
git commit -m "feat: add the throughline CLI"
```

---

### Task 9: Skill pack

**Files:**
- Create: `skills/throughline/SKILL.md`
- Create: `skills/throughline/questions/problem-statement.md`
- Create: `skills/throughline/questions/functional-requirements.md`
- Create: `skills/throughline/questions/domain-model.md`
- Create: `README.md`
- Test: `tests/test_skill_pack.py`

**Interfaces:**
- Consumes: the CLI subcommand names from Task 8
- Produces: no Python interface. The test asserts the skill pack stays consistent with the code.

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_pack.py`:

```python
from pathlib import Path

import pytest

from throughline import nodes

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "throughline" / "SKILL.md"
QUESTIONS = ROOT / "skills" / "throughline" / "questions"


def test_skill_file_exists():
    assert SKILL.is_file()


def test_skill_has_frontmatter_name_and_description():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "\nname: throughline\n" in text
    assert "\ndescription:" in text


def test_skill_documents_every_cli_command():
    text = SKILL.read_text(encoding="utf-8")
    for command in ("init", "nodes", "context", "answer", "write", "status", "next", "stale", "scan"):
        assert f"throughline {command}" in text, f"{command} is undocumented"


def test_skill_states_the_one_next_action_rule():
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "one next" in text


def test_skill_forbids_broadcasting_staleness():
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "never" in text and "stale" in text


def test_question_banks_name_real_nodes():
    known = {node.id for node in nodes.all_nodes()}
    for path in QUESTIONS.glob("*.md"):
        assert path.stem in known, f"{path.name} does not match any node"


@pytest.mark.parametrize("node_id", ["problem-statement", "functional-requirements", "domain-model"])
def test_core_question_banks_exist(node_id):
    assert (QUESTIONS / f"{node_id}.md").is_file()


def test_question_banks_stay_within_the_size_limit():
    for path in QUESTIONS.glob("*.md"):
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("### Q"))
        assert 1 <= count <= 8, f"{path.name} has {count} questions, limit is 8"


def test_every_question_offers_a_recommendation():
    for path in QUESTIONS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        blocks = text.split("### Q")[1:]
        for block in blocks:
            assert "Recommend:" in block, f"a question in {path.name} has no recommendation"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_skill_pack.py -v
```

Expected: failures, starting with `test_skill_file_exists`.

- [ ] **Step 3: Write `skills/throughline/SKILL.md`**

```markdown
---
name: throughline
description: Use when starting, resuming, or tracking analysis and design work on a repository - runs the artifact pipeline through short interviews and answers "where was I" without reading anything long.
---

# Throughline

An analysis and design pipeline anchored in the repo you are working on.
All state lives in `docs/project/`. All deterministic work is done by the
`throughline` CLI. Your job is the conversation.

## Binding rules

These come from the design spec. Violating one breaks the tool for its user.

1. **Never open with a list of things the user has not done.** Open with
   one next action. Exactly one.
2. **Never hand over a document to review.** Ask one question at a time.
   The artifact accretes from the answers.
3. **Every question carries a recommendation** and a one-line reason.
   "Yeah, that one" must always be a valid answer.
4. **Save every answer immediately** with `throughline answer`. Never
   batch answers to the end of an interview.
5. **Never broadcast staleness.** No counts, no badges, no red. Mention a
   stale input only when the user has already opened that node, in one
   sentence, with a one-word way to dismiss it.
6. **Never load the whole repo.** Use `throughline context <node>` and
   work from what it returns.
7. **Eight questions maximum per node.** If a node needs more, it should
   have been split.

## Commands

Run every command with `--repo <path>` pointing at the target repository,
and `--json` when you need to parse the result.

- `throughline init --project NAME --flag has_db=true` - create the pipeline
- `throughline nodes` - active nodes and their status
- `throughline status` - where the user left off plus the one next node
- `throughline next` - just the next node id
- `throughline context <node>` - the scoped context for a node
- `throughline answer <node> <question-id> <answer>` - persist one answer
- `throughline write <node> --summary S --body B --note N` - write the artifact
- `throughline stale <node>` - check one node against its inputs
- `throughline scan` - raw material from an existing repo

## Starting a project

For a new repo, run `throughline init` after the intake interview sets the
flags. For an existing repo, run `throughline scan` first, draft every node
from what comes back, then walk the user through confirming them - the
interview becomes confirmation, not authoring.

Intake asks about six questions and must establish `has_db`, `has_ui`,
`has_state` and `multi_service`. Finish intake by playing back your
understanding in three or four bullets and correcting it until the user
says it fits. Do not proceed to any node before that playback is accepted.

## Running a node

1. `throughline context <node> --json` and read what comes back.
2. Report in one line what you loaded and how many lines it was.
3. Read the matching file in `questions/` if one exists. Otherwise derive
   at most eight questions from the node's purpose.
4. Ask one question at a time. Offer the options, mark one recommended,
   give a one-line reason.
5. Offer these three escape hatches on every question: you decide, let me
   just write it, stop here.
6. After each answer, run `throughline answer`.
7. When the questions are done, write the artifact with
   `throughline write`, including a one-sentence summary and a `--note`
   describing what the user was thinking about. That note is what
   `status` shows next time.
8. Render the diagram if the node's `renders` value is not `markdown`.

## Resuming

Run `throughline status`. Report the "where you left off" line first, then
the single next node. Do not list anything else.
```

- [ ] **Step 4: Write `skills/throughline/questions/problem-statement.md`**

```markdown
# Problem statement

Goal: one paragraph naming who has the problem, what it costs them, and
what "solved" looks like. No solutions.

### Q1: Who has this problem?
Options: you alone / a client and their users / a team you work with
Recommend: whichever the scan suggested. Reason: the answer decides whose language the rest of the pipeline uses.

### Q2: What does the problem cost them today?
Options: time spent / money lost / errors made / work simply not done
Recommend: time spent. Reason: it is the easiest to check afterwards.

### Q3: How do they cope right now?
Options: a manual process / another tool / they do not
Recommend: a manual process. Reason: naming the workaround is what makes the problem concrete.

### Q4: What does solved look like, in one observable change?
Options: something takes less time / something stops breaking / something becomes possible
Recommend: something takes less time. Reason: it gives you a measurable success criterion.

### Q5: What is explicitly out of scope?
Options: propose a delimitation from the answers above / the user names one
Recommend: propose one. Reason: an unstated boundary is where scope creep starts.
```

- [ ] **Step 5: Write `skills/throughline/questions/functional-requirements.md`**

```markdown
# Functional requirements

Goal: a numbered list of what the system must do, each traceable to the
problem statement. Split into one node per feature area if this would run
past eight questions.

### Q1: Who are the actors?
Options: propose a list from the problem statement / the user names them
Recommend: propose a list. Reason: reacting is cheaper than recalling.

### Q2: What is the single most important thing the system must do?
Options: propose three candidates from the problem statement
Recommend: the one that matches the cost named in the problem statement. Reason: it keeps requirements traceable.

### Q3: What else must it do?
Options: propose a list, ask the user to strike out what does not belong
Recommend: propose the list. Reason: striking out is faster than listing.

### Q4: Which of these is not needed for a first version?
Options: present the list from Q3 for the user to cut
Recommend: cut anything not tied to the problem statement. Reason: YAGNI applied while it is still cheap.

### Q5: What must it never do?
Options: propose constraints / none
Recommend: propose constraints. Reason: negative requirements catch what positive ones miss.

### Q6: How fast, how many, how available?
Options: propose figures from the problem statement / not important yet
Recommend: not important yet, unless the problem statement named a number. Reason: invented figures become fake requirements.
```

- [ ] **Step 6: Write `skills/throughline/questions/domain-model.md`**

```markdown
# Domain model

Goal: the project's vocabulary. This artifact is injected into every later
prompt, so precision here pays off in every future session. Renders as a
mermaid `classDiagram`.

### Q1: Are these the core entities?
Options: present the entities found in the code or requirements
Recommend: the list as found. Reason: the code already contains the vocabulary; confirming is cheaper than inventing.

### Q2: Is anything on that list actually a property of something else?
Options: present each questionable entity individually
Recommend: fold it in unless it has its own lifecycle. Reason: an entity that always dies with its parent is a property.

### Q3: Is anything missing that you talk about but never named in code?
Options: propose candidates from the problem statement / nothing missing
Recommend: propose candidates. Reason: unnamed concepts are where miscommunication lives.

### Q4: What is the relationship between each pair?
Options: propose relationships with cardinality for confirmation
Recommend: the proposed set. Reason: cardinality mistakes are cheap now and expensive later.

### Q5: Which terms have two names in the codebase?
Options: present each conflict with a recommended winner
Recommend: the name used most often in the code. Reason: renaming toward existing usage is the smaller change.
```

- [ ] **Step 7: Write `README.md`**

```markdown
# Throughline

An analysis and design pipeline that lives inside the repository it
describes.

Artifacts go in `docs/project/`. State is a single `pipeline.yaml`;
everything else is hand-editable markdown. Nodes are produced by short
interviews rather than document generation, so the person answering stays
the author.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Use

```bash
throughline init --repo path/to/repo --project my-project --flag has_db=true
throughline status --repo path/to/repo
```

The `skills/throughline/` directory holds the Claude Code skill that runs
the interviews on top of this CLI.

## Test

```bash
python -m pytest
```

Design notes are in `docs/superpowers/specs/`.
```

- [ ] **Step 8: Run the test to verify it passes**

```bash
python -m pytest tests/test_skill_pack.py -v
```

Expected: 11 passed.

- [ ] **Step 9: Run the whole suite**

```bash
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add skills README.md tests/test_skill_pack.py
git commit -m "feat: add the throughline skill pack and question banks"
```

---

## Self-Review

**Spec coverage**

| Spec requirement | Task |
|---|---|
| Visible `docs/project/` folder | 2, 3 |
| `pipeline.yaml` as the only machine-owned file | 2 |
| Global node definitions, per-repo state | 1, 2 |
| Always-active node set | 1 |
| Flag-activated nodes | 1 |
| On-demand nodes with slugs | 1, 3 |
| Cut nodes absent | 1 |
| `deps`, `when`, `renders` declared per node | 1 |
| Answers persist immediately | 2, 8 |
| Escape hatches on every question | 9 |
| Eight-question ceiling | 9 |
| Dependency-scoped context, glossary injected | 5 |
| Context size reported to the user | 5, 8, 9 |
| Per-dependency hashing | 4 |
| Staleness never broadcast | 6, 8, 9 |
| Just-in-time staleness on node open | 8, 9 |
| "Where you left off" line | 2, 6 |
| Exactly one next action | 6, 8, 9 |
| Progress strip, progress only | 6 |
| Unconfirmed nodes ordered ahead | 6 |
| Bootstrap scan of code, git, transcripts | 7 |
| Intake with playback loop | 9 |
| Artifact summary line | 3 |

Milestone 6 (the application) is out of scope for this plan by design, and the spec defers it pending validation.

**Placeholder scan:** no TBDs, no "similar to Task N", no "add error handling". Every code step contains complete code.

**Type consistency checked:**
- `NodeDef` fields are used identically in Tasks 1, 3, 5, 6, 8.
- `NodeState.upstream_hashes` is a `dict[str, str]` in Tasks 2, 4, 8.
- `state.node_state()` is the only accessor used for defaulted node entries in Tasks 4, 6, 8.
- `state.project_dir()` is defined in Task 2 and imported by Task 3.
- `artifacts.write_artifact()` keeps the signature `(repo, node_id, body, summary, slug=None)` in Tasks 3, 4, 5, 8.
- `hashing.stamp()` mutates without saving in Task 4; Task 8 is the only caller and saves afterwards.
- `status.next_node()` is a module-level function and `Status.next_node` is a field; both appear in Tasks 6 and 8 without collision because the CLI calls `status_module.next_node`.
