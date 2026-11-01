# Honeyguider CLI

Honeyguider requires Python 3.11 or newer. Its `honeyguider` console script
points to the Typer application; `python -m honeyguider` uses the same CLI.
The CLI uses Typer, Rich, HTTPX and BeautifulSoup, with local JSON progress.
Streamlit is not required for the CLI.

## Isolated installation

From your checkout, choose one of these installation methods. Each creates an
isolated tool environment rather than installing into system Python:

```sh
pipx install --python python3.11 .
honeyguider --help
```

Or, with uv:

```sh
uv tool install --python 3.11 .
honeyguider --help
```

If your tool installer reports that its executable directory is missing from
PATH, follow its PATH setup instructions and open a new terminal. Use the local
checkout path (`.` above); this does not assume a published package exists.
Installation downloads dependencies; the offline demo itself needs no network.

For development and tests, use a separate virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m honeyguider --help
.venv/bin/python -m pytest tests/test_welcome.py tests/test_mvp.py tests/test_tracking.py
```

The complete suite also includes browser tests, which use the Streamlit version
listed in `requirements.txt`.

## Start with the welcome menu

Run `honeyguider` with no arguments in an interactive terminal. Enter a numbered
choice; press Enter or choose `0` to exit or go back. Ctrl-C or end of input
cancels navigation successfully. Opening the menu does not retrieve documents,
inspect installed tools, or create progress files.

- **Explore the deterministic offline demo** initializes or preserves the Celo
  practice fixture. It shows the next actionable task and its action first.
  Choose full details for citations, progress for blockers, or demo command help.
- **Research documentation / prepare a development plan** asks for a public
  HTTPS documentation URL and goal. Retrieval happens only after you answer yes
  to the network prompt (default: no). Research displays excerpts; planning
  creates an in-memory deterministic demonstration scaffold with source
  references. It does not infer verified requirements or save a tracked plan.
- **Resume a local plan / view progress** opens either the selected demo state
  or a previously imported tracking directory. Tracked plans show the next task,
  progress, full citations, and all task details without accessing the original
  receipt or making network requests. Private tracking validation still applies.
- **Command help** lists all commands, including capabilities outside the menu.
  Use `honeyguider COMMAND --help` for command-specific arguments.

Task completion and environment checks remain explicit commands. The menu does
not execute suggested actions. Documentation and AI recommendations remain
untrusted; citations establish source presence, not correctness. The menu has no
payment or wallet actions.

## Offline demo commands

```sh
honeyguider explore --demo
honeyguider next
honeyguider done scope
honeyguider check
honeyguider status
honeyguider next
```

`check` performs read-only inspection using fixed tool version commands and saves
the observed results. Missing tools produce exit code 1; inspect `status` for
blockers. Completion is self-reported and respects prerequisites. The practice
fixture does not establish current event eligibility or submission requirements.

Demo progress retains the legacy default `.pathf1ndar/state.json`. To use another
file, place the global option before the command, or before opening the menu:

```sh
honeyguider --state-file ./practice/state.json
honeyguider --state-file ./practice/state.json next
honeyguider --state-file ./practice/state.json done scope
```

## Documentation and tracked plans

```sh
honeyguider research https://docs.example.org/guide --goal 'install package'
honeyguider plan https://docs.example.org/guide --goal 'install package'
honeyguider plan https://docs.example.org/guide --goal 'install package' --all
honeyguider track --state-dir ./private-plan next
honeyguider track --state-dir ./private-plan status
honeyguider track --state-dir ./private-plan show
honeyguider track --state-dir ./private-plan done TASK_ID
```

Replace the example URL with actual public HTTPS documentation. Direct research
and plan commands retrieve documentation immediately, as before. `plan --all`
shows every task, dependency and source. `--completed TASK_ID` can be repeated
for in-memory, self-reported planning progress.

Tracking requires an existing valid imported plan (default
`.honeyguider/track`); the menu does not import receipts or discover private data.
See `honeyguider track import --help` for importing an already available successful
receipt offline. Tracking storage must be separate from demo storage. Existing
private files and append-only revisions retain their validation and permissions.

## Scripts and exit codes

Existing explicit commands work with redirected input and output. No-argument
invocation requires both stdin and stdout to be terminals to open the menu;
otherwise it prints help and exits with code 2 without reading input or changing
state. `honeyguider --help` always exits successfully without opening the menu.

Menu exit and cancellation return 0. Command failures retain their existing
codes, including when selected through navigation, and end the menu session.
Invalid menu choices reprompt without performing an action. Existing command
arguments, detailed output, state formats, and entry points remain available.
