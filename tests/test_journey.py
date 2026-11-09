import ast
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from honeyguider import cencori, journey, paid, tracking
from honeyguider.planning import Plan
from honeyguider.research import Report, ResearchError, extract

URL = 'https://docs.example.com/guide'
NOW = datetime(2026, 11, 8, 15, 30, 0)
PAYER = '0x' + '1' * 40


def artifact_report(errors=None):
    page = extract(b'<h2>Install</h2><p>Install the package.</p>', URL, 'install package')
    return Report(pages=[page], errors=list(errors or []))


def test_suggest_path_exact_format(tmp_path):
    assert journey.suggest_path(tmp_path, 'req', NOW, '.json') == tmp_path / 'req-20261108-153000.json'
    assert journey.suggest_path(tmp_path, 'req', NOW) == tmp_path / 'req-20261108-153000'
    assert journey.suggest_path(tmp_path, 'req', NOW, '') == tmp_path / 'req-20261108-153000'


def test_suggest_path_is_pure_and_creates_nothing(tmp_path):
    parent = tmp_path / 'not-created'
    path = journey.suggest_path(parent, 'plan', NOW, '.json')
    assert path == parent / 'plan-20261108-153000.json'
    assert not parent.exists()


@pytest.mark.parametrize('label', ['', 'a/b', 'a\\b', '--x', 'a\nb', 'a\tb', 'a\x7fb'])
def test_suggest_path_rejects_unsafe_labels(tmp_path, label):
    with pytest.raises(journey.JourneyError):
        journey.suggest_path(tmp_path, label, NOW)


def test_suggest_path_allows_spaces(tmp_path):
    assert journey.suggest_path(tmp_path, 'plan v2', NOW) == tmp_path / 'plan v2-20261108-153000'


def test_prepare_writes_canonical_request_exclusively(tmp_path):
    request_path = tmp_path / 'artifacts' / 'request.json'  # parent created by preserve_request
    retrieve = AsyncMock(return_value=artifact_report())
    result = journey.prepare(URL, 'install package', request_path, retrieve=retrieve)
    assert result == request_path
    retrieve.assert_awaited_once_with(URL, 'install package')
    body = request_path.read_bytes()
    user = json.loads(json.loads(body)['messages'][1]['content'])
    assert user['goal'] == 'install package'
    assert URL.encode() in body
    assert request_path.stat().st_mode & 0o777 == 0o600


def test_prepare_never_overwrites_existing_artifact(tmp_path):
    request_path = tmp_path / 'request.json'
    request_path.write_bytes(b'x')
    with pytest.raises(cencori.CencoriError):
        journey.prepare(URL, 'install package', request_path,
                        retrieve=AsyncMock(return_value=artifact_report()))
    assert request_path.read_bytes() == b'x'


def test_prepare_propagates_retrieval_errors_without_writing(tmp_path):
    request_path = tmp_path / 'request.json'
    with pytest.raises(cencori.CencoriError):
        journey.prepare(URL, 'install package', request_path,
                        retrieve=AsyncMock(return_value=artifact_report(errors=['boom'])))
    assert not request_path.exists()


@pytest.mark.parametrize('goal', ['x' * 1001, 'bad\x00goal'])
def test_prepare_propagates_invalid_goal_without_writing(tmp_path, goal):
    request_path = tmp_path / 'request.json'
    with pytest.raises(cencori.CencoriError):
        journey.prepare(URL, goal, request_path,
                        retrieve=AsyncMock(return_value=artifact_report()))
    assert not request_path.exists()


def test_prepare_injected_retrieve_never_touches_default(tmp_path):
    retrieve = AsyncMock(return_value=artifact_report())
    with patch('honeyguider.journey._default_retrieve',
               side_effect=AssertionError('default retrieve must not run')) as default:
        journey.prepare(URL, 'install package', tmp_path / 'request.json', retrieve=retrieve)
    default.assert_not_called()
    retrieve.assert_awaited_once_with(URL, 'install package')


def test_default_retrieve_drives_research_offline(tmp_path):
    calls = []

    async def fake_research(url, goal):
        calls.append((url, goal))
        return artifact_report()

    with patch.object(journey, 'research', SimpleNamespace(research=fake_research)):
        result = journey.prepare(URL, 'install package', tmp_path / 'request.json')
    assert result == tmp_path / 'request.json'
    assert calls == [(URL, 'install package')]
    assert result.read_bytes()


def test_default_retrieve_propagates_research_failure():
    async def forbidden(url, goal):
        raise ResearchError('research must not run')

    with patch.object(journey, 'research', SimpleNamespace(research=forbidden)):
        with pytest.raises(ResearchError, match='must not run'):
            journey._default_retrieve(URL, 'install package')


def test_infer_with_receipt_forwards_exactly_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    buy, receipt = tmp_path / 'buy', tmp_path / 'receipt'
    expected_plan = Plan(1, ())
    recorder = Mock(return_value=expected_plan)
    prompt, display = (lambda question: 'x'), (lambda message: None)
    with patch.object(journey.paid, 'infer', recorder):
        result = journey.infer_with_receipt(
            request_path, buy, receipt, 'USDC', prompt, display,
            account='honeyguider', expected_payer=PAYER)
    assert result is expected_plan
    recorder.assert_called_once_with(
        request_path, buy, receipt, 'USDC', prompt, display,
        account='honeyguider', expected_payer=PAYER)
    # Lock released and its diagnostics file retained under the default root.
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'
    assert lock.exists()
    with journey.acquire_attempt_lock(key):
        pass


def test_infer_with_receipt_propagates_exceptions_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, _ = _adapter_request(tmp_path)
    error = cencori.CencoriError('payment refused; no retry')
    with patch.object(journey.paid, 'infer', side_effect=error):
        with pytest.raises(cencori.CencoriError) as caught:
            journey.infer_with_receipt(request_path, tmp_path / 'buy', tmp_path / 'receipt',
                                       'USDC', lambda q: 'x', lambda m: None)
    assert caught.value is error


def test_infer_with_receipt_propagates_keyboard_interrupt_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    with patch.object(journey.paid, 'infer', side_effect=KeyboardInterrupt()):
        with pytest.raises(KeyboardInterrupt):
            journey.infer_with_receipt(request_path, tmp_path / 'buy', tmp_path / 'receipt',
                                       'USDC', lambda q: 'x', lambda m: None)
    # BaseException still unwinds the context manager and releases the lock.
    with journey.acquire_attempt_lock(key):
        pass


def test_infer_with_receipt_passes_artifacts_unmutated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, _ = _adapter_request(tmp_path)
    receipt = tmp_path / 'receipt'
    recorder = Mock(return_value=Plan(1, ()))
    with patch.object(journey.paid, 'infer', recorder):
        journey.infer_with_receipt(request_path, tmp_path / 'buy', receipt,
                                   'USDC', lambda q: 'x', lambda m: None)
    args, kwargs = recorder.call_args.args, recorder.call_args.kwargs
    assert args[0] == request_path
    assert args[2] is receipt
    assert kwargs == {'account': None, 'expected_payer': None}


