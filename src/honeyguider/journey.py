"""Thin, artifact-driven orchestration for the objective-to-plan journey.

Composes existing research, request-building, request-preservation and
paid-inference boundaries. No CLI imports, no console output, no new state.
"""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Awaitable, Callable, Sequence

from . import cencori
from . import paid
from . import research
from . import tracking
from .planning import Plan
from .research import Report

DEFAULT_LOCKS_ROOT = Path('.honeyguider/locks')
DEFAULT_REQUESTS_ROOT = Path('.honeyguider/requests')
DEFAULT_RECEIPTS_ROOT = Path('.honeyguider/receipts')
DEFAULT_TRACK_ROOT = Path('.honeyguider/track')
FINGERPRINT_VERSION = 1
_EXCERPT = 120
_ARTIFACT_LIMITS = {
    'request.json': 32768,
    'stdout.bin': 131072,   # paid.RESPONSE_BYTES
    'stderr.bin': 524288,   # explicit 512 KiB owner-accepted ceiling
    'approval.json': 16384,
    'attempt.json': 16384,
    'outcome.json': 16384,
    'validation.json': 16384,
    'headers.bin': 131073,  # paid.receipt_claims reads RESPONSE_BYTES + 1
}
_ARTIFACT_NAMES = ('request.json', 'stdout.bin', 'stderr.bin', 'approval.json',
                   'attempt.json', 'outcome.json', 'validation.json', 'headers.bin')
_APPROVAL_FIELDS = {'request_sha256', 'token', 'max_amount', 'endpoint', 'method',
                    'buy_executable', 'buy_version', 'approved_at'}

Settlement = Enum('Settlement', ['blocked', 'pre_approval', 'approval_not_launched',
                                 'launched_outcome_unavailable', 'outcome_recorded_unconfirmed',
                                 'provider_confirmed'])


class JourneyError(ValueError):
    """Invalid journey inputs; never a wrapper around underlying failures."""


@dataclass(frozen=True)
class AttemptInProgress(Exception):
    """The content-keyed attempt lock is already held by another holder."""

    lock_path: Path

    def __str__(self):
        return f'Attempt already in progress for lock {self.lock_path}'


@dataclass(frozen=True)
class AttemptRecord:
    directory: Path
    settlement: Settlement
    validation: str
    problems: tuple[str, ...]


def _bounded(text) -> str:
    value = str(text)
    return value if len(value) <= _EXCERPT else value[:_EXCERPT]


def _record(directory, settlement, validation, problems):
    return AttemptRecord(directory, settlement, validation,
                         tuple(_bounded(problem) for problem in problems))


def _valid_digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


