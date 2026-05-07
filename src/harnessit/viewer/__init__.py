"""Trajectory viewer v0.1 — sequence-diagram view of a single eval trace.

Per Build Plan v0.3 §2.1 stage 4a: queries Langfuse for a trace,
transforms the OTel observation tree into a services-as-columns
sequence diagram, renders to a static HTML file. v0.1 deliberately
ships as static HTML + Mermaid.js — no server, no JS framework, no
build step. One trace per file.

Use::

    python -m harnessit.viewer <trace_id> [--output FILE]

The viewer is read-only against Langfuse; it doesn't emit spans of
its own. It uses the existing ``harnessit.config.load_settings()``
to authenticate, so it works against whichever Langfuse backend the
``.langfuse-credentials`` file points at (managed Cloud at v0.1;
self-hosted from Stage 4b onward).

Module layout:

* ``transform`` — pure data-model code: Span, Lane, Message,
  TraceView. Span name → lane mapping. Span tree → message list.
* ``render`` — TraceView → HTML+Mermaid string. No I/O.
* ``client`` — Langfuse fetch wrapper. Mockable for hermetic tests.
* ``__main__`` — CLI entry point.
"""

from harnessit.viewer.transform import (
    Lane,
    Message,
    Span,
    TraceView,
    build_trace_view,
    span_name_to_lane,
)
from harnessit.viewer.render import render_trace_html

__all__ = [
    "Lane",
    "Message",
    "Span",
    "TraceView",
    "build_trace_view",
    "render_trace_html",
    "span_name_to_lane",
]
