# Honeyguider — Build with buy submission brief

## Problem and audience

Developers learning an unfamiliar API must assemble instructions from scattered
pages, distinguish prerequisites from optional work, and decide what to do next.
Honeyguider targets individual developers and hackathon builders working through
technical integrations. The demonstrated use case is planning ERC-8004 service
registration from Celo documentation. Reduced navigation effort is the intended
benefit; no measured time savings or adoption is claimed.

## Product and architecture

Honeyguider retrieves relevant documentation evidence, constructs a dependency
plan, and selects an actionable next step. Developers review and implement the
recommendations themselves. The default planner is an authored deterministic
scaffold; optional Cencori inference generates a plan from retrieved evidence.

The Python 3.11+ core uses Typer/Rich for the CLI, HTTPX/BeautifulSoup for bounded
public HTTPS research, and local JSON for progress. There is no database or
heavyweight agent framework. Components are intentionally small:

- [research.py](../src/honeyguider/research.py): retrieval, public-IP/DNS and same-host restrictions, extraction and evidence limits.
- [planning.py](../src/honeyguider/planning.py): provider protocol, strict task schema, citation membership, acyclic graph validation and prerequisite-aware selection.
- [demo.py](../src/honeyguider/demo.py): the authored offline Celo practice scenario tasks.
- [model.py](../src/honeyguider/model.py), [checks.py](../src/honeyguider/checks.py), [state.py](../src/honeyguider/state.py): task modelling with prerequisite blockers and next-step selection, bounded tool version checks without a shell, and versioned JSON progress.
- [cencori.py](../src/honeyguider/cencori.py) and [paid.py](../src/honeyguider/paid.py): request preparation, quotes and interactive paid inference.
- [tracking.py](../src/honeyguider/tracking.py): opt-in validated receipt import and local plan tracking.
- [journey.py](../src/honeyguider/journey.py): artifact-driven orchestration, the content-keyed attempt lock, attempt-state classification, fingerprinting, idempotent import and tracked-plan listing.
- [welcome.py](../src/honeyguider/welcome.py): the guided terminal menu that composes the validated handlers.
- [wallet.py](../src/honeyguider/wallet.py): read-only wallet identity/readiness, balances, funding guidance, local payment history and proposal-only setup.
- [recorded.py](../src/honeyguider/recorded.py) and the [Streamlit presentation](../browser_demo/streamlit_app.py): sanitized, pinned replay plus a separate deterministic playground. Streamlit is optional, outside the core CLI dependency set.

## Paid workflow and safeguards

