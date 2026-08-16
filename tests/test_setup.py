import json

from throughline import setup, state, status, tasks


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def test_an_empty_repo_detects_nothing_and_does_not_crash(tmp_path):
    found = setup.detect(tmp_path)
    assert found["mcp_servers"] == []
    assert found["ci"] == []
    assert found["commands"] == {}


def test_mcp_servers_are_found_in_the_project_config(tmp_path):
    """This is the detection that changes daily use.

    A repo with a ticket integration means Understand pulls the ticket
    instead of asking the user to paste it.
    """
    _write(
        tmp_path / ".mcp.json",
        json.dumps({"mcpServers": {"trello": {}, "sentry": {}}}),
    )
    assert setup.detect(tmp_path)["mcp_servers"] == ["sentry", "trello"]


def test_mcp_servers_are_found_in_claude_settings(tmp_path):
    _write(
        tmp_path / ".claude" / "settings.json",
        json.dumps({"mcpServers": {"linear": {}}}),
    )
    assert setup.detect(tmp_path)["mcp_servers"] == ["linear"]


def test_mcp_servers_from_several_files_are_merged_without_duplicates(tmp_path):
    _write(tmp_path / ".mcp.json", json.dumps({"mcpServers": {"trello": {}}}))
    _write(
        tmp_path / ".claude" / "settings.local.json",
        json.dumps({"mcpServers": {"trello": {}, "github": {}}}),
    )
    assert setup.detect(tmp_path)["mcp_servers"] == ["github", "trello"]


def test_broken_json_is_ignored_rather_than_fatal(tmp_path):
    """Setup must never fail because a config file is mid-edit."""
    _write(tmp_path / ".mcp.json", "{ not json at all")
    assert setup.detect(tmp_path)["mcp_servers"] == []


def test_launch_configurations_are_found(tmp_path):
    _write(
        tmp_path / ".claude" / "launch.json",
        json.dumps({"configurations": [{"name": "web", "port": 3000}]}),
    )
    assert setup.detect(tmp_path)["launch"] == ["web"]


def test_continuous_integration_workflows_are_found(tmp_path):
    _write(tmp_path / ".github" / "workflows" / "test.yml", "on: push")
    _write(tmp_path / ".github" / "workflows" / "release.yaml", "on: tag")
    assert setup.detect(tmp_path)["ci"] == ["release.yaml", "test.yml"]


def test_node_scripts_become_commands(tmp_path):
    _write(
        tmp_path / "package.json",
        json.dumps({"scripts": {"dev": "vite", "test": "vitest"}}),
    )
    commands = setup.detect(tmp_path)["commands"]
    assert commands["run"] == "npm run dev"
    assert commands["test"] == "npm test"


def test_a_python_project_with_pytest_gets_a_test_command(tmp_path):
    _write(tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths = ['tests']\n")
    assert setup.detect(tmp_path)["commands"]["test"] == "python -m pytest"


def test_a_makefile_target_is_offered(tmp_path):
    _write(tmp_path / "Makefile", "test:\n\techo hi\n")
    assert setup.detect(tmp_path)["commands"]["test"] == "make test"


def test_a_dotnet_solution_gets_commands(tmp_path):
    """Found by running detect on a real .NET repo, which reported nothing."""
    _write(tmp_path / "Thing.slnx", "<Solution />")
    commands = setup.detect(tmp_path)["commands"]
    assert commands["build"] == "dotnet build"
    assert commands["test"] == "dotnet test"


def test_a_csproj_is_enough_for_dotnet(tmp_path):
    _write(tmp_path / "src" / "App" / "App.csproj", "<Project />")
    assert setup.detect(tmp_path)["commands"]["test"] == "dotnet test"


def test_existing_project_notes_are_reported(tmp_path):
    """CLAUDE.md usually answers 'what this is' and half the vocabulary.

    Setup must read it rather than spend questions on what it says.
    """
    _write(tmp_path / "CLAUDE.md", "# The thing\n")
    _write(tmp_path / "README.md", "# Readme\n")
    assert setup.detect(tmp_path)["notes"] == ["CLAUDE.md", "README.md"]


def test_no_notes_is_an_empty_list(tmp_path):
    assert setup.detect(tmp_path)["notes"] == []


def test_setup_is_written_beside_the_project(tmp_path):
    state.init(tmp_path, "demo", {})
    path = setup.write(tmp_path, "It is a thing.", "A summary.")
    assert path == tmp_path / "docs" / "project" / "setup.md"
    assert "It is a thing." in path.read_text(encoding="utf-8")


def test_setup_is_written_with_lf(tmp_path):
    state.init(tmp_path, "demo", {})
    path = setup.write(tmp_path, "It is a thing.", "A summary.")
    assert b"\r\n" not in path.read_bytes()


def test_a_repo_can_be_task_only(tmp_path):
    """Client work does not need twelve nodes about architecture."""
    loaded = state.init(tmp_path, "geedie", {}, task_only=True)
    assert loaded.task_only is True
    assert loaded.nodes == {}


def test_a_task_only_repo_offers_no_project_node(tmp_path):
    state.init(tmp_path, "geedie", {}, task_only=True)
    assert status.for_repo(tmp_path).next_node is None


def test_a_task_only_repo_still_runs_tasks(tmp_path):
    state.init(tmp_path, "geedie", {}, task_only=True)
    slug = tasks.create(tmp_path, "Fix the login bug")
    tasks.record_answer(tmp_path, slug, "understand", "q1", "x")

    result = status.for_repo(tmp_path)
    assert result.task_slug == slug
    assert result.next_node == "understand"


def test_a_task_only_repo_does_not_claim_a_pipeline_is_complete(tmp_path):
    """It has no pipeline. Saying one is finished is simply untrue."""
    state.init(tmp_path, "geedie", {}, task_only=True)
    text = status.render_text(status.for_repo(tmp_path))
    assert "pipeline is complete" not in text
    assert "no task" in text.lower()


def test_a_full_project_still_reports_completion(tmp_path):
    from throughline import artifacts

    loaded = state.init(tmp_path, "demo", {})
    for node_id in list(loaded.nodes):
        artifacts.write_artifact(tmp_path, node_id, "b", "s")
        loaded.nodes[node_id].status = state.CURRENT
    state.save(tmp_path, loaded)
    assert "complete" in status.render_text(status.for_repo(tmp_path))


def test_a_task_only_repo_reports_no_phases(tmp_path):
    """Nothing to show progress against, so nothing is shown."""
    state.init(tmp_path, "geedie", {}, task_only=True)
    assert status.for_repo(tmp_path).phases == []
