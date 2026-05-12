"""Diagnosis-correctness LLM scorer — v0.2 operational-stance grading.

Background. The 2026-05-11 capability-envelope sweep (4 fault classes +
baseline) found that the 5-criterion rubric (multi-hyp / telemetry /
unknowns / ordering / synthesis) does not correlate with diagnosis
correctness. Two PASS-rubric runs reached wrong diagnoses; one
FAIL-rubric run reached the correct one. The rubric measures triage
*quality*; what it doesn't measure is whether the agent's named root
cause matches the substrate's actual fault class.

This module adds that missing axis as a separate LLM judge. The rubric
judge and this judge are deliberately orthogonal — the rubric never
sees ground truth (mirrored from production reality where the agent
doesn't know the answer), while this judge sees ground truth (`Scenario.
root_cause` + `Scenario.intended_symptom`) and grades the response.

**v0.2 grading question (2026-05-12, post Calibrated Commitment skill
A/B)**: would an SRE who reads this response and follows its
recommendations reach the ground-truth fault class? The v0.1 strict
verdict-matching question ("does the agent's stated diagnosis name the
same mechanism class as ground truth?") was mis-grading responses
whose verification/recommendation steps would lead an SRE to the right
answer even when the verbal verdict was more specific or less
committal than strict matching expected.

Offline validation of v0.2 against the 4 with-skill A/B traces
(`sweep-logs-2026-05-12-skill/operational_judge_v02.py`): v0.1 strict
gave 1 CORRECT + 2 NO_DIAGNOSIS + 1 WRONG; v0.2 operational gives
3 CORRECT + 1 WRONG. Three of the four shifts moved toward CORRECT
because the agent's recommended verification steps would actually lead
to the ground-truth diagnosis (e.g., silent-drops "verify drops-per-
million before dispatching cable swap" reveals uniform corruption;
microburst "recapture during incident window" surfaces the incast
pattern). The one hash-polarization WRONG is a true skill overshoot
(agent dismissed visible per-port signal and pointed away from fabric).

Three verdicts:

* **CORRECT** — operational stance (verdict + recommendations +
  verification steps) would lead an SRE to the ground-truth fault
  class. Includes responses where the verdict is over-specific but
  recommended verification catches the over-specificity, and
  responses where the verdict refuses to commit but the recommended
  next step gathers data leading to ground truth.
* **WRONG** — operational stance would lead an SRE *away* from the
  ground-truth fault class (wrong-subsystem investigation, dismissed
  visible signal pointing elsewhere).
* **NO_DIAGNOSIS** — operational stance is "gather more data /
  consult another team" WITHOUT directing investigation toward or
  away from the ground-truth fault class. The honest-refusal case
  where the operational outcome is neutral.

Use::

    correctness_judge = CorrectnessJudge.from_settings(settings)
    judgment = await correctness_judge.score(
        system_prompt=...,
        user_prompt=...,
        agent_response=...,
        intended_symptom=...,  # from substrate.list_scenarios
        root_cause=...,
    )

Tool calls are deliberately NOT passed to this judge. Correctness is
about the agent's final stated stance, not the investigation trajectory;
the trajectory is what the rubric measures. Keeping the prompts
disjoint makes both axes legible in isolation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from harnessit.config import Settings

DEFAULT_CORRECTNESS_JUDGE_MODEL = "claude-opus-4-7"


class Verdict(str, Enum):
    """Three-way verdict for diagnosis correctness.

    Values are upper-case strings so the LLM tool-use submission can use
    the same string literals. The `str` mixin makes the enum
    JSON-serializable as the raw value, which keeps Langfuse span output
    legible.
    """

    CORRECT = "CORRECT"
    WRONG = "WRONG"
    NO_DIAGNOSIS = "NO_DIAGNOSIS"


@dataclass(frozen=True)
class CorrectnessJudgment:
    """The correctness judge's structured verdict on one agent response.

    `agent_diagnosis_summary` is a 1-sentence paraphrase of what the
    agent actually concluded as the root cause — useful at trace-review
    time to see at a glance what the agent said without re-reading the
    full response. For NO_DIAGNOSIS verdicts, this is "no commitment"
    or similar.
    """

    verdict: Verdict
    agent_diagnosis_summary: str
    rationale: str
    judge_model: str

    @property
    def correct(self) -> bool:
        """Convenience boolean: True only when verdict == CORRECT.

        NO_DIAGNOSIS returns False here even though it's not WRONG; the
        Langfuse trace score uses CORRECT-or-not as the numeric signal.
        Higher-fidelity readers should inspect `verdict` directly.
        """
        return self.verdict == Verdict.CORRECT


SUBMIT_CORRECTNESS_TOOL: dict[str, Any] = {
    "name": "submit_correctness",
    "description": (
        "Submit your verdict on whether the response correctly identifies "
        "the fault. You MUST call this exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["CORRECT", "WRONG", "NO_DIAGNOSIS"],
                "description": (
                    "CORRECT = response commits to a diagnosis in the same "
                    "mechanism class as ground truth. WRONG = response "
                    "commits to a different mechanism class. NO_DIAGNOSIS "
                    "= response did not commit (declined, enumerated, or "
                    "explicitly hedged the conclusion)."
                ),
            },
            "agent_diagnosis_summary": {
                "type": "string",
                "description": (
                    "1-sentence paraphrase of the agent's stated root "
                    "cause. For NO_DIAGNOSIS verdicts, write 'no commitment' "
                    "or similar."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "2-4 sentences citing the specific phrases from the "
                    "response that establish the agent's diagnosis (or "
                    "its absence) and your verdict."
                ),
            },
        },
        "required": ["verdict", "agent_diagnosis_summary", "rationale"],
    },
}


CORRECTNESS_JUDGE_SYSTEM_PROMPT = (
    "You are evaluating the OPERATIONAL utility of a network-investigation "
    "response. Unlike a strict verdict-matching judge, you are asking: "
    "**would an SRE who reads this response and follows its recommendations "
    "reach the ground-truth fault class?**\n\n"
    "You have access to the ground-truth fault metadata; the response "
    "under evaluation did not. The response may include the agent's stated "
    "verdict, confidence, falsification conditions, symptom-vs-data "
    "alignment notes, localization caveats, and recommended next steps. "
    "Read the whole response as an operational artifact — not just the "
    "verdict string.\n\n"
    "Three verdicts:\n\n"
    "* CORRECT: the response's operational stance (verdict + recommended "
    "actions + verification steps) would lead an SRE to the ground-truth "
    "fault class. This INCLUDES responses where:\n"
    "  - The verdict string is more specific than ground truth supports "
    "BUT the response includes verification steps that would catch the "
    "over-specificity (e.g., 'verify drops-per-million before dispatching "
    "cable swap' — verifying would reveal uniform corruption, leading to "
    "the right fabric-wide diagnosis).\n"
    "  - The verdict refuses to commit BUT the recommended next step "
    "('capture during incident', 'check different time window') would "
    "gather data leading to the ground-truth diagnosis.\n"
    "  - The verdict commits to a class that is the same as ground truth "
    "AND the recommended actions match what an SRE would do.\n\n"
    "* WRONG: the response's operational stance would lead an SRE AWAY "
    "from the ground-truth fault class. This INCLUDES responses where:\n"
    "  - The verdict commits to a different mechanism class AND the "
    "recommended actions would have the SRE investigate the wrong "
    "subsystem (e.g., 'don't go hunting the fabric — check host side' "
    "when fabric IS the cause).\n"
    "  - The verdict refuses to commit AND the recommended actions "
    "explicitly point away from the area where the ground-truth fault "
    "actually lives.\n\n"
    "* NO_DIAGNOSIS: the response's operational stance is 'gather more "
    "data' or 'consult another team' WITHOUT directing investigation "
    "toward or away from the ground-truth fault class. This is the "
    "honest-refusal case where the operational outcome is neutral — "
    "more investigation is needed but no wrong direction was set.\n\n"
    "Key distinction from a strict verdict-matching judge: a response "
    "that explicitly says 'I can't commit, but verify X before "
    "dispatching fix Y' can be CORRECT if verifying X would reveal the "
    "actual ground-truth class. Operational stance > verdict string.\n\n"
    "Substantive equivalence examples for the operational test:\n"
    "* 'PHY corruption on host 16; verify drops-per-million before "
    "dispatching cable swap' vs ground-truth 'uniform per-link silent "
    "drops' → CORRECT (verification step reveals the uniform rate, "
    "leading to fabric-wide silent-drops conclusion).\n"
    "* 'Bounce to app team — fabric counters don't support the network "
    "cause' vs ground-truth 'synchronized incast' → WRONG (recommended "
    "action sends SRE to wrong team; no verification path leads back "
    "to fabric).\n"
    "* 'Trace doesn't match symptom; capture during incident window' "
    "vs ground-truth 'synchronized incast' → CORRECT (recommended "
    "recapture during an actual incident would surface the incast "
    "pattern more clearly; SRE reaches right diagnosis).\n"
    "* 'Spine 0 degraded, drain it from ECMP' vs ground-truth "
    "'asymmetric spine 0 links' → CORRECT (verdict matches, "
    "remediation matches).\n\n"
    "Submit your verdict via the submit_correctness tool exactly once. "
    "Cite specific phrases from the response in your rationale, "
    "particularly the recommended-next-step / verification language "
    "that load-bears your operational read."
)


def _build_correctness_user_message(
    *,
    system_prompt: str,
    user_prompt: str,
    agent_response: str,
    intended_symptom: str,
    root_cause: str,
) -> str:
    """Assemble the user-message body the correctness judge evaluates."""
    return (
        "## Ground truth (NOT visible to the agent under evaluation)\n\n"
        "### Intended symptom\n\n"
        f"{intended_symptom}\n\n"
        "### Root cause class\n\n"
        f"{root_cause}\n\n"
        "## Inputs the assistant received\n\n"
        "### System prompt to the assistant\n\n"
        f"{system_prompt}\n\n"
        "### User message to the assistant (help ticket)\n\n"
        f"{user_prompt}\n\n"
        "## Assistant's response\n\n"
        f"{agent_response}\n\n"
        "## Submit your verdict\n\n"
        "Call submit_correctness exactly once. Set verdict to one of "
        "CORRECT / WRONG / NO_DIAGNOSIS, agent_diagnosis_summary to a "
        "1-sentence paraphrase of the agent's stated diagnosis (or 'no "
        "commitment' if NO_DIAGNOSIS), and rationale to 2-4 sentences "
        "citing the response phrases that establish your verdict."
    )


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _AnthropicLike(Protocol):
    messages: _MessagesAPI


class CorrectnessJudgeError(RuntimeError):
    """Raised when the correctness judge fails to produce a usable verdict.

    Caught by the runner so the eval can still complete; the failure is
    logged on the eval span as `correctness_error` metadata. Distinct
    from `JudgeError` (the rubric judge) so the runner can recover from
    one without affecting the other.
    """


class CorrectnessJudge:
    """LLM judge for diagnosis correctness, orthogonal to the rubric.

    Same shape as `harnessit.eval.judge.Judge`: constructor takes an
    Anthropic-like client; `from_settings` builds one from `Settings`;
    `score(...)` is async at the boundary with `asyncio.to_thread`
    wrapping the sync SDK call.
    """

    def __init__(
        self,
        *,
        client: _AnthropicLike,
        model: str = DEFAULT_CORRECTNESS_JUDGE_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self.model = model
        self.max_tokens = max_tokens

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> "CorrectnessJudge":
        from anthropic import Anthropic

        return cls(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=model or DEFAULT_CORRECTNESS_JUDGE_MODEL,
            max_tokens=max_tokens,
        )

    async def score(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        agent_response: str,
        intended_symptom: str,
        root_cause: str,
    ) -> CorrectnessJudgment:
        """Score one agent response for diagnosis correctness.

        Raises `CorrectnessJudgeError` on API failure or malformed
        judge output.
        """
        judge_user = _build_correctness_user_message(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            agent_response=agent_response,
            intended_symptom=intended_symptom,
            root_cause=root_cause,
        )

        try:
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                system=CORRECTNESS_JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": judge_user}],
                tools=[SUBMIT_CORRECTNESS_TOOL],
                tool_choice={"type": "tool", "name": "submit_correctness"},
            )
        except Exception as exc:
            raise CorrectnessJudgeError(
                f"Correctness judge API call failed: {exc!r}"
            ) from exc

        return _parse_correctness_judgment(
            response, judge_model=getattr(response, "model", self.model)
        )


def _parse_correctness_judgment(
    response: Any, *, judge_model: str
) -> CorrectnessJudgment:
    """Extract CorrectnessJudgment from a forced-tool-use Anthropic response."""
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != "submit_correctness":
            continue
        return _judgment_from_input(block.input, judge_model=judge_model)
    raise CorrectnessJudgeError(
        "Correctness judge produced no submit_correctness tool_use block "
        "(tool_choice should have forced one)"
    )


def _judgment_from_input(payload: Any, *, judge_model: str) -> CorrectnessJudgment:
    """Validate + structure the submit_correctness tool input dict."""
    if not isinstance(payload, dict):
        raise CorrectnessJudgeError(
            f"submit_correctness payload is not a dict: {type(payload).__name__}"
        )
    try:
        verdict_raw = str(payload["verdict"])
        verdict = Verdict(verdict_raw)
        return CorrectnessJudgment(
            verdict=verdict,
            agent_diagnosis_summary=str(payload["agent_diagnosis_summary"]),
            rationale=str(payload["rationale"]),
            judge_model=judge_model,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CorrectnessJudgeError(
            f"Correctness judge produced malformed payload: {exc!r}"
        ) from exc


__all__ = [
    "DEFAULT_CORRECTNESS_JUDGE_MODEL",
    "CORRECTNESS_JUDGE_SYSTEM_PROMPT",
    "CorrectnessJudge",
    "CorrectnessJudgeError",
    "CorrectnessJudgment",
    "SUBMIT_CORRECTNESS_TOOL",
    "Verdict",
]
