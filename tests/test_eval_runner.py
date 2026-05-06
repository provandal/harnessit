"""Tests for the eval runner — single-run + paired shapes via fakes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from harnessit.eval import EvalContext, EvalScenario, run_eval
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
    def __init__(self, text: str = "model response") -> None:
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

    def __init__(self, comparison: dict[str, Any] | None = None) -> None:
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
                    "summary": {"total": 15, "completed": 15, "incomplete": 0},
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


def _make_model_client(text: str) -> tuple[ModelClient, _RecordingMessagesAPI]:
    api = _RecordingMessagesAPI(text=text)
    client = ModelClient(client=_FakeAnthropic(messages=api), model="claude-opus-4-7")
    return client, api


def _stub_score(_context: EvalContext, completion: Completion) -> Score:
    """Test-only deterministic score: pass iff 'pass' literal in output."""
    p = "pass" in completion.text.lower()
    return Score(
        overall_pass=p,
        criteria={"stub_passed": p},
        rationale=f"stub: {'PASS' if p else 'FAIL'}",
    )


def _make_single_run_scenario(prompt_builder=None) -> EvalScenario:
    return EvalScenario(
        name="test-single-run",
        description="single-run test scenario",
        system_prompt="You are a test assistant.",
        target_scenario="microburst",
        baseline_scenario=None,
        build_user_prompt=prompt_builder or (lambda ctx: "user prompt"),
        score=_stub_score,
        expected_to_pass=False,
    )


def _make_paired_scenario() -> EvalScenario:
    return EvalScenario(
        name="test-paired",
        description="paired test scenario",
        system_prompt="You are a test assistant.",
        target_scenario="spike-burst-silent-drops",
        baseline_scenario="spike-burst-baseline",
        build_user_prompt=lambda ctx: f"delta={ctx.comparison['flow_count_delta']}",
        score=_stub_score,
        expected_to_pass=False,
    )


# ---------- single-run shape ----------

async def test_run_eval_single_run_skips_baseline_and_compare(exporter):
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("triage plan: pass")

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="single",
    )

    # Only one substrate call: the target run. No baseline, no compare.
    assert [c[0] for c in session.calls] == ["run_scenario"]
    assert session.calls[0][1]["name"] == "microburst"
    assert session.calls[0][1]["run_id"] == "single__target"

    assert result.target_run_id == "single__target"
    assert result.target_trace_dir == "traces/single__target"
    assert result.baseline_run_id is None
    assert result.baseline_trace_dir is None
    assert result.comparison is None
    assert result.score.overall_pass is True


async def test_run_eval_single_run_passes_context_to_prompt_builder(exporter):
    captured: dict[str, Any] = {}

    def builder(ctx: EvalContext) -> str:
        captured["ctx"] = ctx
        return f"target_run_id={ctx.target_run['run_id']}"

    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, api = _make_model_client("response: pass")

    await run_eval(
        scenario=_make_single_run_scenario(prompt_builder=builder),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="ctx-test",
    )

    ctx = captured["ctx"]
    assert ctx.target_run["run_id"] == "ctx-test__target"
    assert ctx.baseline_run is None
    assert ctx.comparison is None
    assert "target_run_id=ctx-test__target" in api.calls[0]["messages"][0]["content"]


async def test_run_eval_propagates_scenario_metadata(exporter):
    captured: dict[str, Any] = {}

    def builder(ctx: EvalContext) -> str:
        captured["ctx"] = ctx
        return "user prompt"

    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("response: pass")

    await run_eval(
        scenario=_make_single_run_scenario(prompt_builder=builder),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="meta",
        scenario_metadata={"intended_symptom": "X", "root_cause": "Y"},
    )
    assert captured["ctx"].scenario_metadata == {
        "intended_symptom": "X",
        "root_cause": "Y",
    }


# ---------- paired shape ----------

async def test_run_eval_paired_runs_baseline_target_compare(exporter):
    comparison = {
        "flow_count_delta": -5,
        "has_count_divergence": True,
        "fct_p50_delta_ns": 1000,
        "fct_p99_delta_ns": 50000,
        "fct_p999_delta_ns": 90000,
        "baseline_summary": {"total": 255, "completed": 255, "incomplete": 0},
        "injected_summary": {"total": 250, "completed": 248, "incomplete": 2},
        "findings": ["count divergence"],
    }
    session = _FakeSubstrateSession(comparison=comparison)
    substrate = DoppelgangerClient(session=session)
    model_client, api = _make_model_client("delta detected: pass")

    result = await run_eval(
        scenario=_make_paired_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="pair",
    )

    # Baseline + target + compare, in order.
    assert [c[0] for c in session.calls] == [
        "run_scenario",
        "run_scenario",
        "compare_runs",
    ]
    assert session.calls[0][1]["run_id"] == "pair__baseline"
    assert session.calls[1][1]["run_id"] == "pair__target"
    compare_args = session.calls[2][1]
    assert compare_args["baseline_trace_dir"] == "traces/pair__baseline"
    assert compare_args["injected_trace_dir"] == "traces/pair__target"

    assert result.baseline_run_id == "pair__baseline"
    assert result.target_run_id == "pair__target"
    assert result.comparison == comparison
    # The prompt builder pulled from the comparison
    assert "delta=-5" in api.calls[0]["messages"][0]["content"]


async def test_run_eval_paired_metadata_includes_comparison_signals(exporter):
    session = _FakeSubstrateSession(comparison={
        "flow_count_delta": -3,
        "has_count_divergence": True,
        "baseline_summary": {}, "injected_summary": {},
    })
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("delta=-3: pass")

    await run_eval(
        scenario=_make_paired_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="metadata",
    )

    from langfuse import get_client

    get_client().flush()
    eval_span = next(
        s for s in exporter.get_finished_spans() if s.name == EVAL_SPAN_NAME
    )
    attrs = eval_span.attributes or {}
    assert attrs["langfuse.observation.metadata.flow_count_delta"] == -3
    assert attrs["langfuse.observation.metadata.has_count_divergence"] is True
    assert attrs["langfuse.observation.metadata.baseline_run_id"] == "metadata__baseline"


# ---------- shared behavior ----------

async def test_run_eval_emits_eval_and_generation_spans(exporter):
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("response: pass")

    await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="span-check",
    )

    from langfuse import get_client

    get_client().flush()
    span_names = [s.name for s in exporter.get_finished_spans()]
    assert EVAL_SPAN_NAME in span_names
    assert GENERATION_SPAN_NAME in span_names


async def test_run_eval_visible_failure(exporter):
    """Score returns FAIL when the model output doesn't contain 'pass'."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("vague unhelpful answer")

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
    )
    assert result.score.overall_pass is False