def test_infer_with_receipt_locks_before_payment_and_remains_held_inside(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    expected_plan = Plan(1, ())
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'
    observations = []

    def fake_infer(*args, **kwargs):
        observations.append('paid_infer')
        # Diagnostics exist inside paid.infer: the outer holder already locked.
        assert lock.exists()
        assert json.loads(lock.read_bytes())['request_sha256'] == key
        with pytest.raises(journey.AttemptInProgress) as caught:
            with journey.acquire_attempt_lock(key):
                pass
        assert caught.value.lock_path.resolve() == lock
        return expected_plan

    with patch.object(journey.paid, 'infer', fake_infer):
        result = journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                            tmp_path / 'receipt', 'USDC',
                                            lambda q: 'x', lambda m: None)
    assert result is expected_plan
    assert observations == ['paid_infer']


def test_infer_with_receipt_releases_lock_after_success_and_after_exception(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'
    with patch.object(journey.paid, 'infer', Mock(return_value=Plan(1, ()))):
        journey.infer_with_receipt(request_path, tmp_path / 'buy', tmp_path / 'receipt',
                                   'USDC', lambda q: 'x', lambda m: None)
    with journey.acquire_attempt_lock(key):
        pass
    error = cencori.CencoriError('payment refused')
    with patch.object(journey.paid, 'infer', side_effect=error):
        with pytest.raises(cencori.CencoriError) as caught:
            journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                       tmp_path / 'receipt2', 'USDC',
                                       lambda q: 'x', lambda m: None)
    assert caught.value is error
    with journey.acquire_attempt_lock(key):
        pass
    assert lock.exists()


def test_infer_with_receipt_competing_holder_cannot_enter_second_payment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'
    sentinel = Mock(side_effect=AssertionError('a second payment entered'))
    with journey.acquire_attempt_lock(key):
        with patch.object(journey.paid, 'infer', sentinel):
            with pytest.raises(journey.AttemptInProgress) as caught:
                journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                           tmp_path / 'receipt', 'USDC',
                                           lambda q: 'x', lambda m: None)
    sentinel.assert_not_called()
    assert caught.value.lock_path.resolve() == lock


def test_infer_with_receipt_distinct_requests_do_not_contend(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_a, key_a = _adapter_request(tmp_path / 'a')
    request_b, key_b = _adapter_request(tmp_path / 'b', goal='other goal')
    assert key_a != key_b
    with journey.acquire_attempt_lock(key_a):
        with patch.object(journey.paid, 'infer', Mock(return_value=Plan(1, ()))):
            result = journey.infer_with_receipt(request_b, tmp_path / 'buy',
                                                tmp_path / 'receipt-b', 'USDC',
                                                lambda q: 'x', lambda m: None)
    assert result.tasks == ()
    assert request_a.exists() and request_b.exists()


def test_infer_with_receipt_post_attempt_identity_recheck_detects_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    changed = cencori.build_request('different goal', artifact_report(), 1024)
    calls = []

    def fake_infer(*args, **kwargs):
        calls.append('paid_infer')
        request_path.write_bytes(changed.body)  # rewrite in the journey->paid window
        return Plan(1, ())

    with patch.object(journey.paid, 'infer', fake_infer):
        with pytest.raises(cencori.CencoriError,
                           match='Request file changed during the paid attempt'):
            journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                       tmp_path / 'receipt', 'USDC',
                                       lambda q: 'x', lambda m: None)
    assert calls == ['paid_infer']  # no second payment
    with journey.acquire_attempt_lock(key):
        pass


def test_infer_with_receipt_attempt_in_progress_propagates_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'
    with journey.acquire_attempt_lock(key):
        with patch.object(journey.paid, 'infer',
                          Mock(side_effect=AssertionError('must not run'))):
            with pytest.raises(journey.AttemptInProgress) as caught:
                journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                           tmp_path / 'receipt', 'USDC',
                                           lambda q: 'x', lambda m: None)
    error = caught.value
    assert type(error) is journey.AttemptInProgress
    assert error.lock_path.resolve() == lock


@pytest.mark.parametrize('kind', ['missing', 'malformed'])
def test_infer_with_receipt_identity_failure_surfaces_before_lock(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(tmp_path)
    request_path = tmp_path / 'request.json'
    if kind == 'malformed':
        _private_write(request_path, b'{not json')
    sentinel = Mock(side_effect=AssertionError('must not run'))
    with patch.object(journey.paid, 'infer', sentinel):
        with pytest.raises(cencori.CencoriError):
            journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                       tmp_path / 'receipt', 'USDC',
                                       lambda q: 'x', lambda m: None)
    sentinel.assert_not_called()
    assert not (tmp_path / '.honeyguider').exists()


def test_infer_with_receipt_unbound_legacy_path_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    recorder = Mock(return_value=Plan(1, ()))
    with patch.object(journey.paid, 'infer', recorder):
        journey.infer_with_receipt(request_path, tmp_path / 'buy',
                                   tmp_path / 'receipt', 'USDC',
                                   lambda q: 'x', lambda m: None)
    assert recorder.call_args.kwargs == {'account': None, 'expected_payer': None}
    assert recorder.call_args.args[0] == request_path
    with journey.acquire_attempt_lock(key):
        pass


PROCESS_BOUNDARY_CHILD = textwrap.dedent('''
    import os
    import sys

    root, src, request_path, buy, receipt_dir, marker = sys.argv[1:7]
    sys.path.insert(0, src)
    os.chdir(root)
    from pathlib import Path
    from honeyguider import journey, paid
    from honeyguider.planning import Plan

    request_path, buy, receipt_dir = Path(request_path), Path(buy), Path(receipt_dir)


    def fake_infer(*args, **kwargs):
        with open(marker, 'a') as handle:
            handle.write(f'ENTERED:{os.getpid()}\\n')
        print(f'ENTERED:{os.getpid()}', flush=True)
        sys.stdin.buffer.read(1)
        return Plan(1, ())


    paid.infer = fake_infer
    print('READY', flush=True)
    sys.stdin.buffer.read(1)
    messages = []
    try:
        journey.infer_with_receipt(request_path, buy, receipt_dir, 'USDC',
                                   lambda question: '', messages.append)
    except journey.AttemptInProgress:
        with open(marker, 'a') as handle:
            handle.write(f'ATTEMPT_IN_PROGRESS:{os.getpid()}\\n')
    except BaseException as exc:
        with open(marker, 'a') as handle:
            handle.write(f'ERROR:{type(exc).__name__}\\n')
    else:
        with open(marker, 'a') as handle:
            handle.write('DONE\\n')
''')


