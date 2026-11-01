"""Offline receipt import and append-only private plan progress."""
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from . import paid
from .cencori import CencoriError, ENDPOINT
from .planning import PlanError, validate_completed, validate_plan
from .research import safe_url

STATE_BYTES = 512 * 1024  # Includes ASCII escaping of bounded Unicode plan text.


class TrackingError(ValueError):
    pass


def read_bytes(path: Path, limit: int) -> bytes:
    # Refuse links, devices, FIFOs and shared private data before opening.
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise TrackingError("Expected a private regular file (mode 0600)")
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    if not raw or len(raw) > limit:
        raise TrackingError("Empty or oversized tracking/receipt file")
    return raw


def private_directory(path: Path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise TrackingError("Expected a private directory (mode 0700)")


def receipt_state(directory: Path) -> dict:
    private_directory(directory)
    # Check private-file properties before reusing the existing request parser.
    read_bytes(directory / 'request.json', 32768)
    saved = paid.load_request(directory / 'request.json')
    raw = read_bytes(directory / 'stdout.bin', paid.RESPONSE_BYTES)
    records = {name: paid.strict_json(read_bytes(directory / f'{name}.json', 16384))
               for name in ('approval', 'attempt', 'outcome', 'validation')}
    approval, attempt, outcome, validation = (records[name] for name in
                                             ('approval', 'attempt', 'outcome', 'validation'))
    fields = {'request_sha256', 'token', 'max_amount', 'endpoint', 'method',
              'buy_executable', 'buy_version', 'approved_at'}
    if (not isinstance(approval, dict) or set(approval) != fields
            or any(not isinstance(value, str) or not value for value in approval.values())
            or approval['request_sha256'] != saved.request.sha256
            or approval['endpoint'] != ENDPOINT or approval['method'] != 'POST'
            or approval['buy_version'] != '0.8.4' or approval['token'] not in paid.TOKENS):
        raise TrackingError("Invalid or mismatched receipt approval")
    paid.amount(approval['max_amount'])  # Pure decimal validation; no execution.
    if (not Path(approval['buy_executable']).is_absolute()
            or datetime.fromisoformat(approval['approved_at']).utcoffset() is None):
        raise TrackingError("Invalid receipt executable/time metadata")
    expected_attempt = {**approval, 'outcome': 'starting', 'settlement': 'unknown', 'automatic_retry': False}
    if (not isinstance(attempt, dict) or attempt != expected_attempt
            or attempt.get('automatic_retry') is not False):
        raise TrackingError("Invalid receipt launch record")
    claims = {'claimed_transaction_hash', 'claimed_correlation_id', 'claimed_request_id'}
    if (not isinstance(outcome, dict)
            or set(outcome) - claims != fields | {'outcome', 'returncode', 'settlement', 'automatic_retry'}
            or any(outcome.get(key) != value for key, value in approval.items())
            or outcome.get('outcome') != 'exited' or type(outcome.get('returncode')) is not int
            or outcome['returncode'] != 0 or outcome.get('settlement') != 'unknown'
            or outcome.get('automatic_retry') is not False):
        raise TrackingError("Receipt does not record a successful inference exit")
    for key in claims & outcome.keys():
        pattern = r'0x[0-9a-fA-F]{64}' if key == 'claimed_transaction_hash' else r'[a-zA-Z0-9_.-]{1,128}'
        if not isinstance(outcome[key], str) or not re.fullmatch(pattern, outcome[key]):
            raise TrackingError("Invalid receipt identifier claim")
    if (not isinstance(validation, dict) or set(validation) != {'valid', 'automatic_retry'}
            or validation['valid'] is not True or validation['automatic_retry'] is not False):
        raise TrackingError("Receipt does not record successful validation")
    # validation.json is only a gate: always revalidate original output/evidence.
    plan = paid.parse_completion(raw, saved.sources)
    return {'schema_version': 1, 'revision': 0, 'receipt': str(directory.resolve()),
            'request_sha256': saved.request.sha256,
            'completion_sha256': hashlib.sha256(raw).hexdigest(),
            'sources': sorted(saved.sources), 'plan': asdict(plan), 'completed': []}


def validate(state: dict):
    fields = {'schema_version', 'revision', 'receipt', 'request_sha256',
              'completion_sha256', 'sources', 'plan', 'completed'}
    if (not isinstance(state, dict) or set(state) != fields
            or type(state['schema_version']) is not int or state['schema_version'] != 1
            or type(state['revision']) is not int or not 0 <= state['revision'] <= 20
            or not isinstance(state['receipt'], str) or not Path(state['receipt']).is_absolute()):
        raise TrackingError("Unsupported tracking state schema")
    for key in ('request_sha256', 'completion_sha256'):
        if not isinstance(state[key], str) or not re.fullmatch('[0-9a-f]{64}', state[key]):
            raise TrackingError("Invalid provenance digest")
    sources = state['sources']
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 3
            or any(not isinstance(url, str) or len(url) > 4096 for url in sources)
            or len(set(sources)) != len(sources)):
        raise TrackingError("Invalid saved citation sources")
    for url in sources:
        safe_url(url)  # Local URL validation, no DNS.
    plan = validate_plan(json.dumps(state['plan'], ensure_ascii=False, separators=(',', ':')), set(sources))
    completed = state['completed']
    if not isinstance(completed, list) or any(not isinstance(item, str) for item in completed):
        raise TrackingError("Invalid completed IDs")
    validate_completed(plan, completed)
    if state['revision'] != len(completed):
        raise TrackingError("Revision does not match progress")
    return plan


def append(directory: Path, state: dict):
    """Publish complete, fsynced bytes atomically without replacing any file."""
    validate(state)
    private_directory(directory)
    raw = paid.canonical(state)
    if len(raw) > STATE_BYTES:
        raise TrackingError("Tracking state exceeds byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.pending-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # link is an atomic exclusive publication; competing writers cannot clobber.
        os.link(temporary, directory / f"{state['revision']:06d}.json")
    finally:
        if temporary is not None:
            temporary.unlink()
    paid.sync_directory(directory)


def import_receipt(receipt: Path, directory: Path):
    state = receipt_state(receipt)
    # Even an empty existing directory is refused. No implicit reset or resume.
    directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, parents=False)
    paid.sync_directory(directory.parent)
    append(directory, state)


def load(directory: Path) -> dict:
    private_directory(directory)
    entries = sorted(directory.iterdir())
    if not entries or len(entries) > 21:
        raise TrackingError("Missing or excessive tracking revisions")
    previous = None
    for revision, path in enumerate(entries):
        if path.name != f'{revision:06d}.json':
            raise TrackingError("Unexpected file or missing tracking revision")
        state = paid.strict_json(read_bytes(path, STATE_BYTES))
        validate(state)
        if state['revision'] != revision:
            raise TrackingError("Mismatched tracking revision")
        if previous is not None:
            fixed = set(state) - {'revision', 'completed'}
            if (any(state[key] != previous[key] for key in fixed)
                    or len(state['completed']) != len(previous['completed']) + 1
                    or state['completed'][:-1] != previous['completed']):
                raise TrackingError("Invalid progress history")
        previous = state
    return previous


# Callers convert these expected boundary failures to a concise CLI error.
ERRORS = (TrackingError, CencoriError, PlanError, OSError, ValueError, TypeError, RecursionError)
