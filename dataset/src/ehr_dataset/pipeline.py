"""Article runner: source packet -> extraction -> EHR record -> ICD-10-CM coding -> FHIR R4.

A run directory holds one batch of articles:

    RUN/manifest.json                    settings (context, extraction, fhir) and the article list
    RUN/inputs/<article>/source.jsonl    source packet written by `prepare`
    RUN/articles/<article>/              extraction/, ehr/, fhir/ and receipt.json

Each endpoint (one served model replica) works on `per_endpoint` articles at a time (default one);
an article sends up to `extraction.concurrency_per_endpoint` requests at once. Several endpoints share
the article list.
"""
from __future__ import annotations

import asyncio
from importlib.resources import files
import json
from pathlib import Path
import time

from .run_files import infrastructure_failures, ledger_metrics, read, rows, sha, write, write_rows

MANIFEST_FORMAT = 'synthetic-ehr.run/1'


def catalog_path():
    return Path(str(files('ehr_dataset').joinpath('terminology/icd10cm-2027.json.gz')))


def prepare(run, config, sources, *, split='train', validator_jar=None):
    """Gate each source packet and write the run manifest; sources maps article ID -> packet."""
    from .pilot_extract import PilotConfig, source_gate
    run = Path(run)
    if (run / 'manifest.json').exists():
        raise ValueError(f'{run} already holds a run; choose a new directory')
    extraction = PilotConfig.model_validate(config['extraction'])
    articles = []
    for aid, source in sorted(sources.items()):
        errors = source_gate(source, extraction)
        if errors:
            raise ValueError(f'Source gate failed for {aid}: {errors}')
        write_rows(run / 'inputs' / aid / 'source.jsonl', [source])
        articles.append({'article_id': aid, 'split': split, 'source_characters': len(source['text']),
                         'source_text_sha256': source['text_sha256']})
    catalog = catalog_path()
    manifest = {'format': MANIFEST_FORMAT, 'created_unix': time.time(), 'context': config['context'],
                'article_timeout_seconds': config.get('article_timeout_seconds'),
                'extraction': config['extraction'],
                'fhir': {**config['fhir'], 'catalog_sha256': sha(catalog),
                         'validator_jar': str(validator_jar) if validator_jar else None},
                'articles': articles}
    write(run / 'manifest.json', manifest)
    return manifest


def article_dir(run, aid):
    return Path(run) / 'articles' / aid


def finished(run, aid):
    path = article_dir(run, aid) / 'receipt.json'
    if not path.exists():
        return False
    receipt = read(path)
    return receipt.get('status') == 'done' and (receipt.get('fhir', {}).get('complete') or not receipt.get('has_prediction'))


def coding_ledgers(out):
    return sorted((Path(out) / 'fhir/packet/coding-calls').glob('**/attempts.jsonl'))


async def fhir_stage(run, out, endpoint, manifest):
    """ICD-10-CM selection and FHIR export; failures stay auditable without discarding extracted facts."""
    from .fhir_campaign import run_article_stage
    settings = manifest['fhir']
    output = out / 'fhir'
    start = time.monotonic()
    result = {'status': 'interrupted', 'complete': False, 'release_ready': False,
              'clinical_accuracy_verified': False, 'exports': {}, 'coding': {}}
    try:
        catalog = catalog_path()
        if sha(catalog) != settings['catalog_sha256']:
            raise ValueError('ICD-10-CM catalog checksum differs from the run manifest')
        result = await run_article_stage(out / 'ehr/data/unified.jsonl', run, output, endpoint, run / 'manifest.json',
                                         catalog, **settings['coding'], validator_jar=settings.get('validator_jar'))
    except Exception as exc:
        result.update(status='error', error_type=type(exc).__name__, error=str(exc)[:2000])
    finally:
        ledgers = coding_ledgers(out)
        result.update(elapsed_seconds=time.monotonic() - start, usage=ledger_metrics(ledgers),
                      call_ledgers=[str(p.relative_to(out)) for p in ledgers])
        write(output / 'receipt.json', result)
    return result


