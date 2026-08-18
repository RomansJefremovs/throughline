# Choosing the Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Throughline hand a repo to either Claude Code or opencode, chosen once per machine, and make sure whichever one it hands to actually has the skill installed.

**Architecture:** One new module (`agents.py`) holds a table of the two agents — their argv shape and any environment they need. `spawn_claude` becomes `spawn_agent`, and `_post_start` resolves an agent before spawning: stored one wins, a lone installed one is adopted silently, two installed and nothing stored returns 409 so the app can ask once. A second new module (`skill.py`) copies the skill pack to `~/.claude/skills/throughline/`, which both agents read.

**Tech Stack:** Python 3.12 stdlib only (`shutil`, `filecmp`, `subprocess`), pytest, vanilla JS in `src/throughline/app/`, PyInstaller via `scripts/build-installer.ps1`.

Spec: [`docs/superpowers/specs/2026-08-18-choose-the-agent-design.md`](../specs/2026-08-18-choose-the-agent-design.md)

**Run tests with `uv run python -m pytest`** in this repo. Plain `python` is not on PATH here.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/throughline/agents.py` | **Create.** The only place that names an agent: table, setting file, argv, environment |
| `src/throughline/skill.py` | **Create.** Where the skill pack lives and how it gets to `~/.claude/skills/` |
| `src/throughline/serve.py` | **Modify.** `spawn_agent`, resolution in `_post_start`, `/api/agent` |
| `src/throughline/cli.py` | **Modify.** `throughline agent`, `throughline skill install` |
| `src/throughline/app/app.js` | **Modify.** One `handOff`, the agent's name in copy, the ask-once picker |
| `src/throughline/app/index.html` | **Modify.** The picker modal; drop "by Claude" from the drafted note |
| `skills/throughline/SKILL.md` | **Modify.** Binding rule 3 names both pickers |
| `scripts/build-installer.ps1` | **Modify.** One `--add-data` line carries the skill pack |
| `tests/test_agents.py` | **Create.** |
| `tests/test_skill_install.py` | **Create.** |
| `tests/test_serve.py` | **Modify.** Resolution table, `/api/agent`, the rename |
| `tests/test_cli.py` | **Modify.** The two new commands |

`agents.py` and `skill.py` are separate because they answer different questions — *who runs it* and *what they read* — and only `serve.py` needs both.

---

### Task 1: The agents module

**Files:**
- Create: `src/throughline/agents.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agents.py`:

```python
import pytest

