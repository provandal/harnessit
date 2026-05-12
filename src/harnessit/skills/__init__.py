"""HarnessIT skills — durable, per-SRE-preference prompt fragments.

Skills are procedural prompt fragments that get injected into the
agent's context to shape behavior in ways that are durable across
scenarios. Distinct from system prompts (per-scenario context) and
tools (capability surface). A skill is conceptually "how this SRE
prefers their agent to communicate" — verbosity, structure,
commitment language, etc.

Stage 5b ships the first skill: ``calibrated_commitment``. Vendored
here in HarnessIT for now; will likely migrate to TheConstruct once
the skill API stabilizes and skill content needs to be shared across
projects.

Load via name::

    from harnessit.skills import load_skill_by_name
    skill = load_skill_by_name("calibrated-commitment")
"""

from harnessit.skills.calibrated_commitment import (
    CALIBRATED_COMMITMENT_BODY,
    CALIBRATED_COMMITMENT_NAME,
    CALIBRATED_COMMITMENT_VERSION,
    Skill,
    load_calibrated_commitment,
)


def load_skill_by_name(name: str) -> Skill:
    """Resolve a skill by its public name. Used by the CLI's
    ``--skill <name>`` flag and by EvalScenario factory wiring.

    Raises ``ValueError`` for unknown skill names so the CLI can
    surface "unknown skill" rather than silently dropping it.
    """
    if name == CALIBRATED_COMMITMENT_NAME:
        return load_calibrated_commitment()
    raise ValueError(
        f"Unknown skill {name!r}. Known: {sorted(_known_skill_names())}"
    )


def _known_skill_names() -> set[str]:
    return {CALIBRATED_COMMITMENT_NAME}


__all__ = [
    "CALIBRATED_COMMITMENT_BODY",
    "CALIBRATED_COMMITMENT_NAME",
    "CALIBRATED_COMMITMENT_VERSION",
    "Skill",
    "load_calibrated_commitment",
    "load_skill_by_name",
]
