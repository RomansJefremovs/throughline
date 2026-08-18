# Task-Only Follow-Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a task-only project a front door that always names something to do — set the repo up, or start a task — instead of three screens with no action on any of them.

**Architecture:** The front door needs one fact it cannot currently see, so `/api/project` reports whether a setup document exists. Setup is handed to Claude through the endpoint that already hands repos over, gated by a flag carrying no caller-supplied text. Starting a task is the app's own work, because it is one line off a ticket rather than an interview — it reuses the same `tasks.create` call that promoting a gap already uses. Two documents stating the opposite position change with it.

**Tech Stack:** Python 3.12 stdlib, pytest, vanilla ES2020 in `app.js`, plain CSS.

**Spec:** `docs/superpowers/specs/2026-08-18-task-only-follow-through-design.md`

**Baseline:** `uv run pytest` is **339 passed**. Bare `python` is NOT on PATH — always `uv run`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/throughline/serve.py` | Modify. `has_setup` in the project payload; a `setup` branch in `_post_start`; new `_post_task` |
| `tests/test_serve.py` | Modify. Behavioural tests for all three |
| `src/throughline/app/index.html` | Modify. Two front-door buttons, a Setup action, the `#starting` screen |
| `src/throughline/app/app.js` | Modify. Front-door states, `startSetup`, the start-a-task screen |
| `skills/throughline/SKILL.md` | Modify. Reverse the stated timing of setup |

No new modules, and no new CSS — the `.field` / `.lbl` / `.note.edge` / `.row` rules from the add-a-project screen already cover the new form. Every rule already lives in `tasks`, `setup` and `state`.

---

## Task 1: Report whether setup exists

**Files:**
- Modify: `src/throughline/serve.py:195` (`_get_project`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_the_project_says_whether_setup_has_been_written(tmp_path, monkeypatch):
    """The front door picks between two actions on this one fact.

    A property of the repo, like task_only - never a count of what is
    owed. It says a document exists; it never says one is missing.
    """
    from throughline import setup as setup_module

    repo = _project(tmp_path, monkeypatch)
    first = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert first["has_setup"] is False

    setup_module.write(repo, "A Vue client app.", "What this is.")
    second = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert second["has_setup"] is True


def test_knowing_about_setup_adds_no_count_of_outstanding_work(tmp_path, monkeypatch):
    """has_setup must not become a back door for rule 9."""
    repo = _project(tmp_path, monkeypatch)
    body = (
        serve.route("GET", "/api/project", {"repo": str(repo)}, b"")
        .body.decode("utf-8")
        .lower()
    )
    assert "remaining" not in body
    assert "outstanding" not in body
    assert "todo" not in body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "whether_setup_has_been_written or adds_no_count_of_outstanding" -v`

Expected: the first fails with `KeyError: 'has_setup'`. The second passes already — it is a standing guard, not a new behaviour. Confirm you saw the first fail for that reason before implementing.

- [ ] **Step 3: Add the field**

In `_get_project`, after the `target_side` line:

```python
    payload["target_side"] = loaded.target_side
    # The front door has to choose between naming setup and naming a task,
    # so it needs to know which of them is missing. A fact about the repo,
    # like task_only above it - it says a document exists, and never that
    # one is owed.
    payload["has_setup"] = setup.setup_path(repo).is_file()
    payload["nodes"] = [] if loaded.task_only else _nodes_payload(repo)
```

`setup` is already imported at the top of the module.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_serve.py -k "whether_setup_has_been_written or adds_no_count_of_outstanding" -v`
Expected: 2 passed

Run: `uv run pytest`
Expected: **341 passed**

- [ ] **Step 5: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py
```

Then commit with a short imperative subject and a prose body explaining why, ending with the `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer. Read `git log -3` for the register.

---

## Task 2: Hand a repo to Claude for setup

**Files:**
- Modify: `src/throughline/serve.py:404` (`_post_start`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_repo_can_be_handed_over_for_setup(tmp_path, monkeypatch):
    """Setup is a hand-off like any other, so it lives here.

    Unlike a node id, nothing the caller sent reaches this prompt - there
    is no id to check against the graph because there is no id.
    """
    repo = _project(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: calls.append((r, p)))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls[0][0] == repo.resolve()
    assert "set this repo up" in calls[0][1].lower()


def test_asking_for_a_node_and_setup_at_once_is_refused(tmp_path, monkeypatch):
    """Two different hand-offs, and guessing between them would be worse."""
    repo = _project(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: calls.append(p))
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "setup": "1", "node": "problem-statement"},
        b"",
    )
    assert response.status == 400
    assert calls == []


