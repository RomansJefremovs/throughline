"""The local server the desktop app talks to.

Routing is a pure function of method, path, query and body, so the whole
API is testable without opening a socket. The HTTP layer underneath is
stdlib and deliberately dull.

The sidecar owns every rule. Nothing here decides anything the CLI does
not already decide - if a rule appears in this file that is not in the
CLI, it has been implemented twice and one copy will drift.
"""

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import artifacts
from . import nodes as nodes_module
from . import registry
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
    payload = registry.describe(repo)
    payload["nodes"] = _nodes_payload(repo)
    return _json_response(payload)


def _get_artifact(query: dict) -> Response:
    repo, failure = _tracked_repo(query)
    if failure is not None:
        return failure
    node = query.get("node")
    if not node:
        return _error(400, "node is required")
    path = artifacts.artifact_path(repo, node)
    if not path.is_file():
        return _error(404, "not written yet")
    return _json_response({"node": node, "text": path.read_text(encoding="utf-8")})


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
    node = query.get("node")
    if not node:
        return _error(400, "node is required")
    path = artifacts.artifact_path(repo, node)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return _json_response({"node": node, "saved": True})


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
}


def route(method: str, path: str, query: dict, body: bytes) -> Response:
    if method == "GET" and path in ASSET_TYPES:
        name, content_type = ASSET_TYPES[path]
        return _asset(name, content_type)
    if method == "GET" and path == "/api/home":
        return _get_home()
    if method == "GET" and path == "/api/projects":
        return _get_projects()
    if method == "GET" and path == "/api/project":
        return _get_project(query)
    if method == "GET" and path == "/api/artifact":
        return _get_artifact(query)
    if method == "PUT" and path == "/api/artifact":
        return _put_artifact(query, body)
    return _error(404, "no such route")


class Handler(BaseHTTPRequestHandler):
    def _respond(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        response = route(method, parsed.path, query, body)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self) -> None:
        self._respond("GET")

    def do_PUT(self) -> None:
        self._respond("PUT")

    def log_message(self, *args) -> None:
        """Quiet by default - the terminal is not the product."""


def run(host: str = "127.0.0.1", port: int = 7373) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Throughline on http://{host}:{port}")
    server.serve_forever()
