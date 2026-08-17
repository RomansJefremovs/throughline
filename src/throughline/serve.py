"""The local server the desktop app talks to.

Routing is a pure function of method, path, query and body, so the whole
API is testable without opening a socket. The HTTP layer underneath is
stdlib and deliberately dull.

The sidecar owns every rule. Nothing here decides anything the CLI does
not already decide - if a rule appears in this file that is not in the
CLI, it has been implemented twice and one copy will drift.
"""

import hashlib
import json
import subprocess
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import artifacts
from . import nodes as nodes_module
from . import gaps, hashing, registry, setup, tasks
from . import state as state_module

ASSETS = Path(__file__).parent / "app"


@dataclass
class Response:
    status: int
    content_type: str
    body: bytes


def _json_response(payload, status: int = 200) -> Response:
    return Response(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(payload).encode("utf-8"),
    )


def _error(status: int, message: str) -> Response:
    return _json_response({"error": message}, status)


def _tracked_repo(query: dict) -> tuple[Path | None, Response | None]:
    """Resolve the `repo` parameter, refusing anything not tracked.

    The registry is the allow-list. Without this the server would happily
    read any path a caller named, which on a machine full of client work
    is not a theoretical problem.
    """
    raw = query.get("repo")
    if not raw:
        return None, _error(400, "repo is required")
    resolved = Path(raw).resolve()
    if resolved not in registry.projects():
        return None, _error(403, "that repo is not tracked")
    return resolved, None


def _nodes_payload(repo: Path) -> list[dict]:
    loaded = state_module.load(repo)
    active = nodes_module.active_nodes(loaded.flags, tuple(loaded.on_demand.keys()))
    return [
        {
            "id": node.id,
            "title": node.title,
            "phase": node.phase,
            "deps": list(node.deps),
            "renders": node.renders,
            "status": state_module.node_state(loaded, node.id).status,
            "written": artifacts.artifact_path(repo, node.id).is_file(),
        }
        for node in active
    ]


def _get_home() -> Response:
    repo = registry.last_worked()
    if repo is None:
        return _json_response({})
    return _json_response(registry.describe(repo))


def _get_projects() -> Response:
    return _json_response([registry.describe(repo) for repo in registry.projects()])


