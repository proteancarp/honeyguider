"""Offline one-purpose exporter. Imports validators only; never calls execution.

Run from the repository with PYTHONPATH=src. Output is exclusively public fields.
"""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from honeyguider.paid import load_request, offers, parse_completion, strict_json
from honeyguider.recorded import METADATA, TRANSACTION, validate_recording
from honeyguider.tracking import receipt_state


def require(condition):
    if not condition:
        raise ValueError("Receipt does not match reviewed attempt-005 metadata")


def export(directory: Path):
    # Also validate private receipt consistency; never export the returned state.
    receipt_state(directory)
    saved = load_request(directory / 'request.json')
    with (directory / 'stdout.bin').open('rb') as handle:
        raw = handle.read(128 * 1024 + 1)
    plan = parse_completion(raw, saved.sources)
    response = strict_json(raw)
    request = strict_json(saved.request.body)
    context = strict_json(request['messages'][1]['content'])
    approval = strict_json((directory / 'approval.json').read_bytes())
    outcome = strict_json((directory / 'outcome.json').read_bytes())
    quote = offers((directory / 'quote.stdout').read_bytes(), 'USDC')
    require(outcome['claimed_transaction_hash'] == TRANSACTION)
    require(approval['token'] == 'USDC' and Decimal(approval['max_amount']) == Decimal('0.01'))
    require(any(Decimal(q['price']) == Decimal('0.01') for q in quote))
    require(context['goal'] == METADATA['goal'] and sorted(saved.sources) == METADATA['sources'])
    require(request['model'] == response['model'] == METADATA['model'])
    require(request['max_tokens'] == METADATA['max_output_tokens'])
    require(all(response['usage'][k] == METADATA[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')))
    data = {**METADATA, 'plan': asdict(plan)}
    # Round-trip tuples before applying the browser's schema validation.
    data = json.loads(json.dumps(data))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
    body = json.dumps(data, indent=2) + '\n'
    validate_recording(body)
    return body, hashlib.sha256(canonical).hexdigest()


if __name__ == '__main__':
    body, digest = export(Path(sys.argv[1]))
    # stdout contains only the allowlisted public fixture.
    sys.stdout.write(body)
    print('Public artifact SHA-256: ' + digest, file=sys.stderr)