def test_setup_still_refuses_an_untracked_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(stranger), "setup": "1"}, b""
    )
    assert response.status == 403


def test_setup_reports_when_claude_is_missing(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)

    def boom(_repo, _prompt):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(serve, "spawn_claude", boom)
    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    assert "claude" in _json(response)["error"].lower()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "handed_over_for_setup or node_and_setup_at_once or setup_still_refuses or setup_reports_when_claude" -v`

Expected: the first and second fail because `setup` is ignored today — an empty node id falls through to `get_node("")` and answers 400 "no such node". The third and fourth may pass for the wrong reason, since `_tracked_repo` and the spawn guard already run. Check each failure individually and say which failed for which reason.

- [ ] **Step 3: Restructure `_post_start` around a single spawn**

Replace the whole body of `_post_start`:

```python
def _post_start(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node_id = query.get("node") or ""
    slug = query.get("slug")
    wants_setup = query.get("setup")

    # Two different hand-offs, and one request can only be one of them.
    # Picking a winner would let a caller's typo quietly open the wrong
    # session in someone's repo.
    if wants_setup and node_id:
        return _error(400, "ask for a node or for setup, not both")

    if wants_setup:
        # Nothing the caller sent reaches this prompt. Node ids are checked
        # against the graph because they land in a process argument; here
        # there is no id to check.
        prompt = "Use the throughline skill and set this repo up."
        started = {"setup": True, "started": True}
    elif slug:
        # Node ids and slugs are checked against the graph and the
        # filesystem rather than sanitised. Both reach a process argument,
        # and an allow-list is the only check that cannot be talked around.
        if not tasks.task_path(repo, slug).is_file():
            return _error(404, "no such task")
        try:
            node = nodes_module.get_task_node(node_id)
        except KeyError:
            return _error(400, "no such node")
        prompt = (
            f"Use the throughline skill and work the {node.id} node "
            f"of task {slug}."
        )
        started = {"node": node.id, "started": True}
    else:
        try:
            node = nodes_module.get_node(node_id)
        except KeyError:
            return _error(400, "no such node")
        prompt = f"Use the throughline skill and work the {node.id} node."
        started = {"node": node.id, "started": True}

    try:
        spawn_claude(repo, prompt)
    except FileNotFoundError:
        return _error(500, "claude was not found on PATH")
    except OSError as err:
        return _error(500, f"could not start claude: {err}")
    return _json_response(started)
```

This restructures a function that already has seven tests over it. Those tests are the net: if the node or task paths changed behaviour, they fail.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_serve.py -k "start" -v`
Expected: every pre-existing start test still passes, plus the four new ones.

Run: `uv run pytest`
Expected: **345 passed**

- [ ] **Step 5: Mutation-check the refusal**

Temporarily delete the `if wants_setup and node_id:` guard and re-run
`test_asking_for_a_node_and_setup_at_once_is_refused`. Confirm it fails — a
request carrying both must not silently pick one. Restore, re-run clean, and
report what you saw.

- [ ] **Step 6: Commit**

`src/throughline/serve.py` and `tests/test_serve.py` only. Same message style and trailer as Task 1.

---

## Task 3: Start a task from a ticket

**Files:**
- Modify: `src/throughline/serve.py`
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_task_can_be_started_from_a_ticket(tmp_path, monkeypatch):
    """The app's own work, unlike setup.

    A task title is one line the user is already reading off a ticket, not
    an interview - so this mirrors the promote path rather than opening a
    terminal to capture a string.
    """
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/task",
        {"repo": str(repo), "title": "Fix VAT on credit notes"},
        b"",
    )
    assert response.status == 200

    slug = _json(response)["slug"]
    made = [t for t in tasks_module.all_tasks(repo) if t.slug == slug]
    assert len(made) == 1
    assert made[0].title == "Fix VAT on credit notes"
    assert made[0].origin == "ticket"


def test_a_started_task_can_carry_its_ticket_reference(tmp_path, monkeypatch):
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/task",
        {"repo": str(repo), "title": "Fix VAT", "reference": "ERP-4821"},
        b"",
    )
    slug = _json(response)["slug"]
    made = [t for t in tasks_module.all_tasks(repo) if t.slug == slug]
    assert made[0].reference == "ERP-4821"


