"""Offline public-artifact and isolation regressions."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from honeyguider.planning import PlanError, next_action
from honeyguider.recorded import load_recording, validate_recording

IDS = ['author-registration-file', 'host-registration-file', 'register-from-owner-key',
       'read-agent-id-from-event', 'add-registrations-crossref', 'point-registry-at-file',
       'maintain-payee-wallet', 'support-x402-payments', 'retire-service']


def test_genuine_plan_and_graph():
    data, plan = load_recording()
    assert [t.id for t in plan.tasks] == IDS
    assert sum(t.classification == 'required' for t in plan.tasks) == 6
    assert sum(t.classification == 'optional' for t in plan.tasks) == 3
    assert next_action(plan, frozenset()).id == IDS[0]
    assert all(set(t.sources) <= set(data['sources']) for t in plan.tasks)
    assert all(set(t.prerequisites) <= set(IDS) for t in plan.tasks)


@pytest.mark.parametrize('change', ['extra', 'title', 'cycle', 'citation', 'count', 'model', 'settlement', 'bool'])
def test_tampering_fails_closed(change):
    data = copy.deepcopy(load_recording()[0])
    if change == 'extra': data['headers'] = {'Authorization': 'secret'}
    if change == 'title': data['plan']['tasks'][0]['title'] = 'Replacement'
    if change == 'cycle': data['plan']['tasks'][0]['prerequisites'] = [IDS[0]]
    if change == 'citation': data['plan']['tasks'][0]['sources'] = ['https://evil.example']
    if change == 'count': data['plan']['tasks'].pop()
    if change == 'model': data['model'] = 'other'
    if change == 'settlement': data['local_settlement'] = 'verified'
    if change == 'bool': data['schema_version'] = True
    with pytest.raises(PlanError): validate_recording(json.dumps(data))


@pytest.mark.parametrize('raw', ['{}', 'null', '{', '{"model":1,"model":2}', 'x' * 65537])
def test_malformed(raw):
    with pytest.raises(PlanError): validate_recording(raw)


def test_no_sensitive_fields():
    data, _ = load_recording()
    forbidden = {'messages', 'headers', 'stderr', 'wallet', 'private_key', 'approval', 'session_code',
                 'request', 'response', 'receipt', 'credentials', 'authorization', 'prompt'}
    def walk(value):
        if isinstance(value, dict):
            assert not set(value) & forbidden
            for v in value.values(): walk(v)
        elif isinstance(value, list):
            for v in value: walk(v)
    walk(data)


def test_runtime_import_isolation():
    code = "import sys; from honeyguider.recorded import load_recording; load_recording(); assert not any('honeyguider.'+n in sys.modules for n in ['paid','tracking','cencori','cli','state','checks'])"
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
