"""LLM-as-judge v0.1 — semantic scoring for triage-quality rubrics.

Background. Stage 2's keyword scorer (``harnessit.eval.scoring``) was
shipped as a v0.1 with a known limitation: regex matching is brittle
against the way real model responses phrase things. By 2026-05-07,
six measurements across the three Stage 3 microburst variants had
established the scorer's noise floor at ~2 criteria — score swings of
2/4 ↔ 4/4 on the same scenario code with no intervention. The
pedagogical signal Stage 3 wanted to demonstrate (with-tool reaches
with-topology-quality triage) was buried under regex variance.

Build Plan v0.3 §2.1 placed LLM-as-judge at Stage 11+ ("eval
governance"). The 2026-05-07 findings made that placement wrong: the
brittleness was structural to keyword scoring, not an artifact of
immature scenarios. This module is the v0.4-candidate Build Plan
change — Stage 11's full eval-governance work (panel-of-judges,
calibration dashboards, judge-vs-judge agreement) remains future, but
v0.1 LLM scoring lands here as Stage 3+ infrastructure.

Design. v0.1 deliberately minimal:

* One judge (Anthropic, Opus 4.7 default — same model class as the
  agent, so the judge can recognize sophisticated reasoning the agent
  produces; downshift to Sonnet later if calibration shows it's
  sufficient).
* Fixed rubric mirrored from
  ``harnessit.eval.scoring.score_triage_quality`` so keyword and LLM
  scoring evaluate the same four criteria. The semantic understanding
  is the only difference.
* Structured output via Anthropic's tool_choice mechanism: the judge
  is forced to call a ``submit_score`` tool; the tool's input_schema
  encodes the response shape.
* The judge never sees ground truth (intended_symptom, root_cause).
  These criteria are about triage *quality*, not *correctness* — a
  judge that grades on "knows the answer" would defeat the rubric's
  purpose. In production the agent never has ground truth either.
* Failures (network, malformed output, missing tool_use) raise
  ``JudgeError``. The runner catches and falls back to keyword
  scoring; both scores are preserved on the EvalResult for the
  calibration table.

Use::

    judge = Judge.from_settings(settings)
    judgment = await judge.score(
        system_prompt=...,
        user_prompt=...,
        agent_response=...,
        tool_calls=...,  # ToolCall tuple from runner; may be empty
    )
    score = judgment.to_score()  # for downstream Score-shaped consumers
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from harnessit.config import Settings
from harnessit.eval.scoring import Score
from harnessit.model import ToolCall
from harnessit.tracing import JUDGE_SPAN_NAME  # re-export for legacy callers

__all_re_exports__ = (JUDGE_SPAN_NAME,)  # silence "unused import" linters

DEFAULT_JUDGE_MODEL = "claude-opus-4-7"


@dataclass(frozen=True)
class CriterionJudgment:
    """One criterion's verdict from the judge.

    ``rationale`` is expected to cite a specific phrase or pattern
    from the agent's response — the judge prompt requires it. This is
    what the keyword scorer's per-pattern hits couldn't provide and
    what makes the LLM scorer's output legible at trace-review time.
    """

    name: str
    passed: bool
    rationale: str


@dataclass(frozen=True)
class Judgment:
    """The judge's structured evaluation of one agent response."""

    overall_pass: bool
    overall_rationale: str
    criteria: tuple[CriterionJudgment, ...]
    judge_model: str

    def to_score(self) -> Score:
        """Convert to the keyword-scorer-shaped ``Score`` for compat.

        Loses per-criterion rationale (Score.criteria is bool-only); the
        full ``Judgment`` is preserved on the EvalResult separately for
        the calibration table.
        """
        return Score(
            overall_pass=self.overall_pass,
            criteria={c.name: c.passed for c in self.criteria},
            rationale=self.overall_rationale,
        )


