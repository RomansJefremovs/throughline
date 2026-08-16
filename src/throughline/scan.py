"""Bounded reconnaissance of an existing repository.

This module gathers raw material only. Every inference from it is made by
the model, in the skill, never here.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".idea",
        ".vs",
        "target",
        "bin",
        "obj",
    }
)

READ_LIMIT = 8000


def encode_repo_path(repo: Path) -> str:
    """Claude Code's per-project transcript directory name.

    Every character that is not alphanumeric becomes a single dash, so
    C:\\Dev\\UMES becomes C--Dev-UMES.
    """
    text = str(Path(repo))
    return "".join(char if char.isalnum() else "-" for char in text)


def transcripts_dir(repo: Path, home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".claude" / "projects" / encode_repo_path(repo)


def transcript_files(repo: Path, home: Path | None = None) -> list[Path]:
    directory = transcripts_dir(repo, home)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl"))


def file_tree(repo: Path, limit: int = 200) -> list[str]:
    root = Path(repo)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(found) >= limit:
            break
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        found.append(relative.as_posix())
    return found


def git_log(repo: Path, limit: int = 40) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "log", f"-{limit}", "--oneline"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:READ_LIMIT]


@dataclass
class ScanResult:
    tree: list[str] = field(default_factory=list)
    readme: str | None = None
    claude_md: str | None = None
    git_log: list[str] = field(default_factory=list)
    transcripts: list[str] = field(default_factory=list)


def scan(repo: Path, home: Path | None = None) -> ScanResult:
    root = Path(repo)
    return ScanResult(
        tree=file_tree(root),
        readme=_read(root / "README.md"),
        claude_md=_read(root / "CLAUDE.md"),
        git_log=git_log(root),
        transcripts=[str(p) for p in transcript_files(root, home)],
    )


def render(result: ScanResult) -> str:
    parts = ["## Files", ""]
    parts.extend(result.tree or ["(none)"])
    parts.extend(["", "## Recent commits", ""])
    parts.extend(result.git_log or ["(none)"])
    parts.extend(["", "## README", "", result.readme or "(none)"])
    parts.extend(["", "## CLAUDE.md", "", result.claude_md or "(none)"])
    parts.extend(["", "## Session transcripts", ""])
    parts.extend(result.transcripts or ["(none)"])
    return "\n".join(parts) + "\n"
