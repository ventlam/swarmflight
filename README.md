# SwarmFlight

SwarmFlight is an open-source parallel agent swarm runtime for coding and research workflows.

It is inspired by recent Agent Swarm ideas and focuses on practical engineering:

- dynamic task decomposition
- parallel subagent execution
- strong observability and replayability
- measurable quality, latency, and cost trade-offs

## Project status

Early but usable.

Current baseline includes runtime v0.6 primitives:

- dependency-aware task graph execution
- concurrent tick scheduling with profile-based concurrency limits
- retry policy per task
- hook system (retry backoff, output truncation, stability guard)
- mailbox and worker abstraction
- run checkpoint persistence and resume flow
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
swarmflight bench --width 8 --swarm-workers 4 --max-retries 1 --trace-dir ./.artifacts/traces
swarmflight bench --scenario mixed --width 8 --swarm-workers 4 --max-retries 1
swarmflight bench --scenario mixed --width 8 --swarm-workers 4 --max-retries 1 --checkpoint-file ./.artifacts/checkpoints/swarm.json --stop-after-ticks 2
swarmflight resume ./.artifacts/checkpoints/swarm.json
swarmflight replay ./.artifacts/traces/swarm.jsonl
swarmflight tune --scenario mixed --widths 4,8,12 --episodes 12 --worker-arms 1,2,4,6
ruff check .
pytest
```

## Runtime core snapshot

Current runtime package (`src/swarmflight/runtime/`) includes:

- `orchestrator.py`: dependency-aware orchestrator, concurrent ticks, retries, and checkpoint resume
- `events.py`: runtime event bus and structured runtime events
- `hooks.py`: hook manager and built-in hooks for backoff/truncation/stability suggestions
- `worker.py`: worker protocol and function-based worker implementation
- `mailbox.py`: in-memory mailbox for inter-agent messages
- `models.py`: shared task/message/result data models

Benchmark package (`src/swarmflight/benchmarks/`) includes:

- synthetic wide-search scenario generator
- synthetic deep-search and mixed-search scenarios
- mode comparison for single-agent vs swarm
- metrics: pass rate, retries, stale count, avg parallelism, token cost, critical steps, wall time
- contextual epsilon-greedy tuning for swarm parallelism

Design and metrics docs:

- `docs/k2_5_swarm_reproduction_design.md`
- `docs/metrics.md`

This is a minimal baseline for iterative scheduler and benchmark work.

## Contributing

See `CONTRIBUTING.md` for development workflow, coding standards, and PR process.

## License

MIT
