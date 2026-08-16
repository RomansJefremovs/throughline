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
3. **Every question carries a recommendation** and a one-line reason.
   "Yeah, that one" must always be a valid answer.
4. **Save every answer immediately** with `throughline answer`. Never
   batch answers to the end of an interview.
5. **Never broadcast staleness.** No counts, no badges, no red. Mention a
   stale input only when the user has already opened that node, in one
   sentence, with a one-word way to dismiss it.
6. **Never load the whole repo.** Use `throughline context <node>` and
   work from what it returns.
7. **Eight questions maximum per node.** If a node needs more, it should
   have been split.

## Commands

Run every command with `--repo <path>` pointing at the target repository,
and `--json` when you need to parse the result.

- `throughline init --project NAME --flag has_db=true` - create the pipeline
- `throughline nodes` - active nodes and their status
- `throughline status` - where the user left off plus the one next node
- `throughline next` - just the next node id
- `throughline context <node>` - the scoped context for a node
- `throughline answer <node> <question-id> <answer>` - persist one answer
- `throughline write <node> --summary S --body B --note N` - write the artifact
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
   at most eight questions from the node's purpose.
4. Ask one question at a time. Offer the options, mark one recommended,
   give a one-line reason.
5. Offer these three escape hatches on every question: you decide, let me
   just write it, stop here.
6. After each answer, run `throughline answer`.
7. When the questions are done, write the artifact with
   `throughline write`, including a one-sentence summary and a `--note`
   describing what the user was thinking about. That note is what
   `status` shows next time.
8. Render the diagram if the node's `renders` value is not `markdown`.

## Resuming

Run `throughline status`. Report the "where you left off" line first, then
the single next node. Do not list anything else.
