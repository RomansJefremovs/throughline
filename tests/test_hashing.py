from throughline import artifacts, hashing, state


def test_content_hash_is_stable():
    assert hashing.content_hash("abc") == hashing.content_hash("abc")


def test_content_hash_differs_on_different_content():
    assert hashing.content_hash("abc") != hashing.content_hash("abd")


def test_content_hash_ignores_line_ending_style():
    assert hashing.content_hash("a\r\nb") == hashing.content_hash("a\nb")


def test_content_hash_ignores_trailing_whitespace():
    assert hashing.content_hash("a\n\n") == hashing.content_hash("a")


def test_current_upstream_hashes_covers_every_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    result = hashing.current_upstream_hashes(tmp_path, "domain-model")
    assert set(result) == {"problem-statement", "functional-requirements"}


def test_missing_upstream_artifact_hashes_to_empty_marker(tmp_path):
    result = hashing.current_upstream_hashes(tmp_path, "domain-model")
    assert result["problem-statement"] == hashing.MISSING


def test_a_node_with_no_dependencies_has_no_hashes(tmp_path):
    assert hashing.current_upstream_hashes(tmp_path, "problem-statement") == {}


def test_stale_deps_is_empty_right_after_stamping(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)
    assert hashing.stale_deps(tmp_path, "domain-model", loaded) == []


def test_stale_deps_names_the_changed_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)

    artifacts.write_artifact(tmp_path, "problem-statement", "changed", "s")
    assert hashing.stale_deps(tmp_path, "domain-model", loaded) == ["problem-statement"]


def test_is_stale_is_false_for_a_never_stamped_node(tmp_path):
    loaded = state.init(tmp_path, "demo", {})
    assert hashing.is_stale(tmp_path, "domain-model", loaded) is False


def test_is_stale_is_true_after_an_upstream_change(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)
    artifacts.write_artifact(tmp_path, "problem-statement", "changed", "s")
    assert hashing.is_stale(tmp_path, "domain-model", loaded) is True


def test_stamp_mutates_state_without_saving(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "b", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "b", "s")
    loaded = state.init(tmp_path, "demo", {})
    hashing.stamp(tmp_path, "domain-model", loaded)

    assert loaded.nodes["domain-model"].upstream_hashes != {}
    assert state.load(tmp_path).nodes["domain-model"].upstream_hashes == {}