@contextmanager
def acquire_attempt_lock(request_sha256: str, locks_root: Path = DEFAULT_LOCKS_ROOT):
    """Hold a content-keyed advisory lock for one attempt; never unlinks.

    The digest is validated before any path is built, so traversal strings
    cannot become lock paths. Contention fails fast and never pays. Re-entrancy
    from the same process is intentionally refused: a second open() gets a
    distinct file description and flock reports contention on it.
    """
    if not _valid_digest(request_sha256):
        raise JourneyError('Request digest must be 64 lowercase hex characters')
    try:
        # Platform-local import: the module must stay importable on non-POSIX
        # platforms; only the paid attempt path requires advisory locking.
        import fcntl
    except ImportError as exc:
        raise JourneyError(
            'POSIX advisory locking is unavailable; the paid journey requires a '
            'POSIX platform (Linux verified; macOS unverified; native Windows '
            'locking is not implemented)') from exc
    root = Path(locks_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / f'{request_sha256}.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise AttemptInProgress(path) from exc
        # Diagnostics only: truncate stale bytes, then write one canonical line.
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        line = paid.canonical({'request_sha256': request_sha256, 'pid': os.getpid(),
                               'started_at': datetime.now(timezone.utc).isoformat()}) + b'\n'
        offset = 0
        while offset < len(line):
            offset += os.write(descriptor, line[offset:])
        yield path
    finally:
        # Closing the descriptor releases the kernel lock; the file remains.
        os.close(descriptor)


def _load_identity(directory: Path):
    """Bounded private read + Phase 2 canonical request parser (single source)."""
    tracking.read_bytes(directory / 'request.json', 32768)
    return paid.load_request(directory / 'request.json')


def _output_state(path: Path) -> str:
    """Presence/emptiness without treating output as settlement evidence."""
    if not path.exists():
        return 'invalid' if path.is_symlink() else 'absent'
    try:
        info = path.lstat()
    except OSError:
        return 'invalid'
    if path.is_symlink() or not os.path.isfile(path) or info.st_mode & 0o077:
        return 'invalid'
    return 'empty' if info.st_size == 0 else 'nonempty'


def _validate_approval(raw: bytes, identity: str):
    approval = paid.strict_json(raw)
    if not isinstance(approval, dict) or set(approval) != _APPROVAL_FIELDS:
        raise ValueError('approval field set mismatch')
    if any(not isinstance(value, str) or not value for value in approval.values()):
        raise ValueError('approval values must be nonempty strings')
    if approval['request_sha256'] != identity:
        raise ValueError('approval request hash mismatch')
    if approval['token'] not in paid.TOKENS:
        raise ValueError('approval token unsupported')
    if approval['endpoint'] != cencori.ENDPOINT:
        raise ValueError('approval endpoint mismatch')
    if approval['method'] != 'POST':
        raise ValueError('approval method mismatch')
    if approval['buy_version'] != '0.8.4':
        raise ValueError('approval buy version mismatch')
    paid.amount(approval['max_amount'])
    if datetime.fromisoformat(approval['approved_at']).utcoffset() is None:
        raise ValueError('approval timestamp lacks a timezone')
    return approval


def _validation_axis(directory: Path):
    path = directory / 'validation.json'
    if not path.exists():
        return 'absent', None
    try:
        value = paid.strict_json(tracking.read_bytes(path, 16384))
    except (OSError, tracking.TrackingError, ValueError, RecursionError) as exc:
        return 'absent', f'validation unreadable: {exc}'
    if (not isinstance(value, dict) or set(value) != {'valid', 'automatic_retry'}
            or type(value['valid']) is not bool or value['automatic_retry'] is not False):
        return 'absent', 'ambiguous validation content'
    return ('valid' if value['valid'] else 'rejected'), None


def attempt_state(receipt_dir: Path, *, claim_confirmed_by_provider: bool = False) -> AttemptRecord:
    """Classify one receipt directory from bounded, private local artifacts."""
    directory = Path(receipt_dir)
    try:
        saved = _load_identity(directory)
    except (OSError, tracking.TrackingError, ValueError, RecursionError) as exc:
        return _record(directory, Settlement.blocked, 'absent', [f'request unavailable: {exc}'])
    identity = saved.request.sha256
    names = ('approval.json', 'attempt.json', 'outcome.json', 'validation.json',
             'stdout.bin', 'stderr.bin', 'headers.bin')
    present = {name: (directory / name).exists() for name in names}
    validation, validation_problem = _validation_axis(directory)
    problems = [] if validation_problem is None else [validation_problem]

    # S0: no execution intent at all; quote artifacts are irrelevant here.
    if not (present['approval.json'] or present['attempt.json'] or present['outcome.json']):
        settlement = Settlement.blocked if validation_problem else Settlement.pre_approval
        return _record(directory, settlement, validation, problems)

    # A provider confirmation with no local outcome is contradictory evidence.
    if claim_confirmed_by_provider and not present['outcome.json']:
        return _record(directory, Settlement.blocked, validation,
                       problems + ['provider confirmation without local outcome'])

    if present['outcome.json']:
        if not (present['approval.json'] and present['attempt.json']):
            return _record(directory, Settlement.blocked, validation,
                           problems + ['outcome present without approval/attempt'])
        settlement = (Settlement.provider_confirmed if claim_confirmed_by_provider
                      else Settlement.outcome_recorded_unconfirmed)
        return _record(directory, settlement, validation, problems)

    if present['attempt.json']:
        if not present['approval.json']:
            return _record(directory, Settlement.blocked, validation,
                           problems + ['attempt present without approval'])
        return _record(directory, Settlement.launched_outcome_unavailable, validation, problems)

    # S1 candidate: approval exists, no attempt/outcome yet.
    try:
        raw = tracking.read_bytes(directory / 'approval.json', 16384)
        _validate_approval(raw, identity)
        output_states = (_output_state(directory / 'stdout.bin'),
                         _output_state(directory / 'stderr.bin'))
        if 'invalid' in output_states:
            raise ValueError('invalid attempt output file')
        if output_states != ('absent', 'absent'):
            if 'nonempty' in output_states:
                raise ValueError('attempt output present')
            if 'absent' in output_states:
                raise ValueError('exactly one attempt output stream present')
        if paid.receipt_claims(directory / 'headers.bin'):
            raise ValueError('settlement claim present in headers')
    except (OSError, tracking.TrackingError, ValueError, RecursionError) as exc:
        return _record(directory, Settlement.blocked, validation,
                       problems + [f'approval not launchable: {exc}'])
    return _record(directory, Settlement.approval_not_launched, validation, problems)


def scan_attempts(receipts_root: Path, request_sha256: str,
                 *, claim_confirmed_by_provider: bool = False) -> list[tuple[Path, AttemptRecord]]:
    """Return only matching attempts; unreadable/unstructurable dirs abort."""
    if not _valid_digest(request_sha256):
        raise JourneyError('Request digest must be 64 lowercase hex characters')
    root = Path(receipts_root)
    matches = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        # Unreadable/unstructurable directories propagate; never skipped silently.
        saved = _load_identity(entry)
        if saved.request.sha256 != request_sha256:
            continue
        matches.append((entry, attempt_state(
            entry, claim_confirmed_by_provider=claim_confirmed_by_provider)))
    return matches


def suggest_path(parent: Path, label: str, now: datetime, suffix: str = '') -> Path:
    """Return a timestamped artifact path; never creates anything."""
    if (not isinstance(label, str) or not label or label.startswith('--')
            or '/' in label or '\\' in label
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in label)):
        raise JourneyError(
            'Journey label must be nonempty, without a -- prefix, slash, backslash or control characters')
    return parent / f'{label}-{now:%Y%m%d-%H%M%S}{suffix}'


