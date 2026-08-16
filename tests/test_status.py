from throughline import state, status


def test_next_node_is_the_first_empty_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert status.next_node(loaded) == "problem-statement"


def test_next_node_skips_current_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    assert status.next_node(loaded) == "functional-requirements"


def test_next_node_prefers_an_in_progress_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    loaded.nodes["functional-requirements"].status = state.CURRENT
    loaded.nodes["use-case-diagram"].status = state.CURRENT
    loaded.nodes["domain-model"].status = state.IN_PROGRESS
    assert status.next_node(loaded) == "domain-model"


def test_next_node_prefers_drafted_over_empty(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    for node_id in loaded.nodes:
        loaded.nodes[node_id].status = state.CURRENT
    loaded.nodes["domain-model"].status = state.DRAFTED
    assert status.next_node(loaded) == "domain-model"


def test_next_node_prefers_in_progress_over_drafted(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.DRAFTED
    loaded.nodes["functional-requirements"].status = state.IN_PROGRESS
    assert status.next_node(loaded) == "functional-requirements"


def test_next_node_is_none_when_everything_is_done(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    for node_id in loaded.nodes:
        loaded.nodes[node_id].status = state.CURRENT
    assert status.next_node(loaded) is None


def test_progress_does_not_count_drafted_as_filled(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.DRAFTED
    problem = [p for p in status.progress(loaded) if p.phase == "problem"][0]
    assert problem.filled == 0


def test_progress_counts_only_active_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    design = [p for p in status.progress(loaded) if p.phase == "design"][0]
    assert design.total == 1


def test_progress_counts_flag_enabled_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {"has_db": True})
    design = [p for p in status.progress(loaded) if p.phase == "design"][0]
    assert design.total == 2


def test_progress_fills_current_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.nodes["problem-statement"].status = state.CURRENT
    problem = [p for p in status.progress(loaded) if p.phase == "problem"][0]
    assert problem.filled == 1


def test_progress_omits_phases_with_no_active_nodes(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert "code" not in [p.phase for p in status.progress(loaded)]


def test_compute_carries_the_memory_jog(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    loaded.last_note = "deciding whether a cover belongs to a clip"
    result = status.compute(loaded)
    assert result.where_you_left_off == "deciding whether a cover belongs to a clip"


def test_compute_falls_back_when_there_is_no_note(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    result = status.compute(loaded)
    assert result.where_you_left_off == status.NO_NOTE


def test_compute_names_the_next_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    result = status.compute(loaded)
    assert result.next_title == "Problem statement"


def test_render_text_shows_one_next_action(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    text = status.render_text(status.compute(loaded))
    assert text.count("Next:") == 1


def test_render_text_never_reports_a_stale_count(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    text = status.render_text(status.compute(loaded)).lower()
    assert "stale" not in text
    assert "overdue" not in text


def test_compute_reports_answers_already_given_for_the_next_node(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "a")
    state.record_answer(tmp_path, "problem-statement", "q2", "b")
    result = status.compute(state.load(tmp_path))
    assert result.answered == ["q1", "q2"]


def test_compute_reports_nothing_answered_for_an_untouched_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert status.compute(loaded).answered == []


def test_render_text_names_the_questions_already_answered(tmp_path):
    state.init(tmp_path, "demo", {})
    state.record_answer(tmp_path, "problem-statement", "q1", "a")
    text = status.render_text(status.compute(state.load(tmp_path)))
    assert "q1" in text
