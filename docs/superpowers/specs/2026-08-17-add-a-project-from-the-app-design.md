# Add a project from the app

Date: 2026-08-17
Status: proposed
Extends: `2026-08-16-project-pipeline-design.md`

## Why

The app has no way to start tracking a repository. With nothing tracked, the
front door prints two commands and asks you to go and run them somewhere else:

> Run throughline init in a repository, then throughline add to track it.

That is the one thing the app exists to remove. Capability 1, *start a pipeline
in a repo*, is built and shipped in the CLI; the app simply cannot reach it. The
gap is worse than an inconvenience, because the core job is stated as management
of projects **plural** — and a tool that cannot take on the second project is not
managing a set, it is displaying one.

The empty front door also breaks rule 1 in spirit. Rule 1 says never open with a
list of undone things and always name one next action. Today the empty state
names two actions, both of which are somewhere else.

## What changes

Three new endpoints, a new screen, a plugin in the desktop shell, and one
widened function signature. Nothing existing is removed.

### 1. Two endpoints, one per CLI command

```
POST /api/init   body: {path, project, flags[], target_side, task_only}
POST /api/add    ?path=<absolute path>
```

Each mirrors its command and reuses its refusals:

| Endpoint | Mirrors | Refuses |
|---|---|---|
| `/api/init` | `cmd_init` | `409` when a pipeline already exists |
| `/api/add` | `cmd_add` | `404` when the folder has no pipeline |

Both call the same `state_module.init` and `registry.add` the CLI calls. No rule
is decided here that the CLI does not already decide.

`/api/init` takes a JSON body rather than query parameters because the flags are
a list and the handler collapses repeats — `{k: v[0] for k, v in parse_qs(...)}`
in `Handler._respond` means `?flag=a&flag=b` silently loses `b`. `PUT
/api/artifact` already reads a raw body, so a body is not a new idea here.
`/api/add` has one scalar argument and stays a query parameter.

### 2. The client sequence

The two refusals compose into a probe, so no inspect endpoint is needed:

```
POST /api/add
  200 -> done; the folder already had a pipeline
  404 -> POST /api/init, then POST /api/add
```

`add` is attempted first because it writes nothing. A mistyped path is rejected
before anything can be created.

### 3. Bounds on the carve-out

These are the first two endpoints that do not pass through `_tracked_repo`, and
they cannot — the whole point is a path that is not tracked yet. `init` is
therefore an arbitrary-path **write** reachable over HTTP, which the CLI never
was, and it needs bounds the CLI never needed:

- **The directory must already exist and be a directory.** `state.save` calls
  `path.parent.mkdir(parents=True, exist_ok=True)`, so without this a typo
  conjures `C:\anything\docs\project\` into being.
- **`init` keeps refusing an existing pipeline**, so it cannot overwrite a
  project.
- The path is resolved and used. It is never created.

### 4. An Origin check on every POST

The server is localhost, unauthenticated, on a random port. Today the worst a
malicious page could do by guessing that port is `/api/start`. Once `/api/init`
exists it could write a `pipeline.yaml` into a directory it names, so this
feature is what opens the hole and closes it in the same change.

Any POST carrying an `Origin` header that does not match the request's own
`Host` is refused. Matching against `Host` rather than a configured value is
what makes this work at all, given the port is chosen at runtime and neither
side knows it in advance.

A POST with no `Origin` is allowed — that is curl and the CLI, not a browser.
Browsers always send `Origin` on cross-origin POSTs, which is what makes the
check sufficient.

The check covers every POST, including the existing `/api/promote` and
`/api/start`. GETs are deliberately left alone: they change nothing, and a
cross-origin GET cannot read its own response, so there is nothing to protect
that is not already protected.

### 5. `route()` gains an optional parameter

```python
def route(method, path, query, body, headers=None)
```

`route` is deliberately a pure function of its arguments and around forty tests
call it directly. `headers` is defaulted so every existing call site and test is
untouched, and the Origin check remains testable without opening a socket.

## The interface

### Getting in

**The empty front door** replaces its two-command instruction with one action:

```
No projects yet
Throughline tracks repositories you have pointed it at.
        [ Add a project -> ]
```

**The switcher** gains a permanent `+ Add a project...` row beneath the project
list, so a second project can be added at any time.

### The add screen

A new `"adding"` entry in `SCREENS`, reached with `goTo("adding")` so it takes
part in back and forward like every other screen. Not a modal: the `.scrim`
treatment suits a forced binary decision, not seven controls.

```
ADD A PROJECT
Point Throughline at a folder

