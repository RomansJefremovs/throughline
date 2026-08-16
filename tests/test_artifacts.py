import pytest

from throughline import artifacts


def test_artifacts_are_written_with_lf_line_endings(tmp_path):
    """One line ending everywhere, so an app edit is not a whole-file diff.

    A browser textarea hands back LF whatever it was given. If artifacts
    were written CRLF on Windows, the first save through the app would
    rewrite every line of the file - a diff the user never made.
    """
    artifacts.write_artifact(tmp_path, "problem-statement", "A body.", "A summary.")
    raw = artifacts.artifact_path(tmp_path, "problem-statement").read_bytes()
    assert b"\r\n" not in raw


def test_artifact_path_uses_the_node_filename(tmp_path):
    path = artifacts.artifact_path(tmp_path, "domain-model")
    assert path == tmp_path / "docs" / "project" / "glossary.md"


def test_artifact_path_substitutes_a_slug(tmp_path):
    path = artifacts.artifact_path(tmp_path, "activity-diagram", slug="posting-flow")
    assert path.name == "activity-posting-flow.md"


def test_artifact_path_requires_a_slug_for_on_demand_nodes(tmp_path):
    with pytest.raises(ValueError):
        artifacts.artifact_path(tmp_path, "activity-diagram")


def test_read_artifact_returns_none_when_absent(tmp_path):
    assert artifacts.read_artifact(tmp_path, "domain-model") is None


def test_write_then_read_round_trips(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body text.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert "Body text." in text


def test_write_artifact_starts_with_the_title(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert text.startswith("# Problem statement\n")


def test_write_artifact_includes_the_summary_as_a_blockquote(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "A summary.")
    text = artifacts.read_artifact(tmp_path, "problem-statement")
    assert "> A summary." in text


def test_write_artifact_creates_missing_directories(tmp_path):
    path = artifacts.write_artifact(tmp_path, "problem-statement", "Body.", "S.")
    assert path.is_file()


def test_summary_of_extracts_the_blockquote():
    text = "# Title\n\n> The one-line summary.\n\nBody.\n"
    assert artifacts.summary_of(text) == "The one-line summary."


def test_summary_of_returns_empty_when_absent():
    assert artifacts.summary_of("# Title\n\nBody.\n") == ""


def test_summary_of_ignores_blockquotes_after_body_text():
    text = "# Title\n\nBody first.\n\n> Not the summary.\n"
    assert artifacts.summary_of(text) == ""


def test_mermaid_kinds_cover_every_rendering_node():
    from throughline import nodes

    for node in nodes.all_nodes():
        if node.renders != "markdown":
            assert node.renders in artifacts.MERMAID_KINDS
