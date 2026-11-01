# Honeyguider

A Python CLI that turns fragmented documentation and hackathon work into a
clear next step. Start with a deterministic offline practice plan, inspect local
tools, and track progress in local JSON; no account or wallet is needed.

Open source under the [MIT licence](LICENSE).

## Isolated Streamlit browser demonstration

The optional browser demo reuses `research.research`, `research.extract`,
`planning.build_plan`, and the existing dependency/progress functions. The
terminal CLI and payment workflows are unchanged. Streamlit is installed only
by the deployment requirements; it is not a core CLI dependency.

From the repository root, using Python 3.11+ (Python 3.12 is tested):

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run browser_demo/streamlit_app.py
```

Open **http://localhost:8501**. A working offline example loads automatically,
exactly once per Streamlit session, with no network requests or payments. It
uses a pruned copy of paragraphs from the existing Celo documentation test
capture, shipped as `src/honeyguider/browser_example.html`. The same extractor
and validated deterministic fixture planner process it. The persistent header
identifies the bundled capture and says it does not verify current documentation.

The initial workspace puts **Next action** and **Mark step complete** alongside
a compact dependency roadmap. Completing a step advances the plan; reset clears
progress. The roadmap shows required/optional classification, completion state,
and the titles of tasks blocking unfinished work. Action details and full source
passages expand on demand; the current action's citations remain visible.

Expand **Change source or goal** to edit inputs. To retrieve public documentation,
uncheck **Use bundled offline documentation capture**, enter a public HTTPS HTML
URL and development goal, then select **Retrieve and plan**. Displayed results
retain their submitted context while you edit. Every new submission clears the
old result and progress, including failed submissions. Errors persist across
reruns; failures never automatically restore the offline example. Retry through
the editor or select **Load offline example** to explicitly recover and restore
the default inputs. Initialization failures also require explicit recovery.

The compact workbench uses honey amber, neutral white and soft surfaces, and
forest-green text. It uses Streamlit's bundled sans-serif fonts, without external
font downloads or additional dependencies. Native columns stack on narrow screens,
with wrapping text and no fixed-height scroll areas. Theme settings live in
`.streamlit/config.toml`; the small static CSS block is scoped to named application
containers. No untrusted text enters CSS, HTML or Markdown. Completion history
retains its original order while passing the shared completion validation.

All planning output is persistently labeled as an **authored deterministic
demonstration, not AI inference**, including live retrieval results. Tasks are
an authored scaffold rather than inferred requirements. Validation proves
schema, dependency graph and citation membership, not semantic correctness.
Completion is self-reported. Evidence truncation and omissions remain visible;
code examples are omitted from the browser presentation. Untrusted titles,
excerpts, goals, citations and errors render as plain text, never unsafe HTML.

The browser adapter imports only research and deterministic planning. It has
no paid calls, keyring, credential inputs, environment checks, shell execution,
receipt import, tracking storage, file upload or local-file selection. Do not
put secrets in goals or URLs. Live requests go from the hosting server to the
documentation host; goals stay on the server and are used for keyword matching.
Results and progress live only in Streamlit session memory, with no shared
result cache or writes to CLI state. Reloading/disconnecting may lose progress.
This is application-level isolation, not a sandbox for hostile Python code.

Live retrieval retains the CLI's public-IP/DNS pinning and exact-host HTTPS
restrictions: three pages, six requests, 512 KiB per page, 1 MiB total and a
20-second network retrieval deadline. DNS and HTTP timeouts remain bounded.
Failures and deadline expiry display readable errors; successfully retrieved
partial evidence can still produce a labeled plan. JavaScript-only sites,
compressed responses, anti-bot pages and cross-host redirects may fail. Parsing
bounded HTML and rendering occur outside the asynchronous network deadline.

For Streamlit Community Cloud, after **you** publish the reviewed files to a
GitHub repository, create an app with that repository/branch and entry point
`browser_demo/streamlit_app.py`. Choose **Python 3.12** in Advanced settings.
The root `requirements.txt` installs the local package and pinned Streamlit;
`.streamlit/config.toml` disables usage telemetry and browser exception details
and retains CORS/XSRF protection. No secrets or system packages are required.
Deploy from the repository root so the config and local package resolve.
See Streamlit's official [deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[dependency rules](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
and [file organization](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization).
No Cloud deployment or live retrieval success is implied by offline tests.

Run all tests, including the offline Streamlit UI harness, and check the diff:

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
git diff --check
```

