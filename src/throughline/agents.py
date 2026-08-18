"""Which agent gets handed the work.

Throughline drives a conversation it does not have. The CLI is
deterministic, the artifacts are markdown, and the skill is a set of
rules - none of it cares who is reading them. This module is the only
place that names an agent, so a third one is a table entry rather than
a search through the codebase.

The choice is per machine, not per repo. Which agents are installed is
a fact about the computer, and `pipeline.yaml` is committed - a per-repo
setting would push one person's choice onto a teammate who does not have
that agent at all.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .registry import home

SETTING_FILENAME = "agent"


@dataclass(frozen=True)
class Agent:
    executable: str
    prompt_flag: str | None = None
    environment: dict[str, str] = field(default_factory=dict)

    def argv(self, prompt: str, executable: str | None = None) -> list[str]:
        first = executable or self.executable
        if self.prompt_flag is None:
            return [first, prompt]
        return [first, self.prompt_flag, prompt]


# Order matters twice: `installed()` reports in it, and a machine with
# exactly one agent gets that one without being asked.
AGENTS: dict[str, Agent] = {
    "claude": Agent("claude"),
    "opencode": Agent(
        "opencode",
        "--prompt",
        # opencode's picker is behind a feature flag. Unset, the tool is
        # not registered at all, and binding rule 3 - every question
        # through the picker, never as prose - cannot be kept.
        {"OPENCODE_ENABLE_QUESTION_TOOL": "1"},
    ),
}


def setting_path() -> Path:
    return home() / SETTING_FILENAME


def installed() -> list[str]:
    return [name for name, agent in AGENTS.items() if shutil.which(agent.executable)]


def chosen() -> str | None:
    """Absent, unreadable and unrecognised are all the same answer."""
    try:
        name = setting_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name if name in AGENTS else None


def choose(name: str) -> str:
    if name not in AGENTS:
        known = ", ".join(AGENTS)
        raise ValueError(f"unknown agent {name!r}, expected one of: {known}")
    path = setting_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{name}\n", encoding="utf-8")
    return name


def command(name: str, prompt: str) -> tuple[list[str], dict[str, str]]:
    """The argv to run and the environment to add to the inherited one.

    argv[0] is the resolved path rather than the bare name. npm installs
    opencode as `opencode.CMD` on Windows, and CreateProcess will not
    find a `.CMD` by name the way a shell would - so a bare name fails
    as "not found" for something `installed()` has just reported as
    present, which is the most confusing failure available.

    An unresolvable name is passed through unchanged so the spawn raises
    its own error rather than one invented here.
    """
    agent = AGENTS[name]
    return (
        agent.argv(prompt, shutil.which(agent.executable)),
        dict(agent.environment),
    )