def _default_retrieve(url: str, goal: str) -> Report:
    """Drive the async research boundary from the sync journey entry point."""
    return asyncio.run(research.research(url, goal))


def prepare(url: str, goal: str, request_path: Path,
            retrieve: Callable[[str, str], Awaitable[Report]] | None = None) -> Path:
    """Research, build and exclusively preserve one prepared request."""
    report = _default_retrieve(url, goal) if retrieve is None else asyncio.run(retrieve(url, goal))
    request = cencori.build_request(goal, report, 1024)
    cencori.preserve_request(request, request_path)
    return request_path


def infer_with_receipt(request_path: Path, buy_executable: Path, receipt_dir: Path,
                       token: str, prompt, display, *, account=None,
                       expected_payer=None) -> Plan:
    """Acquire the content-keyed lock, then forward one paid-inference call.

    paid.infer internally re-reads and re-validates the request; journey cannot
    pass the locked bytes through its existing signature, so a local rewrite in
    the journey->paid window is NOT atomically excluded. On the success path the
    request is re-loaded and the identity/lock linkage is re-verified, failing
    closed with a disclosure if the executed body no longer matches the lock.
    """
    identity = paid.load_request(request_path)
    key = identity.request.sha256
    with acquire_attempt_lock(key):
        plan = paid.infer(request_path, buy_executable, receipt_dir, token, prompt,
                          display, account=account, expected_payer=expected_payer)
    final = paid.load_request(request_path)
    if final.request.sha256 != key:
        raise cencori.CencoriError(
            'Request file changed during the paid attempt; the executed body may not match the locked identity')
    return plan


