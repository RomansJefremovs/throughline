---
name: throughline
description: Use when starting, resuming, or tracking analysis and design work on a repository - runs the artifact pipeline through short interviews and answers "where was I" without reading anything long.
---

# Throughline

An analysis and design pipeline anchored in the repo you are working on.
All state lives in `docs/project/`. All deterministic work is done by the
`throughline` CLI. Your job is the conversation.

## Binding rules

These come from the design spec. Violating one breaks the tool for its user.

1. **Never open with a list of things the user has not done.** Open with
   one next action. Exactly one.
2. **Never hand over a document to review.** Ask one question at a time.
   The artifact accretes from the answers.
3. **Every question goes through the interactive picker.** Use the
   `AskUserQuestion` tool - never ask by writing options as prose. The
   user picks; they do not compose. See "Asking a question" below.
4. **Save every answer immediately** with `throughline answer`. Never
   batch answers to the end of an interview.
5. **Never broadcast staleness.** No counts, no badges, no red. Mention a
   stale input only when the user has already opened that node, in one
   sentence, with a one-word way to dismiss it.
6. **Never load the whole repo.** Use `throughline context <node>` and
   work from what it returns.
7. **Four or five questions per node.** Eight is the hard ceiling, not the
   target. If a node needs more, it should have been split.

## Asking a question

One `AskUserQuestion` call per question. Never batch several questions
into one call - the point is that the user faces one decision at a time.

- **2 to 4 options.** Fewer, sharper options beat a wide menu.
- **The recommended option goes first**, labelled `(Recommended)`.
- **Each option's description says what choosing it commits to** - the
  consequence, not a restatement of the label.
- **"Other" is automatic.** That is the write-it-yourself hatch; do not
  add an option for it.
- **Add "You decide" as an option** when the user could reasonably have
  no opinion. Then pick, and say what you picked and why.
- **The user can always say stop.** Do not spend an option slot on it.

When the user's own answer is better than every option you offered, say
so plainly and record theirs, not yours.

## Question hygiene

Learned from real runs. These are the failure modes:

- **Never ask what the user cannot know from their own head.** Market
  sizing, what competitors do, what users think. If the answer needs
  research, either propose one from the scan and ask only for a yes, or
  drop the question.
- **Never ask what to exclude before anything has been decided.** A
  delimitation question at the start of a node gets "I don't know", and
  deserves to. Ask it last, or not at all.
- **A question the code already answers is not a question.** Read the
  code, state the finding, ask for a correction.
- **Two options that differ only in wording are one option.** Cut one.
- If the user answers "I don't know" twice in a node, the questions are
  wrong. Stop asking, propose the rest, and let them correct.

## Commands

Run every command with `--repo <path>` pointing at the target repository,
and `--json` when you need to parse the result.

- `throughline init --project NAME --flag has_db=true` - create the pipeline
- `throughline nodes` - active nodes and their status
- `throughline status` - where the user left off plus the one next node
- `throughline next` - just the next node id
- `throughline context <node>` - the scoped context for a node
- `throughline answer <node> <question-id> <answer>` - persist one answer
- `throughline write <node> --summary S --body-file PATH --note N` - write the artifact

**Always use `--body-file`.** Write the body to a scratch file first, then
point at it. An artifact body is markdown full of brackets, pipes and
newlines; passing that as a shell argument gets word-split before the CLI
ever sees it. `--body` exists only for one-line bodies.
- `throughline write <node> ... --drafted` - write it as a draft instead
- `throughline confirm <node>` - promote a drafted node to current
- `throughline stale <node>` - check one node against its inputs
- `throughline scan` - raw material from an existing repo

### Task commands

- `throughline task new "TITLE" --origin ticket --reference TRELLO-14` - start one
- `throughline task list` - tasks, newest first
- `throughline task answer <slug> <node> <question-id> <answer>` - persist one answer
- `throughline task write <slug> <node> --summary S --body-file PATH` - write the artifact
- `throughline task context <slug> <node>` - the scoped context for a task node
- `throughline task abandon <slug>` - drop it without finishing
- `throughline task reopen <slug>` - pick it back up

### Two-sided commands

- `throughline target on` / `throughline target off` - the per-repo switch
- `throughline gaps` - differences between the sides, computed on the spot
- `throughline promote <node> "<gap title>"` - turn one gap into a task

### Setup commands

- `throughline detect` - what the repo is wired to. Works before `init`
- `throughline init --project NAME --task-only` - track a repo for tasks only
- `throughline setup --summary S --body-file PATH` - write `setup.md`

## Repo setup

Not every repo deserves twelve nodes. A client repo where the work is
fixing what someone else specified needs four things, once:

| Records | Why |
|---|---|
| **What this is** | one paragraph, so a cold session knows where it is |
| **Vocabulary** | the highest-value part - their words, not yours |
| **How to run it** | launch, test and verify commands |
| **What it is wired to** | MCP servers, issue tracker, CI, launch configs |

**Run `throughline detect` first and never ask what a file already
answers.** It reads MCP server declarations, launch configs, CI workflows
and the obvious run and test commands. Present what it found and ask only
for corrections and for the parts no file can answer - the vocabulary
above all.

**The commands it reports are guesses.** Say so when you show them.