UI tests skip when Streamlit is absent; install `requirements.txt` to include
them. Adapter and UI tests use the bundled capture or mocked HTTP/DNS and cover
one-time initialization, session isolation, ordered completion, source provenance,
partial retrieval, deadlines, unsafe input, persistent failures, explicit recovery,
and submitted context without live services. Run the browser-specific checks with:

```bash
.venv/bin/python -m pytest -q tests/test_browser_demo.py tests/test_browser_ui.py
```

Streamlit's in-process harness verifies behavior, not pixel placement. For visual
checks, use a 1366×768 desktop viewport and a shorter 1366×650 viewport to allow
for browser chrome; the initial action title and completion button should be
visible without scrolling. At 390×844, the action should precede the roadmap,
with no horizontal page overflow. Verify keyboard focus and the expanded editor.

## Core capabilities
- Follow an offline Celo practice plan with prerequisite checks
- Inspect local Python, Git, Node.js and npm versions without installing tools
- Retrieve source-linked excerpts from public HTTPS documentation
- Generate deterministic dependency-aware planning scaffolds
- Recommend the next actionable step and track demo progress across sessions

## Quick start (offline)

Requires Python 3.11+. From a checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/honeyguider explore --demo
.venv/bin/honeyguider next
.venv/bin/honeyguider done scope
.venv/bin/honeyguider check
.venv/bin/honeyguider next
.venv/bin/honeyguider status
```

Installation downloads dependencies; the demo commands then work offline.
The first `next` shows `scope`. After marking it complete, `check` records local
tool versions and the next task is `workspace` if all checks pass. Missing Git,
Node.js or npm makes `check` exit 1 and blocks `workspace`; install missing tools
yourself and rerun `check`. `status` explains blockers. Completion is self-reported.

**Development status:** this is an early MVP. The demo is an authored practice
scenario, not verified hackathon rules. Research uses keyword matching and
planning scaffolds are deterministic; Honeyguider does not implement tasks.
Live research requires network access. Installation and offline tests require
no API credentials, blockchain funds or wallet access.

**Live-payment limitation:** the separate `infer` command is experimental, can
spend real funds, and requires explicit interactive approval. The first captured
paid Cencori inference returned an incomplete completion and was rejected; its
Celo transaction was reported successful. Offline tests do not verify live
inference or settlement. Do not run `infer` to verify installation; review the
detailed limitations below before considering any live use.

Keep private prepared requests in `requests/`, receipts in `receipts/`, and
custom state in `.honeyguider/` (or use the default `.pathf1ndar/`). These locations
are ignored by Git. Arbitrary `--request-file`, `--receipt-dir` or `--state-file`
paths are not automatically ignored; check `git status` before staging files.

## Hackathon
Celo Agents on Open Rails — Build with buy

## Stack
Python, Typer, Rich, HTTPX, pytest

## Offline MVP

Requires Python 3.11+. Install explicitly in a local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/honeyguider --help
.venv/bin/honeyguider explore --demo
.venv/bin/honeyguider check
.venv/bin/honeyguider next
.venv/bin/honeyguider done scope
.venv/bin/honeyguider next
.venv/bin/honeyguider status
.venv/bin/python -m pytest -q
```

`check` reports the current Python interpreter and runs only `git --version`,
`node --version`, and `npm --version` through resolved PATH executables, with
five-second timeouts and no shell. It installs nothing. Missing or failing tools
produce exit code 1 and remain blockers. Only run against a trusted local PATH.
The offline commands make no network requests, access no wallets, and perform
no transactions.

`next` selects the first unfinished task with completed prerequisites and passing
required tool checks. `done TASK_ID` records self-reported completion and refuses
blocked or unknown tasks. Complete tasks in this order:
`scope`, `workspace`, `prototype`, `validate`, `submission`.
The workspace task requires successful checks for all four tools. Completion is
manual; honeyguider does not create the prototype or verify its implementation.

Progress is stored in `.pathf1ndar/state.json` relative to the current directory.
This legacy directory name is intentionally retained after the Honeyguider
rename so existing demo progress remains available without migration. No state
files are renamed, deleted, or overwritten by the rename. Use `--state-file`
to choose a different location explicitly. The distribution, Python imports,
and executable are now `honeyguider`; the old import and command names are not
compatibility aliases.
Use the global option before the command to select another file:

```bash
.venv/bin/honeyguider --state-file /tmp/honeyguider-demo.json explore --demo
.venv/bin/honeyguider --state-file /tmp/honeyguider-demo.json status
```

Repeated exploration preserves progress. Checks are saved snapshots; rerun
`check` after environment changes. State writes use atomic replacement; malformed
or unsupported state fails with a readable error and is not overwritten.
Concurrent writers to the same state file are not supported.
To start again, choose a new state file.

