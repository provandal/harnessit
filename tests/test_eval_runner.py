"""Tests for the eval runner — single-run + paired shapes via fakes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from harnessit.eval import EvalContext, EvalScenario, run_eval
from harnessit.eval.judge import (
    DEFAULT_JUDGE_MODEL,
    RUBRIC_CRITERIA,
    CriterionJudgment,
    Judge,
    JudgeError,
    Judgment,
)
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
        elif name == "get_topology":
            # Note: scenario name is NOT in the data payload — that was
            # the Stage 3 first-pass leak (model read "scenario:
            # microburst" as the answer key). It belongs in `source`
            # only, as operator-side trace metadata.
            envelope = {
                "data": {
                    "shape": "leaf-spine",
                    "leaves": 2,
                    "spines": 4,
                    "hosts_per_leaf": 8,
                    "total_hosts": 16,
                },
                "source": f"adapter.scenario_topology({arguments['name']!r})",
                "observed_at_ns": None,
                "confidence": "high",
                "staleness_class": "fresh",
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


def _make_tool_using_scenario(prompt_builder=None) -> EvalScenario:
    """Single-run scenario with uses_tools=True for the Stage 3 path."""
    return EvalScenario(
        name="test-tool-using",
        description="single-run + tool-use test scenario",
        system_prompt="You are a test assistant.",
        target_scenario="microburst",
        baseline_scenario=None,
        build_user_prompt=prompt_builder or (lambda ctx: "ticket"),
        score=_stub_score,
        expected_to_pass=True,
        uses_tools=True,
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


# ---------- tool-use shape ----------


@dataclass
class _FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


class _ScriptedToolUseAPI:
    """Fake messages.create that returns a scripted tool-use sequence.

    Iteration 1: response with stop_reason=tool_use containing a
    get_topology tool_use block.
    Iteration 2: response with stop_reason=end_turn and the final text.
    """

    def __init__(self, final_text: str) -> None:
        self.final_text = final_text
        self.calls: list[dict[str, Any]] = []
        self._iteration = 0

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        self._iteration += 1
        if self._iteration == 1:
            return _FakeMessage(
                content=[
                    _FakeTextBlock(text="let me check the fabric"),
                    _FakeToolUseBlock(id="tu_1", name="get_topology", input={}),
                ],
                model=kwargs["model"],
                usage=_FakeUsage(input_tokens=20, output_tokens=10),
                stop_reason="tool_use",
            )
        return _FakeMessage(
            content=[_FakeTextBlock(text=self.final_text)],
            model=kwargs["model"],
            usage=_FakeUsage(input_tokens=60, output_tokens=25),
            stop_reason="end_turn",
        )


async def test_run_eval_tool_use_invokes_get_topology_through_substrate(exporter):
    """Stage 3 closing-test path: uses_tools=True scenario triggers the
    tool-use branch; agent's get_topology() call forwards through the
    substrate Adapter with the bound scenario name."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    api = _ScriptedToolUseAPI(final_text="2 leaves x 4 spines, host 11.0.0.1 on leaf 0: pass")
    model_client = ModelClient(client=_FakeAnthropic(messages=api), model="claude-opus-4-7")

    result = await run_eval(
        scenario=_make_tool_using_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="tool-use",
    )

    # Substrate sees: target run_scenario, then get_topology with the bound name
    tool_names = [c[0] for c in session.calls]
    assert tool_names == ["run_scenario", "get_topology"]
    get_topology_args = session.calls[1][1]
    assert get_topology_args == {"name": "microburst"}, (
        "harness must bind the scenario.target_scenario when forwarding "
        "the agent's no-arg get_topology() call"
    )

    # Two model iterations: tool_use, then end_turn
    assert len(api.calls) == 2
    assert api.calls[0]["tools"][0]["name"] == "get_topology"

    # Result preserves the tool-call trail and iteration count
    assert result.iterations == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_topology"
    assert result.tool_calls[0].input == {}
    # Output should be the topology data, not the envelope
    assert result.tool_calls[0].output["shape"] == "leaf-spine"
    assert result.score.overall_pass is True
    # Token counts summed across iterations
    assert result.completion.input_tokens == 80  # 20 + 60
    assert result.completion.output_tokens == 35  # 10 + 25


