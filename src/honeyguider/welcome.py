"""Guided terminal workflow over the existing validated command handlers."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

import typer
from typer.main import get_command

from . import cencori, cli, journey, paid, track_cli, wallet
from .demo import TASKS
from .model import blockers, next_task
from .planning import next_action
from .research import ResearchError
from .state import fresh_state


def interactive_terminal() -> bool:
    """Require both input and output terminals; pipes must never prompt."""
    return sys.stdin.isatty() and sys.stdout.isatty()


PAID_STEP_WARNING = ('This step may incur the exactly-quoted paid service call, paid from your '
                     'selected account in the selected stablecoin — you confirm the cap at the '
                     'quote screen.')
FREE_STEP_NOTE = 'No payment is involved in this step.'
UNKNOWN_SETTLEMENT = 'Plan validated for inference output; payment settlement remains UNKNOWN.'
NO_PROVIDER_CLAIM = ('An imported tracking record does not prove that a provider payment '
                     'settled.')
ATTEMPT_START_UNAVAILABLE = ('The paid attempt cannot start on this platform or with this '
                             'request: {detail}. The prepared request is preserved at '
                             '{request_path}.')
ATTEMPT_RECEIPT_DIR_UNAVAILABLE = ('The attempt could not start: the receipt directory could not '
                                   'be created (it may have been created concurrently). The '
                                   'prepared request is preserved at {request_path}. Nothing was '
                                   'charged.')
_ATTEMPT_DETAIL_LIMIT = 120

_CORRELATION = {
    'correlated': ('A single recorded transaction hash matches this receipt claim. That is '
                   'correlation evidence only, never provider authentication of settlement.'),
    'conflicting': ('Correlation evidence is conflicting or ambiguous; settlement remains '
                    'UNKNOWN.'),
    'unavailable': 'No correlation evidence was found; settlement remains UNKNOWN.',
}


def choose(label: str, choices: dict[str, str]) -> str:
    for key, description in choices.items():
        cli.console.print(f"  {key}  {description}")
    while True:
        answer = typer.prompt(label, default="0").strip()
        if answer in choices:
            return answer
        cli.console.print("Invalid choice. Use the number beside an action: " + ", ".join(choices))


def track_context(ctx: typer.Context, directory: Path, command: str):
    """Use the group's parser and callback, including its storage boundary."""
    group = get_command(track_cli.app)
    return group, group.make_context(
        "track", ["--state-dir", str(directory), command], parent=ctx
    )