# Four criteria mirroring harnessit.eval.scoring.score_triage_quality.
# Description text is what the judge sees in its prompt; keep it sharp.
RUBRIC_CRITERIA: tuple[tuple[str, str], ...] = (
    (
        "considers_multiple_hypotheses",
        "Names at least 3 distinct hypothesis classes a network engineer would weigh "
        "given the symptom (e.g., incast/microburst, ECMP imbalance/polarization, "
        "PFC propagation/HoL blocking, ECN/DCQCN behavior, host-side issues like NIC "
        "or driver, link/cable/optical degradation, silent drops, topology issues, "
        "buffer/queue saturation). PASS = at least 3 distinct mechanism classes "
        "actually named (not just mentioned in passing). FAIL = single-explanation "
        "lock-in or only 1-2 hypotheses."
    ),
    (
        "names_telemetry_to_query",
        "Names at least 4 distinct telemetry sources or signal categories the agent "
        "would query: per-flow completion data / FCT lists, percentile distributions, "
        "per-link or per-port counters, queue depth / buffer occupancy, PFC counters / "
        "pause frames, ECN counters / CNP rate, incomplete-flow counts, topology / path "
        "info, NIC-side counters (rx_discards, out_of_buffer, etc.), CRC / FEC errors, "
        "link state. PASS = at least 4 distinct categories named with enough "
        "specificity that an SRE could go pull them. FAIL = generic 'check the "
        "counters' without specificity, or fewer than 4 categories."
    ),
    (
        "acknowledges_unknowns",
        "Acknowledges what it doesn't know. Hedges where appropriate. Asks clarifying "
        "questions. Calls out missing data, missing context, or uncertainty about scope. "
        "PASS = at least one of: explicit hedging language, clarifying questions to the "
        "user, named data gaps ('I'd need X'), or qualified hypotheses ('most likely... "
        "but could also be...'). FAIL = false-confidence guessing, asserting a single "
        "root cause without qualification, or pretending it has data it doesn't."
    ),
    (
        "coherent_investigation_order",
        "The response is structured as an ordered investigation plan, not a bag of "
        "disconnected points. PASS = numbered list, ordered prose with words like "
        "'first / then / next / finally', explicit ranking of hypotheses by likelihood, "
        "or 'start with X because Y, then Z'. FAIL = flat bullet list with no implied "
        "ordering, or a wall of text where the steps are not separable."
    ),
    (
        "synthesizes_available_context",
        "Does the response INTEGRATE the available fabric context (topology data, "
        "scenario inputs, structural facts the agent has been given or has retrieved) "
        "into a sharper analysis, rather than ENUMERATING generic possibilities? This "
        "is the criterion that distinguishes 'thoughtful synthesis' from 'on-call "
        "playbook compliance'. Concrete signals (any one is sufficient evidence): "
        "(a) names specific fabric entities — 'host id 0', 'leaf 0', 'node 16', "
        "'11.0.1.1', 'spine 18' — rather than generic ones like 'the destination's "
        "leaf' or 'a spine'; "
        "(b) uses fabric numbers in quantitative reasoning — '1.5x is consistent "
        "with one or two extra concurrent senders sharing a 25 Gbps link', or 'with "
        "4 spines and 100 Gbps each, polarization onto one spine would explain N'; "
        "(c) explicitly rules out hypotheses based on what the data shows — "
        "'asymmetry: false, so cable degradation is unlikely', 'topology reports no "
        "slow spine, so this isn't structural'; "
        "(d) identifies meta-patterns — 'the cause is dynamic rather than structural', "
        "'this must be runtime-state, not config'. "
        "PASS = at least one synthesis move with phrase-level evidence cited in your "
        "rationale. FAIL = enumeration without integration; lists possibilities "
        "without using available context to prune them; talks about the fabric "
        "abstractly when concrete entities are available; treats the symptom "
        "('1.5x slowdown') as a label rather than a magnitude to reason about. "
        "Note: a response with no available context to integrate (e.g., bare "
        "symptom-only with no topology and no tools) can still pass via meta-pattern "
        "recognition or quantitative reasoning about the symptom itself; but it's "
        "harder, and that's the point — synthesis is genuinely scarcer when context "
        "is scarcer."
    ),
)


