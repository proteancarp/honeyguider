"""Offline, deterministic tests for the read-only wallet inspection module."""
import builtins
import os
import pathlib
import subprocess

import pytest

from honeyguider import wallet

BUY = '/trusted/buy'
ADDRESS = '0x2D99C62C26BcE3C9d96181cea61dC12E7DB79759'
ADDRESS2 = '0x1111111111111111111111111111111111111111'
TX_HASH = '0x' + 'ab' * 32
IDENTITY_STDOUT = (
    'buy on celo\n'
    f'  pays from {ADDRESS}\n'
    '  balances 0 CELO, 0.03 USDC, 0 USDT, 0 USAT, 0 USDm\n'
).encode()
SEPOLIA_STDOUT = (
    'buy on celo-sepolia\n'
    f'  pays from {ADDRESS}\n'
    '  balances 0 CELO, 0.03 USDC\n'
).encode()
NO_ACCOUNT_STDOUT = (b'{"error":{"code":"no_account",'
                     b'"message":"No account configured. Run `buy setup` first."}}\n')
DEFAULT_ACCOUNTS_STDOUT = f'* buy  mainnet  {ADDRESS}  no cap\n'.encode()
CAPPED_ACCOUNTS_STDOUT = f'* buy  mainnet  {ADDRESS}  0.05 weekly\n'.encode()
ENTRY_LINE = '2026-11-01 15:42:03Z  buy  0.01 USDC on celo confirmed [HTTP 200]\n'
CONTINUATION_LINE = f'  https://gateway.usebuy.ai/cencori/v1/chat/completions  {TX_HASH}\n'
ENV_KEYS = {'PATH', 'HOME', 'LANG', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR'}


def runner(stdout=b'', stderr=b'', returncode=0):
    """Fake runner: records argv, returns a precise CompletedProcess."""
    calls = []

    def fake(arguments):
        calls.append(list(arguments))
        return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)

    fake.calls = calls
    return fake


def both(identity_stdout, accounts_stdout=DEFAULT_ACCOUNTS_STDOUT, returncode=0):
    """Fake runner answering both whoami and --json account list calls."""

    def fake(arguments):
        if '--json' in arguments:
            return subprocess.CompletedProcess(arguments, returncode, accounts_stdout, b'')
        return subprocess.CompletedProcess(arguments, returncode, identity_stdout, b'')

    return fake


def dead_runner(arguments):
    raise OSError(8, 'Exec format error')


def test_identity_happy_path_default_account():
    fake = runner(IDENTITY_STDOUT)
    result = wallet.identity('buy', runner=fake)
    assert result == wallet.WalletIdentity(
        'buy', 'celo', ADDRESS,
        {'CELO': '0', 'USDC': '0.03', 'USDT': '0', 'USAT': '0', 'USDm': '0'})
    assert fake.calls == [['buy', 'whoami']]


def test_identity_explicit_account_argv():
    fake = runner(IDENTITY_STDOUT)
    result = wallet.identity(BUY, 'honeyguider', runner=fake)
    assert result == wallet.WalletIdentity(
        'buy', 'celo', ADDRESS,
        {'CELO': '0', 'USDC': '0.03', 'USDT': '0', 'USAT': '0', 'USDm': '0'})
    assert fake.calls == [[BUY, '--account', 'honeyguider', 'whoami']]


def test_identity_sepolia_parses_as_explicit_non_mainnet():
    fake = runner(SEPOLIA_STDOUT)
    result = wallet.identity(BUY, runner=fake)
    assert result.network == 'celo-sepolia'
    assert result.name == 'buy' and result.address == ADDRESS
    assert result.balances == {'CELO': '0', 'USDC': '0.03'}


@pytest.mark.parametrize('returncode', [0, 1])
def test_no_account_envelope_routes_to_setup(returncode):
    fake = runner(NO_ACCOUNT_STDOUT, returncode=returncode)
    with pytest.raises(wallet.WalletUnavailable) as excinfo:
        wallet.identity(BUY, runner=fake)
    assert 'buy setup' in str(excinfo.value)