def test_a_task_with_no_title_is_refused(tmp_path, monkeypatch):
    """Whitespace is not a title, and nothing is written for one."""
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    for attempt in ("", "   "):
        response = serve.route(
            "POST", "/api/task", {"repo": str(repo), "title": attempt}, b""
        )
        assert response.status == 400
    assert tasks_module.all_tasks(repo) == []


def test_starting_a_task_refuses_an_untracked_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    state.init(stranger, "Stranger", {})
    response = serve.route(
        "POST", "/api/task", {"repo": str(stranger), "title": "Nope"}, b""
    )
    assert response.status == 403


def test_a_started_task_is_immediately_the_next_thing(tmp_path, monkeypatch):
    """The point of creating it here: the front door has to move on.

    Without this the app would create a task and still show nothing to
    do, which is the dead end this whole change exists to close.
    """
    repo = _project(tmp_path, monkeypatch)
    serve.route("POST", "/api/task", {"repo": str(repo), "title": "Fix VAT"}, b"")
    payload = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert payload["task"]
    assert payload["next"] == "understand"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "started_from_a_ticket or ticket_reference or no_title_is_refused or starting_a_task_refuses or immediately_the_next_thing" -v`
Expected: all five fail — the route does not exist, so everything answers 404 "no such route".

- [ ] **Step 3: Add the endpoint**

In `src/throughline/serve.py`, below `_post_promote`:

```python
def _post_task(query: dict) -> Response:
    """Start a task from a ticket.

    The same tasks.create that promoting a gap already calls, with the
    other origin. Creating a task is not an interview - it is one line the
    user is reading off a ticket - so the app does it, and hands the work
    that follows to Claude.
    """
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    title = (query.get("title") or "").strip()
    if not title:
        return _error(400, "title is required")
    slug = tasks.create(
        repo,
        title,
        origin="ticket",
        reference=(query.get("reference") or "").strip(),
    )
    return _json_response({"slug": slug, "title": title})
```

- [ ] **Step 4: Route it**

In `route`, beside the other POST routes:

```python
    if method == "POST" and path == "/api/task":
        return _post_task(query)
```

- [ ] **Step 5: Verify**

Run: `uv run pytest`
Expected: **350 passed**

- [ ] **Step 6: Commit**

`src/throughline/serve.py` and `tests/test_serve.py` only. Same style and trailer.

---

## Task 4: The markup

**Files:**
- Modify: `src/throughline/app/index.html`

- [ ] **Step 1: Two more front-door actions**

Replace the `#front` section:

```html
    <section id="front" class="screen">
      <p class="kicker" id="front-project"></p>
      <p class="reminder" id="front-reminder"></p>
      <button id="front-action" class="hero"></button>
      <button id="front-add" class="hero" hidden>Add a project &rarr;</button>
      <button id="front-setup" class="hero" hidden>Set this repo up &rarr;</button>
      <button id="front-start" class="hero" hidden>Start a task &rarr;</button>
      <p class="sub" id="front-sub"></p>
    </section>
```

Only ever one of the four is visible; `drawFront` in Task 5 owns that.

- [ ] **Step 2: An action on the Setup screen**

Replace the `#setup` section:

```html
    <section id="setup" class="screen prose" hidden>
      <p class="kicker">Setup &mdash; task work only</p>
      <h2 id="setup-title"></h2>
      <div id="setup-body"></div>
      <button id="setup-action" class="solid" hidden>Set this repo up &rarr;</button>
    </section>
```

The front door stops offering setup the moment it exists, so without this there is no way back to it.

- [ ] **Step 3: The start-a-task screen**

Insert after the `#adding` section's closing `</section>` and before `<section id="failure"`:

```html
    <section id="starting" class="screen prose" hidden>
      <p class="kicker">Start a task</p>
      <h2 id="start-project"></h2>

      <div class="field">
        <label class="lbl" for="task-title">Title</label>
        <input id="task-title" type="text" spellcheck="false"
               placeholder="Fix VAT on credit notes">
      </div>

      <div class="field">
        <label class="lbl" for="task-reference">Reference</label>
        <input id="task-reference" type="text" spellcheck="false"
               placeholder="ERP-4821, optional">
      </div>

      <div id="task-error" class="note edge" hidden></div>

      <div class="row">
        <button id="task-submit" class="solid">Start task</button>
        <button id="task-cancel" class="hollow">Cancel</button>
      </div>
    </section>
```

No new CSS. `.field`, `.lbl`, `.note.edge` and `.row` all exist already, and both rows here are direct children of `#starting`, so they align the way `#adding`'s folder row does.

