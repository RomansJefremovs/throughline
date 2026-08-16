# Throughline — design

Date: 2026-08-16
Status: approved, ready for planning

## Problem

Work on a project is spread across Claude Code sessions, git history, and whatever files happen to exist. Coming back to a project after a break means re-deriving what was decided and why. Four specific failures:

1. **Losing the thread** — decisions exist in transcripts but are unfindable.
2. **No overview** — no view of what is in progress, blocked, or done.
3. **Scattered artifacts** — nothing links idea to spec to plan to commit.
4. **No visual layer** — designing happens in walls of prose.

Underneath all four is a harder constraint: the user has ADHD. Anything that requires reading a long document, manual upkeep, or deciding what to work on will be abandoned. This is the primary design constraint, not a nice-to-have.

## What this is

A pipeline of analysis and design artifacts, anchored inside a repository, produced through short interviews rather than document generation. Adapted from VIA University College's "From Requirements To Code" method (Ib Havn, 2019), trimmed for solo work.

Not an Obsidian clone. Not a general-purpose markdown editor. The markdown editing part is deliberately out of scope — the user's existing editor already does it.

## Design principles

These are binding. Any implementation decision that violates one is wrong.

1. **The app never opens with a list of things you have not done.** It opens with one thing you can do. Every status signal must justify itself against this.
2. **Never hand over a document to review.** Hand over one decision at a time. The document accretes as a byproduct, so the user is always its author.
3. **Recognition over recall.** Multiple choice with a recommendation beats a blank page. "Yeah, that one" must always be a valid answer.
4. **Every node ends in something you can look at.** A diagram, not a status change.
5. **Interruption is free.** Answers persist immediately. Stopping mid-node never loses work.
6. **No manual upkeep.** All status is derived from file content and git. Nothing is dragged or typed.
7. **Small context.** Each node reads only its declared dependencies, never the whole repo.

## Approach

Hybrid: the pipeline owns graph state and structure; Claude Code does the thinking. Conversational nodes run in the Claude Code desktop app, which is where the user already works.

**Everything through milestone 5 is a skill pack plus a folder convention, with no application.** Claude Code can already read and write the convention, so the whole system is usable before any UI exists. A GUI is deferred until the convention proves itself in real use.

Rationale: the read-only, convention-first path can only produce markdown and YAML in the repo, so a failed experiment costs a docs folder rather than a codebase. It also tests the core thesis — that a structured artifact graph makes re-entry cheap — at a fraction of the cost of testing it through an app.

## File layout

Artifacts live in a **visible** folder, not hidden like `.claude`:

```
docs/project/
  pipeline.yaml        # node state: active, status, upstream hashes
  glossary.md          # domain model, injected into prompts
  01-problem.md
  02-requirements.md
  03-use-cases.md
  ...
```

Visible because it is readable on GitHub, reviewable in a pull request, and discoverable by Claude Code without instruction. Hidden folders are for tool state; this is the user's actual thinking.

**Node definitions are global, node state is per-repo.** The pipeline itself — which nodes exist, their dependencies, their questions — lives once in the skill pack. `pipeline.yaml` holds only this project's state. This boundary makes the pipeline reusable across repos and productizable later.

Everything except `pipeline.yaml` is hand-editable markdown. If the tooling is abandoned, what remains is a clean docs folder, not a dead proprietary format.

## The node graph

Nodes are grouped into four phases: problem, analysis, design, code.

### Always active

| Node | Phase |
|---|---|
| Problem statement | Problem |
| Functional requirements | Analysis |
| Use case diagram | Analysis |
| Use case descriptions | Analysis |
| Domain model (glossary) | Analysis |
| Test cases | Analysis |
| Architecture | Design |

### Conditional

| Node | Activates when | Kind |
|---|---|---|
| ER / relational model | `has_db` | flag |
| State machine | `has_state` | flag |
| Deployment | `multi_service` | flag |
| Activity diagram | The user adds it for a specific flow | on demand |
| Sequence diagram | The user adds it for a specific interaction | on demand |

Two activation kinds. **Flag** nodes resolve automatically from intake answers. **On demand** nodes cannot be decided at intake, because whether a flow is worth diagramming is only knowable once that flow exists — they stay off until explicitly added to a named flow or interaction, and one project may have several instances of each.

Conditional nodes that do not apply are **invisible**, not greyed out.

### Cut from the original method

System sequence diagram, risk assessment, time schedule. These serve academic assessment, not solo delivery. Progress tracking replaces the time schedule.

### Node declaration

Each node definition declares four things:

- **`deps`** — upstream artifacts to load. This is the token budget.
- **`when`** — the activation condition, evaluated against intake flags.
- **`asks`** — interview questions, each with a recommended default.
- **`renders`** — output form: mermaid class diagram, ER, flowchart, or plain markdown.

The domain model is the highest-value node. It is the project's vocabulary and is injected into every subsequent prompt, which is what stops each session from re-deriving the project's own nouns.

## Intake

Runs once per project, before any pipeline node.

