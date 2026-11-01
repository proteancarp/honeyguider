import json
import socket
import subprocess

import httpx
import pytest
from typer.testing import CliRunner

from honeyguider import cencori, paid, tracking
from honeyguider.cli import app
from honeyguider.research import Report, extract

URL = 'https://docs.example.com/guide'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Tracking attempted network, subprocess, wallet access or payment')
    for target, attribute in [(socket, 'getaddrinfo'), (socket, 'create_connection'),
                              (subprocess, 'run'), (subprocess, 'Popen'),
                              (httpx.Client, 'send'), (httpx.AsyncClient, 'send'),
                              (paid, 'infer'), (paid, 'wallet_environment'),
                              (paid, 'supervise'), (cencori, '_run')]:
        monkeypatch.setattr(target, attribute, forbidden)


@pytest.fixture
def receipt(tmp_path):
    directory = tmp_path / 'receipt'
    directory.mkdir(mode=0o700)
    report = Report(pages=[extract(b'<h2>Install package</h2><p>Install package locally.</p>', URL, 'install package')])
    request = cencori.build_request('install package', report)
    (directory / 'request.json').write_bytes(request.body)
    tasks = [{'id': name, 'title': name.title(), 'action': 'Review the source manually.',
              'prerequisites': deps, 'sources': [URL], 'classification': kind}
             for name, deps, kind in [('extra', [], 'optional'), ('setup', [], 'optional'),
                                       ('build', ['setup'], 'required'), ('test', ['build'], 'required')]]
    completion = {'model': cencori.MODEL, 'choices': [{'index': 0, 'finish_reason': 'stop',
                  'message': {'role': 'assistant', 'content': json.dumps({'schema_version': 1, 'tasks': tasks})}}]}
    approval = {'request_sha256': request.sha256, 'token': 'USDC', 'max_amount': '0.01',
                'endpoint': cencori.ENDPOINT, 'method': 'POST', 'buy_executable': '/trusted/buy',
                'buy_version': '0.8.4', 'approved_at': '2026-01-01T00:00:00+00:00'}
    data = {'approval.json': approval,
            'attempt.json': {**approval, 'outcome': 'starting', 'settlement': 'unknown', 'automatic_retry': False},
            'outcome.json': {**approval, 'outcome': 'exited', 'returncode': 0, 'settlement': 'unknown', 'automatic_retry': False},
            'validation.json': {'valid': True, 'automatic_retry': False}, 'stdout.bin': completion}
    for name, value in data.items():
        (directory / name).write_text(json.dumps(value))
    for path in directory.iterdir():
        path.chmod(0o600)
    return directory


def invoke(directory, *args, demo=None):
    prefix = ['--state-file', str(demo)] if demo is not None else []
    return CliRunner().invoke(app, prefix + ['track', '--state-dir', str(directory), *args])


def rewrite(path, mutate):
    value = json.loads(path.read_bytes())
    mutate(value)
    path.write_text(json.dumps(value))


def test_persistent_workflow_and_separate_demo(receipt, tmp_path):
    directory, demo = tmp_path / 'track', tmp_path / 'demo.json'
    assert CliRunner().invoke(app, ['--state-file', str(demo), 'explore', '--demo']).exit_code == 0
    demo_before = demo.read_bytes()
    before = {p.name: p.read_bytes() for p in receipt.iterdir()}
    result = invoke(directory, 'import', '--receipt-dir', str(receipt), demo=demo)
    assert result.exit_code == 0, result.output
    initial = (directory / '000000.json').read_bytes()
    assert directory.stat().st_mode & 0o777 == 0o700
    assert invoke(directory, 'next').output.startswith('setup:')
    shown = invoke(directory, 'show')
    assert shown.exit_code == 0
    for text in ['extra:', 'setup:', 'build:', 'test:', 'Prerequisites: setup', URL, 'Action:', 'blocked', 'optional']:
        assert text in shown.output
    assert invoke(directory, 'done', 'build').exit_code == 1
    assert invoke(directory, 'done', 'unknown').exit_code == 1
    for task in ['setup', 'build', 'test']:
        assert invoke(directory, 'done', task).exit_code == 0
        assert invoke(directory, 'done', task).exit_code == 1
    assert 'All required tasks complete' in invoke(directory, 'next').output
    assert 'Required: 2/2 complete; total: 3/4 complete' in invoke(directory, 'status').output
    assert invoke(directory, 'done', 'extra').exit_code == 0
    assert 'total: 4/4' in invoke(directory, 'status').output
    assert tracking.load(directory)['completed'] == ['setup', 'build', 'test', 'extra']
    assert (directory / '000000.json').read_bytes() == initial
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    assert demo.read_bytes() == demo_before
    assert before == {p.name: p.read_bytes() for p in receipt.iterdir()}