SUBMIT_SCORE_TOOL: dict[str, Any] = {
    "name": "submit_score",
    "description": (
        "Submit your final evaluation. You MUST call this exactly once with one "
        "entry per rubric criterion plus the overall verdict. The criteria array "
        "must contain entries for every rubric criterion named in your instructions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "array",
                "description": (
                    "One entry per rubric criterion. Each entry's name must match "
                    "one of the criterion names in your instructions exactly."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The criterion name; must match exactly.",
                        },
                        "passed": {
                            "type": "boolean",
                            "description": "True if the criterion is satisfied.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": (
                                "1-3 sentences citing specific phrases from the "
                                "assistant's response. No vague summaries."
                            ),
                        },
                    },
                    "required": ["name", "passed", "rationale"],
                },
            },
            "overall_pass": {
                "type": "boolean",
                "description": (
                    "True if and only if every criterion passes. If any criterion "
                    "fails, this MUST be False."
                ),
            },
            "overall_rationale": {
                "type": "string",
                "description": (
                    "1-2 sentence summary verdict. Cite which criteria passed and "
                    "which failed."
                ),
            },
        },
        "required": ["criteria", "overall_pass", "overall_rationale"],
    },
}


JUDGE_SYSTEM_PROMPT = (
    "You are evaluating the quality of an investigation response from a network-"
    "investigation assistant working on an RDMA leaf-spine fabric. The assistant "
    "received a help ticket from a sysadmin and produced a response. Your job is to "
    "judge whether the response demonstrates the listed triage-quality criteria — "
    "the way a competent on-call engineer would reason. You are NOT evaluating "
    "whether the response identifies the correct root cause; you are evaluating the "
    "quality of the investigative thinking.\n\n"
    "Be specific. In your per-criterion rationale, cite phrases from the assistant's "
    "response — quote them when useful. Do not grade on a curve. A response that "
    "asks 5 vague questions but names no fabric mechanisms does not pass "
    "'considers_multiple_hypotheses'. A response that names mechanisms but doesn't "
    "specify telemetry does not pass 'names_telemetry_to_query'. A response that "
    "asserts a single root cause confidently does not pass 'acknowledges_unknowns'.\n\n"
    "Submit your verdict by calling the submit_score tool exactly once."
)


def _format_tool_calls_section(tool_calls: tuple[ToolCall, ...]) -> str:
    """Render tool calls for the judge so it can see what the agent retrieved."""
    if not tool_calls:
        return ""
    lines = ["", "## Tools the assistant invoked during its response", ""]
    for i, tc in enumerate(tool_calls, start=1):
        lines.append(f"{i}. **{tc.name}**(`{tc.input}`)")
        # Truncate long tool outputs so the judge prompt doesn't explode
        output_preview = tc.output_serialized
        if len(output_preview) > 1500:
            output_preview = output_preview[:1500] + "... [truncated]"
        lines.append(f"   Returned: {output_preview}")
    return "\n".join(lines)


def _build_judge_user_message(
    *,
    system_prompt: str,
    user_prompt: str,
    agent_response: str,
    tool_calls: tuple[ToolCall, ...],
) -> str:
    """Assemble the user-message body the judge evaluates."""
    criteria_block = "\n\n".join(
        f"### {name}\n\n{description}" for name, description in RUBRIC_CRITERIA
    )
    tool_calls_block = _format_tool_calls_section(tool_calls)
    return (
        "## Rubric criteria\n\n"
        f"{criteria_block}\n\n"
        "## Inputs the assistant received\n\n"
        "### System prompt to the assistant\n\n"
        f"{system_prompt}\n\n"
        "### User message to the assistant (help ticket)\n\n"
        f"{user_prompt}\n\n"
        "## Assistant's response\n\n"
        f"{agent_response}"
        f"{tool_calls_block}\n\n"
        "## Submit your verdict\n\n"
        "Evaluate each criterion in the order they appear above. The criteria "
        "array in your submit_score call must include exactly one entry per rubric "
        "criterion, with `name` matching the heading exactly. Set `overall_pass` to "
        "True if and only if every criterion passes; if any criterion fails, set it "
        "to False. Submit via the submit_score tool now."
    )


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _AnthropicLike(Protocol):
    messages: _MessagesAPI


