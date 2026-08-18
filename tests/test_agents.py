import pytest

from throughline import agents


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_nothing_chosen_when_the_file_is_absent(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    assert agents.chosen() is None


def test_choosing_writes_one_word(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    agents.choose("opencode")
    assert (home / "agent").read_text(encoding="utf-8") == "opencode\n"
    assert agents.chosen() == "opencode"


def test_an_unknown_name_is_refused(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        agents.choose("cursor")
    assert agents.chosen() is None


def test_garbage_in_the_file_reads_as_unset(tmp_path, monkeypatch):
    """A one-word file with the wrong word in it is not worth an error.

    The worst it costs is one more pick. Refusing to start would be the
    tool getting in its own way.
    """
    home = _home(tmp_path, monkeypatch)
    home.mkdir(parents=True)
    (home / "agent").write_text("emacs\n", encoding="utf-8")
    assert agents.chosen() is None


def test_installed_reports_in_table_order(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")
    assert agents.installed() == ["claude", "opencode"]


def test_installed_is_empty_when_neither_is_on_path(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(agents.shutil, "which", lambda name: None)
    assert agents.installed() == []


def test_claude_takes_its_prompt_positionally():
    argv, environment = agents.command("claude", "do the thing")
    assert argv == ["claude", "do the thing"]
    assert environment == {}


def test_opencode_takes_a_flag_and_needs_the_question_tool_turned_on():
    """Unset, opencode registers no picker at all.

    Verified against the 1.18.12 binary: the builtin tool list is
    `...ro?[H.question]:[]` where `ro` is OPENCODE_ENABLE_QUESTION_TOOL.
    Without it, binding rule 3 has no tool to bind to and every
    interview degrades to prose.
    """
    argv, environment = agents.command("opencode", "do the thing")
    assert argv == ["opencode", "--prompt", "do the thing"]
    assert environment == {"OPENCODE_ENABLE_QUESTION_TOOL": "1"}
