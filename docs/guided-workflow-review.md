# Guided workflow review

Record as of the Phase 7 release; all accepted phases are committed on feat/honeyguider-journey at HEAD 3199449.

## Scope and architecture

Work stayed in the existing worktree on `feat/honeyguider-journey`. The branch
and clean working tree were verified before edits.
Change history: Phases 1-3 revisions and the Phase 4-6 records are committed on feat/honeyguider-journey (implementation dae3d07; documentation 2ca387e and 3199449).

The welcome module remains a Typer/Rich navigation layer. It calls the existing
`cli.done`, `track_cli.done`, and `cli.check` handlers. There is no second progress
system: demo state validation, tool prerequisites, tracking validation, private
storage boundaries, and append-only tracking publication remain in their existing
modules. Completion handlers reread state before writing. The menu catches
rejected completion to allow recovery, presents plain-language feedback, and
leaves explicit command behavior unchanged.

The current step and action list render on entry and after completion or checks.
Instructions and citations are on demand. Read-only views and declined
confirmations return to a compact action prompt. A roadmap exposes all steps,
readiness and blockers; users can inspect any step by ID. If no task is ready,
the next pending task remains visible with blockers. Imported plans preserve
required-work prioritization and identify optional work.

Opening the application has no retrieval, tool checks, payment, or state writes.
Starting a new sample explicitly initializes its state; reopening it only reads.
Completion and tool checks each require confirmation, defaulting to no.
Documentation retrieval has its own network confirmation. Paid inference,
transactions, wallets, receipt handling, Streamlit, state formats, and the legacy
state directory were not changed.

## Interaction

1. Run `honeyguider`; read its documentation-to-development-plan purpose.
2. Choose **3**, sample walkthrough.
3. Choose **2**, instructions and source references for `scope`.
4. Choose **1**, then **y**, to record self-reported completion.
5. See `workspace` immediately, including missing saved tool checks.
6. Choose **3** for the roadmap and blockers, or **5**, then **y**, to run
   the existing read-only local version checks.
7. Inspect and complete subsequent steps using the same actions.
8. Choose **0**, then **0**, to return and exit.
9. Reopen and choose **2**, then **1**, to continue the saved sample.

Already imported AI plans use **2**, then **2**, then their tracking directory.
They support the same inspect/confirm/complete flow and append revisions through
the existing tracking handler. This menu does not import receipts.

## Automated validation

Used the existing `/tmp/honeyguider-cli-usability-venv` environment; no dependency
installation was needed.

- Relevant suite: `python -m pytest -q tests/test_welcome.py tests/test_tracking.py tests/test_mvp.py`
  — **98 passed**, 2.18 seconds.
- Full suite: `python -m pytest -q` — **524 passed**, 7.65 seconds.
- `git diff --check` passed.

Tests cover the welcome choices, on-demand sources, confirmation refusal and EOF,
completion and advancement, persistence across invocation, blocked task attempts,
explicit local checks, invalid input and inspection cancellation, completed-plan
inspection, tracked completion with unchanged earlier revisions and receipts,
noninteractive behavior and explicit command compatibility. Offline fixtures
forbid network, subprocess, wallet access and payment except that the explicit
checks test substitutes deterministic tool results. Retrieval tests use fake
reports after explicit consent.

The UAT regression opens the sample, reads scope and its citation, completes it
using an action and confirmation, sees workspace and its blockers, exits, and
resumes. Another test types the old standalone command at the action prompt and
verifies recovery guidance followed by successful in-menu completion.

## Actual terminal smoke test

Used a real PTY with an 80-column terminal and isolated files under
`/tmp/honeyguider-guided-smoke-NEsqAZ`, invoking the local module with the existing
virtual environment. No fixture progress was written into the repository.

Actual sequence: opened welcome; selected sample; inspected scope and its source;
refused completion; confirmed completion; saw workspace automatically; inspected
the roadmap; tried blocked workspace completion; explicitly approved local tool
checks; inspected and confirmed workspace, prototype, validate and submission;
viewed the 5/5 roadmap; inspected scope again; returned and exited. A second
process resumed through Continue → Sample and retained 5/5 progress and details.

