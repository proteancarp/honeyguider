"""One interactive, explicitly approved inference attempt; never retries."""
import base64
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

from . import cencori
from .planning import PlanError, _object, _text, validate_plan
from .research import CODE_CHARS, MAX_BLOCKS, MAX_EXCERPTS, TEXT_CHARS, safe_url

RESPONSE_BYTES = 128 * 1024
QUOTE_BYTES = 128 * 1024  # Per stream; preserve only this prefix on overflow.
PILOT_CEILING = Decimal('0.05')
# Mainnet token contracts/decimals verified against installed buy-core 0.8.4.
TOKENS = {
    'USDC': '0xceba9300f2b948710d2653dd7b07f33a8b32118c',
    'USDT': '0x48065fbbe25f71c9282ddf5e1cd6d6a887483d5e',
    'USAT': '0xd2ab3c9a02dbbab236bfec45d1d755df4267f771',
}


def strict_json(raw):
    def invalid_constant(value):
        raise ValueError('Non-finite JSON value')
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise cencori.CencoriError('Malformed or duplicate-key JSON') from exc


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise cencori.CencoriError('Unsupported saved request structure')


@dataclass(frozen=True)
class SavedRequest:
    request: cencori.PreparedRequest
    sources: frozenset[str]


def load_request(path: Path) -> SavedRequest:
    try:
        with path.open('rb') as handle:
            body = handle.read(cencori.REQUEST_BYTES + 1)
    except OSError as exc:
        raise cencori.CencoriError('Cannot read prepared request') from exc
    if not body or len(body) > cencori.REQUEST_BYTES:
        raise cencori.CencoriError('Prepared request must be at most 32 KiB')
    data = strict_json(body)
    keys(data, ['model', 'max_tokens', 'messages'])
    if (data['model'] != cencori.MODEL or type(data['max_tokens']) is not int
            or data['max_tokens'] not in cencori.SUPPORTED_TOKENS or canonical(data) != body):
        raise cencori.CencoriError('Unsupported or noncanonical prepared request')
    messages = data['messages']
    if not isinstance(messages, list) or len(messages) != 2:
        raise cencori.CencoriError('Expected system and user messages')
    for message, role in zip(messages, ['system', 'user']):
        keys(message, ['role', 'content'])
        if message['role'] != role or not isinstance(message['content'], str):
            raise cencori.CencoriError('Invalid message role/content')
    user = strict_json(messages[1]['content'])
    keys(user, ['goal', 'untrusted_documentation'])
    try:
        _text(user['goal'], 1000, 'goal')
        pages = user['untrusted_documentation']
        if not isinstance(pages, list) or not 1 <= len(pages) <= 3:
            raise cencori.CencoriError('Invalid evidence pages')
        sources = set()
        excerpts = 0
        for page in pages:
            keys(page, ['source_url', 'title', 'sections'])
            url = _text(page['source_url'], 4096, 'source URL')
            safe_url(url)  # Syntax/address literals only; NO DNS or retrieval.
            if url in sources:
                raise cencori.CencoriError('Duplicate evidence source')
            sources.add(url)
            _text(page['title'], 300, 'title')
            if not isinstance(page['sections'], list) or len(page['sections']) > MAX_EXCERPTS:
                raise cencori.CencoriError('Invalid evidence sections')
            for section in page['sections']:
                keys(section, ['heading', 'source_url', 'truncated', 'blocks'])
                if (section['source_url'] != url or not isinstance(section['heading'], str)
                        or len(section['heading']) > 300 or type(section['truncated']) is not bool
                        or not isinstance(section['blocks'], list) or not 1 <= len(section['blocks']) <= MAX_BLOCKS):
                    raise cencori.CencoriError('Invalid evidence section/citation')
                counts = {'text': 0, 'code': 0, 'notice': 0}
                for block in section['blocks']:
                    keys(block, ['kind', 'text', 'truncated'])
                    if (not isinstance(block['kind'], str) or block['kind'] not in counts
                            or not isinstance(block['text'], str) or type(block['truncated']) is not bool):
                        raise cencori.CencoriError('Invalid evidence block')
                    counts[block['kind']] += len(block['text'])
                if counts['text'] > TEXT_CHARS or counts['code'] > CODE_CHARS or counts['notice'] > 600:
                    raise cencori.CencoriError('Evidence exceeds excerpt budgets')
                excerpts += 1
        if not excerpts:
            raise cencori.CencoriError('No evidence excerpts')
    except (PlanError, ValueError, TypeError) as exc:
        raise cencori.CencoriError('Invalid bounded evidence in prepared request') from exc
    # Require the original builder's trusted instructions and citation schema.
    # This compares instruction text, never regenerates the approved HTTP body.
    if messages[0]['content'] != cencori.request_instructions([p['source_url'] for p in pages]):
        raise cencori.CencoriError('Prepared system instructions/schema do not match this release')
    return SavedRequest(cencori.PreparedRequest(body), frozenset(sources))


