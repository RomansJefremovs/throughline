import pytest

from throughline import state


def test_state_path_is_inside_docs_project(tmp_path):
    assert state.state_path(tmp_path) == tmp_path / "docs" / "project" / "pipeline.yaml"


def test_exists_is_false_before_init(tmp_path):
    assert state.exists(tmp_path) is False


def test_init_creates_the_file(tmp_path):
    state.init(tmp_path, "demo", {"has_db": True})
    assert state.exists(tmp_path) is True


def test_init_records_project_and_flags(tmp_path):
    result = state.init(tmp_path, "demo", {"has_db": True})
    assert result.project == "demo"
    assert result.flags["has_db"] is True


def test_init_defaults_unlisted_flags_to_false(tmp_path):
    result = state.init(tmp_path, "demo", {"has_db": True})
    assert result.flags["has_state"] is False
    assert result.flags["multi_service"] is False


def test_init_seeds_every_active_node_as_empty(tmp_path):
    result = state.init(tmp_path, "demo", {})
    assert result.nodes["problem-statement"].status == state.EMPTY
    assert "er-model" not in result.nodes


def test_load_round_trips_everything(tmp_path):
    original = state.init(tmp_path, "demo", {"has_db": True})
    original.nodes["problem-statement"].status = state.CURRENT
    original.nodes["problem-statement"].answers = {"q1": "yes"}
    original.nodes["problem-statement"].upstream_hashes = {"x": "abc"}
    original.last_note = "deciding on covers"
    state.save(tmp_path, original)

    reloaded = state.load(tmp_path)
    assert reloaded.project == "demo"
    assert reloaded.flags["has_db"] is True
    assert reloaded.nodes["problem-statement"].status == state.CURRENT
    assert reloaded.nodes["problem-statement"].answers == {"q1": "yes"}
    assert reloaded.nodes["problem-statement"].upstream_hashes == {"x": "abc"}
    assert reloaded.last_note == "deciding on covers"


def test_load_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        state.load(tmp_path)


def test_node_state_creates_a_default_entry(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    entry = state.node_state(loaded, "sequence-diagram")
    assert entry.status == state.EMPTY
    assert entry.answers == {}


def test_record_answer_persists_immediately(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "a customer-facing tool")

    reloaded = state.load(tmp_path)
    assert reloaded.nodes["problem-statement"].answers["q1"] == "a customer-facing tool"


def test_record_answer_marks_the_node_in_progress(tmp_path):
    state.init(tmp_path, "demo", {})
    result = state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert result.nodes["problem-statement"].status == state.IN_PROGRESS


def test_record_answer_does_not_downgrade_a_current_node(tmp_path):
    state.init(tmp_path, "demo", {})
    loaded = state.load(tmp_path)
    loaded.nodes["problem-statement"].status = state.CURRENT
    state.save(tmp_path, loaded)

    result = state.record_answer(tmp_path, "problem-statement", "q2", "y")
    assert result.nodes["problem-statement"].status == state.CURRENT


def test_record_answer_stamps_updated(tmp_path):
    state.init(tmp_path, "demo", {})
    result = state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert result.nodes["problem-statement"].updated.endswith("Z")


def test_set_note_records_the_memory_jog(tmp_path):
    state.init(tmp_path, "demo", {})
    state.set_note(tmp_path, "domain-model", "deciding whether a cover belongs to a clip")

    reloaded = state.load(tmp_path)
    assert reloaded.last_note == "deciding whether a cover belongs to a clip"
    assert reloaded.last_node == "domain-model"


def test_utcnow_is_iso_with_z(tmp_path):
    assert state.utcnow().endswith("Z")
    assert "T" in state.utcnow()