Local checks observed Python 3.12.3, Git 2.43.0, Node v24.22.1, npm 11.19.1.
Text and the results table wrapped within the terminal width. Instructions did
not reprint the current task and full menu. The initial smoke test exposed raw
command-style blocker labels; menu completion feedback was refined and a final
fresh-state PTY pass checked scope completion, advancement and blocked workspace
rejection with the revised prompts and plain-language feedback.

This was an interface smoke test: completion was recorded as test self-reports,
not proof that the practice project's development tasks were performed.

## Limitations and follow-up

- Tested in a PTY, not the Kitty application itself; no cursor control, alternate
  screen, or terminal-specific escape sequences were added.
- Long instructions and roadmaps use terminal scrollback; this is not a full TUI.
- Users enter an imported plan's directory and roadmap IDs themselves.
- Completion remains self-reported; source correctness is not verified.
- Missing tools require manual installation; the menu only checks versions.
- Documentation demonstration plans remain in memory and are not saved as AI
  tracking plans. Live AI generation remains outside the guided menu.
- Separate follow-up: rename/migrate the legacy `.pathf1ndar` state directory.
  No directory rename or migration is part of this branch.

## Files

- `src/honeyguider/welcome.py`: guided navigation and confirmed existing handlers.
- `tests/test_welcome.py`: revised navigation coverage and UAT regressions.
- `tests/test_tracking.py`: imported-plan completion and history preservation.
- `docs/cli-usage.md`: revised interaction and recovery documentation.
- `docs/guided-workflow-review.md`: decisions, validation, smoke findings and limits.

## Final independent-review corrections (guided-navigation stage, Phases 1-3)

Completion is now offered only for ready, unfinished steps, including after
roadmap selection. Blocked steps explain prerequisites and required local checks;
completed steps explain that they are already complete. Both retain instructions
and roadmap inspection, and the sample retains local checks. Eligibility is
re-read before confirmation; existing handlers still perform authoritative
validation before writing.

Sample links are labeled offline references, while imported AI-plan links are
labeled citations. The menu explains that imported citations refer to evidence
retrieved for the original plan and that reopening does not re-fetch sources.

Completion errors no longer assert that nothing was recorded. The menu warns
that saved progress may have changed, reads back through existing validated
readers, and reports the currently visible completion state without asserting
durability. If read-back fails, navigation stops with an uncertainty warning.
There is no automatic write retry. Tracking storage, its append-only publication,
state formats, payment code and existing command error boundaries are unchanged.

Final offline validation:

- Focused welcome, tracking and MVP suites: **105 passed**, 2.42 seconds.
- Full suite: **531 passed**, 7.82 seconds.
- `git diff --check` passed.

New regressions cover unavailable completion actions for prerequisite-blocked,
tool-blocked and completed tasks, source terminology, demo replacement followed
by a failure, tracking failures before publication and after publication during
directory sync, and unreadable state after publication. Late-failure tests verify
that a published revision remains visible, earlier history and receipts remain
unchanged, and only one write attempt occurs. The terminal smoke sequence above
records the original redesign run; these final corrections were validated with
the focused offline regressions and full suite.

## Phase 4-6 chronology (final)

The sections above record the guided-navigation work (Phases 1-3) on
`feat/guided-cli-workflow`. Phases 4-6 continued on `feat/honeyguider-journey`
and kept the same append-only tracking and handler boundaries. No progress system,
state format or explicit command behavior was replaced.

### Phase 4 — attempt lock and settlement classification

- `journey.acquire_attempt_lock` holds a content-keyed advisory lock for one paid
  attempt. Contention fails fast, nothing is paid, and the lock file is never
  unlinked. The digest is validated before any path is built.
- `fcntl` is imported only on the paid-attempt path, so the module stays
  importable on non-POSIX platforms; where locking is unavailable it raises a
  clear `JourneyError`.
- `journey.attempt_state` classifies one receipt directory from bounded, private
  artifacts: S0 pre-approval, S1 approval-not-launched, S2
  launched-outcome-unavailable, S3 outcome-recorded-unconfirmed, S4
  caller-asserted provider-confirmed, plus `blocked` for contradictory evidence.