async def run_article(run, aid, endpoint):
    from .ehr_pipeline import run_ehr_stages
    from .pilot_extract import PilotRunner

    class ArticleRunner(PilotRunner):
        async def visual(self, *args, **kwargs):
            async with self.vision_slots:
                return await super().visual(*args, **kwargs)

    run = Path(run)
    manifest = read(run / 'manifest.json')
    cfg, context = manifest['extraction'], manifest['context']
    item = next(a for a in manifest['articles'] if a['article_id'] == aid)
    source = run / 'inputs' / aid / 'source.jsonl'
    out = article_dir(run, aid)
    if out.exists():  # Keep an earlier failed attempt for audit and start clean.
        out.rename(out.with_name(f'{aid}.attempt-{len(list(out.parent.glob(aid + ".attempt-*"))):02d}'))
    out.mkdir(parents=True)
    start = time.monotonic()
    receipt = {'article_id': aid, 'split': item['split'], 'started_unix': time.time(), 'status': 'error'}
    runner = None
    try:
        runner = ArticleRunner(cfg, out / 'extraction', [endpoint], context, 'targeted')
        runner.vision_slots = asyncio.Semaphore(min(2, cfg.get('concurrency_per_endpoint', 64)))
        report = await runner.run(source, image_manifest=None)
        if infrastructure_failures(out):
            raise RuntimeError('Extraction backend failed; article must be retried')
        receipt.update(extraction_seconds=time.monotonic() - start, task_statuses=report['task_statuses'],
                       patients_extracted=report['patients_extracted'])
        if report['selected_articles'] != 1 or report['eligible_articles'] != 1:
            raise ValueError('Article was not selected/eligible; refusing silent partial coverage')
        if any(a.get('omitted_patient_ids_due_to_cap') for a in report['articles']):
            raise ValueError('Discovered patient cap exceeded; refusing a truncated roster')
        side_start = time.monotonic()
        ehr = await run_ehr_stages({'figure_ehr_label': False, 'figure_privacy_flags': False,
                'measurement_series_extraction': True,
                'extraction_config': {**cfg, 'concurrency_per_endpoint': min(2, cfg.get('concurrency_per_endpoint', 64))},
                'default_split': item['split']}, source, out / 'extraction', out / 'ehr', [endpoint], context,
                image_manifest=None)
        receipt.update(ehr_seconds=time.monotonic() - side_start, ehr_errors=ehr['articles'][0]['errors'])
        predictions = rows(out / 'ehr/data/unified.jsonl')
        if set(predictions) - {aid}:
            raise ValueError('Unexpected prediction identity')
        # An invalid roster legitimately produces no record (and no FHIR); a backend failure does not.
        receipt.update(status='done', has_prediction=aid in predictions,
                       prediction_sha256=sha(out / 'ehr/data/unified.jsonl'),
                       all_extraction_tasks_valid=report['valid_tasks'] == report['task_count'])
        receipt['fhir'] = (await fhir_stage(run, out, endpoint, manifest) if aid in predictions else
                           {'status': 'skipped_no_prediction', 'complete': False, 'exports': {}, 'coding': {}})
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc)[:2000])
    finally:
        if runner:
            await runner.close()
        receipt.update(wall_seconds=time.monotonic() - start, ended_unix=time.time(),
                       usage=ledger_metrics([out / 'extraction/attempts.jsonl', out / 'ehr/calls/attempts.jsonl',
                                             *coding_ledgers(out)]))
        failures = infrastructure_failures(out)
        if failures:
            receipt.update(status='error', error_type='InfrastructureError', retryable=True,
                           infrastructure_failures=failures,
                           error='Backend request failed; retained outputs are incomplete, retry this article')
        write(out / 'receipt.json', receipt)
    return receipt


async def run_all(run, endpoints, *, article_ids=None, per_endpoint=1):
    """Process every unfinished article; each endpoint works on up to `per_endpoint` articles at once."""
    run = Path(run)
    manifest = read(run / 'manifest.json')
    timeout = manifest.get('article_timeout_seconds')
    pending = asyncio.Queue()
    for item in manifest['articles']:
        if (article_ids is None or item['article_id'] in article_ids) and not finished(run, item['article_id']):
            pending.put_nowait(item['article_id'])
    receipts = []

    async def worker(endpoint):
        while not pending.empty():
            aid = pending.get_nowait()
            try:
                receipt = await asyncio.wait_for(run_article(run, aid, endpoint), timeout)
            except TimeoutError:
                receipt = read(article_dir(run, aid) / 'receipt.json')
                receipt.update(status='error', error_type='TimeoutError', error='Per-article time budget exceeded')
                write(article_dir(run, aid) / 'receipt.json', receipt)
            receipts.append(receipt)
            print(json.dumps({k: receipt.get(k) for k in ('article_id', 'status', 'wall_seconds', 'error')}), flush=True)
            if receipt.get('error_type') == 'InfrastructureError':
                raise RuntimeError(f'Backend at {endpoint} failed; remaining articles stay pending for a rerun')

    await asyncio.gather(*(worker(endpoint) for endpoint in endpoints for _ in range(per_endpoint)))
    return receipts
