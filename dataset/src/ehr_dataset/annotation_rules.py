"""Render the shared rules (rules/annotation_rules.yaml) into every runtime prompt.

    python -m ehr_dataset.annotation_rules --check   # exit 1 when a prompt file's block is stale
    python -m ehr_dataset.annotation_rules --write   # regenerate the SHARED RULES blocks

Prompt files (prompts/<task>.md) end with a generated SHARED RULES block. Code-built prompts
(roster/summary/timeline in article_tasks, figure visual/EHR/privacy instructions) call
`prompt_block()` at import, so they cannot drift. Edit the YAML, never a block.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import yaml

from . import semantic_rules

RULES_FILE = 'rules/annotation_rules.yaml'
PROMPT_FILES = ('system', 'case_context', 'demographics', 'conditions', 'symptoms_function', 'medications',
                'allergies', 'procedures_devices', 'observations', 'oncology', 'family_genetics',
                'reproductive_perinatal', 'social_exposures', 'outcomes', 'care_plans')
CODE_PROMPTS = ('roster', 'summary', 'timeline', 'figure_visual', 'figure_ehr_label', 'figure_privacy_flags')
PROMPT_START = 'SHARED RULES (generated from rules/annotation_rules.yaml; rule IDs in brackets):'
PROMPT_END = 'END SHARED RULES'
@lru_cache(maxsize=None)
def load_rules():
    data = yaml.safe_load(files('ehr_dataset').joinpath(RULES_FILE).read_text(encoding='utf-8'))
    if data.get('format') != 'synthetic-ehr-annotation-rules/1':
        raise ValueError('Unknown annotation rules format')
    rules = data['rules']
    ids = [r['id'] for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate rule id')
    values = {'EVENT_OCCURRENCES': ', '.join(semantic_rules.EVENT_OCCURRENCES),
              'TEMPORAL_RELATIONS': ', '.join(semantic_rules.TEMPORAL_RELATIONS)}
    out = []
    for r in rules:
        unknown = set(r.get('prompts', [])) - set(PROMPT_FILES) - set(CODE_PROMPTS)
        if unknown:
            raise ValueError(f'{r["id"]}: unknown prompt targets {sorted(unknown)}')
        out.append({**r, 'text': ' '.join(r['text'].format(**values).split())})
    return tuple(out)


def rules_for(prompt):
    return [r for r in load_rules() if prompt in r.get('prompts', [])]


def prompt_block(prompt):
    """Text block appended to one runtime prompt ('' when no rule targets it)."""
    rules = rules_for(prompt)
    if not rules:
        return ''
    return '\n'.join([PROMPT_START] + [f'- [{r["id"]}] {r["text"]}' for r in rules] + [PROMPT_END])


def _replace(text, start, end, block, append_sep):
    if start in text:
        if end not in text.split(start, 1)[1]:
            raise ValueError('Generated block start without end marker')
        before, rest = text.split(start, 1)
        after = rest.split(end, 1)[1]
        return before + block + after
    if not block:
        return text
    return text.rstrip('\n') + append_sep + block + '\n'


def prompt_path(name):
    return Path(str(files('ehr_dataset').joinpath('prompts', f'{name}.md')))


def render_prompt_file(name, text):
    return _replace(text, PROMPT_START, PROMPT_END, prompt_block(name), '\n\n')


def targets():
    """[(path, current_text, rendered_text)] for every runtime prompt file."""
    out = []
    for name in PROMPT_FILES:
        path = prompt_path(name)
        text = path.read_text(encoding='utf-8')
        out.append((path, text, render_prompt_file(name, text)))
    return out


def drift():
    """Prompt files whose generated block differs from the rules file (or lacks it)."""
    return [str(path) for path, text, rendered in targets() if text != rendered]


def write():
    changed = []
    for path, text, rendered in targets():
        if text != rendered:
            path.write_text(rendered, encoding='utf-8'); changed.append(str(path))
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true'); group.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    if args.write:
        for path in write():
            print('updated', path)
        return 0
    stale = drift()
    for path in stale:
        print('drift', path)
    return 1 if stale else 0


if __name__ == '__main__':
    raise SystemExit(main())
