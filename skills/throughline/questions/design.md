# Design

Goal: the change to make, and everything it touches. Not the code.

Three questions. Every one goes through `AskUserQuestion`.

### Q1: Which change?
Options: two or three real approaches from the analysis - the narrow fix,
the one that fixes the class of bug, and the one that changes the design if
the code genuinely offers it. Say what each costs.
Recommend: the narrowest change that fixes the reported symptom. Reason: on paid work the wider fix is unbilled, and the narrow one can always be widened later; the reverse is not true.

### Q2: What does it touch?
Options: the files and behaviours you traced, the same plus the ones you
suspect, and "just the one file".
Recommend: what you traced, naming each file. Reason: this list is what the verify node checks, so anything missing here is untested by construction.

### Q3: What could this break?
Ask LAST. Options: two concrete risks from the analysis - a shared call
site, a migration, a behaviour someone may depend on - plus "nothing that
is not covered".
Recommend: the risk with a real call site behind it. Reason: naming it here is what turns it into a verification step instead of a surprise.

## Not asked

Do not ask about implementation detail - names, signatures, where a helper
lives. That is the work itself, and deciding it in an interview is slower
than doing it.
