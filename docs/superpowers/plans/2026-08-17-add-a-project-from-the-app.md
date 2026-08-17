# Add a Project From the App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let someone point Throughline at a folder from inside the app and have it tracked, creating the pipeline first when the folder does not have one.

**Architecture:** Two POST endpoints mirror `cmd_init` and `cmd_add` one-for-one and reuse their refusals, so the client can try `add` and fall back to `init` without a third "inspect" endpoint. Both must bypass the registry allow-list, since an unadded folder is by definition untracked, so they are bounded instead by requiring the directory to already exist — and an `Origin` check lands on every POST in the same change. A new `adding` screen collects the folder and the `init` arguments; the flag checkboxes are served from `nodes.FLAGS` rather than hardcoded so they cannot drift.

**Tech Stack:** Python 3.12 stdlib (`http.server`, `json`, `pathlib`), pytest, vanilla ES2020 in `app.js`, plain CSS, Tauri 2 with `tauri-plugin-dialog`.

**Spec:** `docs/superpowers/specs/2026-08-17-add-a-project-from-the-app-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/throughline/serve.py` | Modify. Adds `_origin_ok`, `_writable_dir`, `_post_add`, `_post_init`, `_get_flags`; widens `route()` with `headers`; `Handler` passes them |
| `tests/test_serve.py` | Modify. Behavioural tests for all of the above |
| `src/throughline/app/index.html` | Modify. New `#adding` section, `#front-add` button |
| `src/throughline/app/app.css` | Modify. Styles for the form, fieldset and switcher add-row |
| `src/throughline/app/app.js` | Modify. `adding` screen, the add/init sequence, served flags, picker detection |
| `desktop/Cargo.toml` | Modify. `tauri-plugin-dialog` dependency |
| `desktop/src/main.rs` | Modify. Register the dialog plugin |
| `desktop/tauri.conf.json` | Modify. `withGlobalTauri` |
| `desktop/capabilities/default.json` | **Create.** Grants `dialog:allow-open` to the `main` window and allows the runtime-port origin |

No new Python modules. Every rule already lives in `state`, `registry` and `nodes`; `serve.py` only routes to them.

---

## Task 1: Refuse cross-origin POSTs

The server is localhost, unauthenticated, on a port chosen at runtime. Once
`/api/init` exists, a page that guesses the port could write a file into a
directory it names. This lands first because it widens `route()`'s signature,
which every later task builds on.

**Files:**
- Modify: `src/throughline/serve.py:356` (`route`), `src/throughline/serve.py:386` (`Handler._respond`)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_serve.py`, after `test_asset_paths_cannot_escape_the_package`:

```python
def test_a_post_from_another_origin_is_refused(tmp_path, monkeypatch):
    """The server is localhost, unauthenticated, on a guessable port.

    POSTs create files and start processes. A browser always sends
    Origin on a cross-origin POST, so a page that found the port still
    cannot make one.
    """
    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Origin": "http://evil.example", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 403