def session(ctx: typer.Context, directory: Path | None = None):
    """Navigate locally; all writes go through existing validated handlers."""
    child = None
    if directory is not None:
        _, child = track_context(ctx, directory, "next")
        with child:
            child.invoke(track_cli.main, ctx=child, state_dir=directory)
        cli.console.print("AI-generated plan: unverified recommendations. Completion is self-reported.")
        cli.console.print("Citations refer to evidence retrieved for the original plan. Opening this saved plan does not re-fetch its sources.")
    else:
        cli.console.print("Sample walkthrough: a fixed offline practice plan, not AI inference or verified event requirements.")

    def snapshot():
        if child is None:
            state = cli.read(ctx)
            return TASKS, state['completed'], state['checks']
        with track_cli.boundary():
            _, plan, completed = track_cli.read(child)
        return plan.tasks, completed, None

    def missing(task, completed, checks):
        if checks is None:
            return [f"Complete {dep} first" for dep in task.prerequisites if dep not in completed]
        return [f"Complete {item[5:]} first" if item.startswith('task:') else
                f"Check local {item[5:].split()[0]} availability" for item in blockers(task, completed, checks)]

    def overview(tasks, completed, checks):
        cli.console.print(f"Progress: {len(completed)}/{len(tasks)} complete (self-reported)")
        if checks is None:
            required = [t for t in tasks if t.classification == 'required']
            cli.console.print(f"Required: {sum(t.id in completed for t in required)}/{len(required)} complete")
        for item in tasks:
            reasons = missing(item, completed, checks)
            label = 'complete' if item.id in completed else 'blocked' if reasons else 'ready'
            cli.console.print(f"{item.id}: {item.title} — {label}")
            if reasons and item.id not in completed:
                cli.console.print('  ' + '; '.join(reasons))

    def details(task):
        cli.console.print(f"Instructions — {task.title}", style="bold")
        cli.console.print(task.action, highlight=False)
        cli.console.print(f"Prerequisites: {', '.join(task.prerequisites) or 'none'}")
        for source in task.sources:
            label = "Offline sample reference (not fetched)" if child is None else "Plan citation (not re-fetched)"
            cli.console.print(f"{label}: {source}", highlight=False)
        if not task.sources:
            cli.console.print("No source links supplied for this step.")

    def completion_available(task, completed, checks):
        return task is not None and task.id not in completed and not missing(task, completed, checks)

    def explain_unavailable(task, completed, checks):
        if task.id in completed:
            cli.console.print(f'Already complete: {task.id}. Inspect another step from the roadmap to continue.')
        else:
            cli.console.print('Blocked: ' + '; '.join(missing(task, completed, checks)))
            cli.console.print('Complete the prerequisites before recording completion.')
            if child is None and task.tools:
                cli.console.print('Use action 5 to check required local tools; install missing tools manually if needed.')

    def actions(task, completed, checks):
        choices = {}
        if task is not None:
            if completion_available(task, completed, checks):
                choices['1'] = 'Mark this step complete'
            choices['2'] = 'View instructions and sources'
        choices.update({'3': 'View the complete roadmap, progress and blockers',
                        '4': 'Inspect a step from the roadmap'})
        if child is None:
            choices['5'] = 'Check local tools (read-only version checks)'
        choices['0'] = 'Return to the main menu (progress is saved)'
        for key, label in choices.items():
            cli.console.print(f"  {key}  {label}")
        return choices

    refresh = True
    while True:
        if refresh:
            tasks, completed, checks = snapshot()
            if child is None:
                task = next_task(tasks, completed, checks)
            else:
                # Retain required-task prioritization from the tracking model.
                with track_cli.boundary():
                    _, plan, _ = track_cli.read(child)
                task = next_action(plan, frozenset(completed))
            # Keep the next blocked step inspectable instead of ending at a dead end.
            task = task or next((t for t in tasks if t.id not in completed), None)
            cli.console.print(f"\nProgress: {len(completed)}/{len(tasks)} complete (self-reported)")
            if task is None:
                cli.console.print("All tasks complete. You can review the roadmap or return to the main menu.")
            else:
                if child is not None and all(t.id in completed for t in tasks if t.classification == 'required'):
                    cli.console.print('All required steps complete. Remaining steps are optional.')
                suffix = f' ({task.classification})' if child is not None else ''
                cli.console.print(f"Current step: {task.id}: {task.title}{suffix}", style="bold")
                if not completion_available(task, completed, checks):
                    explain_unavailable(task, completed, checks)
            refresh = False
        # Reprint actions only on entry, a task change, completion or checks.
        choices = actions(task, completed, checks)
        while not refresh:
            hint = '1 complete, ' if '1' in choices else ''
            hint += '2 instructions, 3 roadmap, 0 main menu' if task else '3 roadmap, 4 inspect, 0 main menu'
            answer = typer.prompt(f'Action ({hint})', default='0').strip()
            if answer not in choices:
                if answer == '1' and task is not None:
                    explain_unavailable(task, completed, checks)
                else:
                    cli.console.print('Invalid choice. Enter an action number; use 1 to record completion when ready.'
                                      if '1' in choices else 'Invalid choice. Enter an action number shown above.')
                continue
            if answer == '0':
                return
            if answer == '2':
                details(task)
            elif answer == '3':
                overview(*snapshot())
            elif answer == '4':
                tasks, completed, checks = snapshot()
                selected = typer.prompt('Step ID from the roadmap (0 to cancel)', default='0').strip()
                if selected == '0':
                    cli.console.print('Inspection cancelled.')
                    continue
                inspected = next((t for t in tasks if t.id == selected), None)
                if inspected is None:
                    cli.console.print('Unknown step. View the roadmap with action 3 for step IDs.')
                    continue
                task = inspected
                cli.console.print(f"Current step: {task.id}: {task.title}", style='bold')
                details(task)
                if not completion_available(task, completed, checks):
                    explain_unavailable(task, completed, checks)
                choices = actions(task, completed, checks)
            elif answer == '1':
                # Refresh eligibility before prompting; handlers still revalidate on write.
                tasks, completed, checks = snapshot()
                if not completion_available(task, completed, checks):
                    explain_unavailable(task, completed, checks)
                    refresh = True
                    continue
                if not typer.confirm(f'Record {task.id} as complete? This is your self-reported completion', default=False):
                    cli.console.print('Completion cancelled. Progress unchanged.')
                    continue
                try:
                    output_console = cli.console if child is None else track_cli.console
                    with output_console.capture() as output:
                        if child is None:
                            ctx.invoke(cli.done, ctx=ctx, task_id=task.id)
                        else:
                            child.invoke(track_cli.done, ctx=child, task_id=task.id)
                    cli.console.print(output.get(), end='', highlight=False)
                except (typer.Exit, OSError) as exc:
                    if isinstance(exc, typer.Exit) and exc.exit_code not in (1, 2):
                        raise
                    cli.console.print('Completion could not be confirmed. Saved progress may have changed. No write will be retried automatically.')
                    try:
                        # Reuse validated readers; suppress boundary wording that
                        # cannot establish the outcome of the preceding write.
                        with output_console.capture():
                            _, saved_completed, _ = snapshot()
                    except typer.Exit:
                        cli.console.print('Unable to verify saved progress. Inspect the saved plan before attempting another completion.')
                        raise
                    if task.id in saved_completed:
                        cli.console.print(f'Saved state currently shows {task.id} complete. Storage durability was not confirmed.')
                    else:
                        cli.console.print(f'Saved state currently shows {task.id} incomplete. Review blockers and storage before deciding whether to try again.')
                refresh = True
            elif answer == '5':
                if not typer.confirm('Run local tool version checks and save the results?', default=False):
                    cli.console.print('Tool checks cancelled. Progress unchanged.')
                    continue
                try:
                    ctx.invoke(cli.check, ctx=ctx)
                except typer.Exit as exc:
                    if exc.exit_code != 1:
                        raise
                    cli.console.print('Some tools are unavailable. Review the results above and install tools manually if needed.')
                refresh = True


