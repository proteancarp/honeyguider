# Honeyguider demo script

Target: about 3 minutes, in two clearly labelled acts.

- **Act A — Recorded inference showcase.** The hosted Streamlit replay of the
  completed `attempt-005`. This is a replay of saved evidence: no new retrieval,
  inference or payment runs. Keep “Recorded inference — no new payment” visible.
- **Act B — Guided CLI journey rehearsal.** The Phase 6 terminal menu, rehearsed
  offline with test doubles. A real paid run needs an operator-authorized funded
  wallet, is not part of this recording, and must not be implied by it.

Hard rules for the whole recording:

- Use only public pages and the sanitized shipped recording. Never open private
  receipts, wallet keys or session approval codes.
- Never describe transaction-hash correlation or a hosted replay as authenticated
  provider settlement. Local settlement stays **unknown**.
- Do not present the guided rehearsal as a live paid attempt. The recorded
  onchain result is `attempt-005`; the rehearsal is UI and control-flow evidence.

## Act A — Recorded inference showcase (offline replay)

Source: the **Recorded AI Inference** tab at
<https://honeyguider.streamlit.app/>, backed by
[`src/honeyguider/recorded_inference.json`](../src/honeyguider/recorded_inference.json).

| Time | Screen/action | Narration |
| --- | --- | --- |
| 0:00–0:20 | Celo documentation, then Honeyguider title | “Registering a service means finding the right instructions, their prerequisites, and the order to follow. Across fragmented documentation, it is easy to lose the next step. Honeyguider turns retrieved evidence into a source-linked development plan.” |
| 0:20–0:40 | Recorded AI Inference tab; show the replay notice and goal, then follow the documentation source to the registration section | “Our example goal was to register a service. Honeyguider retrieved Celo documentation as input evidence. This link lets us inspect that source today; it is not the original retrieval capture. The showcase replays the completed inference. No new retrieval, inference or payment runs in this tab.” |
| 0:40–1:05 | Return to the recorded tab; show model, amount, approval explanation and transaction link | “Cencori generated this plan; buy supplied the payment transport. The recorded quote and authorization were 0.01 USDC on Celo Mainnet, chain 42220. A person reviewed the request and fresh quote, set the exact cap, and approved one attempt, with no automatic retries. The operator confirmed the linked transaction on Celoscan; Honeyguider's local settlement record remains unknown.” |
| 1:05–1:30 | Nine-task roadmap; expand `author-registration-file` and `host-registration-file` details | “The output passed validation for task structure, citation membership and an acyclic dependency graph. There are six required tasks and three optional ones. Hosting depends on authoring the file; registration depends on hosting. These checks validate the plan's structure. We still review the advice against the documentation.” |
| 1:30–1:50 | Return to the AI-generated next action and its citation | “With nothing completed, the next actionable step is to author the registration file. Honeyguider brings the action and its source together, while later tasks remain blocked by prerequisites. This recorded roadmap is read-only; we are not completing the AI plan here.” |
| 1:50–2:05 | Repository, then back to the recorded action | “The shipped artifact contains the nine tasks, never a copied response envelope. The recording loader validates metadata, graph, citations and a reviewed digest. That proves artifact consistency, not receipt authorship, semantic correctness or onchain settlement.” |

Evidence references for Act A:

- Goal “register a service”, source <https://docs.celo.org/build/agents/8004>.
- Model `maximo-atlas-1.3`, 4096-token output limit, finish reason `stop`,
  1639 prompt tokens and 1206 completion tokens (2845 total).
- Quoted and authorized 0.01 USDC on Celo Mainnet (chain 42220).
- Public transaction:
  <https://celoscan.io/tx/0x4b22baa85c1c57753981163f14703b4c824be553a7ef734091fd808113d9d8d0>.
  The operator independently confirmed it on Celoscan; local settlement remains
  **unknown**.
- Nine tasks, six required and three optional.

If Celoscan is unavailable, show the public transaction URL and disclose that live
explorer verification is unavailable. Do not imply a new verification occurred.
The source-page visit is live browsing of public documentation, not a replay of
the retrieved passages.

## Act B — Guided CLI journey rehearsal (offline)

Act B demonstrates the Phase 6 menu topography and the free consent/readiness
gates. It does **not** perform a live paid attempt. The paid branch is represented
by the recorded result in Act A and by the focused offline regressions below.

Prepare an isolated state path and start from the repository root:

```bash
honeyguider --state-file /tmp/honeyguider-demo.json
```

`honeyguider` with no arguments requires an interactive terminal. Use a fresh
temporary state path so the rehearsal is reproducible; choose another filename if
it already exists.

