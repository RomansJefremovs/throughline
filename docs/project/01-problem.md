# Problem statement

> One person, several codebases, no one to ask - and the cost is that managing the work competes with doing it for the same scarce focus.

A single person, several codebases, and no one to ask what was decided.

# Who

One person, working alone, in more than one codebase. Three overlapping
situations, all of them the same person:

| Situation | What is missing |
|---|---|
| Several repos live at once | An overview. Which project needs you, and for what. |
| A repo you do not own | The reasoning. You did not write it and cannot ask why. |
| Coming back after time away | The thread. What was decided, and what it ruled out. |

No team, no handover, no shared wiki. Whatever is not written down is
reconstructed by reading code, or lost.

# What it costs

**The primary cost is management itself.**

For an ADHD brain, project management and delivery compete for the same
scarce resource. Every switch into *managing* — deciding what to work on,
remembering where things stood, keeping a plan current — is focus taken
directly out of *building*. The resource does not divide; it moves.

So the cost is not "management takes an hour a day". The cost is that the
hour comes out of the only hour that produces anything.

Four consequences follow from that:

| Consequence | How it shows up |
|---|---|
| **Unpaid rework** | A decision is forgotten, the wrong thing gets built, the fix is unbilled |
| **Re-derivation** | Reading your own code back to remember why it is like that |
| **Design that never happens** | Analysis is too heavy to start, so the project runs on whatever was in your head that week |
| **Abandonment** | A wall of text or a list of undone work ends the session outright |

The last one is not a figure of speech. The project does not get harder;
it gets dropped.

# How it is coped with today

The AI conversation, plus whatever markdown happened to get written —
`docs/superpowers/specs`, `CLAUDE.md`, memory files — with nothing linking
them to each other or to the code.

This works while the session is warm. It evaporates when the session ends.
The real thread is left in chat transcripts that nobody scrolls back
through, so the next session starts by rebuilding context that already
existed.

# What solved looks like

Three statements, ordered by what can actually be promised.

**Deliverable — you open it and are working within seconds.** One next
action, named. No reading, no deciding what to do first. If this fails it
fails visibly, which is why it is the one to check against.

**Deliverable — nothing about the project lives only in your head.** Every
decision, and the reason for it, is written down and findable.

**The aim those two serve — project management stops being a separate
activity.** It becomes a by-product of conversations that were happening
anyway, never a task with its own name on a list.

The third is the point. The first two are how you would know it happened.

# Scope

No feature is excluded on principle.