def documentation(ctx: typer.Context):
    cli.console.print("Explore public HTTPS documentation for your development goal. You can read relevant excerpts or view a fixed demonstration plan. These plans are not AI-inferred requirements and are not saved for tracking.")
    choice = choose("Documentation", {"1": "Read relevant documentation excerpts", "2": "View a demonstration development plan", "0": "Back"})
    if choice == "0":
        return
    url = typer.prompt("Documentation HTTPS URL").strip()
    goal = typer.prompt("Development goal").strip()
    if not url or not goal:
        cli.console.print("URL and goal must be non-empty. Returning to the main menu.")
        return
    if not typer.confirm("Retrieve documentation over the network now?", default=False):
        cli.console.print('Retrieval cancelled. No documentation was fetched.')
        return
    try:
        if choice == "1":
            ctx.invoke(cli.research, url=url, goal=goal)
        else:
            ctx.invoke(cli.plan, ctx=ctx, url=url, goal=goal)
    except typer.Exit as exc:
        if exc.exit_code != 1:
            raise
        cli.console.print('Documentation could not be fully processed. Review the retrieval issues above.')


def _account_alias(default: str = wallet.DEFAULT_ACCOUNT) -> str:
    answer = typer.prompt('Wallet account name', default=default).strip()
    return answer or default


