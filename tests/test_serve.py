import json
import re

from throughline import registry, serve, state


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
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: calls.append(p))

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
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
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
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: calls.append((r, p)))

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
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(stranger), "node": "x"}, b""
    )
    assert response.status == 403


def test_start_refuses_an_unknown_node(tmp_path, monkeypatch):
    """The node id reaches a shell, so it is checked against the graph."""
    repo = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(serve, "spawn_claude", lambda r, p: None)
    response = serve.route(
        "POST", "/api/start", {"repo": str(repo), "node": "rm -rf /"}, b""
    )
    assert response.status == 400


def test_start_reports_when_claude_is_missing(tmp_path, monkeypatch):
    repo = _project(tmp_path, monkeypatch)

    def boom(_repo, _prompt):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(serve, "spawn_claude", boom)
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
