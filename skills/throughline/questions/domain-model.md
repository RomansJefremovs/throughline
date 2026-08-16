# Domain model

Goal: the project's vocabulary. This artifact is injected into every later
prompt, so precision here pays off in every future session. Renders as a
mermaid `classDiagram`.

Existing repos: every question here is a confirmation, never an invention.
The code already holds the vocabulary. Four questions.

### Q1: Are these the core entities?
Options: the entity list read out of the models and schema, the same list with
your proposed merges applied, and "You decide".
Recommend: the list as found. Reason: confirming what the code already says is cheaper and more accurate than inventing a parallel vocabulary.

### Q2: Is this one an entity or a property?
Ask once per genuinely ambiguous entity, never as a batch.
Options: its own entity, a property of the named parent, or leave it out of the model.
Recommend: fold it into the parent unless it has its own lifecycle. Reason: something that is always created and destroyed with its parent is a property wearing an entity's name.

### Q3: Do these relationships and cardinalities look right?
Options: the relationship set derived from foreign keys and code paths, an
alternative where the code is genuinely ambiguous, and "You decide".
Recommend: the derived set. Reason: cardinality mistakes cost nothing to fix here and a great deal to fix in the schema.

### Q4: Which name wins where the codebase uses two?
Ask once per conflict, with the conflicting names as the options.
Recommend: the name that appears most often in the code. Reason: renaming toward existing usage is the smaller and safer change.
