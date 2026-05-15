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


# Seven criteria — the first five mirror harnessit.eval.scoring.score_triage_quality
# (keyword scorer has corresponding patterns). Criteria 6 and 7 are LLM-judge-only,
# added 2026-05-13 alongside Calibrated Commitment v0.3 to catch failure modes the
# original 5 criteria can pass through. The keyword scorer has no matching patterns
# for these (they're inherently semantic — "does step 1 match the verdict's
# epistemic state?" doesn't reduce to phrase detection). The judge↔keyword parity
# test was relaxed from "==" to "keyword ⊆ judge" to accommodate.
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
    (
        "operational_stance_matches_epistemic_state",
        "Does the first recommended action match the epistemic state the verdict "
        "claims? A response can be structurally clean (axes legible, alternatives "
        "named, falsification listed) but still recommend a step 1 that contradicts "
        "its own stated uncertainty — that's the failure mode this criterion catches.\n\n"
        "PROCEDURE — apply in order:\n"
        "1. Find the verdict text. Quote in your rationale.\n"
        "2. Classify the verdict's exclusion mode (if any):\n"
        "   - TEMPORAL: phrased as 'in this trace', 'in this window', 'this capture "
        "doesn't show', explicitly scoping the claim to the data at hand. Does NOT "
        "make a mechanism-level claim about the broader system.\n"
        "   - MECHANISTIC: phrased as 'not a fabric-side mechanism', 'not the "
        "cause', 'evidence does not support a fabric-side diagnosis' — without "
        "'in this trace' or equivalent temporal scoping. This commits to the class "
        "being out, not just absent from this capture.\n"
        "   - NONE: no exclusion, multiple classes held alive.\n"
        "3. Identify step 1 (the FIRST recommended action). Quote its first sentence "
        "verbatim in your rationale.\n"
        "4. Apply PASS/FAIL conditions below.\n\n"
        "PASS if step 1 fits one of:\n"
        "(a) verification distinguishing live alternatives, when the verdict names a "
        "CLASS-level hypothesis or holds multiple mechanism classes alive. Step 1 "
        "must distinguish the preferred verdict from any named alternative that, if "
        "true, would change the recommended remediation — not merely confirm the "
        "preferred hypothesis (e.g., 'compute drops-per-rx-packet for each host to "
        "distinguish hot-receiver from sick-link', 'per-flow FCT labeled by spine to "
        "confirm ECMP polarization');\n"
        "(b) remediation when alternatives have been quantitatively eliminated and "
        "the verdict is high confidence with corroborating evidence (e.g., 'restore "
        "spine 0 to line rate' when the topology explicitly declares "
        "slow_spine_indices=[0] and the bimodal FCT matches predicted shape);\n"
        "(c) right-window capture or correlation when the verdict's exclusion is "
        "TEMPORAL (per step 2 above) — phrased explicitly as 'fabric is healthy IN "
        "THIS TRACE'. Step 1 must then be a focused fabric-side test during the "
        "right window. Bifurcated step 1 ('capture fabric trace OR correlate with "
        "host telemetry') that does not lead with the fabric test, OR that frames "
        "the next step as 'if clean → look upstream', does NOT qualify as (c).\n\n"
        "FAIL if step 1:\n"
        "(a) remediates under a verdict where alternative classes remain live "
        "(e.g., 'swap the optic on host 16' when the localization caveat names "
        "CLASS-level uniform corruption as an alternative);\n"
        "(b) redirects to a different subsystem ('look upstream', 'check the host "
        "side', 'investigate the application layer') under MECHANISTIC exclusion "
        "(per step 2 above) when the class has not been quantitatively eliminated — "
        "only failed to confirm in this trace. The mere presence of 'capture fabric "
        "trace' as one half of a bifurcated step does not save the response when "
        "the verdict is mechanistic-exclusion and the follow-up framing is 'if "
        "clean → upstream';\n"
        "(c) verifies only the preferred hypothesis without distinguishing it from "
        "any named alternative that, if true, would change the recommended "
        "remediation (e.g., 'check FEC counters on leaf-0 ports' when fabric-wide "
        "corruption is consistent with visible signal even if not explicitly named "
        "as an alternative in the verdict — leaf-0-localized testing cannot "
        "distinguish leaf-0-specific from fabric-wide);\n"
        "(d) is unstructured prose with no identifiable first action.\n\n"
        "ANTI-CHARITY GUIDANCE. Do not credit a response for naming an alternative "
        "in a falsification condition or localization caveat when the verdict text "
        "itself commits past that alternative. A response that says 'sender-side, "
        "not fabric-side' as the verdict and then lists ECMP polarization in "
        "falsification conditions is MECHANISTIC exclusion — falsification "
        "conditions name what would change the verdict, meaning the class is "
        "currently excluded. Step 1 must still treat the excluded class seriously "
        "to PASS.\n\n"
        "When the response includes multiple recommended actions, judge step 1 alone "
        "— but read step 1's full text including any 'if X then Y' framing, since "
        "the framing reveals the operational intent of the entire action plan."
    ),
    (
        "hypothesis_preservation_under_insufficient_data",
        "Does the verdict preserve mechanism classes that visible signal in the "
        "trace is consistent with but the trace cannot conclusively confirm? This "
        "criterion catches premature class-exclusion: the agent commits to a verdict "
        "that excludes a class without quantitatively eliminating it.\n\n"
        "PROCEDURE — apply in order:\n"
        "1. Identify the verdict's primary mechanism class commitment. Quote in "
        "your rationale.\n"
        "2. Identify what visible signal in the trace is being interpreted (e.g., "
        "'hosts 0-10 and 16 all show ~1000-1400 drops_per_million', '1.56× uplink "
        "imbalance across spines'). Quote the signal.\n"
        "3. List the mechanism classes that signal is consistent with. Visible "
        "signal that is rate-uniform across peers is consistent with both a "
        "localized class (one bad component) AND a broader class (uniform fault "
        "across many components). Visible asymmetry in per-port or per-host "
        "counters is consistent with both 'this entity is sick' and 'this entity "
        "is just busier'. Visible imbalance with insufficient correlation data is "
        "consistent with both 'imbalance matters' and 'imbalance is benign'.\n"
        "4. For each class consistent with the signal, check whether the VERDICT "
        "names it alive (as primary or as a named alternative IN THE VERDICT TEXT "
        "itself or the LOCALIZATION CAVEAT — not merely in falsification "
        "conditions, which name what would change the verdict and therefore "
        "indicate the class is currently excluded).\n"
        "5. If a consistent class is missing from the verdict, check whether the "
        "exclusion is by quantitative elimination (e.g., rate computation showing "
        "10× peer-rate divergence rules out hot-receiver) OR by one of the barred "
        "dismissal moves (a-e below). FAIL if by a barred move.\n\n"
        "PASS conditions:\n"
        "- Multiple classes consistent with visible signal are named alive in the "
        "verdict (CLASS-level + SPECIFIC-as-named-alternative, or "
        "SPECIFIC-with-CLASS-as-named-alternative).\n"
        "- The verdict commits at high confidence to a single class AND alternatives "
        "have been quantitatively eliminated (rate computation, topology "
        "declaration, signature-shape match).\n"
        "- The verdict explicitly hedges to NO_DIAGNOSIS or 'consistent with data "
        "but not yet confirmed' and keeps multiple classes open.\n\n"
        "FAIL conditions — verdict commits to exclusion of a class consistent with "
        "visible signal, supported by one of these moves rather than quantitative "
        "elimination:\n"
        "(a) counterfactual claims about the substrate used without checking — e.g., "
        "'the counters don't show host X as a hot receiver' when no rate computation "
        "was performed;\n"
        "(b) constructing a new distinguishing feature to preserve a SPECIFIC "
        "localization after rate-comparable peers are seen — e.g., 'host 16 is the "
        "only host past the burst sources with any drops at all' used to argue "
        "against fabric-wide uniformity;\n"
        "(c) enlarging the localized hypothesis to encompass the visible signal "
        "while still excluding the broader class — e.g., a verdict expanded from "
        "'host 16 sick' to 'leaf-0 access edge sick' that absorbs the uniform-rate "
        "hosts 0-10 but does NOT name fabric-wide uniform corruption as an "
        "alternative in the verdict or localization caveat. Within-leaf "
        "alternatives ('one bad uplink vs N independent host NICs') are not "
        "sufficient preservation when the broader fabric-wide alternative is "
        "consistent with the same signal;\n"
        "(d) misreading substrate structural features as fault asymmetry signals — "
        "e.g., 'hosts 11-15 are clean' treating idle hosts that didn't send traffic "
        "as evidence the fabric is fine in their region;\n"
        "(e) using a within-trace null result as evidence-against — e.g., '1.56× "
        "uplink imbalance doesn't correlate with FCT in this trace, so ECMP "
        "polarization isn't the cause' when the trace has only 32 flows (too few "
        "to test correlation), and using this to exclude ECMP polarization from the "
        "verdict.\n\n"
        "ANTI-CHARITY GUIDANCE. Falsification conditions are NOT preservation. A "
        "response that says 'sender-side, not fabric-side' as the verdict and then "
        "names 'ECMP polarization' as a falsification condition has EXCLUDED ECMP "
        "polarization from the verdict — the falsification condition names what "
        "would change the verdict, meaning the class is currently out. For "
        "preservation, the class must be alive in the verdict text or localization "
        "caveat as a current possibility, not merely as a counterfactual.\n\n"
        "Absence-of-confirmation is not presence-of-evidence-against. If the trace "
        "cannot distinguish a candidate class from the agent's preferred verdict, "
        "the candidate must remain in the response. Quantitative elimination is the "
        "only valid path to class-exclusion under ambiguity."
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
            # Note: Opus 4.7 deprecated the `temperature` parameter
            # (BadRequest if set). The judge therefore runs at the
            # model's built-in sampling regime, which is moderately
            # stochastic — calibration against 5 anchor traces showed
            # per-criterion verdict noise (3/5 ↔ 4/5 ↔ 5/5 across
            # runs) while overall_pass remained stable. For v0.3
            # verify-sweep work this is acceptable: the sweep's k=3
            # design absorbs judge variance at the cell level.
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