def _buy_path() -> Path:
    return Path(typer.prompt('Path to the buy 0.8.4 executable', default='buy')).expanduser()


def _is_zero(amount) -> bool:
    try:
        return Decimal(str(amount)) == 0
    except (InvalidOperation, ValueError):
        return False


def _show_problems(problems):
    for problem in problems:
        text = str(problem).strip()
        if not text:
            continue
        cli.console.print(f'Wallet problem: {text}')
        lowered = text.lower()
        if 'not mainnet' in lowered:
            cli.console.print('The guided journey requires a Celo Mainnet account; a Sepolia account cannot pay.')
        elif 'no wallet account configured' in lowered:
            cli.console.print('Run 5 → 6 to set up a wallet, then choose 1 to verify readiness.')
        elif 'balance' in lowered:
            cli.console.print('You can fund the wallet, then choose 1 or 2 to refresh.')


def _show_identity(readiness):
    identity = readiness.identity
    if identity is None:
        cli.console.print('Wallet identity unavailable; supported balances could not be read. '
                          'This is missing information, not a zero balance.')
        return
    cli.console.print(f'Account {identity.name} on {identity.network}: {identity.address}')
    balances = readiness.supported_balances
    if not balances:
        cli.console.print('Supported stablecoin balances unavailable; see the problems above. '
                          'This is not evidence of a zero balance.')
        return
    for token in wallet.SUPPORTED_TOKENS:
        if token in balances:
            cli.console.print(f'  {token}: {balances[token]}')
    if all(_is_zero(amount) for amount in balances.values()):
        cli.console.print('No supported stablecoin balance detected (USDC, USDT, USAT).')


def _show_payment_rows(rows):
    if not rows:
        cli.console.print('No locally recorded payment rows were found.')
    else:
        for row in rows:
            cli.console.print(f'{row.date}  {row.account}  {row.amount} {row.token} on '
                              f'{row.network}  {row.state}')
    cli.console.print('These are locally recorded claims from the buy receipt ledger, not settlement proof.')
    if any(getattr(row, 'tx_hash', None) for row in rows):
        cli.console.print('Recorded transaction hashes are unverified correlation only; they do '
                          'not confirm a provider payment.')


