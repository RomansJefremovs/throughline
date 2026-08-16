from throughline import artifacts, context


def test_context_loads_only_declared_dependencies(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "test-cases", "T", "s")

    ctx = context.assemble(tmp_path, "domain-model")
    loaded = {d.node_id for d in ctx.documents}
    assert loaded == {"problem-statement", "functional-requirements"}


def test_context_includes_the_glossary_for_downstream_nodes(tmp_path):
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "use-case-diagram", "U", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "use-case-descriptions")
    assert "domain-model" in {d.node_id for d in ctx.documents}


def test_context_does_not_include_the_glossary_in_its_own_node(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "domain-model")
    assert [d.node_id for d in ctx.documents].count("domain-model") == 0


def test_context_does_not_duplicate_a_glossary_that_is_already_a_dependency(tmp_path):
    artifacts.write_artifact(tmp_path, "functional-requirements", "R", "s")
    artifacts.write_artifact(tmp_path, "domain-model", "G", "s")

    ctx = context.assemble(tmp_path, "architecture")
    assert [d.node_id for d in ctx.documents].count("domain-model") == 1


def test_context_reports_missing_dependencies(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P", "s")
    ctx = context.assemble(tmp_path, "domain-model")
    assert ctx.missing == ["functional-requirements"]


def test_missing_dependencies_are_not_documents(tmp_path):
    ctx = context.assemble(tmp_path, "domain-model")
    assert ctx.documents == []


def test_line_count_sums_the_loaded_documents(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "a\nb", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "c", "s")
    ctx = context.assemble(tmp_path, "domain-model")
    expected = sum(len(d.text.splitlines()) for d in ctx.documents)
    assert ctx.line_count == expected


def test_render_labels_each_document(tmp_path):
    artifacts.write_artifact(tmp_path, "problem-statement", "P body", "s")
    artifacts.write_artifact(tmp_path, "functional-requirements", "R body", "s")
    text = context.render(context.assemble(tmp_path, "domain-model"))
    assert "## Problem statement" in text
    assert "P body" in text


def test_render_notes_missing_dependencies(tmp_path):
    text = context.render(context.assemble(tmp_path, "domain-model"))
    assert "not written yet" in text


def test_render_of_a_root_node_is_short(tmp_path):
    text = context.render(context.assemble(tmp_path, "problem-statement"))
    assert "no upstream" in text
