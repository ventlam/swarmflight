# SwarmFlight

SwarmFlight is an open-source parallel agent swarm runtime for coding and research workflows.

It is inspired by recent Agent Swarm ideas and focuses on practical engineering:

- dynamic task decomposition
- parallel subagent execution
- strong observability and replayability
- measurable quality, latency, and cost trade-offs

## Project status

Early but usable.

Current baseline includes runtime v0.2 primitives:

- dependency-aware task graph execution
- retry policy per task
- mailbox and worker abstraction
- synthetic single-agent vs swarm benchmark harness

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
swarmflight bench --width 8 --swarm-workers 4 --max-retries 1
ruff check .
pytest
```

## Runtime core snapshot

Current runtime package (`src/swarmflight/runtime/`) includes:

- `orchestrator.py`: dependency-aware orchestrator, retries, and round-robin scheduling
- `worker.py`: worker protocol and function-based worker implementation
- `mailbox.py`: in-memory mailbox for inter-agent messages
- `models.py`: shared task/message/result data models

Benchmark package (`src/swarmflight/benchmarks/`) includes:

- synthetic wide-search scenario generator
- mode comparison for single-agent vs swarm
- metrics: pass rate, retries, token cost, critical steps, wall time

This is a minimal baseline for iterative scheduler and benchmark work.

## Contributing

See `CONTRIBUTING.md` for development workflow, coding standards, and PR process.

## License

MIT