def wallet_section(ctx: typer.Context, *, runner=None):
    """Read-only wallet views; setup is printed only and never executed here.

    ``runner`` is the injectable wallet command seam; production passes None so
    the verified wallet boundary uses its bounded subprocess path.
    """
    cli.console.print(FREE_STEP_NOTE)
    choice = choose('Wallet & payments', {
        '1': 'Check wallet identity and readiness',
        '2': 'Balances (refresh after funding)',
        '3': 'Funding instructions',
        '4': 'Payment history (local records)',
        '5': 'Reconciliation (asks buy for on-chain status)',
        '6': 'Set up a wallet (proposal only)',
        '0': 'Back',
    })
    if choice == '0':
        return
    if choice == '6':
        alias = _account_alias()
        try:
            command = wallet.setup_command(alias)
        except wallet.WalletError as exc:
            cli.console.print(f'Wallet setup proposal refused: {exc}')
            return
        cli.console.print('Setup creates a named wallet account. The key goes into YOUR OS '
                          'keychain; Honeyguider never sees or stores it.')
        cli.console.print('Run this command in your own terminal: ' + ' '.join(command),
                          highlight=False)
        cli.console.print('Run it in another terminal, then choose 1 to verify readiness. This '
                          'menu never executes it for you.')
        return
    buy = _buy_path()
    account = _account_alias() if choice in ('1', '2', '3') else None
    try:
        if choice in ('1', '2'):
            readiness = wallet.readiness(buy, account, runner=runner)
            _show_problems(readiness.problems)
            _show_identity(readiness)
        elif choice == '3':
            readiness = wallet.readiness(buy, account, runner=runner)
            _show_problems(readiness.problems)
            identity = readiness.identity
            if identity is None:
                cli.console.print('Funding instructions need a readable wallet identity; choose '
                                  '6 to set up a wallet and 1 to verify.')
                return
            cli.console.print('Funding instructions (read-only; nothing is transferred here).')
            cli.console.print(f'Receiving address: {identity.address}')
            cli.console.print(f'Network: {identity.network} — the guided journey requires Celo Mainnet.')
            cli.console.print('Supported tokens only: USDC, USDT, USAT. Other tokens (including '
                              'USDm or CELO) are not supported journey funds.')
            cli.console.print('The gateway sponsors transaction gas: no separate CELO gas balance '
                              'is needed for the verified x402 payment workflow.')
            cli.console.print('After funding, choose 2 to refresh balances.')
            cli.console.print('Funding a wallet is not approving a paid call; approval happens at '
                              'the quote screen with an exact cap.')
        elif choice == '4':
            _show_payment_rows(wallet.payment_history(buy, runner=runner))
        else:
            if not typer.confirm('Reconciliation asks the buy CLI to check on-chain settlement '
                                 'status. It performs a network read. Continue?', default=False):
                cli.console.print('Reconciliation cancelled. No network read was requested.')
                return
            rows = wallet.payment_history(buy, resolve=True, runner=runner)
            _show_payment_rows(rows)
            answer = typer.prompt('Receipt directory to correlate (empty skips correlation)',
                                  default='').strip()
            if answer:
                try:
                    verdict = journey.correlate_claim(Path(answer).expanduser(), rows)
                except (OSError, ValueError) as exc:
                    cli.console.print(f'Correlation could not be evaluated: {exc}')
                else:
                    cli.console.print(_CORRELATION.get(
                        verdict, 'Unrecognized correlation verdict; settlement remains UNKNOWN.'))
                cli.console.print(NO_PROVIDER_CLAIM)
    except wallet.WalletError as exc:
        cli.console.print(f'Wallet operation refused or failed: {exc}')


