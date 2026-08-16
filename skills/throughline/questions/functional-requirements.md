# Functional requirements

Goal: a numbered list of what the system must do, each traceable to the
problem statement. Split into one node per feature area if this would run
past five questions.

Five questions. Every one goes through `AskUserQuestion`.

### Q1: Are these the actors?
Options: the actor list drawn from the code and the problem statement, an
alternative grouping if the code suggests one, and "You decide".
Recommend: the list as found. Reason: reacting to a concrete list is cheaper than recalling one.

### Q2: Which of these is the system's core job?
Options: two or three candidates, each traceable to a different cost named in
the problem statement.
Recommend: the one matching the cost the user ranked first. Reason: it keeps requirements traceable to the problem instead of to the codebase.

### Q3: Does this list of capabilities look right?
Options: present the capability list from the code as one option, the same list
with your suggested cuts as another, and "You decide".
Recommend: the cut list. Reason: striking things out is faster than adding them, and a shorter first version is cheaper to be wrong about.

### Q4: What must it never do?
Options: the hard rules found in the code or CLAUDE.md, presented for
confirmation, plus "none that the code implies".
Recommend: the rules as found. Reason: a deliberate product rule read later as an unfinished feature is how good constraints get "fixed" away.

### Q5: Are there real numbers behind performance, scale or availability?
Options: figures the problem statement or code actually states, or "not yet".
Recommend: "not yet" unless a real figure exists. Reason: invented figures become fake requirements that later work is held to.
