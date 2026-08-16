# Throughline

An analysis and design pipeline that lives inside the repository it
describes.

Artifacts go in `docs/project/`. State is a single `pipeline.yaml`;
everything else is hand-editable markdown. Nodes are produced by short
interviews rather than document generation, so the person answering stays
the author.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Use

```bash
throughline init --repo path/to/repo --project my-project --flag has_db=true
```

```bash
throughline status --repo path/to/repo
```

The `skills/throughline/` directory holds the Claude Code skill that runs
the interviews on top of this CLI.

## Test

```bash
python -m pytest
```

Design notes are in `docs/superpowers/specs/`.