async def test_run_eval_naked_path_unchanged_when_uses_tools_false(exporter):
    """Regression guard: scenarios without uses_tools must still take
    the Stage 2 naked path (no tools= param to the model)."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, api = _make_model_client("response: pass")

    await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="naked",
    )
    assert len(api.calls) == 1
    assert "tools" not in api.calls[0], (
        "naked path must not pass tools= to messages.create"
    )


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


# ---------- LLM judge integration ----------


class _StubJudge:
    """Stand-in for harnessit.eval.judge.Judge that returns a staged
    Judgment or raises a staged JudgeError. Lets us exercise the
    runner's judge branch without a real client."""

    def __init__(
        self,
        *,
        judgment: Judgment | None = None,
        raise_exc: Exception | None = None,
        model: str = DEFAULT_JUDGE_MODEL,
    ) -> None:
        self.judgment = judgment
        self.raise_exc = raise_exc
        self.model = model
        self.calls: list[dict[str, Any]] = []

    async def score(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        agent_response: str,
        tool_calls: tuple = (),
    ) -> Judgment:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "agent_response": agent_response,
            "tool_calls": tool_calls,
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        assert self.judgment is not None, "test forgot to stage a judgment"
        return self.judgment


def _make_judgment(*, overall_pass: bool, criteria_overrides: dict[str, bool] | None = None) -> Judgment:
    """Build a Judgment with all RUBRIC_CRITERIA populated.

    Each criterion's pass defaults to ``overall_pass`` unless overridden.
    """
    overrides = criteria_overrides or {}
    return Judgment(
        overall_pass=overall_pass,
        overall_rationale=(
            "stub overall rationale (overall_pass=" + str(overall_pass) + ")"
        ),
        criteria=tuple(
            CriterionJudgment(
                name=name,
                passed=overrides.get(name, overall_pass),
                rationale=f"stub rationale for {name}",
            )
            for name, _description in RUBRIC_CRITERIA
        ),
        judge_model=DEFAULT_JUDGE_MODEL,
    )


async def test_run_eval_no_judge_keeps_keyword_path_unchanged(exporter):
    """Regression guard: when no judge is passed, behavior matches the
    pre-judge runner shape exactly. score == keyword_score, llm_judgment
    is None, judge_error is None."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("triage plan: pass")

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="no-judge",
    )

    assert result.llm_judgment is None
    assert result.judge_error is None
    assert result.keyword_score is not None
    # Primary score is the keyword score by reference (same object)
    assert result.score is result.keyword_score


async def test_run_eval_with_judge_uses_llm_score_as_primary(exporter):
    """When the judge succeeds, the primary score reflects the judge's
    verdict, not the keyword scorer's. Both scores are preserved on
    the EvalResult for the calibration table."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    # The agent response is a single weak word; keyword scorer will fail
    # all four criteria.
    model_client, _ = _make_model_client("ok")
    # The judge will be staged with overall_pass=True, demonstrating that
    # the judge can override the keyword scorer.
    stub_judge = _StubJudge(judgment=_make_judgment(overall_pass=True))

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="llm-primary",
        judge=stub_judge,  # type: ignore[arg-type]
    )

    # Primary score reflects the judge
    assert result.score.overall_pass is True
    # Both scores preserved
    assert result.llm_judgment is not None
    assert result.llm_judgment.overall_pass is True
    assert result.keyword_score is not None
    assert result.keyword_score.overall_pass is False, (
        "keyword should fail on this weak response — calibration only "
        "matters if the two scores can disagree"
    )
    assert result.judge_error is None
    # Judge was called with the agent's actual response and the system prompt
    assert len(stub_judge.calls) == 1
    assert stub_judge.calls[0]["agent_response"] == "ok"
    assert stub_judge.calls[0]["system_prompt"] == "You are a test assistant."


