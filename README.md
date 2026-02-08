# SwarmFlight

SwarmFlight is an open-source parallel agent swarm runtime for coding and research workflows.

It is inspired by recent Agent Swarm ideas and focuses on practical engineering:

- dynamic task decomposition
- parallel subagent execution
- strong observability and replayability
- measurable quality, latency, and cost trade-offs

## Project status

Bootstrap stage. Core runtime and benchmarks are under active development.

## Roadmap

1. Runtime core: orchestrator, worker pool, mailbox, task graph.
2. Scheduler policies: baseline heuristic, then PARL-inspired adaptive policy.
3. Evaluation suite: single-agent vs swarm on quality, latency, and cost.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
swarmflight --help
pytest
```

## License

MIT
