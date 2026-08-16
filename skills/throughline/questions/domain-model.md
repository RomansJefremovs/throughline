# Domain model

Goal: the project's vocabulary. This artifact is injected into every later
prompt, so precision here pays off in every future session. Renders as a
mermaid `classDiagram`.

### Q1: Are these the core entities?
Options: present the entities found in the code or requirements
Recommend: the list as found. Reason: the code already contains the vocabulary; confirming is cheaper than inventing.

### Q2: Is anything on that list actually a property of something else?
Options: present each questionable entity individually
Recommend: fold it in unless it has its own lifecycle. Reason: an entity that always dies with its parent is a property.

### Q3: Is anything missing that you talk about but never named in code?
Options: propose candidates from the problem statement / nothing missing
Recommend: propose candidates. Reason: unnamed concepts are where miscommunication lives.

### Q4: What is the relationship between each pair?
Options: propose relationships with cardinality for confirmation
Recommend: the proposed set. Reason: cardinality mistakes are cheap now and expensive later.

### Q5: Which terms have two names in the codebase?
Options: present each conflict with a recommended winner
Recommend: the name used most often in the code. Reason: renaming toward existing usage is the smaller change.