# --- Phase 5: fingerprints, canonical identity and import -------------------


def _artifact_hash(path: Path, limit: int) -> str:
    """Bounded streaming SHA-256 with tracking.read_bytes permission parity.

    The limit is enforced while reading; the complete byte count must equal the
    file's stat size (no prefix hashing). Symlinks, non-regular files and loose
    permissions fail closed, exactly as tracking.read_bytes refuses them.
    """
    try:
        info = path.lstat()
        if path.is_symlink() or not os.path.isfile(path):
            raise JourneyError(f'Expected a private regular file: {path.name}')
        if info.st_mode & 0o077:
            raise JourneyError(f'Expected a private regular file (mode 0600): {path.name}')
        size = os.stat(path).st_size
        if size > limit:
            raise JourneyError(f'Artifact exceeds {limit} bytes: {path.name}')
        digest = hashlib.sha256()
        total = 0
        with path.open('rb') as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise JourneyError(f'Artifact exceeds {limit} bytes while reading: {path.name}')
                digest.update(chunk)
        if total != size:
            raise JourneyError(f'Artifact changed while hashing: {path.name}')
        return digest.hexdigest()
    except JourneyError:
        raise
    except OSError as exc:
        raise JourneyError(_bounded(f'Artifact unreadable: {exc}')) from exc


_PRESENCE_RULES = {
    Settlement.pre_approval: (
        {'request.json', 'headers.bin'},
        {'approval.json', 'attempt.json', 'outcome.json', 'validation.json',
         'stdout.bin', 'stderr.bin'},
        set()),
    Settlement.approval_not_launched: (
        {'request.json', 'approval.json', 'headers.bin'},
        {'attempt.json', 'outcome.json', 'validation.json'},
        {'stdout.bin', 'stderr.bin'}),
    Settlement.launched_outcome_unavailable: (
        {'request.json', 'approval.json', 'attempt.json', 'headers.bin'},
        {'outcome.json', 'validation.json'},
        {'stdout.bin', 'stderr.bin'}),
    Settlement.outcome_recorded_unconfirmed: (set(_ARTIFACT_NAMES), set(), set()),
    Settlement.provider_confirmed: (set(_ARTIFACT_NAMES), set(), set()),
}


def _require_fingerprint_presence(directory: Path, settlement: Settlement):
    required, absent, _optional = _PRESENCE_RULES[settlement]
    present = {name for name in _ARTIFACT_NAMES if (directory / name).exists()}
    missing = required - present
    unexpected = absent & present
    if missing or unexpected:
        details = []
        if missing:
            details.append('missing ' + ', '.join(sorted(missing)))
        if unexpected:
            details.append('unexpected ' + ', '.join(sorted(unexpected)))
        raise JourneyError(_bounded(
            'Receipt presence contradicts its state: ' + '; '.join(details)))


def record_fingerprint(receipt_dir: Path) -> str:
    """Return a deterministic 64-hex fingerprint of one receipt's artifacts.

    Fail closed: the request must parse, the receipt must classify to a
    non-blocked state, and artifact presence must match that state. Absent
    artifacts hash as ``None``; present artifacts stream through the per-file
    ceilings. No paths, filenames, modes or mtimes enter the canonical input.
    """
    directory = Path(receipt_dir)
    paid.load_request(directory / 'request.json')  # CencoriError surfaces unchanged
    record = attempt_state(directory)
    if record.settlement is Settlement.blocked:
        raise JourneyError('Cannot fingerprint a blocked or ambiguous receipt')
    _require_fingerprint_presence(directory, record.settlement)
    artifacts = {}
    for name in _ARTIFACT_NAMES:
        path = directory / name
        artifacts[name] = (_artifact_hash(path, _ARTIFACT_LIMITS[name])
                           if path.exists() else None)
    canonical = paid.canonical({'fingerprint_version': FINGERPRINT_VERSION,
                                'artifacts': artifacts})
    return hashlib.sha256(canonical).hexdigest()