from throughline import agents


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_nothing_chosen_when_the_file_is_absent(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    assert agents.chosen() is None


def test_choosing_writes_one_word(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    agents.choose("opencode")
    assert (home / "agent").read_text(encoding="utf-8") == "opencode\n"
    assert agents.chosen() == "opencode"


def test_an_unknown_name_is_refused(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        agents.choose("cursor")
    assert agents.chosen() is None


def test_garbage_in_the_file_reads_as_unset(tmp_path, monkeypatch):
    """A one-word file with the wrong word in it is not worth an error.

    The worst it costs is one more pick. Refusing to start would be the
    tool getting in its own way.
    """
    home = _home(tmp_path, monkeypatch)
    home.mkdir(parents=True)
    (home / "agent").write_text("emacs\n", encoding="utf-8")
    assert agents.chosen() is None


def test_installed_reports_in_table_order(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")
    assert agents.installed() == ["claude", "opencode"]


def test_installed_is_empty_when_neither_is_on_path(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(agents.shutil, "which", lambda name: None)
    assert agents.installed() == []


def test_claude_takes_its_prompt_positionally():
    argv, environment = agents.command("claude", "do the thing")
    assert argv == ["claude", "do the thing"]
    assert environment == {}


def test_opencode_takes_a_flag_and_needs_the_question_tool_turned_on():
    """Unset, opencode registers no picker at all.

    Verified against the 1.18.12 binary: the builtin tool list is
    `...ro?[H.question]:[]` where `ro` is OPENCODE_ENABLE_QUESTION_TOOL.
    Without it, binding rule 3 has no tool to bind to and every
    interview degrades to prose.
    """
    argv, environment = agents.command("opencode", "do the thing")
    assert argv == ["opencode", "--prompt", "do the thing"]
    assert environment == {"OPENCODE_ENABLE_QUESTION_TOOL": "1"}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run python -m pytest tests/test_agents.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'throughline.agents'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/agents.py`:

```python
"""Which agent gets handed the work.

Throughline drives a conversation it does not have. The CLI is
deterministic, the artifacts are markdown, and the skill is a set of
rules - none of it cares who is reading them. This module is the only
place that names an agent, so a third one is a table entry rather than
a search through the codebase.

The choice is per machine, not per repo. Which agents are installed is
a fact about the computer, and `pipeline.yaml` is committed - a per-repo
setting would push one person's choice onto a teammate who does not have
that agent at all.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .registry import home

SETTING_FILENAME = "agent"


@dataclass(frozen=True)
class Agent:
    executable: str
    prompt_flag: str | None = None
    environment: dict[str, str] = field(default_factory=dict)

    def argv(self, prompt: str) -> list[str]:
        if self.prompt_flag is None:
            return [self.executable, prompt]
        return [self.executable, self.prompt_flag, prompt]


# Order matters twice: `installed()` reports in it, and a machine with
# exactly one agent gets that one without being asked.
AGENTS: dict[str, Agent] = {
    "claude": Agent("claude"),
    "opencode": Agent(
        "opencode",
        "--prompt",
        # opencode's picker is behind a feature flag. Unset, the tool is
        # not registered at all, and binding rule 3 - every question
        # through the picker, never as prose - cannot be kept.
        {"OPENCODE_ENABLE_QUESTION_TOOL": "1"},
    ),
}


def setting_path() -> Path:
    return home() / SETTING_FILENAME


def installed() -> list[str]:
    return [name for name, agent in AGENTS.items() if shutil.which(agent.executable)]


def chosen() -> str | None:
    """Absent, unreadable and unrecognised are all the same answer."""
    try:
        name = setting_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name if name in AGENTS else None


def choose(name: str) -> str:
    if name not in AGENTS:
        known = ", ".join(AGENTS)
        raise ValueError(f"unknown agent {name!r}, expected one of: {known}")
    path = setting_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{name}\n", encoding="utf-8")
    return name


def command(name: str, prompt: str) -> tuple[list[str], dict[str, str]]:
    """The argv to run and the environment to add to the inherited one."""
    agent = AGENTS[name]
    return agent.argv(prompt), dict(agent.environment)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run python -m pytest tests/test_agents.py -v
```

Expected: every test in the file passes.

- [ ] **Step 5: Mutation-check the environment**

Temporarily delete the `{"OPENCODE_ENABLE_QUESTION_TOOL": "1"}` argument from the `opencode` entry (leaving `Agent("opencode", "--prompt")`) and re-run. `test_opencode_takes_a_flag_and_needs_the_question_tool_turned_on` must fail. Put it back. If it did not fail, the test is decorative and the flag could be dropped in a later refactor without anything noticing.

- [ ] **Step 6: Commit**

```bash
git add src/throughline/agents.py tests/test_agents.py && git commit -m "Add the agent table, and the setting that picks one"
```

---

### Task 2: Spawn whichever agent was resolved

**Files:**
- Modify: `src/throughline/serve.py:417-430` (`spawn_claude`), `src/throughline/serve.py:432-482` (`_post_start`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Add the autouse fixture**

Resolution asks the real `PATH`, and the machine running the tests may have neither agent installed. Without this, twelve existing hand-off tests would start passing or failing depending on what is installed on the developer's laptop.

Add near the top of `tests/test_serve.py`, after the existing imports (add `from throughline import agents` to them):

```python
@pytest.fixture(autouse=True)
def _an_agent_to_hand_to(monkeypatch):
    """Every hand-off test needs an agent, and CI has neither.

    Pinning both here keeps the resolution table the only thing that
    varies; the tests for that table override these deliberately.
    """
    monkeypatch.setattr(agents, "chosen", lambda: "claude")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])
```

- [ ] **Step 2: Write the failing resolution tests**

Append to `tests/test_serve.py`:

```python
def test_a_stored_agent_is_used(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls == ["opencode"]
    assert _json(response)["agent"] == "opencode"


def test_a_stored_agent_that_is_gone_says_where_to_change_it(tmp_path, monkeypatch):
    """'Not found' with nowhere to go is a dead end, not an error."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    error = _json(response)["error"]
    assert "opencode" in error
    assert str(agents.setting_path()) in error
    assert calls == []


def test_the_only_installed_agent_is_used_and_remembered(tmp_path, monkeypatch):
    """One agent on the machine is not a decision worth interrupting for."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: ["opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls == ["opencode"]
    stored = tmp_path / "home" / "agent"
    assert stored.read_text(encoding="utf-8").strip() == "opencode"


def test_both_installed_and_nothing_chosen_asks(tmp_path, monkeypatch):
    """Guessing would open a session under an agent nobody picked."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 409
    assert _json(response)["choose"] == ["claude", "opencode"]
    assert calls == []


def test_no_agent_at_all_names_both(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: [])

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    error = _json(response)["error"].lower()
    assert "claude" in error
    assert "opencode" in error
```

- [ ] **Step 3: Run them to verify they fail**

```bash
uv run python -m pytest tests/test_serve.py -k "stored_agent or only_installed or nothing_chosen_asks or no_agent_at_all" -v
```

Expected: all five fail with `AttributeError: <module 'throughline.serve'> does not have the attribute 'spawn_agent'`.

- [ ] **Step 4: Implement in `serve.py`**

Add `import os` beside the existing `import json`, and add `agents` to the package imports:

```python
from . import agents, gaps, hashing, registry, setup, tasks
```

Replace `spawn_claude` (currently at line 417) with:

```python
def spawn_agent(repo: Path, prompt: str, name: str) -> None:
    """Open an agent session in the repo, already asking for the node.

    A new console rather than a child of the server: the session outlives
    the app, and closing the app must never kill work in progress.
    """
    argv, extra = agents.command(name, prompt)
    creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        argv,
        cwd=str(repo),
        creationflags=creation,
        shell=False,
        env={**os.environ, **extra} if extra else None,
    )


def _resolve_agent() -> tuple[str | None, Response | None]:
    """Which agent to hand to, or the response saying why there isn't one.

    Exactly one of the two is not None. The 409 is the only branch that
    asks the user anything, and it exists because picking a winner would
    open a session in someone's repo under an agent they never chose.
    """
    name = agents.chosen()
    available = agents.installed()
    if name is not None:
        if name not in available:
            return None, _error(
                500,
                f"{name} was not found on PATH - "
                f"change it in {agents.setting_path()}",
            )
        return name, None
    if not available:
        return None, _error(
            500, "neither claude nor opencode was found on PATH"
        )
    if len(available) == 1:
        return agents.choose(available[0]), None
    return None, _json_response({"choose": available}, 409)
```

Then in `_post_start`, replace the trailing block:

```python
    name, failure = _resolve_agent()
    if failure is not None:
        return failure

    try:
        spawn_agent(repo, prompt, name)
    except FileNotFoundError:
        return _error(500, f"{name} was not found on PATH")
    except OSError as err:
        return _error(500, f"could not start {name}: {err}")
    return _json_response({**started, "agent": name})
```

- [ ] **Step 5: Update the twelve existing monkeypatch sites**

`spawn_agent` takes a third argument, so every existing stub needs it:

```bash
sed -i 's/"spawn_claude", lambda r, p:/"spawn_agent", lambda r, p, n:/g' tests/test_serve.py
```

That covers ten of the twelve sites. Fix the other two by hand: `def boom(_repo, _prompt)` at lines 507 and 1117 becomes `def boom(_repo, _prompt, _name)`, and the `monkeypatch.setattr(serve, "spawn_claude", boom)` line below each becomes `"spawn_agent"`.

Verify nothing was missed:

```bash
grep -rn "spawn_claude" src tests
```

Expected: no output.

- [ ] **Step 6: Run the whole suite**

```bash
uv run python -m pytest
```

Expected: all tests pass, including the five new ones.

Note: `test_setup_reports_when_claude_is_missing` still passes — the fixture pins `claude` as chosen and installed, so resolution succeeds and the `boom` stub raises from the spawn, exactly as before.

- [ ] **Step 7: Mutation-check the refusal**

Temporarily replace the last line of `_resolve_agent` with `return available[0], None` and run:

```bash
uv run python -m pytest tests/test_serve.py -k nothing_chosen_asks -v
```

Expected: `test_both_installed_and_nothing_chosen_asks` FAILS. Restore the line. If it passed, the 409 is not actually pinned by anything and the ask-once behaviour could vanish silently.

- [ ] **Step 8: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py && git commit -m "Resolve which agent to hand to before spawning one"
```

---

### Task 3: The `/api/agent` endpoints

**Files:**
- Modify: `src/throughline/serve.py` (new handlers, two lines in `route`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_serve.py`:

```python
def test_the_agent_endpoint_reports_choice_and_availability(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])

    response = serve.route("GET", "/api/agent", {}, b"")
    assert response.status == 200
    assert _json(response) == {
        "chosen": "opencode",
        "installed": ["claude", "opencode"],
    }


def test_choosing_an_agent_stores_it(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route("POST", "/api/agent", {"name": "opencode"}, b"")
    assert response.status == 200
    stored = tmp_path / "home" / "agent"
    assert stored.read_text(encoding="utf-8").strip() == "opencode"


def test_choosing_an_unknown_agent_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route("POST", "/api/agent", {"name": "cursor"}, b"")
    assert response.status == 400
    assert not (tmp_path / "home" / "agent").exists()


def test_choosing_an_agent_refuses_another_origin(tmp_path, monkeypatch):
    """It writes a file, so it is guarded like everything else that does."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route(
        "POST",
        "/api/agent",
        {"name": "opencode"},
        b"",
        {"Host": "127.0.0.1:7373", "Origin": "http://evil.example"},
    )
    assert response.status == 403
    assert not (tmp_path / "home" / "agent").exists()


def test_choosing_an_agent_refuses_a_foreign_host(tmp_path, monkeypatch):
    """DNS rebinding reaches loopback carrying someone else's Host."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route(
        "POST",
        "/api/agent",
        {"name": "opencode"},
        b"",
        {"Host": "attacker.example"},
    )
    assert response.status == 403
    assert not (tmp_path / "home" / "agent").exists()
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run python -m pytest tests/test_serve.py -k "agent_endpoint or choosing_an" -v
```

Expected: the first three fail on `404 no such route`. The cross-origin and foreign-Host tests pass already, because `route()` guards every POST before dispatch. That is the guard doing its job, and both tests are worth keeping as the thing that says so.

- [ ] **Step 3: Implement**

Add beside the other handlers in `serve.py`:

```python
def _agent_payload() -> Response:
    return _json_response(
        {"chosen": agents.chosen(), "installed": agents.installed()}
    )


def _post_agent(query: dict) -> Response:
    try:
        agents.choose((query.get("name") or "").strip())
    except ValueError as err:
        return _error(400, str(err))
    return _agent_payload()
```

Add to `route()`, beside the other GETs and POSTs:

```python
    if method == "GET" and path == "/api/agent":
        return _agent_payload()
```

```python
    if method == "POST" and path == "/api/agent":
        return _post_agent(query)
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_serve.py -k "agent_endpoint or choosing_an" -v
```

Expected: all four pass.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py && git commit -m "Read and set the agent over the API"
```

---

### Task 4: `throughline agent` on the CLI

**Files:**
- Modify: `src/throughline/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`, using the `run(capsys, *args)` helper already at the top of that file:

```python
def test_agent_prints_the_current_choice(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")

    code, out = run(capsys, "agent", "--json")
    assert code == 0
    assert json.loads(out) == {
        "chosen": None,
        "installed": ["claude", "opencode"],
    }


def test_agent_sets_the_choice(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")

    code, out = run(capsys, "agent", "opencode", "--json")
    assert code == 0
    assert json.loads(out)["chosen"] == "opencode"
    assert (tmp_path / "home" / "agent").read_text(encoding="utf-8") == "opencode\n"
```

Change the test file's import line to `from throughline import agents, cli, state`.

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run python -m pytest tests/test_cli.py -k agent -v
```

Expected: both fail — argparse exits with `invalid choice: 'agent'`.

- [ ] **Step 3: Implement**

Add `from . import agents as agents_module` to `cli.py`'s imports, and this handler beside the others:

```python
def cmd_agent(args) -> int:
    if args.name:
        try:
            agents_module.choose(args.name)
        except ValueError as error:
            print(error)
            return 1
    chosen = agents_module.chosen()
    installed = agents_module.installed()
    _emit(
        {"chosen": chosen, "installed": installed},
        args.json,
        f"agent: {chosen or 'not chosen'}\n"
        f"installed: {', '.join(installed) or 'none'}",
    )
    return 0
```

Register it in `build_parser()`, beside `target`:

```python
    agent = add("agent", cmd_agent, "which agent gets handed the work")
    agent.add_argument("name", nargs="?", choices=sorted(agents_module.AGENTS))
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_cli.py -k agent -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/cli.py tests/test_cli.py && git commit -m "Add `throughline agent` so the CLI can pick too"
```

---

### Task 5: Bundle the skill pack and install it

**Files:**
- Create: `src/throughline/skill.py`
- Modify: `src/throughline/cli.py`, `scripts/build-installer.ps1:30`
- Test: `tests/test_skill_install.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_install.py`:

```python
from throughline import skill


def _bundle(tmp_path, monkeypatch):
    """Stand in for the shipped pack so tests do not depend on the repo."""
    source = tmp_path / "bundle"
    (source / "questions").mkdir(parents=True)
    (source / "SKILL.md").write_text("# Throughline\n", encoding="utf-8")
    (source / "questions" / "architecture.md").write_text("q\n", encoding="utf-8")
    monkeypatch.setattr(skill, "bundled", lambda: source)
    return source


def test_the_pack_is_findable_in_a_source_checkout():
    """No monkeypatching: this is the real repo layout, asserted."""
    assert (skill.bundled() / "SKILL.md").is_file()


def test_it_installs_into_an_empty_home(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"

    result = skill.install(home=home)
    assert result["written"] is True
    destination = home / ".claude" / "skills" / "throughline"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "# Throughline\n"
    assert (destination / "questions" / "architecture.md").is_file()


def test_an_identical_copy_is_left_alone(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)

    result = skill.install(home=home)
    assert result["written"] is False
    assert result["differs"] == []


def test_a_changed_copy_is_reported_and_not_touched(tmp_path, monkeypatch):
    """Someone tuned it. Their words are the truth, as with `write`."""
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)
    edited = home / ".claude" / "skills" / "throughline" / "SKILL.md"
    edited.write_text("# Mine\n", encoding="utf-8")

    result = skill.install(home=home)
    assert result["written"] is False
    assert result["differs"] == ["SKILL.md"]
    assert edited.read_text(encoding="utf-8") == "# Mine\n"


def test_force_replaces_a_changed_copy(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)
    edited = home / ".claude" / "skills" / "throughline" / "SKILL.md"
    edited.write_text("# Mine\n", encoding="utf-8")

    result = skill.install(home=home, force=True)
    assert result["written"] is True
    assert edited.read_text(encoding="utf-8") == "# Throughline\n"


def test_present_is_false_until_it_is_installed(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    assert skill.present(home) is False
    skill.install(home=home)
    assert skill.present(home) is True
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run python -m pytest tests/test_skill_install.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'throughline.skill'`.

- [ ] **Step 3: Write the implementation**

Create `src/throughline/skill.py`:

```python
"""Putting the skill where an agent will find it.

Both agents read `~/.claude/skills`. opencode was checked directly rather
than taken from its documentation: `opencode debug skill` resolves every
user skill to that directory, so one destination serves both and there
is no second copy to keep in step.

Without this the app's hand-off opens a session and says "use the
throughline skill" to an agent that has never heard of it.
"""

import filecmp
import shutil
from pathlib import Path

SKILL_NAME = "throughline"


def bundled() -> Path:
    """Where the pack is, frozen or from source.

    The frozen build carries it next to the package exactly as it carries
    the app assets. A source checkout has it at the repo root, two levels
    above this file.
    """
    packaged = Path(__file__).parent / "skill"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME


def destination(home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".claude" / "skills" / SKILL_NAME


def present(home: Path | None = None) -> bool:
    return (destination(home) / "SKILL.md").is_file()


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def differs(home: Path | None = None) -> list[str]:
    """Every relative path that is missing, extra, or not byte-identical."""
    source, target = bundled(), destination(home)
    changed: set[str] = set()
    for path in _files(source):
        relative = path.relative_to(source)
        other = target / relative
        if not other.is_file() or not filecmp.cmp(path, other, shallow=False):
            changed.add(relative.as_posix())
    for path in _files(target):
        relative = path.relative_to(target)
        if not (source / relative).is_file():
            changed.add(relative.as_posix())
    return sorted(changed)


def install(home: Path | None = None, force: bool = False) -> dict:
    """Copy the pack in, unless someone has edited the copy that is there.

    A tuned skill is somebody's work, and replacing it silently is the
    same failure as `write` overwriting an edited artifact. Differences
    are reported and `force` is the user's decision, not ours.
    """
    target = destination(home)
    if not present(home):
        shutil.copytree(bundled(), target, dirs_exist_ok=True)
        return {"written": True, "path": str(target), "differs": []}

    changed = differs(home)
    if changed and not force:
        return {"written": False, "path": str(target), "differs": changed}
    if not changed:
        return {"written": False, "path": str(target), "differs": []}

    shutil.copytree(bundled(), target, dirs_exist_ok=True)
    return {"written": True, "path": str(target), "differs": changed}
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_skill_install.py -v
```

Expected: every test passes, including `test_the_pack_is_findable_in_a_source_checkout`, which uses the real repo layout.

- [ ] **Step 5: Add the CLI command**

Add `from . import skill as skill_module` to `cli.py`, then:

```python
def cmd_skill(args) -> int:
    result = skill_module.install(force=args.force)
    if result["written"]:
        text = f"installed the skill to {result['path']}"
    elif result["differs"]:
        text = (
            f"{result['path']} differs from the bundled skill and was left "
            f"alone: {', '.join(result['differs'])}\n"
            "run `throughline skill install --force` to replace it"
        )
    else:
        text = f"already installed at {result['path']}"
    _emit(result, args.json, text)
    return 0
```

Register it in `build_parser()`:

```python
    skill_cmd = add("skill", cmd_skill, "install the skill where agents look")
    skill_cmd.add_argument("action", choices=["install"])
    skill_cmd.add_argument("--force", action="store_true")
```

- [ ] **Step 6: Carry the pack into the frozen build**

In `scripts/build-installer.ps1`, add one line directly below the existing `--add-data` at line 30:

```powershell
    --add-data "$(Join-Path $root 'skills\throughline');throughline/skill" `
```

- [ ] **Step 7: Verify the command runs against the real repo**

```bash
uv run throughline skill install --json
```

Expected: JSON with `"written": true` and a path ending in `.claude\skills\throughline`. Run it a second time and expect `"written": false` with `"differs": []`.

- [ ] **Step 8: Commit**

```bash
git add src/throughline/skill.py src/throughline/cli.py tests/test_skill_install.py scripts/build-installer.ps1 && git commit -m "Install the skill where both agents look for it"
```

---

### Task 6: The hand-off installs the skill when it is missing

**Files:**
- Modify: `src/throughline/serve.py` (`_post_start`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Extend the autouse fixture**

The fixture from Task 2 must also keep the tests off the real home directory. Add to `_an_agent_to_hand_to`, and add `from throughline import skill` to the imports:

```python
    monkeypatch.setattr(skill, "present", lambda home=None: True)
```

- [ ] **Step 2: Write the failing tests**

```python
def test_a_hand_off_installs_the_skill_when_it_is_missing(tmp_path, monkeypatch):
    """Handing a repo to an agent that has never heard of the skill is
    the same as not handing it over at all."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    monkeypatch.setattr(skill, "present", lambda home=None: False)
    installs = []
    monkeypatch.setattr(
        skill, "install", lambda **kw: installs.append(kw) or {"written": True}
    )

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert _json(response)["skill_installed"] is True
    assert len(installs) == 1


def test_a_hand_off_leaves_an_installed_skill_alone(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    installs = []
    monkeypatch.setattr(
        skill, "install", lambda **kw: installs.append(kw) or {"written": True}
    )

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert _json(response)["skill_installed"] is False
    assert installs == []
```

- [ ] **Step 3: Run them to verify they fail**

```bash
uv run python -m pytest tests/test_serve.py -k "hand_off_installs or hand_off_leaves" -v
```

Expected: both fail with `KeyError: 'skill_installed'`.

- [ ] **Step 4: Implement**

Add `skill` to the package imports in `serve.py`:

```python
from . import agents, gaps, hashing, registry, setup, skill, tasks
```

In `_post_start`, between resolution and the spawn:

```python
    # An agent that cannot find the skill will improvise, which is worse
    # than refusing. Installing it here costs one stat call per hand-off.
    fresh = False
    if not skill.present():
        fresh = bool(skill.install().get("written"))
```

and change the success response to:

```python
    return _json_response({**started, "agent": name, "skill_installed": fresh})
```

- [ ] **Step 5: Run the whole suite**

```bash
uv run python -m pytest
```

Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py && git commit -m "Install the skill on the way to handing a repo over"
```

---

### Task 7: The app names the agent, and asks once

**Files:**
- Modify: `src/throughline/app/index.html:84`, `src/throughline/app/index.html:206` (after the `#conflict` modal)
- Modify: `src/throughline/app/app.js:309,320,420,787-788,883-925,964-982`

No CSS is needed — the picker reuses `.scrim`, `.modal` and `.row` from the conflict dialog.

- [ ] **Step 1: Add the picker markup**

In `index.html`, immediately after the `#conflict` block:

```html
<div id="pick-agent" class="scrim" hidden>
  <div class="modal">
    <h3>Which agent should do the work?</h3>
    <p>Both are installed. This is remembered, so you are only asked once.</p>
    <div class="row">
      <button id="pick-claude" class="solid">Claude Code</button>
      <button id="pick-opencode" class="hollow">opencode</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Stop the drafted note naming an agent**

The note describes the artifact's state, not its author, and the agent that drafted it may not be the one selected now. Change line 84 of `index.html`:

```html
      <div id="drafted-note" class="note tint" hidden>Drafted &mdash; not yet read.</div>
```

- [ ] **Step 3: Add the agent name and the picker to `app.js`**

Near the top, beside the other module-level state:

```js
/* Which agent the hand-off opens. The server decides; this is only what
 * the buttons are allowed to say. */
const AGENT_LABELS = { claude: "Claude", opencode: "opencode" };
let agent = "claude";
const agentLabel = () => AGENT_LABELS[agent] || agent;
```

Add beside the other hand-off code:

```js
/* The server refuses to guess when both agents are installed. The choice
 * is made here, once, and storing it is what stops this appearing again. */
function pickAgent() {
  return new Promise((resolve) => {
    const dialog = el("pick-agent");
    dialog.hidden = false;
    const pick = async (name) => {
      dialog.hidden = true;
      await fetch(`/api/agent?name=${name}`, { method: "POST" });
      agent = name;
      resolve(name);
    };
    el("pick-claude").onclick = () => pick("claude");
    el("pick-opencode").onclick = () => pick("opencode");
  });
}
```

- [ ] **Step 4: Fold the two hand-offs into one**

`startNode` and `startSetup` are byte-for-byte identical apart from the query they build. Replace both (lines 883-925) with:

```js
/* One hand-off, two callers. The 409 retry lives here rather than in
 * both, because a dialog that only appears in one of them is the kind of
 * thing nobody notices until it matters.
 *
 * A new console that outlives the app, and a button that says what
 * happened for long enough to read. */
async function handOff(button, query) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = `Opening ${agentLabel()}…`;

  const send = () => fetch(`/api/start?${query}`, { method: "POST" });
  let response = await send();
  if (response.status === 409) {
    await pickAgent();
    button.textContent = `Opening ${agentLabel()}…`;
    response = await send();
  }

  if (response.ok) {
    button.textContent = `Opened in ${agentLabel()}`;
  } else {
    const problem = await response.json().catch(() => ({}));
    button.textContent = problem.error || `Could not open ${agentLabel()}`;
  }
  setTimeout(() => {
    button.disabled = false;
    button.textContent = label;
  }, 4000);
}

async function startNode(nodeId, button, slug = null) {
  if (!nodeId) return;
  const query = new URLSearchParams({ repo: project.path, node: nodeId });
  if (slug) query.set("slug", slug);
  await handOff(button, query);
}

async function startSetup(button) {
  await handOff(
    button,
    new URLSearchParams({ repo: project.path, setup: "1" })
  );
}
```

- [ ] **Step 5: Replace the remaining hardcoded names**

Three sites in `drawFront` and `showArtifact`:

- line 309: `sub.textContent = \`→ opens ${agentLabel()} in ${project.name}/\`;`
- line 320: the same replacement
- line 420: `el("doc-start").textContent = mid ? \`Continue — hands to ${agentLabel()}\` : \`Start — hands to ${agentLabel()}\`;`

And the comment at 787-788, which currently says the work "is still Claude's" — change to "is still the agent's".

Verify none are left:

```bash
grep -n "Claude" src/throughline/app/app.js src/throughline/app/index.html
```

Expected: only `AGENT_LABELS` and the `pick-claude` button label.

- [ ] **Step 6: Load the choice at boot**

In `start()`, after the `projects` fetch:

```js
    const picked = await api("/api/agent");
    if (picked && picked.chosen) agent = picked.chosen;
```

- [ ] **Step 7: Verify in the browser**

Start the dev server (`preview_start` with the `throughline` config in `.claude/launch.json`) and check:

1. The front door's sub-line names the stored agent.
2. With the setting file deleted and both agents on PATH, pressing a hand-off button shows the picker rather than opening anything.
3. Picking one closes the dialog, opens that agent, and a second hand-off does not ask again.
4. `~/.throughline/agent` contains the picked name.

Take a screenshot of the picker for the commit message discussion.

- [ ] **Step 8: Commit**

```bash
git add src/throughline/app/app.js src/throughline/app/index.html && git commit -m "Name the chosen agent in the window, and ask for it once"
```

---

### Task 8: Binding rule 3 names both pickers

**Files:**
- Modify: `skills/throughline/SKILL.md:20-23`

- [ ] **Step 1: Rewrite the rule**

Replace binding rule 3:

```markdown
3. **Every question goes through the interactive picker.** Use
   `AskUserQuestion` under Claude Code, or the `question` tool under
   opencode - never ask by writing options as prose. The user picks;
   they do not compose. See "Asking a question" below.
```

- [ ] **Step 2: Note the one shape difference**

In the "Asking a question" section, after the `2 to 4 options` bullet:

```markdown
- **Keep `header` to 12 characters.** opencode allows 30 and Claude Code
  allows 12, so writing to the shorter limit means a question works under
  either without being rewritten.
```

- [ ] **Step 3: Check the skill-pack test still passes**

```bash
uv run python -m pytest tests/test_skill_pack.py -v
```

Expected: passes. If it asserts on rule wording, update the assertion to match — the rule changed on purpose.

- [ ] **Step 4: Commit**

```bash
git add skills/throughline/SKILL.md && git commit -m "Let binding rule 3 name opencode's picker too"
```

---

### Task 9: Full verification pass

**Files:** none — this task only reads and reports.

- [ ] **Step 1: Whole suite**

```bash
uv run python -m pytest
```

Expected: all tests pass. Record the count.

- [ ] **Step 2: Prove the skill actually arrives**

```bash
uv run throughline skill install --json
```

Then confirm both agents can see it:

```bash
timeout 90 opencode debug skill 2>&1 | grep -c throughline
```

Expected: at least 1. This is the check that the whole "gap this also closes" section was written for — if it returns 0, the destination is wrong and nothing else in this plan matters.

- [ ] **Step 3: Hand a real repo to opencode**

Set the agent to `opencode`, open the app, and press a hand-off button on a scratch repo. Confirm an opencode window opens in that repo with the prompt already in it, and that it can find the throughline skill when asked.

- [ ] **Step 4: Confirm the picker is live under opencode**

Inside that session, confirm the agent has a `question` tool available. If it does not, `OPENCODE_ENABLE_QUESTION_TOOL` is not reaching the process and Task 2's environment overlay is wrong — that is the single most likely thing in this plan to be silently broken, because nothing in the test suite can observe it.

- [ ] **Step 5: Report**

State plainly: test count, whether the skill is visible to both agents, whether the opencode hand-off opened, and whether the picker was live. Say which of these were observed rather than inferred.
