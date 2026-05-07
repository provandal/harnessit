"""Trajectory viewer CLI.

Use::

    python -m harnessit.viewer <trace_id> [--output FILE]

By default writes the rendered HTML to stdout; pass ``--output FILE``
to write to a file (creating parent directories if needed). Reads
Langfuse credentials via the existing ``harnessit.config.load_settings()``
mechanism — same workspace credential file as the eval runner.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harnessit.config import load_settings
from harnessit.tracing import init_langfuse
from harnessit.viewer.client import fetch_trace_view
from harnessit.viewer.render import render_trace_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harnessit.viewer",
        description=(
            "Render a HarnessIT eval trace as a static HTML sequence "
            "diagram. Reads from Langfuse using the workspace credentials."
        ),
    )
    parser.add_argument(
        "trace_id",
        help=(
            "The Langfuse trace id to render — the 32-character hex string "
            "logged at the end of an eval run (e.g. 8c4399b12477966d8ca0ad3fb1a1323d)."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help=(
            "Write HTML to this path instead of stdout. Parent directories "
            "are created if needed."
        ),
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    langfuse_client = init_langfuse(settings, tracing_enabled=False)

    view = fetch_trace_view(args.trace_id, langfuse_client=langfuse_client)
    html = render_trace_html(view)

    if args.output is None:
        sys.stdout.write(html)
        return 0

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    sys.stderr.write(f"wrote {out_path} ({len(html):,} bytes)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