## Architecture and scope

`src/honeyguider/cli.py` handles Typer commands and Rich output. `model.py` holds
tasks and prerequisite selection, `demo.py` defines the deterministic Celo
practice fixture, `checks.py` inspects local tools, and `state.py` validates and
persists versioned JSON. Tests mock tool execution and need no network or Node
installation. HTTPX and BeautifulSoup are declared for future documentation
retrieval in `research.py`; the offline demo does not use them.

The demo is an authored practice scenario inspired by the hackathon context,
not an authoritative event checklist. Its documentation references are
[Celo documentation](https://docs.celo.org/) and
[Build on Celo](https://docs.celo.org/build-on-celo); they are not fetched or
verified by this program. Eligibility, deadlines, SDK details and actual
submission rules must be checked against current official event materials.
Automatic implementation remains outside this MVP. Paid AI planning is available
only through the explicitly approved `infer` workflow below. An existing successful
receipt can be imported for offline progress tracking with `track`.

## Dependency planning (Phase 3A)

```bash
.venv/bin/honeyguider plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip"
.venv/bin/honeyguider plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip" --all
.venv/bin/honeyguider plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip" --completed review-1
.venv/bin/honeyguider plan --help
.venv/bin/python -m pytest -q
```

`plan` reuses the existing research retrieval and safety controls. The only
provider is an explicitly labeled **deterministic demonstration fixture**. It
uses retrieved section headings and source URLs to build a scaffold: review
each distinct passage in order, record its prerequisites and steps, build a
local prototype from those notes, and optionally add an offline test. These
authored tasks are not documentation requirements or AI inference. Source
references identify input evidence; citation presence does not establish that
the documentation requires or supports the scaffold's development choices.

The default output displays one next action. `--all` displays all tasks, their
dependencies, citations, required/optional classifications and
ready/blocked/completed states. A task is blocked until every prerequisite is
completed. Required work and its prerequisite closure take priority over
optional-only work. Optional prerequisites still block their dependents;
optional is not synonymous with ready or skippable for a dependent task.

Use repeated `--completed TASK_ID` options to supply self-reported progress
for the current invocation. Unknown IDs, duplicates, and completed tasks with
unfinished prerequisites are rejected. No new plan or progress is persisted.
The offline Celo demo JSON, `done`, `next`, and `status` remain separate and
unchanged; `plan` neither reads nor writes `--state-file`. Re-running research
against changed documentation can change review IDs, so inspect `--all` before
supplying completion IDs.

`planning.py` defines a small provider protocol returning JSON and a strict
validation boundary shared with future adapters. Schema version 1 contains
`schema_version` and `tasks`. Every task contains exactly `id`, `title`,
`action`, `prerequisites`, `sources`, and `classification` (`required` or
`optional`). Limits are 20 tasks, 40 characters per ID, 160 per title, 1200 per
action, three citations per task, 4096 characters per source URL, and 64 KiB of
provider JSON. IDs must be unique lowercase identifiers; dependencies must be
unique, known, non-self-referential and acyclic. Every task must cite at least
one actually retrieved page URL; discovered-but-unfetched links do not qualify.
Missing/unknown fields, wrong types, duplicate JSON keys, control characters,
and unsupported versions are rejected. These checks validate structure and
provenance membership, not semantic correctness or task completion.

No relevant retrieved sections means no plan. Partial research failures are
reported; a plan can use successfully retrieved evidence but exits with code 1.
Truncated evidence and page warnings remain visible. Evidence and provider
output are untrusted data: the planner executes no commands, source examples,
transactions, or provider instructions. There are no AI/paid API calls, new
dependencies or automatic implementation. This `plan` command has no cross-session
planning persistence; the separate opt-in `track` workflow below imports AI receipts.
Tests exercise the provider and CLI with offline fixtures and mocked research.

## Cencori request preparation and unpaid quotes (Phase 3B.1)

Default `plan` behavior remains the deterministic demonstration. Cencori modes
prepare a future inference request; they do not retrieve an AI completion or
perform a payment. `--prepare-only` retrieves documentation and saves the body
without contacting the gateway:

```bash
.venv/bin/honeyguider plan https://docs.celo.org/build/agents/8004 \
  --goal "Register an ERC-8004 agent on Celo" \
  --prepare-only --max-tokens 1024 \
  --request-file /tmp/honeyguider-cencori-prepare.json
```

For an unpaid quote, supply an **already installed, trusted** `@celo/buy@0.8.4`
executable. Replace the executable path below with its actual absolute path;
honeyguider does not install packages, invoke npx, create wallets, inspect keys,
or fund accounts. Each invocation requires a new output filename:

```bash
.venv/bin/honeyguider plan https://docs.celo.org/build/agents/8004 \
  --goal "Register an ERC-8004 agent on Celo" \
  --quote-only --max-tokens 1024 \
  --buy-executable /absolute/path/to/trusted/buy \
  --request-file /tmp/honeyguider-cencori-quote.json
.venv/bin/python -m json.tool /tmp/honeyguider-cencori-quote.json
sha256sum /tmp/honeyguider-cencori-quote.json
.venv/bin/python -m pytest -q
```

The adapter checks `buy --version`, accepts only the tested 0.8.4 interface,
and invokes the documented
[buy quote command](https://github.com/celo-org/buy-skill/blob/main/skills/use-api-gateway/SKILL.md#partner-paywalls)
using `quote -X POST -H 'content-type: application/json' --data BODY` and the
fixed endpoint `https://gateway.usebuy.ai/cencori/v1/chat/completions`. `BODY` is
the **exact saved body**, passed as one argument, not a placeholder prompt or
shell command. Only these two fixed buy operations are available. Version and
quote timeouts are five and thirty seconds, with no retry. Executable identity
is trusted by your explicit path selection, not proven by its version string;
use a trusted installation and PATH for its runtime. Credentials, wallet
variables, and Node options from the parent environment are not forwarded.

The request builder uses only `model`, `max_tokens`, and `messages`, targeting
`maximo-atlas-1.3`. Output budgets are restricted to 256, 1024 or 4096 tokens.
System instructions include the strict plan JSON shape, graph rules, limits,
and allowed citation URLs. The user message encodes the goal and bounded
retrieved excerpts as untrusted JSON data, preserving code, source attribution,
and truncation/omission flags. Unfetched links are excluded. Retrieval failures,
missing excerpts, mismatched citations and out-of-budget evidence are rejected.
The complete outer request is serialized once using sorted keys, compact
separators and ASCII escapes, and rejected above **32768 bytes**. There is no
automatic shortening to silently remove instructions or alter code.

Request files contain the canonical body only, without a trailing newline;
they are exclusively created with owner-only permissions and never overwrite
existing files or the selected demo state. The CLI prints the SHA-256 and byte
count before quoting. A failure leaves the body available for inspection.
Keep that file and digest for later exact-request approval; regenerating a
request from changed documentation creates a different request. A future paid
integration must verify those bytes and obtain approval separately. The preparation/quote modes provide no payment path; the separate `infer`
command below adds interactive execution for already saved requests.

Quote mode sends the goal and excerpts to the external gateway via buy, so
review the saved content and keep secrets out of goals and public evidence.
Quote output is untrusted text, displayed with terminal controls removed and
at most 16000 bytes from each output stream. It is never used as executable
instructions, an endpoint override, a payment authorization, or a price cap.
No token/amount is hardcoded: the returned quote is authoritative. The confirmed
gateway supports USDC, USDT and USAT on Celo; token selection and payment are
outside this phase. Quote failures exit 1; conflicting options exit 2.

Offline tests mock buy and HTTP research. They verify the request contract,
byte limits, injection separation, exact quote arguments, failure handling and
absence of payment commands. No live quote success is implied by those tests.

## Live documentation research

```bash
.venv/bin/honeyguider research https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip"
.venv/bin/honeyguider research https://docs.celo.org/ --goal "build agents"
.venv/bin/honeyguider research --help
.venv/bin/python -m pytest -q
```

Research prints the retrieved page title, at most five relevant excerpts and
five matching documentation links per page. Excerpts are source text, not
independently verified facts. Relevance uses distinct overlapping words of at
least three ASCII letters/digits, ignoring common question words and generic
site terms such as `python`, `celo`, and `documentation`. Hostnames and query
strings do not contribute to link scores. Links require at least two focused
goal terms, or the sole focused term for a one-term goal. A goal consisting
only of generic terms retrieves the starting page but produces no matching
excerpts or followed links. Links rank by overlap then URL. Sections prioritize
headings matching the goal's first focused term, then heading overlap and total
overlap, with document order breaking ties. Continuations share their section's
rank and retain source order; consecutive excerpts display the heading once.
There are no AI summaries or
generated requirements.

Semantic navigation, headers, footers, sidebars, breadcrumbs, tables of contents,
and common documentation-theme wrappers are removed heuristically. Repeated
content blocks are deduplicated within each page. Each excerpt contains at most
four blocks, 600 prose characters and 1200 code characters. Truncation and
omission are explicit; matching can occur before final truncation, so a matched
word may fall outside the displayed excerpt. Code text inside `pre` elements
preserves whitespace, indentation, tabs, blank lines and adjacent syntax spans.
Code bypasses terminal wrapping and tab expansion. Oversized code and code
containing unsafe control characters are omitted with a notice, never clipped
into a partial command. Source text is never repaired or reconstructed; malformed
examples must be checked at their source. Extraction reflects static HTML text,
not browser layout or JavaScript-generated examples.

Within a relevant section, excerpts retain a contiguous passage in source order,
including paragraphs without matching goal words. A matching heading starts the
passage at the section opening; otherwise it starts up to four blocks before the
first matching block. Longer passages split into consecutive excerpts within
the existing budgets, rather than skipping nonmatching procedural steps. The
five-excerpt page cap still applies; shortened excerpts explicitly direct the
reader to the source for full context.
Semantic paragraph markup (`data-as="p"` and `role="paragraph"`) is recognized
alongside native HTML paragraphs, including MDX-rendered spans and divs.

The in-memory research representation remains bounded and source-linked:
`Report.pages` contains page URLs, titles, relevant headings, sections and links.
Sections retain their source URL, matched terms, truncation flag, and ordered
typed blocks (`text`, `code`, or omission `notice`). This keeps evidence and
inferred relevance separate. Research itself performs no inference; saved
evidence can be submitted through the explicitly approved `infer` workflow.

Only the top two sufficiently matching links from the starting page are followed;
zero or one may qualify. Linked pages do not expand the crawl. All pages and redirects must use HTTPS port 443
and the exact original hostname. Research is independent of plan storage: it
does not read, create, or overwrite progress JSON, including `--state-file`.

Retrieval limits:

- Three pages total, two redirects per page, six HTTP requests total (including
  failures and redirects); no automatic retries.
- 512 KiB per response and 1 MiB of received response bodies total. Content-Length
  is checked when present, and streamed bytes are always checked. A crossing
  chunk is received then rejected, so reported bytes can exceed the limit by
  that chunk; the oversized body is not parsed.
- A 20-second asynchronous retrieval deadline, DNS timeout of three seconds,
  connect timeout of three seconds, and other HTTP operation timeouts of five
  seconds. Bounded HTML parsing is synchronous and can add processing time.
- Only `text/html` with identity encoding is supported. Compressed responses,
  PDFs, JSON and other formats are reported as unsupported. No JavaScript,
  browser rendering, login, downloads, shell commands, or page instructions run.

URL safety rejects credentials, non-HTTPS schemes, alternative ports, local
hostnames, non-public IPs, mixed public/private DNS answers, and IPv6 transition
addresses. IPv6 is restricted to ordinary global unicast outside special
protocol assignments. Every request, including each redirect, resolves and
validates DNS, then connects to a validated numeric IP. The original hostname
is sent as Host and TLS SNI, with certificate verification enabled, using the
[HTTPCore SNI extension](https://www.encode.io/httpcore/extensions/#sni_hostname).
This avoids a second hostname resolution between validation and connection.
Environment proxies and custom CA environment settings are disabled. Platform
DNS calls run in bounded-count daemon workers so a stuck resolver cannot hold
CLI shutdown; a timed-out platform lookup may continue until process exit.

These controls are not a complete network sandbox: they rely on the operating
system resolver, routing, TLS trust store, and IP address classification. They
cannot identify private services exposed through public IPs or unusual local
routes. Use network-level egress controls for hostile deployments. Only the
first validated DNS address is tried; unreachable IPv6 or IP-specific routing
can therefore make an otherwise available site inaccessible. Cross-host
redirects (including `www` or CDN migrations) are refused; supply the intended
final documentation hostname explicitly. Internationalized hostnames are not
supported in this minimal implementation.

External text is untrusted and terminal control characters are stripped before
display. Hidden/script/navigation elements are removed heuristically, not with
a browser's CSS engine. Sparse HTML and explicit JavaScript notices produce a
warning; detecting all JavaScript-dependent pages is not possible. HTTP/DNS/TLS
failures are reported with their source URL. Exit code 1 means a retrieval issue
occurred, including partial success; successful pages remain visible. No live
website availability is implied by the mocked tests.


## Explicitly approved inference (Phase 3B.2)

`infer` reads an existing canonical Cencori request without fetching documentation
or regenerating the HTTP body. It rejects oversized (>32 KiB), duplicate-key,
noncanonical or unsupported JSON, modified system instructions/schema, unsupported
models/token budgets, and evidence outside the original excerpt limits. Allowed
plan citations come only from page URLs in that request. This checks internal
consistency; it does not cryptographically attest that a manually authored file
was retrieved from the web. Review prepared files before approving them.

The following is a **paid command**, provided for review and independently authorized
live testing. Do not run it merely to verify installation; use `infer --help`
and pytest for offline checks. Automated tests use synthetic responses and mocked
payments; the separately captured live attempt is described below.

```bash
.venv/bin/honeyguider infer --help
.venv/bin/python -m pytest -q

# PAID: requires active interactive approval; use only after independent review.
.venv/bin/honeyguider infer \
  --request-file /tmp/honeyguider-cencori-quote.json \
  --buy-executable /home/anu/.local/share/honeyguider-buy/node_modules/.bin/buy \
  --receipt-dir receipts/cencori-attempt-001 \
  --token USDC
```

The buy path above was inspected locally: `--version`, `--help` and
`curl --help` reported **0.8.4**. Choose your own trusted absolute executable
path on another machine. `infer` requires a new receipt directory whose parent
already exists (for example, create `receipts/` manually). It never reuses or
resumes an attempt directory, and refuses unattended stdin/stdout. There is no
`--yes`, approval environment variable, automatic spend cap, or payment retry.

The installed 0.8.4 quote implementation explicitly supports `buy --json quote`;
this returns the parsed x402 envelope on stdout. Honeyguider runs:

```text
BUY --version
BUY --json quote --token TOKEN -X POST -H "content-type: application/json" --data EXACT_BODY ENDPOINT
BUY --json curl --max-amount CAP --token TOKEN -X POST -H "content-type: application/json" --data EXACT_BODY --dump-header PRIVATE_HEADERS_FILE ENDPOINT
```

The last invocation happens only after approval. `--json` is a global buy option
and must precede `curl`; `--max-amount` and `--token` are buy curl options.
`--dump-header` is forwarded to curl, supported by buy's inspected header-capture
path; stdout remains the response body. No `--data-file` is used: the original
in-memory UTF-8 body is passed unchanged as one argv element to both calls.
Nothing is interpolated into a shell. Honeyguider invokes no wallet setup,
funding, key access, signer implementation or payment-negotiation code of its own.

The narrowly supported quote shape has `x402Version: 1` and an `accepts`
array in buy's normalized form: `network: "celo"`, `scheme: "exact"`, `asset`,
`maxAmountRequired` (decimal atomic integer) and `payTo`. Mainnet token addresses
and six-decimal conversion are pinned to the locally inspected buy-core 0.8.4
USDC/USDT/USAT definitions. Version 2 is explicitly rejected until its gateway schema is confirmed. Unsupported shapes, networks or schemes are refused.
The selected token must actually be offered; buy also enforces token selection
at payment time. There is no hardcoded inference price.

After displaying the fresh selected-token offer(s), Honeyguider prompts for a
positive cap in **human-readable token units**, not atomic units. Caps support
at most six decimal places and a fixed conservative pilot ceiling of **0.05
token units**. A selected-token quote above that ceiling is rejected, not used
to raise the ceiling. The human cap must equal a freshly quoted selected-token
offer exactly in value; both smaller and larger caps are refused. Equivalent
decimal spellings such as `0.01` and `0.010000` have the same token value, but
the final approval phrase must still match the literal cap entered. It then requires typing exactly:

```text
APPROVE FULL_64_CHARACTER_SHA256 TOKEN CAP
```

The request hash, token and literal cap must all match, and approval expires
five minutes after the quote. Refusal, EOF, interrupted input, a changed request
file, or an expired approval launches no payment. Approval is not inferred from
wallet balances or from any prior quote. Price may change between quote and
purchase; buy enforces the human's approved cap. A person must review any new
attempt independently, especially after ambiguous settlement.

Only OS session context (`PATH`, `HOME`, `LANG`, `DBUS_SESSION_BUS_ADDRESS`,
`XDG_RUNTIME_DIR`) is forwarded so buy can access its existing default account
and **system keychain**. No Node options, API credentials, private-key environment
variables, BUY_HOME overrides, or file-keystore backend selector are forwarded.
Custom wallet directories/accounts and file-keystore mode are intentionally not
supported in this first implementation. Honeyguider does not inspect the
wallet; buy owns all supported local key access.

A receipt directory is mode 0700 and files are exclusively created mode 0600:

- `request.json`: exact approved bytes; `quote.stdout`/`quote.stderr`: private
  streamed quote diagnostics (at most 128 KiB per stream). `quote-outcome.json`
  identifies failure, interruption, timeout, or truncated output. Overflow kills
  the quote process group and rejects it before any payment approval; partial
  or truncated quotes are never used for pricing. Reads are fixed 16 KiB chunks,
  avoiding unbounded memory capture and limiting retained disk diagnostics.
- `approval.json`: approved hash/token/cap, endpoint, executable/version and time.
- `attempt.json`: durable launch intent, written **before** the single paid
  subprocess invocation. A starting record alone means settlement is unknown.
- `stdout.bin`, `stderr.bin`, `headers.bin`: complete raw paid-attempt evidence,
  retained even if exit status, completion parsing or plan validation fails.
- `outcome.json`: command outcome and exit status, with settlement explicitly
  unknown. Valid-format transaction and correlation/request identifiers found
  in response headers are recorded as **unverified claims**, not proof of payment.
- `validation.json`: completion/plan validation success or failure, if reached.

Do not publish raw files: provider bodies, stderr or headers may contain sensitive
information. They are not echoed to the terminal. Payment stdout/stderr remain
complete raw captures; only unpaid quote diagnostics have a prefix limit.

Before launch, Honeyguider fsyncs the receipt directory's entry in its parent,
request bytes and header/output placeholders, approval and launch intent. Every
JSON record is file-fsynced, then its containing directory is fsynced. The final
`attempt.json` directory barrier precedes Popen. A pre-launch filesystem error
stops execution. After launch, raw files and outcome/validation records are
synced, and any error stops processing without another invocation. This uses
[the separate file/directory fsync requirements](https://man7.org/linux/man-pages/man2/fsync.2.html),
not a transaction journal. Filesystem/hardware behavior and successful fsync
completion remain prerequisites for durability. Missing or partial records are
**never evidence that no payment occurred**. A durable starting intent, by itself,
means settlement UNKNOWN; disk failures may prevent even final error bookkeeping.

On POSIX, SIGINT and SIGTERM handlers installed before Popen only set a
cancellation flag; they do not raise exceptions inside process creation. Once
Popen returns and assigns the child handle, pending cancellation kills its
process group and reaps the leader. After launch the supervisor uses
50 ms polling slices (not hard OS response deadlines), keeps non-raising
handlers through cleanup, and restores the prior
handlers afterwards. This closes the signal-exception handle-assignment window
explained in [Python's signal documentation](https://docs.python.org/3/library/signal.html#note-on-signal-handlers-and-exceptions).
Timeouts (120 seconds for payment, 30 for quotes), interruption and output-limit
failures never cause a retry. Quote supervision uses the same launch protection.
Settlement remains UNKNOWN after interruptions even if the child exits normally.

This is main-thread POSIX supervision, not a kernel service manager. SIGKILL,
interpreter/host crashes, or other exception-raising signal handlers can bypass
Python cleanup. A stuck OS spawn may delay access to the child handle; pending
SIGINT/SIGTERM cancellation is acted on once spawn returns. Descendants that
intentionally leave the process group cannot be supervised by group termination.
An uninterruptible kernel wait may delay reaping. No local cleanup can reverse
a payment already submitted, and no missing record authorizes another attempt.
Inspect all available local and buy evidence before any independent new approval.

The supported completion is a JSON object containing exactly one
`choices[0]` with `index: 0`, `finish_reason: "stop"` and an assistant message
whose `content` is a JSON plan string, without tool calls or a refusal. Standard
OpenAI metadata fields are accepted with type checks; unsupported fields and
response shapes fail closed. Cencori's optional top-level `safety` object is
supported narrowly: it must contain exactly `scanned`, with a JSON boolean
(`true` or `false`). Missing `scanned`, nulls, numeric/string substitutes and
additional safety fields (including `input` verdicts) remain unsupported.
[Cencori's safety documentation](https://cencori.com/docs/api/chat#safety-classification)
describes `scanned: false` as passthrough without scanning. Neither boolean
value is proof that the response is safe, the plan is valid, or payment settled;
the field does not affect plan validation or authorize execution.

The complete envelope is bounded to 128 KiB for
parsing (raw capture remains complete), then `planning.validate_plan()` enforces
the original schema, graph and citation constraints. Markdown fences and code
reconstruction are not accepted. Incomplete completions, including
`finish_reason: "length"`, remain invalid even with well-formed safety metadata
or syntactically complete plan JSON. Successful output shows the dependency-aware
next action, labeled an AI-generated, unverified recommendation; no model command
is executed and demo progress remains in legacy `.pathf1ndar/state.json`.

**First captured paid inference and limitations:** the operator reported these
selected response fields from the first live Cencori paid attempt:

```json
{
  "model": "maximo-atlas-1.3",
  "safety": {"scanned": false},
  "choices": [{"finish_reason": "length"}],
  "usage": {"completion_tokens": 1024}
}
```

The request allowed 1,024 output tokens and used all 1,024. Honeyguider rejected
the response: `safety` was previously an unsupported top-level field, and
`finish_reason: "length"` independently marks an incomplete completion. The
compatibility change accepts the narrow safety metadata shape; it does not make
that captured response valid or recover a usable plan. Private receipts remain
outside this repository; regressions use synthetic data, not private captures.

Request preparation already supports `--max-tokens 4096`, alongside 256 and
1024 (the unchanged default). A larger budget may avoid this particular token
limit but cannot guarantee a complete or valid plan. Changing a request changes
its bytes/hash and requires a fresh quote and independent interactive approval
for any future paid attempt. There is no automatic budget escalation or retry.

The Celo transaction was reported successful, but an on-chain transaction alone
does not establish verified application-level settlement: Honeyguider has not
verified that the gateway settled the approved request and delivered a valid
plan. Outcome records keep `settlement: "unknown"`; response-header identifiers
are unverified claims, and buy exit 0 is not payment proof. This change performs
no chain verification or new live inference. Other gateway completion metadata,
settlement headers and correlation identifiers remain only partially observed;
unsupported shapes fail closed and raw evidence is preserved. A body that fails
strict validation is never repaired or repaid automatically.

## Offline AI plan tracking (opt-in)

Import an **existing successful private inference receipt**. These commands make
no network requests, invoke no subprocesses, access no wallets, send no payments,
and execute no task actions. No new inference is needed or triggered.

```bash
.venv/bin/honeyguider track import --receipt-dir receipts/cencori-attempt-001
.venv/bin/honeyguider track show
.venv/bin/honeyguider track next
.venv/bin/honeyguider track done TASK_ID
.venv/bin/honeyguider track status

# Choose a separate new tracking directory for another plan:
.venv/bin/honeyguider track --state-dir .honeyguider/another-plan import \
  --receipt-dir receipts/cencori-attempt-002
```

`import` checks matching approval/launch/outcome records, request SHA-256, exit
status zero, and a successful validation record. It then independently reruns
`paid.load_request()` and `paid.parse_completion()` on the saved request and raw
completion, including bounded evidence, instruction, citation and dependency
validation. `validation.json` alone never establishes validity. Missing, corrupt,
unsupported, shared-permission or symlinked required files are refused. The
receipt directory must be private (0700) and required files private (0600).
Quote diagnostics, stderr and headers are not imported or used to prove validity.
Receipt files are read only; import starts with no completed tasks.

`show` displays the full graph as task dependency lists, including actions,
citations, required/optional classifications and ready/blocked/completed states.
`next` selects an unblocked task needed by required work, including optional
prerequisites, and stops when all required tasks are complete. Optional-only
work remains visible and can be completed manually. `done` rejects unknown or
duplicate completions and unfinished prerequisite chains. `status` reports
required and overall progress plus each task's blockers. Completion is entirely
self-reported; AI recommendations and citation entailment remain unverified.

Tracking defaults to `.honeyguider/track/`, separate from the global demo
`--state-file` and legacy `.pathf1ndar/state.json`. Import refuses **any existing
destination**, even an empty directory. There is no reset, migration or overwrite.
`tracking.py` stores a schema-version-1 snapshot in `000000.json`, then one new
immutable revision per completion. Each revision contains the validated plan,
allowed sources, receipt path, request/completion hashes and completion IDs.
Files are created privately, fsynced, and published atomically using an exclusive
hard link; the directory is then fsynced. Earlier revisions are never replaced.
Every read validates the schema, graph, completion chain and complete revision
history. These private files may contain sensitive task text: keep them out of Git.

This storage requires a local POSIX filesystem supporting hard links and fsync.
Concurrent writers are not supported; exclusive publication prevents clobbering,
and a conflicting command fails. A crash can leave an empty import directory or
an unexpected pending file; reads fail closed rather than automatically repairing
history. Inspect and preserve such files before choosing a new destination.
Durability depends on the filesystem; snapshots and hashes do not authenticate
receipt authorship, web provenance, task correctness or payment settlement.
Tracking checks local consistency without verifying settlement on-chain. The
receipt need not remain available after import. Offline tests use synthetic
receipts and do not demonstrate live inference or payment success.
