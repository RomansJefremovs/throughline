import http.client
import json
import re
import threading
from email.message import Message

import pytest

from throughline import agents, nodes, registry, serve, state


@pytest.fixture(autouse=True)
def _an_agent_to_hand_to(monkeypatch):
    """Every hand-off test needs an agent, and CI has neither.

    Resolution asks the real PATH. Pinning both here keeps the resolution
    table the only thing that varies; the tests for that table override
    these deliberately.
    """
    monkeypatch.setattr(agents, "chosen", lambda: "claude")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])


def _project(tmp_path, monkeypatch, name="Demo"):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / name.lower()
    repo.mkdir()
    state.init(repo, name, {})
    registry.add(repo)
    return repo


def _json(response):
    return json.loads(response.body.decode("utf-8"))


def test_port_zero_gets_a_real_port_from_the_operating_system():
    """The desktop shell asks for any free port and is told which.

    A fixed port is how a stale server ends up quietly serving old code
    while the new one fails to bind and disappears.
    """
    server = serve.make_server("127.0.0.1", 0)
    try:
        assert server.server_address[1] != 0
    finally:
        server.server_close()


def test_a_requested_port_is_honoured():
    server = serve.make_server("127.0.0.1", 0)
    chosen = server.server_address[1]
    server.server_close()

    again = serve.make_server("127.0.0.1", chosen)
    try:
        assert again.server_address[1] == chosen
    finally:
        again.server_close()


def test_unknown_path_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert serve.route("GET", "/nope", {}, b"").status == 404


