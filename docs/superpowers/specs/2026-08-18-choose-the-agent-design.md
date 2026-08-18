# Choosing the agent

Date: 2026-08-18
Status: proposed
Extends: `2026-08-18-task-only-follow-through-design.md`

## Why

Every hand-off in Throughline launches Claude Code. One function does it —
`spawn_claude` in `serve.py` — and it is nine lines around `["claude", prompt]`.
Nothing else in the codebase knows what an agent is. The CLI is deterministic
Python, the artifacts are markdown, and the skill drives the conversation
through commands that have no opinion about who is running them.

That makes a second agent cheap, and there is a reason to want one. opencode
runs against any OpenAI-compatible endpoint, including a self-hosted vLLM. The
flow it matters most for is documenting an existing repo: `throughline scan`
followed by one `write --drafted` per node is pure analysis with no interview,
and it is the longest and most token-hungry thing the tool does.

## What was verified, not assumed

Three things had to be true for this to be worth building. Each was checked
against the installed opencode 1.18.12 binary rather than its documentation.

**opencode reads Claude Code's skill directory.** `opencode debug skill`
returned every user skill on this machine, each resolving to
`C:\Users\<user>\.claude\skills\<name>\SKILL.md`. The skill pack needs no
porting, no duplicate copy and no second format.

**opencode has a picker, and it is nearly the same shape as
`AskUserQuestion`.** From the binary's own schema:

| `AskUserQuestion` | opencode `question` | Difference |
|---|---|---|
| `question` | `question` | none |
| `header`, max 12 chars | `header`, max 30 chars | 12 is safe on both |
| `options[].label` | `options[].label` | both documented "1-5 words" |
| `options[].description` | `options[].description` | none |
| `multiSelect` | `multiple` | name only |
| "Other" is automatic | `custom`, defaults true | opencode can switch the hatch off |

Answers arrive as `{answers: [[...]]}` — an array of strings per question, in
the order asked. `questions` is an array on both, so both can batch several
questions into one call, and binding rule 3 forbids that on both.

**The picker is behind a feature flag.** The binary registers the builtin tool
list as `...ro?[H.question]:[]`, where `ro` is
`enableQuestionTool: k("OPENCODE_ENABLE_QUESTION_TOOL")`. Unset, the tool does
not exist.

`opencode debug agent build` prints `"question": true` whether or not the flag
is set. That line is a permission default and is **not** evidence the tool is
live; the two outputs are byte-identical with the flag on and off.

So the spawn sets `OPENCODE_ENABLE_QUESTION_TOOL=1`. Without it, binding rule 3
has no tool to bind to and every interview silently degrades to prose, which is
the exact failure the rule exists to prevent.

## The gap this also closes

**The throughline skill is installed nowhere.** `~/.claude/skills/` holds 55
skills on this machine and `throughline` is not among them. Only the
`superpowers` plugin is enabled. Nothing in `build-installer.ps1`, the CLI or
the desktop shell copies `skills/throughline/` anywhere, and a `skills/`
directory at a repo root is not a location any agent discovers.

The app's hand-off therefore opens a session in the target repo and says *"Use
the throughline skill"* to an agent that has never heard of it. The button was
verified to spawn; the session on the other end was never verified to be able
to act on the prompt.

That is a separate bug from choosing an agent, and it is folded in here because
the fix is the same directory for both agents and because an agent switch is
worthless while neither agent can follow the prompt.

## Design

### The setting: `~/.throughline/agent`

One line, the word `claude` or `opencode`, newline. It sits beside
`projects.txt` under the same stated philosophy: hand-editable, the smallest
possible thing, and losing it costs a re-pick and no content. Not JSON.

`THROUGHLINE_HOME` already redirects that directory, so tests get isolation
without new plumbing.

The choice is global, per machine. Which agent is installed is a property of
the machine, not of a repo — and `pipeline.yaml` is committed, so a per-repo
setting would push one person's choice onto a teammate who may not have that
agent at all.

### The module: `src/throughline/agents.py`

A table, not a class hierarchy:

```python
AGENTS = {
    "claude": lambda prompt: ["claude", prompt],
    "opencode": lambda prompt: ["opencode", "--prompt", prompt],
}

ENVIRONMENT = {
    "opencode": {"OPENCODE_ENABLE_QUESTION_TOOL": "1"},
}
```

`claude` takes its prompt positionally; `opencode` takes `--prompt` and gets
the repo from the working directory, which the spawn already sets. Only
opencode needs an environment addition, and the table says so rather than the
spawn carrying a special case.

Four functions:

- `installed()` — `shutil.which` over the table, in table order
- `chosen()` — read the setting file; `None` when absent, empty, or naming
  something not in the table
- `choose(name)` — write it, refusing any name not in the table
- `command(name, prompt)` — the argv and the environment overlay

