# Use case descriptions

> Seven flows, each short on purpose - and drafting from an existing repo is bounded by a token budget rather than by reading the code.

Seven flows. Each one is short on purpose — a use case that needs a page
of steps is a use case that will not be followed.

# UC1 — Start tracking a repo

**Trigger:** the user points Throughline at a folder.

| # | Step |
|---|---|
| 1 | Claude asks, once: full project pipeline, or task-only |
| 2 | `throughline scan` runs — file names, recent commits, README |
| 3 | For a full pipeline: intake, then a drafted first pass of every node |
| 4 | For task-only: vocabulary, how to run it, what tools exist. Nothing else |
| 5 | `throughline init` writes `docs/project/pipeline.yaml` |

**Ownership is never inferred.** Git remote and commit authorship are not
consulted. Ownership may suggest a default; it decides nothing.

## Drafting is bounded, and the bound is a token budget

The user rejected "read the codebase and draft from it" on cost grounds,
correctly. The real costs:

| Approach | Roughly | Yields |
|---|---|---|
| Read the whole repo | 10,000+ lines | Everything once, then a dead session |
| `throughline scan` | ~200 lines | Structure and vocabulary, not decisions |
| Targeted read while answering | 1–2 files | The one fact the question needs |

**So: scan cheaply, draft structure from that, and read individual source
files only when a specific question needs a specific fact.** On Scissors
Farm, `db.py` was read to answer the schema question — not to "understand
the project".

**This extends rule 6 to source code.** The rule currently governs
artifacts only. It should read: never read the repository to understand
it, only to answer a question that has already been asked.

# UC2 — Work the next node

**Trigger:** the user clicks the next node, or asks Claude directly.

| # | Step |
|---|---|
| 1 | `throughline context <node>` returns the node's declared inputs |
| 2 | Claude reports in one line what it loaded and how long it was |
| 3 | Four or five questions, one at a time, through the picker |
| 4 | Each answer is saved the moment it is given |
| 5 | `throughline write` produces the artifact, a summary and a note |
| 6 | A diagram is rendered if the node calls for one |

## Alternate — the dependency is empty

The user wants architecture today; requirements is untouched.

**Claude offers to do the prerequisite first.** If declined, the node runs
on whatever context exists and records in one line which input was missing.

This does not contradict the zero-decisions rule. That rule governs the
*front door*, where nothing has been chosen yet. Jumping ahead is itself a
deliberate choice, so one follow-up question there is not a cold start.

## Alternate — the session dies

Answers survive; the conversation does not. Covered in the use case
diagram. On resume, status hands back the answers already given and the
interview continues at the next unanswered question.

# UC3 — Find where to work

**Trigger:** opening the app.

| # | Step |
|---|---|
| 1 | The app opens on the project last worked in |
| 2 | One next action is named. No list, no choosing |
| 3 | Optionally, a click reaches the overview — state only, across all repos |
| 4 | Entering a project from the overview lands in step 1 |

**Steps 3 and 4 are optional and never automatic.** The overview does not
greet anyone.

# UC4 — Read the record

**Trigger:** the user wants to know what was decided, and why.

| # | Step |
|---|---|
| 1 | Open a project; the node graph is the map |
| 2 | Open an artifact; markdown and diagrams render |
| 3 | Follow a dependency edge to the artifact upstream of it |

The graph is the navigation. There is no separate file tree to learn.

# UC5 — Correct the record

**Trigger:** a sentence is wrong.

| # | Step |
|---|---|
| 1 | Edit it in place, in the app or in any text editor |
| 2 | It saves as markdown. That file is the truth |
| 3 | Nothing visible happens to the documents built on it |
| 4 | Next time one of those is opened, one sentence notes the changed input |
| 5 | One word dismisses it |

# UC6 — Run a task

**Trigger:** a ticket arrives.

| # | Step |
|---|---|
| 1 | Claude pulls the ticket using whatever integration setup recorded |
| 2 | It plays back what it thinks was asked; the user corrects it |
| 3 | **Understand** — what is being asked, in the user's terms |
| 4 | **Analyze** — what is actually happening, and why |
| 5 | **Design** — the change, and what it touches |
| 6 | **Verify** — how you will know it worked |

**No paste step.** On a repo with a Trello MCP, Claude fetches the card
itself and Understand opens already half-answered.

**The original ticket text is kept** alongside the user's correction, so
the client's own wording survives a later argument about scope.

Where no integration exists, the user supplies the text and everything else
is identical.

# UC7 — Promote a gap to a task

**Trigger:** the user decides an observation is now work.

| # | Step |
|---|---|
| 1 | While reading an artifact, the user picks a recorded gap |
| 2 | A task is created, inheriting that artifact as context |
| 3 | Understand is already answered, so the flow starts at Analyze |

**Always explicit.** No gap becomes a task on its own — the pipeline run on
one real system produced roughly a dozen gaps in an afternoon, and
promoting those automatically is precisely the list rule 1 forbids.