| Step | Input | Expected output |
| --- | --- | --- |
| 1 | Start `honeyguider` | Title and purpose, then the main menu: **1** Explore documentation, **2** Continue a saved plan, **3** Try a sample walkthrough, **4** Help and advanced commands, **5** Wallet & payments, **6** Create a tracked plan, **0** Exit. Opening the menu writes nothing. |
| 2 | `5` | “No payment is involved in this step.” Wallet sub-menu: **1** identity/readiness, **2** balances, **3** funding instructions, **4** payment history, **5** reconciliation, **6** setup (proposal only), **0** Back. |
| 3 | `6`, then accept the default alias `honeyguider` | Setup text explains that the key goes into the OS keychain and Honeyguider never sees or stores it. It prints `buy setup --name honeyguider` and says to run it in your own terminal, then choose **1** to verify. The menu does not execute it, and the wallet sub-menu returns to the main menu. |
| 4 | `6` (main menu) | “Create a tracked plan” description, the paid-step warning, and “No payment is involved in this step” for retrieval, preparation and readiness. Prompts for the documentation HTTPS URL and development goal. |
| 5 | Enter a public HTTPS URL and a goal, then answer the retrieval consent `n` | “Retrieval cancelled. Nothing was retrieved; no files were created.” No request is written, nothing is charged, and the flow returns to the main menu. |
| 6 | Run the offline control command below (not a menu input) | The doubles exercise the full research → preserved request → readiness → quote → cap → approval-code → lock → import path without a network call, wallet or payment. |
| 7 | `2`, then `3` | “No tracked plans found.” or a numbered list of local plans with completed/task counts and `attempt/settlement: unknown`. Selecting a listed number opens that plan; a path can be entered instead. Listing creates nothing. |

What a full live run would show, and why it is not in this recording:

1. Readiness checks the named buy account and Celo Mainnet identity; a Sepolia or
   unreadable identity returns without charging and preserves the request.
2. After an explicit proceed confirmation, the flow asks for a payment token
   (default USDC; USDC, USDT and USAT are supported) and a new receipt directory.
   A fresh quote then appears, followed by a prompt for an exact cap in
   human-readable token units.
3. A session approval code is displayed. Typing it exactly authorizes one locked
   attempt; an incorrect, stale or missing code launches no payment.
4. The attempt is content-keyed by the request digest and never retries
   automatically. Interruption or failure leaves settlement **UNKNOWN**.
5. A validated outcome is imported idempotently into `.honeyguider/track`. A
   custom tracking root asks for separate consent.
6. The tracking session opens only after printing that the plan is validated for
   inference output but **payment settlement remains UNKNOWN**, and that an
   imported record does not prove a provider payment settled.

This branch requires an operator-authorized, funded Celo Mainnet wallet and a
trusted buy 0.8.4 CLI on a POSIX host (Linux verified; macOS unverified; no
native Windows locking). Do not perform it for this recording.

### Offline controls used for the rehearsal

The guided journey is exercised with doubles so no network, wallet or payment is
touched:

```bash
.venv/bin/python -m pytest -q tests/test_welcome.py -k guided_journey
.venv/bin/python -m pytest -q tests/test_journey.py
```

The first command scripts the same menu choices shown above against stubbed
`journey.prepare`, `journey.infer_with_receipt`, `journey.import_outcome`, a
stubbed wallet readiness result and a stubbed tracking session. It checks that the
paid-step warning precedes the validated plan, that the paid call receives the
expected account and payer, that the UNKNOWN-settlement and no-provider-claim
lines print before the session opens, and that no output says “provider
confirmed”. The second command covers the lock, attempt-state classification,
fingerprint and idempotent-import boundaries without a live payment.

These are offline rehearsal controls, not evidence that a live payment settled.

## Transition and close

| Time | Screen/action | Narration |
| --- | --- | --- |
| 2:05–2:35 | Local terminal, Act B steps 1–5 and 7 | “The same guided menu keeps retrieval, wallet inspection and the paid step behind separate consent. Wallet views are read-only; setup is printed for you to run yourself; declining retrieval creates nothing. Existing tracked plans are listed with settlement left explicitly unknown.” |
| 2:35–3:00 | Return to the recorded action/source, then the repository | “From evidence to a validated plan, an actionable step, and progress tracking: Honeyguider helps developers organize integration work. Developers implement and verify the tasks themselves. This is a working MVP, with no measured performance improvement or independent-user evidence yet. The repository documents the architecture, tests and remaining verification gaps.” |

Do not imply the Act B rehearsal tracks the recorded AI plan. Act A and Act B use
different artifacts: Act A replays `attempt-005`; Act B shows the menu and its
offline controls. The final video URL remains a submission item; this script is
not a finished video.
