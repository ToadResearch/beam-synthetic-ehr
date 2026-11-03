"""Run the dataset builder on Modal: Beam servers (tensor parallel 4), one per 4xB200 container.

    modal run --detach runners/modal_app.py --run diverse30 --stage-only   # weights + articles, CPU only
    modal run --detach runners/modal_app.py --run diverse30                # then extraction and export
    modal volume get ehr-dataset exports/diverse30 ./hf-dataset

A detached `modal run` still stops when the local client loses its connection. For long runs,
deploy once and spawn the chain, which then runs on Modal alone:

    modal deploy runners/modal_app.py
    python -c "import modal; modal.Function.from_name('ehr-dataset', 'build').spawn(
        open('configs/articles/diverse30.yaml').read(), 'diverse30', False, 2, 3)"
    modal app logs ehr-dataset

Weights, run folders and exports live on the `ehr-dataset` volume. Each step is skipped when its
output exists, and finished articles are committed every two minutes, so rerunning resumes.
"""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

import modal

DATASET = Path(__file__).resolve().parents[1]
CONFIG = '/opt/dataset/configs/beam.yaml'
IMAGE = 'vllm/vllm-openai@sha256:25635d363e0a86a099e16690f642e85301c4940ee11acf9335c4570657db9d9d'
GIB = 1024  # MiB

# vLLM runs on the image's own /usr/bin/python3; the builder gets a separate Python.
image = (modal.Image.from_registry(IMAGE, add_python='3.12')
         .entrypoint([])
         .apt_install('openjdk-17-jre-headless')
         .add_local_dir(DATASET, '/opt/dataset', copy=True,
                        ignore=['.venv', 'runs', 'weights', 'hf-dataset', '**/__pycache__'])
         .run_commands('python -m pip install --no-cache-dir "/opt/dataset[weights]"'))
volume = modal.Volume.from_name('ehr-dataset', create_if_missing=True)
app = modal.App('ehr-dataset', image=image)


def sh(*args):
    subprocess.run([str(a) for a in args], check=True)


@app.function(cpu=8, memory=32 * GIB, timeout=3 * 3600, volumes={'/vol': volume})
def weights():
    if not Path('/vol/weights/model/config.json').exists():
        os.environ.update(HF_HOME='/tmp/hf', HF_XET_CHUNK_CACHE_SIZE_BYTES='0')
        sh('ehr-dataset', 'weights', '--config', CONFIG, '--dest', '/vol/weights')
        volume.commit()


@app.function(cpu=4, memory=16 * GIB, timeout=3600, volumes={'/vol': volume})
def prepare(articles: str, run: str):
    if Path(f'/vol/runs/{run}/manifest.json').exists():
        return
    path = Path('/tmp/articles.yaml')
    path.write_text(articles)
    sh('ehr-dataset', 'prepare', '--config', CONFIG, '--articles', path, '--run', f'/vol/runs/{run}',
       '--sources', '/tmp/sources', '--validator', '/vol/tools/validator_cli.jar')
    volume.commit()


# B300 is the fallback when no B200s are free; the image's kernels cover the Blackwell family.
@app.function(gpu=['B200:4', 'B300:4'], cpu=16.0, memory=(256 * GIB, 448 * GIB), timeout=12 * 3600,
              volumes={'/vol': volume})
def process(run: str, articles: list[str], per_server: int):
    """One Beam server (tensor parallel 4) works through its share of the articles."""
    gpus = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                          capture_output=True, text=True).stdout.split('\n')
    worker = {'platform': 'Modal', 'gpu_name': next((g.strip() for g in gpus if g.strip()), None),
              'gpu_count': sum(1 for g in gpus if g.strip()), 'started_unix': time.time(), 'articles': articles}
    record = Path(f'/vol/runs/{run}/workers/{os.environ.get("MODAL_TASK_ID", int(worker["started_unix"]))}.json')

    def save_worker():
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(worker, indent=2))
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
    server = subprocess.Popen(['ehr-dataset', 'serve', '--config', CONFIG, '--weights', '/vol/weights',
                               '--gpus', '0,1,2,3', '--port', '8000', '--cache', '/tmp/serving'], env=env)
    deadline = time.time() + 5400  # loading ~290 GB and compiling takes 20-30 minutes
    while True:
        try:
            urllib.request.urlopen('http://127.0.0.1:8000/v1/models', timeout=5)
            break
        except OSError:
            if time.time() > deadline or server.poll() is not None:
                raise RuntimeError('vLLM did not start')
            time.sleep(10)
    worker['server_ready_unix'] = time.time()
    save_worker()
    stop = threading.Event()

    def commit_progress():
        while not stop.wait(120):
            volume.commit()
    threading.Thread(target=commit_progress, daemon=True).start()
    try:
        sh('ehr-dataset', 'run', '--run', f'/vol/runs/{run}', '--endpoint', 'http://127.0.0.1:8000/v1',
           '--per-endpoint', str(per_server), *(arg for aid in articles for arg in ('--article', aid)))
    finally:
        stop.set()
        worker['ended_unix'] = time.time()
        save_worker()
        volume.commit()
        server.terminate()


@app.function(cpu=4, memory=16 * GIB, timeout=3600, volumes={'/vol': volume})
def export(run: str):
    sh('ehr-dataset', 'export', '--run', f'/vol/runs/{run}', '--out', f'/vol/exports/{run}')
    volume.commit()


@app.function(cpu=1.0, memory=2 * GIB, timeout=14 * 3600, volumes={'/vol': volume})
def build(articles: str, run: str, stage_only: bool, servers: int, per_server: int):
    """Runs the whole chain on Modal, so a detached run continues without the local client."""
    weights.remote()
    prepare.remote(articles, run)
    if stage_only:
        return f'staged runs/{run}'
    volume.reload()
    manifest = json.loads(Path(f'/vol/runs/{run}/manifest.json').read_text())
    shares, loads = [[] for _ in range(servers)], [0] * servers
    for item in sorted(manifest['articles'], key=lambda a: -a['source_characters']):
        share = loads.index(min(loads))
        shares[share].append(item['article_id'])
        loads[share] += item['source_characters']
    list(process.starmap([(run, share, per_server) for share in shares]))  # one container per server, in parallel
    export.remote(run)
    return f'modal volume get ehr-dataset exports/{run} ./hf-dataset'


@app.local_entrypoint()
def main(articles: str = str(DATASET / 'configs/articles/diverse30.yaml'), run: str = 'diverse30',
         stage_only: bool = False, servers: int = 2, per_server: int = 3):
    print(build.remote(Path(articles).read_text(), run, stage_only, servers, per_server))
