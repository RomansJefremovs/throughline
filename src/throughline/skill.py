"""Putting the skill where an agent will find it.

Both agents read `~/.claude/skills`. opencode was checked directly rather
than taken from its documentation: `opencode debug skill` resolves every
user skill to that directory, so one destination serves both and there
is no second copy to keep in step.

Without this the app's hand-off opens a session and says "use the
throughline skill" to an agent that has never heard of it.
"""

import filecmp
import shutil
from pathlib import Path

SKILL_NAME = "throughline"


def bundled() -> Path:
    """Where the pack is, frozen or from source.

    The frozen build carries it next to the package exactly as it carries
    the app assets. A source checkout has it at the repo root, two levels
    above this file.
    """
    packaged = Path(__file__).parent / "skill"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME


def destination(home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".claude" / "skills" / SKILL_NAME


def present(home: Path | None = None) -> bool:
    return (destination(home) / "SKILL.md").is_file()


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def differs(home: Path | None = None) -> list[str]:
    """Every relative path that is missing, extra, or not byte-identical."""
    source, target = bundled(), destination(home)
    changed: set[str] = set()
    for path in _files(source):
        relative = path.relative_to(source)
        other = target / relative
        if not other.is_file() or not filecmp.cmp(path, other, shallow=False):
            changed.add(relative.as_posix())
    for path in _files(target):
        relative = path.relative_to(target)
        if not (source / relative).is_file():
            changed.add(relative.as_posix())
    return sorted(changed)


def install(home: Path | None = None, force: bool = False) -> dict:
    """Copy the pack in, unless someone has edited the copy that is there.

    A tuned skill is somebody's work, and replacing it silently is the
    same failure as `write` overwriting an edited artifact. Differences
    are reported and `force` is the user's decision, not ours.
    """
    target = destination(home)
    if not present(home):
        shutil.copytree(bundled(), target, dirs_exist_ok=True)
        return {"written": True, "path": str(target), "differs": []}

    changed = differs(home)
    if not changed:
        return {"written": False, "path": str(target), "differs": []}
    if not force:
        return {"written": False, "path": str(target), "differs": changed}

    shutil.copytree(bundled(), target, dirs_exist_ok=True)
    return {"written": True, "path": str(target), "differs": changed}
