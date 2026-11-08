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

- **Explore documentation** asks for a public HTTPS URL and development goal.
  Choose relevant excerpts or a fixed demonstration plan. Retrieval requires
  explicit network confirmation (default: no). Demonstration plans are not
  AI-inferred requirements and are not saved for tracking.
- **Continue a saved plan** offers the sample walkthrough, a previously imported
  AI plan, or a list of existing tracked plans (**3**). Imported plans remain
  unverified recommendations; private tracking validation and append-only
  revisions apply.
- **Try a sample walkthrough** starts or resumes fixed offline Celo practice data.
  It shows a compact current step and progress count. No source is fetched.
- **Help and advanced commands** explains the workflow and lists CLI commands.
- **Wallet & payments** opens read-only wallet and payment views plus a
  proposal-only setup. It never holds keys and never confirms settlement;
  reconciliation is the only action that explicitly asks buy for on-chain
  status (default: no).
- **Create a tracked plan** runs the guided paid journey: research, one approved
  paid attempt, idempotent import and a local tracking session.
- **Exit** leaves saved progress available for the next visit.

For a ready, unfinished step, choose **1** to mark it complete, then explicitly
confirm self-reported completion (default: no). Existing completion handlers
validate prerequisites and save progress; the next actionable step appears
immediately. If no step is actionable, the next pending step shows its blockers.
Choose **2** for instructions and sources, **3** for the complete roadmap,
progress and blockers, **4** to inspect a step by its roadmap ID, or **0** to
return to the main menu. Blocked or completed steps have no completion action;
the menu explains prerequisites, required tool checks, or existing completion.
Instructions and roadmap inspection remain available. Completion applies to the
inspected step when it is ready and unfinished. After a
successful completion, navigation returns to the next available step.

For the sample, **5** offers local tool version checks, with a separate explicit
confirmation. These checks save a snapshot and never install tools. The workspace
step remains blocked until the required tools have successful saved checks.
Read-only views, invalid choices and refused confirmations do not repeat the
entire task and action list. The numbered actions remain available in scrollback.

If a completion attempt fails, saved progress may already have changed. The
menu re-reads validated saved state when possible and reports what is currently
visible; this does not establish storage durability after a late failure. Writes
are never automatically retried. If progress cannot be verified, navigation
stops so you can inspect the saved plan before attempting another completion.

Offline sample links are references that have not been fetched. Imported AI-plan
links are citations to the evidence retrieved for the original plan. Opening an
imported plan does not re-fetch those sources.

You do not need standalone commands to complete the walkthrough. Suggested task
work is performed manually outside Honeyguider; completion records your report,
not verified execution. Source references establish citation presence, not
correctness. Recorded examples are saved outputs, not live inference. Paid
inference and wallet actions live only under **5 Wallet & payments** and
**6 Create a tracked plan**, both of which state their own limits.

## Guided journey (Phase 6)

The main menu composes the existing boundaries rather than replacing them:

| Menu | Action | Network or payment |
| --- | --- | --- |
| **5** | Wallet & payments | Read-only by default; reconciliation asks separately |
| **6** | Create a tracked plan | Retrieval consent and one separately approved paid attempt |
| **2 → 3** | List existing tracked plans | None; reads local tracking directories |

Every menu entry begins with the same rule: opening the menu stays offline, the
sample is fixed practice data, imported plans are unverified AI recommendations,
and recorded examples are saved outputs rather than live inference.

### Wallet & payments (**5**)

Sub-options are **1** identity and readiness, **2** balances, **3** funding
instructions, **4** payment history, **5** reconciliation and **6** setup.

- Identity/readiness separates a genuinely zero supported balance from balances
  that could not be read; missing information is never reported as zero. Sepolia
  identities are routed to Celo Mainnet, which the paid journey requires.
- Funding instructions list the receiving address and supported tokens (USDC,
  USDT, USAT), note that the gateway sponsors transaction gas so no separate CELO
  gas balance is needed, and separate funding a wallet from approving a paid call.
- Payment history shows locally recorded claims from the buy receipt ledger, not
  settlement proof. Recorded transaction hashes are unverified correlation only.
- Reconciliation asks for its own network consent (default: no), then offers an
  optional receipt-directory correlation. A single match is correlation evidence
  only, never provider authentication of settlement; the menu repeats that an
  imported record does not prove a provider payment settled.
- Setup is a proposal only. The menu prints `buy setup --name <alias>` for you to
  run in your own terminal, then asks you to choose **1** to verify readiness. It
  never executes setup, never reads or stores key material, and never creates the
  account for you.

### Create a tracked plan (**6**)

The guided paid journey runs in this order:

1. Enter the documentation URL and development goal; retrieval needs a separate
   network consent (default: no). Declining creates nothing.
2. `journey.prepare` builds and exclusively preserves the exact request under
   `.honeyguider/requests`. Preparation is free.
3. A readiness gate checks the named buy account and Celo Mainnet identity. If the
   wallet is unreadable, not mainnet, or otherwise unsuitable, the flow returns
   without charging and keeps the prepared request for later.
4. After an explicit proceed confirmation, choose a payment token (default USDC,
   validated against USDC/USDT/USAT) and a new receipt directory under
   `.honeyguider/receipts`.
5. `journey.infer_with_receipt` runs the paid attempt under the content-keyed
   lock, with the named account and expected payer: a fresh quote, an
   exact-match spend cap, a session approval code, and one attempt with no
   automatic retry.
6. `journey.import_outcome` imports the validated outcome idempotently. A custom
   tracking root requires explicit consent (default: no). A previously imported
   record is recognized rather than duplicated.
7. The tracking session opens with the statement that the plan is validated for
   inference output but **payment settlement remains UNKNOWN**, and that an
   imported record does not prove a provider payment settled.

If the paid attempt cannot start (for example, advisory locking is unavailable on
this platform), the request is preserved and nothing is charged. If a paid call is
refused or fails, the menu states that settlement is UNKNOWN and never confirms
it. Payment may settle even when response validation fails; a new attempt always
needs fresh review.

### Resuming tracked plans (**2 → 3**)

**2 Continue a saved plan**, then **3 List existing tracked plans**, shows each
local tracking directory with completed/task counts and its recorded attempt or
settlement label. Settlement is reported as `unknown`; an unreadable or missing
receipt also adds a bounded problem row. Selecting a listed number opens that
plan; a path can be entered instead. Listing creates nothing, follows no
symlinks, and never promotes settlement to confirmed.

See [demo-script.md](demo-script.md) for the presenter flow and
[guided-workflow-review.md](guided-workflow-review.md) for the implementation
record.

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
`.honeyguider/track`); the menu never imports receipts; only 2 → 3 lists existing local tracking directories (read-only). The previously imported AI plan path still requires a manually entered directory.
See `honeyguider track import --help` for importing an already available successful
receipt offline. Tracking storage must be separate from demo storage. Existing
private files and append-only revisions retain their validation and permissions.

## Scripts and exit codes

Existing explicit commands work with redirected input and output. No-argument
invocation requires both stdin and stdout to be terminals to open the menu;
otherwise it prints help and exits with code 2 without reading input or changing
state. `honeyguider --help` always exits successfully without opening the menu.

Menu exit and cancellation return 0. Explicit command failures retain their
existing codes. Inside the menu, rejected completion, unavailable tools and
retrieval issues show feedback and allow navigation to continue. Invalid saved
state and storage boundary errors stop navigation without resetting progress.
Invalid menu choices reprompt without performing an action. Existing command
arguments, detailed output, state formats, and entry points remain available.