def test_index_is_html(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    response = serve.route("GET", "/", {}, b"")
    assert response.status == 200
    assert "text/html" in response.content_type


def test_mermaid_is_served_from_the_package(tmp_path, monkeypatch):
    """Vendored, not fetched. A CDN would break offline and Tauri's CSP."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    response = serve.route("GET", "/vendor/mermaid.min.js", {}, b"")
    assert response.status == 200
    assert "javascript" in response.content_type
    assert len(response.body) > 100_000


def test_the_hidden_attribute_beats_the_stylesheet():
    """Everything the app hides, it hides by setting `hidden`.

    The browser's own rule for that attribute is `display: none`, and it
    is the weakest rule there is: any `display` in app.css targeting the
    same element outranks it, because author styles beat the user
    agent's. `.scrim { display: flex }` did that to the conflict dialog
    and pinned it open over every screen, on top of a full-viewport
    scrim that ate every click. So app.css has to say so itself, and
    `!important` is not decoration here - `[hidden]` scores the same as
    `.scrim` and loses on source order, and less than `#editing`.
    """
    css = (serve.ASSETS / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\[hidden\][^{]*\{[^}]*display\s*:\s*none\s*!important", css)


def test_asset_paths_cannot_escape_the_package(tmp_path, monkeypatch):
    """Assets are an allow-list, so there is no path to traverse."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    for attempt in ("/vendor/../../../state.py", "/../cli.py", "/vendor/anything.js"):
        assert serve.route("GET", attempt, {}, b"").status == 404


def test_a_post_from_another_origin_is_refused(tmp_path, monkeypatch):
    """The server is localhost, unauthenticated, on a guessable port.

    POSTs create files and start processes. A browser always sends
    Origin on a cross-origin POST, so a page that found the port still
    cannot make one.
    """
    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Origin": "http://evil.example", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 403


def test_a_post_from_the_app_itself_is_allowed(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Origin": "http://127.0.0.1:7373", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 200


def test_a_post_with_no_origin_is_allowed(tmp_path, monkeypatch):
    """Nothing sends Origin from a terminal. curl and the CLI still work."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "node": "problem-statement"},
        b"",
        {"Host": "127.0.0.1:7373"},
    )
    assert response.status == 200


def test_header_case_does_not_decide_the_origin_check():
    """http.server hands headers back in whatever case they arrived in."""
    response = serve.route(
        "POST",
        "/api/promote",
        {},
        b"",
        {"origin": "http://evil.example", "host": "127.0.0.1:7373"},
    )
    assert response.status == 403


def test_an_opaque_origin_is_refused():
    """`null` is what a sandboxed iframe or a data: URL sends as Origin.

    It is refused today because it parses to an empty netloc, which
    never matches a real Host - but that is easy to lose. "An opaque
    origin is like no origin, so let it through" is a plausible-sounding
    edit, and every other test in this file would still pass if someone
    made it. This one exists so that edit fails instead.
    """
    response = serve.route(
        "POST",
        "/api/promote",
        {},
        b"",
        {"Origin": "null", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 403


def test_a_real_http_message_is_refused_like_any_other_mapping():
    """Handler hands `_origin_ok` an email.message.Message, not a dict.

    Every other test in this file passes a plain dict as a stand-in.
    This one builds the actual object type `http.server` hands over and
    checks that it travels through `route` and `dict(headers)` intact
    and still yields the right status.
    """
    headers = Message()
    headers.add_header("Origin", "http://evil.example")
    headers.add_header("Host", "127.0.0.1:7373")
    response = serve.route("POST", "/api/promote", {}, b"", headers)
    assert response.status == 403


def test_a_put_from_another_origin_is_refused_without_writing_the_file(
    tmp_path, monkeypatch
):
    """A guard that returns 403 after already writing would be worse than
    no guard at all, so the 403 alone does not prove the fix works - the
    file on disk has to be checked too.
    """
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "Original.", "S.")
    response = serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement"},
        b"clobbered\n",
        {"Origin": "http://evil.example", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 403
    on_disk = artifacts.artifact_path(repo, "problem-statement").read_text("utf-8")
    assert "Original." in on_disk


def test_a_put_from_the_app_itself_is_allowed(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "Original.", "S.")
    response = serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement"},
        b"edited\n",
        {"Origin": "http://127.0.0.1:7373", "Host": "127.0.0.1:7373"},
    )
    assert response.status == 200


def test_projects_lists_what_is_tracked(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    response = serve.route("GET", "/api/projects", {}, b"")
    assert response.status == 200
    assert _json(response)[0]["project"] == "Demo"
    assert _json(response)[0]["path"] == str(repo.resolve())


def test_projects_never_reports_a_count_of_outstanding_work(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    body = serve.route("GET", "/api/projects", {}, b"").body.decode("utf-8").lower()
    assert "remaining" not in body
    assert "outstanding" not in body
    assert "todo" not in body


def test_home_names_the_project_to_open(tmp_path, monkeypatch):
    """The front door must resolve without the user choosing."""
    repo = _project(tmp_path, monkeypatch)
    response = serve.route("GET", "/api/home", {}, b"")
    assert _json(response)["path"] == str(repo.resolve())


def test_home_is_empty_when_nothing_is_tracked(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert _json(serve.route("GET", "/api/home", {}, b"")) == {}


def test_project_reports_its_nodes(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    response = serve.route("GET", "/api/project", {"repo": str(repo)}, b"")
    payload = _json(response)
    assert payload["project"] == "Demo"
    assert payload["nodes"][0]["id"] == "problem-statement"
    assert payload["nodes"][0]["status"] == "empty"


def test_project_requires_a_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert serve.route("GET", "/api/project", {}, b"").status == 400


def test_project_refuses_a_repo_that_is_not_tracked(tmp_path, monkeypatch):
    """Serving any path the caller names would read arbitrary files."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    state.init(stranger, "Stranger", {})
    response = serve.route("GET", "/api/project", {"repo": str(stranger)}, b"")
    assert response.status == 403


TWO_SIDED = (
    "# Current\n\nIt is like this.\n\n"
    "# Target\n\n## Scope accounts to the project\n\nNeeds `project_id`.\n"
)


def test_a_task_only_project_reports_itself_as_such(tmp_path, monkeypatch):
    """An empty node graph reads as broken. Say why it is empty."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "geedie"
    repo.mkdir()
    state.init(repo, "Geedie", {}, task_only=True)
    registry.add(repo)

    payload = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert payload["task_only"] is True
    assert payload["nodes"] == []


def test_the_setup_document_is_served_when_there_is_one(tmp_path, monkeypatch):
    from throughline import setup as setup_module

    repo = _project(tmp_path, monkeypatch)
    setup_module.write(repo, "A Vue client app.", "What this is.")

    response = serve.route("GET", "/api/setup", {"repo": str(repo)}, b"")
    assert response.status == 200
    assert "A Vue client app." in _json(response)["text"]


def test_no_setup_document_is_not_an_error(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    response = serve.route("GET", "/api/setup", {"repo": str(repo)}, b"")
    assert response.status == 404


def test_gaps_are_returned_only_from_their_own_endpoint(tmp_path, monkeypatch):
    """Nothing else may hand back a list of outstanding differences."""
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "architecture", TWO_SIDED, "Two sides.")

    project = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert "gaps" not in project

    listed = _json(serve.route("GET", "/api/gaps", {"repo": str(repo)}, b""))
    assert listed[0]["title"] == "Scope accounts to the project"


def test_gaps_can_be_scoped_to_one_node(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "architecture", TWO_SIDED, "Two sides.")

    listed = _json(
        serve.route("GET", "/api/gaps", {"repo": str(repo), "node": "architecture"}, b"")
    )
    assert len(listed) == 1
    empty = _json(
        serve.route(
            "GET", "/api/gaps", {"repo": str(repo), "node": "problem-statement"}, b""
        )
    )
    assert empty == []


def test_promoting_needs_an_explicit_request(tmp_path, monkeypatch):
    from throughline import artifacts, tasks

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "architecture", TWO_SIDED, "Two sides.")

    serve.route("GET", "/api/gaps", {"repo": str(repo)}, b"")
    assert tasks.all_tasks(repo) == []

    response = serve.route(
        "POST",
        "/api/promote",
        {
            "repo": str(repo),
            "node": "architecture",
            "title": "Scope accounts to the project",
        },
        b"",
    )
    assert response.status == 200
    assert len(tasks.all_tasks(repo)) == 1


def test_promoting_an_unknown_gap_is_refused(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "architecture", TWO_SIDED, "Two sides.")
    response = serve.route(
        "POST",
        "/api/promote",
        {"repo": str(repo), "node": "architecture", "title": "Invented"},
        b"",
    )
    assert response.status == 404


def test_project_names_the_live_task(tmp_path, monkeypatch):
    from throughline import tasks

    repo = _project(tmp_path, monkeypatch)
    slug = tasks.create(repo, "Fix the metrics")
    tasks.record_answer(repo, slug, "understand", "q1", "x")

    payload = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert payload["task"] == slug
    assert payload["next"] == "understand"


def test_tasks_are_listed_only_when_asked_for(tmp_path, monkeypatch):
    """The list exists and can be opened. It never arrives unrequested."""
    from throughline import tasks

    repo = _project(tmp_path, monkeypatch)
    tasks.create(repo, "Fix the metrics")

    project = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert "tasks" not in project

    listed = _json(serve.route("GET", "/api/tasks", {"repo": str(repo)}, b""))
    assert listed[0]["title"] == "Fix the metrics"


def test_a_task_artifact_is_read_by_slug(tmp_path, monkeypatch):
    from throughline import tasks

    repo = _project(tmp_path, monkeypatch)
    slug = tasks.create(repo, "Fix it")
    tasks.write(repo, slug, "understand", "The ticket says X.", "A summary.")

    response = serve.route(
        "GET",
        "/api/artifact",
        {"repo": str(repo), "slug": slug, "node": "understand"},
        b"",
    )
    assert response.status == 200
    assert "The ticket says X." in _json(response)["text"]


def test_a_task_artifact_is_saved_by_slug(tmp_path, monkeypatch):
    from throughline import tasks

    repo = _project(tmp_path, monkeypatch)
    slug = tasks.create(repo, "Fix it")
    tasks.write(repo, slug, "understand", "Old.", "A summary.")
    body = b"# Understand\n\n> A summary.\n\nEdited by hand.\n"

    serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "slug": slug, "node": "understand"},
        body,
    )
    assert tasks.artifact_path(repo, slug, "understand").read_bytes() == body


def test_start_works_on_a_task_node(tmp_path, monkeypatch):
    from throughline import tasks

    repo = _project(tmp_path, monkeypatch)
    slug = tasks.create(repo, "Fix it")
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(p))

    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "slug": slug, "node": "understand"},
        b"",
    )
    assert response.status == 200
    assert slug in calls[0]
    assert "understand" in calls[0]


def test_start_refuses_an_unknown_task(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "slug": "2026-01-01-nope", "node": "understand"},
        b"",
    )
    assert response.status == 404


def test_start_spawns_claude_in_the_repo(tmp_path, monkeypatch):
    """The one action the app exists to make cheap."""
    repo = _project(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append((r, p)))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "node": "problem-statement"}, b""
    )
    assert response.status == 200
    assert calls[0][0] == repo.resolve()
    assert "problem-statement" in calls[0][1]


def test_start_refuses_an_untracked_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(stranger), "node": "x"}, b""
    )
    assert response.status == 403


def test_start_refuses_an_unknown_node(tmp_path, monkeypatch):
    """The node id reaches a shell, so it is checked against the graph."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "node": "rm -rf /"}, b""
    )
    assert response.status == 400


def test_start_reports_when_claude_is_missing(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)

    def boom(_repo, _prompt, _name):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(serve, "spawn_agent", boom)
    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "node": "problem-statement"}, b""
    )
    assert response.status == 500
    assert "claude" in _json(response)["error"].lower()


