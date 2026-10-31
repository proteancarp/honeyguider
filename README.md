# Honeyguider

A Python CLI that turns fragmented documentation and hackathon work into a
clear next step. Start with a deterministic offline practice plan, inspect local
tools, and track progress in local JSON; no account or wallet is needed.

Open source under the [MIT licence](LICENSE).

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
spend real funds, and requires explicit interactive approval. No paid Cencori
response or on-chain settlement has been verified by this project's offline
tests. Do not run `infer` to verify installation; review the detailed limitations
below before considering any live use.

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
only through the explicitly approved `infer` workflow below.

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
dependencies, automatic implementation, or cross-session planning persistence.
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

The following is a **paid command**, provided for review and later authorized
live testing. Do not run it merely to verify installation; use `infer --help`
and pytest for offline checks. No real payment was used to test this phase.

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
response shapes fail closed. The complete envelope is bounded to 128 KiB for
parsing (raw capture remains complete), then `planning.validate_plan()` enforces
the original schema, graph and citation constraints. Markdown fences and code
reconstruction are not accepted. Successful output shows the dependency-aware
next action, labeled an AI-generated, unverified recommendation; no model command
is executed and demo progress remains in legacy `.pathf1ndar/state.json`.

**Live-test limitations:** no paid Cencori response has been captured in this
phase. Installed buy source confirms body-on-stdout and response-header capture,
but the gateway's exact optional completion fields, settlement headers and
correlation identifiers still need a separately authorized live test. Opaque
receipts remain preserved if those shapes differ. Identifier extraction does
not verify on-chain settlement, and buy exit 0 is not treated as payment proof.
A body that fails strict validation is never repaired or repaid automatically.
