# Functional requirements

> Two actors, eighteen capabilities and ten hard rules - with no performance figures, because the requirement is fewer steps to work, not fewer milliseconds.

Two actors, eighteen capabilities, ten hard rules — and no performance
numbers, deliberately.

# Actors

| Actor | Does |
|---|---|
| **Developer** | Answers questions, reads artifacts, edits them directly |
| **Claude** | Runs the interview, invokes the CLI, writes the artifacts |

Outside tools — issue trackers, MCP servers, CI, git — are **not** actors.
Claude reaches for them on the developer's behalf.

Keeping Claude as an actor rather than folding it into the system is
deliberate: most of the hard rules below are constraints on what Claude
must and must not do, and they need somewhere to live.

# The core job

**Efficient management of projects — plural — for an ADHD brain.**

The job is not scoped to one repository. Deciding *which* of several live
projects needs attention, and what the one next thing is there, is the job
itself. Answering "where was I and what now" is how that job is performed
inside a single repo; doing it across repos, without the user holding the
set in their head, is what makes it management rather than note-taking.

Everything else — artifacts, diagrams, the app — exists to make that
answer trustworthy.

# Capabilities

All eighteen are in scope. Nothing was struck.

## Built

| # | Capability |
|---|---|
| 1 | Start a pipeline in a repo |
| 2 | Show active nodes and their status |
| 3 | Assemble scoped context for one node |
| 4 | Save an answer the moment it is given |
| 5 | Write an artifact |
| 6 | Detect when a node's inputs have changed |
| 7 | Scan a repo — files, commits, transcripts |
| 8 | Give one next action, never a list |

## Specified, not built

| # | Capability |
|---|---|
| 9 | Task pipelines, many per repo |
| 10 | Two sides per artifact — current and target |
| 11 | Repo setup — vocabulary, how to run it, what tools exist |
| 12 | Promote a gap to a task |

## The app

| # | Capability |
|---|---|
| 13 | Overview across all repos |
| 14 | Switch projects, Obsidian-style |
| 15 | See the node graph |
| 16 | Read artifacts rendered, diagrams included |
| 17 | Edit an artifact in place |
| 18 | Start the next node from the app |

### Risk carried, not cut

**#12 is the capability that can turn artifacts into a backlog.** Running
the pipeline on one real system produced roughly a dozen gaps in an
afternoon; promoted automatically, that is a twelve-item list greeting the
user next morning — exactly what rule 1 forbids.

It stays in scope, and it stays bound to rule 8: promotion is always
explicit.

# Hard rules

Ten. Each one is a thing the system must never do.

| # | Rule | Breaking it causes |
|---|---|---|
| 1 | Never open with a list of undone things — one next action only | The user stops opening it |
| 2 | Never hand over a document to review — one question at a time | The document is not read, so it is not true |
| 3 | Every question goes through the interactive picker | Recall replaces recognition, and answers get thinner |
| 4 | Save every answer immediately, never batch | An interrupted node loses work |
| 5 | Never broadcast staleness — no counts, badges, red | Pressure, then avoidance |
| 6 | Never load the whole repo — only a node's declared inputs | Sessions die mid-node; answers drift to whatever code was read |
| 7 | Four or five questions per node, eight ceiling | The interview outlasts the attention paying for it |
| 8 | Gaps never become tasks automatically | The artifacts become a tracker |
| 9 | Never display an open-task count | Same failure as rule 1, wearing a number |
| 10 | Files stay hand-editable markdown — they are the truth | Two sources of truth, and one of them rots |

**A proposed eleventh — that the app must never become required — was
offered and not adopted.** The app's boundaries are left to be decided in
architecture rather than fixed here.

# Performance, scale, availability

**No figures, and that is a decision rather than an omission.**

The requirement is about getting to work as a UX and process property, not
a measured one. What is being minimised is the number of steps and
decisions between opening the tool and doing real work — not milliseconds.

A screen that loads in fifty milliseconds but asks the user to choose what
to work on **has already failed** the requirement. A slower one that names
the next action has met it.

Two numbers survive, because they bound the interview rather than the
software:

| Figure | Where it is enforced |
|---|---|
| Eight questions per node, hard ceiling | The skill's binding rules |
| About ten minutes for a full task pipeline | The task pipeline spec |