def wallet_environment():
    # Only OS session context needed for the EXISTING system keychain. No BUY_*
    # overrides, private keys, provider credentials, NODE_OPTIONS or curl config.
    return {key: value for key, value in os.environ.items() if key in {
        'PATH', 'HOME', 'LANG', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR',
    }}


def private_file(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb')


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_file(handle):
    handle.flush()
    os.fsync(handle.fileno())


def record(path, data):
    with private_file(path) as handle:
        handle.write(canonical(data))
        sync_file(handle)
    # File content/inode and its directory entry require separate barriers.
    sync_directory(path.parent)


def amount(value):
    # No exponent, sign, NaN, atomic-unit ambiguity, or --force-sized amounts.
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,6})?', value) or not Decimal('0') < Decimal(value) <= PILOT_CEILING:
        raise cencori.CencoriError('Cap must be positive decimal token units, at most the 0.05 pilot ceiling, with at most six decimal places')
    return value


def offers(raw, token):
    quote = strict_json(raw)
    if not isinstance(quote, dict) or type(quote.get('x402Version')) is not int or quote['x402Version'] != 1:
        raise cencori.CencoriError('Unsupported buy JSON quote envelope: only verified x402 v1 is supported; v2 is rejected')
    accepted = quote.get('accepts')
    if not isinstance(accepted, list) or not 1 <= len(accepted) <= 20:
        raise cencori.CencoriError('Quote has no bounded offers')
    matched = []
    for offer in accepted:
        if (not isinstance(offer, dict) or offer.get('network') != 'celo'
                or offer.get('scheme') != 'exact' or not isinstance(offer.get('asset'), str)
                or offer['asset'].lower() != TOKENS[token]):
            continue
        price = offer.get('maxAmountRequired')
        recipient = offer.get('payTo')
        if (not isinstance(price, str) or not re.fullmatch(r'[0-9]{1,24}', price) or int(price) <= 0
                or not isinstance(recipient, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', recipient)
                or offer.get('resource', cencori.ENDPOINT) != cencori.ENDPOINT):
            raise cencori.CencoriError('Malformed matching quote offer')
        human_price = Decimal(price) / Decimal(1000000)
        if human_price > PILOT_CEILING:
            raise cencori.CencoriError('Fresh selected-token quote exceeds the 0.05 pilot ceiling; no payment allowed')
        matched.append({'price': format(human_price, 'f'), 'pay_to': recipient})
    if not matched:
        raise cencori.CencoriError('Selected token has no supported Celo exact offer')
    return matched


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def parse_completion(raw, sources):
    if not raw or len(raw) > RESPONSE_BYTES:
        raise cencori.CencoriError('Completion envelope exceeds response limit or is empty')
    response = strict_json(raw)
    allowed = {'id', 'object', 'created', 'model', 'choices', 'usage', 'system_fingerprint', 'service_tier', 'safety'}
    if not isinstance(response, dict) or set(response) - allowed:
        raise cencori.CencoriError('Unsupported completion envelope')
    if 'safety' in response:
        safety = response['safety']
        if (not isinstance(safety, dict) or set(safety) != {'scanned'}
                or type(safety['scanned']) is not bool):
            raise cencori.CencoriError('Invalid or unsupported completion safety metadata')
        # Cencori's scan status is metadata, never proof of safety or validity.
    for field in ('id', 'system_fingerprint', 'service_tier'):
        if field in response and response[field] is not None and (not isinstance(response[field], str) or len(response[field]) > 200):
            raise cencori.CencoriError('Invalid completion metadata')
    if 'created' in response and (type(response['created']) is not int or response['created'] < 0):
        raise cencori.CencoriError('Invalid completion creation time')
    if 'usage' in response and not isinstance(response['usage'], dict):
        raise cencori.CencoriError('Invalid completion usage metadata')
    if 'object' in response and response['object'] != 'chat.completion':
        raise cencori.CencoriError('Unsupported completion object')
    if 'model' in response and response['model'] != cencori.MODEL:
        raise cencori.CencoriError('Unexpected completion model')
    choices = response.get('choices')
    if not isinstance(choices, list) or len(choices) != 1:
        raise cencori.CencoriError('Expected one completion choice')
    choice = choices[0]
    if (not isinstance(choice, dict) or set(choice) - {'index', 'message', 'finish_reason', 'logprobs'}
            or type(choice.get('index')) is not int or choice['index'] != 0 or choice.get('finish_reason') != 'stop'):
        raise cencori.CencoriError('Incomplete or unsupported completion choice')
    message = choice.get('message')
    if (not isinstance(message, dict) or set(message) - {'role', 'content', 'refusal'}
            or message.get('role') != 'assistant' or message.get('refusal') is not None
            or not isinstance(message.get('content'), str)):
        raise cencori.CencoriError('Expected assistant JSON text without tool calls/refusal')
    # First pass rejects non-finite values and duplicate keys at every depth.
    strict_json(message['content'])
    return validate_plan(message['content'], set(sources))


def receipt_claims(path):
    """Only bounded response-header identifiers, never authorization material."""
    try:
        with path.open('rb') as handle:
            raw = handle.read(RESPONSE_BYTES + 1)
    except OSError:
        return {}
    if len(raw) > RESPONSE_BYTES:
        return {}
    claims = {}
    for line in raw.decode('iso-8859-1').splitlines():
        key, _, value = line.partition(':')
        if key.lower() == 'x-payment-response' and len(value.strip()) <= 8192:
            try:
                proof = strict_json(base64.b64decode(value.strip(), validate=True))
                tx = proof.get('transaction') if isinstance(proof, dict) else None
                if isinstance(tx, str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', tx):
                    claims['claimed_transaction_hash'] = tx
            except (ValueError, cencori.CencoriError):
                pass
        if key.lower() == 'x-correlation-id' and re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', value.strip()):
            claims['claimed_correlation_id'] = value.strip()
        if key.lower() == 'x-request-id' and re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', value.strip()):
            claims['claimed_request_id'] = value.strip()
    return claims


def supervise(arguments, stdout, stderr, timeout, *, output_limit=None):
    """POSIX main-thread supervision; signal handlers NEVER unwind Popen.

    A signal during constructor/handle assignment is remembered until Popen
    returns. Keep these handlers installed through process-group termination and
    reaping. Do not block signals: the exec'd child must not inherit a mask.
    """
    process = None
    cancelled = False
    outcome, returncode = 'interrupted', None
    previous = {}
    pipes = selectors.DefaultSelector()

    def cancel(signum, frame):
        nonlocal cancelled
        cancelled = True

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, cancel)
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE if output_limit is not None else stdout,
                                   stderr=subprocess.PIPE if output_limit is not None else stderr,
                                   stdin=subprocess.DEVNULL, shell=False,
                                   env=wallet_environment(), start_new_session=True)
        deadline = time.monotonic() + timeout
        if output_limit is not None:
            pipes.register(process.stdout, selectors.EVENT_READ, [stdout, 0])
            pipes.register(process.stderr, selectors.EVENT_READ, [stderr, 0])
        while True:
            if cancelled:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome = 'timeout'
                break
            if output_limit is None:
                try:
                    returncode = process.wait(timeout=min(0.05, remaining))
                    outcome = 'exited' if returncode == 0 else 'nonzero'
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                # One fixed-size read per ready stream; bounded RAM and disk
                # diagnostics even if the child floods either stream forever.
                for key, _ in pipes.select(min(0.05, remaining)):
                    chunk = os.read(key.fileobj.fileno(), 16384)
                    if not chunk:
                        pipes.unregister(key.fileobj)
                        continue
                    target, captured = key.data
                    keep = chunk[:max(0, output_limit - captured)]
                    target.write(keep)
                    key.data[1] += len(keep)
                    if len(keep) != len(chunk):
                        outcome = 'output-limit'
                        break
                if outcome == 'output-limit':
                    break
                if not pipes.get_map() and process.poll() is not None:
                    returncode = process.wait()
                    outcome = 'exited' if returncode == 0 else 'nonzero'
                    break
    except KeyboardInterrupt:
        outcome = 'interrupted'  # Also handle synchronous interruptions in wait.
    except OSError:
        outcome = 'launch-error' if process is None else 'io-error'
    finally:
        try:
            if process is not None:
                if outcome != 'exited' or cancelled:
                    # Kill the group even if its leader exited: curl may remain.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
        finally:
            pipes.close()
            if process is not None and output_limit is not None:
                process.stdout.close()
                process.stderr.close()
            # A final cancellation during cleanup must not become success.
            if cancelled:
                outcome = 'interrupted'
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    return outcome, returncode


