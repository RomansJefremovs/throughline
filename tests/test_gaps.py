from throughline import gaps, state, tasks

TWO_SIDED = """# ER model

> Two sides.

SQLite. Some prose that belongs to neither side.

# Current

The schema as built.

## Views are stored twice

`clips.views` and `clip_metrics` disagree.

# Target

## Accounts scoped to the project

`credentials` gains `project_id`.

## Real foreign keys on retrofitted columns

Six columns need a table rebuild.
"""

ONE_SIDED = """# Problem statement

> One side only.

Nobody has a target here.
"""


def test_a_one_sided_artifact_has_no_target():
    sides = gaps.split_sides(ONE_SIDED)
    assert sides.target == ""
    assert "Nobody has a target here." in sides.current


def test_splitting_finds_both_sides():
    sides = gaps.split_sides(TWO_SIDED)
    assert "The schema as built." in sides.current
    assert "`credentials` gains `project_id`." in sides.target


def test_the_preamble_belongs_to_neither_side():
    sides = gaps.split_sides(TWO_SIDED)
    assert "belongs to neither side" in sides.preamble
    assert "belongs to neither side" not in sides.current


def test_current_side_subsections_are_not_gaps():
    """A gap is a difference, not an observation about today."""
    found = gaps.from_text("er-model", TWO_SIDED)
    assert "Views are stored twice" not in [g.title for g in found]


def test_each_target_subsection_is_one_gap():
    found = gaps.from_text("er-model", TWO_SIDED)
    assert [g.title for g in found] == [
        "Accounts scoped to the project",
        "Real foreign keys on retrofitted columns",
    ]


def test_a_gap_carries_its_own_text():
    found = gaps.from_text("er-model", TWO_SIDED)
    assert "`credentials` gains `project_id`." in found[0].text


def test_side_headings_may_carry_a_descriptive_suffix():
    """Real artifacts write `# Target - single VPS, split images`.

    Matching the heading exactly meant those artifacts reported no sides
    and therefore no gaps - a silent zero, which is worse than an error.
    """
    text = (
        "# Deployment\n\n> S.\n\n"
        "# Current — local Windows\n\none process\n\n"
        "# Target — single VPS, split images\n\n## Split the images\n\ndo it\n"
    )
    sides = gaps.split_sides(text)
    assert "one process" in sides.current
    assert [g.title for g in gaps.from_text("deployment", text)] == ["Split the images"]


def test_a_heading_that_merely_contains_the_word_is_not_a_side():
    text = "# Thing\n\n> S.\n\n# Current state of the target audience\n\nprose\n"
    assert gaps.split_sides(text).target == ""


def test_prose_before_the_first_subsection_is_not_its_own_gap():
    """Real artifacts open the target side with a sentence of framing.

    Counting that as an untitled gap put a blank row in the list on the
    first run against real data.
    """
    text = (
        "# Thing\n\n> S.\n\n# Current\n\nnow\n\n"
        "# Target\n\nTwo changes, both following from earlier decisions.\n\n"
        "## First change\n\ndo this\n\n## Second change\n\ndo that\n"
    )
    found = gaps.from_text("architecture", text)
    assert [g.title for g in found] == ["First change", "Second change"]


def test_a_target_with_no_subsections_is_a_single_gap():
    text = "# Thing\n\n> S.\n\n# Current\n\nnow\n\n# Target\n\nit should be better\n"
    found = gaps.from_text("architecture", text)
    assert len(found) == 1
    assert "it should be better" in found[0].text


def test_a_one_sided_artifact_yields_nothing():
    assert gaps.from_text("problem-statement", ONE_SIDED) == []


def test_gaps_are_never_stored(tmp_path):
    """Rule: a gap is a reading of a document, computed on demand.

    Nothing in pipeline.yaml may record them - a stored gap acquires a
    lifecycle, a lifecycle needs closing, and closing needs a list.
    """
    state.init(tmp_path, "demo", {})
    from throughline import artifacts

    artifacts.write_artifact(tmp_path, "architecture", TWO_SIDED, "S.")
    gaps.for_repo(tmp_path)
    raw = state.state_path(tmp_path).read_text(encoding="utf-8")
    assert "gap" not in raw.lower()


def test_for_repo_finds_gaps_across_nodes(tmp_path):
    state.init(tmp_path, "demo", {})
    from throughline import artifacts

    artifacts.write_artifact(tmp_path, "architecture", TWO_SIDED, "S.")
    found = gaps.for_repo(tmp_path)
    assert [g.node for g in found] == ["architecture", "architecture"]


def test_promoting_a_gap_creates_a_task_starting_at_analyze(tmp_path):
    """Understand is already answered - the artifact said what is wanted."""
    state.init(tmp_path, "demo", {})
    from throughline import artifacts

    artifacts.write_artifact(tmp_path, "architecture", TWO_SIDED, "S.")
    found = gaps.for_repo(tmp_path)

    slug = gaps.promote(tmp_path, found[0])
    task = tasks.load(tmp_path, slug)
    assert task.origin == "gap"
    assert tasks.next_node(task) == "analyze"


def test_a_promoted_task_keeps_its_lineage(tmp_path):
    state.init(tmp_path, "demo", {})
    from throughline import artifacts

    artifacts.write_artifact(tmp_path, "architecture", TWO_SIDED, "S.")
    found = gaps.for_repo(tmp_path)
    slug = gaps.promote(tmp_path, found[0])

    task = tasks.load(tmp_path, slug)
    assert "architecture" in task.reference
    written = tasks.artifact_path(tmp_path, slug, "understand").read_text("utf-8")
    assert "`credentials` gains `project_id`." in written


def test_promotion_never_happens_on_its_own(tmp_path):
    """Rule 8. Reading the gaps must not create anything."""
    state.init(tmp_path, "demo", {})
    from throughline import artifacts

    artifacts.write_artifact(tmp_path, "architecture", TWO_SIDED, "S.")
    gaps.for_repo(tmp_path)
    assert tasks.all_tasks(tmp_path) == []
