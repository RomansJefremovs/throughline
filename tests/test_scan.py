from pathlib import Path

from throughline import scan


def test_encode_replaces_each_separator_with_one_dash():
    assert scan.encode_repo_path(Path(r"C:\Dev\UMES")) == "C--Dev-UMES"


def test_encode_handles_a_dot_directory():
    encoded = scan.encode_repo_path(Path(r"C:\Users\roman\.claude"))
    assert encoded == "C--Users-roman--claude"


def test_encode_preserves_internal_dashes():
    assert scan.encode_repo_path(Path(r"C:\Dev\Scissors-Farm")) == "C--Dev-Scissors-Farm"


def test_transcripts_dir_is_under_claude_projects(tmp_path):
    result = scan.transcripts_dir(Path(r"C:\Dev\UMES"), home=tmp_path)
    assert result == tmp_path / ".claude" / "projects" / "C--Dev-UMES"


def test_transcript_files_is_empty_when_the_dir_is_absent(tmp_path):
    assert scan.transcript_files(Path(r"C:\Dev\Nope"), home=tmp_path) == []


def test_transcript_files_finds_jsonl(tmp_path):
    target = tmp_path / ".claude" / "projects" / "C--Dev-UMES"
    target.mkdir(parents=True)
    (target / "a.jsonl").write_text("{}", encoding="utf-8")
    (target / "notes.txt").write_text("x", encoding="utf-8")

    found = scan.transcript_files(Path(r"C:\Dev\UMES"), home=tmp_path)
    assert [p.name for p in found] == ["a.jsonl"]


def test_file_tree_lists_relative_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x", encoding="utf-8")
    tree = scan.file_tree(tmp_path)
    assert "src/main.py" in tree


def test_file_tree_skips_noise_directories(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x", encoding="utf-8")
    tree = scan.file_tree(tmp_path)
    assert tree == ["keep.py"]


def test_file_tree_respects_the_limit(tmp_path):
    for index in range(10):
        (tmp_path / f"f{index}.py").write_text("x", encoding="utf-8")
    assert len(scan.file_tree(tmp_path, limit=4)) == 4


def test_scan_reads_the_readme(tmp_path):
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    assert scan.scan(tmp_path, home=tmp_path).readme == "# Hello"


def test_scan_reads_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("rules", encoding="utf-8")
    assert scan.scan(tmp_path, home=tmp_path).claude_md == "rules"


def test_scan_returns_none_for_absent_files(tmp_path):
    result = scan.scan(tmp_path, home=tmp_path)
    assert result.readme is None
    assert result.claude_md is None


def test_git_log_is_empty_outside_a_repo(tmp_path):
    assert scan.git_log(tmp_path) == []


def test_render_includes_each_section(tmp_path):
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    text = scan.render(scan.scan(tmp_path, home=tmp_path))
    assert "## Files" in text
    assert "## README" in text
