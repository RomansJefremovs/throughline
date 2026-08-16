# Problem statement

Goal: one paragraph naming who has the problem, what it costs them, and
what "solved" looks like. No solutions.

Four questions. Every one goes through `AskUserQuestion`.

### Q1: Who has this problem?
Options: build them from the scan - the person the code actually serves today,
the person it is being built to serve, and a third only if the code genuinely
suggests one.
Recommend: whichever the scan supports, and say which file told you. Reason: the answer decides whose language every later node uses.

### Q2: What does it cost them today?
Options: time, money, skill they do not have, work that simply never happens.
Offer the three the scan supports as separate options; multi-select is fine here.
Recommend: the cost the product's own design is shaped around. Reason: it is the one you can check afterwards.

### Q3: What does solved look like, in one observable change?
Options: derive two or three genuinely different end-states from the code - not
rewordings of each other. State plainly which one the product can actually
deliver and which is an outcome it can only aim at.
Recommend: the deliverable one. Reason: an aim the code cannot guarantee becomes a requirement nobody can satisfy.

### Q4: Is this how they cope today?
Ask this LAST and only as a confirmation. Propose the coping behaviour the scan
implies - an existing tool, a manual process, or nothing - and offer "You decide".
Recommend: the proposal from the scan. Reason: asking someone to characterise a market they have not researched produces "I don't know", which is a wasted question.

## Not asked

Do not ask what is out of scope. Delimitation before anything is decided has
nothing to bite on. If the user volunteers a boundary, record it; otherwise
write "no feature excluded on principle" and move on.
