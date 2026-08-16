import json

import pytest

from throughline import cli, state


def run(capsys, *args):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out


def test_parse_flags_reads_true():
    assert cli.parse_flags(["has_db=true"]) == {"has_db": True}


def test_parse_flags_reads_false():
    assert cli.parse_flags(["has_db=false"]) == {"has_db": False}


def test_parse_flags_rejects_an_unknown_name():
    with pytest.raises(SystemExit):
        cli.parse_flags(["nonsense=true"])


def test_parse_flags_rejects_a_missing_equals():
    with pytest.raises(SystemExit):
        cli.parse_flags(["has_db"])


def test_init_creates_the_pipeline(tmp_path, capsys):
    code, _ = run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    assert code == 0
    assert state.exists(tmp_path)


def test_init_applies_flags(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo", "--flag", "has_db=true")
    assert state.load(tmp_path).flags["has_db"] is True


def test_init_refuses_to_overwrite(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "init", "--repo", str(tmp_path), "--project", "other")
    assert code == 1
    assert "already" in out


def test_nodes_lists_active_ids(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "nodes", "--repo", str(tmp_path), "--json")
    assert code == 0
    payload = json.loads(out)
    assert "problem-statement" in [n["id"] for n in payload]


def test_nodes_omits_inactive_flag_nodes(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "nodes", "--repo", str(tmp_path), "--json")
    assert "er-model" not in [n["id"] for n in json.loads(out)]


def test_context_reports_line_count(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "context", "domain-model", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["line_count"] == 0


def test_answer_persists(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(capsys, "answer", "problem-statement", "q1", "yes", "--repo", str(tmp_path))
    assert code == 0
    assert state.load(tmp_path).nodes["problem-statement"].answers["q1"] == "yes"


def test_write_marks_the_node_current(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "A summary.",
        "--body", "The body.",
        "--note", "wrote the problem statement",
    )
    assert code == 0
    loaded = state.load(tmp_path)
    assert loaded.nodes["problem-statement"].status == state.CURRENT
    assert loaded.last_note == "wrote the problem statement"


def test_write_drafted_marks_the_node_drafted(tmp_path, capsys):
    """A drafted node is written by Claude and read by nobody yet."""
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "A summary.",
        "--body", "The body.",
        "--drafted",
    )
    assert code == 0
    assert state.load(tmp_path).nodes["problem-statement"].status == state.DRAFTED


def test_confirm_promotes_a_drafted_node_to_current(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "A summary.",
        "--body", "The body.",
        "--drafted",
    )
    code, _ = run(capsys, "confirm", "problem-statement", "--repo", str(tmp_path))
    assert code == 0
    assert state.load(tmp_path).nodes["problem-statement"].status == state.CURRENT


def test_confirm_refuses_a_node_with_no_artifact(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(capsys, "confirm", "problem-statement", "--repo", str(tmp_path))
    assert code == 1


def test_write_accepts_a_body_file(tmp_path, capsys):
    """A markdown body cannot survive as a shell argument.

    Real use hit this immediately: a body containing brackets and newlines
    was word-split by the shell before argparse ever saw it.
    """
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    source = tmp_path / "body.md"
    source.write_text("# Heading\n\nflowchart LR\n  a[Node one] --> b[Node two]\n", encoding="utf-8")

    code, _ = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "s",
        "--body-file", str(source),
    )
    assert code == 0
    from throughline import artifacts

    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert "a[Node one] --> b[Node two]" in text


def test_write_rejects_both_body_and_body_file(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    source = tmp_path / "body.md"
    source.write_text("x", encoding="utf-8")

    code, out = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "s",
        "--body", "inline",
        "--body-file", str(source),
    )
    assert code == 1
    assert "not both" in out


def test_write_requires_one_of_body_or_body_file(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s")
    assert code == 1
    assert "--body" in out


def test_write_reports_a_missing_body_file(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path),
        "--summary", "s",
        "--body-file", str(tmp_path / "nope.md"),
    )
    assert code == 1
    assert "no such file" in out.lower()


def test_write_stamps_upstream_hashes(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "functional-requirements", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "domain-model", "--repo", str(tmp_path), "--summary", "s", "--body", "b")

    loaded = state.load(tmp_path)
    assert loaded.nodes["domain-model"].upstream_hashes != {}


def test_status_names_the_next_node(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "status", "--repo", str(tmp_path))
    assert code == 0
    assert "Problem statement" in out


def test_status_json_carries_the_answers_already_given(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "answer", "problem-statement", "q1", "x", "--repo", str(tmp_path))
    code, out = run(capsys, "status", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["answered"] == ["q1"]


def test_add_tracks_a_repo_for_the_app(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, _ = run(capsys, "add", "--repo", str(tmp_path))
    assert code == 0
    from throughline import registry

    assert registry.projects() == [tmp_path.resolve()]


def test_add_refuses_a_repo_with_no_pipeline(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    code, _ = run(capsys, "add", "--repo", str(tmp_path))
    assert code == 1


def test_projects_lists_tracked_repos(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "add", "--repo", str(tmp_path))
    code, out = run(capsys, "projects", "--json")
    assert code == 0
    assert json.loads(out)[0]["project"] == "demo"


def test_forget_stops_tracking_a_repo(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "add", "--repo", str(tmp_path))
    code, _ = run(capsys, "forget", "--repo", str(tmp_path))
    assert code == 0
    from throughline import registry

    assert registry.projects() == []


TWO_SIDED = """# Current

It is like this.

# Target

## Scope accounts to the project

`credentials` needs `project_id`.
"""


def _two_sided(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo", "--target-side")
    run(
        capsys, "write", "architecture",
        "--repo", str(tmp_path), "--summary", "Two sides.", "--body-file",
        str(_body_file(tmp_path)),
    )


def _body_file(tmp_path):
    path = tmp_path / "body.md"
    path.write_bytes(TWO_SIDED.encode("utf-8"))
    return path


def _write_node(capsys, tmp_path, body="The body."):
    return run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path), "--summary", "A summary.", "--body", body,
    )


def test_writing_records_what_it_wrote(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path)
    assert state.load(tmp_path).nodes["problem-statement"].artifact_hash


def test_writing_twice_in_a_row_is_fine(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path, "First.")
    code, _ = _write_node(capsys, tmp_path, "Second.")
    assert code == 0


def test_writing_over_a_hand_edit_is_refused(tmp_path, capsys):
    """Rule 10 cuts both ways. The user's own words are the truth too."""
    from throughline import artifacts

    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path, "What Claude wrote.")

    path = artifacts.artifact_path(tmp_path, "problem-statement")
    path.write_bytes(b"# Problem statement\n\n> S.\n\nWhat the user wrote.\n")

    code, out = _write_node(capsys, tmp_path, "Claude writing again.")
    assert code == 1
    assert "What the user wrote." in path.read_text(encoding="utf-8")


def test_a_refused_write_says_how_to_proceed(tmp_path, capsys):
    """A refusal that does not say what to do next is just a wall."""
    from throughline import artifacts

    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path)
    artifacts.artifact_path(tmp_path, "problem-statement").write_bytes(b"edited\n")

    cli.main([
        "write", "problem-statement",
        "--repo", str(tmp_path), "--summary", "S.", "--body", "b",
    ])
    complaint = capsys.readouterr().err
    assert "edited since" in complaint
    assert "--force" in complaint


def test_force_overwrites_a_hand_edit(tmp_path, capsys):
    from throughline import artifacts

    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path)
    artifacts.artifact_path(tmp_path, "problem-statement").write_bytes(b"edited\n")

    code, _ = run(
        capsys, "write", "problem-statement",
        "--repo", str(tmp_path), "--summary", "S.", "--body", "Claude insists.",
        "--force",
    )
    assert code == 0
    written = artifacts.artifact_path(tmp_path, "problem-statement").read_text("utf-8")
    assert "Claude insists." in written


def test_an_app_save_protects_the_text_too(tmp_path, capsys, monkeypatch):
    """Editing in the app is the user writing, not the tool writing.

    So it earns the same protection a Notepad edit gets: Claude cannot
    overwrite it without being told to.
    """
    from throughline import artifacts, registry, serve

    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _write_node(capsys, tmp_path)
    registry.add(tmp_path)

    serve.route(
        "PUT",
        "/api/artifact",
        {"repo": str(tmp_path), "node": "problem-statement"},
        b"# Problem statement\n\n> S.\n\nEdited in the app.\n",
    )

    code, _ = _write_node(capsys, tmp_path, "Claude writing after an app save.")
    assert code == 1
    kept = artifacts.artifact_path(tmp_path, "problem-statement").read_text("utf-8")
    assert "Edited in the app." in kept


def test_init_can_make_a_repo_task_only(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "geedie", "--task-only")
    assert state.load(tmp_path).task_only is True
    code, out = run(capsys, "next", "--repo", str(tmp_path))
    assert out.strip() == ""


def test_detect_reports_what_the_repo_is_wired_to(tmp_path, capsys):
    (tmp_path / ".mcp.json").write_bytes(b'{"mcpServers": {"trello": {}}}')
    code, out = run(capsys, "detect", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["mcp_servers"] == ["trello"]


def test_detect_works_before_init(tmp_path, capsys):
    """Detection is how setup starts, so it cannot require a pipeline."""
    code, _ = run(capsys, "detect", "--repo", str(tmp_path))
    assert code == 0


def test_setup_writes_the_document(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "geedie", "--task-only")
    code, _ = run(
        capsys, "setup",
        "--repo", str(tmp_path),
        "--summary", "A Vue client app.",
        "--body", "Vocabulary: a board is a Trello board.",
    )
    assert code == 0
    written = (tmp_path / "docs" / "project" / "setup.md").read_text(encoding="utf-8")
    assert "Vocabulary: a board is a Trello board." in written


def test_setup_requires_a_body(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "geedie", "--task-only")
    code, _ = run(capsys, "setup", "--repo", str(tmp_path), "--summary", "S.")
    assert code == 1


def test_init_can_turn_the_target_side_on(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo", "--target-side")
    assert state.load(tmp_path).target_side is True


def test_target_command_flips_the_switch(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "target", "on", "--repo", str(tmp_path))
    assert state.load(tmp_path).target_side is True
    run(capsys, "target", "off", "--repo", str(tmp_path))
    assert state.load(tmp_path).target_side is False


def test_gaps_lists_the_target_side_differences(tmp_path, capsys):
    _two_sided(tmp_path, capsys)
    code, out = run(capsys, "gaps", "--repo", str(tmp_path), "--json")
    assert code == 0
    listed = json.loads(out)
    assert listed[0]["title"] == "Scope accounts to the project"
    assert listed[0]["node"] == "architecture"


def test_gaps_is_quiet_when_there_are_none(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "gaps", "--repo", str(tmp_path))
    assert code == 0
    assert "no gaps" in out.lower()


def test_promote_turns_one_gap_into_a_task(tmp_path, capsys):
    _two_sided(tmp_path, capsys)
    code, out = run(
        capsys, "promote", "architecture", "Scope accounts to the project",
        "--repo", str(tmp_path), "--json",
    )
    assert code == 0
    from throughline import tasks

    slug = json.loads(out)["slug"]
    assert tasks.next_node(tasks.load(tmp_path, slug)) == "analyze"


def test_promote_refuses_a_gap_that_is_not_there(tmp_path, capsys):
    _two_sided(tmp_path, capsys)
    code, _ = run(
        capsys, "promote", "architecture", "Something nobody wrote",
        "--repo", str(tmp_path),
    )
    assert code == 1


def test_task_new_creates_a_task(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(
        capsys, "task", "new", "Fix the metrics display",
        "--repo", str(tmp_path), "--origin", "ticket", "--reference", "TRELLO-14",
        "--json",
    )
    assert code == 0
    from throughline import tasks

    slug = json.loads(out)["slug"]
    assert tasks.load(tmp_path, slug).reference == "TRELLO-14"


def test_task_list_is_quiet_when_there_are_none(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "task", "list", "--repo", str(tmp_path))
    assert code == 0
    assert "no tasks" in out.lower()


def test_task_answer_then_write_advances_the_task(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "task", "new", "Fix it", "--repo", str(tmp_path), "--json")
    slug = json.loads(out)["slug"]

    run(capsys, "task", "answer", slug, "understand", "q1", "x", "--repo", str(tmp_path))
    code, _ = run(
        capsys, "task", "write", slug, "understand",
        "--repo", str(tmp_path), "--summary", "A summary.", "--body", "The body.",
    )
    assert code == 0
    code, out = run(capsys, "next", "--repo", str(tmp_path))
    assert out.strip() == "analyze"


def test_task_write_requires_a_body(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "task", "new", "Fix it", "--repo", str(tmp_path), "--json")
    slug = json.loads(out)["slug"]
    code, _ = run(
        capsys, "task", "write", slug, "understand",
        "--repo", str(tmp_path), "--summary", "A summary.",
    )
    assert code == 1


def test_task_abandon_gives_the_slot_back(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "task", "new", "Fix it", "--repo", str(tmp_path), "--json")
    slug = json.loads(out)["slug"]
    run(capsys, "task", "answer", slug, "understand", "q1", "x", "--repo", str(tmp_path))
    run(capsys, "task", "abandon", slug, "--repo", str(tmp_path))

    code, out = run(capsys, "next", "--repo", str(tmp_path))
    assert out.strip() == "problem-statement"


def test_task_context_scopes_to_the_task(tmp_path, capsys):
    """A task node reads its own upstream, not the whole project."""
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    _, out = run(capsys, "task", "new", "Fix it", "--repo", str(tmp_path), "--json")
    slug = json.loads(out)["slug"]
    run(
        capsys, "task", "write", slug, "understand",
        "--repo", str(tmp_path), "--summary", "A summary.", "--body", "Ticket says X.",
    )
    code, out = run(capsys, "task", "context", slug, "analyze", "--repo", str(tmp_path))
    assert code == 0
    assert "Ticket says X." in out


def test_serve_is_a_command_with_a_port(tmp_path):
    args = cli.build_parser().parse_args(["serve", "--port", "9000"])
    assert args.port == 9000


def test_next_prints_only_the_node_id(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "next", "--repo", str(tmp_path))
    assert code == 0
    assert out.strip() == "problem-statement"


def test_stale_reports_nothing_for_a_fresh_node(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    code, out = run(capsys, "stale", "domain-model", "--repo", str(tmp_path), "--json")
    assert code == 0
    assert json.loads(out)["stale"] is False


def test_stale_detects_an_upstream_change(tmp_path, capsys):
    run(capsys, "init", "--repo", str(tmp_path), "--project", "demo")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "functional-requirements", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "domain-model", "--repo", str(tmp_path), "--summary", "s", "--body", "b")
    run(capsys, "write", "problem-statement", "--repo", str(tmp_path), "--summary", "s", "--body", "different")

    _, out = run(capsys, "stale", "domain-model", "--repo", str(tmp_path), "--json")
    payload = json.loads(out)
    assert payload["stale"] is True
    assert payload["changed"] == ["problem-statement"]


def test_scan_runs_on_an_empty_directory(tmp_path, capsys):
    code, out = run(capsys, "scan", "--repo", str(tmp_path))
    assert code == 0
    assert "## Files" in out


def test_commands_fail_cleanly_without_a_pipeline(tmp_path, capsys):
    code, out = run(capsys, "status", "--repo", str(tmp_path))
    assert code == 1
    assert "no pipeline" in out.lower()