Honeyguider prepares an exact request body from retrieved evidence. An
explicitly selected, already installed buy 0.8.4 executable obtains a quote from the fixed
[Cencori gateway endpoint](https://gateway.usebuy.ai/cencori/v1/chat/completions).
buy supplies the payment transport to an external inference service; Cencori
supplies the completion used to build the plan. This paid call serves the
planning workflow rather than an unrelated transaction demonstration.

Before one paid attempt, the CLI requires interactive input/output, validates
the saved request, displays its digest and a fresh quote, requires a token cap
matching a quoted offer, and requests a randomly generated session approval code.
Before launch, the CLI rejects a quote if more than five minutes have elapsed
since quote validation. This is a quote-freshness check, not a separate expiration
timer for the session approval code. It also rechecks request bytes before
launching buy with the cap. There is no unattended approval or automatic retry.
Honeyguider does not read wallet keys; signing is delegated to the operator's external buy
setup. It does not install buy, fund wallets or execute generated tasks.
Payment can settle even when completion validation fails. Local settlement is
explicitly unknown, and validation must not be described as a settlement proof.

The guided **6 Create a tracked plan** flow runs the same boundary behind a
readiness gate. It preserves the request before asking for payment, binds the
attempt to the named account and expected payer, and holds a content-keyed
advisory lock for the attempt. Import is idempotent and recognizes an existing
tracking record rather than duplicating it. The platform claim is deliberate:
Linux is verified; macOS is unverified; native Windows locking is not implemented.
The paid journey requires a POSIX platform and reports a clear error where
advisory locking is unavailable. Transaction-hash correlation, when requested,
is match evidence only; it never authenticates provider settlement.

## Identity and recorded result

The checked-in [agent metadata](../agent.json) declares ERC-8004 Agent ID **10015**
on Celo (42220), registry
`0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`. It lists the public app and repository
and sets `x402Support: false`: Honeyguider consumes a paid service; the metadata
does not advertise a payment-accepting endpoint. Registry ownership and the
current agent URI still require independent public verification.

The [public recording](../src/honeyguider/recorded_inference.json), identified as
`attempt-005` in the existing README, records goal “register a service”, model
`maximo-atlas-1.3`, a 4096-token output limit, and finish reason `stop`.
It contains nine tasks (six required, three optional), 1639 prompt tokens and
1206 completion tokens. Quoted and authorized amount: 0.01 USDC on Celo mainnet.
The [public transaction](https://celoscan.io/tx/0x4b22baa85c1c57753981163f14703b4c824be553a7ef734091fd808113d9d8d0)
was independently confirmed by the operator, as documented in the README.
This review could not retrieve the explorer page; local settlement stays unknown.

The [hosted showcase](https://honeyguider.streamlit.app/) reads a sanitized shipped
artifact. It runs no live inference or payment. The recording loader validates
metadata, graph, citations and a reviewed digest; those checks establish artifact
consistency, not authorship, semantic correctness or onchain settlement.

## Final implementation summary (Phase 1-6)

The product now exists in the following implemented form:

- **Phase 1 — offline MVP:** `explore`, `check`, `next`, `done`, `status`,
  read-only tool version checks without a shell, and validated local JSON.
- **Phase 2 — research and deterministic planning:** bounded public HTTPS
  retrieval with public-IP/DNS and same-host controls, explicit extraction
  limits, a strict provider schema and dependency-graph validation.
- **Phase 3 — paid request boundary:** exact request preparation and
  preservation, unpaid quotes through a trusted buy 0.8.4, and explicit
  one-attempt inference with a fresh quote, exact cap, session approval code,
  private receipts and unknown settlement.
- **Phase 4 — execution lock and classification:** a content-keyed advisory lock
  around one paid attempt, account binding and expected-payer checks, S0–S4
  attempt-state classification, and UNKNOWN as the default.
- **Phase 5 — fingerprint and idempotent import:** a deterministic receipt
  fingerprint, duplicate recognition, custom-root consent, and fail-closed
  import that never promotes settlement.
- **Phase 6 — guided wiring:** the validated handlers composed into the terminal
  menu, read-only wallet views and proposal-only setup, `6 Create a tracked
  plan`, and `2 → 3` tracked-plan listing.

Recorded acceptance for the canonical suite: the guided-navigation stage ended at
**105 focused / 531 full**; the final Phase 6 run recorded **819 passed** with no
failures or skips (journey 146, welcome 81, paid 234, wallet 75, tracking 56,
plus the remaining MVP, Cencori, planning, recorded and research suites). Tests
use offline fixtures and doubles; they do not establish live inference,
settlement or adoption. This documentation revision did not rerun the suite.

Submission-channel notes:

- The sanitized showcase and recording loader are already published on `main`.
  The submission documentation changes in this revision are committed in this release.
- Installation is from GitHub with pipx or uv; no PyPI release is claimed.
- The deployed Streamlit revision and the video URL remain submission items to
  verify separately.
- A new live guided demonstration would require an owner-authorized, funded
  operator run; it is not part of the recorded evidence.

Evidence checklist: [submission-evidence.md](submission-evidence.md) records the
public references, verification boundaries, platform claim and remaining gaps.
The presenter flow is in [demo-script.md](demo-script.md).

Owner actions before submission:

- Verify ERC-8004 registration, registry ownership, current agent URI and the
  wallet linked to the entry.
- Gather genuine, consented independent-user evidence under the organizers'
  definition; none exists yet, and simulated demand must not be presented.
- Confirm with organizers whether the attribution-tag exemption applies to this
  entry; the recorded FAQ text is ambiguous and no attribution data is invented
  here.

## Distinctive value and limits

Honeyguider connects retrieved evidence, required/optional dependencies, an
explicit next action, and human control over paid inference. The same validation
boundary handles deterministic and AI plans. A read-only replay makes the paid
result inspectable without asking visitors to pay.

This is a working MVP. Keyword matching and bounded HTML retrieval can miss
context; JavaScript-only pages and some redirects fail. Citations establish
membership in retrieved inputs, not support for every recommendation. Completion
is self-reported; the agent does not implement or verify development tasks. The
earlier paid attempt documented in the README returned an incomplete response and
failed validation. No independent users, qualifying demand, benchmark
improvements or repeat usage have been established. The guided CLI journey
(Phase 6) is implemented and documented; its paid branch still requires an
operator-authorized live run and is not independent-user evidence. Deployment
freshness, identity verification, payment attribution and final submission
requirements remain in the [evidence checklist](submission-evidence.md).