def create_tracked_plan(ctx: typer.Context):
    """Orchestrate research -> one approved paid attempt -> import -> tracking."""
    cli.console.print('Create a tracked plan: retrieve documentation, request one paid AI '
                      'inference, import the validated plan, then track progress locally.')
    cli.console.print(PAID_STEP_WARNING)
    cli.console.print('Retrieval, request preparation and readiness review are free. ' + FREE_STEP_NOTE)
    url = typer.prompt('Documentation HTTPS URL').strip()
    goal = typer.prompt('Development goal').strip()
    if not url or not goal:
        cli.console.print('URL and goal must be non-empty. Nothing was retrieved or charged.')
        return
    if not typer.confirm('Retrieve documentation over the network now?', default=False):
        cli.console.print('Retrieval cancelled. Nothing was retrieved; no files were created.')
        return
    proposed = journey.suggest_path(journey.DEFAULT_REQUESTS_ROOT, 'req', datetime.now(), '.json')
    cli.console.print(f'Proposed request path: {proposed}')
    answer = typer.prompt('Request path', default=str(proposed)).strip()
    request_path = Path(answer or proposed).expanduser()
    try:
        request_path = journey.prepare(url, goal, request_path)
    except (cencori.CencoriError, journey.JourneyError, ResearchError, OSError) as exc:
        cli.console.print(f'Preparation failed; nothing was charged. {exc}')
        return

    alias = _account_alias()
    buy = _buy_path()
    try:
        readiness = wallet.readiness(buy, alias)
    except wallet.WalletError as exc:
        cli.console.print(f'Wallet readiness could not be checked: {exc}')
        cli.console.print(f'No attempt started; your request is preserved at {request_path}.')
        return
    _show_problems(readiness.problems)
    _show_identity(readiness)
    if readiness.identity is None:
        cli.console.print('The paid attempt needs a readable Celo Mainnet identity. No attempt '
                          f'started; your request is preserved at {request_path}.')
        return
    if any('balance' in str(problem).lower() for problem in readiness.problems):
        cli.console.print('You can fund and choose 1/2 to refresh, then start a new attempt.')
    if not typer.confirm('Proceed to the paid attempt after review?', default=False):
        cli.console.print(f'No attempt started; your request is preserved at {request_path}.')
        return

    token = 'USDC'
    while True:
        chosen = typer.prompt('Payment token', default=token).strip().upper() or 'USDC'
        if chosen in paid.TOKENS:
            token = chosen
            break
        cli.console.print('Unsupported token. Choose USDC, USDT or USAT.')

    receipt_dir = None
    for _ in range(3):
        proposal = journey.suggest_path(journey.DEFAULT_RECEIPTS_ROOT, 'attempt', datetime.now())
        cli.console.print(f'Proposed receipt directory: {proposal}')
        answer = typer.prompt('Receipt directory', default=str(proposal)).strip()
        candidate = Path(answer or proposal).expanduser()
        if candidate.exists():
            cli.console.print('That receipt directory already exists; choose a new path.')
            continue
        receipt_dir = candidate
        break
    if receipt_dir is None:
        cli.console.print('No unused receipt directory selected. Nothing was charged; the '
                          f'request is preserved at {request_path}.')
        return

    def paid_prompt(label):
        return typer.prompt(label, default='', show_default=False)

    def paid_display(text):
        cli.console.print(text, highlight=False)

    try:
        plan = journey.infer_with_receipt(
            request_path, Path(buy), receipt_dir, token,
            prompt=paid_prompt, display=paid_display,
            account=alias, expected_payer=readiness.identity.address)
    except journey.AttemptInProgress as exc:
        cli.console.print(f"Another attempt holds this request's lock ({exc.lock_path}). "
                          'Nothing was started.')
        return
    except cencori.CencoriError as exc:
        cli.console.print(f'Paid inference did not complete: {exc}')
        cli.console.print('The attempt did not start or was refused. The prepared request and any '
                          'receipt remain at the paths shown. Payment settlement is UNKNOWN and '
                          'this menu never confirms it.')
        return
    except journey.JourneyError as exc:
        detail = str(exc)
        if len(detail) > _ATTEMPT_DETAIL_LIMIT:
            detail = detail[:_ATTEMPT_DETAIL_LIMIT]
        cli.console.print(ATTEMPT_START_UNAVAILABLE.format(detail=detail,
                                                           request_path=request_path))
        return
    except OSError:
        cli.console.print(ATTEMPT_RECEIPT_DIR_UNAVAILABLE.format(request_path=request_path))
        return

    tasks = getattr(plan, 'tasks', ())
    cli.console.print(f'Validated plan: {len(tasks)} task(s).')
    if tasks:
        cli.console.print(f'First actionable task: {tasks[0].id}: {tasks[0].title}')

    root_answer = typer.prompt('Tracking root', default=str(journey.DEFAULT_TRACK_ROOT)).strip()
    tracking_root = Path(root_answer or journey.DEFAULT_TRACK_ROOT).expanduser()

    def attempt_import(custom_consent=False):
        return journey.import_outcome(receipt_dir, tracking_root=tracking_root,
                                      custom_root_consent=custom_consent)

    preserved = f'The prepared request and receipt are preserved at {request_path} and {receipt_dir}.'
    try:
        outcome = attempt_import()
    except (journey.JourneyError, cencori.CencoriError, OSError) as exc:
        cli.console.print(f'Import failed: {exc}')
        cli.console.print(preserved)
        return
    if outcome.disposition == 'custom_consent_required':
        cli.console.print(f'Canonical duplicate at the default root: {outcome.canonical_duplicate}')
        cli.console.print(f'Destination at the custom root: {outcome.destination}')
        for problem in outcome.problems:
            cli.console.print(f'Import problem: {problem}')
        if not typer.confirm('Create an additional tracking record at this custom root? This is a '
                             'duplicate plan, not a new payment.', default=False):
            cli.console.print('No additional record created. ' + preserved)
            return
        try:
            outcome = attempt_import(custom_consent=True)
        except (journey.JourneyError, cencori.CencoriError, OSError) as exc:
            cli.console.print(f'Import failed: {exc}')
            cli.console.print(preserved)
            return
    if outcome.disposition in ('imported', 'already_imported') and outcome.destination is not None:
        cli.console.print(f'Tracking record: {outcome.destination}')
        cli.console.print(UNKNOWN_SETTLEMENT)
        cli.console.print(NO_PROVIDER_CLAIM)
        session(ctx, outcome.destination)
        return
    for problem in outcome.problems:
        cli.console.print(f'Import problem: {problem}')
    cli.console.print(preserved + ' You can resume or inspect them later from 2 → 3.')