async def test_run_eval_default_run_id_prefix_uses_scenario_name(exporter):
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("response: pass")

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
    )
    assert result.target_run_id.startswith("test-single-run-")
    assert result.target_run_id.endswith("__target")


# ---------- format_eval_summary ----------

def test_format_eval_summary_single_run_omits_baseline_and_comparison():
    from harnessit.eval.types import EvalResult

    result = EvalResult(
        scenario_name="microburst-symptom-only",
        target_run_id="abc__target",
        target_trace_dir="traces/abc__target",
        completion=Completion(
            text="triage response",
            model="claude-opus-4-7",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        ),
        score=Score(
            overall_pass=True,
            criteria={"considers_multiple_hypotheses": True},
            rationale="x",
        ),
        user_prompt="prompt",
        langfuse_trace_id="trace-xyz",
    )
    text = format_eval_summary(result)
    assert "microburst-symptom-only" in text
    assert "abc__target" in text
    assert "baseline" not in text  # single-run mode
    assert "flow_count_delta" not in text
    assert "trace-xyz" in text
    assert "PASS" in text


def test_format_eval_summary_paired_includes_comparison():
    from harnessit.eval.types import EvalResult

    result = EvalResult(
        scenario_name="paired-test",
        target_run_id="xyz__target",
        target_trace_dir="traces/xyz__target",
        baseline_run_id="xyz__baseline",
        baseline_trace_dir="traces/xyz__baseline",
        comparison={
            "flow_count_delta": -5,
            "has_count_divergence": True,
            "fct_p50_delta_ns": 1000,
            "fct_p99_delta_ns": 50000,
            "fct_p999_delta_ns": 90000,
        },
        completion=Completion(
            text="x", model="m", input_tokens=1, output_tokens=1, stop_reason=None,
        ),
        score=Score(overall_pass=False, criteria={"x": False}, rationale=""),
        user_prompt="p",
    )
    text = format_eval_summary(result)
    assert "flow_count_delta: -5" in text
    assert "xyz__baseline" in text
    assert "FAIL" in text
