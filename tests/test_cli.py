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
    assert loaded.nodes["problem-statement"].confirmed is True
    assert loaded.last_note == "wrote the problem statement"


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