async def test_run_eval_falls_back_to_keyword_on_judge_error(exporter):
    """JudgeError → primary score is the keyword score, judge_error is
    populated, llm_judgment stays None. The eval still completes."""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    model_client, _ = _make_model_client("triage plan: pass")
    stub_judge = _StubJudge(raise_exc=JudgeError("simulated network down"))

    result = await run_eval(
        scenario=_make_single_run_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="judge-fail",
        judge=stub_judge,  # type: ignore[arg-type]
    )

    assert result.llm_judgment is None
    assert result.judge_error == "simulated network down"
    assert result.keyword_score is not None
    assert result.score is result.keyword_score
    # Eval still completed; primary score is whatever keyword produced
    assert result.score.overall_pass is True  # 'pass' literal in completion


async def test_run_eval_judge_receives_tool_calls_for_tool_using_scenarios(exporter):
    """When the agent uses tools, the judge should see the tool calls
    so it can evaluate 'did the agent retrieve the right data?'"""
    session = _FakeSubstrateSession(comparison=None)
    substrate = DoppelgangerClient(session=session)
    api = _ScriptedToolUseAPI(final_text="leaf 0 is the bottleneck: pass")
    model_client = ModelClient(client=_FakeAnthropic(messages=api), model="claude-opus-4-7")
    stub_judge = _StubJudge(judgment=_make_judgment(overall_pass=True))

    await run_eval(
        scenario=_make_tool_using_scenario(),
        substrate=substrate,
        model_client=model_client,
        run_id_prefix="judge-tool",
        judge=stub_judge,  # type: ignore[arg-type]
    )

    assert len(stub_judge.calls) == 1
    forwarded = stub_judge.calls[0]["tool_calls"]
    assert len(forwarded) == 1
    assert forwarded[0].name == "get_topology"


def test_format_eval_summary_renders_keyword_vs_llm_table():
    """When both scores are present, the summary renders a side-by-side
    table — the actual calibration view we want to read at trace-review
    time."""
    from harnessit.eval.types import EvalResult

    keyword = Score(
        overall_pass=False,
        criteria={
            "considers_multiple_hypotheses": True,
            "names_telemetry_to_query": False,
            "acknowledges_unknowns": False,
            "coherent_investigation_order": True,
        },
        rationale="keyword: 2/4",
    )
    llm = _make_judgment(
        overall_pass=True,
        criteria_overrides={
            "considers_multiple_hypotheses": True,
            "names_telemetry_to_query": True,
            "acknowledges_unknowns": True,
            "coherent_investigation_order": True,
        },
    )
    result = EvalResult(
        scenario_name="microburst-with-topology-tool",
        target_run_id="t",
        target_trace_dir="traces/t",
        completion=Completion(
            text="response", model="m", input_tokens=1, output_tokens=1, stop_reason="end_turn"
        ),
        score=llm.to_score(),
        user_prompt="u",
        keyword_score=keyword,
        llm_judgment=llm,
    )
    text = format_eval_summary(result)
    assert "keyword | LLM" in text
    # Disagreement is visible: keyword FAIL on one criterion, LLM PASS
    assert "names_telemetry_to_query: FAIL | PASS" in text
    # Overall row shows both verdicts
    assert "keyword=FAIL | LLM=PASS" in text
    # Per-criterion rationale section renders
    assert "LLM judge rationale" in text
    # Primary marker indicates LLM is in charge
    assert "LLM judge" in text


def test_format_eval_summary_falls_back_to_single_table_when_no_judge():
    """Backward compat: when llm_judgment is None and keyword_score is
    None (legacy EvalResult shape), the summary still renders."""
    from harnessit.eval.types import EvalResult

    result = EvalResult(
        scenario_name="legacy",
        target_run_id="t",
        target_trace_dir="traces/t",
        completion=Completion(
            text="response", model="m", input_tokens=1, output_tokens=1, stop_reason="end_turn"
        ),
        score=Score(overall_pass=True, criteria={"a": True}, rationale="ok"),
        user_prompt="u",
        # keyword_score and llm_judgment both None
    )
    text = format_eval_summary(result)
    assert "scoring" in text
    assert "a: PASS" in text
    assert "overall_pass: True" in text
