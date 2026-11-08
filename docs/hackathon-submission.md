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

## Distinctive value and limits

Honeyguider connects retrieved evidence, required/optional dependencies, an
explicit next action, and human control over paid inference. The same validation
boundary handles deterministic and AI plans. A read-only replay makes the paid
result inspectable without asking visitors to pay.

This is an early MVP. Keyword matching and bounded HTML retrieval can miss context;
JavaScript-only pages and some redirects fail. Citations establish membership in
retrieved inputs, not support for every recommendation. Completion is self-reported;
the agent does not implement or verify development tasks. The earlier paid attempt
documented in the README returned an incomplete response and failed validation.
No independent users, qualifying demand, benchmark improvements or repeat usage
have been established. The CLI redesign is independent and is not represented
here as completed. Deployment freshness, identity verification, payment attribution
and final submission requirements remain in the [evidence checklist](submission-evidence.md).
