# pathf1ndar

A terminal-native AI agent that helps developers
navigate hackathons and fragmented technical documentation.

## Core capabilities
- Research hackathon requirements and documentation
- Inspect local development prerequisites safely
- Generate dependency-aware implementation plans
- Recommend the next actionable step
- Track progress across sessions

## Hackathon
Celo Agents on Open Rails — Build with buy

## Stack
Python, Typer, Rich, HTTPX, pytest

## Offline MVP

Requires Python 3.11+. Install explicitly in a local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pathf1ndar --help
.venv/bin/pathf1ndar explore --demo
.venv/bin/pathf1ndar check
.venv/bin/pathf1ndar next
.venv/bin/pathf1ndar done scope
.venv/bin/pathf1ndar next
.venv/bin/pathf1ndar status
.venv/bin/python -m pytest -q
```

`check` reports the current Python interpreter and runs only `git --version`,
`node --version`, and `npm --version` through resolved PATH executables, with
five-second timeouts and no shell. It installs nothing. Missing or failing tools
produce exit code 1 and remain blockers. Only run against a trusted local PATH.
No network requests, wallet access, or transactions occur.

`next` selects the first unfinished task with completed prerequisites and passing
required tool checks. `done TASK_ID` records self-reported completion and refuses
blocked or unknown tasks. Complete tasks in this order:
`scope`, `workspace`, `prototype`, `validate`, `submission`.
The workspace task requires successful checks for all four tools. Completion is
manual; pathf1ndar does not create the prototype or verify its implementation.

Progress is stored in `.pathf1ndar/state.json` relative to the current directory.
Use the global option before the command to select another file:

```bash
.venv/bin/pathf1ndar --state-file /tmp/pathf1ndar-demo.json explore --demo
.venv/bin/pathf1ndar --state-file /tmp/pathf1ndar-demo.json status
```

Repeated exploration preserves progress. Checks are saved snapshots; rerun
`check` after environment changes. State writes use atomic replacement; malformed
or unsupported state fails with a readable error and is not overwritten.
Concurrent writers to the same state file are not supported.
To start again, choose a new state file.

## Architecture and scope

`src/pathf1ndar/cli.py` handles Typer commands and Rich output. `model.py` holds
tasks and prerequisite selection, `demo.py` defines the deterministic Celo
practice fixture, `checks.py` inspects local tools, and `state.py` validates and
persists versioned JSON. Tests mock tool execution and need no network or Node
installation. HTTPX and BeautifulSoup are declared for future documentation
retrieval; the offline MVP does not use them.

The demo is an authored practice scenario inspired by the hackathon context,
not an authoritative event checklist. Its documentation references are
[Celo documentation](https://docs.celo.org/) and
[Build on Celo](https://docs.celo.org/build-on-celo); they are not fetched or
verified by this program. Eligibility, deadlines, SDK details and actual
submission rules must be checked against current official event materials.
Live exploration, documentation retrieval, AI planning, automatic implementation,
and on-chain operations remain outside this MVP.
