import pytest

from throughline import nodes


def test_all_nodes_have_unique_ids():
    ids = [n.id for n in nodes.all_nodes()]
    assert len(ids) == len(set(ids))


def test_every_dependency_refers_to_a_real_node():
    ids = {n.id for n in nodes.all_nodes()}
    for node in nodes.all_nodes():
        for dep in node.deps:
            assert dep in ids, f"{node.id} depends on unknown node {dep}"


def test_dependencies_come_earlier_in_the_tuple():
    seen = set()
    for node in nodes.all_nodes():
        for dep in node.deps:
            assert dep in seen, f"{node.id} depends on {dep} which is defined later"
        seen.add(node.id)


def test_every_phase_is_known():
    for node in nodes.all_nodes():
        assert node.phase in nodes.PHASES


def test_get_node_returns_the_definition():
    assert nodes.get_node("domain-model").title == "Domain model"


def test_get_node_raises_on_unknown_id():
    with pytest.raises(KeyError):
        nodes.get_node("no-such-node")


def test_always_nodes_are_active_with_no_flags():
    active = {n.id for n in nodes.active_nodes({})}
    assert "problem-statement" in active
    assert "domain-model" in active
    assert "architecture" in active


def test_flag_nodes_are_inactive_when_flag_is_false():
    active = {n.id for n in nodes.active_nodes({"has_db": False})}
    assert "er-model" not in active


def test_flag_nodes_are_active_when_flag_is_true():
    active = {n.id for n in nodes.active_nodes({"has_db": True})}
    assert "er-model" in active


def test_missing_flag_is_treated_as_false():
    active = {n.id for n in nodes.active_nodes({})}
    assert "state-machine" not in active


def test_on_demand_nodes_are_inactive_by_default():
    active = {n.id for n in nodes.active_nodes({"has_db": True})}
    assert "activity-diagram" not in active


def test_on_demand_nodes_activate_when_named():
    active = {n.id for n in nodes.active_nodes({}, on_demand=("activity-diagram",))}
    assert "activity-diagram" in active


def test_active_nodes_preserve_pipeline_order():
    active = [n.id for n in nodes.active_nodes({"has_db": True})]
    assert active.index("problem-statement") < active.index("domain-model")
    assert active.index("domain-model") < active.index("er-model")
