import pytest
import yaml

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


def test_the_target_side_is_off_by_default(tmp_path):
    """Describing what is comes free. Proposing what should be is a choice."""
    assert state.init(tmp_path, "demo", {}).target_side is False


def test_the_target_side_can_be_turned_on_at_init(tmp_path):
    assert state.init(tmp_path, "demo", {}, target_side=True).target_side is True


def test_the_target_side_is_a_switch_not_a_consequence(tmp_path):
    """Changeable at any time, on any repo, whoever owns it."""
    state.init(tmp_path, "demo", {})
    state.set_target_side(tmp_path, True)
    assert state.load(tmp_path).target_side is True
    state.set_target_side(tmp_path, False)
    assert state.load(tmp_path).target_side is False


def test_drafted_is_a_status(tmp_path):
    assert state.DRAFTED == "drafted"


def test_node_state_has_no_confirmed_flag(tmp_path):
    assert not hasattr(state.NodeState(), "confirmed")


def test_load_migrates_an_unconfirmed_current_node_to_drafted(tmp_path):
    state.init(tmp_path, "demo", {})
    path = state.state_path(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["nodes"]["problem-statement"] = {"status": "current", "confirmed": False}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    assert state.load(tmp_path).nodes["problem-statement"].status == state.DRAFTED


def test_load_leaves_a_confirmed_current_node_alone(tmp_path):
    state.init(tmp_path, "demo", {})
    path = state.state_path(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["nodes"]["problem-statement"] = {"status": "current", "confirmed": True}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    assert state.load(tmp_path).nodes["problem-statement"].status == state.CURRENT


def test_record_answer_refreshes_the_left_off_note(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert "Problem statement" in state.load(tmp_path).last_note


def test_record_answer_note_says_the_interview_is_partway_through(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "x")
    assert "mid-interview" in state.load(tmp_path).last_note.lower()


def test_set_note_records_the_memory_jog(tmp_path):
    state.init(tmp_path, "demo", {})
    state.set_note(tmp_path, "domain-model", "deciding whether a cover belongs to a clip")

    reloaded = state.load(tmp_path)
    assert reloaded.last_note == "deciding whether a cover belongs to a clip"
    assert reloaded.last_node == "domain-model"


def test_utcnow_is_iso_with_z(tmp_path):
    assert state.utcnow().endswith("Z")
    assert "T" in state.utcnow()
