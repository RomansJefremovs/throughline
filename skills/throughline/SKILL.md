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
- `throughline stale <node>` - check one node against its inputs
- `throughline scan` - raw material from an existing repo

## Starting a project

For a new repo, run `throughline init` after the intake interview sets the
flags. For an existing repo, run `throughline scan` first, draft every node
from what comes back, then walk the user through confirming them - the
interview becomes confirmation, not authoring.

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
