"""Campaign-owned validator staging and bounded repair of quarantined bundles."""
import json
from pathlib import Path
import urllib.request
import httpx
from .fhir_pipeline import sha
from .fhir_validation import official_validate
from .fhir_repair import repair, SYSTEM

JAR_SHA = '57aa43fb40cec5de41def81c927725fd85908eeb71509b7f9313e04d9b8ec79b'


def stage(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix('.download')
        urllib.request.urlretrieve('https://github.com/hapifhir/org.hl7.fhir.core/releases/download/7.0.3/validator_cli.jar', temporary)
        if sha(temporary) != JAR_SHA:
            raise ValueError('Official validator checksum mismatch')
        temporary.replace(path)
    if sha(path) != JAR_SHA:
        raise ValueError('Official validator checksum mismatch')
    # Resolve core/extension packages on CPU before GPU workers are submitted.
    probe = path.parent / 'probe.json'
    probe.write_text(json.dumps({'resourceType': 'Bundle', 'type': 'collection'}))
    outcome = path.parent / 'probe-outcome.json'
    outcome.unlink(missing_ok=True)
    result = official_validate(probe, path, output=outcome, timeout=900)
    if not result.get('outcome'):
        raise ValueError('Validator package warmup failed')


def repair_exports(packet, export_dir, report, endpoint, model, jar):
    evidence = {'articles': [json.loads(line) for line in (packet / 'articles.jsonl').read_text().splitlines()],
                'sources': [json.loads(p.read_text()) for p in (packet / 'sources').glob('*.json')]}
    results = []
    def propose(request):
        with httpx.Client(timeout=180) as client:
            response = client.post(endpoint.rstrip('/') + '/chat/completions', json={
                'model': model, 'messages': [{'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': json.dumps(request)}], 'max_tokens': 16384})
            response.raise_for_status()
            return response.json()
    for patient in report['patients']:
        if patient['status'] != 'quarantined':
            continue
        source = export_dir / patient['bundle']
        target = export_dir / 'repair' / source.stem
        result = repair(json.loads(source.read_text()), evidence, target, jar, propose, attempts=2)
        usages = [json.loads(p.read_text()).get('usage') for p in target.glob('round-*/response.json')]
        result['usage'] = usages
        results.append({'patient_id': patient['patient_id'], 'directory': str(target), **result})
    (export_dir / 'repair-report.json').write_text(json.dumps(results, indent=2))
    return results