def capture_quote(arguments, directory):
    """Retain bounded private prefixes; never authorize from truncated output."""
    with private_file(directory / 'quote.stdout') as stdout, private_file(directory / 'quote.stderr') as stderr:
        try:
            outcome, returncode = supervise(arguments, stdout, stderr, 30, output_limit=QUOTE_BYTES)
        finally:
            sync_file(stdout)
            sync_file(stderr)
    sync_directory(directory)
    record(directory / 'quote-outcome.json', {'outcome': outcome, 'returncode': returncode,
                                             'prefix_limit_per_stream': QUOTE_BYTES,
                                             'truncated': outcome == 'output-limit'})
    if outcome != 'exited':
        raise cencori.CencoriError('Fresh quote failed, interrupted, or exceeded output limits; no payment authorized')
    # At most QUOTE_BYTES, already enforced while streaming, not after capture.
    return (directory / 'quote.stdout').read_bytes()


def run_attempt(arguments, directory, approval):
    """Durable intent precedes the only launch; all outcomes remain UNKNOWN."""
    with private_file(directory / 'stdout.bin') as stdout, private_file(directory / 'stderr.bin') as stderr:
        # Persist output names and intent before any external payment process.
        sync_file(stdout)
        sync_file(stderr)
        record(directory / 'attempt.json', {**approval, 'outcome': 'starting', 'settlement': 'unknown', 'automatic_retry': False})
        try:
            outcome, returncode = supervise(arguments, stdout, stderr, 120)
        finally:
            sync_file(stdout)
            sync_file(stderr)
    with (directory / 'headers.bin').open('rb') as headers:
        os.fsync(headers.fileno())
    record(directory / 'outcome.json', {**approval, 'outcome': outcome, 'returncode': returncode,
                                      'settlement': 'unknown', 'automatic_retry': False,
                                      **receipt_claims(directory / 'headers.bin')})
    if outcome != 'exited':
        raise cencori.CencoriError('Paid attempt failed or was interrupted; settlement is UNKNOWN. Raw evidence preserved. Never retry automatically.')


