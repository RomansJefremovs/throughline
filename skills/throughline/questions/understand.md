# Understand

Goal: what is being asked, in the user's own words rather than the
ticket's. No causes, no fixes.

Three questions. Every one goes through `AskUserQuestion`.

**Open with a playback, not a question.** If setup recorded a ticket
integration, fetch the ticket yourself and say what you think was asked.
Never make the user paste it.

### Q1: Is this what you have been asked to do?
Options: your reading of the ticket, one genuinely different reading if the
wording supports one, and "You decide".
Recommend: your reading of the ticket. Reason: correcting a concrete sentence is cheaper than composing one, and the correction is the part worth recording.

### Q2: What does the person who reported it actually see?
Options: the symptom as written, the symptom as you suspect it really is if
the code disagrees with the report, and "not reproduced yet".
Recommend: the report as written unless the code plainly contradicts it. Reason: the reported symptom is the thing acceptance is judged against, whatever the underlying cause turns out to be.

### Q3: What would make this not worth doing?
Ask LAST. Options: two concrete conditions drawn from the repo - a cheaper
workaround, a rewrite already planned, nobody actually affected - plus
"nothing, it needs doing".
Recommend: "nothing, it needs doing" unless the repo says otherwise. Reason: this is the cheapest moment to decline work, and the only one where declining costs nothing.

## Not asked

Do not ask what causes it. That is the next node, and guessing here
anchors the analysis to the first idea anyone had.

**Keep the original wording.** Whatever the user corrects, the ticket's own
text stays in the artifact. It is what a later argument about scope is
settled against.