def test_artifact_returns_the_markdown(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    from throughline import artifacts

    artifacts.write_artifact(repo, "problem-statement", "The body.", "A summary.")
    response = serve.route(
        "GET", "/api/artifact", {"repo": str(repo), "node": "problem-statement"}, b""
    )
    assert response.status == 200
    assert "The body." in _json(response)["text"]


def test_artifact_is_not_found_before_it_is_written(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "GET", "/api/artifact", {"repo": str(repo), "node": "problem-statement"}, b""
    )
    assert response.status == 404


def test_stale_is_reported_only_for_the_node_you_opened(tmp_path, monkeypatch):
    """Rule 3: never broadcast. It is asked for one document at a time."""
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    payload = _json(
        serve.route(
            "GET", "/api/stale", {"repo": str(repo), "node": "functional-requirements"}, b""
        )
    )
    assert payload["stale"] is False

    artifacts.write_artifact(repo, "problem-statement", "First.", "S.")
    serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement"},
        b"changed after the fact\n",
    )
    assert "changed" in _json(
        serve.route(
            "GET", "/api/stale", {"repo": str(repo), "node": "functional-requirements"}, b""
        )
    )


def test_no_other_endpoint_reports_staleness(tmp_path, monkeypatch):
    project = _json(
        serve.route(
            "GET", "/api/project", {"repo": str(_project(tmp_path, monkeypatch))}, b""
        )
    )
    assert "stale" not in json.dumps(project)