**The fourth row is the one that changes daily use.** A repo with a ticket
integration means the task flow pulls the ticket rather than asking for a
paste, and that only happens because setup went looking.

**`--task-only` means no project pipeline at all.** No nodes, no
architecture questions, nothing about the system as a whole. Ask which the
user wants when first pointing at a repo, once.

**Setup is optional and can come later.** A task runs perfectly well
without it. Offer setup when a repo turns out to be worth it - the second
or third task in - rather than demanding it up front.

## Two sides

A project node can describe two things: **what is true today**, and **what
should be true**. Write them as two top-level sections, in this order:

```
# Current

What the code actually does.

# Target

## One change per subsection

What should be true instead, and why.
```

**Each `##` under `# Target` is one gap.** Write them so that is true -
one change per subsection, with a title someone could act on. Anything
that is not a change to make ("not changing", "already correct") belongs
on the current side or after both sections, never under Target.

**The target side is a switch, not a consequence of ownership.** It is set
per repo and changeable at any time. Ownership only suggests the default,
and never decides: proposing where a codebase should go is a perfectly
good thing to do on a repo you do not own, whether to pitch the work or to
argue for it.

| Switch | Nodes |
|---|---|
| on | write both sides |
| off | describe what is, and stop |

**Ask once, at setup, and then leave it alone.** Do not raise it again per
node.

**Gaps are read, never stored.** `throughline gaps` recomputes them from
the artifacts every time. There is no list to maintain and nothing to
mark done.

**Never promote a gap on your own initiative, and never promote several at
once.** One real run produced a dozen gaps in an afternoon; turning those
into tasks automatically is the backlog rule 1 forbids, arriving through
another door. The user picks one, or none.

## Tasks

A project pipeline answers what a system is. A **task** answers one thing
you are changing - a bug, a small feature, a ticket. Four nodes, about ten
minutes, and no architecture questions.

| Node | Produces |
|---|---|
| `understand` | what is being asked, in the user's own words |
| `analyze` | what is actually happening, and why |
| `design` | the change to make, and what it touches |
| `verify` | how you will know it worked |

**Use a task, not the project pipeline, whenever the work is a change
rather than a system.** Running twelve nodes to fix a bug is how this tool
goes unused for most real work.

**Verify is the node that pays for the rest.** Rework is unbilled, so the
proof is agreed before the fix is written. Never skip it because the fix
looks obvious.

**Start from the ticket, and fetch it yourself.** If the repo has an issue
tracker or MCP server, pull the ticket and open `understand` with a
playback of what you think was asked. Never ask the user to paste it. Keep
the original wording in the artifact whatever they correct - it is what a
later argument about scope is settled against.

**A gap is promoted to a task only when the user says so.** Never create a
task from a gap on your own initiative, and never create one per gap. One
run on a real system produced a dozen gaps in an afternoon; promoting those
automatically is the backlog rule 1 forbids, arriving by another door.

**A task that is going nowhere gets abandoned, not left open.** Abandoning
is reversible and costs nothing. An abandoned task stops competing for the
one next-action slot, which is the only reason task status is stored.

## The four node states

| State | Means |
|---|---|
| `empty` | nothing yet |
| `drafted` | **you wrote it from the scan. Nobody has read it** |
| `in_progress` | mid-interview, answers saved, no artifact yet |
| `current` | written, and confirmed by the person whose project it is |

`drafted` is not a lesser `current`. A drafted node is your guess, and it
stays your guess until the user has been through it. Never build on a
drafted node without saying that is what you are doing.

## Starting a project

For a new repo, run `throughline init` after the intake interview sets the
flags.

For an existing repo, run `throughline scan` first, then write every node
with `--drafted` from what comes back. Walk the user through them one at a
time, and run `throughline confirm <node>` when they have been through one
- the interview becomes confirmation, not authoring.

**Never confirm a node on the user's behalf.** Confirming is the moment a
document stops being yours and becomes theirs.

Intake asks about six questions and must establish `has_db`, `has_ui`,
`has_state` and `multi_service`. Finish intake by playing back your
understanding in three or four bullets and correcting it until the user
says it fits. Do not proceed to any node before that playback is accepted.

## Running a node

1. `throughline context <node> --json` and read what comes back.
2. Report in one line what you loaded and how many lines it was.
3. Read the matching file in `questions/` if one exists. Otherwise derive
   at most five questions from the node's purpose.
4. Ask one question at a time through `AskUserQuestion`, following
   "Asking a question" above.
5. After each answer, run `throughline answer`.
6. When the questions are done, write the artifact with
   `throughline write`, including a one-sentence summary and a `--note`
   describing what the user was thinking about. That note is what
   `status` shows next time.
7. Render the diagram if the node's `renders` value is not `markdown`.

## Resuming

Run `throughline status`. Report the "where you left off" line first, then
the single next node. Do not list anything else.

**Check `answered` before asking anything.** `status --json` returns the
question ids already saved for that node. If it is non-empty the node was
interrupted partway through - read those answers out of `pipeline.yaml`,
say in one line what is already settled, and continue at the next
unanswered question.

Never re-ask a question that has an answer. A session dying mid-node must
cost the user nothing, and being asked the same thing twice is the most
visible way to prove it did.
