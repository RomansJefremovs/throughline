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


def test_skill_mandates_the_interactive_picker():
    text = SKILL.read_text(encoding="utf-8")
    assert "AskUserQuestion" in text, "the skill must require the interactive picker"
    assert "prose" in text, "the skill must forbid asking with options written as prose"


def test_skill_documents_question_hygiene():
    text = SKILL.read_text(encoding="utf-8")
    assert "## Question hygiene" in text


def test_shipped_question_banks_model_the_target_length():
    """The rule is four or five questions; eight is only the hard ceiling.

    The banks that ship with the skill are the examples every derived
    interview copies, so they hold to the target rather than the ceiling.
    """
    for path in QUESTIONS.glob("*.md"):
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("### Q"))
        assert 1 <= count <= 5, f"{path.name} has {count} questions, target is 4-5"


def test_every_question_offers_a_recommendation():
    for path in QUESTIONS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        blocks = text.split("### Q")[1:]
        for block in blocks:
            assert "Recommend:" in block, f"a question in {path.name} has no recommendation"