def test_reading_an_artifact_returns_a_version(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "The body.", "A summary.")
    payload = _json(
        serve.route(
            "GET", "/api/artifact", {"repo": str(repo), "node": "problem-statement"}, b""
        )
    )
    assert payload["version"]


def test_saving_with_a_stale_version_is_refused(tmp_path, monkeypatch):
    """Two writers, and neither one silently wins.

    The app loaded the artifact, a Claude session rewrote it, and the app
    then saved. Without this the session's work vanishes with no sign.
    """
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "Original.", "A summary.")
    loaded = _json(
        serve.route(
            "GET", "/api/artifact", {"repo": str(repo), "node": "problem-statement"}, b""
        )
    )

    artifacts.write_artifact(repo, "problem-statement", "Claude wrote this.", "S.")

    response = serve.route(
        "PUT",
        "/api/artifact",
        {
            "repo": str(repo),
            "node": "problem-statement",
            "version": loaded["version"],
        },
        b"The app wrote this.\n",
    )
    assert response.status == 409
    body = _json(response)
    assert "Claude wrote this." in body["text"]
    assert body["version"]


def test_a_refused_save_leaves_the_file_untouched(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "Original.", "A summary.")
    serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement", "version": "nonsense"},
        b"clobbered\n",
    )
    on_disk = artifacts.artifact_path(repo, "problem-statement").read_text("utf-8")
    assert "Original." in on_disk


def test_saving_with_the_current_version_succeeds(tmp_path, monkeypatch):
    from throughline import artifacts

    repo = _project(tmp_path, monkeypatch)
    artifacts.write_artifact(repo, "problem-statement", "Original.", "A summary.")
    loaded = _json(
        serve.route(
            "GET", "/api/artifact", {"repo": str(repo), "node": "problem-statement"}, b""
        )
    )
    response = serve.route(
        "PUT",
        "/api/artifact",
        {
            "repo": str(repo),
            "node": "problem-statement",
            "version": loaded["version"],
        },
        b"Edited by hand.\n",
    )
    assert response.status == 200
    assert response.body and _json(response)["version"] != loaded["version"]


def test_saving_an_artifact_writes_the_file_verbatim(tmp_path, monkeypatch):
    """Rule 10: the file is the truth, so an edit is stored as typed."""
    repo = _project(tmp_path, monkeypatch)
    from throughline import artifacts

    artifacts.write_artifact(repo, "problem-statement", "Old.", "A summary.")
    edited = "# Problem statement\n\n> A summary.\n\nNew body, hand written.\n"
    response = serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement"},
        edited.encode("utf-8"),
    )
    assert response.status == 200
    on_disk = artifacts.artifact_path(repo, "problem-statement").read_text(
        encoding="utf-8"
    )
    assert on_disk == edited


