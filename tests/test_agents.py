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


def test_claude_takes_its_prompt_positionally(monkeypatch):
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")
    argv, environment = agents.command("claude", "do the thing")
    assert argv == ["/bin/claude", "do the thing"]
    assert environment == {}


def test_argv_uses_the_resolved_path_not_the_bare_name(monkeypatch):
    """npm installs opencode as a .CMD shim on Windows.

    CreateProcess will not find a .CMD by name the way a shell would, so
    a bare name spawns as "not found" for something `which` has just
    reported as installed - which is the most confusing failure available.
    """
    monkeypatch.setattr(
        agents.shutil, "which", lambda name: rf"C:\shims\{name}.CMD"
    )
    argv, _ = agents.command("opencode", "go")
    assert argv == [r"C:\shims\opencode.CMD", "--prompt", "go"]


def test_an_unresolvable_name_is_left_as_it_is(monkeypatch):
    """Let the spawn raise its own error rather than inventing one here."""
    monkeypatch.setattr(agents.shutil, "which", lambda name: None)
    argv, _ = agents.command("claude", "go")
    assert argv == ["claude", "go"]


def test_opencode_takes_a_flag_and_needs_the_question_tool_turned_on(monkeypatch):
    """opencode's picker is asked for rather than assumed.

    The binary gates its `question` tool on a flag read from this
    variable. Measured against 1.18.12's tool registry, the tool is
    present with the variable set, unset and false alike - so setting it
    pins the behaviour rather than enabling it. Binding rule 3 has no
    picker without that tool, which is a dependency worth stating.
    """
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")
    argv, environment = agents.command("opencode", "do the thing")
    assert argv == ["/bin/opencode", "--prompt", "do the thing"]
    assert environment == {"OPENCODE_ENABLE_QUESTION_TOOL": "1"}
