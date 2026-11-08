# Submission evidence and readiness

Reviewed November 8, 2026 (this documentation revision); initial review
November 1, 2026. Links below are public URLs only. “Present” means evidence
exists in the reviewed checkout; it does not imply that a deployment or a
transaction was independently verified during this review. No private receipts
were opened or copied.

## Public evidence

| Item | Public reference | Status and verification boundary |
| --- | --- | --- |
| GitHub repository | [proteancarp/honeyguider](https://github.com/proteancarp/honeyguider) | Public repository resolves. The recording, loader and Streamlit showcase code are already published on main, confirmed through the GitHub connector. This does not verify the deployed app. Submission documentation changes remain uncommitted. |
| Hosted app | [Honeyguider Streamlit](https://honeyguider.streamlit.app/) | URL declared in agent metadata; hosted replay reported in project context. Web tool could not retrieve it. Manually verify availability, replay tab, nine tasks and deployment revision. |
| ERC-8004 Agent ID 10015 | [Public registration metadata](https://github.com/proteancarp/honeyguider/blob/main/agent.json), [Celo identity documentation](https://docs.celo.org/build/agents/8004) | Local agent.json declares ID 10015 and Celo registry 0x8004a169fb4a3325136eb29fa0ceb6d2e539a432. Obtain a verified registry/profile link, registration transaction, current agent URI and owner-to-entry wallet match. Metadata alone does not prove registration. |
| attempt-005 payment | [Celo mainnet transaction](https://celoscan.io/tx/0x4b22baa85c1c57753981163f14703b4c824be553a7ef734091fd808113d9d8d0) | Hash matches sanitized fixture and README; operator confirmation documented. Explorer retrieval unavailable in this review. Independently verify success, token transfer, amount, recipient and association with the call. Local settlement remains unknown. |
| Recorded completion | [Sanitized artifact](https://github.com/proteancarp/honeyguider/blob/main/src/honeyguider/recorded_inference.json), [loader](https://github.com/proteancarp/honeyguider/blob/main/src/honeyguider/recorded.py) | Published artifact and loader retrieved from main through the GitHub connector: nine tasks, six required/three optional; quoted and authorized 0.01 USDC, finish reason stop. No raw request or response envelope is needed. |
| Cencori / buy integration | [Cencori adapter](https://github.com/proteancarp/honeyguider/blob/main/src/honeyguider/cencori.py), [paid boundary](https://github.com/proteancarp/honeyguider/blob/main/src/honeyguider/paid.py), [official buy gateway guide](https://github.com/celo-org/buy-skill/blob/main/skills/use-api-gateway/SKILL.md) | Fixed Cencori endpoint, tested buy 0.8.4 interface, exact-body quotes and explicitly capped interactive payment in source. Does not establish compatibility with newer buy releases. |
| Automated tests | [tests directory](https://github.com/proteancarp/honeyguider/tree/main/tests), [project configuration](https://github.com/proteancarp/honeyguider/blob/main/pyproject.toml), [CI workflows](https://github.com/proteancarp/honeyguider/tree/main/.github/workflows) | pytest covers research safety, plan validation, offline CLI/state, quotes/payment safeguards, tracking and recorded/browser isolation. Tests use fixtures/mocks; no live inference, settlement or adoption is established by them. UI tests may skip without Streamlit. |

## Official requirements review

Source: [official Loops House event page](https://www.loops.house/agents-on-open-rails),
reviewed 2026-11-01 (timeline, rules, identity, attribution and Build with buy FAQs).

Confirmed requirements and judging statements:

- Deadline: November 9, 09:00 GMT, for registration and submission.
- Public GitHub repository must remain accessible at judging; code must be written during the hackathon.
- Register ERC-8004 identity and add the agent wallet to the entry before the deadline.
- Mainnet activity counts; sponsored gas is not builder contribution.
- Build with buy assesses the problem, external paid-service integration and resulting demand. Provide service names and payment proof. Independent users are a qualifier.
- The Build with buy FAQ explicitly exempts this track from attribution tags, despite the general tagging rule. Separately, x402 guidance requests a PayTo address because x402 does not support tags.

Given the FAQ exemption, whether the attribution-tagging rule applies to this
entry remains unresolved; the judging description's tagged-wallet and x402
reporting language does not resolve it. Confirm the applicable reporting fields
with organizers, and do not infer eligibility from either statement.

Outstanding: confirm enrollment, wallet/identity linkage, code dates, payment
qualification and the applicable PayTo submission fields. No independent-user
evidence is available; do not claim qualification. Confirm ambiguous entry fields
and new-user assessment with organizers; do not infer eligibility from one call.

### Wallet roles and x402 reporting

Keep these roles separate when preparing evidence:

| Role | Meaning in this submission | Outstanding verification |
| --- | --- | --- |
| Agent wallet | Honeyguider identity/entry wallet; distinguish the ERC-8004 owner from the registered agentWallet if they differ. | Verify registry values, ownership and the wallet linked to the entry. |
| Payment-sending wallet | The wallet authorizing payment through the operator's external buy setup. | Verify the sender/authorizer from public payment evidence and its relationship to the agent wallet; do not assume they coincide. |
| External service recipient | The pay_to recipient quoted for the external Cencori service through buy. | Verify the recipient against public settlement evidence; the quote alone does not establish ownership. |

The provider's `pay_to` is not established as a Honeyguider-controlled address
and must not be presented as Honeyguider's own wallet. Honeyguider consumes the
service; its metadata advertises no x402 payment-accepting endpoint. The event
page's request for “your PayTo” leaves the consumer-side entry fields unclear.
Ask organizers whether they want the external recipient as payment evidence,
the sending wallet, or both, and in which fields. Do not substitute the external
recipient into the agent-wallet field.

## Recommendations and evidence gaps

These are preparation recommendations, not additional confirmed event rules:

- Manually inspect hosted replay, registry ownership/URI and explorer evidence;
  record the verification date and public links. No additional paid call is
  required to make the video.
- Confirm the external x402 recipient from public evidence and label its role.
  Resolve the consumer-side PayTo reporting fields with organizers before entry;
  preserve the distinction from Honeyguider's identity and payment-sending wallets.
- Gather genuine, consented developer feedback and independent-user evidence
  under the organizers' definition. Do not create or fund wallets to simulate
  independent demand. No adoption or performance measurements are claimed.
- Finish and host the 2–3 minute demo video. Confirm form-specific fields,
  media requirements and any entry-specific instructions in the enrollment
  portal; this review covered the public event page, not a submitted form.
- Publish the submission documentation after independent review. The sanitized
  showcase is already on main; check the deployed revision separately.
- Complete independent CLI usability review before showcasing the redesign.
  The existing CLI can demonstrate offline practice in the meantime.
- Attach the actual local test outcome to the review; separately inspect public
  CI status. Neither implies live service or blockchain verification.

## Local verification outcome

On 2026-11-01, `.venv/bin/python -m pytest -q` completed with **515 passed**
in 7.37 seconds. Relative documentation links resolved and `git diff --check`
passed. Public GitHub, Celo documentation and the buy guide were retrievable;
app/explorer/profile verification was unavailable through the web tool.
During the final documentation revision, the GitHub connector retrieved the
recording, loader and showcase code from main. The deployed Streamlit app could
not be retrieved and remains unverified. No tests were rerun for this
wording-only revision: this 2026-11-01 result is historical evidence from the
initial preparation run, not the final test result for this revision. Relative links
and `git diff --check` were checked again.

The added material was reviewed for private data: it uses the existing sanitized
recording and public metadata only. No implementation or private receipt changes
are included.
