"""Read-only wallet inspection and consensual setup for the pinned Celo buy 0.8.4 CLI.

Never touches or displays key material. Every verdict comes from the exact
documented output shape of the pinned binary, never from a return code alone
(``buy whoami`` exits 0 even for a missing account), and any unrecognized
output, unreadable executable, or timeout fails closed as WalletError.
Sepolia identities parse as an explicit non-mainnet result that callers must
refuse. USDm balances parse as raw information but are never supported journey
funds (SUPPORTED_TOKENS only). No console output, no networking, no secrets.
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

DEFAULT_ACCOUNT = 'honeyguider'
SUPPORTED_TOKENS = ('USDC', 'USDT', 'USAT')

# Only OS session context needed for the EXISTING system keychain. Mirrors
# paid.wallet_environment(): no BUY_* overrides, private keys, provider
# credentials, NODE_OPTIONS or curl config are ever read or forwarded.
_ENV_KEYS = frozenset({
    'PATH', 'HOME', 'LANG', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR',
})
_EXCERPT = 120

# Verified whoami identity shape; the whole stdout must be exactly these three
# lines (a trailing line ending is tolerated), MULTILINE per family convention.
_IDENTITY = re.compile(
    r'(\S+) on (celo|celo-sepolia)\n'
    r'  pays from (0x[0-9a-fA-F]{40})\n'
    r'  balances ([0-9]+(?:\.[0-9]+)? [A-Za-z]+(?:, [0-9]+(?:\.[0-9]+)? [A-Za-z]+)*)\Z',
    re.MULTILINE)
# Verified `buy --json account list` row: optional default star, double spaces.
_ACCOUNT_ROW = re.compile(r'(?:(\*) )?(\S+)  (\S+)  (0x[0-9a-fA-F]{40})  (.+)$')
# Verified receipts entry line and its two-space-indented continuation line.
_PAYMENT_ROW = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z)  (\S+)  '
    r'([0-9]+(?:\.[0-9]+)?) ([A-Za-z]+) on (\S+) (\S+) \[HTTP ([0-9]+)\]$')
_PAYMENT_CONTINUATION = re.compile(r'  (\S+)  (0x[0-9a-fA-F]{64})$')


class WalletError(ValueError):
    """Any refused or failed wallet parse or runtime; always fails closed."""


class WalletUnavailable(WalletError):
    """The verified ``no_account`` error envelope was observed; route to setup."""


@dataclass(frozen=True)
class WalletIdentity:
    name: str
    network: str
    address: str
    balances: dict[str, str]  # Raw parsed tokens, including USDm/CELO.


@dataclass(frozen=True)
class AccountRow:
    name: str
    network: str
    address: str
    cap: str
    default: bool


@dataclass(frozen=True)
class PaymentRow:
    date: str
    account: str
    amount: str
    token: str
    network: str
    state: str
    http_code: str | None
    resource: str | None
    tx_hash: str | None


@dataclass(frozen=True)
class WalletReadiness:
    executable_ok: bool
    identity: WalletIdentity | None
    cap: str | None
    default: bool
    supported_balances: dict[str, str]
    problems: tuple[str, ...]


def _effective_amount(amount):
    """Zero-safe decimal for regex-bounded balance amounts; fail closed on junk."""
    try:
        return Decimal(amount)
    except InvalidOperation as exc:
        raise WalletError(f'Unparseable balance amount: {_excerpt(amount)}') from exc


def _validated_account(account):
    """Same spirit as setup_command, plus whitespace: refuse unsafe account names."""
    if (not account or account.startswith('--')
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in account)
            or any(ch.isspace() for ch in account)):
        raise WalletError(f'Wallet account name must be nonempty, without a -- prefix, '
                          f'whitespace or control characters: {_excerpt(account)}')
    return account


def _excerpt(text):
    if not isinstance(text, str):
        text = '' if text is None else str(text)
    return repr(text[:_EXCERPT])


def _stream(value):
    """Decode a runner's stream; never raises on unusual bytes."""
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _binary(buy):
    return str(buy)


def private_env():
    """The five OS session keys only, when present; never any other variable."""
    return {key: value for key, value in os.environ.items() if key in _ENV_KEYS}


def _run(buy, arguments, *, timeout=30, runner=None):
    """Execute one bounded read command with the private session environment.

    The injected runner is called as ``runner(arguments)`` and must return an
    object with ``.returncode``, ``.stdout`` and ``.stderr``. Every failure of
    the runner or of the default subprocess path fails closed as WalletError.
    """
    if runner is not None:
        try:
            return runner(arguments)
        except WalletError:
            raise
        except Exception as exc:
            raise WalletError(f'Wallet command runner failed: {type(exc).__name__}') from exc
    try:
        return subprocess.run(arguments, capture_output=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, env=private_env())
    except Exception as exc:
        raise WalletError(f'Wallet command failed before producing output: {type(exc).__name__}') from exc