def welcome(ctx: typer.Context):
    cli.console.print("Honeyguider", style="bold")
    cli.console.print("Turn technical documentation into actionable development plans. Follow steps, inspect sources, and save your progress here.")
    cli.console.print("Opening this menu stays offline. Completion records what you report; tasks are never executed for you.")
    try:
        while True:
            choice = choose("Main menu", {
                "1": "Explore documentation",
                "2": "Continue a saved plan",
                "3": "Try a sample walkthrough",
                "4": "Help and advanced commands",
                "5": "Wallet & payments",
                "6": "Create a tracked plan", "0": "Exit",
            })
            if choice == "0":
                cli.console.print('Goodbye. Saved progress will be here when you return.')
                return
            if choice == "1":
                documentation(ctx)
            elif choice == "2":
                kind = choose("Continue", {"1": "Sample walkthrough", "2": "Previously imported AI plan",
                                          "3": "List existing tracked plans", "0": "Back"})
                if kind == "1":
                    if not ctx.obj.exists():
                        cli.console.print('No saved sample yet. Choose 3 on the main menu to start one.')
                    else:
                        session(ctx)
                elif kind == "2":
                    directory = Path(typer.prompt("Tracking directory", default=".honeyguider/track")).expanduser()
                    session(ctx, directory)
                elif kind == "3":
                    while True:
                        plans = journey.list_tracked_plans()
                        if not plans:
                            cli.console.print('No tracked plans found.')
                            break
                        for index, plan in enumerate(plans, 1):
                            settlement = plan.settlement or 'unknown'
                            cli.console.print(f'{index}: {plan.directory.name} — tasks '
                                              f'{plan.completed}/{plan.tasks} completed; '
                                              f'attempt/settlement: {settlement}')
                            for problem in plan.problems:
                                cli.console.print(f'  Problem: {problem}')
                        answer = typer.prompt('Tracking directory (empty = re-list; the number '
                                              'above, or a path)', default='').strip()
                        if not answer:
                            break
                        if answer.isdigit():
                            index = int(answer)
                            if 1 <= index <= len(plans):
                                session(ctx, plans[index - 1].directory)
                                break
                            cli.console.print('No plan has that number. Use a listed number or a path.')
                            continue
                        session(ctx, Path(answer).expanduser())
                        break
            elif choice == "3":
                if ctx.obj.exists():
                    cli.read(ctx)  # Validate without rewriting existing progress.
                else:
                    cli.write(ctx, fresh_state())
                session(ctx)
            elif choice == "5":
                wallet_section(ctx)
            elif choice == "6":
                create_tracked_plan(ctx)
            else:
                cli.console.print('Use the guided actions to inspect steps and record completion. You can exit and continue later. Source links are not fetched when viewing a saved plan.')
                cli.console.print('The sample is fixed practice data. Imported AI plans contain unverified AI recommendations. Recorded examples are saved outputs, not live inference. Paid inference is available only through the guided \'Create a tracked plan\' flow, which shows the exact quote and requires your explicit approval code.')
                cli.console.print(ctx.get_help())
    except (typer.Abort, KeyboardInterrupt, EOFError):
        cli.console.print("Navigation cancelled. Previously saved progress is retained.")
