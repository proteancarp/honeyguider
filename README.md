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
The offline commands make no network requests, access no wallets, and perform
no transactions.

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
retrieval in `research.py`; the offline demo does not use them.

The demo is an authored practice scenario inspired by the hackathon context,
not an authoritative event checklist. Its documentation references are
[Celo documentation](https://docs.celo.org/) and
[Build on Celo](https://docs.celo.org/build-on-celo); they are not fetched or
verified by this program. Eligibility, deadlines, SDK details and actual
submission rules must be checked against current official event materials.
Live AI planning, automatic implementation, and on-chain operations remain outside
this MVP.

## Dependency planning (Phase 3A)

```bash
.venv/bin/pathf1ndar plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip"
.venv/bin/pathf1ndar plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip" --all
.venv/bin/pathf1ndar plan https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip" --completed review-1
.venv/bin/pathf1ndar plan --help
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
.venv/bin/pathf1ndar plan https://docs.celo.org/build/agents/8004 \
  --goal "Register an ERC-8004 agent on Celo" \
  --prepare-only --max-tokens 1024 \
  --request-file /tmp/pathf1ndar-cencori-prepare.json
```

For an unpaid quote, supply an **already installed, trusted** `@celo/buy@0.8.4`
executable. Replace the executable path below with its actual absolute path;
pathf1ndar does not install packages, invoke npx, create wallets, inspect keys,
or fund accounts. Each invocation requires a new output filename:

```bash
.venv/bin/pathf1ndar plan https://docs.celo.org/build/agents/8004 \
  --goal "Register an ERC-8004 agent on Celo" \
  --quote-only --max-tokens 1024 \
  --buy-executable /absolute/path/to/trusted/buy \
  --request-file /tmp/pathf1ndar-cencori-quote.json
.venv/bin/python -m json.tool /tmp/pathf1ndar-cencori-quote.json
sha256sum /tmp/pathf1ndar-cencori-quote.json
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
integration must verify those bytes and obtain approval separately. This phase
provides no approval storage, signing, payment path or inference-response parser.

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
.venv/bin/pathf1ndar research https://docs.python.org/3/tutorial/venv.html --goal "create virtual environment pip"
.venv/bin/pathf1ndar research https://docs.celo.org/ --goal "build agents"
.venv/bin/pathf1ndar research --help
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
inferred relevance separate for possible later inference; no LLM is integrated.

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