def test_saving_does_not_rewrite_line_endings(tmp_path, monkeypatch):
    """Verbatim means byte for byte.

    Python's text write translates newlines to the platform's by default,
    so on Windows a body sent with LF lands on disk as CRLF. That is the
    file being edited by the tool rather than by its owner.
    """
    repo = _project(tmp_path, monkeypatch)
    from throughline import artifacts

    artifacts.write_artifact(repo, "problem-statement", "Old.", "A summary.")
    body = b"# Problem statement\n\n> A summary.\n\nExactly these bytes.\n"
    serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(repo), "node": "problem-statement"},
        body,
    )
    assert artifacts.artifact_path(repo, "problem-statement").read_bytes() == body


def test_a_folder_with_a_pipeline_can_be_tracked_from_the_app(tmp_path, monkeypatch):
    """The one thing the app could not do.

    Every other endpoint refuses a repo the registry has not heard of,
    which is exactly what a folder being added always is.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "fresh"
    repo.mkdir()
    state.init(repo, "Fresh", {})

    response = serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    assert response.status == 200
    assert repo.resolve() in registry.projects()


def test_adding_a_folder_with_no_pipeline_is_refused(tmp_path, monkeypatch):
    """404 here means one thing only, so the app can act on it.

    A missing folder is a bad argument and answers 400. Only "there is
    no pipeline in it" answers 404, which is what tells the app to
    create one.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    bare = tmp_path / "bare"
    bare.mkdir()

    response = serve.route("POST", "/api/add", {"path": str(bare)}, b"")
    assert response.status == 404
    assert registry.projects() == []


def test_adding_a_folder_that_is_not_there_is_a_bad_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    response = serve.route(
        "POST", "/api/add", {"path": str(tmp_path / "nope")}, b""
    )
    assert response.status == 400


def test_adding_a_file_rather_than_a_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    lonely = tmp_path / "notes.md"
    lonely.write_text("hello", encoding="utf-8")
    response = serve.route("POST", "/api/add", {"path": str(lonely)}, b"")
    assert response.status == 400


def test_adding_a_folder_twice_is_harmless(tmp_path, monkeypatch):
    """registry.add already no-ops on a repeat. Say so in a test."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "fresh"
    repo.mkdir()
    state.init(repo, "Fresh", {})

    serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    serve.route("POST", "/api/add", {"path": str(repo)}, b"")
    assert registry.projects() == [repo.resolve()]


def test_a_pipeline_can_be_created_from_the_app(tmp_path, monkeypatch):
    """Mirrors cmd_init, including which nodes the flags switch on."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps(
        {
            "path": str(repo),
            "project": "Bare",
            "flags": ["has_db"],
            "target_side": True,
            "task_only": False,
        }
    ).encode("utf-8")

    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 200

    loaded = state.load(repo)
    assert loaded.project == "Bare"
    assert loaded.flags["has_db"] is True
    assert loaded.flags["has_state"] is False
    assert loaded.target_side is True
    assert loaded.task_only is False


def test_creating_a_pipeline_can_make_a_task_only_repo(tmp_path, monkeypatch):
    """Task-only is the mode the Setup screen exists for."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "client"
    repo.mkdir()
    body = json.dumps(
        {"path": str(repo), "project": "Client", "task_only": True}
    ).encode("utf-8")

    serve.route("POST", "/api/init", {}, body)
    assert state.load(repo).task_only is True


def test_creating_a_pipeline_over_an_existing_one_is_refused(tmp_path, monkeypatch):
    """Same refusal as cmd_init, and the file must not move."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "taken"
    repo.mkdir()
    state.init(repo, "Original", {})
    before = state.state_path(repo).read_bytes()

    body = json.dumps({"path": str(repo), "project": "Usurper"}).encode("utf-8")
    response = serve.route("POST", "/api/init", {}, body)

    assert response.status == 409
    assert state.state_path(repo).read_bytes() == before


def test_creating_a_pipeline_never_creates_the_folder(tmp_path, monkeypatch):
    """state.save calls mkdir(parents=True).

    Over HTTP that turns one mistyped character into a directory tree
    somewhere nobody asked for.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    missing = tmp_path / "not" / "there"

    body = json.dumps({"path": str(missing), "project": "Ghost"}).encode("utf-8")
    response = serve.route("POST", "/api/init", {}, body)

    assert response.status == 400
    assert not missing.exists()
    assert not (tmp_path / "not").exists()


def test_creating_a_pipeline_needs_a_name(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps({"path": str(repo), "project": "   "}).encode("utf-8")
    assert serve.route("POST", "/api/init", {}, body).status == 400


def test_an_unknown_flag_is_refused(tmp_path, monkeypatch):
    """Flags are an allow-list, like node ids are."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps(
        {"path": str(repo), "project": "Bare", "flags": ["has_teeth"]}
    ).encode("utf-8")

    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 400
    assert not state.exists(repo)


