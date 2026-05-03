# HarnessIT

An agentic harness reference architecture and reference implementation, built in public.

HarnessIT is a learning-and-teaching project that explores how an LLM-driven agent can investigate AI fabric operations through running code. It consumes one or more **Substrate Adapters** (each exposing a different underlying fabric or simulator through a common MCP interface) plus packaged skills and persistent memory.

## Status

Design phase as of 2026-05.

See [`docs/HarnessIT_Architecture_v0.4.docx`](docs/HarnessIT_Architecture_v0.4.docx) (architecture) and [`docs/HarnessIT_BuildPlan_v0.2.docx`](docs/HarnessIT_BuildPlan_v0.2.docx) (build plan). Plain-text extractions are in `docs/arch.txt` and `docs/build.txt`.

## Sister projects

- [`provandal/doppelganger`](https://github.com/provandal/doppelganger) — NS-3-based Substrate Adapter (the initial substrate)
- [`provandal/theconstruct`](https://github.com/provandal/theconstruct) — packaged skills (procedural knowledge) consumed by HarnessIT

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
