# Task-only follow-through

Date: 2026-08-18
Status: proposed
Extends: `2026-08-17-add-a-project-from-the-app-design.md`

## Why

Adding a project from the app closed one dead end and revealed the next one.

A repo added as **task work only** lands on a front door with nothing to do.
Observed directly, on a repo added through the new flow:

| Screen | What it says |
|---|---|
| Front door | "Nothing yet - this is the first session." No action button at all |
| Setup | "No setup written yet — ask Claude to set this repo up when it earns it." |
| Tasks | "No tasks in this project yet." |

Three screens, zero actions. "Ask Claude" points outside the app and "start one
when a ticket arrives" offers no way to start one — the same errand the app
exists to remove, one screen deeper than before.

This is specific to task-only repos. A full pipeline resolves `next` to its
first node, so its front door names an action from the moment it is created.
Task-only repos have no nodes, so `next` is null until a task exists, and
nothing in the app can create the first one.

Two CLI capabilities are unreachable from the app: `throughline setup`, which
writes the repo's setup document, and `throughline task new`, which starts a
task from a ticket.

## The position this overturns

`SKILL.md` currently instructs Claude:

> Setup is optional and can come later. A task runs perfectly well without it.
> Offer setup when a repo turns out to be worth it - the second or third task
> in - rather than demanding it up front.

The Setup screen's copy carries the same idea in the phrase "when it earns it".

This design has the front door name setup as the next action whenever it is
missing, which is the opposite. **That is a deliberate reversal, and the skill
and the screen copy change with it.** Leaving both positions in place is the
one option not on the table: the app would demand setup while the skill told
Claude to defer it, and a user following the app would be argued with by the
assistant the app just handed them to.

## What changes

Three endpoints' worth of server work, one new screen, and two documents whose
stated position moves.

### 1. The front door gains two states, for task-only repos only

| State | Action | On press |
|---|---|---|
| No setup | **Set this repo up →** | hands to Claude in that repo |
| Setup, no task | **Start a task →** | opens the start-a-task screen |
| Task in flight | **Continue: Understand →** | unchanged |

Full-pipeline projects are untouched. Their front door already names the next
node and keeps doing exactly that.

### 2. `/api/project` reports whether setup exists

The front door has to choose between two actions, so it needs one fact it
cannot currently see. `has_setup` joins `task_only` and `target_side` in the
project payload.

This is a property of the repo, not a count of outstanding work, so it does not
cross rule 9. It says a document exists; it never says one is missing, owed, or
overdue, and nothing renders a number from it.

### 3. `/api/start` gains a `setup` flag

```
POST /api/start?repo=&setup=1
```

Sent instead of `node`, not alongside it. A request carrying both is refused
rather than guessed at, so the two hand-offs can never be confused for one
another.

Handing a repo to Claude for setup is the same act as handing it over for a
node, so it belongs to the endpoint that already does that. `/api/start`
already resolves the repo through the registry allow-list, already spawns a
detached console so the session outlives the app, and already reports a missing
`claude` binary as a real error rather than a silent failure.

The flag carries no caller-supplied text into the prompt. Node ids are checked
against the graph precisely because they reach a process argument; a fixed
setup prompt has nothing to check, which makes this strictly the safer of the
two paths already in that function.

The prompt tells Claude to use the throughline skill and set the repo up. The
skill's own setup section then governs what it does — run `throughline detect`
first and never ask what a file already answers.

### 4. `POST /api/task` creates a task from a ticket

```
POST /api/task?repo=&title=&reference=
```

Mirrors `tasks.create(origin="ticket")`, exactly as `/api/promote` already
mirrors it for `origin="gap"`. Returns the slug.

Creating a task is not an interview — it is one line the user is already
looking at on a ticket — so this is the app's to do, unlike setup. The work
that follows is still Claude's: on success the app reopens the project, the
front door reads **Continue: Understand →**, and the next click hands over.

`title` is required and trimmed. A blank or whitespace-only title is refused and
creates nothing. `reference` is optional and stored as given.

### 5. A start-a-task screen

A new `"starting"` entry in `SCREENS`, following the `adding` screen added by
the previous design, so it takes part in back and forward like every other
screen.

```
START A TASK
Sales

Title      [ Fix VAT on credit notes            ]
Reference  [ ERP-4821                 ]  optional

                        [ Start task ]  [ Cancel ]
```

Two fields. An empty title is caught client-side before any request, the same
way the folder field already is.

### 6. The Setup screen keeps its own action

When no setup document exists, the Setup screen offers **Set this repo up →**
as well. The front door stops offering it the moment setup exists, and without
this there would be no way to reach it again.

Its copy loses "when it earns it", which is the sentence encoding the position
being reversed.

## Errors

| Condition | Says |
|---|---|
| Empty title | Give the task a title. |
| `claude` not installed, on setup | The existing "Could not open Claude" path, unchanged |
| Task created but the reopen fails | The task exists; say so rather than resetting silently |
| Anything else | The server's own message, verbatim |

## Testing

Server-side, in the existing behavioural style:

- `has_setup` is true only when the document is on disk, and false otherwise
- `/api/task` creates a task recorded with `origin="ticket"` and returns a slug
  that resolves
- a blank or whitespace-only title is refused and no task is written
- a reference round-trips onto the task
- `/api/start` with the setup flag spawns Claude in the right repo, and reports
  a missing binary the way node starts already do
- `/api/start` with the setup flag still refuses an untracked repo

## Not in scope

**Rewriting an existing setup document from the app.** Setup is a markdown file
like any other and can be edited by hand. An in-app editor for it is a separate
question from being able to create one at all.

**Changing what setup asks.** The skill's four rows — what this is, vocabulary,
how to run it, what it is wired to — are unchanged. Only *when* it is offered
moves.

**Task-only detection or suggestions.** Nothing here guesses whether a repo
should be task-only; that is chosen when the project is added.
