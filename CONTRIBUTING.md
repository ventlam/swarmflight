# Contributing to SwarmFlight

Thanks for helping build SwarmFlight.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Local quality checks

Before opening a pull request, run:

```bash
ruff check .
pytest -q
```

## Coding guidelines

- Keep runtime behavior deterministic where practical.
- Add tests for bug fixes and new core behavior.
- Prefer small, focused pull requests.
- Keep public APIs in `src/swarmflight/runtime/` stable and well typed.

## Pull request process

1. Create a branch from `main`.
2. Implement and test your change locally.
3. Fill out the PR template with motivation, behavior changes, and validation.
4. Wait for CI and review feedback.

## Issue reporting

- Use bug reports for incorrect behavior or regressions.
- Use feature requests for scheduler/runtime capability proposals.
- Include reproduction steps and environment details when possible.
