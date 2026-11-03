"""File helpers and model-call accounting shared by the pipeline stages."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    found = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        aid = row['article_id']
        if aid in found or not re.fullmatch(r'PMC\d+\.\d+', aid):
            raise ValueError(f'Duplicate/invalid article ID: {aid}')
        found[aid] = row
    return found


def write_rows(path, values):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def ledger_metrics(paths):
    metrics = {'model_calls': 0, 'failed_attempts': 0}
    by_task = {}
    reasoning_statuses = Counter()
    finish_reasons = Counter()
    for k in ('prompt_tokens', 'completion_tokens', 'reasoning_tokens'):
        metrics[k] = 0
        metrics['unknown_' + k] = 0
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            entry = json.loads(line)
            response = entry.get('response')
            if entry.get('errors'):
                metrics['failed_attempts'] += 1
            if response is None:
                continue
            metrics['model_calls'] += 1
            task = by_task.setdefault(entry.get('task', 'unknown_legacy'), {'model_calls':0, 'length_limited_calls':0,
                'out_of_batch_candidates':0, 'prompt_tokens':0, 'completion_tokens':0, 'reasoning_tokens':0})
            task['model_calls'] += 1
            task['length_limited_calls'] += entry.get('metrics', {}).get('finish_reason') == 'length'
            task['out_of_batch_candidates'] += len(entry.get('scope_routing', []))
            finish_reasons[entry.get('metrics', {}).get('finish_reason') or 'unknown'] += 1
            reasoning_statuses[response.get('reasoning_status', 'unknown_legacy')] += 1
            if response.get('error') and not entry.get('errors'):
                metrics['failed_attempts'] += 1
            for k in ('prompt_tokens', 'completion_tokens', 'reasoning_tokens'):
                value = entry.get('metrics', {}).get(k)
                task[k] = task[k] + value if task[k] is not None and value is not None else None
                if value is None:
                    metrics['unknown_' + k] += 1
                else:
                    metrics[k] += value
    for k in ('prompt_tokens', 'completion_tokens', 'reasoning_tokens'):
        metrics['reported_' + k] = metrics[k]
        if metrics['unknown_' + k]:
            metrics[k] = None
    metrics['reasoning_statuses'] = dict(reasoning_statuses)
    metrics['finish_reasons'] = dict(finish_reasons)
    metrics['task_usage'] = by_task
    return metrics


def infrastructure_failures(attempt):
    """Terminal task transport failures; recovered retries are not failures.

    Inspect task results rather than every ledger entry, so a successful retry
    does not invalidate an otherwise completed article. Keep all raw outputs.
    """
    failures = []
    transient = {'ReadTimeout', 'ConnectTimeout', 'ConnectError', 'ReadError',
                 'RemoteProtocolError', 'TimeoutError', 'total_request_deadline'}
    for folder in ('extraction', 'ehr'):
        for path in (attempt / folder).rglob('tasks/*.json'):
            task = read(path)
            if task.get('status') == 'valid':
                continue
            for entry in task.get('attempts', [])[-1:]:
                response = entry.get('response') or {}
                status = response.get('http_status')
                error = response.get('error')
                if (entry.get('metrics', {}).get('transport_error') or
                        status in {408, 429} or isinstance(status, int) and status >= 500 or
                        error in transient or error in {'http_408', 'http_429'} or
                        isinstance(error, str) and error.startswith('http_5')):
                    failures.append({'task': task.get('task'), 'file': str(path.relative_to(attempt)),
                                     'error': error or 'transport_error'})
    return failures
