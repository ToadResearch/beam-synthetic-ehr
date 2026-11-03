"""Collect a finished run into a Hugging Face dataset folder.

    OUT/README.md               dataset card (configs: uncoded, coded, extraction)
    OUT/data/uncoded.jsonl      one validated FHIR R4 Bundle per patient, no model-selected codes
    OUT/data/coded.jsonl        the same bundles with unreviewed model-selected ICD-10-CM codes
    OUT/data/extraction.jsonl   one cited extraction record per article, plus its figures with image links
    OUT/manifest.json           counts, checksums and every patient that was not exported, with its status

Bundles and records are stored as JSON strings so every row has the same columns. Figure images are
not copied: each figure keeps its PubMed Central open-access image links, which anyone can download.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from .pipeline import article_dir
from .run_files import read, rows, sha, write

EXPORTS = {'uncoded': 'uncoded', 'coded': 'experimental-coded'}


def source_packet(run, aid):
    return next(iter(rows(Path(run) / 'inputs' / aid / 'source.jsonl').values()))


CC_URL = re.compile(r'https?://creativecommons\.org/(?:licenses|publicdomain)/[a-z-]+/\d\.\d/?')


def license_terms(license):
    """License name and license URL from the article's own license statements."""
    statements = license.get('statements', [])
    urls = [u for s in statements for u in (s.get('url'), *(s.get('urls') or [])) if u and 'creativecommons.org' in u]
    urls += [m.group(0) for s in statements for m in CC_URL.finditer(s.get('text') or '')]
    url = urls[0] if urls else None
    version = license.get('version') or (re.search(r'/(\d\.\d)/?$', url).group(1) if url else None)
    return ' '.join(x for x in (license.get('code'), version) if x), url


def article_metadata(source):
    name, url = license_terms(source.get('license', {}))
    return {'article_id': source['article_id'], 'title': source.get('title'), 'doi': source.get('doi'),
            'source_url': source.get('source_url'), 'license': name, 'license_url': url}


def figure_links(source):
    """Label, caption and open-access image links for every figure in the article."""
    return [{'figure_id': f.get('figure_id'), 'label': f.get('label'), 'caption': f.get('caption'),
             'image_urls': list(f.get('image_urls') or [])} for f in source.get('figures', [])]


def run_settings(manifest):
    extraction = manifest['extraction']
    return {'model': extraction.get('model_id'), 'context': manifest.get('context'),
            'sampling': {k: extraction.get(k) for k in ('temperature', 'top_p', 'reasoning_strength')}}


def export(run, out, *, generated_on=None):
    run, out = Path(run), Path(out)
    manifest = read(run / 'manifest.json')
    (out / 'data').mkdir(parents=True, exist_ok=True)
    index, counts = [], Counter()
    streams = {name: (out / 'data' / f'{name}.jsonl').open('w', encoding='utf-8') for name in (*EXPORTS, 'extraction')}
    try:
        for item in manifest['articles']:
            aid = item['article_id']
            folder = article_dir(run, aid)
            receipt = read(folder / 'receipt.json') if (folder / 'receipt.json').exists() else {}
            entry = {'article_id': aid, 'status': receipt.get('status', 'not_run'),
                     'fhir_status': receipt.get('fhir', {}).get('status'), 'patients': {}}
            index.append(entry)
            if receipt.get('status') != 'done' or not receipt.get('has_prediction'):
                continue
            source = source_packet(run, aid)
            meta = article_metadata(source)
            record = next(iter(rows(folder / 'ehr/data/unified.jsonl').values()))
            figures = figure_links(source)
            streams['extraction'].write(json.dumps({**meta, 'split': item['split'], 'figures': figures,
                                                    'record': json.dumps(record, ensure_ascii=False)}, ensure_ascii=False) + '\n')
            counts['articles_exported'] += 1
            counts['figures'] += len(figures)
            for name, directory in EXPORTS.items():
                report_path = folder / 'fhir' / directory / 'report.json'
                if not report_path.exists():
                    continue
                for patient in read(report_path)['patients']:
                    entry['patients'].setdefault(patient['patient_id'], {})[name] = patient['status']
                    if patient['status'] != 'passed' or not patient.get('bundle'):
                        continue
                    bundle_path = report_path.parent / patient['bundle']
                    if sha(bundle_path) != patient['sha256']:
                        raise ValueError(f'FHIR output changed after validation: {bundle_path}')
                    bundle = read(bundle_path)
                    streams[name].write(json.dumps({**meta, 'patient_id': patient['patient_id'], 'bundle_id': bundle.get('id'),
                                                    'bundle': json.dumps(bundle, ensure_ascii=False)}, ensure_ascii=False) + '\n')
                    counts[f'{name}_bundles'] += 1
    finally:
        for stream in streams.values():
            stream.close()
    summary = {'format': 'synthetic-ehr.dataset/1', **run_settings(manifest), 'generated_on': generated_on,
               'articles_planned': len(manifest['articles']), **counts,
               'files': {f'data/{name}.jsonl': sha(out / 'data' / f'{name}.jsonl') for name in (*EXPORTS, 'extraction')},
               'articles': index,
               'policy': 'Only bundles that passed validation are exported; every other patient is listed here with its status.'}
    write(out / 'manifest.json', summary)
    (out / 'README.md').write_text(card(summary), encoding='utf-8')
    return summary


