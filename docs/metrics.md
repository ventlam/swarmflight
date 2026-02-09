# SwarmFlight Metrics Specification

This document defines core metrics for comparing single-agent and swarm runs.

## Quality

- `pass_rate`: completed tasks divided by total tasks.
- `failed`: tasks with terminal `failed` status.
- `skipped`: tasks skipped due to failed dependencies.

## Latency

- `critical_steps`: estimated critical-path duration under worker constraints.
- `wall_time_ms`: measured wall-clock runtime for the whole benchmark mode.
- `avg_parallelism`: average scheduled attempts per active scheduler tick.

## Cost

- `token_cost`: sum of task token cost multiplied by number of attempts.
- `retry_count`: total attempts minus number of terminal tasks.

## Stability

- `total_attempts`: total execution attempts across tasks.
- `failure_rate`: `failed / total_tasks`.
- `skip_rate`: `skipped / total_tasks`.

## Trace Metrics

JSONL trace files are event streams used for replay and debugging. Typical event kinds:

- `worker_registered`
- `task_submitted`
- `policy_action`
- `task_attempt`
- `task_retrying`
- `task_skipped`

Use `swarmflight replay <trace_file>` to summarize event counts.