def test_infer_with_receipt_process_boundary_one_attempt_only(tmp_path, monkeypatch):
    # Process-level kernel-lock boundary; POSIX/Linux. paid.infer is fully
    # replaced by a double; no real inference, quote, provider or payment.
    monkeypatch.chdir(tmp_path)
    request_path, key = _adapter_request(tmp_path)
    buy = tmp_path / 'buy'
    marker = tmp_path / 'markers.txt'
    marker.write_text('')
    src_entry = str(Path(journey.__file__).resolve().parents[1])
    repo_root = Path(__file__).resolve().parents[1]
    lock = tmp_path / '.honeyguider' / 'locks' / f'{key}.lock'

    def spawn(receipt_dir):
        return subprocess.Popen(
            [sys.executable, '-c', PROCESS_BOUNDARY_CHILD, str(tmp_path), src_entry,
             str(request_path), str(buy), str(receipt_dir), str(marker)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    child_a = spawn(tmp_path / 'receipt-a')
    child_b = None
    try:
        # Both children handshake READY before any attempt begins.
        assert child_a.stdout.readline() == b'READY\n'
        child_b = spawn(tmp_path / 'receipt-b')
        assert child_b.stdout.readline() == b'READY\n'

        # A proceeds first, acquires the lock and enters the inference double.
        child_a.stdin.write(b'1')
        child_a.stdin.flush()
        assert child_a.stdout.readline() == f'ENTERED:{child_a.pid}\n'.encode()
        assert lock.exists()  # held across the mocked inference body

        # B now attempts the same payment path and must fail fast on contention.
        child_b.stdin.write(b'1')
        child_b.stdin.flush()
        assert child_b.wait(timeout=20) == 0

        # Release A only after B has been refused.
        child_a.stdin.write(b'2')
        child_a.stdin.flush()
        child_a.stdin.close()
        assert child_a.wait(timeout=20) == 0
    finally:
        for child in (child_a, child_b):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=20)
            if child is not None:
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()

    lines = marker.read_text().splitlines()
    entered = [line for line in lines if line.startswith('ENTERED:')]
    assert entered == [f'ENTERED:{child_a.pid}']  # exactly one inference execution
    assert lines.count('DONE') == 1
    assert f'ATTEMPT_IN_PROGRESS:{child_b.pid}' in lines
    assert f'ENTERED:{child_b.pid}' not in lines
    assert not any(line.startswith('ERROR:') for line in lines)

    # The lock file persists and the kernel released it after both exits.
    assert lock.exists()
    with journey.acquire_attempt_lock(key):
        pass
    # chdir discipline: no lock artifacts leaked into the repository worktree.
    assert not (repo_root / '.honeyguider').exists()


def test_journey_has_no_cli_ui_or_state_imports():
    tree = ast.parse(Path(journey.__file__).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
            else:
                modules.extend(alias.name for alias in node.names)
    roots = {name.split('.')[0] for name in modules}
    assert roots.isdisjoint({'typer', 'rich', 'cli', 'track_cli', 'welcome'})
    assert roots <= {'asyncio', 'contextlib', 'dataclasses', 'datetime', 'enum',
                     'fcntl', 'hashlib', 'os', 'pathlib', 're', 'typing',
                     'cencori', 'paid', 'research', 'tracking', 'planning'}


# --- Phase 4: content-keyed lock -------------------------------------------


def _private_write(path, data: bytes):
    path.write_bytes(data)
    path.chmod(0o600)


def _write_json(path, value):
    _private_write(path, paid.canonical(value))


def _request_tree(directory, goal='install package'):
    directory.mkdir(parents=True, exist_ok=True)
    request = cencori.build_request(goal, artifact_report(), 1024)
    cencori.preserve_request(request, directory / 'request.json')
    return request


def _approval(request, **overrides):
    values = {
        'request_sha256': request.sha256,
        'token': 'USDC',
        'max_amount': '0.01',
        'endpoint': cencori.ENDPOINT,
        'method': 'POST',
        'buy_executable': '/usr/bin/buy',
        'buy_version': '0.8.4',
        'approved_at': '2026-11-08T15:30:00+00:00',
    }
    values.update(overrides)
    return values


def _approved_tree(directory):
    request = _request_tree(directory)
    _write_json(directory / 'approval.json', _approval(request))
    _private_write(directory / 'headers.bin', b'')
    return request


def _launched_tree(directory, *, outcome=True):
    request = _request_tree(directory)
    approval = _approval(request)
    _write_json(directory / 'approval.json', approval)
    _write_json(directory / 'attempt.json',
                {**approval, 'outcome': 'starting', 'settlement': 'unknown',
                 'automatic_retry': False})
    _private_write(directory / 'headers.bin', b'')
    if outcome:
        _write_json(directory / 'outcome.json', {})
    return request


def _adapter_request(directory, goal='install package'):
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / 'request.json'
    request = cencori.build_request(goal, artifact_report(), 1024)
    cencori.preserve_request(request, request_path)
    return request_path, request.sha256


def test_attempt_lock_mode_persistence_and_diagnostics(tmp_path):
    root = tmp_path / 'locks'
    digest = 'a' * 64
    lock = root / f'{digest}.lock'
    with journey.acquire_attempt_lock(digest, root) as path:
        assert path == lock
        assert lock.is_file()
        assert lock.stat().st_mode & 0o777 == 0o600
        text = lock.read_bytes().decode()
        assert text.endswith('\n') and text.count('\n') == 1
        data = json.loads(text)
        assert data['request_sha256'] == digest
        assert data['pid'] == os.getpid()
        assert datetime.fromisoformat(data['started_at']).utcoffset() is not None
    # Never unlinked; kernel release happens on close.
    assert lock.exists()


def test_attempt_lock_contention_same_process(tmp_path):
    root, digest = tmp_path / 'locks', 'b' * 64
    lock = root / f'{digest}.lock'
    with journey.acquire_attempt_lock(digest, root):
        with pytest.raises(journey.AttemptInProgress) as caught:
            with journey.acquire_attempt_lock(digest, root):
                pass
        assert str(lock) in str(caught.value)
        assert caught.value.lock_path == lock
    # Released after the exception-safe exit.
    with journey.acquire_attempt_lock(digest, root):
        pass


CHILD_LOCK_SCRIPT = """
import fcntl, os, sys
path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
os.write(1, b'locked\\n')
os.read(0, 1)
os._exit(0)
"""


def test_attempt_lock_released_when_child_process_exits(tmp_path):
    # The only real subprocess in this file: a harmless Python lock holder.
    root, digest = tmp_path / 'locks', 'c' * 64
    root.mkdir(mode=0o700)
    lock = root / f'{digest}.lock'
    child = subprocess.Popen([sys.executable, '-c', CHILD_LOCK_SCRIPT, str(lock)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        assert child.stdout.readline() == b'locked\n'
        with pytest.raises(journey.AttemptInProgress):
            with journey.acquire_attempt_lock(digest, root):
                pass
        child.stdin.write(b'x')
        child.stdin.flush()
        assert child.wait(timeout=20) == 0
        # Kernel crash/exit release: acquisition now succeeds.
        with journey.acquire_attempt_lock(digest, root) as path:
            assert path == lock
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=20)
        child.stdin.close()
        child.stdout.close()


def test_attempt_lock_content_keys_are_separate(tmp_path):
    root, one, two = tmp_path / 'locks', '1' * 64, '2' * 64
    with journey.acquire_attempt_lock(one, root):
        with journey.acquire_attempt_lock(two, root) as path:
            assert path == root / f'{two}.lock'
    assert (root / f'{one}.lock').exists()
    assert (root / f'{two}.lock').exists()


def test_attempt_lock_released_on_body_exception(tmp_path):
    root, digest = tmp_path / 'locks', 'd' * 64
    lock = root / f'{digest}.lock'
    with pytest.raises(RuntimeError):
        with journey.acquire_attempt_lock(digest, root):
            raise RuntimeError('body failed')
    assert lock.exists()
    with journey.acquire_attempt_lock(digest, root):
        pass


def test_attempt_lock_clears_stale_diagnostics(tmp_path):
    root, digest = tmp_path / 'locks', 'e' * 64
    root.mkdir(mode=0o700)
    lock = root / f'{digest}.lock'
    _private_write(lock, b'garbage-not-json\n')
    with journey.acquire_attempt_lock(digest, root):
        data = json.loads(lock.read_bytes())
        assert data['request_sha256'] == digest


@pytest.mark.parametrize('digest', ['A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, '',
                                    '../' + 'a' * 61, None, 123])
def test_attempt_lock_rejects_invalid_digest_before_building_paths(tmp_path, digest):
    root = tmp_path / 'locks'
    with pytest.raises(journey.JourneyError):
        with journey.acquire_attempt_lock(digest, root):
            pass
    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


def test_attempt_lock_creates_private_root(tmp_path):
    root = tmp_path / 'nested' / 'locks'
    with journey.acquire_attempt_lock('f' * 64, root):
        pass
    assert root.stat().st_mode & 0o777 == 0o700


# --- Phase 4: S0-S4 attempt classification ---------------------------------


def test_attempt_state_pre_approval_ignores_quote_artifacts(tmp_path):
    directory = tmp_path / 'receipt'
    _request_tree(directory)
    _write_json(directory / 'quote-outcome.json', {'outcome': 'exited', 'returncode': 0})
    record = journey.attempt_state(directory)
    assert record.directory == directory
    assert record.settlement is journey.Settlement.pre_approval
    assert record.validation == 'absent'
    assert record.problems == ()


def test_attempt_state_approval_not_launched(tmp_path):
    directory = tmp_path / 'receipt'
    _approved_tree(directory)
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.approval_not_launched
    assert record.validation == 'absent'
    assert record.problems == ()


@pytest.mark.parametrize('stdout,stderr,blocked', [
    (None, None, False),
    ('empty', 'empty', False),
    ('text', 'empty', True),
    ('empty', 'text', True),
    ('empty', None, True),
    (None, 'empty', True),
])
def test_attempt_state_output_presence_matrix(tmp_path, stdout, stderr, blocked):
    directory = tmp_path / 'receipt'
    _approved_tree(directory)
    for name, value in (('stdout.bin', stdout), ('stderr.bin', stderr)):
        if value is not None:
            _private_write(directory / name, b'' if value == 'empty' else b'output\n')
    record = journey.attempt_state(directory)
    if blocked:
        assert record.settlement is journey.Settlement.blocked
        assert record.problems
    else:
        assert record.settlement is journey.Settlement.approval_not_launched


def test_attempt_state_blocks_settlement_claim_in_headers(tmp_path):
    directory = tmp_path / 'receipt'
    request = _request_tree(directory)
    _write_json(directory / 'approval.json', _approval(request))
    proof = base64.b64encode(json.dumps(
        {'success': True, 'transaction': '0x' + 'a' * 64}).encode())
    _private_write(directory / 'headers.bin',
                   b'HTTP/2 200\r\nX-PAYMENT-RESPONSE: ' + proof + b'\r\n')
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.blocked
    assert any('settlement claim present in headers' in problem for problem in record.problems)


@pytest.mark.parametrize('variant', ['missing', 'extra', 'nonstring', 'hash', 'token',
                                     'version', 'amount-nan', 'amount-ceiling', 'date'])
def test_attempt_state_invalid_approval_blocks(tmp_path, variant):
    directory = tmp_path / 'receipt'
    request = _request_tree(directory)
    approval = _approval(request)
    if variant == 'missing':
        approval.pop('token')
    elif variant == 'extra':
        approval['extra'] = 'x'
    elif variant == 'nonstring':
        approval['request_sha256'] = 123
    elif variant == 'hash':
        approval['request_sha256'] = '0' * 64
    elif variant == 'token':
        approval['token'] = 'DOGE'
    elif variant == 'version':
        approval['buy_version'] = '0.9.0'
    elif variant == 'amount-nan':
        approval['max_amount'] = 'NaN'
    elif variant == 'amount-ceiling':
        approval['max_amount'] = '1'
    elif variant == 'date':
        approval['approved_at'] = 'not-a-date'
    _write_json(directory / 'approval.json', approval)
    _private_write(directory / 'headers.bin', b'')
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.blocked
    assert record.problems
    assert all(len(problem) <= 120 for problem in record.problems)


def test_attempt_state_unreadable_approval_blocks_and_preserves_file(tmp_path):
    directory = tmp_path / 'receipt'
    request = _request_tree(directory)
    path = directory / 'approval.json'
    _write_json(path, _approval(request))
    path.chmod(0o644)
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.blocked
    assert any('approval not launchable' in problem for problem in record.problems)
    assert path.exists()


@pytest.mark.parametrize('validation_body', [
    None,
    paid.canonical({'valid': False, 'automatic_retry': False}),
    b'not-json',
])
def test_attempt_state_launched_outcome_unavailable_ignores_validation(tmp_path, validation_body):
    directory = tmp_path / 'receipt'
    _launched_tree(directory, outcome=False)
    if validation_body is not None:
        _private_write(directory / 'validation.json', validation_body)
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.launched_outcome_unavailable
    assert record.validation in {'absent', 'rejected'}


def test_attempt_state_outcome_recorded_unconfirmed(tmp_path):
    directory = tmp_path / 'receipt'
    _launched_tree(directory)
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.outcome_recorded_unconfirmed


def test_attempt_state_confirmation_without_outcome_blocks(tmp_path):
    directory = tmp_path / 'receipt'
    _launched_tree(directory, outcome=False)
    record = journey.attempt_state(directory, claim_confirmed_by_provider=True)
    assert record.settlement is journey.Settlement.blocked
    assert any('confirmation without local outcome' in problem for problem in record.problems)


def test_attempt_state_provider_confirmed(tmp_path):
    directory = tmp_path / 'receipt'
    _launched_tree(directory)
    record = journey.attempt_state(directory, claim_confirmed_by_provider=True)
    assert record.settlement is journey.Settlement.provider_confirmed


def test_attempt_state_provider_confirmation_requires_approval_and_attempt(tmp_path):
    directory = tmp_path / 'receipt'
    _request_tree(directory)
    _write_json(directory / 'outcome.json', {})
    record = journey.attempt_state(directory, claim_confirmed_by_provider=True)
    assert record.settlement is journey.Settlement.blocked


def test_attempt_state_corrupt_request_blocks(tmp_path):
    directory = tmp_path / 'receipt'
    directory.mkdir()
    _private_write(directory / 'request.json', b'{not json')
    record = journey.attempt_state(directory)
    assert record.settlement is journey.Settlement.blocked
    assert record.problems
    assert all(len(problem) <= 120 for problem in record.problems)


def test_attempt_state_unreadable_directory_blocks(tmp_path):
    directory = tmp_path / 'receipt'
    _request_tree(directory)
    directory.chmod(0o644)
    try:
        record = journey.attempt_state(directory)
    finally:
        directory.chmod(0o700)
    assert record.settlement is journey.Settlement.blocked
    assert record.problems
    assert all(len(problem) <= 120 for problem in record.problems)


def test_scan_attempts_matches_only_the_request_identity(tmp_path):
    root = tmp_path / 'receipts'
    root.mkdir(mode=0o700)
    request = cencori.build_request('install package', artifact_report(), 1024)
    for name in ('s0', 's1'):
        directory = root / name
        directory.mkdir(mode=0o700)
        cencori.preserve_request(request, directory / 'request.json')
    _write_json(root / 's1' / 'approval.json', _approval(request))
    _private_write(root / 's1' / 'headers.bin', b'')
    other = root / 'other'
    other.mkdir(mode=0o700)
    cencori.preserve_request(cencori.build_request('other goal', artifact_report(), 1024),
                             other / 'request.json')
    (root / 'notes.txt').write_text('not a directory')
    matches = journey.scan_attempts(root, request.sha256)
    assert [path.name for path, _ in matches] == ['s0', 's1']
    assert matches[0][1].settlement is journey.Settlement.pre_approval
    assert matches[1][1].settlement is journey.Settlement.approval_not_launched


def test_scan_attempts_aborts_on_unstructurable_directory(tmp_path):
    root = tmp_path / 'receipts'
    root.mkdir(mode=0o700)
    request = cencori.build_request('install package', artifact_report(), 1024)
    good = root / 'good'
    good.mkdir(mode=0o700)
    cencori.preserve_request(request, good / 'request.json')
    broken = root / 'broken'
    broken.mkdir(mode=0o700)
    (broken / 'request.json').mkdir()  # non-regular request artifact
    with pytest.raises(tracking.TrackingError):
        journey.scan_attempts(root, request.sha256)


@pytest.mark.parametrize('digest', ['A' * 64, 'a' * 63, '../' + 'a' * 61, None])
def test_scan_attempts_validates_request_digest(tmp_path, digest):
    with pytest.raises(journey.JourneyError):
        journey.scan_attempts(tmp_path, digest)


# --- Phase 5: fingerprints, destinations and import ------------------------


def _completion_bytes():
    tasks = [{'id': 'review', 'title': 'Review requirements',
              'action': 'Read the retrieved installation passage and record its prerequisites.',
              'prerequisites': [], 'sources': [URL], 'classification': 'required'}]
    return json.dumps({
        'id': 'completion-1', 'object': 'chat.completion', 'created': 1,
        'model': cencori.MODEL,
        'choices': [{'index': 0, 'finish_reason': 'stop',
                     'message': {'role': 'assistant',
                                 'content': json.dumps({'schema_version': 1, 'tasks': tasks})}}],
    }).encode()


def _importable_tree(directory, goal='install package'):
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    request = cencori.build_request(goal, artifact_report(), 1024)
    approval = _approval(request)
    _private_write(directory / 'request.json', request.body)
    _write_json(directory / 'approval.json', approval)
    _write_json(directory / 'attempt.json',
                {**approval, 'outcome': 'starting', 'settlement': 'unknown',
                 'automatic_retry': False})
    _write_json(directory / 'outcome.json',
                {**approval, 'outcome': 'exited', 'returncode': 0,
                 'settlement': 'unknown', 'automatic_retry': False})
    _write_json(directory / 'validation.json', {'valid': True, 'automatic_retry': False})
    _private_write(directory / 'stdout.bin', _completion_bytes())
    _private_write(directory / 'stderr.bin', b'')
    _private_write(directory / 'headers.bin', b'')
    return directory, request.sha256


def _s0_tree(directory):
    _request_tree(directory)
    _private_write(directory / 'headers.bin', b'')
    return directory


def _s1_tree(directory):
    _approved_tree(directory)
    return directory


def _s2_tree(directory):
    _launched_tree(directory, outcome=False)
    return directory


def _headers_with_claim(transaction):
    proof = base64.b64encode(json.dumps(
        {'success': True, 'transaction': transaction}).encode())
    return b'HTTP/2 200\r\nX-PAYMENT-RESPONSE: ' + proof + b'\r\n'


def test_fingerprint_is_deterministic_across_identical_copies(tmp_path):
    first, _ = _importable_tree(tmp_path / 'first')
    second, _ = _importable_tree(tmp_path / 'second')
    value = journey.record_fingerprint(first)
    assert value == journey.record_fingerprint(first)
    assert value == journey.record_fingerprint(second)
    assert len(value) == 64 and value == value.lower()


def test_fingerprint_includes_version(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    base = journey.record_fingerprint(directory)
    with patch.object(journey, 'FINGERPRINT_VERSION', 2):
        assert journey.record_fingerprint(directory) != base


def _mutate_artifact(directory, name):
    path = directory / name
    if name == 'request.json':
        _private_write(path, cencori.build_request('different goal', artifact_report(), 1024).body)
    elif name.endswith('.json'):
        _private_write(path, json.dumps(paid.strict_json(path.read_bytes())).encode())
    else:
        _private_write(path, b'changed')


@pytest.mark.parametrize('name', list(journey._ARTIFACT_LIMITS))
def test_fingerprint_changes_for_each_of_eight_artifacts(tmp_path, name):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    base = journey.record_fingerprint(directory)
    _mutate_artifact(directory, name)
    assert journey.record_fingerprint(directory) != base


@pytest.mark.parametrize('builder,settlement', [
    (_s0_tree, journey.Settlement.pre_approval),
    (_s1_tree, journey.Settlement.approval_not_launched),
    (_s2_tree, journey.Settlement.launched_outcome_unavailable),
])
def test_fingerprint_absence_map_null_matches_state(tmp_path, builder, settlement):
    directory = builder(tmp_path / 'receipt')
    blobs = []
    real = paid.canonical

    def capture(value):
        blob = real(value)
        blobs.append(blob)
        return blob

    with patch.object(journey.paid, 'canonical', side_effect=capture):
        journey.record_fingerprint(directory)
    document = next(json.loads(blob) for blob in blobs if b'fingerprint_version' in blob)
    artifacts = document['artifacts']
    assert document['fingerprint_version'] == journey.FINGERPRINT_VERSION
    assert set(artifacts) == set(journey._ARTIFACT_NAMES)
    if settlement is journey.Settlement.pre_approval:
        for name in ('approval.json', 'attempt.json', 'outcome.json', 'validation.json',
                     'stdout.bin', 'stderr.bin'):
            assert artifacts[name] is None
    elif settlement is journey.Settlement.approval_not_launched:
        for name in ('attempt.json', 'outcome.json', 'validation.json',
                     'stdout.bin', 'stderr.bin'):
            assert artifacts[name] is None
    else:
        for name in ('outcome.json', 'validation.json', 'stdout.bin', 'stderr.bin'):
            assert artifacts[name] is None


def test_fingerprint_rejects_presence_contradiction(tmp_path):
    directory = _s0_tree(tmp_path / 'receipt')
    _private_write(directory / 'stdout.bin', b'')
    with pytest.raises(journey.JourneyError, match='contradicts'):
        journey.record_fingerprint(directory)


def test_fingerprint_refuses_blocked_or_ambiguous(tmp_path):
    directory = tmp_path / 'receipt'
    _request_tree(directory)
    _write_json(directory / 'outcome.json', {})  # outcome without approval/attempt
    with pytest.raises(journey.JourneyError, match='blocked'):
        journey.record_fingerprint(directory)


def test_fingerprint_rejects_loose_permissions_and_links(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    (directory / 'stdout.bin').chmod(0o644)
    with pytest.raises(journey.JourneyError, match='0600'):
        journey.record_fingerprint(directory)

    other, _ = _importable_tree(tmp_path / 'other')
    target = tmp_path / 'target'
    _private_write(target, b'x')
    (other / 'stderr.bin').unlink()
    (other / 'stderr.bin').symlink_to(target)
    with pytest.raises(journey.JourneyError):
        journey.record_fingerprint(other)

    third, _ = _importable_tree(tmp_path / 'third')
    (third / 'headers.bin').unlink()
    (third / 'headers.bin').mkdir()
    with pytest.raises(journey.JourneyError):
        journey.record_fingerprint(third)


@pytest.mark.parametrize('name', list(journey._ARTIFACT_LIMITS))
def test_artifact_hash_enforces_exact_size_limit(tmp_path, name):
    limit = journey._ARTIFACT_LIMITS[name]
    path = tmp_path / 'artifact.bin'
    _private_write(path, b'a' * limit)
    assert journey._artifact_hash(path, limit) == hashlib.sha256(b'a' * limit).hexdigest()
    _private_write(path, b'a' * limit + b'b')
    with pytest.raises(journey.JourneyError, match='exceeds'):
        journey._artifact_hash(path, limit)


def test_artifact_limits_match_owner_contract():
    assert journey._ARTIFACT_LIMITS == {
        'request.json': 32768, 'stdout.bin': 131072, 'stderr.bin': 524288,
        'approval.json': 16384, 'attempt.json': 16384, 'outcome.json': 16384,
        'validation.json': 16384, 'headers.bin': 131073,
    }
    assert journey._ARTIFACT_LIMITS['headers.bin'] == paid.RESPONSE_BYTES + 1
    assert journey._ARTIFACT_LIMITS['stdout.bin'] == paid.RESPONSE_BYTES


@pytest.mark.parametrize('bad', ['a' * 63, 'a' * 65, 'A' * 64, 'g' * 64,
                                 '../' + 'a' * 61, None, 123])
def test_tracking_destination_validates_both_digests_before_paths(tmp_path, bad):
    with pytest.raises(journey.JourneyError):
        journey.tracking_destination(bad, 'f' * 64, tmp_path)
    with pytest.raises(journey.JourneyError):
        journey.tracking_destination('f' * 64, bad, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_canonical_identity_normalises_equivalent_forms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = journey._canonical_identity(tmp_path / 'a' / 'track')
    assert journey._canonical_identity('a/track') == expected
    assert journey._canonical_identity(tmp_path / 'a' / '..' / 'a' / 'track') == expected
    assert journey._canonical_identity(str(tmp_path) + '//a/track') == expected
    # A symlinked alias resolves to its target identity.
    (tmp_path / 'other').mkdir()
    (tmp_path / 'alias').symlink_to(tmp_path / 'other', target_is_directory=True)
    assert (journey._canonical_identity(tmp_path / 'alias')
            == journey._canonical_identity(tmp_path / 'other'))
    # A not-yet-existing final component is not created or followed.
    missing = journey._canonical_identity(tmp_path / 'missing' / 'track')
    assert missing.endswith('missing/track') and not (tmp_path / 'missing').exists()


def test_import_outcome_imports_valid_s3_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    fingerprint = journey.record_fingerprint(receipt)
    first = journey.import_outcome(receipt)
    assert first.disposition == 'imported'
    assert first.record.settlement is journey.Settlement.outcome_recorded_unconfirmed
    assert first.record.validation == 'valid'
    expected_destination = tmp_path / '.honeyguider' / 'track' / f'{key}-{fingerprint}'
    assert first.destination.resolve() == expected_destination
    assert first.canonical_duplicate is False
    state = tracking.load(expected_destination)
    assert state['receipt'] == str(receipt.resolve())
    assert state['request_sha256'] == key
    assert [entry.name for entry in expected_destination.iterdir()] == ['000000.json']

    second = journey.import_outcome(receipt)
    assert second.disposition == 'already_imported'
    assert second.canonical_duplicate is True
    assert second.destination.resolve() == expected_destination
    assert [entry.name for entry in expected_destination.iterdir()] == ['000000.json']


@pytest.mark.parametrize('builder', [_s0_tree, _s1_tree, _s2_tree])
def test_import_outcome_rejects_ineligible_states(tmp_path, monkeypatch, builder):
    monkeypatch.chdir(tmp_path)
    receipt = builder(tmp_path / 'receipt')
    data = journey.import_outcome(receipt)
    assert data.disposition == 'unimportable'
    assert data.record.settlement is not journey.Settlement.outcome_recorded_unconfirmed
    assert data.destination is None or data.record.settlement is not journey.Settlement.blocked


def test_import_outcome_rejects_blocked_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt = tmp_path / 'receipt'
    _request_tree(receipt)
    _write_json(receipt / 'outcome.json', {})
    data = journey.import_outcome(receipt)
    assert data.disposition == 'unimportable'
    assert data.record.settlement is journey.Settlement.blocked
    assert data.destination is None
    assert data.canonical_duplicate is None


def test_import_outcome_provider_confirmed_is_not_eligible(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    confirmed = journey.AttemptRecord(receipt, journey.Settlement.provider_confirmed,
                                      'valid', ())
    with patch.object(journey, 'attempt_state', return_value=confirmed):
        data = journey.import_outcome(receipt)
    assert data.disposition == 'unimportable'
    assert data.record.settlement is journey.Settlement.provider_confirmed


def test_import_outcome_custom_root_requires_explicit_consent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    custom = tmp_path / 'custom-track'
    refused = journey.import_outcome(receipt, tracking_root=custom)
    assert refused.disposition == 'custom_consent_required'
    assert refused.custom_root is True and refused.custom_root_consent is False
    assert refused.destination.parent == custom
    assert not custom.exists()

    allowed = journey.import_outcome(receipt, tracking_root=custom, custom_root_consent=True)
    assert allowed.disposition == 'imported'
    assert allowed.custom_root is True and allowed.custom_root_consent is True
    assert allowed.destination.exists()
    assert tracking.load(allowed.destination)['request_sha256'] == key


def test_import_outcome_interrupted_destination_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    fingerprint = journey.record_fingerprint(receipt)
    destination = journey.tracking_destination(key, fingerprint)
    destination.mkdir(parents=True, mode=0o700)
    data = journey.import_outcome(receipt)
    assert data.disposition == 'interrupted_destination'
    assert data.destination == destination
    assert list(destination.iterdir()) == []


def test_import_outcome_malformed_destination_conflicts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    fingerprint = journey.record_fingerprint(receipt)
    destination = journey.tracking_destination(key, fingerprint)
    destination.mkdir(parents=True, mode=0o700)
    (destination / 'junk').write_text('not a revision')
    data = journey.import_outcome(receipt)
    assert data.disposition == 'conflict'
    assert any('malformed destination' in problem for problem in data.problems)


def test_import_outcome_recognises_byte_identical_copy_without_relocating(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    first = journey.import_outcome(receipt)
    assert first.disposition == 'imported'
    copy = tmp_path / 'copy'
    shutil.copytree(receipt, copy)
    for path in copy.iterdir():
        path.chmod(0o600)
    copy.chmod(0o700)
    second = journey.import_outcome(copy)
    assert second.disposition == 'already_imported'
    assert second.destination == first.destination
    assert tracking.load(first.destination)['receipt'] == str(receipt.resolve())


def test_import_outcome_conflicts_when_recorded_receipt_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    first = journey.import_outcome(receipt)
    assert first.disposition == 'imported'
    copy = tmp_path / 'copy'
    shutil.copytree(receipt, copy)
    for path in copy.iterdir():
        path.chmod(0o600)
    copy.chmod(0o700)
    shutil.rmtree(receipt)
    data = journey.import_outcome(copy)
    assert data.disposition == 'conflict'
    assert any('recorded receipt missing or unreadable' in problem for problem in data.problems)


def test_import_outcome_conflicts_when_recorded_receipt_changed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    copy = tmp_path / 'copy'
    shutil.copytree(receipt, copy)
    for path in copy.iterdir():
        path.chmod(0o600)
    copy.chmod(0o700)
    assert journey.import_outcome(receipt).disposition == 'imported'
    _private_write(receipt / 'stderr.bin', b'changed-after-import')
    data = journey.import_outcome(copy)
    assert data.disposition == 'conflict'
    assert any('does not match this evidence' in problem for problem in data.problems)


def test_import_outcome_canonical_duplicate_tristate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    assert journey.import_outcome(receipt).canonical_duplicate is False
    assert journey.import_outcome(receipt).canonical_duplicate is True

    bad, _ = _importable_tree(tmp_path / 'bad', goal='different goal')
    fingerprint = journey.record_fingerprint(bad)
    canonical = journey.tracking_destination(
        paid.load_request(bad / 'request.json').request.sha256, fingerprint)
    canonical.mkdir(parents=True, mode=0o700)
    (canonical / 'junk').write_text('x')
    data = journey.import_outcome(bad)
    assert data.canonical_duplicate is None
    assert any('canonical duplicate unverifiable' in problem for problem in data.problems)


def test_import_outcome_post_import_mutation_discloses_without_deleting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    real_import = tracking.import_receipt

    def mutating(receipt_dir, destination):
        _private_write(Path(receipt_dir) / 'stderr.bin', b'mutated-during-import')
        return real_import(receipt_dir, destination)

    with patch.object(journey.tracking, 'import_receipt', side_effect=mutating):
        data = journey.import_outcome(receipt)
    assert data.disposition == 'conflict'
    assert any('changed during import' in problem for problem in data.problems)
    assert data.destination.exists()
    assert list(data.destination.iterdir())


def test_import_outcome_maps_concurrent_creation_to_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    with patch.object(journey.tracking, 'import_receipt',
                      side_effect=FileExistsError('appeared concurrently')):
        data = journey.import_outcome(receipt)
    assert data.disposition == 'conflict'
    assert any('concurrently' in problem for problem in data.problems)


def test_import_outcome_maps_tracking_refusal_to_unimportable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    with patch.object(journey.tracking, 'import_receipt',
                      side_effect=tracking.TrackingError('tracking says no')):
        data = journey.import_outcome(receipt)
    assert data.disposition == 'unimportable'
    assert any('tracking refused receipt' in problem for problem in data.problems)


def test_import_outcome_keeps_unknown_settlement_unknown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt, key = _importable_tree(tmp_path / 'receipt')
    assert journey.attempt_state(receipt).settlement is journey.Settlement.outcome_recorded_unconfirmed
    data = journey.import_outcome(receipt)
    assert data.disposition == 'imported'
    after = journey.attempt_state(receipt)
    assert after.settlement is journey.Settlement.outcome_recorded_unconfirmed
    assert after.settlement is not journey.Settlement.provider_confirmed


def test_correlate_claim_unavailable_without_claim_or_rows(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    assert journey.correlate_claim(directory, []) == 'unavailable'
    transaction = '0x' + 'a' * 64
    _private_write(directory / 'headers.bin', _headers_with_claim(transaction))
    assert journey.correlate_claim(directory, []) == 'unavailable'


def test_correlate_claim_correlates_single_consistent_row(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    transaction = '0x' + 'a' * 64
    _private_write(directory / 'headers.bin', _headers_with_claim(transaction))
    row = SimpleNamespace(tx_hash=transaction.upper(), token='USDC', network='celo')
    assert journey.correlate_claim(directory, [row]) == 'correlated'


def test_correlate_claim_conflicts_on_ambiguous_or_inconsistent_rows(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    transaction = '0x' + 'a' * 64
    _private_write(directory / 'headers.bin', _headers_with_claim(transaction))
    good = SimpleNamespace(tx_hash=transaction, token='USDC', network='celo')
    duplicate = SimpleNamespace(tx_hash=transaction, token='USDC', network='celo')
    wrong_token = SimpleNamespace(tx_hash=transaction, token='USDT', network='celo')
    wrong_network = SimpleNamespace(tx_hash=transaction, token='USDC', network='celo-sepolia')
    assert journey.correlate_claim(directory, [good, duplicate]) == 'conflicting'
    assert journey.correlate_claim(directory, [wrong_token]) == 'conflicting'
    assert journey.correlate_claim(directory, [wrong_network]) == 'conflicting'


def test_correlation_never_changes_attempt_state(tmp_path):
    directory, _ = _importable_tree(tmp_path / 'receipt')
    transaction = '0x' + 'a' * 64
    _private_write(directory / 'headers.bin', _headers_with_claim(transaction))
    before = journey.attempt_state(directory)
    assert journey.correlate_claim(
        directory, [SimpleNamespace(tx_hash=transaction, token='USDC', network='celo')]) == 'correlated'
    after = journey.attempt_state(directory)
    assert before.settlement is after.settlement is journey.Settlement.outcome_recorded_unconfirmed


def test_correlation_result_is_independent_of_import_disposition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt = _s2_tree(tmp_path / 'receipt')
    transaction = '0x' + 'a' * 64
    _private_write(receipt / 'headers.bin', _headers_with_claim(transaction))
    row = SimpleNamespace(tx_hash=transaction, token='USDC', network='celo')
    assert journey.correlate_claim(receipt, [row]) == 'correlated'
    data = journey.import_outcome(receipt)
    assert data.disposition == 'unimportable'
    assert data.record.settlement is journey.Settlement.launched_outcome_unavailable


def test_canonical_identity_works_for_roots_outside_cwd(tmp_path, monkeypatch):
    outside = tmp_path / 'outside' / 'track'
    monkeypatch.chdir(tmp_path)
    assert journey._canonical_identity(outside) == os.path.realpath(outside)
    assert journey._canonical_identity('/tmp') == os.path.realpath('/tmp')


# --- Phase 6: lazy locking and tracked-plan listing --------------------------


def test_acquire_attempt_lock_reports_missing_posix_locking(tmp_path):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == 'fcntl':
            raise ImportError('simulated non-POSIX platform')
        return real_import(name, *args, **kwargs)

    with patch('builtins.__import__', side_effect=fake_import):
        with pytest.raises(journey.JourneyError) as caught:
            with journey.acquire_attempt_lock('a' * 64, tmp_path / 'locks'):
                pass
    message = str(caught.value)
    for phrase in ('POSIX advisory locking is unavailable', 'Linux verified',
                   'macOS unverified', 'native Windows locking is not implemented'):
        assert phrase in message
    # The platform check precedes lock-directory creation (no artifacts).
    assert not (tmp_path / 'locks').exists()


def test_journey_has_no_module_level_fcntl_import():
    tree = ast.parse(Path(journey.__file__).read_text())
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)
    assert 'fcntl' not in top_level
    assert not hasattr(journey, 'fcntl')


def _tracked_plan(root, receipt, name='plan'):
    destination = root / name
    tracking.import_receipt(receipt, destination)
    return destination


def _snapshot(root):
    return {path.relative_to(root): (path.read_bytes(), path.stat().st_mode & 0o777)
            for path in sorted(root.rglob('*')) if path.is_file()}


def test_list_tracked_plans_missing_or_empty_root(tmp_path):
    assert journey.list_tracked_plans(tmp_path / 'missing') == []
    empty = tmp_path / 'empty'
    empty.mkdir()
    assert journey.list_tracked_plans(empty) == []


def test_list_tracked_plans_contains_each_directory_failure(tmp_path):
    receipt, key = _importable_tree(tmp_path / 'receipt')
    root = tmp_path / 'track'
    root.mkdir(mode=0o700)
    healthy = _tracked_plan(root, receipt, 'healthy')
    corrupt = root / 'corrupt'
    corrupt.mkdir(mode=0o700)

    plans = journey.list_tracked_plans(root)
    assert [plan.directory.name for plan in plans] == ['corrupt', 'healthy']
    broken, good = plans
    assert broken.directory == corrupt
    assert broken.request_sha256 is None and broken.fingerprint is None
    assert broken.tasks == 0 and broken.completed == 0
    assert broken.settlement == 'unknown'
    assert broken.problems and 'unreadable or malformed tracking directory' in broken.problems[0]

    assert good.directory == healthy
    assert good.request_sha256 == key
    assert good.fingerprint == journey.record_fingerprint(receipt)
    assert good.tasks == 1 and good.completed == 0
    assert good.settlement == 'unknown' and good.problems == ()
    assert all(plan.settlement != 'confirmed' for plan in plans)


def test_list_tracked_plans_skips_files_and_symlinks(tmp_path):
    receipt, _ = _importable_tree(tmp_path / 'receipt')
    root = tmp_path / 'track'
    root.mkdir(mode=0o700)
    healthy = _tracked_plan(root, receipt)
    (root / 'notes.txt').write_text('not a plan')
    (root / 'alias').symlink_to(healthy, target_is_directory=True)

    plans = journey.list_tracked_plans(root)
    assert [plan.directory for plan in plans] == [healthy]
    assert plans[0].settlement == 'unknown'


def test_list_tracked_plans_reports_archived_receipt_without_confirming(tmp_path):
    receipt, key = _importable_tree(tmp_path / 'receipt')
    root = tmp_path / 'track'
    _tracked_plan(root, receipt)
    receipt.rename(tmp_path / 'receipt-archived')

    plan, = journey.list_tracked_plans(root)
    assert plan.request_sha256 == key
    assert plan.fingerprint is None
    assert plan.settlement is None
    assert plan.problems and 'recorded receipt missing or unreadable' in plan.problems[0]


def test_list_tracked_plans_is_read_only(tmp_path):
    receipt, _ = _importable_tree(tmp_path / 'receipt')
    root = tmp_path / 'track'
    _tracked_plan(root, receipt)
    receipt_before = _snapshot(tmp_path)
    root_before = _snapshot(root)
    journey.list_tracked_plans(root)
    assert _snapshot(root) == root_before
    assert _snapshot(tmp_path) == receipt_before


def test_list_tracked_plans_does_not_recurse(tmp_path):
    receipt, _ = _importable_tree(tmp_path / 'receipt')
    root = tmp_path / 'track'
    root.mkdir(mode=0o700)
    broken = root / 'broken'
    broken.mkdir(mode=0o700)
    nested = broken / 'nested'
    tracking.import_receipt(receipt, nested)
    nested_before = _snapshot(nested)

    plans = journey.list_tracked_plans(root)
    assert [plan.directory for plan in plans] == [broken]
    assert plans[0].problems
    assert _snapshot(nested) == nested_before
