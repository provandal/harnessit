"""Tests for harnessit.eval.correctness — hermetic via fake Anthropic client.

Mirrors the test_eval_judge.py pattern: scripted fake messages.create
returns a pre-built tool_use response so we can verify prompt
construction, response parsing, verdict enum handling, and error paths
without spending tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from harnessit.eval.correctness import (
    CORRECTNESS_JUDGE_SYSTEM_PROMPT,
    DEFAULT_CORRECTNESS_JUDGE_MODEL,
    SUBMIT_CORRECTNESS_TOOL,
    CorrectnessJudge,
    CorrectnessJudgeError,
    CorrectnessJudgment,
    Verdict,
    _judgment_from_input,
)


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
class _FakeMessage:
    content: list[Any]
    model: str = DEFAULT_CORRECTNESS_JUDGE_MODEL
    stop_reason: str | None = "tool_use"


class _ScriptedAPI:
    def __init__(
        self,
        response: _FakeMessage | None = None,
        *,
        raise_exc: Exception | None = None,
    ) -> None:
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


def _make_payload(
    *,
    verdict: str = "CORRECT",
    agent_diagnosis_summary: str = "agent diagnosed ECN misconfiguration",
    rationale: str = "stub rationale citing 'ECN threshold' from response",
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "agent_diagnosis_summary": agent_diagnosis_summary,
        "rationale": rationale,
    }


def _make_response(payload: dict[str, Any]) -> _FakeMessage:
    return _FakeMessage(
        content=[_FakeToolUseBlock(id="tu_1", name="submit_correctness", input=payload)],
    )


def _make_judge(
    response: _FakeMessage | None = None,
    *,
    raise_exc: Exception | None = None,
) -> tuple[CorrectnessJudge, _ScriptedAPI]:
    api = _ScriptedAPI(response=response, raise_exc=raise_exc)
    judge = CorrectnessJudge(
        client=_FakeAnthropic(messages=api),
        model=DEFAULT_CORRECTNESS_JUDGE_MODEL,
    )
    return judge, api


# ---------- verdict enum ----------

def test_verdict_enum_values():
    assert Verdict.CORRECT.value == "CORRECT"
    assert Verdict.WRONG.value == "WRONG"
    assert Verdict.NO_DIAGNOSIS.value == "NO_DIAGNOSIS"


def test_verdict_constructible_from_string():
    assert Verdict("CORRECT") is Verdict.CORRECT
    assert Verdict("NO_DIAGNOSIS") is Verdict.NO_DIAGNOSIS


def test_judgment_correct_property():
    judgment_correct = CorrectnessJudgment(
        verdict=Verdict.CORRECT,
        agent_diagnosis_summary="x",
        rationale="y",
        judge_model="m",
    )
    judgment_wrong = CorrectnessJudgment(
        verdict=Verdict.WRONG,
        agent_diagnosis_summary="x",
        rationale="y",
        judge_model="m",
    )
    judgment_no_dx = CorrectnessJudgment(
        verdict=Verdict.NO_DIAGNOSIS,
        agent_diagnosis_summary="no commitment",
        rationale="y",
        judge_model="m",
    )
    assert judgment_correct.correct is True
    # NO_DIAGNOSIS returns False — distinct from CORRECT, even though
    # not WRONG.
    assert judgment_no_dx.correct is False
    assert judgment_wrong.correct is False


# ---------- submit_correctness tool schema ----------

def test_submit_tool_schema_shape():
    assert SUBMIT_CORRECTNESS_TOOL["name"] == "submit_correctness"
    schema = SUBMIT_CORRECTNESS_TOOL["input_schema"]
    assert set(schema["required"]) == {"verdict", "agent_diagnosis_summary", "rationale"}
    assert set(schema["properties"]["verdict"]["enum"]) == {
        "CORRECT",
        "WRONG",
        "NO_DIAGNOSIS",
    }


# ---------- score() end-to-end via fake client ----------

@pytest.mark.asyncio
async def test_score_correct_verdict_parses():
    payload = _make_payload(verdict="CORRECT")
    judge, api = _make_judge(_make_response(payload))
    judgment = await judge.score(
        system_prompt="sysprompt",
        user_prompt="ticket",
        agent_response="I diagnose ECN misconfig.",
        intended_symptom="PFC elevated alongside ECN near zero",
        root_cause="ECN threshold misconfiguration: KMIN > buffer",
    )
    assert judgment.verdict is Verdict.CORRECT
    assert judgment.correct is True
    assert judgment.judge_model == DEFAULT_CORRECTNESS_JUDGE_MODEL
    # Verify the request shape: system prompt, single user message,
    # forced submit_correctness tool_choice.
    assert len(api.calls) == 1
    call = api.calls[0]
    assert call["system"] == CORRECTNESS_JUDGE_SYSTEM_PROMPT
    assert call["tool_choice"] == {"type": "tool", "name": "submit_correctness"}
    assert call["tools"] == [SUBMIT_CORRECTNESS_TOOL]
    # The user message must contain ground truth and the agent response
    user_msg = call["messages"][0]["content"]
    assert "PFC elevated alongside ECN near zero" in user_msg
    assert "ECN threshold misconfiguration" in user_msg
    assert "I diagnose ECN misconfig." in user_msg


@pytest.mark.asyncio
async def test_score_wrong_verdict_parses():
    payload = _make_payload(verdict="WRONG", agent_diagnosis_summary="diagnosed slow spine")
    judge, _api = _make_judge(_make_response(payload))
    judgment = await judge.score(
        system_prompt="s",
        user_prompt="u",
        agent_response="It is the slow spine.",
        intended_symptom="silent drops",
        root_cause="per-link silent drops at 0.001",
    )
    assert judgment.verdict is Verdict.WRONG
    assert judgment.correct is False


@pytest.mark.asyncio
async def test_score_no_diagnosis_verdict_parses():
    payload = _make_payload(
        verdict="NO_DIAGNOSIS",
        agent_diagnosis_summary="no commitment — bounced to app team",
    )
    judge, _api = _make_judge(_make_response(payload))
    judgment = await judge.score(
        system_prompt="s",
        user_prompt="u",
        agent_response="Counters do not support a network cause.",
        intended_symptom="microburst",
        root_cause="synchronized incast",
    )
    assert judgment.verdict is Verdict.NO_DIAGNOSIS
    assert judgment.correct is False  # not CORRECT, even though not WRONG


# ---------- error paths ----------

@pytest.mark.asyncio
async def test_api_failure_raises_correctness_error():
    judge, _api = _make_judge(raise_exc=RuntimeError("network down"))
    with pytest.raises(CorrectnessJudgeError) as exc_info:
        await judge.score(
            system_prompt="s",
            user_prompt="u",
            agent_response="r",
            intended_symptom="i",
            root_cause="rc",
        )
    assert "network down" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_tool_use_block_raises():
    # Response contains only text, no tool_use — judge violated forced
    # tool_choice somehow. Treat as error.
    response = _FakeMessage(content=[_FakeTextBlock(text="I refuse to use the tool")])
    judge, _api = _make_judge(response)
    with pytest.raises(CorrectnessJudgeError):
        await judge.score(
            system_prompt="s",
            user_prompt="u",
            agent_response="r",
            intended_symptom="i",
            root_cause="rc",
        )


def test_judgment_from_input_rejects_unknown_verdict():
    with pytest.raises(CorrectnessJudgeError):
        _judgment_from_input(
            {
                "verdict": "MAYBE",  # not in enum
                "agent_diagnosis_summary": "x",
                "rationale": "y",
            },
            judge_model="m",
        )


def test_judgment_from_input_rejects_missing_fields():
    with pytest.raises(CorrectnessJudgeError):
        _judgment_from_input(
            {"verdict": "CORRECT"},  # missing summary + rationale
            judge_model="m",
        )


def test_judgment_from_input_rejects_non_dict():
    with pytest.raises(CorrectnessJudgeError):
        _judgment_from_input("not a dict", judge_model="m")
