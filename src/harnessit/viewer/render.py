"""TraceView → static HTML+Mermaid string.

v0.1 produces a single self-contained HTML document: header (trace
metadata + scores), Mermaid sequence diagram, then per-message
collapsible detail blocks. Mermaid.js loads from CDN; no build step
or local assets.

Pure data-in / string-out. No I/O. Tests stay hermetic.
"""

from __future__ import annotations

import html
import json
from typing import Any

from harnessit.viewer.transform import Lane, Message, TraceView


_MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"


def _esc(text: str) -> str:
    """HTML-escape, preserving line breaks for <pre> blocks."""
    return html.escape(text or "", quote=True)


def _esc_mermaid_label(text: str) -> str:
    """Escape a Mermaid sequence-diagram message label.

    Mermaid is sensitive to ``;``, ``:``, and unbalanced parens in
    inline labels. Strip newlines (one-line labels), trim, and replace
    the few characters that break the parser.
    """
    if not text:
        return ""
    cleaned = text.replace("\n", " ").strip()
    cleaned = cleaned.replace(";", ",")
    cleaned = cleaned.replace(":", " -")
    return cleaned[:120]


def _lane_id(lane: Lane) -> str:
    """Mermaid participant id (alphanumeric, no spaces)."""
    return lane.name  # USER, AGENT, TOOL, etc.


def _format_payload_block(payload: dict[str, Any]) -> str:
    """Render a payload dict as a pre-formatted JSON block."""
    if not payload:
        return ""
    try:
        text = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    except Exception:  # never let serialization crash the renderer
        text = repr(payload)
    return f"<pre class='payload'>{_esc(text)}</pre>"


def _render_mermaid_diagram(view: TraceView) -> str:
    """Build the Mermaid ``sequenceDiagram`` source for the trace."""
    if not view.active_lanes:
        return "sequenceDiagram\n  participant USER as User\n  USER->>USER: (no spans)"
    lines = ["sequenceDiagram"]
    for lane in view.active_lanes:
        lines.append(f"  participant {_lane_id(lane)} as {lane.value}")
    for msg in view.messages:
        arrow = "-->>" if msg.is_response else "->>"
        from_id = _lane_id(msg.from_lane)
        to_id = _lane_id(msg.to_lane)
        label = _esc_mermaid_label(msg.label)
        lines.append(f"  {from_id}{arrow}{to_id}: {label}")
    return "\n".join(lines)


def _render_message_detail(idx: int, msg: Message) -> str:
    """Collapsible detail block for one message."""
    arrow_glyph = "←" if msg.is_response else "→"
    title = (
        f"<strong>{idx}.</strong> "
        f"{_esc(msg.from_lane.value)} {arrow_glyph} {_esc(msg.to_lane.value)} "
        f"<span class='label'>{_esc(msg.label)}</span>"
    )
    payload_html = _format_payload_block(msg.payload)
    span_link = ""
    if msg.span_id:
        span_link = (
            f"<div class='span-id'>span: <code>{_esc(msg.span_id)}</code></div>"
        )
    return (
        "<details class='message'>\n"
        f"  <summary>{title}</summary>\n"
        f"  {span_link}\n"
        f"  {payload_html}\n"
        "</details>"
    )


def _render_judge_panel(view: TraceView) -> str:
    """Per-criterion rationale rendered inline.

    The 2026-05-07 finding: rationale is the load-bearing addition
    that makes the eval self-explaining. The viewer's job is to put
    it next to the agent's response so the SRE doesn't have to
    cross-reference two views.
    """
    if not view.judge_criteria:
        return ""
    rows = []
    for entry in view.judge_criteria:
        passed = entry.get("passed", False)
        marker = "PASS" if passed else "FAIL"
        marker_cls = "pass" if passed else "fail"
        name = _esc(str(entry.get("name", "")))
        rationale = _esc(str(entry.get("rationale", "")))
        rows.append(
            f"<tr><td class='{marker_cls}'>{marker}</td>"
            f"<td class='criterion-name'>{name}</td>"
            f"<td class='rationale'>{rationale}</td></tr>"
        )
    overall_block = ""
    if view.judge_rationale:
        overall_block = (
            "<div class='judge-overall'>"
            f"<strong>Overall ({_esc(view.judge_model or 'judge')}):</strong> "
            f"{_esc(view.judge_rationale)}"
            "</div>"
        )
    return (
        "<section class='judge-panel'>\n"
        "  <h2>LLM judge — per-criterion rationale</h2>\n"
        "  <table class='judge-table'>\n"
        "    <thead><tr><th>Verdict</th><th>Criterion</th><th>Rationale</th></tr></thead>\n"
        f"    <tbody>{''.join(rows)}</tbody>\n"
        "  </table>\n"
        f"  {overall_block}\n"
        "</section>"
    )