class JudgeError(RuntimeError):
    """Raised when the judge fails to produce a usable verdict.

    Caught by the runner so the eval can fall back to keyword scoring;
    the failure is logged on the eval span as ``judge_error`` metadata.
    """


class Judge:
    """v0.1 LLM-as-judge for triage-quality scoring.

    Parameters
    ----------
    client:
        An object exposing ``client.messages.create(...)`` — the
        Anthropic SDK's ``Anthropic`` instance, or a fake in tests.
    model:
        Judge model id. Defaults to claude-opus-4-7 (same model class
        as the agent so the judge can recognize sophisticated
        reasoning).
    max_tokens:
        Max tokens for the judge's response. Default 2048 — enough for
        a per-criterion rationale + overall summary; too low risks
        truncation mid-tool-use.
    """

    def __init__(
        self,
        *,
        client: _AnthropicLike,
        model: str = DEFAULT_JUDGE_MODEL,
        max_tokens: int = 2048,
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
        max_tokens: int = 2048,
    ) -> "Judge":
        """Construct using a real ``anthropic.Anthropic`` from Settings."""
        from anthropic import Anthropic

        return cls(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=model or DEFAULT_JUDGE_MODEL,
            max_tokens=max_tokens,
        )

    async def score(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        agent_response: str,
        tool_calls: tuple[ToolCall, ...] = (),
    ) -> Judgment:
        """Score one agent response. Raises ``JudgeError`` on failure.

        Async at the outer boundary so the runner can call it from an
        async eval loop; the underlying SDK call is sync via
        ``asyncio.to_thread`` (same pattern as ``ModelClient.complete_with_tools``).
        """
        judge_user = _build_judge_user_message(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            agent_response=agent_response,
            tool_calls=tool_calls,
        )

        try:
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": judge_user}],
                tools=[SUBMIT_SCORE_TOOL],
                tool_choice={"type": "tool", "name": "submit_score"},
            )
        except Exception as exc:  # network / auth / SDK error
            raise JudgeError(f"Judge API call failed: {exc!r}") from exc

        return _parse_judgment(response, judge_model=getattr(response, "model", self.model))


def _parse_judgment(response: Any, *, judge_model: str) -> Judgment:
    """Extract Judgment from a forced-tool-use Anthropic response."""
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != "submit_score":
            continue
        return _judgment_from_input(block.input, judge_model=judge_model)
    raise JudgeError(
        "Judge produced no submit_score tool_use block (tool_choice should have "
        "forced one)"
    )


def _judgment_from_input(payload: Any, *, judge_model: str) -> Judgment:
    """Validate + structure the submit_score tool input dict."""
    if not isinstance(payload, dict):
        raise JudgeError(f"submit_score payload is not a dict: {type(payload).__name__}")
    try:
        criteria_raw = payload["criteria"]
        if not isinstance(criteria_raw, list):
            raise JudgeError(
                f"submit_score criteria is not a list: {type(criteria_raw).__name__}"
            )
        criteria = tuple(
            CriterionJudgment(
                name=str(c["name"]),
                passed=bool(c["passed"]),
                rationale=str(c["rationale"]),
            )
            for c in criteria_raw
        )
        return Judgment(
            overall_pass=bool(payload["overall_pass"]),
            overall_rationale=str(payload["overall_rationale"]),
            criteria=criteria,
            judge_model=judge_model,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise JudgeError(f"Judge produced malformed submit_score payload: {exc!r}") from exc


__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "JUDGE_SPAN_NAME",
    "JUDGE_SYSTEM_PROMPT",
    "Judge",
    "JudgeError",
    "Judgment",
    "CriterionJudgment",
    "RUBRIC_CRITERIA",
    "SUBMIT_SCORE_TOOL",
]