def test_a_non_iterable_flags_value_is_refused(tmp_path, monkeypatch):
    """A number, not a string - a string would prove nothing here.

    ``{"flags": "has_db"}`` is iterable, so without the isinstance
    guard it would iterate characters and still land on a clean
    ``400: no such flag: h`` - the same answer with or without the
    guard, pinning nothing. A truthy, non-iterable JSON scalar like a
    number, a float, or a bool is the only input that reaches the bare
    `for name in asked` loop and raises `TypeError` instead, which
    nothing between there and `Handler._respond` catches.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    repo = tmp_path / "bare"
    repo.mkdir()
    body = json.dumps(
        {"path": str(repo), "project": "Bare", "flags": 42}
    ).encode("utf-8")

    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 400
    assert not state.exists(repo)


def test_a_body_that_is_not_json_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    assert serve.route("POST", "/api/init", {}, b"not json").status == 400


def test_the_flags_are_served_with_what_each_one_adds(tmp_path, monkeypatch):
    """The form must not keep its own copy of this list.

    app.js already hardcodes PHASES, duplicating nodes.py. A second copy
    of the same kind would drift the moment a flag is added or removed.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    payload = _json(serve.route("GET", "/api/flags", {}, b""))

    assert [item["name"] for item in payload] == list(nodes.FLAGS)
    by_name = {item["name"]: item["adds"] for item in payload}
    assert by_name["has_db"] == "ER / relational model"
    assert by_name["has_state"] == "State machine"


def test_a_flag_that_switches_on_nothing_says_so(tmp_path, monkeypatch):
    """has_ui is declared but no node declares it.

    Until that is resolved the form must describe it honestly rather
    than offer a checkbox that quietly does nothing.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    payload = _json(serve.route("GET", "/api/flags", {}, b""))
    assert {"name": "has_ui", "adds": None} in payload


def test_the_running_server_actually_enforces_the_origin_check():
    """route() is not what ships - Handler._respond is.

    Every Origin test above calls route() directly and hands it headers
    by hand, so none of them would notice if Handler._respond stopped
    passing self.headers through to route(). Delete that one argument
    and every test above still passes while the guard goes dark in
    production, because route()'s default `headers=None` reads as
    "allowed". This binds a real socket and sends a real request, so
    the wiring itself is what is under test, not just the function it
    wires to.
    """
    server = serve.make_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(
                "POST",
                "/api/promote",
                body=b"",
                headers={
                    "Origin": "http://evil.example",
                    "Host": f"127.0.0.1:{port}",
                },
            )
            response = conn.getresponse()
            response.read()
            assert response.status == 403
        finally:
            conn.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_a_request_addressed_to_a_foreign_host_is_refused_on_a_get(
    tmp_path, monkeypatch
):
    """DNS rebinding defeats the same-origin check alone.

    A page served from evil.example, with a short DNS TTL, can flip its
    own record to 127.0.0.1 after the browser has loaded it. From then
    on the browser treats http://evil.example:PORT as same-origin with
    the sidecar - Origin and Host both read evil.example:PORT, so
    _origin_ok's "do Origin and Host agree" check is satisfied outright.
    Same-origin also means the page can read the response, so a GET is
    exactly as exposed as a POST once this works - the Host itself has
    to be checked against loopback, on every method, not just writes.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    response = serve.route(
        "GET", "/api/projects", {}, b"", {"Host": "evil.example:7373"}
    )
    assert response.status == 403


def test_dns_rebinding_cannot_forge_a_same_origin_write(tmp_path, monkeypatch):
    """The exact rebinding scenario: Origin and Host agree, both foreign.

    Without a Host check, this passes _origin_ok's same-origin
    comparison and reaches the route - the failure mode a same-origin
    check alone cannot catch, because the attacker controls both
    headers and can make them match each other perfectly.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    response = serve.route(
        "POST",
        "/api/promote",
        {},
        b"",
        {"Origin": "http://evil.example:7373", "Host": "evil.example:7373"},
    )
    assert response.status == 403


def test_loopback_hosts_are_allowed_in_every_spelling(tmp_path, monkeypatch):
    """127.0.0.1, localhost, and the IPv6 literal are all this machine.

    The IPv6 form arrives bracketed - "[::1]:7373" - so a plain
    str.split(":") would cut it at the wrong colon; this is here so
    that particular mistake fails loudly instead of quietly rejecting
    every IPv6 loopback caller.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    for host in ("127.0.0.1:7373", "localhost:7373", "[::1]:7373"):
        response = serve.route("GET", "/api/projects", {}, b"", {"Host": host})
        assert response.status == 200


