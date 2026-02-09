from __future__ import annotations

import argparse
from pathlib import Path

from swarmflight import __version__
from swarmflight.benchmarks import (
    format_mode_resume_report,
    format_report,
    format_tuning_report,
    resume_synthetic_mode,
    run_synthetic_benchmark,
    tune_parallelism,
)
from swarmflight.runtime import load_trace, summarize_trace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarmflight",
        description="SwarmFlight CLI",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")
    bench = subparsers.add_parser("bench", help="Run synthetic single vs swarm benchmark.")
    bench.add_argument(
        "--scenario",
        choices=("wide", "deep", "mixed"),
        default="wide",
        help="Synthetic benchmark scenario type.",
    )
    bench.add_argument(
        "--width",
        type=int,
        default=8,
        help="Number of parallel branch tasks in the benchmark graph.",
    )
    bench.add_argument(
        "--swarm-workers",
        type=int,
        default=4,
        help="Worker count for swarm mode.",
    )
    bench.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Retry budget per task.",
    )
    bench.add_argument(
        "--trace-dir",
        default=None,
        help="Optional output directory for benchmark trace JSONL files.",
    )
    bench.add_argument(
        "--checkpoint-file",
        default=None,
        help="Optional checkpoint output path for swarm mode runtime state.",
    )
    bench.add_argument(
        "--stop-after-ticks",
        type=int,
        default=None,
        help="Optional early stop tick budget for swarm mode (use with --checkpoint-file).",
    )

    replay = subparsers.add_parser("replay", help="Replay and summarize a JSONL trace.")
    replay.add_argument("trace_file", help="Path to trace JSONL file.")

    resume = subparsers.add_parser("resume", help="Resume a run from checkpoint JSON.")
    resume.add_argument("checkpoint_file", help="Path to checkpoint JSON file.")
    resume.add_argument(
        "--trace-file",
        default=None,
        help="Optional output trace file for resumed run events.",
    )

    tune = subparsers.add_parser("tune", help="Tune swarm worker parallelism with a bandit policy.")
    tune.add_argument(
        "--scenario",
        choices=("wide", "deep", "mixed"),
        default="wide",
        help="Synthetic benchmark scenario type.",
    )
    tune.add_argument(
        "--widths",
        default="4,8,12",
        help="Comma-separated width values for contextual tuning.",
    )
    tune.add_argument(
        "--episodes",
        type=int,
        default=12,
        help="Number of training episodes.",
    )
    tune.add_argument(
        "--worker-arms",
        default="1,2,4,6",
        help="Comma-separated worker choices for bandit exploration.",
    )
    tune.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Retry budget per task during tuning runs.",
    )
    tune.add_argument(
        "--epsilon",
        type=float,
        default=0.2,
        help="Exploration rate for epsilon-greedy policy.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"swarmflight {__version__}")
        return 0

    if args.command == "bench":
        if args.stop_after_ticks is not None and args.checkpoint_file is None:
            raise ValueError("--stop-after-ticks requires --checkpoint-file")
        report = run_synthetic_benchmark(
            scenario=args.scenario,
            width=args.width,
            swarm_workers=args.swarm_workers,
            max_retries=args.max_retries,
            trace_dir=args.trace_dir,
            checkpoint_file=args.checkpoint_file,
            stop_after_ticks=args.stop_after_ticks,
        )
        print(format_report(report))
        return 0

    if args.command == "replay":
        trace_path = Path(args.trace_file)
        events = load_trace(trace_path)
        summary = summarize_trace(events)
        print(f"trace={trace_path}")
        print(f"total={summary.pop('total', 0)}")
        for key in sorted(summary):
            print(f"{key}={summary[key]}")
        return 0

    if args.command == "resume":
        metrics = resume_synthetic_mode(
            checkpoint_file=args.checkpoint_file,
            trace_file=args.trace_file,
        )
        print(format_mode_resume_report(metrics, checkpoint_file=args.checkpoint_file))
        return 0

    if args.command == "tune":
        widths = _parse_int_list(args.widths)
        worker_arms = _parse_int_list(args.worker_arms)
        result = tune_parallelism(
            scenario=args.scenario,
            widths=widths,
            episodes=args.episodes,
            worker_arms=worker_arms,
            max_retries=args.max_retries,
            epsilon=args.epsilon,
        )
        print(format_tuning_report(result))
        return 0

    parser.print_help()
    return 0


def _parse_int_list(raw: str) -> list[int]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("expected at least one integer")
    return [int(value) for value in values]


if __name__ == "__main__":
    raise SystemExit(main())
