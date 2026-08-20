# Telling you a release exists

Date: 2026-08-20
Status: **superseded** by `2026-08-20-updating-itself-design.md`

The reason this stopped short of an auto-updater was wrong, and was checked
rather than argued. See that document.

## Why

There is no update path. Six releases shipped in three days, each one found by
somebody happening to look at GitHub, downloaded by hand, and installed over
the last. The v0.6.0 fix mattered — before it, the agent window could not run a
single command — and nothing in the product would have told anyone.

## What this is not

**Not an auto-updater.** Tauri has one, and it is the right answer for a real
product: a signing keypair, `createUpdaterArtifacts`, a `latest.json` published
per release, downloads applied in place.

It is not the right answer yet, for one reason. The installer is unsigned, so
every silent update ends at a SmartScreen warning the user has to click
through — a download they did not ask for, from a dialog telling them not to
trust it. **Signing is the blocker, not the updater.** Once there is a
certificate, revisit this and build the real thing; until then an in-place
updater buys almost nothing over a link.

## The thing this changes about the tool

Throughline has never made an outbound request. Mermaid is vendored, 3.5MB of
it, specifically so the app works offline. The server binds loopback, refuses
cross-origin writes, and refuses any request whose `Host` is not this machine.

This adds the first call to the internet, and that is a change in character
worth naming rather than sliding in. Three things bound it:

- **The window does not make it.** The sidecar does. The window keeps talking
  only to `127.0.0.1`, so nothing about the existing posture changes.
- **Nothing about you is sent.** One GET to `api.github.com` for this
  project's own latest release, carrying a User-Agent and nothing else. No repo
  paths, no project names, no identifiers. On a machine full of client work
  that is the part that matters.
- **Every failure is silent.** No network, GitHub down, rate limited, garbled
  JSON: the answer is "nothing to say", never an error. A tool that complains
  about not reaching the internet is worse than one that never looked.

## Design

### The module: `src/throughline/updates.py`

```python
RELEASES = "https://api.github.com/repos/RomansJefremovs/throughline/releases/latest"
```

- `current() -> str` — this build's version
- `latest(timeout=3.0) -> tuple[str, str] | None` — `(tag, url)` from GitHub, or
  `None` for any failure whatsoever
- `is_newer(candidate, current) -> bool` — compares `vX.Y.Z` as integer
  tuples, leading `v` optional on either side. Anything unparseable is "not
  newer", because a tag nobody can read is not a release worth chasing
- `check(force=False) -> dict` — the cached answer, refreshing at most once a
  day
- `dismiss(version)` / `dismissed() -> str | None`

Nothing here raises. The one and only contract is that a caller can always ask
and always get an answer.

### Where the version comes from

`throughline/__init__.py` gains `__version__`. The frozen build has no
`pyproject.toml` to read and PyInstaller does not reliably carry package
metadata, so a constant is the only thing that works in both.

That makes a fifth place to bump on release, which is a drift risk — so a test
asserts `__version__` equals the version in `pyproject.toml`. Discipline is not
a mechanism; the test is.

### State: two files in `~/.throughline/`

Beside `agent` and `projects.txt`, under the same stated philosophy —
hand-editable, the smallest possible thing, and losing any of it costs nothing.

| File | Holds |
|---|---|
| `checked` | one line: the epoch seconds of the last check, a space, and the tag it found (or `-` for a failure) |
| `dismissed` | one line: the version the user said they had seen |

A dismissed version stays dismissed until a newer one appears. Deleting either
file asks again, which is the whole recovery story.

### Cadence

At most one check a day, on the first `GET /api/update` after the stamp goes
stale. Never on a timer, never on a background thread, never blocking
anything: the endpoint answers from cache and refreshes when the cache is old.

### Endpoints

- `GET /api/update` → `{"current": "0.6.0", "latest": "0.7.0", "newer": true,
  "url": "...", "dismissed": false}`
- `POST /api/update/dismiss?version=0.7.0` → records it, origin-checked like
  every other write
- `POST /api/update/open` → opens the release page in the default browser

**`/api/update/open` takes no URL.** The server already knows it, from its own
cached check. A route that opened whatever a caller named would be a way to
make the app launch anything, reachable from any page the window ever renders.
The caller gets to say "open it" and nothing else.

### The CLI

`throughline update` prints the current version, the latest, and whether it is
newer. `--json` for the app and for scripts. It never installs anything and
never opens a browser — the CLI is the tool, and this is the same fact the
window shows.

### The front door

One line under the action, in the existing quiet `sub` style:

> 0.7.0 is available. **What's new** · **Dismiss**

This bends binding rule 1, which says the front door names exactly one action,
and the bend is deliberate. It is not a list of things the user has not done —
it is one fact about the tool, in one sentence, dismissed with one word. That
is the exact shape rule 5 already permits for a stale input, and the same
reasoning applies: mentioned where you are already looking, once, and never
again once you have said you saw it.

Two rules it does not bend: the action stays first and stays the only thing
that looks like an action, and the line is absent unless there is genuinely a
newer version that has not been dismissed.

## What this does not do

- **No downloading and no installing.** "What's new" opens the release page in
  a browser; the human decides.
- **No timer.** Nothing polls. The check happens when the front door is drawn
  and the stamp is a day old.
- **No pre-releases.** `releases/latest` skips them by definition, which is the
  behaviour wanted.
- **No telling you when you are ahead.** Running a build newer than the latest
  release — every developer on master — shows nothing.

## Testing

Every test monkeypatches the fetch. **No test touches the network**, which is
also the assertion that the module fails silently rather than hanging a suite.

**`updates.py`** — `is_newer` across equal, older, newer, differing lengths,
and unparseable tags; `latest()` returning `None` for a timeout, a connection
error, a 404, a 500, non-JSON, and JSON with no `tag_name`; `check()` using the
cache inside a day and refetching outside it; dismissal surviving a reload and
lapsing when a newer version appears.

**The version constant** — one test asserting `__version__` matches
`pyproject.toml`, which is the only thing standing between five bump sites and
a wrong number in the release notes.

**Endpoints** — the payload shape; dismissal storing; both POSTs refused
cross-origin and from a foreign Host; and `/api/update/open` ignoring any URL a
caller tries to supply.

**The mutation check.** Making `latest()` re-raise instead of returning `None`
must break a test. If it does not, the silence this whole design rests on is
not actually pinned.