def _error_envelope(text):
    """Return the error code of a JSON envelope, or None if not envelope-shaped."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        envelope = json.loads(stripped)
    except ValueError:
        return None
    if isinstance(envelope, dict) and isinstance(envelope.get('error'), dict):
        code = envelope['error'].get('code')
        if isinstance(code, str):
            return code
    return None


def identity(buy, account=None, *, runner=None):
    """Strictly parse `buy [account] whoami`; verdict by shape, never return code."""
    if account is not None:
        _validated_account(account)
    argv = [_binary(buy), *(['--account', account] if account else []), 'whoami']
    result = _run(buy, argv, runner=runner)
    text = _stream(result.stdout)
    match = _IDENTITY.fullmatch(text.rstrip('\r\n'))
    if match is None:
        code = _error_envelope(text)
        if code == 'no_account':
            raise WalletUnavailable('No account configured. Run `buy setup` first.')
        if code is not None:
            raise WalletError(f'buy whoami refused with error code {code}')
        raise WalletError(f'buy whoami output has no identity shape: {_excerpt(text)}')
    balances = {}
    for pair in match.group(4).split(', '):
        amount, _, token = pair.partition(' ')
        if token in balances:
            raise WalletError(f'buy whoami repeated balance token {token}')
        balances[token] = amount
    return WalletIdentity(match.group(1), match.group(2), match.group(3), balances)


def accounts(buy, *, runner=None):
    """Strictly parse `buy --json account list` rows, or fail closed."""
    argv = [_binary(buy), '--json', 'account', 'list']
    result = _run(buy, argv, runner=runner)
    if result.returncode != 0:
        raise WalletError(f'buy account list exited {result.returncode}')
    rows = []
    for line in _stream(result.stdout).splitlines():
        if not line:
            continue
        match = _ACCOUNT_ROW.fullmatch(line)
        if match is None:
            raise WalletError(f'buy account list row has no known shape: {_excerpt(line)}')
        rows.append(AccountRow(match.group(2), match.group(3), match.group(4),
                               match.group(5), match.group(1) == '*'))
    if not rows:
        raise WalletError('buy account list produced no rows')
    return rows


def payment_history(buy, *, resolve=False, runner=None):
    """Strictly parse `buy receipts [--resolve]` rows, or fail closed per row."""
    argv = [_binary(buy), 'receipts']
    if resolve:
        argv.append('--resolve')
    result = _run(buy, argv, runner=runner)
    if result.returncode != 0:
        raise WalletError(f'buy receipts exited {result.returncode}')
    rows = []
    current = None
    for line in _stream(result.stdout).splitlines():
        if not line:
            continue
        if current is not None:
            continuation = _PAYMENT_CONTINUATION.fullmatch(line)
            if continuation is None:
                entry = _PAYMENT_ROW.fullmatch(line)
                if entry is None:
                    raise WalletError(
                        f'buy receipts continuation line has no known shape: {_excerpt(line)}')
                rows.append(PaymentRow(*current, None, None))
                current = entry.groups()
                continue
            rows.append(PaymentRow(*current, continuation.group(1), continuation.group(2)))
            current = None
            continue
        entry = _PAYMENT_ROW.fullmatch(line)
        if entry is None:
            raise WalletError(f'buy receipts entry line has no known shape: {_excerpt(line)}')
        current = entry.groups()
    if current is not None:
        rows.append(PaymentRow(*current, None, None))
    return rows


def readiness(buy, account=None, *, runner=None):
    """Report journey readiness as problems; never raises for refusal or failure.

    Every WalletError from any call chain into readiness becomes a problems
    entry, never an exception. The executable is deemed ok only on a
    well-parsed identity or the verified ``no_account`` envelope. USDm/CELO
    balances are informational only.
    """
    problems: list[str] = []
    ident = None
    executable_ok = False
    try:
        ident = identity(buy, account, runner=runner)
        executable_ok = True
    except WalletUnavailable:
        executable_ok = True
        problems.append('No wallet account configured; run setup')
    except WalletError as exc:
        problems.append(str(exc))
    supported: dict[str, str] = {}
    cap = None
    default = False
    if ident is not None:
        if ident.network != 'celo':
            problems.append('not mainnet')
        try:
            supported = {token: amount for token, amount in ident.balances.items()
                         if token in SUPPORTED_TOKENS}
            if all(_effective_amount(amount) == 0 for amount in supported.values()):
                problems.append('No supported token balance (' + ', '.join(SUPPORTED_TOKENS) + ')')
        except WalletError:
            supported = {}
            problems.append('Could not evaluate supported token balances')
        try:
            rows = accounts(buy, runner=runner)
        except WalletError as exc:
            problems.append(str(exc))
        else:
            if account is not None:
                row = next((candidate for candidate in rows if candidate.name == account), None)
                if row is None:
                    problems.append(f'Account {_excerpt(account)} not found in account list')
            else:
                row = next((candidate for candidate in rows if candidate.default), None)
            if row is not None:
                default = row.default
                cap = None if row.cap == 'no cap' else row.cap
    return WalletReadiness(executable_ok, ident, cap, default, supported, tuple(problems))


def setup_command(name=DEFAULT_ACCOUNT):
    """Pure proposal: consent-bound setup argv. NEVER --force, NEVER --import."""
    if not name or name.startswith('--') or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise WalletError('Setup account name must be nonempty, without control '
                          'characters and without a leading --')
    return ['buy', 'setup', '--name', name]
