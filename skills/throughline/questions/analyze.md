# Analyze

Goal: what is actually happening, and why. Still no fix.

Three questions. Every one goes through `AskUserQuestion`.

**Read the code first.** This is the node where targeted reading pays for
itself - open the two or three files the symptom points at, and open them
to answer a question, never to understand the project.

### Q1: Is this the cause?
Options: the cause you found, with the file and line that shows it; one
alternative if the evidence genuinely allows two readings; and "not found
yet".
Recommend: the cause you can point at in the code. Reason: a cause you can name a line for is one the fix can be checked against; a cause you cannot is a guess wearing a diagnosis.

### Q2: Why did it survive until now?
Options: never exercised, only breaks on a path nobody takes, a test covers
the neighbouring case, or a recent change broke it.
Recommend: whatever the git history supports, and say which commit. Reason: the answer decides whether the fix needs a test, a migration, or a conversation.

### Q3: What else touches this?
Options: the call sites and data you found, the same list plus the ones you
suspect but have not checked, and "nothing else".
Recommend: the list you actually verified. Reason: an unchecked call site listed as fact is how a small fix becomes unpaid rework.

## Not asked

Do not ask which fix to apply. The design node exists so the fix is chosen
after the cause is agreed, not alongside it.
