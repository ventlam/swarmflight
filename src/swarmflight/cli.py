from __future__ import annotations

import argparse

from swarmflight import __version__
from swarmflight.benchmarks import format_report, run_synthetic_benchmark


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"swarmflight {__version__}")
        return 0

    if args.command == "bench":
        report = run_synthetic_benchmark(
            width=args.width,
            swarm_workers=args.swarm_workers,
            max_retries=args.max_retries,
        )
        print(format_report(report))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
