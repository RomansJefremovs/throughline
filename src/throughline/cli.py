"""Command line entry point.

The CLI owns every deterministic operation. It never calls a model; the
skill markdown does the talking and shells out to these commands.
"""

import argparse
import json
import sys
from pathlib import Path

from . import artifacts, context, hashing, nodes as nodes_module, scan as scan_module
from . import state as state_module
from . import status as status_module


def parse_flags(pairs: list[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"flag must be name=true or name=false, got {pair!r}")
        name, _, value = pair.partition("=")
        name = name.strip()
        if name not in nodes_module.FLAGS:
            known = ", ".join(nodes_module.FLAGS)
            raise SystemExit(f"unknown flag {name!r}, expected one of: {known}")
        result[name] = value.strip().lower() in {"true", "yes", "1"}
    return result


def _emit(payload, as_json: bool, text: str) -> None:
    print(json.dumps(payload, indent=2) if as_json else text.rstrip("\n"))


def _load(repo: Path):
    try:
        return state_module.load(repo)
    except FileNotFoundError as error:
        print(f"no pipeline here - run `throughline init` first ({error})")
        return None


def cmd_init(args) -> int:
    repo = Path(args.repo)
    if state_module.exists(repo):
        print("a pipeline already exists here; refusing to overwrite it")
        return 1
    flags = parse_flags(args.flag or [])
    result = state_module.init(repo, args.project, flags)
    _emit(
        {"project": result.project, "flags": result.flags},
        args.json,
        f"created {state_module.state_path(repo)}",
    )
    return 0


def cmd_nodes(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    active = nodes_module.active_nodes(loaded.flags, tuple(loaded.on_demand.keys()))
    payload = [
        {
            "id": node.id,
            "title": node.title,
            "phase": node.phase,
            "deps": list(node.deps),
            "renders": node.renders,
            "status": state_module.node_state(loaded, node.id).status,
            "confirmed": state_module.node_state(loaded, node.id).confirmed,
        }
        for node in active
    ]
    text = "\n".join(f"{item['status']:<12} {item['id']}" for item in payload)
    _emit(payload, args.json, text)
    return 0


def cmd_context(args) -> int:
    repo = Path(args.repo)
    ctx = context.assemble(repo, args.node)
    payload = {
        "node": args.node,
        "line_count": ctx.line_count,
        "loaded": [d.node_id for d in ctx.documents],
        "missing": ctx.missing,
        "text": context.render(ctx),
    }
    _emit(payload, args.json, context.render(ctx))
    return 0


def cmd_answer(args) -> int:
    repo = Path(args.repo)
    if not state_module.exists(repo):
        print("no pipeline here - run `throughline init` first")
        return 1
    state_module.record_answer(repo, args.node, args.question, args.answer)
    _emit({"saved": True}, args.json, "saved")
    return 0


def _resolve_body(args) -> str | None:
    """The body comes from a file or the flag, never both.

    An artifact body is a markdown document with brackets, pipes and
    newlines in it. Shells word-split that before argparse sees it, so
    --body-file is the path any real body should take.
    """
    if args.body is not None and args.body_file is not None:
        print("pass --body or --body-file, not both")
        return None
    if args.body is not None:
        return args.body
    if args.body_file is None:
        print("pass --body for a short body, or --body-file for a real one")
        return None
    source = Path(args.body_file)
    if not source.is_file():
        print(f"no such file: {source}")
        return None
    return source.read_text(encoding="utf-8")


def cmd_write(args) -> int:
    repo = Path(args.repo)
    body = _resolve_body(args)
    if body is None:
        return 1
    loaded = _load(repo)
    if loaded is None:
        return 1
    path = artifacts.write_artifact(
        repo, args.node, body, args.summary, slug=args.slug
    )
    entry = state_module.node_state(loaded, args.node)
    entry.status = state_module.CURRENT
    entry.confirmed = True
    entry.updated = state_module.utcnow()
    hashing.stamp(repo, args.node, loaded)
    loaded.last_node = args.node
    if args.note:
        loaded.last_note = args.note
    state_module.save(repo, loaded)
    _emit({"path": str(path)}, args.json, f"wrote {path}")
    return 0


def cmd_status(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    result = status_module.compute(loaded)
    payload = {
        "project": result.project,
        "where_you_left_off": result.where_you_left_off,
        "next": result.next_node,
        "next_title": result.next_title,
        "phases": [
            {"phase": p.phase, "filled": p.filled, "total": p.total}
            for p in result.phases
        ],
    }
    _emit(payload, args.json, status_module.render_text(result))
    return 0


def cmd_next(args) -> int:
    loaded = _load(Path(args.repo))
    if loaded is None:
        return 1
    chosen = status_module.next_node(loaded)
    _emit({"next": chosen}, args.json, chosen or "")
    return 0


def cmd_stale(args) -> int:
    repo = Path(args.repo)
    loaded = _load(repo)
    if loaded is None:
        return 1
    changed = hashing.stale_deps(repo, args.node, loaded)
    payload = {"node": args.node, "stale": bool(changed), "changed": changed}
    text = (
        f"{args.node} was written before {', '.join(changed)} changed"
        if changed
        else f"{args.node} is up to date with its inputs"
    )
    _emit(payload, args.json, text)
    return 0


def cmd_scan(args) -> int:
    result = scan_module.scan(Path(args.repo))
    payload = {
        "tree": result.tree,
        "git_log": result.git_log,
        "readme": result.readme,
        "claude_md": result.claude_md,
        "transcripts": result.transcripts,
    }
    _emit(payload, args.json, scan_module.render(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="throughline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--repo", default=".")
        sub.add_argument("--json", action="store_true")
        sub.set_defaults(handler=handler)
        return sub

    init = add("init", cmd_init, "create the pipeline in a repo")
    init.add_argument("--project", required=True)
    init.add_argument("--flag", action="append")

    add("nodes", cmd_nodes, "list active nodes and their status")

    ctx = add("context", cmd_context, "assemble the context for one node")
    ctx.add_argument("node")

    answer = add("answer", cmd_answer, "persist a single interview answer")
    answer.add_argument("node")
    answer.add_argument("question")
    answer.add_argument("answer")

    write = add("write", cmd_write, "write a node's artifact and mark it current")
    write.add_argument("node")
    write.add_argument("--summary", required=True)
    write.add_argument("--body")
    write.add_argument("--body-file")
    write.add_argument("--slug")
    write.add_argument("--note")

    add("status", cmd_status, "where you left off and the one next node")
    add("next", cmd_next, "print the next node id")

    stale = add("stale", cmd_stale, "check one node against its inputs")
    stale.add_argument("node")

    add("scan", cmd_scan, "gather raw material from an existing repo")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.handler(args)
