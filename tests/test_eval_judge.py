"""Tests for harnessit.eval.judge — hermetic via fake Anthropic client.

Live judge calls (real Anthropic) are gated as ``requires_anthropic``.
The fake client returns scripted tool_use responses so we can verify
prompt construction, response parsing, and error paths without spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from harnessit.config import load_settings
from harnessit.eval.judge import (
    DEFAULT_JUDGE_MODEL,
    JUDGE_SYSTEM_PROMPT,
    RUBRIC_CRITERIA,
    SUBMIT_SCORE_TOOL,
    CriterionJudgment,
    Judge,
    JudgeError,
    Judgment,
    _judgment_from_input,
)
from harnessit.eval.scoring import score_triage_quality
from harnessit.eval.types import EvalContext
from harnessit.model import Completion, ToolCall


# ---------- fake Anthropic client ----------

@dataclass
class _FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int = 800
    output_tokens: int = 200


@dataclass
class _FakeMessage:
    content: list[Any]
    model: str = DEFAULT_JUDGE_MODEL
    usage: _FakeUsage | None = None
    stop_reason: str | None = "tool_use"


class _ScriptedAPI:
    """Fake messages.create that returns a single pre-built response.

    Records every call so we can assert on prompt shape / tool_choice.
    """

    def __init__(self, response: _FakeMessage | None = None, *, raise_exc: Exception | None = None) -> None:
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.response is None:
            raise AssertionError("test forgot to stage a response or raise_exc")
        return self.response


@dataclass
class _FakeAnthropic:
    messages: _ScriptedAPI


def _make_judgment_payload(
    *,
    overall_pass: bool = True,
    default_criterion_passed: bool = True,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Produce a well-formed submit_score input matching RUBRIC_CRITERIA.

    Per-criterion ``passed`` defaults to ``default_criterion_passed``,
    independent of ``overall_pass`` — so a test can model a 3/4 PASS
    scenario (overall_pass=False but only one criterion failed) by
    overriding just the failed criterion.
    """
    overrides = overrides or {}
    criteria = []
    for name, _description in RUBRIC_CRITERIA:
        ov = overrides.get(name, {})
        criteria.append({
            "name": name,
            "passed": ov.get("passed", default_criterion_passed),
            "rationale": ov.get("rationale", f"stub rationale for {name}"),
        })
    return {
        "criteria": criteria,
        "overall_pass": overall_pass,
        "overall_rationale": "stub overall rationale",
    }


def _make_judge(response: _FakeMessage | None = None, *, raise_exc: Exception | None = None) -> tuple[Judge, _ScriptedAPI]:
    api = _ScriptedAPI(response=response, raise_exc=raise_exc)
    judge = Judge(client=_FakeAnthropic(messages=api), model=DEFAULT_JUDGE_MODEL)
    return judge, api


# ---------- rubric ↔ keyword scorer parity ----------

def test_keyword_criteria_are_subset_of_judge_criteria():
    """The keyword scorer's criteria must be a subset of the judge's
    rubric. The judge may have additional semantic-only criteria
    (e.g., v0.3 added operational_stance_matches_epistemic_state and
    hypothesis_preservation_under_insufficient_data — both
    inherently semantic and not phrase-detectable). EvalResult
    comparisons for the shared criteria remain apples-to-apples; the
    judge-only criteria are LLM-judge-only by design."""
    completion = Completion(
        text="dummy", model="m", input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )
    context = EvalContext(target_run={"run_id": "x", "trace_dir": "y"})
    keyword_score = score_triage_quality(context, completion)

    judge_criterion_names = {name for name, _description in RUBRIC_CRITERIA}
    keyword_criterion_names = set(keyword_score.criteria.keys())
    extra_in_keyword = keyword_criterion_names - judge_criterion_names
    assert not extra_in_keyword, (
        "Keyword scorer has criteria the judge rubric doesn't. "
        f"Keyword-only: {extra_in_keyword}. This breaks the calibration "
        "table — every keyword criterion needs a matching judge criterion."
    )


def test_v03_judge_only_criteria_present():
    """v0.3 added two LLM-judge-only criteria. Catch accidental
    deletion or rename of either — the verify sweep and rubric audit
    depend on both being present."""
    judge_criterion_names = {name for name, _description in RUBRIC_CRITERIA}
    assert "operational_stance_matches_epistemic_state" in judge_criterion_names
    assert "hypothesis_preservation_under_insufficient_data" in judge_criterion_names