def test_other_error_code_is_plain_wallet_error():
    fake = runner(b'{"error":{"code":"keychain_locked","message":"locked"}}', returncode=1)
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY, runner=fake)
    assert type(excinfo.value) is wallet.WalletError


def malformed_cases():
    pay = f'  pays from {ADDRESS}\n'.encode()
    balances = b'  balances 0 CELO, 0.03 USDC\n'
    header = b'buy on celo\n'
    return [
        pytest.param(b'\n', id='blank_stdout'),
        pytest.param(b'', id='stderr_only_error'),
        pytest.param(b'buy on celo\n' + pay + balances + b'dipped in honey\n', id='trailing_junk'),
        pytest.param(b'buy on\n' + pay + balances, id='network_missing'),
        pytest.param(header + f'  pays from {ADDRESS[:-1]}\n'.encode() + balances,
                     id='address_39_hex'),
        pytest.param(header + f'  pays from {ADDRESS}a\n'.encode() + balances,
                     id='address_41_hex'),
        pytest.param(header + pay + b'  balances\n', id='balances_line_missing'),
        pytest.param(header + pay + pay + balances, id='second_pays_from_line'),
        pytest.param(NO_ACCOUNT_STDOUT + b'junk\n', id='error_envelope_plus_junk'),
    ]


@pytest.mark.parametrize('stdout', malformed_cases())
def test_identity_malformed_output_fails_closed(stdout):
    for returncode in (0, 1):
        fake = runner(stdout, stderr=b'fatal: boom', returncode=returncode)
        with pytest.raises(wallet.WalletError) as excinfo:
            wallet.identity(BUY, runner=fake)
        assert type(excinfo.value) is wallet.WalletError


def test_identity_failure_messages_stay_under_budget():
    fake = runner(b'x' * 500, returncode=0)
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY, runner=fake)
    assert str(excinfo.value).count('x' * 121) == 0


def test_accounts_parses_default_and_multiple_rows():
    stdout = (
        f'* buy  mainnet  {ADDRESS}  no cap\n'
        f'other  sepolia  {ADDRESS2}  0.05 weekly\n'
    ).encode()
    fake = runner(stdout)
    rows = wallet.accounts(BUY, runner=fake)
    assert rows == [
        wallet.AccountRow('buy', 'mainnet', ADDRESS, 'no cap', True),
        wallet.AccountRow('other', 'sepolia', ADDRESS2, '0.05 weekly', False),
    ]
    assert fake.calls == [[BUY, '--json', 'account', 'list']]


def test_accounts_missing_default_row_is_ok():
    fake = runner(f'only  mainnet  {ADDRESS}  no cap\n'.encode())
    rows = wallet.accounts(BUY, runner=fake)
    assert [row.name for row in rows] == ['only']
    assert all(not row.default for row in rows)


@pytest.mark.parametrize('stdout', [
    pytest.param(f'* buy  mainnet  {ADDRESS} no cap\n'.encode(), id='single_space_separator'),
    pytest.param(f'* buy  mainnet  {ADDRESS}\n'.encode(), id='cap_missing'),
    pytest.param(b'\n', id='blank_stdout'),
    pytest.param(b'{"rows":[]}\n', id='json_garbage'),
])
def test_accounts_malformed_output_fails_closed(stdout):
    fake = runner(stdout)
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.accounts(BUY, runner=fake)
    assert type(excinfo.value) is wallet.WalletError


def test_accounts_nonzero_exit_fails_closed():
    fake = runner(DEFAULT_ACCOUNTS_STDOUT, returncode=1)
    with pytest.raises(wallet.WalletError):
        wallet.accounts(BUY, runner=fake)


def test_payment_history_parses_entry_and_continuation():
    fake = runner((ENTRY_LINE + CONTINUATION_LINE).encode())
    rows = wallet.payment_history(BUY, runner=fake)
    assert rows == [wallet.PaymentRow(
        '2026-11-01 15:42:03Z', 'buy', '0.01', 'USDC', 'celo', 'confirmed', '200',
        'https://gateway.usebuy.ai/cencori/v1/chat/completions', TX_HASH)]
    assert fake.calls == [[BUY, 'receipts']]


