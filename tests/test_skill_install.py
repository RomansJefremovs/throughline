from throughline import skill


def _bundle(tmp_path, monkeypatch):
    """Stand in for the shipped pack so tests do not depend on the repo."""
    source = tmp_path / "bundle"
    (source / "questions").mkdir(parents=True)
    (source / "SKILL.md").write_text("# Throughline\n", encoding="utf-8")
    (source / "questions" / "architecture.md").write_text("q\n", encoding="utf-8")
    monkeypatch.setattr(skill, "bundled", lambda: source)
    return source


def test_the_pack_is_findable_in_a_source_checkout():
    """No monkeypatching: this is the real repo layout, asserted."""
    assert (skill.bundled() / "SKILL.md").is_file()


def test_it_installs_into_an_empty_home(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"

    result = skill.install(home=home)
    assert result["written"] is True
    destination = home / ".claude" / "skills" / "throughline"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "# Throughline\n"
    assert (destination / "questions" / "architecture.md").is_file()


def test_an_identical_copy_is_left_alone(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)

    result = skill.install(home=home)
    assert result["written"] is False
    assert result["differs"] == []


def test_a_changed_copy_is_reported_and_not_touched(tmp_path, monkeypatch):
    """Someone tuned it. Their words are the truth, as with `write`."""
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)
    edited = home / ".claude" / "skills" / "throughline" / "SKILL.md"
    edited.write_text("# Mine\n", encoding="utf-8")

    result = skill.install(home=home)
    assert result["written"] is False
    assert result["differs"] == ["SKILL.md"]
    assert edited.read_text(encoding="utf-8") == "# Mine\n"


def test_force_replaces_a_changed_copy(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    skill.install(home=home)
    edited = home / ".claude" / "skills" / "throughline" / "SKILL.md"
    edited.write_text("# Mine\n", encoding="utf-8")

    result = skill.install(home=home, force=True)
    assert result["written"] is True
    assert edited.read_text(encoding="utf-8") == "# Throughline\n"


def test_present_is_false_until_it_is_installed(tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    home = tmp_path / "home"
    assert skill.present(home) is False
    skill.install(home=home)
    assert skill.present(home) is True
