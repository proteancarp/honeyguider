# Honeyguider demo script

Target: 2 minutes 40 seconds. Keep “Recorded inference — no new payment” visible
during the showcase. Use only public pages and the sanitized shipped recording.
Never open private receipts or execute `infer` for this recording.

| Time | Screen/action | Narration |
| --- | --- | --- |
| 0:00–0:20 | Celo documentation, then Honeyguider title | “Registering a service means finding the right instructions, their prerequisites, and the order to follow. Across fragmented documentation, it is easy to lose the next step. Honeyguider turns retrieved evidence into a source-linked development plan.” |
| 0:20–0:40 | Recorded AI Inference tab; show replay notice and goal, then follow Documentation source to the registration section | “Our example goal was to register a service. Honeyguider retrieved Celo documentation as input evidence. This link lets us inspect that source today; it is not the original retrieval capture. The showcase replays the completed inference. No new retrieval, inference or payment runs in this tab.” |
| 0:40–1:05 | Return to recorded tab; show model, amount, approval explanation and transaction link | “Cencori generated this plan; buy supplied the payment transport. The recorded quote and authorization were 0.01 USDC on Celo mainnet. A person reviewed the request and fresh quote, set the exact cap, and approved one attempt, with no automatic retries. The operator confirmed the linked transaction on Celoscan; local settlement remains unknown.” |
| 1:05–1:30 | Nine-task roadmap; expand author-registration-file and host-registration-file details | “The output passed validation for task structure, citation membership and an acyclic dependency graph. There are six required tasks and three optional ones. Hosting depends on authoring the file; registration depends on hosting. These checks validate the plan's structure. We still review the advice against the documentation.” |
| 1:30–1:50 | Return to AI-generated next action and its citation | “With nothing completed, the next actionable step is to author the registration file. Honeyguider brings the action and its source together, while later tasks remain blocked by prerequisites. This recorded roadmap is read-only; we are not completing the AI plan here.” |
| 1:50–2:20 | Local terminal, offline commands below, when the CLI is ready; overlay “Separate deterministic practice plan” | “To show progress tracking without private receipts or another payment, we switch to a separate deterministic practice plan. Explore loads it, next shows scope, and done records self-reported completion. Check inspects local tools; next and status then show what is available or blocked. These are different tasks from the recorded AI plan.” |
| 2:20–2:40 | Return to recorded action/source, then repository | “From evidence to a validated plan, an actionable step, and progress tracking: Honeyguider helps developers organize integration work. Developers implement and verify the tasks themselves. This is an early MVP, with no measured performance improvement or independent-user evidence yet. The repository documents the architecture, tests and remaining verification gaps.” |

Use a fresh temporary state path for a reproducible offline terminal segment:

```bash
honeyguider --state-file /tmp/honeyguider-video-demo.json explore --demo
honeyguider --state-file /tmp/honeyguider-video-demo.json next
honeyguider --state-file /tmp/honeyguider-video-demo.json done scope
honeyguider --state-file /tmp/honeyguider-video-demo.json check
honeyguider --state-file /tmp/honeyguider-video-demo.json next
honeyguider --state-file /tmp/honeyguider-video-demo.json status
```

Choose an unused filename if it already exists. `check` can exit with status 1
when required tools (Git, Node.js, npm) are missing, and blockers must be shown
honestly, not hidden. Do not imply this segment tracks the
recorded AI plan. Use the currently reviewed CLI; capture the separate usability
redesign only after it is ready and independently reviewed. If unavailable,
replace the terminal segment with the existing CLI guide and label it a walkthrough.

The source-page visit is live browsing of public documentation, not a replay of
the retrieved passages. Do not show playground excerpts as the original paid
request evidence. Keep the transition to the separate practice plan explicit.

Before capture, manually confirm the deployed app actually shows the recording.
If Celoscan is unavailable, show the public transaction URL and disclose that
live explorer verification is unavailable. Do not imply a new verification occurred.
The final video URL remains a submission item; this script is not a finished video.
