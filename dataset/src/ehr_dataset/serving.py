"""Serve the configured model with vLLM (Reflection Beam NVFP4 + DFlash2 by default).

`serving.args` in the config is the vLLM command line after `vllm serve`; these placeholders are
filled in: {model}, {draft}, {port}, {host}, {served_model}, {context}.
"""
from __future__ import annotations

from pathlib import Path

WEIGHT_PATTERNS = ['*.json', '*.jinja', '*.py', '*.safetensors', '*.model', '*.tiktoken', '*.txt',
                   'l4_200k_base', 'README.md', 'LICENSE*', 'USE_POLICY.md']


def command(config, *, weights, port=8000, host='127.0.0.1', python='/usr/bin/python3'):
    weights = Path(weights)
    values = {'{model}': str(weights / 'model'), '{draft}': str(weights / 'draft'), '{port}': str(port),
              '{host}': host, '{served_model}': config['extraction']['served_model'], '{context}': str(config['context'])}

    def fill(arg):
        for key, value in values.items():
            arg = arg.replace(key, value)
        return arg
    return [python, '-m', 'vllm.entrypoints.cli.main', 'serve', *(fill(str(a)) for a in config['serving']['args'])]


def environment(config, *, devices, cache):
    cache = Path(cache)
    return {'CUDA_VISIBLE_DEVICES': devices, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'HF_DATASETS_OFFLINE': '1', 'VLLM_NO_USAGE_STATS': '1', 'DO_NOT_TRACK': '1',
            'PYTHONDONTWRITEBYTECODE': '1', 'HF_HOME': str(cache / 'hf'), 'VLLM_CACHE_ROOT': str(cache / 'vllm'),
            'TRITON_CACHE_DIR': str(cache / 'triton'), 'TORCHINDUCTOR_CACHE_DIR': str(cache / 'inductor'),
            'XDG_CACHE_HOME': str(cache / 'xdg'), **{k: str(v) for k, v in config['serving'].get('environment', {}).items()}}


def download_weights(config, dest, *, tokenizer_only=False):
    """Download the pinned model (and draft model, if any) to DEST/model and DEST/draft."""
    from huggingface_hub import snapshot_download
    for name, spec in config['serving']['weights'].items():
        if tokenizer_only and name != 'model':
            continue
        snapshot_download(repo_id=spec['repo'], revision=spec['revision'], local_dir=Path(dest) / name,
                          allow_patterns=[p for p in WEIGHT_PATTERNS if p != '*.safetensors'] if tokenizer_only
                          else WEIGHT_PATTERNS)