def test_payment_history_resolve_argv():
    fake = runner((ENTRY_LINE + CONTINUATION_LINE).encode())
    rows = wallet.payment_history(BUY, resolve=True, runner=fake)
    assert rows[0].tx_hash == TX_HASH
    assert fake.calls == [[BUY, 'receipts', '--resolve']]


def test_payment_history_missing_continuation_fields_none():
    fake = runner(ENTRY_LINE.encode())
    rows = wallet.payment_history(BUY, runner=fake)
    assert rows == [wallet.PaymentRow(
        '2026-11-01 15:42:03Z', 'buy', '0.01', 'USDC', 'celo', 'confirmed', '200', None, None)]


def test_payment_history_consecutive_entries_without_continuation():
    fake = runner((ENTRY_LINE + ENTRY_LINE).encode())
    rows = wallet.payment_history(BUY, runner=fake)
    assert len(rows) == 2
    for row in rows:
        assert row.resource is None and row.tx_hash is None


@pytest.mark.parametrize('stdout', [
    pytest.param(
        (ENTRY_LINE + f'  https://gateway.usebuy.ai/cencori/v1/x  {"ab" * 31}c\n').encode(),
        id='malformed_tx_hash'),
    pytest.param(
        (ENTRY_LINE + f'  {"ab" * 32}\n').encode(), id='tx_hash_missing_0x'),
    pytest.param(
        (ENTRY_LINE + f'  https://only-one-column {TX_HASH}\n').encode(), id='single_space_column'),
    pytest.param(
        '2026-11-01 15:42:03  buy  0.01 USDC on celo confirmed [HTTP 200]\n'.encode(),
        id='timestamp_without_z'),
    pytest.param(
        '2026-11-01 15:42:03Z  buy  0.0.1 USDC on celo confirmed [HTTP 200]\n'.encode(),
        id='garbage_amount'),
    pytest.param(
        '2026-11-01 15:42:03Z  buy  0.01 USDC on celo confirmed\n'.encode(),
        id='http_marker_missing'),
])
def test_payment_history_malformed_lines_fail_closed(stdout):
    fake = runner(stdout)
    with pytest.raises(wallet.WalletError):
        wallet.payment_history(BUY, runner=fake)


def test_payment_history_nonzero_exit_fails_closed():
    fake = runner((ENTRY_LINE + CONTINUATION_LINE).encode(), returncode=1)
    with pytest.raises(wallet.WalletError):
        wallet.payment_history(BUY, runner=fake)


def test_readiness_full_mainnet_happy_path():
    fake = both(IDENTITY_STDOUT)
    result = wallet.readiness(BUY, runner=fake)
    assert result.executable_ok is True
    assert result.identity is not None and result.identity.network == 'celo'
    assert result.default is True
    assert result.supported_balances == {'USDC': '0.03', 'USDT': '0', 'USAT': '0'}
    assert result.problems == ()


def test_readiness_cap_uses_default_row_remainder():
    fake = both(IDENTITY_STDOUT, CAPPED_ACCOUNTS_STDOUT)
    result = wallet.readiness(BUY, runner=fake)
    assert result.cap == '0.05 weekly'


def test_readiness_cap_none_for_no_cap_row():
    fake = both(IDENTITY_STDOUT)
    assert wallet.readiness(BUY, runner=fake).cap is None


def test_readiness_missing_executable_reports_problems():
    result = wallet.readiness(BUY, runner=dead_runner)
    assert result.executable_ok is False
    assert result.identity is None
    assert result.cap is None and result.supported_balances == {}
    assert result.problems and all(isinstance(problem, str) for problem in result.problems)


def test_readiness_no_account_routes_to_setup():
    fake = runner(NO_ACCOUNT_STDOUT)
    result = wallet.readiness(BUY, runner=fake)
    assert result.executable_ok is True
    assert result.identity is None
    assert 'No wallet account configured; run setup' in result.problems