- `claim_confirmed_by_provider` is caller-supplied and never set by the product.
- The journey→paid TOCTOU window is disclosed: `paid.infer` re-reads the request,
  and the success path re-verifies the digest after the attempt, failing closed.
- Coverage: the canonical journey suite contains 146 tests, including lock
  contention, content-key separation, stale diagnostics, state transitions and
  the post-attempt identity recheck.

### Phase 5 — fingerprint and idempotent import

- `journey.record_fingerprint` hashes bounded private artifacts deterministically;
  absent artifacts hash as `None`, and presence must match the classified state.
- `journey.import_outcome` imports only a validation-valid S3 outcome,
  idempotently. It recognizes an existing record, preserves an interrupted
  destination, requires explicit consent for a custom tracking root, and
  re-verifies evidence before and after writing.
- `provider_confirmed` is not importable; UNKNOWN is never promoted.
- `journey.correlate_claim` treats a single hash match as match evidence only.
- Coverage: tracking (56 tests) and journey coverage of fingerprint stability,
  duplicate recognition, custom-root consent, conflict preservation and
  post-import re-verification.

### Phase 6 — guided wiring

- `welcome.py` composes the validated handlers into the main menu: **1** Explore
  documentation, **2** Continue a saved plan (including **3** List existing
  tracked plans), **3** Try a sample walkthrough, **4** Help and advanced
  commands, **5** Wallet & payments, **6** Create a tracked plan, **0** Exit.
- **5 Wallet & payments** offers identity/readiness, balances, funding
  instructions, local payment history, opt-in reconciliation and proposal-only
  setup. Setup prints `buy setup --name <alias>` and never executes it.
- **6 Create a tracked plan** runs research consent → preserved request →
  readiness gate → token and receipt path → `journey.infer_with_receipt` →
  `journey.import_outcome` → tracking session, with UNKNOWN-settlement and
  no-provider-claim lines printed before the session opens.
- `journey.list_tracked_plans` backs **2 → 3** with read-only, bounded summaries;
  settlement is `unknown` and never `confirmed`.
- Coverage: welcome 81 tests, paid 234, wallet 75, journey 146, tracking 56.

### Test-count chronology

| Stage | Focused | Canonical full suite |
| --- | --- | --- |
| Guided navigation (Phases 1-3) final | 105 | 531 |
| Phase 6 final | — | **819 passed** (no failures or skips) |

Intermediate per-phase totals for Phases 4 and 5 were not recorded separately;
this document reports the endpoints rather than inventing intermediate numbers.
The final per-file counts are journey 146, welcome 81, paid 234, wallet 75,
tracking 56, plus the MVP, Cencori, planning, recorded and research suites.
These are offline fixtures and doubles; they do not establish live inference,
settlement or adoption.

### Safety invariants carried forward

- Opening the menu stays offline; retrieval, reconciliation and payment each
  need their own explicit consent, defaulting to no.
- Paid inference is one attempt with a fresh quote, exact cap and session
  approval code; there is no automatic retry.
- The request is preserved before the readiness gate; platform or wallet failure
  returns without charging.
- Local settlement is UNKNOWN by default; import, correlation and tracking never
  claim provider-confirmed settlement.
- No key material is read or stored; setup is a printed proposal only.
- Tracking publication remains append-only, private and validated.

### Platform claim

Linux is verified; macOS is unverified; POSIX-only locking; no native Windows
locking. The paid journey requires a POSIX platform, and the CLI reports a clear
error where advisory locking is unavailable.

### Remaining deferred items

- No independent-user evidence, adoption or performance measurement.
- A new live guided demonstration requires an owner-authorized, funded operator
  run; it is not part of the recorded evidence.
- macOS and Windows paid journeys remain unverified and unimplemented
  respectively.
- ERC-8004 registry ownership, deployed-app freshness and payment attribution
  remain verification items tracked in the evidence checklist.
- The legacy `.pathf1ndar` state directory rename/migration remains out of scope.