- [ ] **Step 4: Check it renders**

Run: `uv run throughline serve --port 7380`

In the browser console:

```js
document.getElementById('starting').hidden = false;
```

Expected: two labelled fields whose inputs line up with each other, the error box invisible, and the two buttons on one row. Stop the server afterwards.

- [ ] **Step 5: Commit**

`src/throughline/app/index.html` only.

---

## Task 5: Wire the front door and the task screen

**Files:**
- Modify: `src/throughline/app/app.js`

- [ ] **Step 1: Register the screen**

Replace the `SCREENS` line:

```js
const SCREENS = ["front", "map", "setup", "reading", "editing", "tasks", "adding", "starting", "failure"];
```

- [ ] **Step 2: Teach the front door its three states**

Replace `drawFront` entirely:

```js
function drawFront() {
  el("front-project").textContent = project.project || project.name;
  el("front-reminder").textContent = project.note || "";
  el("front-add").hidden = true;
  el("front-setup").hidden = true;
  el("front-start").hidden = true;

  const action = el("front-action");
  const sub = el("front-sub");

  if (project.next) {
    const verb = project.task ? "Continue" : "Next";
    action.hidden = false;
    action.textContent = `${verb}: ${project.next_title}`;
    sub.textContent = `→ opens Claude in ${project.name}/`;
    return;
  }

  action.hidden = true;

  /* A task-only repo has no nodes, so `next` stays null until a task
   * exists - and nothing could create the first one. That left the one
   * screen which must always name something to do naming nothing. */
  if (project.task_only && !project.has_setup) {
    el("front-setup").hidden = false;
    sub.textContent = `→ opens Claude in ${project.name}/`;
  } else if (project.task_only) {
    el("front-start").hidden = false;
    sub.textContent = "A task is four short nodes, start to verified.";
  } else {
    sub.textContent = "Nothing waiting — every document is written.";
  }
}
```

- [ ] **Step 3: The setup hand-off**

Add below `startNode`:

```js
/* Setup is handed over exactly as a node is - a new console that outlives
 * the app, and a button that says what happened for long enough to read. */
async function startSetup(button) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Opening Claude…";

  const query = new URLSearchParams({ repo: project.path, setup: "1" });
  const response = await fetch(`/api/start?${query}`, { method: "POST" });

  if (response.ok) {
    button.textContent = "Opened in Claude";
  } else {
    const problem = await response.json().catch(() => ({}));
    button.textContent = problem.error || "Could not open Claude";
  }
  setTimeout(() => {
    button.disabled = false;
    button.textContent = label;
  }, 4000);
}

el("front-setup").onclick = (event) => startSetup(event.currentTarget);
el("setup-action").onclick = (event) => startSetup(event.currentTarget);
```

- [ ] **Step 4: The start-a-task screen**

Add just above the `/* Tasks */` banner:

```js
/* Starting a task -------------------------------------------------- */

function taskError(text) {
  const box = el("task-error");
  box.textContent = text;
  box.hidden = !text;
}

function openStart() {
  el("start-project").textContent = project.project || project.name;
  el("task-title").value = "";
  el("task-reference").value = "";
  taskError("");
  goTo("starting");
  el("task-title").focus();
}

el("task-cancel").onclick = async () => {
  if (history.length) await goBack();
  else show("front");
};

/* Created here rather than handed to Claude: a title is one line off a
 * ticket, not an interview. The work that follows is still Claude's - the
 * front door names it the moment this returns. */
async function submitTask() {
  const title = el("task-title").value.trim();
  if (!title) return taskError("Give the task a title.");

  const button = el("task-submit");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Starting…";
  taskError("");
  let started = false;

  try {
    const query = new URLSearchParams({ repo: project.path, title });
    const reference = el("task-reference").value.trim();
    if (reference) query.set("reference", reference);

    const response = await fetch(`/api/task?${query}`, { method: "POST" });
    if (!response.ok) return taskError(await said(response));
    started = true;
    await openProject(project.path);
  } catch {
    // Which half failed decides what is true. Saying the task was not
    // started when it was would send someone off to start it twice.
    taskError(
      started
        ? "The task was started, but the screen could not refresh. Open it from Tasks."
        : "Throughline did not respond. The task was not started."
    );
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

el("task-submit").onclick = submitTask;
el("front-start").onclick = () => openStart();
```

`said` and `goBack` already exist, from the add-a-project screen.