def _canonical_identity(root: Path) -> str:
    """Canonical filesystem identity of a tracking root.

    ``os.path.realpath`` resolves symlinks in every existing path component;
    a final component that does not exist yet is not followed, so a root-level
    alias to a not-yet-created directory is not canonicalised to its target.
    """
    return os.path.realpath(os.path.normpath(os.path.expanduser(str(root))))


def tracking_destination(request_sha256: str, fingerprint: str,
                         tracking_root: Path = DEFAULT_TRACK_ROOT) -> Path:
    """Return ``<root>/<request>-<fingerprint>`` after validating both digests."""
    if not _valid_digest(request_sha256):
        raise JourneyError('Request digest must be 64 lowercase hex characters')
    if not _valid_digest(fingerprint):
        raise JourneyError('Fingerprint digest must be 64 lowercase hex characters')
    return Path(tracking_root) / f'{request_sha256}-{fingerprint}'


@dataclass(frozen=True)
class ImportOutcomeData:
    disposition: str
    destination: Path | None
    record: AttemptRecord | None
    canonical_duplicate: bool | None
    custom_root: bool
    custom_root_consent: bool
    problems: tuple[str, ...]


def _revision_count(directory: Path) -> int:
    try:
        return len(list(directory.iterdir()))
    except OSError:
        return -1


def _canonical_duplicate_check(key: str, fingerprint):
    if fingerprint is None:
        return None, []
    try:
        canonical = tracking_destination(key, fingerprint, DEFAULT_TRACK_ROOT)
    except JourneyError as exc:
        return None, [_bounded(str(exc))]
    try:
        canonical.lstat()
    except FileNotFoundError:
        return False, []
    except OSError as exc:
        return None, [_bounded(f'canonical tracking root unreadable: {exc}')]
    try:
        state = tracking.load(canonical)
    except (tracking.TrackingError, OSError, ValueError, TypeError, RecursionError) as exc:
        return None, [_bounded(f'canonical duplicate unverifiable: {exc}')]
    recorded = state.get('receipt')
    if not isinstance(recorded, str) or not Path(recorded).is_absolute():
        return None, ['canonical duplicate has no absolute recorded receipt']
    try:
        recomputed = record_fingerprint(Path(recorded))
        recorded_key = paid.load_request(Path(recorded) / 'request.json').request.sha256
    except (JourneyError, OSError, ValueError, RecursionError) as exc:
        return None, [_bounded(f'canonical duplicate unverifiable: {exc}')]
    if state.get('request_sha256') == key and recomputed == fingerprint and recorded_key == key:
        return True, []
    return None, ['canonical duplicate does not match this evidence']


