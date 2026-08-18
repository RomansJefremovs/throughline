import os

from throughline import registry, state


def test_registry_path_is_under_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert registry.registry_path().parent == tmp_path


def test_listing_is_empty_before_anything_is_added(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert registry.projects() == []


def test_add_records_a_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()
    registry.add(repo)
    assert registry.projects() == [repo.resolve()]


def test_add_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()
    registry.add(repo)
    registry.add(repo)
    assert len(registry.projects()) == 1


def test_remove_forgets_a_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()
    registry.add(repo)
    registry.remove(repo)
    assert registry.projects() == []


def test_projects_keeps_paths_that_no_longer_exist(tmp_path, monkeypatch):
    """A missing folder is not the same as a forgotten one.

    Silently dropping a repo that is temporarily unmounted would look
    exactly like data loss, so the path is kept and reported as missing.
    """
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    gone = tmp_path / "gone"
    gone.mkdir()
    registry.add(gone)
    gone.rmdir()
    assert registry.projects() == [gone.resolve()]


def test_describe_reports_a_missing_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    gone = tmp_path / "gone"
    gone.mkdir()
    registry.add(gone)
    gone.rmdir()
    assert registry.describe(gone.resolve())["missing"] is True


def test_describe_reports_a_project_name_and_next_node(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()
    state.init(repo, "Demo project", {})
    registry.add(repo)

    described = registry.describe(repo.resolve())
    assert described["project"] == "Demo project"
    assert described["next"] == "problem-statement"
    assert described["missing"] is False


def test_describe_reports_a_folder_with_no_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    repo = tmp_path / "bare"
    repo.mkdir()
    registry.add(repo)
    assert registry.describe(repo.resolve())["tracked"] is False


def test_last_worked_is_none_before_anything_happens(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    assert registry.last_worked() is None


def test_last_worked_is_the_most_recently_updated_project(tmp_path, monkeypatch):
    """The front door opens here, so this has to need no decision."""
    monkeypatch.setenv("THROUGHLINE_HOME", str(tmp_path))
    older = tmp_path / "older"
    newer = tmp_path / "newer"
    for repo in (older, newer):
        repo.mkdir()
        state.init(repo, repo.name, {})
        registry.add(repo)

    state.record_answer(older, "problem-statement", "q1", "x")
    state.record_answer(newer, "problem-statement", "q1", "x")

    # Two writes this close together can land on the same mtime - the
    # clock behind st_mtime is coarser than the writes are - and a tie
    # goes to whichever came first in the registry. That made this test
    # fail about one run in three for a reason the product never had.
    # Stamping both says what the test is actually about.
    os.utime(state.state_path(older), (1_000_000, 1_000_000))
    os.utime(state.state_path(newer), (2_000_000, 2_000_000))

    assert registry.last_worked() == newer.resolve()