- [ ] **Step 5: Show the Setup action only when there is no document**

Replace `drawSetup`:

```js
async function drawSetup() {
  el("setup-title").textContent = project.project || project.name;
  const data = await api(`/api/setup?repo=${encodeURIComponent(project.path)}`);
  el("setup-body").innerHTML = data
    ? render(data.text)
    : '<p class="muted">No setup written yet.</p>';
  el("setup-action").hidden = !!data;
}
```

The old copy ended "ask Claude to set this repo up when it earns it". The screen now offers the action instead of naming someone else to ask, and "when it earns it" is the sentence Task 6 reverses.

- [ ] **Step 6: Verify by hand**

Run: `node --check src/throughline/app/app.js` — must pass.

Then `uv run throughline serve --port 7380` and make a task-only repo:

```bash
mkdir -p build/tasktest
```

```bash
cd build/tasktest && uv run --project C:/Dev/throughline throughline init --project "Task Test" --task-only && uv run --project C:/Dev/throughline throughline add
```

In the app, switch to **Task Test**. Expected in order:

1. Front door reads **Set this repo up →**, not a blank screen.
2. The Setup screen offers the same action.
3. Write a setup document from the command line so the state moves on:

```bash
uv run throughline setup --repo build/tasktest --summary "A test repo." --body "What this is."
```

4. Reload. The front door now reads **Start a task →**.
5. Press it, enter a title, submit. The front door must land on **Continue: Understand →**.

Clean up afterwards: `throughline forget` in that directory, then delete it.

- [ ] **Step 7: Commit**

`src/throughline/app/app.js` only.

---

## Task 6: Reverse the documented position

**Files:**
- Modify: `skills/throughline/SKILL.md:140-142`

The app now names setup as the next action whenever it is missing. `SKILL.md` currently tells Claude the opposite, and two instructions that disagree are worse than either alone — a user following the front door would be argued with by the assistant the front door just handed them to.

- [ ] **Step 1: Replace the paragraph**

Find:

```
**Setup is optional and can come later.** A task runs perfectly well
without it. Offer setup when a repo turns out to be worth it - the second
or third task in - rather than demanding it up front.
```

Replace with:

```
**Setup comes first, and the app asks for it.** A repo tracked for task
work opens on `Set this repo up` until the document exists, so a session
that follows the front door arrives here before its first task. Write it
then rather than deferring it - the app has already asked, and putting it
off leaves the user looking at the same prompt tomorrow.
```

- [ ] **Step 2: Check nothing else still states the old position**

Run: `grep -rn "earns it" skills/ src/`

Expected: no hits once Task 5 has replaced `drawSetup`. If `docs/project/` still carries the phrase, leave it alone and report it — those are the project's own pipeline artifacts, edited through the pipeline rather than by hand.

- [ ] **Step 3: Verify the skill pack tests**

Run: `uv run pytest tests/test_skill_pack.py -v`

Expected: all pass. That suite asserts on the skill's structure. If any assertion covers this paragraph's wording, update it and say exactly what you changed.

Run: `uv run pytest`
Expected: **350 passed**

- [ ] **Step 4: Commit**

`skills/throughline/SKILL.md` only.

---

## Task 7: Full pass

**Files:** none — verification only.

- [ ] **Step 1: Whole suite**

Run: `uv run pytest`
Expected: **350 passed**

- [ ] **Step 2: The front door names exactly one action**

With a task-only project that has neither setup nor a task loaded, in the console:

```js
["front-action","front-add","front-setup","front-start"].filter(id => !document.getElementById(id).hidden)
```

Expected: exactly one id, `front-setup`. Rule 1 is one next action, so more than one here is a failure.

- [ ] **Step 3: The old dead-end copy is gone**

```js
document.getElementById("setup-body").textContent.includes("when it earns it")
```

Expected: `false`

- [ ] **Step 4: Confirm the tree is clean**

```bash
git status --short
```

Expected: clean apart from `uv.lock` and `.claude/settings.local.json`, both deliberately untracked.

---

## Notes for whoever runs this

**`_post_start` is restructured, not extended.** It had two branches sharing one spawn; it now has three. The seven existing start tests are the net that catches a behaviour change in the node and task paths — do not skip them, and do not "tidy" them.

**Do not let `has_setup` grow into a count.** It answers one yes-or-no question for one button. The moment anything renders a number or a badge from it, rule 9 is broken.

**`build/` is gitignored**, so the scratch repo in Task 5 will not dirty the tree.
