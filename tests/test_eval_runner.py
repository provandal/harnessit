"""Tests for the eval runner — fakes for substrate + model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from harnessit.eval import EvalScenario, run_eval
from harnessit.eval.runner import EVAL_SPAN_NAME, format_eval_summary
from harnessit.eval.scoring import Score
from harnessit.model import Completion, ModelClient
from harnessit.substrate import DoppelgangerClient
from harnessit.tracing import GENERATION_SPAN_NAME


# ---------- shared fakes ----------

@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[Any]
    model: str
    usage: Any
    stop_reason: str | None = "end_turn"


class _RecordingMessagesAPI:
    def __init__(self, text: str = "model said this") -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        return _FakeMessage(
            content=[_FakeTextBlock(text=self.text)],
            model=kwargs["model"],
            usage=_FakeUsage(input_tokens=42, output_tokens=7),
        )


@dataclass
class _FakeAnthropic:
    messages: _RecordingMessagesAPI


# ---------- fake substrate session ----------

@dataclass
class _FakeTextContent:
    text: str
    type: str = "text"


@dataclass
class _FakeToolResult:
    content: list[Any]
    isError: bool = False


class _FakeSubstrateSession:
    """Mimics enough of mcp.ClientSession for run_eval. Records calls."""

    def __init__(self, comparison: dict[str, Any]) -> None:
        self.comparison = comparison
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> _FakeToolResult:
        self.calls.append((name, arguments))
        if name == "run_scenario":
            run_id = arguments.get("run_id", f"auto-{arguments['name']}")
            envelope = {
                "data": {
                    "scenario": arguments["name"],
                    "run_id": run_id,
                    "trace_dir": f"traces/{run_id}",
                    "compiled_config_path": None,
                    "wall_clock_seconds": 1.5,
                    "summary": {},
                    "flows": [],
                },
                "source": "driver.run_scenario",
                "observed_at_ns": None,
                "confidence": "high",
                "staleness_class": "fresh",
            }
        elif name == "compare_runs":
            envelope = {
                "data": self.comparison,
                "source": "eval.compare_runs(parsed-from-disk)",
                "observed_at_ns": None,
                "confidence": "high",
                "staleness_class": "stale",
            }
        else:
            raise AssertionError(f"unexpected tool call: {name}")
        return _FakeToolResult(content=[_FakeTextContent(text=json.dumps(envelope))])

    async def list_tools(self) -> Any:
        raise NotImplementedError


# ---------- shared comparison + scenario builders ----------

def _comparison_with_silent_drops() -> dict[str, Any]:
    return {
        "baseline_trace_dir": "traces/base",
        "injected_trace_dir": "traces/inj",
        "flow_count_delta": -5,
        "has_count_divergence": True,
        "fct_p50_delta_ns": 12_000,
        "fct_p99_delta_ns": 80_000,
        "fct_p999_delta_ns": 120_000,
        "baseline_summary": {"total": 255, "completed": 255, "incomplete": 0},
        "injected_summary": {"total": 250, "completed": 248, "incomplete": 2},
        "findings": ["flow count divergence detected"],
    }


def _build_user_prompt(comparison: dict[str, Any]) -> str:
    return (
        f"flow_count_delta: {comparison['flow_count_delta']}\n"
        f"fct_p99_delta_ns: {comparison['fct_p99_delta_ns']}\n"
        f"findings: {comparison['findings']}\n"
    )


def _strict_score(comparison: dict[str, Any], completion: Completion) -> Score:
    return Score(
        overall_pass="silent drop" in completion.text.lower(),
        criteria={"identifies_failure_class": "silent drop" in completion.text.lower()},
        rationale="strict scorer for tests",
    )


def _make_scenario() -> EvalScenario:
    return EvalScenario(
        name="silent-drops-localization",
        description="naked model attempts to localize silent drops",
        system_prompt="You are an investigation agent.",
        baseline_scenario="spike-burst-baseline",
        injected_scenario="spike-burst-silent-drops",
        build_user_prompt=_build_user_prompt,
        score=_strict_score,
        expected_to_pass=False,
    )


def _make_model_client(text: str) -> tuple[ModelClient, _RecordingMessagesAPI]:
    api = _RecordingMessagesAPI(text=text)
    client = ModelClient(client=_FakeAnthropic(messages=api), model="claude-opus-4-7")
    return client, api


# ---------- tests (use shared `exporter` fixture from conftest) ----------

async def test_run_eval_orchestrates_substrate_calls_and_completion(exporter):
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, api = _make_model_client("I see silent drops here.")

    result = await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="test-prefix",
    )

    # Substrate call sequence: baseline, injected, compare
    assert [c[0] for c in session.calls] == [
        "run_scenario",
        "run_scenario",
        "compare_runs",
    ]
    # run_id pass-through
    assert session.calls[0][1]["run_id"] == "test-prefix__baseline"
    assert session.calls[1][1]["run_id"] == "test-prefix__injected"
    # compare_runs gets the trace_dirs from prior run results
    compare_args = session.calls[2][1]
    assert compare_args["baseline_trace_dir"] == "traces/test-prefix__baseline"
    assert compare_args["injected_trace_dir"] == "traces/test-prefix__injected"

    # Model call gets the formatted prompt from the scenario
    assert "flow_count_delta: -5" in api.calls[0]["messages"][0]["content"]


async def test_run_eval_returns_full_result(exporter):
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("I see silent drops here.")

    result = await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="case-a",
    )
    assert result.scenario_name == "silent-drops-localization"
    assert result.baseline_run_id == "case-a__baseline"
    assert result.injected_run_id == "case-a__injected"
    assert result.baseline_trace_dir == "traces/case-a__baseline"
    assert result.injected_trace_dir == "traces/case-a__injected"
    assert result.comparison["flow_count_delta"] == -5
    assert result.score.overall_pass is True
    assert result.langfuse_trace_id  # populated from the live client


async def test_run_eval_naked_model_visible_failure(exporter):
    """Naked model gives a vague answer; eval correctly marks it failed."""
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("I'm not sure, more telemetry needed.")

    result = await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
    )
    assert result.score.overall_pass is False


async def test_run_eval_emits_eval_and_generation_spans(exporter):
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("silent drop detected")

    await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="span-check",
    )
    from langfuse import get_client

    get_client().flush()
    span_names = [s.name for s in exporter.get_finished_spans()]
    assert EVAL_SPAN_NAME in span_names
    assert GENERATION_SPAN_NAME in span_names


async def test_run_eval_eval_span_records_score_metadata(exporter):
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("silent drop detected")

    await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="metadata-check",
    )
    from langfuse import get_client

    get_client().flush()
    eval_span = next(
        s for s in exporter.get_finished_spans() if s.name == EVAL_SPAN_NAME
    )
    attrs = eval_span.attributes or {}
    output = json.loads(attrs["langfuse.observation.output"])
    assert output["overall_pass"] is True
    assert output["criteria"] == {"identifies_failure_class": True}
    assert attrs["langfuse.observation.metadata.flow_count_delta"] == -5
    assert attrs["langfuse.observation.metadata.has_count_divergence"] is True
    assert (
        attrs["langfuse.observation.metadata.baseline_run_id"]
        == "metadata-check__baseline"
    )


async def test_run_eval_default_run_id_prefix_uses_scenario_name(exporter):
    session = _FakeSubstrateSession(_comparison_with_silent_drops())
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("silent drop")

    result = await run_eval(
        scenario=_make_scenario(),
        substrate=substrate,
        model_client=model_client,
    )
    assert result.baseline_run_id.startswith("silent-drops-localization-")
    assert result.baseline_run_id.endswith("__baseline")


def test_format_eval_summary_includes_key_fields():
    from harnessit.eval.types import EvalResult

    result = EvalResult(
        scenario_name="silent-drops-localization",
        baseline_run_id="abc__baseline",
        baseline_trace_dir="traces/abc__baseline",
        injected_run_id="abc__injected",
        injected_trace_dir="traces/abc__injected",
        comparison=_comparison_with_silent_drops(),
        completion=Completion(
            text="silent drop, fewer flows, p99",
            model="claude-opus-4-7",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        ),
        score=Score(
            overall_pass=False,
            criteria={"identifies_failure_class": True, "cites_flow_count_delta": False},
            rationale="x",
        ),
        user_prompt="prompt",
        langfuse_trace_id="trace-xyz",
    )
    text = format_eval_summary(result)
    assert "silent-drops-localization" in text
    assert "flow_count_delta: -5" in text
    assert "abc__baseline" in text
    assert "trace-xyz" in text
    assert "PASS" in text  # at least one criterion passed
    assert "FAIL" in text  # at least one criterion failed
    assert "overall_pass: False" in text