1. **Point at a repo** — new or existing.
2. **Scan** (existing repos only) — source structure, README, `CLAUDE.md`, git log, and prior Claude Code session transcripts for that repo. Transcripts are stored per project as JSONL and carry `cwd`, `gitBranch`, `timestamp`, `sessionId`, `parentUuid`, and message content, which is enough to recover past decisions and their reasoning.
3. **Intake interview** — roughly six questions establishing purpose, users, and the conditional flags (`has_db`, `has_ui`, `has_state`, `multi_service`).
4. **Playback** — the agent states its understanding in a few bullets; the user corrects it. This repeats until it fits. Playback is the synchronisation mechanism, and it is the step that prevents a plausible-but-wrong understanding from propagating downstream.
5. **Pipeline shaped** — conditional nodes resolve; only applicable nodes become visible.

## Bootstrap (existing repos)

For an existing repo the scan drafts **every** node at once, pre-filled as proposals. The interview then becomes confirmation rather than authoring: "I found Clip, Campaign and Cover as core entities, and Cover looks like part of Clip — right?"

- The glossary comes out first and nearly free, since the code already contains the vocabulary.
- The scan is a single bounded pass. Subsequent nodes read only their declared dependencies.
- Inferred-but-unconfirmed nodes are **not** flagged. Instead, `/next` orders unconfirmed upstream nodes ahead of downstream ones. Ordering does the work that alarms would otherwise do.

## Node interview

Invoked as `/node <name>` or `/next`.

1. **Context assembly** — load only the node's declared dependencies plus the glossary.
2. **Interview** — one question at a time. Mostly multiple choice. Every question carries a recommendation and a one-line reason.
3. **Persist per answer** — every answer is written to disk as it is given, not batched at the end. Resuming reports "you were on question 4 of 6".
4. **Render** — markdown plus a mermaid diagram is written to `docs/project/`; the node becomes current.

### Escape hatches

Every question offers all three:

- **"You decide"** — the agent picks and explains, and the user reacts rather than deciding cold.
- **"Let me just write it"** — for when the answer is already formed and questions are friction.
- **"Stop here"** — ends the node with no loss.

### Sizing

A node interview must not exceed roughly eight questions. Nodes that would exceed it split — functional requirements becomes one node per feature area. Four finished small nodes beat one abandoned large one.

### On-screen elements

The interview surface shows: node name, `N of M` progress, a one-line statement of what context was loaded and how large it is, the question, options with exactly one recommended, the three escape hatches, and a note that stopping loses nothing.

## Staleness

Each node stores a hash of its upstream artifacts. When upstream content changes, downstream nodes are internally marked stale.

**Staleness is computed but never broadcast.** Specifically:

- No red, no counts, no badges. A "7 stale" indicator is debt-shaped and produces avoidance.
- Stale nodes never auto-regenerate.
- Staleness surfaces **just in time**: when the user opens a node whose upstream has changed, one sentence appears offering a diff.
- Dismissal is one click. "Still fine" is always available. Debt only feels heavy when clearing it is expensive.
- The full graph view is opt-in and never presented unprompted.

This produces an honest three-state status — empty, current, stale — derived entirely from file content, with nothing to groom.

## Status view

`/status` shows, in order:

1. Project name, time since last work, commits since.
2. **"Where you left off"** — one sentence. This is the primary feature.
3. **Exactly one next node**, with questions remaining and an estimate, and a single control to continue.
4. A compact progress strip: one bar per node, grouped by phase, filled or empty. Progress only — no warnings.
5. An opt-in link to the full graph.

No list of outstanding items appears anywhere in this view.

## Build order

| # | Milestone | Size |
|---|---|---|
| 1 | Pipeline definition and file format — node list, dependencies, `docs/project` schema | small |
| 2 | One node end to end — interview, artifact and diagram on disk | medium |
| 3 | `/status` and `/next` — the graph and the memory jog | small |
| — | *Useful from here on* | |
| 4 | Bootstrap an existing repo — pre-fill from code, git and past sessions | medium |
| 5 | Staleness and just-in-time diffs | small |
| — | *Only build the following if the above earned it* | |
| 6 | The application — ambient view, all repos at once, canvas | large |

Milestones 1–5 require no application and no installation beyond the skill pack.

### Validation

After milestone 5, bootstrap an existing project and spend roughly twenty minutes confirming the drafted nodes. The test: does the resulting glossary and use case set make the next working session on that project measurably cheaper to re-enter? If yes, milestone 6 is justified. If the tool goes unused for two weeks, it is not, and the cost of learning that was days rather than weeks.

## Non-goals

- A markdown editor. The user's existing editor is not being replaced.
- Replacing or embedding the Claude Code desktop app.
- Multi-user, sync, or hosting.
- Gamification — streaks, points, badges. Progress is the real work, not an invented metric.
- Any status display that resembles a backlog or an inbox.

## Productisation

Built single-user. Kept productisable by two boundaries: node definitions are separate from node state, and repository access, configuration, and Claude Code invocation stay behind their own interfaces. No further accommodation for future users is made now.