@pytest.mark.parametrize('kind', ['missing-request', 'bad-request', 'bad-system', 'bad-completion',
    'truncated', 'cycle', 'citation', 'duplicate-json', 'oversize', 'missing-outcome',
    'failed', 'timeout', 'bad-returncode', 'hash', 'attempt', 'invalid', 'unknown-field',
    'shared-file', 'shared-directory', 'symlink', 'missing-validation', 'missing-attempt',
    'invalid-cap', 'invalid-time', 'duplicate-validation', 'validation-only'])
def test_bad_receipts_never_create_state(receipt, tmp_path, kind):
    request, raw = receipt / 'request.json', receipt / 'stdout.bin'
    if kind == 'missing-request': request.unlink()
    elif kind == 'bad-request': request.write_bytes(b'{}')
    elif kind == 'bad-system':
        value = json.loads(request.read_bytes()); value['messages'][0]['content'] = 'tampered'
        request.write_bytes(paid.canonical(value))
    elif kind == 'bad-completion': raw.write_bytes(b'not json')
    elif kind == 'truncated': rewrite(raw, lambda v: v['choices'][0].update(finish_reason='length'))
    elif kind in ('cycle', 'citation'):
        value = json.loads(raw.read_bytes())
        plan = json.loads(value['choices'][0]['message']['content'])
        if kind == 'cycle': plan['tasks'][1]['prerequisites'] = ['test']
        else: plan['tasks'][0]['sources'] = ['https://invented.example.com/']
        value['choices'][0]['message']['content'] = json.dumps(plan)
        raw.write_text(json.dumps(value))
    elif kind == 'duplicate-json': raw.write_bytes(b'{"choices":[],"choices":[]}')
    elif kind == 'oversize': raw.write_bytes(b'x' * (paid.RESPONSE_BYTES + 1))
    elif kind == 'missing-outcome': (receipt / 'outcome.json').unlink()
    elif kind == 'failed': rewrite(receipt / 'outcome.json', lambda v: v.update(returncode=1))
    elif kind == 'timeout': rewrite(receipt / 'outcome.json', lambda v: v.update(outcome='timeout'))
    elif kind == 'bad-returncode': rewrite(receipt / 'outcome.json', lambda v: v.update(returncode=False))
    elif kind == 'hash': rewrite(receipt / 'approval.json', lambda v: v.update(request_sha256='0' * 64))
    elif kind == 'attempt': rewrite(receipt / 'attempt.json', lambda v: v.update(token='USAT'))
    elif kind == 'invalid': rewrite(receipt / 'validation.json', lambda v: v.update(valid=False))
    elif kind == 'unknown-field': rewrite(receipt / 'validation.json', lambda v: v.update(extra=1))
    elif kind == 'shared-file': raw.chmod(0o644)
    elif kind == 'shared-directory': receipt.chmod(0o755)
    elif kind == 'symlink':
        raw.rename(receipt / 'original'); raw.symlink_to(receipt / 'original')
    elif kind == 'missing-validation': (receipt / 'validation.json').unlink()
    elif kind == 'missing-attempt': (receipt / 'attempt.json').unlink()
    elif kind == 'invalid-cap': rewrite(receipt / 'approval.json', lambda v: v.update(max_amount='NaN'))
    elif kind == 'invalid-time': rewrite(receipt / 'approval.json', lambda v: v.update(approved_at='invalid'))
    elif kind == 'duplicate-validation': (receipt / 'validation.json').write_text('{"valid":true,"valid":true,"automatic_retry":false}')
    elif kind == 'validation-only':
        for path in receipt.iterdir():
            if path.name != 'validation.json': path.unlink()
    directory = tmp_path / 'track'
    result = invoke(directory, 'import', '--receipt-dir', str(receipt))
    assert result.exit_code == 1, result.output
    assert not directory.exists()


@pytest.mark.parametrize('kind', ['version', 'boolean-version', 'unknown-field', 'unknown-id',
    'duplicate-id', 'prerequisites', 'wrong-type', 'plan', 'sources', 'hash', 'duplicate-key', 'large'])
def test_corrupt_state_is_preserved(receipt, tmp_path, kind):
    directory = tmp_path / 'track'
    tracking.import_receipt(receipt, directory)
    path = directory / '000000.json'
    state = json.loads(path.read_bytes())
    if kind == 'version': state['schema_version'] = 2
    elif kind == 'boolean-version': state['schema_version'] = True
    elif kind == 'unknown-field': state['extra'] = 1
    elif kind == 'unknown-id': state.update(completed=['missing'], revision=1)
    elif kind == 'duplicate-id': state.update(completed=['setup', 'setup'], revision=2)
    elif kind == 'prerequisites': state.update(completed=['test'], revision=1)
    elif kind == 'wrong-type': state['completed'] = [None]
    elif kind == 'plan': state['plan']['tasks'][0]['prerequisites'] = ['extra']
    elif kind == 'sources': state['sources'] = ['http://localhost/']
    elif kind == 'hash': state['request_sha256'] = 'bad'
    path.write_text(json.dumps(state))
    if kind == 'duplicate-key': path.write_text('{"schema_version":1,"schema_version":1}')
    if kind == 'large': path.write_bytes(b'x' * (tracking.STATE_BYTES + 1))
    before = path.read_bytes()
    for command in [('status',), ('next',), ('show',), ('done', 'setup'), ('import', '--receipt-dir', str(receipt))]:
        assert invoke(directory, *command).exit_code == 1
        assert path.read_bytes() == before
        assert len(list(directory.iterdir())) == 1


