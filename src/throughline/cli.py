"""Command line entry point.

The CLI owns every deterministic operation. It never calls a model; the
skill markdown does the talking and shells out to these commands.
"""

import argparse
import json
import sys
from pathlib import Path

from . import artifacts, context, hashing, nodes as nodes_module, scan as scan_module
from . import gaps, registry, serve, tasks
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
    result = state_module.init(repo, args.project, flags, target_side=args.target_side)
    _emit(
        {
            "project": result.project,
            "flags": result.flags,
            "target_side": result.target_side,
        },
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
    entry.status = state_module.DRAFTED if args.drafted else state_module.CURRENT
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
    result = status_module.for_repo(Path(args.repo))
    payload = {
        "project": result.project,
        "where_you_left_off": result.where_you_left_off,
        "next": result.next_node,
        "next_title": result.next_title,
        "answered": result.answered,
        "task": result.task_slug,
        "task_title": result.task_title,
        "phases": [
            {"phase": p.phase, "filled": p.filled, "total": p.total}
            for p in result.phases
        ],
    }
    _emit(payload, args.json, status_module.render_text(result))
    return 0


def cmd_next(args) -> int:
    repo = Path(args.repo)
    if _load(repo) is None:
        return 1
    result = status_module.for_repo(repo)
    payload = {"next": result.next_node, "task": result.task_slug}
    _emit(payload, args.json, result.next_node or "")
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


def cmd_confirm(args) -> int:
    """Promote a drafted node to current.

    Confirming is the moment a document stops being something Claude
    wrote and becomes something its owner stands behind, so it refuses
    when there is no artifact to have read.
    """
    repo = Path(args.repo)
    loaded = _load(repo)
    if loaded is None:
        return 1
    if not artifacts.artifact_path(repo, args.node).is_file():
        print(f"no artifact written for {args.node}", file=sys.stderr)
        return 1
    entry = state_module.node_state(loaded, args.node)
    entry.status = state_module.CURRENT
    entry.updated = state_module.utcnow()
    state_module.save(repo, loaded)
    _emit({"node": args.node, "status": entry.status}, args.json, f"confirmed {args.node}")
    return 0


def cmd_target(args) -> int:
    on = args.setting == "on"
    state_module.set_target_side(Path(args.repo), on)
    word = "on" if on else "off"
    _emit({"target_side": on}, args.json, f"target side {word}")
    return 0


def cmd_gaps(args) -> int:
    """List the differences between the two sides of every artifact.

    Computed on the spot and never stored. Reading them creates nothing -
    a gap becomes work only when the user promotes it.
    """
    repo = Path(args.repo)
    found = gaps.for_node(repo, args.node) if args.node else gaps.for_repo(repo)
    payload = [{"node": g.node, "title": g.title, "text": g.text} for g in found]
    text = "\n".join(f"{g.node:<24} {g.title}" for g in found)
    _emit(payload, args.json, text or "no gaps - nothing has a target side yet")
    return 0


def cmd_promote(args) -> int:
    repo = Path(args.repo)
    wanted = args.title.strip().lower()
    for gap in gaps.for_node(repo, args.node):
        if gap.title.strip().lower() == wanted:
            slug = gaps.promote(repo, gap)
            _emit({"slug": slug}, args.json, f"created {slug}")
            return 0
    print(f"no gap called {args.title!r} in {args.node}", file=sys.stderr)
    return 1


def cmd_task_new(args) -> int:
    repo = Path(args.repo)
    slug = tasks.create(repo, args.title, origin=args.origin, reference=args.reference)
    _emit({"slug": slug, "title": args.title}, args.json, f"created {slug}")
    return 0


def cmd_task_list(args) -> int:
    """The list exists and can be opened. It never greets anyone.

    No count is printed, here or anywhere - three unfinished tasks read
    the same as none until you deliberately look.
    """
    found = tasks.all_tasks(Path(args.repo))
    payload = [
        {
            "slug": t.slug,
            "title": t.title,
            "status": t.status,
            "origin": t.origin,
            "reference": t.reference,
            "next": tasks.next_node(t),
        }
        for t in found
    ]
    text = "\n".join(f"{t.status:<12} {t.title}  ({t.slug})" for t in found)
    _emit(payload, args.json, text or "no tasks in this repo")
    return 0


def cmd_task_answer(args) -> int:
    tasks.record_answer(Path(args.repo), args.slug, args.node, args.question, args.answer)
    _emit({"saved": True}, args.json, "saved")
    return 0


def cmd_task_write(args) -> int:
    body = _resolve_body(args)
    if body is None:
        return 1
    path = tasks.write(Path(args.repo), args.slug, args.node, body, args.summary)
    _emit({"path": str(path)}, args.json, f"wrote {path}")
    return 0


def cmd_task_context(args) -> int:
    repo = Path(args.repo)
    task = tasks.load(repo, args.slug)
    node = nodes_module.get_task_node(args.node)
    parts = [f"# Context for {node.title}", "", f"Task: {task.title}"]
    if task.reference:
        parts.append(f"Reference: {task.reference}")
    parts.append("")
    for dep in node.deps:
        path = tasks.artifact_path(repo, args.slug, dep)
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    text = "\n".join(parts)
    _emit({"node": node.id, "text": text}, args.json, text)
    return 0


def cmd_task_abandon(args) -> int:
    tasks.abandon(Path(args.repo), args.slug)
    _emit({"slug": args.slug, "status": tasks.ABANDONED}, args.json, "abandoned")
    return 0


def cmd_task_reopen(args) -> int:
    task = tasks.reopen(Path(args.repo), args.slug)
    _emit({"slug": args.slug, "status": task.status}, args.json, "reopened")
    return 0


def cmd_add(args) -> int:
    """Track a repo so the app can show it.

    Refuses a folder with no pipeline: the registry is a list of projects,
    and a folder that has never been initialised is not one yet.
    """
    repo = Path(args.repo).resolve()
    if not state_module.exists(repo):
        print(f"no pipeline in {repo} - run init there first", file=sys.stderr)
        return 1
    registry.add(repo)
    _emit({"path": str(repo)}, args.json, f"tracking {repo}")
    return 0


def cmd_forget(args) -> int:
    repo = Path(args.repo).resolve()
    registry.remove(repo)
    _emit({"path": str(repo)}, args.json, f"forgot {repo}")
    return 0


def cmd_projects(args) -> int:
    payload = [registry.describe(repo) for repo in registry.projects()]
    text = "\n".join(
        f"{item['project'] or item['name']}"
        + ("  (folder not found)" if item["missing"] else "")
        for item in payload
    )
    _emit(payload, args.json, text or "nothing tracked yet")
    return 0


def cmd_serve(args) -> int:
    serve.run(port=args.port)
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
    init.add_argument("--target-side", action="store_true")

    add("nodes", cmd_nodes, "list active nodes and their status")

    target = add("target", cmd_target, "turn the target side on or off")
    target.add_argument("setting", choices=["on", "off"])

    gaps_cmd = add("gaps", cmd_gaps, "differences between the two sides")
    gaps_cmd.add_argument("node", nargs="?")

    promote = add("promote", cmd_promote, "turn one gap into a task")
    promote.add_argument("node")
    promote.add_argument("title")

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
    write.add_argument("--drafted", action="store_true")

    confirm = add("confirm", cmd_confirm, "promote a drafted node to current")
    confirm.add_argument("node")

    add("status", cmd_status, "where you left off and the one next node")
    add("next", cmd_next, "print the next node id")

    stale = add("stale", cmd_stale, "check one node against its inputs")
    stale.add_argument("node")

    add("scan", cmd_scan, "gather raw material from an existing repo")

    add("add", cmd_add, "track this repo so the app can show it")
    add("forget", cmd_forget, "stop tracking this repo")
    add("projects", cmd_projects, "list tracked projects")

    serve_cmd = add("serve", cmd_serve, "run the local app")
    serve_cmd.add_argument("--port", type=int, default=7373)

    task = subparsers.add_parser("task", help="small units of work, four nodes each")
    task_subs = task.add_subparsers(dest="task_command", required=True)

    def add_task(name, handler, help_text):
        sub = task_subs.add_parser(name, help=help_text)
        sub.add_argument("--repo", default=".")
        sub.add_argument("--json", action="store_true")
        sub.set_defaults(handler=handler)
        return sub

    new = add_task("new", cmd_task_new, "start a task")
    new.add_argument("title")
    new.add_argument("--origin", default="ticket", choices=["ticket", "gap"])
    new.add_argument("--reference", default="")

    add_task("list", cmd_task_list, "list tasks, newest first")

    t_answer = add_task("answer", cmd_task_answer, "persist one task answer")
    t_answer.add_argument("slug")
    t_answer.add_argument("node")
    t_answer.add_argument("question")
    t_answer.add_argument("answer")

    t_write = add_task("write", cmd_task_write, "write a task node's artifact")
    t_write.add_argument("slug")
    t_write.add_argument("node")
    t_write.add_argument("--summary", required=True)
    t_write.add_argument("--body")
    t_write.add_argument("--body-file")
    t_write.add_argument("--note")

    t_ctx = add_task("context", cmd_task_context, "the scoped context for a task node")
    t_ctx.add_argument("slug")
    t_ctx.add_argument("node")

    t_abandon = add_task("abandon", cmd_task_abandon, "drop a task without finishing it")
    t_abandon.add_argument("slug")

    t_reopen = add_task("reopen", cmd_task_reopen, "pick an abandoned task back up")
    t_reopen.add_argument("slug")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.handler(args)