def import_outcome(receipt_dir: Path, *, tracking_root: Path | None = None,
                   custom_root_consent: bool = False) -> ImportOutcomeData:
    """Import one validation-valid S3 outcome; offline, idempotent, fail closed.

    Only ``outcome_recorded_unconfirmed`` with validation ``valid`` is eligible;
    ``provider_confirmed`` is not importable in this phase and UNKNOWN settlement
    is never promoted. A custom tracking root requires explicit consent. Track's
    own ``TrackingError`` refusal (returncode, permissions, validation) maps to
    ``unimportable`` because it is the authoritative layer rejecting the receipt;
    structural destination problems map to ``conflict``. Post-import evidence is
    re-verified; on mismatch the imported record is preserved and a conflict is
    disclosed, never deleted or rewritten.
    """
    directory = Path(receipt_dir)
    identity = paid.load_request(directory / 'request.json')
    key = identity.request.sha256
    record = attempt_state(directory)
    root = Path(tracking_root) if tracking_root is not None else DEFAULT_TRACK_ROOT
    custom_root = _canonical_identity(root) != _canonical_identity(DEFAULT_TRACK_ROOT)
    problems = list(record.problems)

    eligible = (record.settlement is Settlement.outcome_recorded_unconfirmed
                and record.validation == 'valid')
    fingerprint = None
    try:
        fingerprint = record_fingerprint(directory)
    except JourneyError as exc:
        problems.append(_bounded(str(exc)))
    destination = (tracking_destination(key, fingerprint, root)
                   if fingerprint is not None else None)
    canonical_duplicate, canonical_problems = _canonical_duplicate_check(key, fingerprint)
    problems.extend(canonical_problems)

    def outcome(disposition, extra=()):
        return ImportOutcomeData(disposition, destination, record, canonical_duplicate,
                                 custom_root, custom_root_consent,
                                 tuple(problems) + tuple(_bounded(p) for p in extra))

    if not eligible:
        return outcome('unimportable',
                       ['Only a validation-valid S3 (outcome recorded, unconfirmed) is importable'])
    if fingerprint is None or destination is None:
        return outcome('unimportable', ['Receipt cannot be fingerprinted'])
    if custom_root and not custom_root_consent:
        return outcome('custom_consent_required',
                       ['Custom tracking root requires explicit consent'])

    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        return outcome('conflict', [f'destination unreadable: {exc}'])
    else:
        try:
            entries = list(destination.iterdir())
        except OSError as exc:
            return outcome('conflict', [f'destination unreadable: {exc}'])
        if not entries:
            return outcome('interrupted_destination',
                           ['Destination exists but is empty; preserved and never reused'])
        try:
            state = tracking.load(destination)
        except (tracking.TrackingError, OSError, ValueError, TypeError, RecursionError) as exc:
            return outcome('conflict', [f'malformed destination: {exc}'])
        recorded = state.get('receipt')
        if not isinstance(recorded, str) or not Path(recorded).is_absolute():
            return outcome('conflict', ['Destination record has no absolute receipt path'])
        recorded_path = Path(recorded)
        try:
            recorded_fingerprint = record_fingerprint(recorded_path)
            recorded_key = paid.load_request(recorded_path / 'request.json').request.sha256
        except (JourneyError, OSError, ValueError, RecursionError) as exc:
            return outcome('conflict',
                           [f'recorded receipt missing or unreadable at {recorded_path}: {exc}'])
        if (state.get('request_sha256') == key and recorded_fingerprint == fingerprint
                and recorded_key == key):
            return outcome('already_imported')
        return outcome('conflict',
                       [f'recorded receipt at {recorded_path} does not match this evidence'])

    # Pre-import consistency: recompute immediately before writing.
    rechecked = attempt_state(directory)
    try:
        rechecked_fingerprint = record_fingerprint(directory)
    except JourneyError as exc:
        return outcome('conflict', [f'receipt changed before import: {exc}'])
    if (rechecked.settlement is not record.settlement
            or rechecked.validation != record.validation
            or rechecked_fingerprint != fingerprint):
        return outcome('conflict', ['Receipt evidence changed before import'])

    try:
        tracking.import_receipt(directory, destination)
    except FileExistsError:
        return outcome('conflict',
                       ['destination appeared concurrently; nothing overwritten'])
    except tracking.TrackingError as exc:
        return outcome('unimportable', [f'tracking refused receipt: {exc}'])

    # Post-import consistency: preserve on mismatch, only disclose.
    try:
        imported_state = tracking.load(destination)
        post_fingerprint = record_fingerprint(directory)
        post_record = attempt_state(directory)
    except (tracking.TrackingError, JourneyError, OSError, ValueError, RecursionError) as exc:
        revisions = _revision_count(destination)
        return outcome('conflict', [
            'Receipt evidence changed during import; destination name may not describe the imported record',
            f'imported destination has {revisions} revision(s) at {destination}: {exc}'])
    revisions = _revision_count(destination)
    if (post_fingerprint != fingerprint
            or imported_state.get('request_sha256') != key
            or post_record.settlement is not Settlement.outcome_recorded_unconfirmed
            or post_record.validation != 'valid'):
        return outcome('conflict', [
            'Receipt evidence changed during import; destination name may not describe the imported record',
            f'imported destination has {revisions} revision(s) at {destination}'])
    return outcome('imported')