def test_readiness_sepolia_flags_not_mainnet():
    fake = both(SEPOLIA_STDOUT)
    result = wallet.readiness(BUY, runner=fake)
    assert result.executable_ok is True
    assert 'not mainnet' in result.problems


def test_readiness_zero_supported_balances_is_a_problem():
    zero = ('buy on celo\n'
            f'  pays from {ADDRESS}\n'
            '  balances 0 CELO, 0 USDC, 0 USDT, 0 USAT\n').encode()
    result = wallet.readiness(BUY, runner=both(zero))
    assert result.supported_balances == {'USDC': '0', 'USDT': '0', 'USAT': '0'}
    assert any('No supported token balance (USDC, USDT, USAT)' in problem
               for problem in result.problems)


def test_readiness_positive_usdc_has_no_balance_problem():
    result = wallet.readiness(BUY, runner=both(IDENTITY_STDOUT))
    assert result.supported_balances['USDC'] == '0.03'
    assert all('No supported token balance' not in problem for problem in result.problems)


def test_readiness_usdm_only_is_unsupported_alone():
    usdm_only = ('buy on celo\n'
                 f'  pays from {ADDRESS}\n'
                 '  balances 0 USDm\n').encode()
    result = wallet.readiness(BUY, runner=both(usdm_only))
    assert result.supported_balances == {}
    assert 'USDm' not in result.supported_balances
    assert any('No supported token balance (USDC, USDT, USAT)' in problem
               for problem in result.problems)


def test_supported_tokens_boundary():
    assert wallet.SUPPORTED_TOKENS == ('USDC', 'USDT', 'USAT')
    assert 'USDm' not in wallet.SUPPORTED_TOKENS
    assert 'CELO' not in wallet.SUPPORTED_TOKENS


def test_setup_command_exact_argv():
    assert wallet.setup_command() == ['buy', 'setup', '--name', 'honeyguider']
    assert wallet.setup_command('travel') == ['buy', 'setup', '--name', 'travel']


def test_setup_command_is_pure_never_force_or_import():
    argv = wallet.setup_command('travel')
    assert wallet.setup_command('travel') == argv
    assert argv[0] == 'buy' and argv[1] == 'setup'
    assert argv.index('--name') == 2 and argv[3] == 'travel'
    assert '--force' not in argv and '--import' not in argv
    assert len(argv) == 4


@pytest.mark.parametrize('name', ['', '--force', '--', 'a\x00b', 'a\x1fb', 'a\x7fb', 'a\nb'])
def test_setup_command_rejects_unsafe_names(name):
    with pytest.raises(wallet.WalletError):
        wallet.setup_command(name)


@pytest.mark.parametrize('error', [OSError('no exec'), KeyError('boom'),
                                   subprocess.TimeoutExpired(['buy'], 5)])
def test_injected_runner_failures_fail_closed(error):
    def broken(arguments):
        raise error

    with pytest.raises(wallet.WalletError):
        wallet.identity(BUY, runner=broken)
    with pytest.raises(wallet.WalletError):
        wallet.accounts(BUY, runner=broken)
    with pytest.raises(wallet.WalletError):
        wallet.payment_history(BUY, runner=broken)
    reported = wallet.readiness(BUY, runner=broken)
    assert reported.executable_ok is False
    assert isinstance(reported.problems, tuple) and reported.problems


@pytest.mark.parametrize('error', [OSError('cannot exec'), subprocess.TimeoutExpired(['buy'], 30)])
def test_default_run_failures_wrapped(monkeypatch, error):
    def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(subprocess, 'run', failing)
    with pytest.raises(wallet.WalletError):
        wallet.identity(BUY)


def test_default_run_wraps_arbitrary_exceptions(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('internal provider breakage')

    monkeypatch.setattr(subprocess, 'run', broken)
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY)
    assert 'RuntimeError' in str(excinfo.value)
    assert 'breakage' not in str(excinfo.value)


