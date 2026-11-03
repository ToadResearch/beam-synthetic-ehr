"""ehr-dataset: source-grounded FHIR R4 patient records from open-access case reports.

    ehr-dataset weights --config configs/beam.yaml --dest weights
    ehr-dataset serve   --config configs/beam.yaml --weights weights --gpus 0,1,2,3 --port 8000 [--apptainer beam.sif]
    ehr-dataset prepare --config configs/beam.yaml --articles configs/articles/diverse30.yaml --run runs/diverse30
    ehr-dataset run     --run runs/diverse30 --endpoint http://127.0.0.1:8000/v1 [--endpoint ...]
    ehr-dataset status  --run runs/diverse30
    ehr-dataset export  --run runs/diverse30 --out hf-dataset [--generated-on "Modal, 8x NVIDIA B200"]
    ehr-dataset card    --out hf-dataset [--run runs/diverse30] [--generated-on ...]
    ehr-dataset stats   --run runs/diverse30 --out hf-dataset --tokenizer weights/model
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import sys

import yaml


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def cmd_weights(args):
    from .serving import download_weights
    download_weights(load_yaml(args.config), args.dest, tokenizer_only=args.tokenizer_only)


def cmd_serve(args):
    from .serving import command, environment
    config = load_yaml(args.config)
    cache = Path(args.cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    argv = command(config, weights=Path(args.weights).resolve(), port=args.port, host=args.host)
    env = environment(config, devices=args.gpus, cache=cache)
    if args.apptainer:
        weights = str(Path(args.weights).resolve())
        prefix = ['apptainer', 'exec', '--nv', '--cleanenv', '--bind', f'{weights}:{weights}:ro',
                  '--bind', f'{cache}:{cache}']
        for target in {str(Path(weights, name).resolve()) for name in ('model', 'draft') if Path(weights, name).exists()}:
            prefix += ['--bind', f'{target}:{target}:ro']  # symlinked weight folders resolve outside WEIGHTS
        for key, value in env.items():
            prefix += ['--env', f'{key}={value}']
        argv, env = prefix + [args.apptainer] + argv, os.environ.copy()
    else:
        env = {**os.environ, **env}
    print(json.dumps(argv), file=sys.stderr, flush=True)
    os.execvpe(argv[0], argv, env)


def cmd_prepare(args):
    from .acquire import acquire
    from .pipeline import prepare
    config, articles = load_yaml(args.config), load_yaml(args.articles)
    ids = list(dict.fromkeys(articles['articles']))
    sources, skipped = asyncio.run(acquire(ids, args.sources or Path(args.run).with_name(Path(args.run).name + '-sources'),
                                           permissive_only=config.get('acquisition', {}).get('permissive_only', True)))
    for aid, reason in skipped.items():
        print(f'skipped {aid}: {reason.get("status")}', file=sys.stderr)
    jar = None
    if not args.no_official_validator:
        from .fhir_campaign_repair import stage
        jar = Path(args.validator or Path.home() / '.cache/ehr-dataset/validator_cli.jar').resolve()
        stage(jar)
    manifest = prepare(args.run, config, sources, split=articles.get('split', 'train'), validator_jar=jar)
    print(f'{len(manifest["articles"])} articles ready in {args.run} ({len(skipped)} skipped)')


def cmd_run(args):
    from .pipeline import run_all
    receipts = asyncio.run(run_all(args.run, args.endpoint, article_ids=set(args.article) if args.article else None,
                                   per_endpoint=args.per_endpoint))
    print(json.dumps(Counter(r['status'] for r in receipts)))


def cmd_status(args):
    from .pipeline import article_dir, finished
    from .run_files import read
    manifest = read(Path(args.run) / 'manifest.json')
    states = Counter()
    for item in manifest['articles']:
        aid = item['article_id']
        path = article_dir(args.run, aid) / 'receipt.json'
        state = 'finished' if finished(args.run, aid) else read(path).get('status', 'error') if path.exists() else 'pending'
        states[state] += 1
    print(json.dumps({'articles': len(manifest['articles']), **states}))


def cmd_export(args):
    from .export import export
    summary = export(args.run, args.out, generated_on=args.generated_on)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('articles', 'files', 'policy')}))


def cmd_stats(args):
    from .stats import write_stats
    print(json.dumps(write_stats(args.run, args.out, args.tokenizer), indent=2, default=str))


def cmd_card(args):
    from .export import render_card
    render_card(args.out, run=args.run, generated_on=args.generated_on)
    print(f'wrote {Path(args.out) / "README.md"}')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ehr-dataset', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('weights', help='download the pinned model weights')
    p.add_argument('--config', required=True); p.add_argument('--dest', required=True)
    p.add_argument('--tokenizer-only', action='store_true', help='only the tokenizer files (for stats)')
    p = sub.add_parser('serve', help='start one vLLM server for the configured model')
    p.add_argument('--config', required=True); p.add_argument('--weights', required=True)
    p.add_argument('--gpus', default='0,1,2,3'); p.add_argument('--port', type=int, default=8000)
    p.add_argument('--host', default='127.0.0.1'); p.add_argument('--cache', default='.cache/serving')
    p.add_argument('--apptainer', help='run vLLM inside this Apptainer image (SIF) instead of natively')
    p = sub.add_parser('prepare', help='fetch articles and write a run directory')
    p.add_argument('--config', required=True); p.add_argument('--articles', required=True); p.add_argument('--run', required=True)
    p.add_argument('--sources', help='source packet cache (default: RUN-sources)')
    p.add_argument('--validator', help='HL7 validator jar path (downloaded if missing)')
    p.add_argument('--no-official-validator', action='store_true', help='skip the official HL7 validator')
    p = sub.add_parser('run', help='process the run against one or more served endpoints')
    p.add_argument('--run', required=True); p.add_argument('--endpoint', action='append', required=True)
    p.add_argument('--article', action='append', help='only these article IDs')
    p.add_argument('--per-endpoint', type=int, default=1, help='articles each server works on at once')
    p = sub.add_parser('status', help='count finished, failed and pending articles')
    p.add_argument('--run', required=True)
    p = sub.add_parser('export', help='write a Hugging Face dataset folder')
    p.add_argument('--run', required=True); p.add_argument('--out', required=True)
    p.add_argument('--generated-on', help='hardware note for the dataset card, e.g. "Modal, 8x NVIDIA B200"')
    p = sub.add_parser('stats', help='add the run record and dataset size (tokens) to an export folder')
    p.add_argument('--run', required=True); p.add_argument('--out', required=True)
    p.add_argument('--tokenizer', help='folder with tokenizer.json (see weights --tokenizer-only)')
    p = sub.add_parser('card', help='rewrite the dataset card of an export folder')
    p.add_argument('--out', required=True); p.add_argument('--run', help='run folder to take model settings from')
    p.add_argument('--generated-on', help='hardware note for the dataset card')
    args = parser.parse_args(argv)
    {'weights': cmd_weights, 'serve': cmd_serve, 'prepare': cmd_prepare, 'run': cmd_run,
     'status': cmd_status, 'export': cmd_export, 'stats': cmd_stats, 'card': cmd_card}[args.command](args)


if __name__ == '__main__':
    main()