Folder   [ C:\Dev\my-project              ] [ Browse... ]

+- If this folder does not have a pipeline yet -------------+
| Name    [ my-project                     ]                |
| Kind    (o) Full pipeline   ( ) Task work only            |
| Extras  [ ] Database          adds ER / relational model  |
|         [ ] State             adds State machine          |
|         [ ] Multiple services adds Deployment             |
|         [ ] User interface    adds nothing yet            |
|         [ ] Track a target side as well as current        |
+-----------------------------------------------------------+

              [ Add project ]  [ Cancel ]
```

The name field is prefilled from the folder's own name.

The fieldset legend is load-bearing. Because the API mirrors the CLI and there
is no inspect endpoint, the client cannot know whether the folder has a pipeline
until it POSTs. The legend states that condition plainly rather than having the
form pretend to adapt to something it cannot see.

### Flags are served, not hardcoded

`GET /api/flags` returns `[{name, adds}]`, derived from `nodes_module.FLAGS` and
the nodes that declare each one.

This matters for three reasons. The labels cannot drift from the pipeline
definition. `has_ui` renders honestly as *adds nothing yet* rather than as a
checkbox that lies — no node declares `flag="has_ui"`, so setting it activates
nothing. And when that is resolved, the checkbox corrects itself with no change
here. `app.js` already hardcodes `PHASES`, duplicating `nodes.py`; this avoids a
second copy of the same mistake.

### The folder picker

Native in the desktop shell, typed everywhere else. A browser's
`<input webkitdirectory>` withholds real filesystem paths by design, so there is
no third option.

Four changes to the shell:

1. `tauri-plugin-dialog` in `Cargo.toml`, `.plugin(tauri_plugin_dialog::init())`
   in `main.rs`
2. `"withGlobalTauri": true` in `tauri.conf.json`, so plain `app.js` can call it
   with no bundler
3. A capability granting `dialog:allow-open` to the main window
4. `"remote": { "urls": ["http://127.0.0.1:*"] }` on that capability

Item 4 is the cost of `WebviewUrl::External`. The sidecar's port is chosen at
runtime, so the pattern must be a wildcard, which means any page served from any
port on 127.0.0.1 could open a folder dialog in that window. The window only
ever loads our own sidecar, so the practical exposure is small, but it is a real
widening and is recorded here rather than left in a diff.

The page feature-detects `window.__TAURI__`. Absent, the Browse button is not
rendered and the text field is the only input.

## Errors

Every failure is one plain sentence, shown next to the field:

| Condition | Says |
|---|---|
| Empty path | Type or choose a folder. |
| No such folder, or not a directory | There is no folder at that path. |
| Path is a file | That is a file, not a folder. |
| Already tracked | `registry.add` is idempotent, so this succeeds and opens the project |
| `init` refused, pipeline exists | Fall through to `add`; the folder is tracked and opened |
| Anything else | The server's own message, verbatim |

On success the app refreshes its project list and opens the new project at its
front door.

## Testing

Python, in `tests/test_serve.py`, following the existing behavioural naming:

- `add` on an untracked folder that has a pipeline tracks it
- `add` on a folder with no pipeline returns 404 and leaves the registry alone
- `init` writes the name, flags, task-only and target-side through
- `init` refuses an existing pipeline and leaves the file byte-identical
- `init` on a path that does not exist creates nothing — the `mkdir` guard
- `init` refuses a path that is a file rather than a directory
- a POST with a foreign `Origin` is refused; own-origin and absent both pass
- `/api/flags` lists exactly `nodes_module.FLAGS`

## Not in scope

**The dead `has_ui` flag.** It is declared in `FLAGS`, the glossary says flags
decide which nodes exist, and `SKILL.md` spends one of the intake interview's
six questions establishing it — but no node declares it, so the answer is
discarded. Deciding whether to give it a document or remove it is a product
decision about the pipeline, tracked separately. This design only ensures the
form describes it honestly in the meantime.

**Prefilling flags by detection.** `setup.detect` deliberately works before
`init` and would be the natural source, but it reads MCP servers, launch
configs, CI and commands — tooling, not domain shape. It cannot infer `has_db`
or its siblings, so the flags are asked.

**Creating the folder.** The app tracks folders that exist. Making a directory
is not this feature's job, and permitting it is what the `mkdir` bound above
exists to prevent.