def _render_scores_block(view: TraceView) -> str:
    if not view.scores:
        return ""
    rows = []
    for s in view.scores:
        marker_cls = "pass" if (s.value or 0) >= 1.0 else "fail"
        rows.append(
            f"<tr><td class='criterion-name'>{_esc(s.name)}</td>"
            f"<td class='{marker_cls}'>{_esc(str(s.value))}</td>"
            f"<td>{_esc(s.comment or '')}</td></tr>"
        )
    return (
        "<section class='scores-panel'>\n"
        "  <h2>Trace-level scores</h2>\n"
        "  <table class='scores-table'>\n"
        "    <thead><tr><th>Name</th><th>Value</th><th>Comment</th></tr></thead>\n"
        f"    <tbody>{''.join(rows)}</tbody>\n"
        "  </table>\n"
        "</section>"
    )


def _render_header(view: TraceView) -> str:
    eval_metadata_rows = []
    for key in ("scenario_name", "scoring_mode", "expected_to_pass", "target_run_id"):
        if key in view.eval_metadata:
            eval_metadata_rows.append(
                f"<dt>{_esc(key)}</dt><dd>{_esc(str(view.eval_metadata[key]))}</dd>"
            )
    metadata_dl = (
        f"<dl class='eval-meta'>{''.join(eval_metadata_rows)}</dl>"
        if eval_metadata_rows
        else ""
    )
    return (
        "<header class='trace-header'>\n"
        f"  <h1>HarnessIT trajectory: {_esc(view.scenario_name or view.trace_name or view.trace_id)}</h1>\n"
        f"  <div class='trace-id'>trace: <code>{_esc(view.trace_id)}</code></div>\n"
        f"  <div class='timestamp'>{_esc(view.timestamp.isoformat())}</div>\n"
        f"  {metadata_dl}\n"
        "</header>"
    )


_CSS = """
:root {
  --bg: #fafafa; --fg: #1a1a1a; --accent: #2563eb;
  --muted: #6b7280; --pass: #15803d; --fail: #b91c1c;
  --panel-bg: #ffffff; --border: #e5e7eb;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0; padding: 2rem; max-width: 1100px;
  margin-left: auto; margin-right: auto;
  background: var(--bg); color: var(--fg); line-height: 1.5;
}
h1 { margin: 0 0 0.5rem 0; font-size: 1.5rem; }
h2 { margin: 1.5rem 0 0.75rem; font-size: 1.15rem; }
.trace-header { padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.trace-id, .timestamp { color: var(--muted); font-size: 0.875rem; margin: 0.25rem 0; }
.eval-meta { display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 0.75rem; margin-top: 0.5rem; font-size: 0.875rem; }
.eval-meta dt { color: var(--muted); }
.eval-meta dd { margin: 0; }
.diagram { background: var(--panel-bg); padding: 1rem; border-radius: 6px; border: 1px solid var(--border); margin: 1rem 0; overflow-x: auto; }
section { background: var(--panel-bg); padding: 1rem 1.5rem; margin: 1rem 0; border-radius: 6px; border: 1px solid var(--border); }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { padding: 0.5rem; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
th { font-weight: 600; color: var(--muted); }
.criterion-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; }
td.pass { color: var(--pass); font-weight: 600; }
td.fail { color: var(--fail); font-weight: 600; }
.rationale { color: var(--fg); }
.judge-overall { margin-top: 0.75rem; padding: 0.75rem; background: #f3f4f6; border-radius: 4px; font-size: 0.95rem; }
details.message { background: var(--panel-bg); margin: 0.5rem 0; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 4px; }
details.message summary { cursor: pointer; }
details.message summary .label { color: var(--accent); }
.span-id { font-size: 0.75rem; color: var(--muted); margin: 0.25rem 0; }
.payload { background: #f9fafb; padding: 0.5rem; border-radius: 4px; font-size: 0.825rem; overflow-x: auto; max-height: 24rem; overflow-y: auto; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.875rem; }
.section-heading { color: var(--muted); font-size: 0.875rem; margin: 1.5rem 0 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
"""


def render_trace_html(view: TraceView) -> str:
    """Render a TraceView to a self-contained HTML string."""
    diagram_source = _render_mermaid_diagram(view)
    detail_blocks = "\n".join(
        _render_message_detail(i, m)
        for i, m in enumerate(view.messages, start=1)
    )
    title = view.scenario_name or view.trace_name or view.trace_id
    judge_panel = _render_judge_panel(view)
    scores_panel = _render_scores_block(view)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>HarnessIT trajectory — {_esc(title)}</title>
  <style>{_CSS}</style>
</head>
<body>
  {_render_header(view)}

  <section class="diagram-section">
    <h2>Sequence diagram</h2>
    <div class="diagram">
      <pre class="mermaid">{_esc(diagram_source)}</pre>
    </div>
  </section>

  {scores_panel}
  {judge_panel}

  <section class="messages-section">
    <h2>Messages ({len(view.messages)})</h2>
    {detail_blocks}
  </section>

  <script src="{_MERMAID_CDN}"></script>
  <script>
    mermaid.initialize({{ startOnLoad: true, theme: 'default', sequence: {{ showSequenceNumbers: true }} }});
  </script>
</body>
</html>"""


__all__ = ["render_trace_html"]