def test_a_request_with_no_host_header_is_allowed(tmp_path, monkeypatch):
    """Missing Host means a terminal client, not a browser.

    Same reasoning as a missing Origin: real browsers always send Host,
    so its absence is curl or the CLI, not a page that found the port.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    response = serve.route(
        "GET", "/api/projects", {}, b"", {"X-Something": "value"}
    )
    assert response.status == 200


def test_a_non_string_path_is_refused_rather_than_crashing(tmp_path, monkeypatch):
    """The twin of the flags-scalar bug, in the same function.

    A string is the wrong counter-test here, for the same reason as
    with flags: any string is a valid argument to Path(), so it would
    exercise a different branch entirely and pin nothing. `Path(raw)`
    raises TypeError on a non-string, non-PathLike argument, and a
    truthy JSON number is exactly what survives `if not raw` and
    reaches Path() with no check in front of it.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    body = json.dumps({"path": 42, "project": "X"}).encode("utf-8")
    response = serve.route("POST", "/api/init", {}, body)
    assert response.status == 400


def test_a_json_array_body_is_refused_rather_than_crashing(tmp_path, monkeypatch):
    """The direct twin of the flags-list guard, one level up.

    `[]` parses as valid JSON but is not a JSON object, so `.get(...)`
    on it would raise AttributeError rather than answer a clean 400.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    response = serve.route("POST", "/api/init", {}, b"[]")
    assert response.status == 400


def test_the_project_says_whether_setup_has_been_written(tmp_path, monkeypatch):
    """The front door picks between two actions on this one fact.

    A property of the repo, like task_only - never a count of what is
    owed. It says a document exists; it never says one is missing.
    """
    from throughline import setup as setup_module

    repo = _project(tmp_path, monkeypatch)
    first = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert first["has_setup"] is False

    setup_module.write(repo, "A Vue client app.", "What this is.")
    second = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert second["has_setup"] is True


def test_knowing_about_setup_adds_no_count_of_outstanding_work(tmp_path, monkeypatch):
    """has_setup must not become a back door for rule 9."""
    repo = _project(tmp_path, monkeypatch)
    body = (
        serve.route("GET", "/api/project", {"repo": str(repo)}, b"")
        .body.decode("utf-8")
        .lower()
    )
    assert "remaining" not in body
    assert "outstanding" not in body
    assert "todo" not in body


def test_a_repo_can_be_handed_over_for_setup(tmp_path, monkeypatch):
    """Setup is a hand-off like any other, so it lives here.

    Unlike a node id, nothing the caller sent reaches this prompt - there
    is no id to check against the graph because there is no id.
    """
    repo = _project(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append((r, p)))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls[0][0] == repo.resolve()
    assert "set this repo up" in calls[0][1].lower()


def test_asking_for_a_node_and_setup_at_once_is_refused(tmp_path, monkeypatch):
    """Two different hand-offs, and guessing between them would be worse."""
    repo = _project(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(p))
    response = serve.route(
        "POST",
        "/api/start",
        {"repo": str(repo), "setup": "1", "node": "problem-statement"},
        b"",
    )
    assert response.status == 400
    assert calls == []


def test_setup_still_refuses_an_untracked_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(stranger), "setup": "1"}, b""
    )
    assert response.status == 403


def test_setup_reports_when_claude_is_missing(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)

    def boom(_repo, _prompt, _name):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(serve, "spawn_agent", boom)
    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    assert "claude" in _json(response)["error"].lower()


def test_a_task_can_be_started_from_a_ticket(tmp_path, monkeypatch):
    """The app's own work, unlike setup.

    A task title is one line the user is already reading off a ticket, not
    an interview - so this mirrors the promote path rather than opening a
    terminal to capture a string.
    """
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/task",
        {"repo": str(repo), "title": "Fix VAT on credit notes"},
        b"",
    )
    assert response.status == 200

    slug = _json(response)["slug"]
    made = [t for t in tasks_module.all_tasks(repo) if t.slug == slug]
    assert len(made) == 1
    assert made[0].title == "Fix VAT on credit notes"
    assert made[0].origin == "ticket"


def test_a_started_task_can_carry_its_ticket_reference(tmp_path, monkeypatch):
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    response = serve.route(
        "POST",
        "/api/task",
        {"repo": str(repo), "title": "Fix VAT", "reference": "ERP-4821"},
        b"",
    )
    slug = _json(response)["slug"]
    made = [t for t in tasks_module.all_tasks(repo) if t.slug == slug]
    assert made[0].reference == "ERP-4821"


def test_a_task_with_no_title_is_refused(tmp_path, monkeypatch):
    """Whitespace is not a title, and nothing is written for one."""
    from throughline import tasks as tasks_module

    repo = _project(tmp_path, monkeypatch)
    for attempt in ("", "   "):
        response = serve.route(
            "POST", "/api/task", {"repo": str(repo), "title": attempt}, b""
        )
        assert response.status == 400
    assert tasks_module.all_tasks(repo) == []


def test_starting_a_task_refuses_an_untracked_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    state.init(stranger, "Stranger", {})
    response = serve.route(
        "POST", "/api/task", {"repo": str(stranger), "title": "Nope"}, b""
    )
    assert response.status == 403


def test_a_started_task_is_immediately_the_next_thing(tmp_path, monkeypatch):
    """The point of creating it here: the front door has to move on.

    Without this the app would create a task and still show nothing to
    do, which is the dead end this whole change exists to close.
    """
    repo = _project(tmp_path, monkeypatch)
    serve.route("POST", "/api/task", {"repo": str(repo), "title": "Fix VAT"}, b"")
    payload = _json(serve.route("GET", "/api/project", {"repo": str(repo)}, b""))
    assert payload["task"]
    assert payload["next"] == "understand"


def test_a_stored_agent_is_used(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls == ["opencode"]
    assert _json(response)["agent"] == "opencode"


def test_a_stored_agent_that_is_gone_says_where_to_change_it(tmp_path, monkeypatch):
    """'Not found' with nowhere to go is a dead end, not an error."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    error = _json(response)["error"]
    assert "opencode" in error
    assert str(agents.setting_path()) in error
    assert calls == []


