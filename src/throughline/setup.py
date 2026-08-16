"""Repo setup: the cheap alternative to a whole project pipeline.

Most work is not "analyse a system", it is "fix this in someone else's
repo". Setup records just enough to make that work well - what the repo
is, its vocabulary, how to run it, and what it is wired to - and stops.

Detection is the part that changes daily use. If a repo has a ticket
integration, the task flow pulls the ticket instead of asking the user to
paste it, and that only happens if setup went looking. Everything here is
detected rather than assumed: no fixed toolchain, no required layout.

Nothing here ever fails on a malformed config. A file being mid-edit must
not stop setup running.
"""

import json
import re
from pathlib import Path

from .state import PROJECT_DIR

SETUP_FILENAME = "setup.md"

# Files that may declare MCP servers, in the order a reader would expect.
MCP_SOURCES = (
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)


def setup_path(repo: Path) -> Path:
    return Path(repo) / PROJECT_DIR / SETUP_FILENAME


def _read_json(path: Path) -> dict:
    """Never raise. A config being mid-edit is not an error here."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _mcp_servers(repo: Path) -> list[str]:
    found: set[str] = set()
    for relative in MCP_SOURCES:
        servers = _read_json(repo / relative).get("mcpServers")
        if isinstance(servers, dict):
            found.update(str(name) for name in servers)
    return sorted(found)


def _launch(repo: Path) -> list[str]:
    configs = _read_json(repo / ".claude" / "launch.json").get("configurations")
    if not isinstance(configs, list):
        return []
    return [str(c.get("name")) for c in configs if isinstance(c, dict) and c.get("name")]


def _ci(repo: Path) -> list[str]:
    workflows = repo / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    return sorted(
        p.name for p in workflows.iterdir() if p.suffix in {".yml", ".yaml"}
    )


def _make_targets(repo: Path) -> set[str]:
    makefile = repo / "Makefile"
    if not makefile.is_file():
        return set()
    try:
        text = makefile.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    return set(re.findall(r"^([A-Za-z0-9_.-]+):", text, re.MULTILINE))


def _commands(repo: Path) -> dict[str, str]:
    """Best guesses at how to run and test this repo.

    Guesses, and labelled as such wherever they are shown. Setup asks the
    user to confirm them rather than trusting the detection.
    """
    commands: dict[str, str] = {}

    scripts = _read_json(repo / "package.json").get("scripts")
    if isinstance(scripts, dict):
        for name in ("dev", "start", "serve"):
            if name in scripts:
                commands["run"] = f"npm run {name}"
                break
        if "test" in scripts:
            commands["test"] = "npm test"
        if "build" in scripts:
            commands["build"] = "npm run build"

    pyproject = repo / "pyproject.toml"
    if "test" not in commands and pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            text = ""
        if "pytest" in text:
            commands["test"] = "python -m pytest"

    if "test" not in commands and _is_dotnet(repo):
        commands["build"] = "dotnet build"
        commands["test"] = "dotnet test"

    targets = _make_targets(repo)
    if "test" not in commands and "test" in targets:
        commands["test"] = "make test"
    if "run" not in commands and "run" in targets:
        commands["run"] = "make run"

    return commands


def _is_dotnet(repo: Path) -> bool:
    """A solution at the root, or a project file anywhere shallow.

    Added after running detect on a real .NET repo and getting nothing
    back - the whole point of detection is that it works on the repos
    that actually exist.
    """
    patterns = ("*.sln", "*.slnx", "*.csproj", "*/*.csproj", "*/*/*.csproj")
    # `any(repo.glob(p) for p in patterns)` looks right and is not: each
    # glob returns a generator, and a generator object is always truthy.
    return any(any(repo.glob(pattern)) for pattern in patterns)


def _notes(repo: Path) -> list[str]:
    """Documents that already answer what setup would otherwise ask.

    CLAUDE.md in particular usually states what the project is and half
    its vocabulary. Reading it beats spending questions on it.
    """
    return [
        name
        for name in ("CLAUDE.md", "AGENTS.md", "README.md", "CONTRIBUTING.md")
        if (repo / name).is_file()
    ]


def detect(repo: Path) -> dict:
    """Everything worth knowing about a repo that can be read, not asked.

    The interview should never spend a question on something a file
    already answers.
    """
    repo = Path(repo)
    return {
        "mcp_servers": _mcp_servers(repo),
        "launch": _launch(repo),
        "ci": _ci(repo),
        "notes": _notes(repo),
        "commands": _commands(repo),
    }


def render(found: dict) -> str:
    lines = ["# What this repo is wired to", ""]
    rows = [
        ("MCP servers", ", ".join(found["mcp_servers"])),
        ("Launch configs", ", ".join(found["launch"])),
        ("CI workflows", ", ".join(found["ci"])),
        ("Existing notes", ", ".join(found.get("notes", []))),
    ]
    for label, value in rows:
        lines.append(f"{label:<16} {value or '-'}")
    lines.append("")
    lines.append("Commands, guessed:")
    if found["commands"]:
        for name, command in found["commands"].items():
            lines.append(f"  {name:<8} {command}")
    else:
        lines.append("  none found")
    return "\n".join(lines)


def write(repo: Path, body: str, summary: str) -> Path:
    """Setup is a document like any other - markdown, hand-editable.

    LF on every platform, and written as raw bytes, for the same reason
    artifacts are: an edit through the app must not rewrite every line.
    """
    path = setup_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"# Repo setup\n\n> {summary.strip()}\n\n{body.strip()}\n"
    path.write_bytes(text.encode("utf-8"))
    return path