def test_exclusive_atomic_revisions_and_failure_cleanup(receipt, tmp_path, monkeypatch):
    directory = tmp_path / 'track'
    tracking.import_receipt(receipt, directory)
    state = tracking.load(directory)
    original = (directory / '000000.json').read_bytes()
    with pytest.raises(FileExistsError): tracking.append(directory, state)
    assert (directory / '000000.json').read_bytes() == original
    state.update(completed=['setup'], revision=1)
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(tracking.os, 'fsync', fail)
    with pytest.raises(OSError): tracking.append(directory, state)
    assert [p.name for p in directory.iterdir()] == ['000000.json']
    assert tracking.load(directory)['completed'] == []


@pytest.mark.parametrize('kind', ['gap', 'unexpected', 'changed-plan', 'changed-history', 'permissions'])
def test_history_integrity(receipt, tmp_path, kind):
    directory = tmp_path / 'track'
    tracking.import_receipt(receipt, directory)
    assert invoke(directory, 'done', 'setup').exit_code == 0
    assert invoke(directory, 'done', 'build').exit_code == 0
    if kind == 'gap': (directory / '000001.json').unlink()
    elif kind == 'unexpected': (directory / '.pending-crash').touch()
    elif kind == 'changed-plan': rewrite(directory / '000001.json', lambda v: v['plan']['tasks'][0].update(title='Changed'))
    elif kind == 'changed-history': rewrite(directory / '000002.json', lambda v: v.update(completed=['extra', 'setup']))
    else: (directory / '000001.json').chmod(0o644)
    assert invoke(directory, 'status').exit_code == 1


def test_import_refuses_existing_and_demo_paths(receipt, tmp_path):
    directory = tmp_path / 'empty'
    directory.mkdir(mode=0o700)
    assert invoke(directory, 'import', '--receipt-dir', str(receipt)).exit_code == 1
    assert list(directory.iterdir()) == []
    assert invoke(tmp_path / 'new', 'status').exit_code == 1
    demo = tmp_path / 'demo.json'
    demo.write_text('preserve')
    assert invoke(demo, 'import', '--receipt-dir', str(receipt), demo=demo).exit_code == 2
    assert invoke(tmp_path, 'import', '--receipt-dir', str(receipt), demo=demo).exit_code == 2
    assert demo.read_text() == 'preserve'


def test_saved_plan_survives_missing_receipt(receipt, tmp_path):
    directory = tmp_path / 'track'
    tracking.import_receipt(receipt, directory)
    receipt.rename(tmp_path / 'archived')
    assert invoke(directory, 'done', 'setup').exit_code == 0
    assert invoke(directory, 'next').output.startswith('build:')


def test_default_directory_is_opt_in(receipt, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ['track', 'status']).exit_code == 1
    assert not (tmp_path / '.honeyguider').exists()
    result = CliRunner().invoke(app, ['track', 'import', '--receipt-dir', str(receipt)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / '.honeyguider/track/000000.json').exists()
    assert not (tmp_path / '.pathf1ndar').exists()


def test_atomic_publication_and_link_failure(receipt, tmp_path, monkeypatch):
    directory = tmp_path / 'track'
    tracking.import_receipt(receipt, directory)
    state = tracking.load(directory)
    state.update(completed=['setup'], revision=1)
    real_link = tracking.os.link
    def inspect(source, destination):
        assert not destination.exists()
        assert json.loads(source.read_bytes()) == state
        assert source.stat().st_mode & 0o777 == 0o600
        real_link(source, destination)
    monkeypatch.setattr(tracking.os, 'link', inspect)
    tracking.append(directory, state)
    assert tracking.load(directory)['completed'] == ['setup']
    state.update(completed=['setup', 'build'], revision=2)
    def fail(*args): raise OSError('link failed')
    monkeypatch.setattr(tracking.os, 'link', fail)
    with pytest.raises(OSError): tracking.append(directory, state)
    assert tracking.load(directory)['completed'] == ['setup']
    assert sorted(p.name for p in directory.iterdir()) == ['000000.json', '000001.json']