def test_default_run_binds_private_environment_and_devnull(monkeypatch):
    captured = {}

    def fake_run(arguments, **kwargs):
        captured.update(kwargs)
        captured['arguments'] = list(arguments)
        return subprocess.CompletedProcess(arguments, 0, DEFAULT_ACCOUNTS_STDOUT, b'')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setenv('SECRET_PROVIDER_KEY', 'must-not-leak')
    rows = wallet.accounts('buy')
    assert rows == [wallet.AccountRow('buy', 'mainnet', ADDRESS, 'no cap', True)]
    assert captured['arguments'] == ['buy', '--json', 'account', 'list']
    assert captured['timeout'] == 30
    assert captured['capture_output'] is True
    assert captured['stdin'] is subprocess.DEVNULL
    assert set(captured) == {'arguments', 'capture_output', 'timeout', 'stdin', 'env'}
    assert set(captured['env']) <= ENV_KEYS


def test_private_env_is_whitelist_only(monkeypatch):
    monkeypatch.setenv('SECRET_PROVIDER_KEY', 'nope')
    monkeypatch.setenv('NODE_OPTIONS', '--evil')
    monkeypatch.delenv('DBUS_SESSION_BUS_ADDRESS', raising=False)
    env = wallet.private_env()
    assert set(env) <= ENV_KEYS
    assert {'PATH', 'HOME'} <= set(env)
    assert 'DBUS_SESSION_BUS_ADDRESS' not in env
    assert 'SECRET_PROVIDER_KEY' not in env and 'NODE_OPTIONS' not in env


def test_wallet_module_never_opens_files_and_never_prints(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('wallet.py attempted filesystem access')

    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(pathlib.Path, 'open', forbidden)
    identity_fake = runner(IDENTITY_STDOUT)
    accounts_fake = runner(DEFAULT_ACCOUNTS_STDOUT)
    payments_fake = runner((ENTRY_LINE + CONTINUATION_LINE).encode())
    result = wallet.identity(BUY, runner=identity_fake)
    assert result.network == 'celo'
    assert len(wallet.accounts(BUY, runner=accounts_fake)) == 1
    assert len(wallet.payment_history(BUY, resolve=True, runner=payments_fake)) == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == ''


def test_identity_duplicate_balance_token_fails_closed():
    stdout = ('buy on celo\n'
              f'  pays from {ADDRESS}\n'
              '  balances 0.01 USDC, 0.02 USDC\n').encode()
    fake = runner(stdout)
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY, runner=fake)
    assert type(excinfo.value) is wallet.WalletError
    assert 'repeated balance token' in str(excinfo.value)
    assert len(str(excinfo.value)) < 60  # bounded message; full stdout never echoed


def test_identity_crlf_line_endings_are_refused():
    fake = runner(IDENTITY_STDOUT.replace(b'\n', b'\r\n'))
    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY, runner=fake)
    assert type(excinfo.value) is wallet.WalletError


@pytest.mark.parametrize('account', ['', '--force', '--', 'a\x00b', 'a\x7fb', 'a\nb', 'a b', '\t'])
def test_identity_rejects_unsafe_account_names_without_running(account):
    def sentinel(arguments):
        pytest.fail('subprocess invocation reached the runner')

    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.identity(BUY, account=account, runner=sentinel)
    assert type(excinfo.value) is wallet.WalletError
    assert len(str(excinfo.value)) < 200  # bounded excerpt, never the raw value chain


def test_readiness_explicit_account_matching_row_has_no_problem():
    stdout = (f'other  mainnet  {ADDRESS2}  no cap\n'
              f'* honeyguider  mainnet  {ADDRESS}  no cap\n').encode()
    result = wallet.readiness(BUY, 'honeyguider', runner=both(IDENTITY_STDOUT, stdout))
    assert not any('not found in account list' in problem for problem in result.problems)
    assert result.problems == ()
    assert result.default is True


def test_readiness_explicit_account_missing_row_reports_problem():
    result = wallet.readiness(BUY, 'ghost', runner=both(IDENTITY_STDOUT))
    assert any('not found in account list' in problem for problem in result.problems)
    assert result.cap is None
    assert result.default is False


def test_wallet_error_is_value_error():
    assert issubclass(wallet.WalletError, ValueError)
    assert issubclass(wallet.WalletUnavailable, wallet.WalletError)