An unreadable or unrecognised setting file counts as *unset* rather than as an
error, matching how `registry.py` treats a missing registry as an empty list
rather than a failure.

### Resolution at hand-off

`spawn_claude` becomes `spawn_agent(repo, prompt, name)`. It keeps
`CREATE_NEW_CONSOLE` and keeps the property its comment exists to protect: the
session outlives the app, and closing the app never kills work in progress.
Only argv and environment change.

`_post_start` resolves before spawning:

| State | Response |
|---|---|
| chosen, and on PATH | spawn it |
| chosen, not on PATH | 500, naming the agent and the setting file |
| nothing chosen, one installed | spawn it, and store that choice |
| nothing chosen, both installed | 409 `{"choose": ["claude", "opencode"]}`, no spawn |
| nothing installed | 500, naming both |

The 409 is what makes "ask once" possible without the server ever blocking on a
human. The app turns it into one picker, POSTs the answer, and repeats the
start. Every hand-off afterwards skips it.

Storing the choice when only one agent is installed is deliberate: it means the
common case never asks anything, and a later second install does not silently
change which agent gets the work.

### Endpoints

- `GET /api/agent` → `{"chosen": "claude" | "opencode" | null, "installed": [...]}`
- `POST /api/agent?name=opencode` → stores it, returns the same shape

`POST` is origin-checked and Host-checked by the existing guards in `route()`,
like every other endpoint that writes.

On the CLI: `throughline agent` prints the current choice and what is
installed; `throughline agent opencode` sets it. The CLI is the tool and the
window is a view onto it, so neither gets a capability the other lacks.

### The skill install

`build-installer.ps1` already carries `src/throughline/app` into the frozen exe
with one `--add-data` line. One more line carries `skills/throughline` to
`throughline/skill`, and `Path(__file__).parent / "skill"` resolves it in both
frozen and source runs — exactly the trick `ASSETS` uses today.

`throughline skill install` copies the pack to `~/.claude/skills/throughline/`.
One destination serves both agents.

The hand-off checks before spawning. No `SKILL.md` at the destination, and it
installs the pack and says so in the response. Every file present and
byte-identical to the bundled pack, and it does nothing.

**Present but differing in any file, and it leaves the destination alone and
reports it.**
`--force` exists for the user's decision. This is the same stance `write` takes
when an artifact has been edited since the tool last wrote it: someone else's
words are the truth, and clobbering a skill somebody had tuned is the same
failure as clobbering their sentences. A stale skill is a real problem, but it
is a problem the user gets told about rather than one solved behind their back.

### SKILL.md

Binding rule 3 names `AskUserQuestion` and nothing else, so on opencode it
reads as unfollowable. It must name both tools and keep the rule identical:
one call per question, 2 to 4 options, recommended first, never prose.

The `header` limit becomes 12 characters for both — the stricter of the two,
so a question written once works under either agent.

Nothing else in the skill is Claude-specific. Every command is `throughline`.

## What this does not do

- **No per-repo override.** Global only.
- **No model selection.** Which model opencode points at is opencode's config,
  not Throughline's business.
- **No change to any artifact, node or pipeline.** An agent switch that changed
  the documents would be a different feature.
- **It adds no silent default.** With both agents installed and nothing
  chosen, the hand-off asks rather than picking. Table order matters only to
  the mutation check below.
- **It does not promise the skill works as well on another model.** The switch
  makes the tool reachable; whether a given model honours seven binding rules
  is a quality question no amount of argv can answer. The drafting flow, which
  needs no picker at all, is the one with the least to lose.

## Testing

Every test uses `THROUGHLINE_HOME` pointed at a temporary directory, as the
registry tests already do.

**`agents.py`** — `installed()` with each agent present, both, neither;
`chosen()` for absent, empty, valid and garbage files; `choose()` refusing an
unknown name; `command()` producing the right argv for both and the
`OPENCODE_ENABLE_QUESTION_TOOL` overlay for opencode only.

**Resolution** — one test per row of the table above, with `spawn_agent`
monkeypatched, asserting the response and whether a spawn happened. The 409
must assert that nothing was spawned, since a spawn there would open a session
in someone's repo under an agent they had not picked.

**Endpoints** — `GET` shape; `POST` storing; `POST` refusing an unknown name;
`POST` refused from another origin and from a non-loopback Host, alongside the
existing tests for `/api/add` and `/api/init`.

**Skill install** — into an empty destination; a no-op when identical; refused
and reported when different; overwriting under `--force`. Plus one test that
the bundled pack is findable from the source tree, which is what
`test_skill_pack.py` already asserts about the repo copy.

**The both-installed refusal is the mutation check.** Removing the 409 branch
so resolution falls through to `claude` must make a test fail. If it does not,
the test is decorative.