def test_the_only_installed_agent_is_used_and_remembered(tmp_path, monkeypatch):
    """One agent on the machine is not a decision worth interrupting for."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: ["opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 200
    assert calls == ["opencode"]
    stored = tmp_path / "home" / "agent"
    assert stored.read_text(encoding="utf-8").strip() == "opencode"


def test_both_installed_and_nothing_chosen_asks(tmp_path, monkeypatch):
    """Guessing would open a session under an agent nobody picked."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])
    calls = []
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: calls.append(n))

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 409
    assert _json(response)["choose"] == ["claude", "opencode"]
    assert calls == []


def test_no_agent_at_all_names_both(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(agents, "chosen", lambda: None)
    monkeypatch.setattr(agents, "installed", lambda: [])
    # Stubbed even though resolution should refuse first: without it, a
    # regression here opens a real console on whoever runs the tests.
    monkeypatch.setattr(serve, "spawn_agent", lambda r, p, n: None)

    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "setup": "1"}, b""
    )
    assert response.status == 500
    error = _json(response)["error"].lower()
    assert "claude" in error
    assert "opencode" in error


def test_the_agent_endpoint_reports_choice_and_availability(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agents, "chosen", lambda: "opencode")
    monkeypatch.setattr(agents, "installed", lambda: ["claude", "opencode"])

    response = serve.route("GET", "/api/agent", {}, b"")
    assert response.status == 200
    assert _json(response) == {
        "chosen": "opencode",
        "installed": ["claude", "opencode"],
    }


def test_choosing_an_agent_stores_it(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route("POST", "/api/agent", {"name": "opencode"}, b"")
    assert response.status == 200
    stored = tmp_path / "home" / "agent"
    assert stored.read_text(encoding="utf-8").strip() == "opencode"


def test_choosing_an_unknown_agent_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route("POST", "/api/agent", {"name": "cursor"}, b"")
    assert response.status == 400
    assert not (tmp_path / "home" / "agent").exists()


def test_choosing_an_agent_refuses_another_origin(tmp_path, monkeypatch):
    """It writes a file, so it is guarded like everything else that does."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route(
        "POST",
        "/api/agent",
        {"name": "opencode"},
        b"",
        {"Host": "127.0.0.1:7373", "Origin": "http://evil.example"},
    )
    assert response.status == 403
    assert not (tmp_path / "home" / "agent").exists()


def test_choosing_an_agent_refuses_a_foreign_host(tmp_path, monkeypatch):
    """DNS rebinding reaches loopback carrying someone else's Host."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))

    response = serve.route(
        "POST",
        "/api/agent",
        {"name": "opencode"},
        b"",
        {"Host": "attacker.example"},
    )
    assert response.status == 403
    assert not (tmp_path / "home" / "agent").exists()