def test_v03_criteria_descriptions_cover_failure_modes():
    """The two v0.3 criteria descriptions must cite the concrete failure
    modes observed across the 10-trace cross-scenario analysis —
    otherwise the judge has no anchor for what to FAIL on. We check
    for concept-level substrings rather than verbatim phrases."""
    desc_by_name = dict(RUBRIC_CRITERIA)

    stance = desc_by_name["operational_stance_matches_epistemic_state"].lower()
    # The three PASS branches
    assert "verification" in stance
    assert "remediation" in stance
    assert "right-window" in stance or "temporal" in stance
    # The four FAIL branches
    assert "redirect" in stance
    # Step-1 focus, not the entire action plan
    assert "step 1" in stance

    preservation = desc_by_name["hypothesis_preservation_under_insufficient_data"].lower()
    # The five barred dismissal moves
    assert "counterfactual" in preservation
    assert "new distinguishing feature" in preservation
    assert "enlarging" in preservation
    assert "structural feature" in preservation or "idle" in preservation
    assert "null result" in preservation
    # The core epistemic principle
    assert "absence-of-confirmation" in preservation


# ---------- structured-output mechanics ----------

def test_submit_score_tool_schema_required_fields_present():
    """The schema's required fields must include criteria/overall_pass/
    overall_rationale; the per-criterion required fields must include
    name/passed/rationale. Catches schema regressions silently."""
    schema = SUBMIT_SCORE_TOOL["input_schema"]
    assert set(schema["required"]) == {"criteria", "overall_pass", "overall_rationale"}
    item_schema = schema["properties"]["criteria"]["items"]
    assert set(item_schema["required"]) == {"name", "passed", "rationale"}


@pytest.mark.asyncio
async def test_score_passes_tool_choice_to_anthropic():
    """v0.1 forces structured output via Anthropic's tool_choice. If
    this regresses to plain prompting, the parser's strict tool_use
    requirement starts producing JudgeError on the live path."""
    judge, api = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=_make_judgment_payload())],
    ))
    await judge.score(
        system_prompt="agent system",
        user_prompt="agent user",
        agent_response="agent response",
    )
    assert len(api.calls) == 1
    call = api.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_score"}
    assert call["tools"] == [SUBMIT_SCORE_TOOL]
    assert call["system"] == JUDGE_SYSTEM_PROMPT
    assert call["model"] == DEFAULT_JUDGE_MODEL


@pytest.mark.asyncio
async def test_score_returns_judgment_with_all_criteria():
    """A well-formed tool_use response should be parsed into a Judgment
    with one CriterionJudgment per RUBRIC_CRITERIA entry."""
    payload = _make_judgment_payload(overall_pass=True)
    judge, _ = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=payload)],
        model="claude-opus-4-7",
    ))
    judgment = await judge.score(
        system_prompt="s", user_prompt="u", agent_response="r",
    )
    assert isinstance(judgment, Judgment)
    assert judgment.overall_pass is True
    assert judgment.judge_model == "claude-opus-4-7"
    assert {c.name for c in judgment.criteria} == {n for n, _ in RUBRIC_CRITERIA}
    assert all(isinstance(c, CriterionJudgment) for c in judgment.criteria)


@pytest.mark.asyncio
async def test_score_propagates_overall_pass_false():
    """A judgment with overall_pass=False must round-trip; verify by
    setting one criterion to passed=False and overall_pass=False."""
    overrides = {"considers_multiple_hypotheses": {"passed": False, "rationale": "only 1 hypothesis"}}
    payload = _make_judgment_payload(overall_pass=False, overrides=overrides)
    judge, _ = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=payload)],
    ))
    judgment = await judge.score(system_prompt="s", user_prompt="u", agent_response="r")
    assert judgment.overall_pass is False
    failed = [c for c in judgment.criteria if not c.passed]
    assert len(failed) == 1
    assert failed[0].name == "considers_multiple_hypotheses"


# ---------- prompt content ----------

@pytest.mark.asyncio
async def test_score_prompt_includes_agent_inputs_verbatim():
    """The judge user message must include the agent's system+user+
    response — this is what the judge evaluates against."""
    judge, api = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=_make_judgment_payload())],
    ))
    await judge.score(
        system_prompt="UNIQUE_SYSTEM_MARKER",
        user_prompt="UNIQUE_USER_MARKER",
        agent_response="UNIQUE_RESPONSE_MARKER",
    )
    user_msg = api.calls[0]["messages"][0]["content"]
    assert "UNIQUE_SYSTEM_MARKER" in user_msg
    assert "UNIQUE_USER_MARKER" in user_msg
    assert "UNIQUE_RESPONSE_MARKER" in user_msg


@pytest.mark.asyncio
async def test_score_prompt_includes_tool_calls_when_present():
    """Tool calls should be summarized in the judge prompt so the
    judge can evaluate 'did the agent retrieve the right data?'"""
    judge, api = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=_make_judgment_payload())],
    ))
    tc = ToolCall(
        id="agent_tu_1",
        name="get_topology",
        input={},
        output={"shape": "leaf-spine", "leaves": 2},
        output_serialized='{"shape": "leaf-spine", "leaves": 2}',
    )
    await judge.score(
        system_prompt="s", user_prompt="u", agent_response="r",
        tool_calls=(tc,),
    )
    user_msg = api.calls[0]["messages"][0]["content"]
    assert "get_topology" in user_msg
    # Should mention the section header explicitly
    assert "Tools the assistant invoked" in user_msg


