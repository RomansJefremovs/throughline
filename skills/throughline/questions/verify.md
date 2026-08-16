# Verify

Goal: how you will know it worked, decided **before** the fix is written.

**This is the node that pays for the rest.** Rework is unbilled, so
agreeing the proof in advance is the whole point of running a task flow at
all. Never let this node be skipped because the fix "is obvious".

Three questions. Every one goes through `AskUserQuestion`.

Write the result as instructions, not descriptions: **do this, expect
exactly this, tick or do not.**

### Q1: What proves the reported symptom is gone?
Options: two concrete checks drawn from the understand node - the exact
steps the reporter would take, and an automated test if the code allows
one.
Recommend: the reporter's own steps. Reason: they are what acceptance is judged against, whatever the underlying cause turned out to be.

### Q2: What proves nothing else broke?
Options: the existing suite, the specific call sites named in design, and
"nothing else was touched".
Recommend: the call sites from the design node. Reason: they are already written down, so this costs nothing and covers the risk that was actually identified.

### Q3: Who runs each of these?
Options: split so anything checkable from files or commands is automated
and the rest is ticked by hand; all manual; all automated.
Recommend: the split. Reason: a long manual list is the artifact that gets skipped on the second run, so the manual column has to stay short enough to actually do.

## Not asked

Do not ask whether the fix is done. This node is written before the fix,
and a verify artifact that describes finished work has been written too
late to be worth anything.