def render_card(out, *, run=None, generated_on=None):
    """Rewrite README.md for an export folder, optionally adding run settings and where it was generated."""
    out = Path(out)
    summary = read(out / 'manifest.json')
    if run:
        summary.update(run_settings(read(Path(run) / 'manifest.json')))
    if generated_on:
        summary['generated_on'] = generated_on
    write(out / 'manifest.json', summary)
    (out / 'README.md').write_text(card(summary), encoding='utf-8')
    return summary


def generation_table(summary):
    sampling = summary.get('sampling') or {}
    record = summary.get('run_record') or {}
    usage = record.get('usage') or {}
    gpus = Counter(f"{w.get('gpu_count')}× {w.get('gpu_name')}" for w in record.get('workers', []))
    rows = [('Model', summary.get('model')),
            ('Sampling', ', '.join(f'{name} {sampling[key]}' for key, name in
                                   (('temperature', 'temperature'), ('top_p', 'top-p'), ('reasoning_strength', 'reasoning effort'))
                                   if sampling.get(key) is not None)),
            ('Context', f"{summary['context']:,} tokens" if summary.get('context') else None),
            ('Generated on', summary.get('generated_on')),
            ('Servers', ', '.join(f'{n} × {desc}' for desc, n in gpus.items()) if gpus else None),
            ('GPU-hours', record.get('gpu_hours')),
            ('Wall clock', f"{record['run_wall_clock_hours']} h on the GPUs" if record.get('run_wall_clock_hours') else
                           f"{record['articles_wall_clock_hours']} h" if record.get('articles_wall_clock_hours') else None),
            ('Model calls', f"{usage['model_calls']:,}" if usage.get('model_calls') else None),
            ('Model tokens', f"{usage.get('prompt_tokens', 0):,} input, {usage.get('completion_tokens', 0):,} output "
                             f"({usage.get('reasoning_tokens', 0):,} reasoning), repairs included" if usage else None)]
    return '\n'.join(['| Setting | Value |', '|---|---|'] + [f'| {k} | {v} |' for k, v in rows if v])


def size_table(summary):
    size = summary.get('size')
    if not size:
        return ''
    tokens = bool(size.get('tokenizer'))
    head = '| Config | Rows | MB |' + (' Tokens |' if tokens else '') + '\n|---|---:|---:|' + ('---:|' if tokens else '')
    lines = [f"| `{name}` | {f['rows']:,} | {f['megabytes']} |" + (f" {f.get('tokens', 0):,} |" if tokens else '')
             for name, f in size['files'].items()]
    total = size['total']
    lines.append(f"| total | {int(total['rows']):,} | {total['megabytes']} |" + (f" {int(total['tokens']):,} |" if tokens else ''))
    note = (f"\n\nTokens: the FHIR bundle or extraction record of each row, counted with the {summary.get('model')} "
            "tokenizer. Each bundle embeds its source article and extraction packet as base64 attachments, "
            "which make up much of its size." if tokens else '')
    return '\n\n## Size\n\n' + head + '\n' + '\n'.join(lines) + note


def card(summary):
    return f'''---
license: cc-by-4.0
language:
- en
pretty_name: Synthetic EHR from case reports
tags:
- fhir
- hl7-fhir-r4
- electronic-health-records
- icd-10-cm
- clinical-nlp
- case-reports
- pubmed-central
configs:
- config_name: uncoded
  data_files: data/uncoded.jsonl
  default: true
- config_name: coded
  data_files: data/coded.jsonl
- config_name: extraction
  data_files: data/extraction.jsonl
---

# Synthetic EHR from case reports

Patients described in open-access (CC BY) PubMed Central case reports, as HL7 FHIR R4 Bundles.
Every clinical fact cites the sentence or table cell it came from. {summary['model']} did the reading
(patients, clinical facts, measurement tables, timeline and ICD-10-CM selection); a deterministic
compiler built the FHIR, which was checked with the official HL7 validator.

| Config | Rows | Content |
|---|---:|---|
| `uncoded` | {summary.get('uncoded_bundles', 0)} | One Bundle per patient (JSON string in `bundle`) |
| `coded` | {summary.get('coded_bundles', 0)} | The same Bundles with unreviewed model-selected ICD-10-CM codes |
| `extraction` | {summary.get('articles_exported', 0)} | One cited extraction record per article (JSON string in `record`) and its {summary.get('figures', 0)} figures |

Each row also has `article_id`, `title`, `doi`, `source_url`, `license` and `license_url`.
Extraction was text-only:
figure images are not included, but each `extraction` row lists its figures (`figure_id`, `label`,
`caption`, `image_urls`), and the links are public PubMed Central open-access files.

## How it was generated

{generation_table(summary)}{size_table(summary)}

## Limitations

- Model output, not clinically reviewed. Codes are research normalization, not billing.
- Times are relative to the case as reported; no dates, encounters or clinicians are invented.
- Case reports over-represent rare and unusual presentations.
- Identities are synthetic, but the source articles are public.

## License and attribution

Every source article is open access under a Creative Commons Attribution license (CC BY); each row
names its article's license, license link and source link. The records are adaptations:
facts were extracted from the article text by the model and compiled into FHIR, so they are not the
articles themselves. Released under CC BY 4.0; when you use a record, credit the original case report
as given in its row. ICD-10-CM content comes from the CDC/NCHS FY2027 release.
'''