@pytest.mark.asyncio
async def test_score_prompt_truncates_long_tool_outputs():
    """Tool outputs > 1500 chars should be truncated so the judge prompt
    stays manageable on multi-tool runs."""
    judge, api = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=_make_judgment_payload())],
    ))
    huge_output = "X" * 5000
    tc = ToolCall(
        id="agent_tu_1", name="get_topology", input={},
        output={}, output_serialized=huge_output,
    )
    await judge.score(
        system_prompt="s", user_prompt="u", agent_response="r",
        tool_calls=(tc,),
    )
    user_msg = api.calls[0]["messages"][0]["content"]
    assert "[truncated]" in user_msg
    # The full 5000-char string should NOT appear verbatim
    assert huge_output not in user_msg


@pytest.mark.asyncio
async def test_score_prompt_omits_tool_section_when_no_tool_calls():
    """If the agent didn't use tools, don't include an empty tools
    section — saves prompt tokens and avoids confusing the judge."""
    judge, api = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=_make_judgment_payload())],
    ))
    await judge.score(system_prompt="s", user_prompt="u", agent_response="r")
    user_msg = api.calls[0]["messages"][0]["content"]
    assert "Tools the assistant invoked" not in user_msg


# ---------- to_score conversion ----------

def test_judgment_to_score_preserves_overall_and_per_criterion():
    judgment = Judgment(
        overall_pass=False,
        overall_rationale="3/4 passed",
        criteria=(
            CriterionJudgment(name="a", passed=True, rationale="..."),
            CriterionJudgment(name="b", passed=False, rationale="..."),
        ),
        judge_model="claude-opus-4-7",
    )
    score = judgment.to_score()
    assert score.overall_pass is False
    assert score.criteria == {"a": True, "b": False}
    assert score.rationale == "3/4 passed"


# ---------- error paths ----------

@pytest.mark.asyncio
async def test_score_raises_judge_error_on_anthropic_exception():
    """SDK / network errors are wrapped in JudgeError so the runner
    can catch a single exception type and fall back."""
    judge, _ = _make_judge(raise_exc=RuntimeError("network down"))
    with pytest.raises(JudgeError, match="Judge API call failed"):
        await judge.score(system_prompt="s", user_prompt="u", agent_response="r")


@pytest.mark.asyncio
async def test_score_raises_judge_error_when_no_tool_use_block():
    """tool_choice should force submit_score, but if the SDK ever
    returns text-only, fail loudly with JudgeError, not a silent pass."""
    judge, _ = _make_judge(_FakeMessage(
        content=[_FakeTextBlock(text="I think it's fine")],
        stop_reason="end_turn",
    ))
    with pytest.raises(JudgeError, match="no submit_score"):
        await judge.score(system_prompt="s", user_prompt="u", agent_response="r")


@pytest.mark.asyncio
async def test_score_raises_judge_error_on_malformed_payload():
    """Missing required fields in the tool input should raise."""
    bad_payload = {"criteria": [{"name": "x"}], "overall_pass": True}  # missing fields
    judge, _ = _make_judge(_FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_score", input=bad_payload)],
    ))
    with pytest.raises(JudgeError, match="malformed submit_score"):
        await judge.score(system_prompt="s", user_prompt="u", agent_response="r")


def test_judgment_from_input_rejects_non_dict():
    with pytest.raises(JudgeError, match="not a dict"):
        _judgment_from_input("not a dict", judge_model="m")


def test_judgment_from_input_rejects_non_list_criteria():
    with pytest.raises(JudgeError, match="criteria is not a list"):
        _judgment_from_input(
            {"criteria": "oops", "overall_pass": True, "overall_rationale": "x"},
            judge_model="m",
        )


# ---------- live ----------

@pytest.mark.requires_anthropic
async def test_live_judge_smoke():
    """Live smoke test: real Anthropic, evaluating a deliberately weak
    response (one hypothesis, no telemetry, no hedging, no order).
    The judge should produce overall_pass=False with rationale citing
    the missing criteria."""
    settings = load_settings()
    judge = Judge.from_settings(settings, max_tokens=1024)
    judgment = await judge.score(
        system_prompt=(
            "You are a network-investigation assistant for an RDMA leaf-spine "
            "fabric. Help the user diagnose their issue."
        ),
        user_prompt="step time on jobs targeting host 11.0.0.1 is up about 1.5x.",
        agent_response="It's the network. Reboot the host.",
    )
    assert judgment.overall_pass is False, (
        f"Live judge gave overall_pass=True for a deliberately weak response. "
        f"Rationale: {judgment.overall_rationale}"
    )
    assert any(not c.passed for c in judgment.criteria)