def _get_project(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    if not state_module.exists(repo):
        return _error(404, "no pipeline in that repo")
    loaded = state_module.load(repo)
    payload = registry.describe(repo)
    # An empty node list reads as breakage unless the app can say why it
    # is empty, so the repo kind travels with it.
    payload["task_only"] = loaded.task_only
    payload["target_side"] = loaded.target_side
    payload["nodes"] = [] if loaded.task_only else _nodes_payload(repo)
    return _json_response(payload)


def _get_tasks(query: dict) -> Response:
    """The task list, only ever on request.

    Nothing else in the API returns it. A list of unfinished work that
    arrives without being asked for is the pattern rule 1 forbids, and
    the app must not be able to render one by accident.
    """
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    return _json_response(
        [
            {
                "slug": task.slug,
                "title": task.title,
                "status": task.status,
                "origin": task.origin,
                "reference": task.reference,
                "next": tasks.next_node(task),
                "nodes": [
                    {
                        "id": node.id,
                        "title": node.title,
                        "status": task.nodes[node.id].status,
                        "written": tasks.artifact_path(
                            repo, task.slug, node.id
                        ).is_file(),
                    }
                    for node in nodes_module.TASK_NODES
                ],
            }
            for task in tasks.all_tasks(repo)
        ]
    )


def _get_setup(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    path = setup.setup_path(repo)
    if not path.is_file():
        return _error(404, "no setup written for this repo")
    return _json_response({"text": path.read_text(encoding="utf-8")})


def _get_stale(query: dict) -> Response:
    """Whether one document's inputs have moved since it was written.

    Its own endpoint, asked for one node at a time, because rule 5 says
    staleness is surfaced when someone opens the thing and never
    broadcast. No other response carries it.
    """
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node = query.get("node")
    if not node:
        return _error(400, "node is required")
    changed = hashing.stale_deps(repo, node, state_module.load(repo))
    return _json_response({"node": node, "stale": bool(changed), "changed": changed})


def _get_gaps(query: dict) -> Response:
    """Differences between an artifact's two sides, recomputed each time.

    Its own endpoint, like the task list, so no other response can carry
    a list of outstanding work by accident.
    """
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node = query.get("node")
    found = gaps.for_node(repo, node) if node else gaps.for_repo(repo)
    return _json_response(
        [{"node": g.node, "title": g.title, "text": g.text} for g in found]
    )


def _post_promote(query: dict) -> Response:
    """Turn one named gap into a task. Only ever one, only ever on request."""
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node = query.get("node")
    title = (query.get("title") or "").strip().lower()
    if not node or not title:
        return _error(400, "node and title are required")
    for gap in gaps.for_node(repo, node):
        if gap.title.strip().lower() == title:
            return _json_response({"slug": gaps.promote(repo, gap)})
    return _error(404, "no such gap")


def _artifact_target(repo: Path, query: dict) -> tuple[Path | None, Response | None]:
    """Where an artifact lives, project or task, from the same query."""
    node = query.get("node")
    if not node:
        return None, _error(400, "node is required")
    slug = query.get("slug")
    if not slug:
        return artifacts.artifact_path(repo, node), None
    if not tasks.task_path(repo, slug).is_file():
        return None, _error(404, "no such task")
    try:
        return tasks.artifact_path(repo, slug, node), None
    except KeyError:
        return None, _error(400, "no such task node")


def _version_of(path: Path) -> str:
    """What the file looked like when it was handed out.

    A hash rather than a timestamp: two writes inside the same second are
    exactly the case this exists to catch.
    """
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_artifact(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    path, failure = _artifact_target(repo, query)
    if failure is not None:
        return failure
    if not path.is_file():
        return _error(404, "not written yet")
    return _json_response(
        {
            "node": query.get("node"),
            "text": path.read_text(encoding="utf-8"),
            "version": _version_of(path),
        }
    )


def _put_artifact(query: dict, body: bytes) -> Response:
    """Store an edit exactly as typed.

    Rule 10: the file is the truth. Nothing here reformats, re-wraps or
    re-derives the summary line - what the user typed is what is on disk.

    The bytes are written raw. Python's text write would translate
    newlines to the platform's, so on Windows a body sent with LF would
    land as CRLF - the tool editing the file rather than its owner.
    """
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    path, failure = _artifact_target(repo, query)
    if failure is not None:
        return failure

    # Two writers, and neither may silently win. The caller says which
    # version it started from; if the file has moved on since, the save
    # is refused and the newer text comes back so nothing is guessed at.
    expected = query.get("version")
    actual = _version_of(path)
    if expected is not None and expected != actual:
        return _json_response(
            {
                "error": "changed while you were editing",
                "text": path.read_text(encoding="utf-8") if path.is_file() else "",
                "version": actual,
            },
            409,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return _json_response(
        {"node": query.get("node"), "saved": True, "version": _version_of(path)}
    )


def spawn_claude(repo: Path, prompt: str) -> None:
    """Open a Claude session in the repo, already asking for the node.

    A new console rather than a child of the server: the session outlives
    the app, and closing the app must never kill work in progress.
    """
    creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        ["claude", prompt],
        cwd=str(repo),
        creationflags=creation,
        shell=False,
    )


def _post_start(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node_id = query.get("node") or ""
    slug = query.get("slug")
    # Node ids and slugs are checked against the graph and the filesystem
    # rather than sanitised. Both reach a process argument, and an
    # allow-list is the only check that cannot be talked around.
    if slug:
        if not tasks.task_path(repo, slug).is_file():
            return _error(404, "no such task")
        try:
            node = nodes_module.get_task_node(node_id)
        except KeyError:
            return _error(400, "no such node")
        prompt = (
            f"Use the throughline skill and work the {node.id} node "
            f"of task {slug}."
        )
    else:
        try:
            node = nodes_module.get_node(node_id)
        except KeyError:
            return _error(400, "no such node")
        prompt = f"Use the throughline skill and work the {node.id} node."
    try:
        spawn_claude(repo, prompt)
    except FileNotFoundError:
        return _error(500, "claude was not found on PATH")
    except OSError as err:
        return _error(500, f"could not start claude: {err}")
    return _json_response({"node": node.id, "started": True})


def _asset(name: str, content_type: str) -> Response:
    path = ASSETS / name
    if not path.is_file():
        return _error(404, "missing asset")
    return Response(status=200, content_type=content_type, body=path.read_bytes())


# An allow-list, not a directory. There is no path to traverse because
# nothing the caller sends is ever joined onto a filesystem path.
ASSET_TYPES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/vendor/mermaid.min.js": ("vendor/mermaid.min.js", "text/javascript; charset=utf-8"),
    "/vendor/archivo.css": ("vendor/archivo.css", "text/css; charset=utf-8"),
    "/vendor/archivo-400.woff2": ("vendor/archivo-400.woff2", "font/woff2"),
    "/vendor/archivo-600.woff2": ("vendor/archivo-600.woff2", "font/woff2"),
    "/vendor/archivo-800.woff2": ("vendor/archivo-800.woff2", "font/woff2"),
}


def _origin_ok(headers) -> bool:
    """Whether a POST came from the app rather than from another page.

    The server has no authentication and its port is chosen at runtime,
    so there is no configured origin to compare against - the host the
    request was addressed to is the only thing both sides agree on.

    A missing Origin is allowed on purpose. Browsers always send one on
    a cross-origin POST; terminals never send one at all, so curl and
    the CLI are untouched. GETs are left alone: they change nothing, and
    a cross-origin GET cannot read its own response.
    """
    if not headers:
        return True
    lowered = {str(name).lower(): value for name, value in dict(headers).items()}
    origin = lowered.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == lowered.get("host", "")


def route(
    method: str, path: str, query: dict, body: bytes, headers=None
) -> Response:
    if method == "POST" and not _origin_ok(headers):
        return _error(403, "cross-origin request refused")
    if method == "GET" and path in ASSET_TYPES:
        name, content_type = ASSET_TYPES[path]
        return _asset(name, content_type)
    if method == "GET" and path == "/api/home":
        return _get_home()
    if method == "GET" and path == "/api/projects":
        return _get_projects()
    if method == "GET" and path == "/api/project":
        return _get_project(query)
    if method == "GET" and path == "/api/setup":
        return _get_setup(query)
    if method == "GET" and path == "/api/stale":
        return _get_stale(query)
    if method == "GET" and path == "/api/gaps":
        return _get_gaps(query)
    if method == "GET" and path == "/api/tasks":
        return _get_tasks(query)
    if method == "GET" and path == "/api/artifact":
        return _get_artifact(query)
    if method == "PUT" and path == "/api/artifact":
        return _put_artifact(query, body)
    if method == "POST" and path == "/api/promote":
        return _post_promote(query)
    if method == "POST" and path == "/api/start":
        return _post_start(query)
    return _error(404, "no such route")


class Handler(BaseHTTPRequestHandler):
    def _respond(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        response = route(method, parsed.path, query, body, self.headers)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self) -> None:
        self._respond("GET")

    def do_PUT(self) -> None:
        self._respond("PUT")

    def do_POST(self) -> None:
        self._respond("POST")

    def log_message(self, *args) -> None:
        """Quiet by default - the terminal is not the product."""


def make_server(host: str = "127.0.0.1", port: int = 7373) -> ThreadingHTTPServer:
    """Bind a server. Port 0 means "any free port, and tell me which".

    The desktop shell uses that. A fixed port is how a stale server ends
    up quietly serving old code while the new one fails to bind and its
    window closes - which looks exactly like the app being broken.
    """
    return ThreadingHTTPServer((host, port), Handler)


def run(host: str = "127.0.0.1", port: int = 7373) -> None:
    server = make_server(host, port)
    actual = server.server_address[1]
    # One line, flushed, so a parent process can read the port back
    # before it makes the first request.
    print(f"Throughline on http://{host}:{actual}", flush=True)
    server.serve_forever()
