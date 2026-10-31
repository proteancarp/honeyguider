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
AI planning, automatic implementation, and on-chain operations remain outside
this MVP.

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
excerpts or followed links. Links rank by overlap then URL; sections rank by
overlap with document order breaking ties. There are no AI summaries or
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