def correlate_claim(receipt_dir: Path, rows: Sequence[Any]) -> str:
    """Tx-hash equality is MATCH-EVIDENCE, not provider authentication.

    Correlation never sets ``claim_confirmed_by_provider=True``; ambiguous,
    multiple, missing or unverifiable provenance stays unconfirmed. Rows are
    duck-typed payments exposing ``tx_hash``, ``token`` and ``network``.
    """
    directory = Path(receipt_dir)
    claimed = paid.receipt_claims(directory / 'headers.bin').get('claimed_transaction_hash')
    if not isinstance(claimed, str):
        return 'unavailable'
    token = None
    try:
        approval = paid.strict_json(tracking.read_bytes(directory / 'approval.json', 16384))
        if isinstance(approval, dict) and isinstance(approval.get('token'), str):
            token = approval['token']
    except (OSError, tracking.TrackingError, ValueError, RecursionError):
        token = None
    matching = [row for row in rows
                if isinstance(getattr(row, 'tx_hash', None), str)
                and row.tx_hash.lower() == claimed.lower()]
    if not matching:
        return 'unavailable'
    if len(matching) != 1:
        return 'conflicting'
    row = matching[0]
    if getattr(row, 'network', None) != 'celo':
        return 'conflicting'
    if token is not None and getattr(row, 'token', None) != token:
        return 'conflicting'
    return 'correlated'


# --- Phase 6: bounded tracking summary ---------------------------------------


@dataclass(frozen=True)
class TrackedPlanSummary:
    directory: Path
    request_sha256: str | None
    fingerprint: str | None
    tasks: int
    completed: int
    settlement: str | None
    problems: tuple[str, ...]


def list_tracked_plans(directory: Path = DEFAULT_TRACK_ROOT) -> list[TrackedPlanSummary]:
    """Summarize existing tracking directories; read-only and bounded.

    Only direct children of the requested root are inspected: non-directories
    and symlinks are skipped silently, and nothing is created, written or
    followed. Per-directory containment is deliberate here (unlike
    ``scan_attempts``): one unreadable or malformed directory becomes a summary
    row with bounded problems and never aborts the listing. Settlement is never
    ``'confirmed'`` — local evidence cannot confirm a provider payment — and is
    ``None`` when the recorded receipt is missing or unreadable.
    """
    root = Path(directory)
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    summaries = []
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        try:
            state = tracking.load(entry)
        except tracking.ERRORS as exc:
            summaries.append(TrackedPlanSummary(
                entry, None, None, 0, 0, 'unknown',
                (_bounded(f'unreadable or malformed tracking directory: {exc}'),)))
            continue
        fingerprint = None
        settlement = None
        problems: tuple[str, ...] = ()
        try:
            fingerprint = record_fingerprint(Path(state['receipt']))
            settlement = 'unknown'
        except (JourneyError, cencori.CencoriError, OSError) as exc:
            problems = (_bounded(f'recorded receipt missing or unreadable: {exc}'),)
        summaries.append(TrackedPlanSummary(
            entry, state['request_sha256'], fingerprint,
            len(state['plan']['tasks']), len(state['completed']),
            settlement, problems))
    return summaries