def infer(request_file, executable, receipt_dir, token, prompt, display):
    """Interactive boundary; prompts occur only after an exact-body fresh quote."""
    if not interactive():
        raise cencori.CencoriError('Paid inference requires active interactive stdin and stdout; no unattended approval is supported')
    if token not in TOKENS:
        raise cencori.CencoriError('Unsupported payment token')
    saved = load_request(request_file)
    request_hash = saved.request.sha256
    buy = str(cencori.trusted_buy(executable))
    version = cencori._run([buy, '--version'], 5)
    if version.returncode or version.stdout.strip() != b'0.8.4':
        raise cencori.CencoriError('Paid workflow requires buy 0.8.4')
    # A new private directory also prevents overwriting or resuming an attempt.
    receipt_dir.mkdir(mode=0o700)
    sync_directory(receipt_dir.parent)
    with private_file(receipt_dir / 'request.json') as handle:
        handle.write(saved.request.body)
        sync_file(handle)
    with private_file(receipt_dir / 'headers.bin') as headers:
        sync_file(headers)
    sync_directory(receipt_dir)
    quote_args = [buy, '--json', 'quote', '--token', token, '-X', 'POST', '-H', 'content-type: application/json',
                  '--data', saved.request.body.decode('utf-8'), cencori.ENDPOINT]
    quote_raw = capture_quote(quote_args, receipt_dir)
    selected = offers(quote_raw, token)
    quoted_at = time.monotonic()
    display(f'Fresh unpaid quote for SHA-256 {request_hash}; POST {cencori.ENDPOINT}')
    for offer in selected:
        display(f"Untrusted offer: {offer['price']} {token} on Celo; recipient {offer['pay_to']}")
    cap = amount(prompt(f'Maximum spend in human-readable {token} units (from the quote)'))
    if not any(Decimal(offer['price']) == Decimal(cap) for offer in selected):
        raise cencori.CencoriError('Approved cap must match a freshly quoted selected-token offer exactly; no payment attempted')
    phrase = f'APPROVE {request_hash} {token} {cap}'
    display('One paid request may settle even if the response fails. No automatic retries. Type exactly: ' + phrase)
    if prompt('Approval') != phrase:
        raise cencori.CencoriError('Approval refused or does not match the exact hash, token and cap')
    if time.monotonic() - quoted_at > 300:
        raise cencori.CencoriError('Quote approval expired; no payment attempted')
    # File tampering cannot change the in-memory bytes, but fail closed anyway.
    if load_request(request_file).request.body != saved.request.body:
        raise cencori.CencoriError('Request file changed after quotation; no payment attempted')
    approval = {'request_sha256': request_hash, 'token': token, 'max_amount': cap,
                'endpoint': cencori.ENDPOINT, 'method': 'POST',
                'buy_executable': buy, 'buy_version': '0.8.4',
                'approved_at': datetime.now(timezone.utc).isoformat()}
    record(receipt_dir / 'approval.json', approval)
    arguments = [buy, '--json', 'curl', '--max-amount', cap, '--token', token,
                 '-X', 'POST', '-H', 'content-type: application/json', '--data', saved.request.body.decode('utf-8'),
                 '--dump-header', str((receipt_dir / 'headers.bin').resolve()), cencori.ENDPOINT]
    run_attempt(arguments, receipt_dir, approval)
    with (receipt_dir / 'stdout.bin').open('rb') as handle:
        raw = handle.read(RESPONSE_BYTES + 1)
    try:
        plan = parse_completion(raw, saved.sources)
    except (cencori.CencoriError, PlanError):
        record(receipt_dir / 'validation.json', {'valid': False, 'automatic_retry': False})
        raise cencori.CencoriError('AI response/plan validation failed; raw evidence preserved. Payment may have settled. Do not retry automatically.')
    record(receipt_dir / 'validation.json', {'valid': True, 'automatic_retry': False})
    return plan
