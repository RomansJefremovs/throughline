# Task pipelines and two-sided artifacts

Date: 2026-08-16
Status: proposed
Extends: `2026-08-16-project-pipeline-design.md`

## Why

Two gaps surfaced during the first real run, on Scissors Farm.

**The target state kept leaking out unstructured.** Requirements ended with a
"required change". Architecture ended with "known structural debt". Two test
cases were written to fail on purpose. Every node was quietly producing two
things — what is, and what should be — with no place to put the second.

**The pipeline is far too heavy for small work.** Most work is not "analyse a
system"; it is "fix this bug in a client repo". Running twelve nodes to fix a
bug is absurd, so the tool would simply go unused for the majority of real work.

## What changes

Three additions. Nothing in the existing design is removed.

### 1. Pipeline kinds

There are now two kinds of pipeline.

| Kind | Count | Answers |
|---|---|---|
| `project` | one per repo | what this system is |
| `task` | many per repo | one thing you are changing |

Node definitions stay global and data-driven, so a second kind is mostly new
data rather than new machinery.

### 2. Two-sided artifacts, and when the second side is skipped

Which sides a node writes depends on one fact recorded at setup: **whose
direction is this?**

| Repo | Sides written | Why |
|---|---|---|
| Owned, existing | Current **and** target | You decide where it goes |
| Owned, new | Target only | There is no current state yet |
| **Not owned** | **Current only** | The direction is not yours to set |

**The target side is skippable, and for client work it is skipped entirely.**
On a repo like Geedie, where the work is fixing bugs and building features
someone else specified, proposing a target state is not analysis — it is
inventing opinions nobody asked for and nobody will act on. The artifact
describes what is, and stops.

Skipping is per repo, decided at setup, and changeable later. A repo that starts
as client work and becomes yours can turn the target side on.

**Where both sides exist, the gap between them is the backlog.** It is computed
from artifacts that already exist, not maintained as a separate list. This is
the link between analysis and project management that the original spec left
open — and it simply does not apply to repos you do not own.

### 3. Repo setup

A lightweight one-time setup per repo, cheaper than the full project pipeline
and sufficient on its own for task work. It records four things:

- **Whose direction is this** — owned, or someone else's. Decides whether the
  target side is written at all. Everything else in the tool follows from it.
- **What this is** — one paragraph
- **Vocabulary** — the mini glossary, the highest-value part
- **How to run it** — launch, test and verify commands
- **What tools exist** — MCP servers, issue tracker, CI, launch configs

The fourth is the one that changes daily use. If a repo has a Trello MCP, the
task flow pulls the ticket rather than asking the user to paste it. Setup should
detect available integrations rather than assume a fixed toolchain.

Setup runs when task work is first requested in a repo. It is not required
first: a task can run with no setup, and setup can be done later once a repo
turns out to be worth it.

## The task pipeline

Four nodes. Target is roughly ten minutes before starting work.

| Node | Produces | Deps |
|---|---|---|
| **Understand** | what is being asked, in the user's own terms | repo setup, ticket if available |
| **Analyze** | what is actually happening, and why | understand, repo vocabulary |
| **Design** | the change to make, and what it touches | analyze |
| **Verify** | how you will know it worked | design |

Each node is an interview of two to four questions, following the existing
rules: interactive picker, one question at a time, a recommendation on every
question, answers saved immediately.

**Verify is the node that pays for the rest.** Rework is unpaid, so deciding the
proof before writing the fix is the point of the whole flow.

### Where tasks live

```
docs/project/
  pipeline.yaml
  glossary.md
  01-problem.md
  ...
  tasks/
    2026-08-16-fix-metrics-display/
      task.yaml
      01-understand.md
      02-analyze.md
      03-design.md
      04-verify.md
```

`tasks/` sits inside the same visible folder. A task directory is named by date
and slug so the list sorts chronologically without a database.

For a repo with no project pipeline, `docs/project/` holds only `setup.md`,
`glossary.md` and `tasks/`.

### Where tasks come from

**Owned repos:** a gap recorded on the target side of any project node can be
promoted to a task. The task inherits the artifact it came from as context, so
"Understand" is already answered and the flow starts at "Analyze".

Promotion is always explicit. Gaps never become tasks automatically — that would
produce exactly the backlog-shaped list of undone work the original spec forbids.

**Repos you do not own:** there are no gaps, because there is no target side.
Tasks come from outside — a ticket, a message, a request — which is why setup
records what the repo is wired to. On a repo with a Trello MCP, "Understand"
pulls the ticket rather than asking for a paste.

This is the common case, not the fallback. Most task work is client work.

## Status and the one next action

The existing rule holds: status shows one next action, never a list.

With tasks in play, the next action is chosen in this order:

1. A task that is in progress
2. The task most recently worked on, if it is unfinished
3. The next project-pipeline node
4. Nothing

An open-task count is never displayed. The task list exists and can be opened
deliberately; it never greets the user.

## Open questions

- Whether a task should be able to declare that it closes a specific gap, so the
  target side can be marked reached when the task finishes. Attractive, but it
  risks turning the artifacts into a tracker.
- Whether repo setup should be a third pipeline kind rather than a special case.
