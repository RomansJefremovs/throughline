# Test cases

> Seventeen cases - seven that the flows work and ten that the tool stays honest - plus one written to fail, because a failing test is how a known bug survives without a tracker.

Seventeen cases: seven that the flows work, ten that the tool stays honest.

**Who runs what.** Claude runs anything provable from files or CLI output
and reports the evidence. You tick only what needs eyes. The manual column
is deliberately short — a long tick-list is the artifact that gets
abandoned on its second run.

Where a rule can be reduced to counting, it is **counted, not judged**.

---

# Flow cases

## TC-1 — Start tracking a repo · Claude

| | |
|---|---|
| **Do** | Point Throughline at a repo with no `docs/project/` |
| **Expect** | It asks once: full project pipeline or task-only. Nothing else is asked first |
| **Then** | `pipeline.yaml` exists; its `flags` match what was answered |
| **Result** | ☐ |

## TC-2 — Work a node · Claude

| | |
|---|---|
| **Do** | Run any node with empty upstreams filled |
| **Expect** | Claude states in one line what it loaded and how many lines |
| **Then** | Between four and five questions, one at a time, each through the picker |
| **Then** | `pipeline.yaml` gains one answer *after each question*, not at the end |
| **Result** | ☐ |

## TC-3 — Find where to work · you

| | |
|---|---|
| **Do** | Open the app cold, with three or more projects tracked |
| **Expect** | It opens on the project you last worked in |
| **Expect** | Exactly one next action is named |
| **Count** | Decisions required before you can start working — **expect 0** |
| **Result** | ☐ |

## TC-4 — Read the record · you

| | |
|---|---|
| **Do** | Open a project, click a node, follow one dependency edge upstream |
| **Expect** | Markdown and mermaid both render; you never see a file tree |
| **Result** | ☐ |

## TC-5 — Correct the record · Claude

| | |
|---|---|
| **Do** | Edit a sentence in `01-problem.md` in a plain text editor. Save |
| **Expect** | The app shows the new sentence with no import or refresh step |
| **Then** | No downstream document changes appearance in any way |
| **Result** | ☐ |

## TC-6 — Run a task · you

| | |
|---|---|
| **Do** | On a repo with a ticket integration, start a task |
| **Expect** | Claude has already fetched the ticket and plays it back |
| **Count** | Times you paste anything — **expect 0** |
| **Then** | Four nodes run: understand, analyze, design, verify |
| **Time** | Start to verified — **target ten minutes** |
| **Result** | ☐ |

## TC-7 — Promote a gap · Claude

| | |
|---|---|
| **Do** | Open an artifact with a target side and promote one gap |
| **Expect** | A task directory appears, naming the artifact and sentence it came from |
| **Then** | The task starts at *analyze* — understand is already answered |
| **Then** | No gap anywhere becomes a task without you saying so |
| **Result** | ☐ |

---

# Rule cases

## TC-R1 — One next action · Claude

| | |
|---|---|
| **Do** | Run `throughline status` on a project with six empty nodes |
| **Count** | Node names in the output — **expect 1** |
| **Result** | ☐ |

## TC-R2 — One question at a time · you

| | |
|---|---|
| **Do** | Run any node start to finish |
| **Expect** | You are never handed a document and asked to review it |
| **Count** | Questions asked in a single message — **expect 1, always** |
| **Result** | ☐ |

## TC-R3 — Always the picker · Claude

| | |
|---|---|
| **Do** | Read back a full node transcript |
| **Count** | Questions asked as prose with options written out — **expect 0** |
| **Result** | ☐ |

## TC-R4 — Answers saved immediately · Claude

| | |
|---|---|
| **Do** | Answer question 2 of 5, then kill the session |
| **Expect** | `pipeline.yaml` already contains answers `q1` and `q2` |
| **Result** | ☐ |

## TC-R5 — Staleness is never broadcast · you

| | |
|---|---|
| **Do** | Edit an upstream artifact, then look at every screen |
| **Count** | Badges, red marks, or numbers indicating stale work — **expect 0** |
| **Then** | Open one affected document: one sentence, dismissable in a word |
| **Result** | ☐ |

## TC-R6 — Never load the whole repo · Claude

| | |
|---|---|
| **Do** | Run `throughline context <node>` on a large repo |
| **Expect** | Only the node's declared deps plus the glossary |
| **Count** | Source files read before a question was asked — **expect 0** |
| **Result** | ☐ |

## TC-R7 — Question ceiling · Claude

| | |
|---|---|
| **Do** | Count questions in each completed node |
| **Expect** | Four or five typical; **never more than eight** |
| **Result** | ☐ |

## TC-R8 — No automatic promotion · Claude

| | |
|---|---|
| **Do** | Complete a project pipeline that records a dozen gaps |
| **Count** | Tasks created without you asking — **expect 0** |
| **Result** | ☐ |

## TC-R9 — No open-task count · you

| | |
|---|---|
| **Do** | With several unfinished tasks, look at every screen |
| **Count** | Places showing how many tasks are open — **expect 0** |
| **Result** | ☐ |

## TC-R10 — Files are the truth · Claude

| | |
|---|---|
| **Do** | Close the app. Edit an artifact in Notepad. Reopen |
| **Expect** | Your edit is present and was not overwritten |
| **Then** | Delete the app's own config. Artifacts are still readable markdown |
| **Result** | ☐ |

---

# TC-8 — Resume after a dead session · Claude · **fixed**

| | |
|---|---|
| **Do** | Answer 2 of 5 questions in a node. Kill the session. Start a new one |
| **Expect** | Status names the questions already answered, so the interview resumes at question 3 |
| **Expect** | "Where you left off" describes *this* node, partway through |
| **Result** | ☑ passing |

Written first as known-failing, then fixed. Observed output:

```
Where you left off
  Mid-interview on Problem statement - 2 answers saved.

Next: Problem statement
  already answered: q1, q2
```

**Two fixes were needed, for two different problems:**

1. `status` reports the answers already saved for the next node, and the
   skill must read them before asking anything. *Stops repeated questions.*
2. Every saved answer rewrites the left-off note, so it describes the node
   in progress rather than the last one that finished. *Stops the tool
   looking as though nothing happened.*

The first without the second still leaves a note describing the previous
node. The second without the first still re-asks question one.

**Writing it as a failing case is what made it survivable.** Gaps are
deliberately not stored anywhere, so a test written against intended
behaviour is how a known bug outlives the conversation that found it.
