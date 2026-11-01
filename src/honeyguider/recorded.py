"""Public, read-only recorded inference. No private workflow dependencies."""
import hashlib
from importlib.resources import files
import json

from .planning import PlanError, _object, validate_plan

SOURCE = 'https://docs.celo.org/build/agents/8004'
TRANSACTION = '0x4b22baa85c1c57753981163f14703b4c824be553a7ef734091fd808113d9d8d0'
EXPLORER = 'https://celoscan.io/tx/' + TRANSACTION
METADATA = {
    'schema_version': 1,
    'label': 'Recorded AI Inference',
    'goal': 'register a service',
    'model': 'maximo-atlas-1.3',
    'sources': [SOURCE],
    'network': 'Celo Mainnet',
    'chain_id': 42220,
    'transaction_hash': TRANSACTION,
    'token': 'USDC',
    'authorized_amount': '0.01',
    'quoted_amount': '0.01',
    'max_output_tokens': 4096,
    'prompt_tokens': 1639,
    'completion_tokens': 1206,
    'total_tokens': 2845,
    'finish_reason': 'stop',
    'local_settlement': 'unknown',
}
# Pins the reviewed public artifact, not the private response envelope.
FIXTURE_SHA256 = 'a431a58f70c0a0aa72a3b49ca8172725236cc24240b6b6d4d9cd8b8c1438dc43'


def validate_recording(raw: str):
    """Strict schema plus provenance pin; fail closed on changed public data."""
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 65536:
        raise PlanError('Invalid recording size')
    try:
        data = json.loads(raw, object_pairs_hook=_object)
    except (ValueError, RecursionError) as exc:
        raise PlanError('Invalid recording JSON') from exc
    if not isinstance(data, dict) or set(data) != set(METADATA) | {'plan'}:
        raise PlanError('Invalid recording fields')
    if any(type(data[k]) is not type(v) or data[k] != v for k, v in METADATA.items()):
        raise PlanError('Unexpected recording metadata')
    plan = validate_plan(json.dumps(data['plan']), {SOURCE})
    if len(plan.tasks) != 9 or sum(t.classification == 'required' for t in plan.tasks) != 6:
        raise PlanError('Unexpected recorded task counts')
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != FIXTURE_SHA256:
        raise PlanError('Recording differs from reviewed export')
    return data, plan


def load_recording():
    return validate_recording(files('honeyguider').joinpath('recorded_inference.json').read_text(encoding='utf-8'))
