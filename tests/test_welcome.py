"""Deterministic navigation tests; no real network, tools or paid operations."""
import os.path
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from typer.testing import CliRunner

from honeyguider import cencori, cli, journey, paid, tracking, wallet, welcome
from honeyguider.research import Report, extract
from honeyguider.state import fresh_state, load, save

terminal_detector = welcome.interactive_terminal


@pytest.fixture(autouse=True)
def offline_terminal(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(welcome, "interactive_terminal", lambda: True)

    def forbidden(*args, **kwargs):
        pytest.fail("Navigation attempted external I/O or payment")

    for target, name in [(socket, "getaddrinfo"), (socket, "create_connection"),
                         (subprocess, "run"), (subprocess, "Popen"),
                         (httpx.Client, "send"), (httpx.AsyncClient, "send"),
                         (paid, "infer"), (paid, "wallet_environment"),
                         (paid, "supervise"), (cencori, "_run")]:
        monkeypatch.setattr(target, name, forbidden)


def invoke(text="", args=()):
    return CliRunner().invoke(cli.app, list(args), input=text)


def test_welcome_help_exit_do_not_create_state(tmp_path):
    result = invoke("4\n0\n")
    assert result.exit_code == 0, result.output
    for command in ("explore", "research", "plan", "track", "check", "next", "done", "status"):
        assert command in result.output
    assert not (tmp_path / ".pathf1ndar").exists()
    assert not (tmp_path / ".honeyguider").exists()


def test_demo_navigation_and_full_citations(tmp_path):
    state = tmp_path / "custom.json"
    result = invoke("3\n2\n3\n0\n0\n", ("--state-file", str(state)))
    assert result.exit_code == 0, result.output
    assert "Current step: scope:" in result.output
    assert "Offline sample reference (not fetched): https://docs.celo.org/" in result.output
    assert "0/5 complete" in result.output
    assert load(state) == fresh_state()
    compact = invoke("3\n0\n0\n", ("--state-file", str(state)))
    assert "Current step: scope:" in compact.output
    assert "Offline sample reference" not in compact.output
    assert "prototype:" not in compact.output


def test_resume_preserves_state_and_shows_blockers(tmp_path):
    state = tmp_path / "progress.json"
    save(state, fresh_state() | {"completed": ["scope"]})
    before = state.read_bytes()
    result = invoke("2\n1\n3\n0\n0\n", ("--state-file", str(state)))
    assert result.exit_code == 0, result.output
    assert "Blocked:" in result.output
    assert "1/5 complete" in result.output
    assert state.read_bytes() == before


@pytest.mark.parametrize("directory_name", ["private-plan", "private plan", "plan's $(not-run); [draft]"])
@pytest.mark.parametrize("use_home", [False, True])
def test_resume_tracked_plan(tmp_path, directory_name, use_home):
    directory = tmp_path / directory_name
    directory.mkdir(mode=0o700)
    url = "https://docs.example.com/"
    state = {"schema_version": 1, "revision": 0, "receipt": str(tmp_path / "missing-receipt"),
             "request_sha256": "a" * 64, "completion_sha256": "b" * 64,
             "sources": [url], "completed": [], "plan": {"schema_version": 1, "tasks": [
                 {"id": "review", "title": "Review docs", "action": "Read the source.",
                  "prerequisites": [], "sources": [url], "classification": "required"}]}}
    tracking.append(directory, state)
    before = (directory / "000000.json").read_bytes()
    # Reach only the temporary fixture via ~, without changing the real home.
    entered = "~/" + os.path.relpath(directory, Path.home()) if use_home else str(directory)
    result = invoke(f"2\n2\n{entered}\n2\n3\n0\n0\n")
    assert result.exit_code == 0, result.output
    assert "Current step: review: Review docs" in result.output
    assert f"Plan citation (not re-fetched): {url}" in result.output
    assert "Opening this saved plan does not re-fetch its sources" in " ".join(result.output.split())
    assert "Offline sample reference" not in result.output
    assert "not fetched" not in result.output
    assert "Required: 0/1 complete" in result.output
    assert "Completion command:" not in result.output
    assert (directory / "000000.json").read_bytes() == before
    assert len(list(directory.iterdir())) == 1


@pytest.mark.parametrize("text", ["bad\n99\n0\n", "\n", "0\n"])
def test_invalid_input_and_default_exit(text):
    result = invoke(text)
    assert result.exit_code == 0, result.output
    if text.startswith("bad"):
        assert result.output.count("Invalid choice") == 2


@pytest.mark.parametrize("text", ["", "\x03", "1\n1\n", "1\n2\nhttps://docs.example.com/\n"])
def test_cancellation_at_prompts(text, tmp_path):
    result = invoke(text)
    assert result.exit_code == 0, result.output
    assert "Navigation cancelled" in result.output
    assert not (tmp_path / ".pathf1ndar").exists()


@pytest.mark.parametrize("text", ["1\n0\n0\n", "2\n0\n0\n",
                                      "1\n1\nhttps://docs.example.com/\ninstall\nn\n0\n"])
def test_back_and_network_refusal(text, monkeypatch):
    retrieve = AsyncMock(side_effect=AssertionError("Unexpected retrieval"))
    monkeypatch.setattr(cli, "research_pages", retrieve)
    result = invoke(text)
    assert result.exit_code == 0, result.output
    retrieve.assert_not_called()


@pytest.mark.parametrize("choice", ["1", "2"])
def test_documentation_explicit_retrieval(choice, monkeypatch, tmp_path):
    url = "https://docs.example.com/"
    report = Report(pages=[extract(b"<h2>Install</h2><p>Install the package.</p>", url, "install")])
    retrieve = AsyncMock(return_value=report)
    monkeypatch.setattr(cli, "research_pages", retrieve)
    result = invoke(f"1\n{choice}\n{url}\ninstall\ny\n0\n")
    assert result.exit_code == 0, result.output
    retrieve.assert_awaited_once_with(url, "install")
    assert "Source" in result.output
    assert not (tmp_path / ".pathf1ndar").exists()


@pytest.mark.parametrize("stdin_tty,stdout_tty", [(False, True), (True, False), (False, False), (True, True)])
def test_terminal_detection(stdin_tty, stdout_tty, monkeypatch):
    monkeypatch.setattr(welcome.sys, "stdin", Mock(isatty=lambda: stdin_tty))
    monkeypatch.setattr(welcome.sys, "stdout", Mock(isatty=lambda: stdout_tty))
    assert terminal_detector() is (stdin_tty and stdout_tty)


def test_noninteractive_help_and_compatibility(monkeypatch, tmp_path):
    monkeypatch.setattr(welcome, "interactive_terminal", lambda: False)
    result = invoke("1\n")
    assert result.exit_code == 2
    assert "Usage:" in result.output
    assert "Welcome:" not in result.output
    assert invoke(args=("--help",)).exit_code == 0
    assert invoke(args=("unknown-command",)).exit_code == 2
    assert invoke(args=("explore",)).exit_code == 2
    assert invoke(args=("next",)).exit_code == 1
    assert invoke(args=("explore", "--demo")).exit_code == 0
    assert invoke(args=("next",)).output.startswith("scope:")
    assert invoke(args=("done", "scope")).exit_code == 0
    assert "1/5 complete" in invoke(args=("status",)).output


def test_explicit_commands_never_open_menu(monkeypatch):
    monkeypatch.setattr(welcome, "welcome", Mock(side_effect=AssertionError("Menu opened")))
    assert invoke(args=("--help",)).exit_code == 0
    assert invoke(args=("explore", "--demo")).exit_code == 0
    assert invoke(args=("track", "--help")).exit_code == 0


@pytest.mark.parametrize("selection", ["3\n", "2\n1\n"])
def test_corrupt_demo_fails_closed(selection, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("broken")
    result = invoke(selection, ("--state-file", str(state)))
    assert result.exit_code == 1
    assert state.read_text() == "broken"


def test_missing_track_and_overlapping_storage_fail_closed(tmp_path):
    missing = tmp_path / "missing"
    result = invoke(f"2\n2\n{missing}\n")
    assert result.exit_code == 1
    assert not missing.exists()
    result = invoke(f"2\n2\n{tmp_path}\n", ("--state-file", str(tmp_path / "demo.json")))
    assert result.exit_code == 2
    assert "Tracking directory must be separate" in result.output


def test_first_time_welcome_is_clear_and_read_only(tmp_path):
    result = invoke('0\n')
    assert result.exit_code == 0
    for label in ('technical documentation', 'Explore documentation', 'Continue a saved plan',
                  'Try a sample walkthrough', 'Help and advanced commands', 'Exit'):
        assert label in result.output
    assert not list(tmp_path.iterdir())


def test_uat_inspect_complete_advance_and_resume(tmp_path):
    """The original dead end: reading scope must lead to in-menu completion."""
    result = invoke('3\n2\n1\ny\n3\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Write a one-paragraph use case' in result.output
    assert 'https://docs.celo.org/' in result.output
    assert 'Completed: scope (self-reported)' in result.output
    assert 'Current step: workspace:' in result.output
    assert 'Check local python availability' in result.output
    assert 'honeyguider done' not in result.output
    assert result.output.count('Current step: scope:') == 1
    assert result.output.count('Mark this step complete') == 1  # blocked workspace has no completion action
    state = tmp_path / '.pathf1ndar/state.json'
    assert load(state)['completed'] == ['scope']
    before = state.read_bytes()
    reopened = invoke('2\n1\n2\n0\n0\n')
    assert reopened.exit_code == 0, reopened.output
    assert 'Current step: workspace:' in reopened.output
    assert '1/5 complete' in reopened.output
    assert state.read_bytes() == before


def test_completion_refusal_and_eof_do_not_mutate(tmp_path):
    state = tmp_path / 'demo.json'
    save(state, fresh_state())
    before = state.read_bytes()
    for text in ('3\n1\nn\n0\n0\n', '3\n1\n'):
        result = invoke(text, ('--state-file', str(state)))
        assert result.exit_code == 0, result.output
        assert 'cancelled' in result.output
        assert 'Completed:' not in result.output
        assert state.read_bytes() == before


def test_blocked_step_has_no_completion_action_and_stays_in_menu(tmp_path):
    result = invoke('3\n4\nworkspace\n1\n2\n3\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Complete scope first' in result.output
    assert 'task:scope' not in result.output
    inspected = result.output.split('Current step: workspace:')[1]
    assert 'Mark this step complete' not in inspected
    assert '1 complete' not in inspected
    assert 'Record workspace as complete?' not in inspected
    assert 'Check local tools' in inspected
    assert load(tmp_path / '.pathf1ndar/state.json')['completed'] == []


def test_local_checks_are_explicit_and_advance(monkeypatch, tmp_path):
    checks = Mock(return_value={tool: {'available': True, 'version': 'test', 'detail': ''}
                               for tool in ('python', 'git', 'node', 'npm')})
    monkeypatch.setattr(cli, 'inspect_environment', checks)
    result = invoke('3\n1\ny\n5\nn\n5\ny\n1\ny\n0\n0\n')
    assert result.exit_code == 0, result.output
    checks.assert_called_once_with()
    assert 'Current step: prototype:' in result.output
    assert load(tmp_path / '.pathf1ndar/state.json')['completed'] == ['scope', 'workspace']


def test_old_command_input_has_actionable_recovery():
    result = invoke('3\n2\nhoneyguider done scope\n1\ny\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert 'use 1 to record completion' in result.output
    assert 'Completed: scope' in result.output


def test_inspection_cancellation_and_unknown_step():
    result = invoke('3\n4\n0\n4\nunknown\n2\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Inspection cancelled' in result.output
    assert 'Unknown step' in result.output
    assert result.output.count('Current step: scope:') == 1


def test_all_complete_plan_can_still_inspect_steps(tmp_path):
    from honeyguider.demo import TASKS
    state = tmp_path / 'complete.json'
    save(state, fresh_state() | {'completed': [task.id for task in TASKS],
                               'checks': {tool: {'available': True, 'version': 'test', 'detail': ''}
                                          for tool in ('python', 'git', 'node', 'npm')}})
    before = state.read_bytes()
    result = invoke('2\n1\n4\nscope\n2\n1\n0\n0\n', ('--state-file', str(state)))
    assert result.exit_code == 0, result.output
    assert 'All tasks complete' in result.output
    assert 'Already complete: scope' in result.output
    assert 'Mark this step complete' not in result.output
    assert 'Record scope as complete?' not in result.output
    assert '1 complete' not in result.output
    assert state.read_bytes() == before


def test_tool_blocked_step_keeps_inspection_and_checks_without_completion(tmp_path, monkeypatch):
    state = tmp_path / 'demo.json'
    save(state, fresh_state() | {'completed': ['scope']})
    done = Mock(side_effect=AssertionError('Unavailable completion was invoked'))
    monkeypatch.setattr(cli, 'done', done)
    before = state.read_bytes()
    result = invoke('2\n1\n1\n2\n3\n5\nn\n0\n0\n', ('--state-file', str(state)))
    assert result.exit_code == 0, result.output
    assert 'Mark this step complete' not in result.output
    assert '1 complete' not in result.output
    assert 'Record workspace as complete?' not in result.output
    assert 'Check local python availability' in result.output
    assert 'Use action 5' in result.output
    assert 'Instructions — Prepare a local workspace' in result.output
    assert 'scope: Define a Celo hackathon agent — complete' in result.output
    assert 'Tool checks cancelled' in result.output
    done.assert_not_called()
    assert state.read_bytes() == before


@pytest.mark.parametrize('error', [OSError, cli.StateError])
def test_demo_late_save_failure_reads_back_without_retry(tmp_path, monkeypatch, error):
    state = tmp_path / 'demo.json'
    save(state, fresh_state())

    def late_failure(path, value):
        save(path, value)
        raise error('simulated error after replacement')

    writer = Mock(side_effect=late_failure)
    monkeypatch.setattr(cli, 'save', writer)
    result = invoke('2\n1\n1\ny\n0\n0\n', ('--state-file', str(state)))
    output = ' '.join(result.output.split())
    assert result.exit_code == 0, result.output
    assert 'Completion could not be confirmed' in output
    assert 'Saved state currently shows scope complete.' in output
    assert 'Completion not recorded' not in output
    assert 'Current step: workspace:' in output
    assert writer.call_count == 1
    assert load(state)['completed'] == ['scope']


# --- Phase 6: wallet & payments submenu -------------------------------------

_ADDRESS = '0x' + 'a' * 40


def _flat(text):
    return ' '.join(text.split())


def _wallet_identity(network='celo', balances=None):
    return wallet.WalletIdentity('honeyguider', network, _ADDRESS,
                                 dict(balances or {'USDC': '0'}))


def _fake_readiness(identity=_wallet_identity(), supported=None, problems=()):
    return wallet.WalletReadiness(True, identity, None, False,
                                  dict(supported or {}), tuple(problems))


def _stub_readiness(monkeypatch, fake):
    readiness = Mock(return_value=fake) if not isinstance(fake, Exception) else Mock(side_effect=fake)
    monkeypatch.setattr(welcome.wallet, 'readiness', readiness)
    return readiness


def _payment_row(**overrides):
    values = dict(date='2026-11-08 15:30:00Z', account='honeyguider', amount='0.01',
                  token='USDC', network='celo', state='exited', http_code='200',
                  resource='https://api.example.com/', tx_hash=None)
    values.update(overrides)
    return wallet.PaymentRow(**values)


def test_main_menu_lists_wallet_and_tracked_plan_options(tmp_path):
    result = invoke('0\n')
    assert result.exit_code == 0, result.output
    assert '5  Wallet & payments' in result.output
    assert '6  Create a tracked plan' in result.output
    assert not (tmp_path / '.honeyguider').exists()


def test_wallet_submenu_is_free_and_back_returns(tmp_path):
    result = invoke('5\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert welcome.FREE_STEP_NOTE in result.output
    for label in ('Check wallet identity and readiness', 'Balances (refresh after funding)',
                  'Funding instructions', 'Payment history (local records)',
                  'Reconciliation (asks buy for on-chain status)',
                  'Set up a wallet (proposal only)'):
        assert label in result.output
    assert not (tmp_path / '.honeyguider').exists()


def test_wallet_submenu_invalid_input_reprompts_without_side_effects(monkeypatch, tmp_path):
    readiness = _stub_readiness(monkeypatch, _fake_readiness())
    result = invoke('5\nbad\n0\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Invalid choice' in result.output
    readiness.assert_not_called()
    assert not (tmp_path / '.honeyguider').exists()


@pytest.mark.parametrize('text', ['5\n', '6\n', '6\nhttps://docs.example.com/\n'])
def test_new_flows_cancel_cleanly_at_eof(text):
    result = invoke(text)
    assert result.exit_code == 0, result.output
    assert 'Navigation cancelled' in result.output


def test_wallet_identity_zero_balance_message(monkeypatch, tmp_path):
    _stub_readiness(monkeypatch, _fake_readiness(
        supported={'USDC': '0', 'USDT': '0.0', 'USAT': '0'},
        problems=('No supported token balance (USDC, USDT, USAT)',)))
    result = invoke('5\n1\n/usr/bin/buy\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    assert f'Account honeyguider on celo: {_ADDRESS}' in result.output
    assert 'No supported stablecoin balance detected (USDC, USDT, USAT).' in result.output
    assert 'Wallet problem: No supported token balance (USDC, USDT, USAT)' in result.output
    assert not (tmp_path / '.honeyguider').exists()


def test_wallet_identity_unavailable_problem_is_not_zero_balance(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness(
        identity=None,
        problems=('buy whoami output has no identity shape: \'SEED-FIXTURE-SECRET\'',)))
    result = invoke('5\n1\n/usr/bin/buy\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Wallet identity unavailable' in result.output
    assert 'not a zero balance' in result.output
    assert 'No supported stablecoin balance detected' not in result.output
    assert 'SEED-FIXTURE-SECRET' in result.output  # problem text is bounded, never a secret value
    assert 'private key' not in result.output.lower()


def test_wallet_sepolia_identity_gets_routing_message(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness(
        identity=_wallet_identity(network='celo-sepolia'), problems=('not mainnet',)))
    result = invoke('5\n1\n/usr/bin/buy\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Wallet problem: not mainnet' in result.output
    assert 'requires a Celo Mainnet account' in result.output


def test_wallet_never_prints_secret_material(monkeypatch):
    secret = 'SEED-FIXTURE-SECRET-PHRASE'
    _stub_readiness(monkeypatch, _fake_readiness(
        supported={'USDC': '1.5'}, problems=(f'unexpected output {secret}',)))
    result = invoke('5\n1\n/usr/bin/buy\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    assert '0x' + 'b' * 64 not in result.output
    assert 'mnemonic' not in result.output.lower()


def test_funding_instructions_separate_funding_from_approval(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness(supported={'USDC': '2'}))
    result = invoke('5\n3\n/usr/bin/buy\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert f'Receiving address: {_ADDRESS}' in flat
    assert 'Network: celo — the guided journey requires Celo Mainnet' in flat
    assert 'Supported tokens only: USDC, USDT, USAT' in flat
    assert 'no separate CELO gas balance is needed' in flat
    assert 'After funding, choose 2 to refresh balances.' in flat
    assert 'Funding a wallet is not approving a paid call' in flat
    assert 'approval happens at the quote screen with an exact cap' in flat


def test_payment_history_shows_local_claims_not_settlement(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness())
    rows = [_payment_row(tx_hash='0x' + 'c' * 64)]
    history = Mock(return_value=rows)
    monkeypatch.setattr(welcome.wallet, 'payment_history', history)
    result = invoke('5\n4\n/usr/bin/buy\n0\n')
    assert result.exit_code == 0, result.output
    history.assert_called_once()
    assert history.call_args.kwargs.get('resolve') is not True
    assert '2026-11-08 15:30:00Z  honeyguider  0.01 USDC on celo  exited' in result.output
    assert 'locally recorded claims' in result.output
    assert 'unverified correlation only' in result.output
    assert 'provider confirmed' not in result.output.lower()


def test_reconciliation_requires_separate_consent(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness())
    history = Mock(return_value=[])
    monkeypatch.setattr(welcome.wallet, 'payment_history', history)
    result = invoke('5\n5\n/usr/bin/buy\nn\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Reconciliation asks the buy CLI to check on-chain settlement status' in _flat(result.output)
    assert 'Reconciliation cancelled. No network read was requested.' in result.output
    history.assert_not_called()


def test_reconciliation_with_consent_resolves_and_correlates(monkeypatch):
    _stub_readiness(monkeypatch, _fake_readiness())
    history = Mock(return_value=[_payment_row(tx_hash='0x' + 'c' * 64)])
    monkeypatch.setattr(welcome.wallet, 'payment_history', history)
    correlate = Mock(return_value='correlated')
    monkeypatch.setattr(welcome.journey, 'correlate_claim', correlate)
    result = invoke('5\n5\n/usr/bin/buy\ny\n/tmp/receipt\n0\n')
    assert result.exit_code == 0, result.output
    assert history.call_args.kwargs.get('resolve') is True
    correlate.assert_called_once()
    assert correlate.call_args.args[0] == Path('/tmp/receipt')
    flat = _flat(result.output)
    assert 'correlation evidence only, never provider authentication of settlement' in flat
    assert _flat(welcome.NO_PROVIDER_CLAIM) in flat


@pytest.mark.parametrize('verdict,expected', [
    ('unavailable', 'No correlation evidence was found; settlement remains UNKNOWN.'),
    ('conflicting', 'Correlation evidence is conflicting or ambiguous; settlement remains UNKNOWN.'),
])
def test_reconciliation_verdict_branches(monkeypatch, verdict, expected):
    _stub_readiness(monkeypatch, _fake_readiness())
    monkeypatch.setattr(welcome.wallet, 'payment_history', Mock(return_value=[_payment_row()]))
    monkeypatch.setattr(welcome.journey, 'correlate_claim', Mock(return_value=verdict))
    result = invoke('5\n5\n/usr/bin/buy\ny\n/tmp/receipt\n0\n')
    assert result.exit_code == 0, result.output
    assert expected in _flat(result.output)
    assert _flat(welcome.NO_PROVIDER_CLAIM) in _flat(result.output)


def test_setup_is_a_printed_proposal_only(tmp_path):
    result = invoke('5\n6\nhoneyguider\n0\n')
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert 'buy setup --name honeyguider' in flat
    assert 'Run this command in your own terminal' in flat
    assert 'OS keychain' in flat
    assert 'Honeyguider never sees or stores it' in flat
    assert '--force' not in result.output and '--import' not in result.output
    assert 'mnemonic' not in result.output.lower() and 'seed phrase' not in result.output.lower()
    assert not (tmp_path / '.honeyguider').exists()


# --- Phase 6: guided tracked-plan journey ----------------------------------


def _fake_plan(count=1):
    return SimpleNamespace(tasks=[SimpleNamespace(id='review', title='Review requirements')][:count])


def _outcome(disposition, destination=None, *, canonical=False, custom=False,
             problems=()):
    return journey.ImportOutcomeData(disposition, destination, None, canonical, custom,
                                     False, tuple(problems))


_GUIDED = ('6\nhttps://docs.example.com/\ninstall package\n'
           'y\n\n\n/usr/bin/buy\ny\n\n\n\n0\n')


def _stub_journey(monkeypatch, tmp_path, *, identity=_wallet_identity(),
                  supported=None, problems=(), plan=None, outcomes=None):
    prepare = Mock(return_value=tmp_path / 'prepared-request.json')
    infer = Mock(return_value=plan if plan is not None else _fake_plan())
    imported = Mock(side_effect=list(outcomes) if outcomes else
                    [_outcome('imported', tmp_path / 'track' / 'plan')])
    # Record the session call as an ordered event as well as echoing a marker. The
    # echo stays harmless; ordering proofs should use `opened.events`, not captured
    # text, because Rich wraps long absolute paths and can split the marker.
    events = []
    opened = Mock(side_effect=lambda ctx, directory=None: (
        events.append(('session', directory)),
        cli.console.print(f'SESSION:{directory}')))
    opened.events = events
    monkeypatch.setattr(welcome.journey, 'prepare', prepare)
    monkeypatch.setattr(welcome.journey, 'infer_with_receipt', infer)
    monkeypatch.setattr(welcome.journey, 'import_outcome', imported)
    monkeypatch.setattr(welcome, 'session', opened)
    _stub_readiness(monkeypatch, _fake_readiness(identity, supported, problems))
    return prepare, infer, imported, opened


def test_guided_journey_happy_path(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)

    # Prove ordering from print/session *events*, not from CliRunner's captured
    # text. Rich wraps long absolute tmp paths, so a printed 'SESSION:<path>'
    # marker may never appear contiguously in result.output. This recorder is
    # scoped to this test so the other _stub_journey callers are unaffected.
    events = opened.events
    original_print = cli.console.print

    def _recording_print(*args, **kwargs):
        if args:
            events.append(('output', args[0]))
        return original_print(*args, **kwargs)

    monkeypatch.setattr(cli.console, 'print', _recording_print)
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert _flat(welcome.PAID_STEP_WARNING) in flat
    assert flat.index(_flat(welcome.PAID_STEP_WARNING)) < flat.index('Validated plan: 1 task(s).')
    assert f'First actionable task: review: Review requirements' in flat

    prepare.assert_called_once()
    url, goal, request_path = prepare.call_args.args
    assert (url, goal) == ('https://docs.example.com/', 'install package')
    assert request_path.name.startswith('req-') and request_path.suffix == '.json'
    assert request_path.parent == journey.DEFAULT_REQUESTS_ROOT

    infer.assert_called_once()
    arguments = infer.call_args.args
    assert arguments[0] == prepare.return_value
    assert arguments[1] == Path('/usr/bin/buy')
    assert arguments[2].parent == journey.DEFAULT_RECEIPTS_ROOT
    assert arguments[2].name.startswith('attempt-')
    assert arguments[3] == 'USDC'
    kwargs = infer.call_args.kwargs
    assert kwargs['account'] == 'honeyguider'
    assert kwargs['expected_payer'] == _ADDRESS
    assert callable(kwargs['prompt']) and callable(kwargs['display'])

    imported.assert_called_once()
    assert imported.call_args.kwargs['tracking_root'] == Path('.honeyguider/track')
    destination = tmp_path / 'track' / 'plan'
    opened.assert_called_once()
    assert opened.call_args.args[1] == destination
    unknown_events = [index for index, (kind, value) in enumerate(events)
                      if kind == 'output' and isinstance(value, str)
                      and _flat(welcome.UNKNOWN_SETTLEMENT) in _flat(value)]
    session_events = [index for index, (kind, _) in enumerate(events) if kind == 'session']
    assert len(unknown_events) == 1
    assert len(session_events) == 1
    assert unknown_events[0] < session_events[0]
    assert _flat(welcome.NO_PROVIDER_CLAIM) in flat
    assert 'provider confirmed' not in flat.lower()


def test_research_consent_no_never_prepares(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)
    result = invoke('6\nhttps://docs.example.com/\ninstall package\nn\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Nothing was retrieved; no files were created.' in result.output
    prepare.assert_not_called()
    infer.assert_not_called()
    imported.assert_not_called()
    opened.assert_not_called()


def test_paid_authorization_refusal_claims_no_settlement(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)
    infer.side_effect = cencori.CencoriError(
        'Approval refused or does not match this session code; no payment attempted')
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    assert 'did not start or was refused' in result.output
    assert 'Payment settlement is UNKNOWN' in result.output
    imported.assert_not_called()
    opened.assert_not_called()
    flat = _flat(result.output).lower()
    for banned in ('provider confirmed', 'settlement confirmed', 'payment confirmed'):
        assert banned not in flat


def test_paid_attempt_platform_error_preserves_request(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)
    infer.side_effect = journey.JourneyError(
        'POSIX advisory locking is unavailable; the paid journey requires a POSIX platform')
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert 'The paid attempt cannot start on this platform or with this request:' in flat
    assert 'POSIX advisory locking is unavailable' in flat
    assert 'The prepared request is preserved at' in flat
    assert str(prepare.return_value) in ''.join(result.output.split())
    assert 'Nothing was charged' not in flat
    imported.assert_not_called()
    opened.assert_not_called()


def test_paid_attempt_receipt_directory_race_preserves_request(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)
    infer.side_effect = FileExistsError('exists')
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert ('receipt directory could not be created (it may have been created concurrently)'
            in flat)
    assert 'Nothing was charged.' in flat
    assert 'The prepared request is preserved at' in flat
    assert str(prepare.return_value) in ''.join(result.output.split())
    imported.assert_not_called()
    opened.assert_not_called()


def test_readiness_identity_unavailable_preserves_request(monkeypatch, tmp_path):
    prepare, infer, imported, opened = _stub_journey(
        monkeypatch, tmp_path, identity=None,
        problems=('No wallet account configured; run setup',))
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\n0\n')
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert 'Wallet identity unavailable' in flat
    assert 'Run 5 → 6 to set up a wallet' in flat
    assert str(tmp_path / 'prepared-request.json') in ''.join(result.output.split())
    infer.assert_not_called()
    imported.assert_not_called()
    opened.assert_not_called()


def test_readiness_not_mainnet_routing_message(monkeypatch, tmp_path):
    _stub_journey(monkeypatch, tmp_path,
                  identity=_wallet_identity(network='celo-sepolia'), problems=('not mainnet',))
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\nn\n0\n')
    assert result.exit_code == 0, result.output
    assert 'requires a Celo Mainnet account' in result.output
    assert 'No attempt started' in result.output


def test_readiness_zero_balance_funding_block(monkeypatch, tmp_path):
    _, infer, imported, _ = _stub_journey(
        monkeypatch, tmp_path, supported={'USDC': '0'},
        problems=('No supported token balance (USDC, USDT, USAT)',))
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\nn\n0\n')
    assert result.exit_code == 0, result.output
    assert 'No supported stablecoin balance detected (USDC, USDT, USAT).' in result.output
    assert 'You can fund and choose 1/2 to refresh' in result.output
    infer.assert_not_called()


def test_readiness_wallet_error_is_bounded(monkeypatch, tmp_path):
    prepare, infer, imported, _ = _stub_journey(monkeypatch, tmp_path)
    monkeypatch.setattr(welcome.wallet, 'readiness', Mock(side_effect=wallet.WalletError('boom')))
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Wallet readiness could not be checked: boom' in result.output
    assert str(tmp_path / 'prepared-request.json') in ''.join(result.output.split())
    infer.assert_not_called()


def test_attempt_in_progress_message(monkeypatch, tmp_path):
    _, infer, imported, opened = _stub_journey(monkeypatch, tmp_path)
    infer.side_effect = journey.AttemptInProgress(Path('/tmp/locks/deadbeef.lock'))
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    assert ("Another attempt holds this request's lock (/tmp/locks/deadbeef.lock). "
            'Nothing was started.') in _flat(result.output)
    imported.assert_not_called()
    opened.assert_not_called()


def test_import_custom_root_consent_retries_once(monkeypatch, tmp_path):
    destination = Path('/tmp/custom/track/plan')
    _, infer, imported, opened = _stub_journey(monkeypatch, tmp_path, outcomes=[
        _outcome('custom_consent_required', destination, canonical=True, custom=True,
                 problems=('Custom tracking root requires explicit consent',)),
        _outcome('imported', destination, custom=True),
    ])
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\ny\n'
                    '\n\n/custom/track\ny\n0\n')
    assert result.exit_code == 0, result.output
    assert imported.call_count == 2
    first, second = imported.call_args_list
    assert first.kwargs['tracking_root'] == Path('/custom/track')
    assert second.kwargs['tracking_root'] == Path('/custom/track')
    assert second.kwargs['custom_root_consent'] is True
    opened.assert_called_once()
    assert opened.call_args.args[1] == destination


def test_import_custom_root_refusal_does_not_retry(monkeypatch, tmp_path):
    _, _, imported, opened = _stub_journey(monkeypatch, tmp_path, outcomes=[
        _outcome('custom_consent_required', Path('/tmp/custom/track/plan'),
                 canonical=True, custom=True, problems=('Custom tracking root requires explicit consent',)),
    ])
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\ny\n'
                    '\n\n/custom/track\nn\n0\n')
    assert result.exit_code == 0, result.output
    assert 'No additional record created.' in result.output
    assert imported.call_count == 1
    opened.assert_not_called()


@pytest.mark.parametrize('disposition', ['conflict', 'unimportable', 'interrupted_destination'])
def test_unimportable_dispositions_preserve_artifacts(monkeypatch, tmp_path, disposition):
    _, _, imported, opened = _stub_journey(monkeypatch, tmp_path, outcomes=[
        _outcome(disposition, tmp_path / 'track' / 'plan',
                 problems=(f'{disposition} problem',))])
    result = invoke(_GUIDED)
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert f'Import problem: {disposition} problem' in flat
    assert 'preserved at' in flat
    assert 'resume or inspect them later from 2 → 3' in flat
    opened.assert_not_called()


# --- Phase 6: resumption by number -----------------------------------------


def test_continue_lists_tracked_plans_and_opens_selected_number(monkeypatch, tmp_path):
    healthy = tmp_path / 'plan-a'
    corrupt = tmp_path / 'plan-b'
    monkeypatch.setattr(welcome.journey, 'list_tracked_plans', Mock(return_value=[
        journey.TrackedPlanSummary(healthy, 'a' * 64, 'b' * 64, 3, 1, 'unknown', ()),
        journey.TrackedPlanSummary(corrupt, None, None, 0, 0, 'unknown',
                                   ('unreadable or malformed tracking directory: boom',)),
    ]))
    infer = Mock(side_effect=AssertionError('resumption must never pay'))
    monkeypatch.setattr(welcome.journey, 'infer_with_receipt', infer)
    monkeypatch.setattr(welcome.paid, 'infer', Mock(side_effect=AssertionError('paid called')))
    opened = Mock(side_effect=lambda ctx, directory=None: cli.console.print(f'SESSION:{directory}'))
    monkeypatch.setattr(welcome, 'session', opened)

    result = invoke('2\n3\n1\n0\n')
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert '1: plan-a — tasks 1/3 completed; attempt/settlement: unknown' in flat
    assert '2: plan-b — tasks 0/0 completed; attempt/settlement: unknown' in flat
    assert 'Problem: unreadable or malformed tracking directory: boom' in flat
    opened.assert_called_once()
    assert opened.call_args.args[1] == healthy
    infer.assert_not_called()


def test_continue_accepts_a_tracking_path(monkeypatch, tmp_path):
    listed = tmp_path / 'listed-plan'
    monkeypatch.setattr(welcome.journey, 'list_tracked_plans', Mock(return_value=[
        journey.TrackedPlanSummary(listed, 'a' * 64, 'b' * 64, 1, 0, 'unknown', ())]))
    opened = Mock(side_effect=lambda ctx, directory=None: cli.console.print(f'SESSION:{directory}'))
    monkeypatch.setattr(welcome, 'session', opened)
    result = invoke('2\n3\n/custom/track\n0\n')
    assert result.exit_code == 0, result.output
    opened.assert_called_once()
    assert opened.call_args.args[1] == Path('/custom/track')

    opened.reset_mock()
    result = invoke('2\n3\n\n0\n')
    assert result.exit_code == 0, result.output
    assert 'No tracked plans found.' not in result.output
    opened.assert_not_called()  # an empty answer re-lists and returns to the main menu.


def test_continue_with_no_tracked_plans_returns_to_menu(monkeypatch):
    monkeypatch.setattr(welcome.journey, 'list_tracked_plans', Mock(return_value=[]))
    opened = Mock()
    monkeypatch.setattr(welcome, 'session', opened)
    result = invoke('2\n3\n0\n')
    assert result.exit_code == 0, result.output
    assert 'No tracked plans found.' in result.output
    opened.assert_not_called()


def test_guided_journey_rejects_unsupported_token_then_accepts(monkeypatch, tmp_path):
    _, infer, _, _ = _stub_journey(monkeypatch, tmp_path)
    result = invoke('6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\ny\n'
                    'DOGE\nUSDT\n\n\n0\n')
    assert result.exit_code == 0, result.output
    assert 'Unsupported token. Choose USDC, USDT or USAT.' in _flat(result.output)
    infer.assert_called_once()
    assert infer.call_args.args[3] == 'USDT'


def test_guided_journey_rejects_existing_receipt_directory(monkeypatch, tmp_path):
    _, infer, _, _ = _stub_journey(monkeypatch, tmp_path)
    taken = tmp_path / 'taken-receipt'
    taken.mkdir()
    result = invoke(f'6\nhttps://docs.example.com/\ninstall package\ny\n\n\n/usr/bin/buy\ny\n'
                    f'\n{taken}\n\n\n0\n')
    assert result.exit_code == 0, result.output
    assert 'That receipt directory already exists; choose a new path.' in _flat(result.output)
    infer.assert_called_once()
    assert infer.call_args.args[2] != taken
    assert not list(taken.iterdir())


def test_help_states_paid_inference_is_guided_only():
    result = invoke('4\n0\n')
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert ("Paid inference is available only through the guided 'Create a tracked plan' "
            'flow, which shows the exact quote and requires your explicit approval code.') in flat


def test_welcome_imports_journey_without_initializing_locking():
    assert callable(journey.acquire_attempt_lock)
    assert callable(journey.list_tracked_plans)
    assert journey.DEFAULT_REQUESTS_ROOT == Path('.honeyguider/requests')
    assert journey.DEFAULT_RECEIPTS_ROOT == Path('.honeyguider/receipts')
    assert not hasattr(journey, 'fcntl')  # import remains function-local


def test_continue_out_of_range_number_relists(monkeypatch, tmp_path):
    listed = tmp_path / 'plan-a'
    monkeypatch.setattr(welcome.journey, 'list_tracked_plans', Mock(return_value=[
        journey.TrackedPlanSummary(listed, 'a' * 64, 'b' * 64, 2, 1, 'unknown', ())]))
    opened = Mock()
    monkeypatch.setattr(welcome, 'session', opened)
    result = invoke('2\n3\n9\n1\n0\n')
    assert result.exit_code == 0, result.output
    assert 'No plan has that number.' in result.output
    opened.assert_called_once()
    assert opened.call_args.args[1] == listed
