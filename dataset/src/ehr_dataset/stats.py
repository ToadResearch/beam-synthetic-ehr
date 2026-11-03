"""Run record and dataset size.

The run record sums every article receipt (model calls and prompt, completion and reasoning
tokens, including repairs) and reads RUN/workers/*.json, which runners write with the GPU type,
GPU count and server timing, to count GPU-hours. Dataset size counts rows, megabytes and
tokens of the exported payloads (FHIR bundles, extraction records) with the model's tokenizer.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import statistics

from .run_files import read

USAGE = ('model_calls', 'prompt_tokens', 'completion_tokens', 'reasoning_tokens')
PAYLOAD = {'uncoded': 'bundle', 'coded': 'bundle', 'extraction': 'record'}


def run_record(run):
    run = Path(run)
    receipts = [read(p) for p in sorted(run.glob('articles/*/receipt.json'))]
    done = [r for r in receipts if r.get('status') == 'done']
    usage, unknown = Counter(), Counter()
    for receipt in receipts:
        for key in USAGE:
            value = (receipt.get('usage') or {}).get(key)
            if value is None:
                unknown[key] += 1
            else:
                usage[key] += value
    seconds = [r['wall_seconds'] for r in done if r.get('wall_seconds') is not None]
    starts = [r['started_unix'] for r in receipts if r.get('started_unix')]
    ends = [r['ended_unix'] for r in receipts if r.get('ended_unix')]
    # Hardware and timing only; which articles each server handled stays in the run folder.
    workers = [{k: v for k, v in read(p).items() if k != 'articles'} for p in sorted(run.glob('workers/*.json'))]
    gpu_hours = sum((w['ended_unix'] - w['started_unix']) / 3600 * w['gpu_count']
                    for w in workers if w.get('ended_unix') and w.get('started_unix'))
    # Wall clock counts the time at least one GPU server was up, so a later rerun adds its own
    # time rather than the gap before it.
    busy, span = 0.0, None
    for start, end in sorted((w['started_unix'], w['ended_unix']) for w in workers if w.get('started_unix') and w.get('ended_unix')):
        if span and start <= span[1]:
            span[1] = max(span[1], end)
        else:
            busy += span[1] - span[0] if span else 0
            span = [start, end]
    busy += span[1] - span[0] if span else 0
    return {'articles': len(receipts), 'articles_done': len(done),
            'patients': sum(r.get('patients_extracted') or 0 for r in done),
            'article_minutes': {'mean': round(statistics.mean(seconds) / 60, 1), 'max': round(max(seconds) / 60, 1)}
                               if seconds else None,
            'articles_wall_clock_hours': round((max(ends) - min(starts)) / 3600, 2) if starts and ends else None,
            'usage': dict(usage), 'usage_unknown': dict(unknown),
            'run_wall_clock_hours': round(busy / 3600, 2) if workers and all(w.get('ended_unix') for w in workers) else None,
            'workers': workers, 'gpu_hours': round(gpu_hours, 1) if workers else None}


def dataset_size(out, tokenizer=None, label=None):
    """Rows, megabytes and (with a tokenizer.json) payload tokens for every data/*.jsonl file.
    The tokenizer is recorded by `label` (the model name), never by its local path."""
    encoder = None
    if tokenizer:
        from tokenizers import Tokenizer
        encoder = Tokenizer.from_file(str(Path(tokenizer) / 'tokenizer.json'))
    files = {}
    for path in sorted((Path(out) / 'data').glob('*.jsonl')):
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        entry = {'rows': len(rows), 'megabytes': round(path.stat().st_size / 1e6, 2)}
        field = PAYLOAD.get(path.stem)
        if encoder and field:
            texts = [row[field] for row in rows if isinstance(row.get(field), str)]
            entry['tokens'] = sum(len(e.ids) for e in encoder.encode_batch(texts, add_special_tokens=False))
        files[path.stem] = entry
    total = {key: round(sum(f.get(key, 0) for f in files.values()), 2) for key in ('rows', 'megabytes', 'tokens')}
    return {'files': files, 'total': total, 'tokenizer': (label or Path(tokenizer).name) if tokenizer else None}


def write_stats(run, out, tokenizer=None):
    """Store the run record and dataset size in OUT/manifest.json and refresh the dataset card."""
    from .export import render_card, run_settings
    out = Path(out)
    summary = read(out / 'manifest.json')
    for key, value in run_settings(read(Path(run) / 'manifest.json')).items():
        summary.setdefault(key, value)
    summary['run_record'] = run_record(run)
    summary['size'] = dataset_size(out, tokenizer, label=f"{summary['model']} tokenizer" if summary.get('model') else None)
    (out / 'manifest.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    render_card(out)
    return {'run_record': summary['run_record'], 'size': summary['size']}