def test_a_post_from_the_app_itself_is_allowed(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Origin": "http://127.0.0.1:7373", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 200


def test_a_post_with_no_origin_is_allowed(tmp_path, monkeypatch):
    """Nothing sends Origin from a terminal. curl and the CLI still work."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Host": "127.0.0.1:7373"},
    )
    assert response.status == 200


def test_header_case_does_not_decide_the_origin_check():
    """http.server hands headers back in whatever case they arrived in."""
    response = serve.route(
        "POST",
        "/api/promote",
        {},
        b"",
        {"origin": "http://evil.example", "host": "127.0.0.1:7373"},
    )
    assert response.status == 403
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "origin or header_case" -v`
Expected: FAIL — `TypeError: route() takes 4 positional arguments but 5 were given`

- [ ] **Step 3: Add the check**

In `src/throughline/serve.py`, add above `route`:

```python
def _origin_ok(headers) -> bool:
    """Whether a POST came from the app rather than from another page.

    The server has no authentication and its port is chosen at runtime,
    so there is no configured origin to compare against - the host the
    request was addressed to is the only thing both sides agree on.

    A missing Origin is allowed on purpose. Browsers always send one on
    a cross-origin POST; terminals never send one at all, so curl and
    the CLI are untouched. GETs are left alone: they change nothing, and
    a cross-origin GET cannot read its own response.
    """
    if not headers:
        return True
    lowered = {str(name).lower(): value for name, value in dict(headers).items()}
    origin = lowered.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == lowered.get("host", "")
```

- [ ] **Step 4: Widen `route` and wire the handler**

Replace the `def route(...)` line at `src/throughline/serve.py:356`:

```python
def route(
    method: str, path: str, query: dict, body: bytes, headers=None
) -> Response:
    if method == "POST" and not _origin_ok(headers):
        return _error(403, "cross-origin request refused")
    if method == "GET" and path in ASSET_TYPES:
```

`headers` is defaulted so the forty-odd existing call sites and tests are
untouched.

In `Handler._respond`, replace the `route(...)` call at
`src/throughline/serve.py:391`:

```python
        response = route(method, parsed.path, query, body, self.headers)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_serve.py -k "origin or header_case" -v`
Expected: 4 passed

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest`
Expected: all pass — 309 before, 313 now

- [ ] **Step 7: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py
git commit -m "Refuse a POST that another page sent"
```

---

## Task 2: `POST /api/add`

**Files:**
- Modify: `src/throughline/serve.py`
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_folder_with_a_pipeline_can_be_tracked_from_the_app(tmp_path, monkeypatch):
    """The one thing the app could not do.

    Every other endpoint refuses a repo the registry has not heard of,
    which is exactly what a folder being added always is.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "fresh"
    repo.mkdir()
    state.init(repo, "Fresh", {})

    response = serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    assert response.status == 200
    assert repo.resolve() in registry.projects()


def test_adding_a_folder_with_no_pipeline_is_refused(tmp_path, monkeypatch):
    """404 here means one thing only, so the app can act on it.

    A missing folder is a bad argument and answers 400. Only "there is
    no pipeline in it" answers 404, which is what tells the app to
    create one.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    bare = tmp_path / "bare"
    bare.mkdir()

    response = serve.route("POST", "/api/add", {"path": str(bare)}, b"")
    assert response.status == 404
    assert registry.projects() == []


def test_adding_a_folder_that_is_not_there_is_a_bad_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    response = serve.route(
        "POST", "/api/add", {"path": str(tmp_path / "nope")}, b""
    )
    assert response.status == 400


def test_adding_a_file_rather_than_a_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    lonely = tmp_path / "notes.md"
    lonely.write_text("hello", encoding="utf-8")
    response = serve.route("POST", "/api/add", {"path": str(lonely)}, b"")
    assert response.status == 400


def test_adding_a_folder_twice_is_harmless(tmp_path, monkeypatch):
    """registry.add already no-ops on a repeat. Say so in a test."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "fresh"
    repo.mkdir()
    state.init(repo, "Fresh", {})

    serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    assert registry.projects() == [repo.resolve()]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "tracked_from_the_app or no_pipeline_is_refused or not_there_is_a_bad or file_rather_than_a_folder or folder_twice" -v`
Expected: FAIL — all return 404 "no such route"

- [ ] **Step 3: Add the shared path guard and the endpoint**

In `src/throughline/serve.py`, add below `_tracked_repo`:

```python
def _named_dir(raw: str | None) -> tuple[Path | None, Response | None]:
    """Resolve a path the caller named, for the two endpoints that must
    accept one the registry has never heard of.

    Onboarding a folder means naming one that is not tracked yet, so the
    allow-list cannot apply. The bound instead is that the folder has to
    be there already: state.save creates parent directories, so without
    this a typo would conjure a whole tree into being at any path.

    A missing or non-directory path answers 400 rather than 404, so that
    404 keeps a single meaning for the caller - the folder is real and
    has no pipeline in it.
    """
    if not raw:
        return None, _error(400, "path is required")
    resolved = Path(raw).resolve()
    if not resolved.exists():
        return None, _error(400, "there is no folder at that path")
    if not resolved.is_dir():
        return None, _error(400, "that is a file, not a folder")
    return resolved, None


def _post_add(query: dict) -> Response:
    """Track a folder that already has a pipeline. Mirrors cmd_add."""
    repo, failure = _named_dir(query.get("path"))
    if failure is not None:
        return failure
    if not state_module.exists(repo):
        return _error(404, "no pipeline in that folder")
    registry.add(repo)
    return _json_response({"path": str(repo)})
```

- [ ] **Step 4: Route it**

In `route`, add above the `/api/start` line:

```python
    if method == "POST" and path == "/api/add":
        return _post_add(query)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_serve.py -k "tracked_from_the_app or no_pipeline_is_refused or not_there_is_a_bad or file_rather_than_a_folder or folder_twice" -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py
git commit -m "Track a folder from the app"
```

---

## Task 3: `POST /api/init`

**Files:**
- Modify: `src/throughline/serve.py`
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_pipeline_can_be_created_from_the_app(tmp_path, monkeypatch):
    """Mirrors cmd_init, including which nodes the flags switch on."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps(
        {
            "path": str(repo),
            "project": "Bare",
            "flags": ["has_db"],
            "target_side": True,
            "task_only": False,
        }
    ).encode("utf-8")

    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 200

    loaded = state.load(repo)
    assert loaded.project == "Bare"
    assert loaded.flags["has_db"] is True
    assert loaded.flags["has_state"] is False
    assert loaded.target_side is True
    assert loaded.task_only is False


def test_creating_a_pipeline_can_make_a_task_only_repo(tmp_path, monkeypatch):
    """Task-only is the mode the Setup screen exists for."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "client"
    repo.mkdir()
    body = json.dumps(
        {"path": str(repo), "project": "Client", "task_only": True}
    ).encode("utf-8")

    serve.route("POST", "/api/init", {}, body)
    assert state.load(repo).task_only is True


def test_creating_a_pipeline_over_an_existing_one_is_refused(tmp_path, monkeypatch):
    """Same refusal as cmd_init, and the file must not move."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "taken"
    repo.mkdir()
    state.init(repo, "Original", {})
    before = state.state_path(repo).read_bytes()

    body = json.dumps({"path": str(repo), "project": "Usurper"}).encode("utf-8")
    response = serve.route("POST", "/api/init", {}, body)

    assert response.status == 409
    assert state.state_path(repo).read_bytes() == before


def test_creating_a_pipeline_never_creates_the_folder(tmp_path, monkeypatch):
    """state.save calls mkdir(parents=True).

    Over HTTP that turns one mistyped character into a directory tree
    somewhere nobody asked for.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    missing = tmp_path / "not" / "there"

    body = json.dumps({"path": str(missing), "project": "Ghost"}).encode("utf-8")
    response = serve.route("POST", "/api/init", {}, body)

    assert response.status == 400
    assert not missing.exists()
    assert not (tmp_path / "not").exists()


def test_creating_a_pipeline_needs_a_name(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps({"path": str(repo), "project": "   "}).encode("utf-8")
    assert serve.route("POST", "/api/init", {}, body).status == 400


def test_an_unknown_flag_is_refused(tmp_path, monkeypatch):
    """Flags are an allow-list, like node ids are."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps(
        {"path": str(repo), "project": "Bare", "flags": ["has_teeth"]}
    ).encode("utf-8")

    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 400
    assert not state.exists(repo)


def test_a_body_that_is_not_json_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    assert serve.route("POST", "/api/init", {}, b"not json").status == 400
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "created_from_the_app or task_only_repo or over_an_existing_one or never_creates_the_folder or needs_a_name or unknown_flag or not_json" -v`
Expected: FAIL — all return 404 "no such route"

- [ ] **Step 3: Add the endpoint**

In `src/throughline/serve.py`, add below `_post_add`:

```python
def _post_init(body: bytes) -> Response:
    """Create a pipeline in a folder. Mirrors cmd_init.

    A JSON body rather than query parameters because the flags are a
    list, and Handler keeps only the first value of a repeated
    parameter - sent in the query, every flag but one would vanish
    silently.
    """
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _error(400, "body must be json")
    if not isinstance(payload, dict):
        return _error(400, "body must be a json object")

    repo, failure = _named_dir(payload.get("path"))
    if failure is not None:
        return failure

    project = str(payload.get("project") or "").strip()
    if not project:
        return _error(400, "project is required")
    if state_module.exists(repo):
        return _error(409, "that folder already has a pipeline")

    asked = payload.get("flags") or []
    if not isinstance(asked, list):
        return _error(400, "flags must be a list")
    for name in asked:
        if name not in nodes_module.FLAGS:
            return _error(400, f"no such flag: {name}")

    state_module.init(
        repo,
        project,
        {name: name in asked for name in nodes_module.FLAGS},
        target_side=bool(payload.get("target_side")),
        task_only=bool(payload.get("task_only")),
    )
    return _json_response({"path": str(repo), "project": project})
```

- [ ] **Step 4: Route it**

In `route`, beside the `/api/add` line:

```python
    if method == "POST" and path == "/api/init":
        return _post_init(body)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_serve.py -k "created_from_the_app or task_only_repo or over_an_existing_one or never_creates_the_folder or needs_a_name or unknown_flag or not_json" -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py
git commit -m "Create a pipeline from the app"
```

---

## Task 4: `GET /api/flags`

**Files:**
- Modify: `src/throughline/serve.py`
- Test: `tests/test_serve.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_the_flags_are_served_with_what_each_one_adds(tmp_path, monkeypatch):
    """The form must not keep its own copy of this list.

    app.js already hardcodes PHASES, duplicating nodes.py. A second copy
    of the same kind would drift the moment a flag is added or removed.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    payload = _json(serve.route("GET", "/api/flags", {}, b""))

    assert [item["name"] for item in payload] == list(nodes.FLAGS)
    by_name = {item["name"]: item["adds"] for item in payload}
    assert by_name["has_db"] == "ER / relational model"
    assert by_name["has_state"] == "State machine"


def test_a_flag_that_switches_on_nothing_says_so(tmp_path, monkeypatch):
    """has_ui is declared but no node declares it.

    Until that is resolved the form must describe it honestly rather
    than offer a checkbox that quietly does nothing.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    payload = _json(serve.route("GET", "/api/flags", {}, b""))
    assert {"name": "has_ui", "adds": None} in payload
```

Add `nodes` to the import at the top of `tests/test_serve.py`:

```python
from throughline import nodes, registry, serve, state
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve.py -k "flags_are_served or switches_on_nothing" -v`
Expected: FAIL — 404 "no such route"

- [ ] **Step 3: Add the endpoint**

In `src/throughline/serve.py`, add below `_get_projects`:

```python
def _get_flags() -> Response:
    """Every flag, and the document it switches on.

    Served rather than hardcoded in the app so the form cannot drift
    from the pipeline definition, and so a flag that activates nothing
    reports null instead of pretending to do something.
    """
    adds = {
        node.flag: node.title
        for node in nodes_module.NODES
        if node.activation == nodes_module.FLAG and node.flag
    }
    return _json_response(
        [{"name": name, "adds": adds.get(name)} for name in nodes_module.FLAGS]
    )
```

- [ ] **Step 4: Route it**

In `route`, below the `/api/projects` line:

```python
    if method == "GET" and path == "/api/flags":
        return _get_flags()
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_serve.py -k "flags_are_served or switches_on_nothing" -v`
Expected: 2 passed

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest`
Expected: all pass — 309 at the start, plus 4 + 5 + 7 + 2 from Tasks 1 to 4,
so 327

- [ ] **Step 7: Commit**

```bash
git add src/throughline/serve.py tests/test_serve.py
git commit -m "Serve the flags rather than repeating them in the app"
```

---

## Task 5: The add screen's markup and styles

**Files:**
- Modify: `src/throughline/app/index.html:50-55` (front section), after `:113` (tasks section)
- Modify: `src/throughline/app/app.css`

- [ ] **Step 1: Add the empty-state button**

In `src/throughline/app/index.html`, replace the `#front` section:

```html
    <section id="front" class="screen">
      <p class="kicker" id="front-project"></p>
      <p class="reminder" id="front-reminder"></p>
      <button id="front-action" class="hero"></button>
      <button id="front-add" class="hero" hidden>Add a project &rarr;</button>
      <p class="sub" id="front-sub"></p>
    </section>
```

- [ ] **Step 2: Add the screen**

In `src/throughline/app/index.html`, after the `#tasks` section's closing
`</section>` and before `<section id="failure"`:

```html
    <section id="adding" class="screen prose" hidden>
      <p class="kicker">Add a project</p>
      <h2>Point Throughline at a folder</h2>

      <div class="field">
        <span class="lbl">Folder</span>
        <div class="pick">
          <input id="add-path" type="text" spellcheck="false"
                 placeholder="C:\Dev\my-project">
          <button id="add-browse" class="hollow" hidden>Browse&hellip;</button>
        </div>
      </div>

      <fieldset id="add-new">
        <legend>If this folder doesn't have a pipeline yet</legend>

        <div class="field">
          <span class="lbl">Name</span>
          <input id="add-name" type="text" spellcheck="false">
        </div>

        <div class="field">
          <span class="lbl">Kind</span>
          <div class="choices">
            <label><input type="radio" name="add-kind" value="full" checked>
              Full pipeline</label>
            <label><input type="radio" name="add-kind" value="task">
              Task work only</label>
          </div>
        </div>

        <div class="field">
          <span class="lbl">Extras</span>
          <div class="choices">
            <div id="add-flags"></div>
            <label><input id="add-target" type="checkbox">
              Track a target side as well as current</label>
          </div>
        </div>
      </fieldset>

      <div id="add-error" class="note edge" hidden></div>

      <div class="row">
        <button id="add-submit" class="solid">Add project</button>
        <button id="add-cancel" class="hollow">Cancel</button>
      </div>
    </section>
```

- [ ] **Step 3: Add the styles**

In `src/throughline/app/app.css`, append at the end:

```css
/* Adding a project -------------------------------------------------- */

.field { display: flex; align-items: baseline; gap: 16px; margin-bottom: 16px; }
.field .lbl { flex: none; width: 74px; font-size: 12px; color: var(--muted); }

.field input[type="text"] {
  flex: 1;
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--divider);
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
  padding: 10px 12px;
  outline: none;
}

.field input[type="text"]:focus { border-color: var(--accent); }
.pick { flex: 1; display: flex; gap: 8px; min-width: 0; }

#add-new {
  border: 1px solid var(--divider);
  border-left: 3px solid var(--divider);
  padding: 18px 20px 4px;
  margin: 0 0 20px;
}

#add-new legend {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
  padding: 0 8px;
}

.choices { display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
.choices label { display: flex; align-items: baseline; gap: 8px; }
.choices .adds { color: var(--muted); }

.sw-add { color: var(--accent-text); font-weight: 800; }
```

- [ ] **Step 4: Check it renders**

Run: `uv run throughline serve --port 7380`

Open `http://127.0.0.1:7380` in the Browser pane, then in the console:

```js
document.getElementById('adding').hidden = false;
```

Expected: the form appears, labels line up, the fieldset legend reads
"If this folder doesn't have a pipeline yet". Stop the server afterwards.

- [ ] **Step 5: Commit**

```bash
git add src/throughline/app/index.html src/throughline/app/app.css
git commit -m "Add the markup for the add-a-project screen"
```

---

## Task 6: Wire the screen up

**Files:**
- Modify: `src/throughline/app/app.js`

- [ ] **Step 1: Register the screen and the flag labels**

In `src/throughline/app/app.js`, replace the `SCREENS` line at `:21`:

```js
const SCREENS = ["front", "map", "setup", "reading", "editing", "tasks", "adding", "failure"];

/* Human words for the flags. The list itself comes from the server so it
 * cannot drift; only the wording lives here, and an unknown flag falls
 * back to its own name rather than disappearing. */
const FLAG_WORDS = {
  has_db: "Database",
  has_ui: "User interface",
  has_state: "State",
  multi_service: "Multiple services",
};
```

- [ ] **Step 2: Add the screen's logic**

In `src/throughline/app/app.js`, add just above the `/* Tasks */` banner:

```js
/* Adding a project ------------------------------------------------- */

let flagList = null;

async function drawFlags() {
  if (!flagList) flagList = (await api("/api/flags")) || [];
  const box = el("add-flags");
  box.innerHTML = "";
  flagList.forEach((flag) => {
    const row = document.createElement("label");
    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.className = "flag";
    tick.value = flag.name;
    const words = document.createElement("span");
    words.innerHTML =
      `${esc(FLAG_WORDS[flag.name] || flag.name)} ` +
      `<span class="adds">${flag.adds ? `adds ${esc(flag.adds)}` : "adds nothing yet"}</span>`;
    row.append(tick, words);
    box.appendChild(row);
  });
}

function addError(text) {
  const box = el("add-error");
  box.textContent = text;
  box.hidden = !text;
}

async function openAdd() {
  el("add-path").value = "";
  el("add-name").value = "";
  delete el("add-name").dataset.touched;
  el("add-target").checked = false;
  document.querySelector('input[name="add-kind"][value="full"]').checked = true;
  addError("");
  await drawFlags();
  // The picker only exists inside the desktop shell. In a browser the
  // text field is the whole input, so the button is not offered.
  el("add-browse").hidden = !(window.__TAURI__ && window.__TAURI__.dialog);
  goTo("adding");
  el("add-path").focus();
}

/* The folder's own name is the project's name nine times out of ten,
 * so it is filled in until the moment someone types their own. */
el("add-path").oninput = () => {
  if (el("add-name").dataset.touched) return;
  const typed = el("add-path").value.trim().replace(/[\\/]+$/, "");
  el("add-name").value = typed.split(/[\\/]/).pop() || "";
};

el("add-name").oninput = () => { el("add-name").dataset.touched = "1"; };

el("add-browse").onclick = async () => {
  const chosen = await window.__TAURI__.dialog.open({
    directory: true,
    multiple: false,
  });
  if (typeof chosen !== "string") return;
  el("add-path").value = chosen;
  el("add-path").dispatchEvent(new Event("input"));
};

el("add-cancel").onclick = async () => {
  if (history.length) await el("back").onclick();
  else show("front");
};

async function said(response) {
  const problem = await response.json().catch(() => ({}));
  return problem.error || "That didn't work.";
}

/* Add first, and only create a pipeline if there is none.
 *
 * The two endpoints mirror the two CLI commands, and their refusals
 * compose: add writes nothing, so a mistyped path is turned away before
 * anything can be created. 404 from add means one thing only - the
 * folder is real and has no pipeline in it. */
el("add-submit").onclick = async () => {
  const path = el("add-path").value.trim();
  if (!path) return addError("Type or choose a folder.");

  const button = el("add-submit");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Adding…";
  addError("");

  const track = () =>
    fetch(`/api/add?path=${encodeURIComponent(path)}`, { method: "POST" });

  try {
    let response = await track();

    if (response.status === 404) {
      const created = await fetch("/api/init", {
        method: "POST",
        body: JSON.stringify({
          path,
          project: el("add-name").value.trim(),
          flags: [...document.querySelectorAll("#add-flags input.flag:checked")]
            .map((tick) => tick.value),
          target_side: el("add-target").checked,
          task_only:
            document.querySelector('input[name="add-kind"]:checked').value === "task",
        }),
      });
      if (!created.ok) return addError(await said(created));
      response = await track();
    }

    if (!response.ok) return addError(await said(response));

    const added = await response.json();
    projects = (await api("/api/projects")) || [];
    await openProject(added.path);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
};
```

- [ ] **Step 3: Add the two entry points**

In `drawSwitcher`, before the closing `}`:

```js
  const more = document.createElement("button");
  more.className = "sw-row sw-add";
  more.innerHTML = "<span>+ Add a project…</span>";
  more.onclick = () => { el("switcher").hidden = true; openAdd(); };
  box.appendChild(more);
```

In `drawFront`, immediately after the opening line that sets
`front-project`, hide the empty-state button — a loaded project never shows
it:

```js
  el("front-add").hidden = true;
```

In `start()`, replace the no-projects branch:

```js
    if (!home || !home.path) {
      el("front-project").textContent = "No projects yet";
      el("front-reminder").textContent =
        "Throughline tracks repositories you have pointed it at.";
      el("front-action").hidden = true;
      el("front-add").hidden = false;
      el("front-sub").textContent = "";
      show("front");
      return;
    }
```

And wire the button, next to the other top-level handlers:

```js
el("front-add").onclick = () => openAdd();
```

- [ ] **Step 4: Verify the empty state**

Run: `uv run throughline serve --port 7380`

With nothing tracked, open `http://127.0.0.1:7380` in the Browser pane.
Expected: "No projects yet" and one red **Add a project →** button, with no
mention of a command to go and run.

Click it. Expected: the form, with **Browse…** absent because this is a
browser, and four flag rows — `has_ui` reading "adds nothing yet".

- [ ] **Step 5: Verify a real add, end to end**

In a second shell:

```bash
mkdir C:\Dev\throughline\build\addtest
```

In the app, type `C:\Dev\throughline\build\addtest`, confirm the name
prefills to `addtest`, and press **Add project**.

Expected: the app lands on that project's front door. Then confirm on disk:

Run: `uv run throughline projects`
Expected: `addtest` is listed.

Clean up: `uv run throughline forget --repo C:\Dev\throughline\build\addtest`
then remove the folder. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add src/throughline/app/app.js
git commit -m "Add a project without leaving the app"
```

---

## Task 7: The native folder picker

**Files:**
- Modify: `desktop/Cargo.toml:11-12`
- Modify: `desktop/src/main.rs:136`
- Modify: `desktop/tauri.conf.json:9-14`
- Create: `desktop/capabilities/default.json`

- [ ] **Step 1: Add the plugin dependency**

In `desktop/Cargo.toml`, replace the `[dependencies]` block:

```toml
[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-dialog = "2"
```

- [ ] **Step 2: Register the plugin**

In `desktop/src/main.rs`, replace the builder's opening line at `:136`:

```rust
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
```

- [ ] **Step 3: Expose the API to a plain script**

In `desktop/tauri.conf.json`, replace the `"app"` block:

```json
  "app": {
    "withGlobalTauri": true,
    "windows": [],
    "security": {
      "csp": null
    }
  },
```

`app.js` is a plain `<script>` with no bundler, so `window.__TAURI__` is the
only way it can reach the plugin.

- [ ] **Step 4: Grant the permission**

Create `desktop/capabilities/default.json`:

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "The main window may ask the operating system for a folder.",
  "windows": ["main"],
  "remote": {
    "urls": ["http://127.0.0.1:*"]
  },
  "permissions": ["dialog:allow-open"]
}
```

`remote.urls` is required and is the one real widening here. The window is
pointed at `WebviewUrl::External`, so as far as Tauri is concerned the page is
a remote origin and gets no IPC without being named. The sidecar's port is
chosen at runtime, so the pattern has to be a wildcard — which means any page
served from any port on 127.0.0.1 could open a folder dialog in this window.
The window only ever loads our own sidecar, which is what keeps that narrow.

- [ ] **Step 5: Build and check it compiles**

Run: `cargo check --manifest-path desktop/Cargo.toml`
Expected: finishes with no errors. The first run compiles the dialog plugin
and its dependencies, so allow several minutes. `cargo` needs to be on
`PATH` — it installs to `%USERPROFILE%\.cargo\bin`, which the shell may not
pick up until it is added explicitly.

- [ ] **Step 6: Verify the picker in the real shell**

Run: `powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1`

This machine needs the project venv on `PATH` first, because the script calls
bare `python`:

```bash
$env:PATH = "C:\Dev\throughline\.venv\Scripts;$env:USERPROFILE\.cargo\bin;$env:PATH"
```

Install to a neutral directory — `%LOCALAPPDATA%` is redirected inside an MSIX
container and PyInstaller's onefile bootloader refuses to run under that
redirection:

```bash
Start-Process -Wait -FilePath "desktop\target\release\bundle\nsis\Throughline_0.1.1_x64-setup.exe" -ArgumentList "/S","/D=C:\Dev\throughline\build\pickertest"
```

Launch `C:\Dev\throughline\build\pickertest\throughline-desktop.exe`, open the
add screen and press **Browse…**.

Expected: a native folder dialog opens, and choosing a folder fills the path
field and prefills the name.

Uninstall afterwards with
`C:\Dev\throughline\build\pickertest\uninstall.exe /S`.

- [ ] **Step 7: Commit**

```bash
git add desktop/Cargo.toml desktop/Cargo.lock desktop/src/main.rs desktop/tauri.conf.json desktop/capabilities/default.json
git commit -m "Let the shell ask the operating system for a folder"
```

---

## Task 8: Full pass

**Files:** none — verification only.

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest`
Expected: all pass, 327 tests

- [ ] **Step 2: Confirm the empty state is gone for good**

Run: `uv run throughline serve --port 7380`

With nothing tracked, load the app and check no screen anywhere names a
command to run in a terminal:

```js
[...document.querySelectorAll('#front, #adding')]
  .map(s => s.textContent).join(' ').includes('throughline init')
```

Expected: `false`

- [ ] **Step 3: Confirm the Origin guard is live over real HTTP**

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST -H "Origin: http://evil.example" "http://127.0.0.1:7380/api/add?path=C:/Dev"
```

Expected: `403`

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:7380/api/add?path=C:/Dev"
```

Expected: `404` — no Origin, so the check passes and it fails on the real
reason instead. Stop the server.

- [ ] **Step 4: Commit anything outstanding**

```bash
git status --short
```

Expected: clean apart from `uv.lock`, which is a separate decision.

---

## Notes for whoever runs this

**`has_ui` is a dead flag.** It is in `FLAGS`, the glossary says flags decide
which nodes exist, and `SKILL.md` spends an intake question on it — but no node
declares it. Task 4 makes the form say "adds nothing yet" rather than lie about
it. Fixing it properly is tracked separately and is deliberately not in this
plan.

**`build/` is gitignored,** so the scratch folders in Tasks 6 and 7 will not
dirty the repo.

**Do not "fix" `route`'s signature by making `headers` required.** It is
defaulted so that the existing tests keep calling it with four arguments, which
is what keeps this change small.
