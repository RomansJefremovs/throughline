import pytest

from throughline import nodes, state, tasks


def test_there_are_four_task_nodes():
    assert len(nodes.TASK_NODES) == 4


def test_task_nodes_are_in_order():
    assert [n.id for n in nodes.TASK_NODES] == [
        "understand",
        "analyze",
        "design",
        "verify",
    ]


def test_task_nodes_form_a_line():
    """Each one only makes sense after the one before it."""
    assert nodes.get_task_node("understand").deps == ()
    assert nodes.get_task_node("analyze").deps == ("understand",)
    assert nodes.get_task_node("design").deps == ("analyze",)
    assert nodes.get_task_node("verify").deps == ("design",)


def test_verify_is_the_node_that_pays_for_the_rest():
    assert "verify" in nodes.get_task_node("verify").filename


def test_slug_is_dated_and_readable():
    assert tasks.make_slug("Fix the metrics display", "2026-08-16") == (
        "2026-08-16-fix-the-metrics-display"
    )


def test_slug_strips_punctuation():
    assert tasks.make_slug("Won't render: covers!", "2026-08-16") == (
        "2026-08-16-wont-render-covers"
    )


def test_create_writes_the_task_beside_the_project(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix the metrics display")
    assert (tmp_path / "docs" / "project" / "tasks" / slug / "task.yaml").is_file()


def test_create_records_the_title_and_origin(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it", origin="ticket", reference="TRELLO-14")
    loaded = tasks.load(tmp_path, slug)
    assert loaded.title == "Fix it"
    assert loaded.origin == "ticket"
    assert loaded.reference == "TRELLO-14"


def test_a_new_task_is_open(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    assert tasks.load(tmp_path, slug).status == tasks.OPEN


def test_two_tasks_on_one_day_do_not_collide(tmp_path):
    state.init(tmp_path, "demo", {})
    first = tasks.create(tmp_path, "Fix it", today="2026-08-16")
    second = tasks.create(tmp_path, "Fix it", today="2026-08-16")
    assert first != second


def test_listing_is_empty_before_any_task(tmp_path):
    state.init(tmp_path, "demo", {})
    assert tasks.all_tasks(tmp_path) == []


def test_listing_is_newest_first(tmp_path):
    state.init(tmp_path, "demo", {})
    tasks.create(tmp_path, "Older", today="2026-08-01")
    tasks.create(tmp_path, "Newer", today="2026-08-16")
    assert [t.title for t in tasks.all_tasks(tmp_path)] == ["Newer", "Older"]


def test_answering_persists_immediately(tmp_path):
    """Rule 4 holds inside a task exactly as it does in a project."""
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    tasks.record_answer(tmp_path, slug, "understand", "q1", "the metrics are wrong")
    reloaded = tasks.load(tmp_path, slug)
    assert reloaded.nodes["understand"].answers["q1"] == "the metrics are wrong"


def test_answering_a_task_refreshes_the_left_off_note(tmp_path):
    """The resume fix applies to tasks too, or the same bug returns."""
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix the metrics")
    tasks.record_answer(tmp_path, slug, "understand", "q1", "x")

    note = state.load(tmp_path).last_note
    assert "Fix the metrics" in note
    assert "Understand" in note


def test_writing_a_task_node_refreshes_the_left_off_note(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix the metrics")
    tasks.write(tmp_path, slug, "understand", "The body.", "A summary.")
    assert "Fix the metrics" in state.load(tmp_path).last_note


def test_answering_moves_the_task_to_in_progress(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    tasks.record_answer(tmp_path, slug, "understand", "q1", "x")
    assert tasks.load(tmp_path, slug).status == tasks.IN_PROGRESS


def test_next_node_is_the_first_unfinished_one(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    assert tasks.next_node(tasks.load(tmp_path, slug)) == "understand"


def test_next_node_skips_written_nodes(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    tasks.write(tmp_path, slug, "understand", "The body.", "A summary.")
    assert tasks.next_node(tasks.load(tmp_path, slug)) == "analyze"


def test_writing_a_node_puts_the_file_in_the_task_folder(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    path = tasks.write(tmp_path, slug, "understand", "The body.", "A summary.")
    assert path.parent.name == slug
    assert "The body." in path.read_text(encoding="utf-8")


def test_finishing_verify_finishes_the_task(tmp_path):
    """Done is reached by doing the work, not by declaring it."""
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    for node in ("understand", "analyze", "design", "verify"):
        tasks.write(tmp_path, slug, node, "The body.", "A summary.")
    assert tasks.load(tmp_path, slug).status == tasks.DONE


def test_abandoning_a_task_is_reversible(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    tasks.abandon(tmp_path, slug)
    assert tasks.load(tmp_path, slug).status == tasks.ABANDONED
    tasks.reopen(tmp_path, slug)
    assert tasks.load(tmp_path, slug).status != tasks.ABANDONED


def test_an_abandoned_task_is_never_the_live_one(tmp_path):
    """A dead task must not own the single next-action slot forever."""
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    tasks.record_answer(tmp_path, slug, "understand", "q1", "x")
    tasks.abandon(tmp_path, slug)
    assert tasks.live_task(tmp_path) is None


def test_the_live_task_is_the_one_in_progress(tmp_path):
    state.init(tmp_path, "demo", {})
    tasks.create(tmp_path, "Untouched", today="2026-08-16")
    started = tasks.create(tmp_path, "Started", today="2026-08-01")
    tasks.record_answer(tmp_path, started, "understand", "q1", "x")
    assert tasks.live_task(tmp_path).slug == started


def test_a_finished_task_is_not_live(tmp_path):
    state.init(tmp_path, "demo", {})
    slug = tasks.create(tmp_path, "Fix it")
    for node in ("understand", "analyze", "design", "verify"):
        tasks.write(tmp_path, slug, node, "The body.", "A summary.")
    assert tasks.live_task(tmp_path) is None


def test_load_raises_for_an_unknown_task(tmp_path):
    state.init(tmp_path, "demo", {})
    with pytest.raises(FileNotFoundError):
        tasks.load(tmp_path, "2026-08-16-nope")
