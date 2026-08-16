from pathlib import Path

import pytest

from throughline import nodes

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "throughline" / "SKILL.md"
QUESTIONS = ROOT / "skills" / "throughline" / "questions"


def test_skill_file_exists():
    assert SKILL.is_file()


def test_skill_has_frontmatter_name_and_description():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "\nname: throughline\n" in text
    assert "\ndescription:" in text


def test_skill_documents_every_cli_command():
    text = SKILL.read_text(encoding="utf-8")
    for command in ("init", "nodes", "context", "answer", "write", "status", "next", "stale", "scan"):
        assert f"throughline {command}" in text, f"{command} is undocumented"


def test_skill_states_the_one_next_action_rule():
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "one next" in text


def test_skill_forbids_broadcasting_staleness():
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "never" in text and "stale" in text


def test_question_banks_name_real_nodes():
    known = {node.id for node in nodes.all_nodes()}
    for path in QUESTIONS.glob("*.md"):
        assert path.stem in known, f"{path.name} does not match any node"


@pytest.mark.parametrize("node_id", ["problem-statement", "functional-requirements", "domain-model"])
def test_core_question_banks_exist(node_id):
    assert (QUESTIONS / f"{node_id}.md").is_file()


def test_question_banks_stay_within_the_size_limit():
    for path in QUESTIONS.glob("*.md"):
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("### Q"))
        assert 1 <= count <= 8, f"{path.name} has {count} questions, limit is 8"


def test_every_question_offers_a_recommendation():
    for path in QUESTIONS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        blocks = text.split("### Q")[1:]
        for block in blocks:
            assert "Recommend:" in block, f"a question in {path.name} has no recommendation"
