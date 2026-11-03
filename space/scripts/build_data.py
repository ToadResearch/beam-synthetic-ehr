"""Build the site's data files from a finished run and its exported dataset.

    python scripts/build_data.py --run ../dataset/runs/diverse30 --dataset ../dataset/hf-dataset --out public/data

Writes index.json, one gzipped JSON per article (source text, figures, extracted facts with their
evidence and the model's stated reasons), one per patient (the coded FHIR bundle) and tour.json.gz,
the worked example behind the walkthrough. Standard library only.
"""
import argparse
import gzip
import json
import re
import shutil
from pathlib import Path

SECTIONS = {
    'demographics': 'Demographics', 'case_context': 'Case context', 'conditions': 'Conditions',
    'symptoms_function': 'Symptoms and function', 'observations': 'Observations', 'medications': 'Medications',
    'procedures_devices': 'Procedures and devices', 'allergies': 'Allergies', 'oncology': 'Oncology',
    'family_genetics': 'Family and genetics', 'reproductive_perinatal': 'Reproductive and perinatal',
    'social_exposures': 'Social and exposures', 'outcomes': 'Outcomes', 'care_plans': 'Care plans'}
# Item fields shown as the row's headline or kept out of the detail table.
HIDDEN = {'subject', 'evidence', 'time', 'name', 'attribute', 'assertion', 'temporality', 'numeric_value', 'unit',
          'comparator', 'text_value', 'dose_value', 'dose_unit', 'dose_text'}
ICD = 'http://hl7.org/fhir/sid/icd-10-cm'


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_gz(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))


def norm(text):
    return re.sub(r'\W+', ' ', (text or '').lower()).strip()


def number(value):
    if value is None:
        return None
    value = float(value)
    return f'{value:,.0f}' if value.is_integer() and abs(value) >= 1000 else f'{value:g}'


# ---------------------------------------------------------------- article tables
# Each table_row segment repeats its table: [label, caption, *header lines, group heading, row], one per line,
# empty parts left out. The row is the last line (without '|' when a single cell is left under rowspans).
# Body cells carry ' [rowspan=r,colspan=c]' markers; header lines carry none, so their spans are inferred.
# Cell IDs follow the pipeline (measurement_series.table_grid): '<segment>-c<j>' is cell j of the segment's
# last '|' line and '<segment>-h<j>' cell j of the '|' line before it; `map` says which drawn row each is.

SPAN = re.compile(r'\s*\[rowspan=(\d+),colspan=(\d+)\]$')
LABEL = re.compile(r'^(supplementary\s+)?(table|tab\.?)\b', re.I)


def split_row(line):
    return [c.strip() for c in line.split('|')]


def table_cell(text):
    """{t: text without the span marker, rs: rowspan, cs: colspan}, spans only when above 1."""
    m = SPAN.search(text)
    if not m:
        return {'t': text}
    cell = {'t': text[:m.start()].rstrip()}
    if int(m.group(1)) > 1:
        cell['rs'] = int(m.group(1))
    if int(m.group(2)) > 1:
        cell['cs'] = int(m.group(2))
    return cell


def grid_width(rows):
    """Columns the body fills, placing each row's cells around the rowspans from rows above."""
    width, covered = 0, {}
    for cells in rows:
        busy = set(covered)
        covered = {c: n - 1 for c, n in covered.items() if n > 1}
        col = 0
        for cell in cells:
            while col in busy:
                col += 1
            if cell.get('rs', 1) > 1:
                covered.update((c, cell['rs'] - 1) for c in range(col, col + cell.get('cs', 1)))
            col += cell.get('cs', 1)
        width = max(width, col, max(busy, default=-1) + 1)
    return width


def lead_number(text):
    m = re.match(r'\s*([−-]?\d+(?:\.\d+)?)', text)
    return float(m.group(1).replace('−', '-')) if m else None


def group_sizes(k, children):
    """How k spanning header cells divide the n cells below them: evenly, or where a run of numbers restarts."""
    n = len(children)
    if k <= 1 or n < k:
        return [n] if k == 1 else None
    if n % k == 0:
        return [n // k] * k
    values = [lead_number(c['t']) for c in children]
    if None not in values:
        drops = sorted(((values[i] - values[i + 1], i + 1) for i in range(n - 1) if values[i + 1] < values[i]),
                       reverse=True)
        if len(drops) >= k - 1:
            cuts = sorted(at for _, at in drops[:k - 1])
            return [b - a for a, b in zip([0] + cuts, cuts + [n])]
    return [n // k + (i < n % k) for i in range(k)]


def header_rows(lines, width, first_body):
    """Header lines as cells with inferred spans: the top line's first cells reach down to the body, the rest
    group the cells of the line below; a single short line copies the first row's colspans or widens its stub."""
    rows = [[table_cell(t) for t in split_row(line)] for line in lines]
    if not rows or any('rs' in c or 'cs' in c for r in rows for c in r):
        return rows
    last = rows[-1]
    if len(rows) == 1:
        if width > len(last):
            if first_body and len(first_body) == len(last):
                for c, b in zip(last, first_body):
                    if b.get('cs', 1) > 1:
                        c['cs'] = b['cs']
            else:
                last[0]['cs'] = width - len(last) + 1
        return rows
    stubs = width - len(last)
    if stubs < 0 or stubs >= len(rows[0]):
        return rows
    for c in rows[0][:stubs]:
        c['rs'] = len(rows)
    for upper in range(len(rows) - 2, -1, -1):
        parents = rows[upper][stubs:] if upper == 0 else rows[upper]
        children = rows[upper + 1]
        sizes = group_sizes(len(parents), children)
        if not sizes:
            break
        at = 0
        for parent, n in zip(parents, sizes):
            span = sum(c.get('cs', 1) for c in children[at:at + n])
            if span > 1:
                parent['cs'] = span
            at += n
    return rows


def table_block(tid, segments):
    """One table drawn as printed: header rows, body rows with their spans, group and mid-table header rows."""
    sids = [s['segment_id'] for s in segments]
    lines = [s['text'].split('\n') for s in segments]
    n = len(lines)
    if n == 1 and len(lines[0]) <= 2 and '|' not in lines[0][-1] and (len(lines[0]) == 1 or LABEL.match(lines[0][0])):
        # Label and caption only: the table itself is an image or empty.
        return {'type': 'table', 'id': tid, 'label': lines[0][0] if len(lines[0]) == 2 else '', 'caption': lines[0][-1],
                'head': [], 'rows': [], 'map': {}, 'notes': []}
    common = lines[0][:-1]
    for ls in lines[1:]:
        k = 0
        while k < min(len(common), len(ls) - 1) and common[k] == ls[k]:
            k += 1
        common = common[:k]
    at, label, caption = 0, '', ''
    if at < len(common) and '|' not in common[at] and LABEL.match(common[at]):
        label, at = common[at], at + 1
    if at < len(common) and '|' not in common[at]:
        caption, at = common[at], at + 1
    head_lines = common[at:]
    row_cells = [[table_cell(t) for t in split_row(ls[-1])] for ls in lines]
    is_group = [len(r) == 1 and r[0].get('cs', 1) > 1 for r in row_cells]
    if head_lines and is_group[0] and head_lines[-1] == row_cells[0][0]['t']:
        head_lines = head_lines[:-1]  # every row sits under one group heading
    pipes = [[l for l in ls if '|' in l] for ls in lines]
    first_is_head = not head_lines and n > 1 and len(pipes[0]) == 1 and len(pipes[1]) == 1 and '|' in lines[0][-1]

    rows, mapping, group, subs = [], {}, None, 0
    for k, (sid, ls) in enumerate(zip(sids, lines)):
        keys = [None] * len(ls)
        for i in range(len(head_lines)):
            keys[at + i] = f'h{i}'
        if is_group[k]:
            group = row_cells[k][0]['t']
        extra = list(range(len(common), len(ls) - 1))
        if extra and ls[extra[-1]] == group:
            extra.pop()
        for i, pos in enumerate(extra):
            keys[pos] = f's{i}'
            if i >= subs:  # a header row first printed here, part way down the table
                rows.append({'key': f's{i}', 'kind': 'sub', 'cells': header_rows([ls[pos]], 0, None)[0]})
                subs += 1
        if k == 0 and first_is_head:
            keys[-1] = 'h0'
        else:
            keys[-1] = sid
            rows.append({'id': sid, 'kind': 'group' if is_group[k] else 'row', 'cells': row_cells[k]})
        pipe_at = [i for i, l in enumerate(ls) if '|' in l]
        h = c = None
        if len(pipe_at) >= 2:
            h, c = keys[pipe_at[-2]], keys[pipe_at[-1]]
        elif len(pipe_at) == 1:
            if k == 0 and n > 1 and len(pipes[1]) == 1:
                h = keys[pipe_at[0]]
            else:
                c = keys[pipe_at[0]]
        if h or c:
            mapping[sid] = [h, c]

    body = [r['cells'] for r in rows if r['kind'] != 'sub']
    first_body = next((r['cells'] for r in rows if r['kind'] == 'row'), None)
    width = max([grid_width(body)] + [len(split_row(l)) for l in head_lines[-1:]])
    if first_is_head:
        head = [{'key': 'h0', 'id': sids[0], 'cells': header_rows([lines[0][-1]], width, first_body)[0]}]
    else:
        head = [{'key': f'h{i}', 'cells': cells} for i, cells in enumerate(header_rows(head_lines, width, first_body))]
    return {'type': 'table', 'id': tid, 'label': label, 'caption': caption, 'head': head, 'rows': rows,
            'map': mapping, 'notes': []}


def pipeline_cells(source):
    """cell_id -> literal text for every article table cell, numbered as the pipeline numbers them."""
    out, tables = {}, {}
    for seg in source['segments']:
        if seg['kind'] == 'table_row':
            tables.setdefault(seg.get('table_id') or seg['segment_id'], []).append(seg)
    for segs in tables.values():
        pipes = [[l for l in s['text'].split('\n') if '|' in l] for s in segs]
        for i, (seg, lines) in enumerate(zip(segs, pipes)):
            header = row = None
            if len(lines) >= 2:
                header, row = lines[-2], lines[-1]
            elif len(lines) == 1 and i == 0 and len(segs) > 1 and len(pipes[1]) == 1:
                header = lines[0]
            elif len(lines) == 1:
                row = lines[0]
            for j, t in enumerate(split_row(header) if header else []):
                out[f'{seg["segment_id"]}-h{j}'] = t
            for j, t in enumerate(split_row(row) if row else []):
                out[f'{seg["segment_id"]}-c{j}'] = t
    return out


# ---------------------------------------------------------------- article text

def article_blocks(source):
    """Headings, paragraphs, tables and figures in reading order; figures follow their first citation."""
    figures = {f['figure_id']: f for f in source.get('figures') or []}
    captions = {s.get('figure_id'): s['segment_id'] for s in source['segments'] if s['kind'] == 'figure_caption'}
    blocks, tables, placed, heading = [], {}, set(), object()
    rows_of = {}
    for seg in source['segments']:
        if seg['kind'] == 'table_row':
            rows_of.setdefault(seg.get('table_id') or seg['segment_id'], []).append(seg)

    def figure(fid):
        f = figures[fid]
        placed.add(fid)
        return {'type': 'figure', 'id': fid, 'label': f.get('label') or fid, 'caption': f.get('caption') or '',
                'captionId': captions.get(fid), 'images': [m['url'] for m in f.get('media') or [] if m.get('url')]}

    for seg in source['segments']:
        kind, sid = seg['kind'], seg['segment_id']
        if kind == 'figure_caption':
            continue
        if seg.get('heading') != heading:
            heading = seg.get('heading')
            if heading:
                blocks.append({'type': 'heading', 'text': heading})
        if kind == 'table_row':
            tid = seg.get('table_id') or sid
            if tid not in tables:
                tables[tid] = table_block(tid, rows_of[tid])
                blocks.append(tables[tid])
            continue
        if kind == 'table_footnote' and seg.get('table_id') in tables:
            tables[seg['table_id']]['notes'].append({'id': sid, 'text': seg['text']})
            continue
        blocks.append({'type': 'p', 'id': sid, 'text': seg['text']})
        for ref in seg.get('cross_references') or []:
            if ref.get('ref_type') == 'fig':
                blocks += [figure(fid) for fid in ref.get('target_ids') or [] if fid in figures and fid not in placed]
    rest = [fid for fid in figures if fid not in placed]
    if rest:
        blocks.append({'type': 'heading', 'text': 'Figures'})
        blocks += [figure(fid) for fid in rest]
    return blocks


def attribution(source):
    lic = source.get('license') or {}
    statement = next((s.get('text') for s in lic.get('statements') or [] if s.get('type') == 'copyright-statement'), None)
    code = ' '.join(x for x in (lic.get('code'), lic.get('version')) if x)
    url = next((s.get('url') for s in lic.get('statements') or [] if (s.get('url') or '').startswith('http')), None)
    return {'license': code, 'licenseUrl': url, 'copyright': statement}


# ---------------------------------------------------------------- extracted facts

def model_tasks(article_dir):
    tasks = [json.loads(p.read_text()) for p in sorted((article_dir / 'extraction/tasks').glob('*.json'))]
    return sorted(tasks, key=lambda t: not t['task'].startswith('clinical_window_'))


def reasoning_of(task):
    for attempt in reversed(task.get('attempts') or []):
        text = (attempt.get('response') or {}).get('reasoning_text')
        if text:
            return text
    return None


def task_index(tasks):
    """(patient, section, name, quote) -> the model output that produced a fact, with its stated reasons."""
    index = {}
    for task in tasks:
        section = task['task'].removeprefix('clinical_window_')
        data = task.get('data') if isinstance(task.get('data'), dict) else {}
        items = (data.get('extraction') or {}).get('items') or []
        if section not in SECTIONS or not items:
            continue
        scopes = {s.get('path'): s.get('reason') for s in data.get('fact_scopes') or []}
        decisions = {d.get('segment_id'): d.get('reason') for d in data.get('source_decisions') or []}
        pid = task['identity'].get('patient_id')
        for i, item in enumerate(items):
            quote = norm(((item.get('evidence') or [{}])[0]).get('quote'))
            name = norm(item.get('name') or item.get('attribute'))
            found = {'task': task['task'], 'window': task['identity'].get('focus_segment_ids') or [],
                     'why': scopes.get(f'/items/{i}'), 'decisions': decisions, 'reasoning': reasoning_of(task),
                     'status': task.get('status'), 'attempts': len(task.get('attempts') or [])}
            for key in ((pid, section, name, quote), (pid, section, name), (pid, section, '', quote)):
                index.setdefault(key, found)
    return index


def excerpt(text, needles, source='', width=640):
    """The reasoning around the first mention of the fact in the model's own words (not a copy of the
    article), cut at sentence or line boundaries."""
    if not text:
        return None
    low, copied = text.lower(), norm(source)
    for needle in needles:
        needle = (needle or '').lower().strip()
        at = low.find(needle) if len(needle) >= 3 else -1
        while at >= 0 and copied and norm(text[max(0, at - 40):at + len(needle) + 40]) in copied:
            at = low.find(needle, at + len(needle))
        if at < 0:
            continue
        start = max(text.rfind('\n', 0, at) + 1, text.rfind('. ', 0, at) + 2, at - 240, 0)
        end = min(len(text), start + width)
        stop = max(text.rfind('. ', start, end), text.rfind('\n', start, end))
        if stop > at + len(needle):
            end = stop + 1
        return ('… ' if start > 0 else '') + text[start:end].strip() + (' …' if end < len(text) else '')
    return None


def headline(section, item):
    """Short value text for a fact row."""
    if item.get('numeric_value') is not None:
        comparator = item.get('comparator') if item.get('comparator') not in (None, '=', 'unknown') else ''
        return ' '.join(x for x in (f'{comparator}{number(item["numeric_value"])}', item.get('unit')) if x)
    if section == 'medications':
        dose = item.get('dose_text') or ' '.join(x for x in (number(item.get('dose_value')), item.get('dose_unit')) if x)
        return ', '.join(x for x in (dose, item.get('route'), item.get('frequency')) if x) or None
    return item.get('text_value')


def facts(patient, index, source_text):
    pid, out = patient['patient_id'], []
    for section, label in SECTIONS.items():
        rows = []
        for n, item in enumerate((patient['sections'].get(section) or {}).get('items') or []):
            evidence = [{'seg': e.get('source_section'), 'quote': e.get('quote')} for e in item.get('evidence') or []
                        if e.get('source_section') and e.get('quote')]
            name = item.get('name') or (item.get('attribute') or '').replace('_', ' ') or label
            quote = norm(evidence[0]['quote']) if evidence else ''
            found = (index.get((pid, section, norm(name), quote)) or index.get((pid, section, norm(name)))
                     or index.get((pid, section, '', quote)) or {})
            first = evidence[0] if evidence else {}
            rows.append({
                'id': f'{section}-{n}', 'name': name, 'value': headline(section, item),
                'assertion': item.get('assertion'), 'temporality': item.get('temporality'),
                'time': (item.get('time') or {}).get('text'),
                'fields': {k: v for k, v in item.items() if k not in HIDDEN and v not in (None, '', 'unknown', [])
                           and not isinstance(v, (dict, list))},
                'evidence': evidence,
                'why': found.get('why'),
                'segmentWhy': (found.get('decisions') or {}).get(first.get('seg')),
                'task': found.get('task'), 'window': found.get('window'), 'subject': item.get('subject'),
                'status': found.get('status'), 'attempts': found.get('attempts'),
                'reasoning': excerpt(found.get('reasoning'), [name, (first.get('quote') or '')[:48],
                                                               ' '.join((first.get('quote') or '').split()[:3])],
                                     source_text)})
        if rows:
            out.append({'key': section, 'label': label, 'items': rows})
    return out


CELL_NUMBER = re.compile(r'(<=|>=|[<>≤≥])?\s*([+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+\-−]?\.\d+)'
                         r'(?:\s*[×x*]\s*10\s*\^\s*\(?([+\-−]?\d{1,2})\)?)?\s*(.*)')
NOTE_MARK = re.compile(r'\s*(?:\^\([^)]{1,8}\)|\^[A-Za-z*†‡§¶#]|[*†‡§¶#])$')


def cell_number(text):
    """(value, unit) of a cell holding one number, as '8,400 IU/ml', '<0.5', '1.3 kE/L', '79', '1.0 × 10^(9)/L';
    None for ranges, pairs and words. Used where the pipeline left a cell unparsed (units outside its list)."""
    m = CELL_NUMBER.fullmatch(SPAN.sub('', text or '').strip())
    if not m:
        return None, None
    rest = m.group(4)
    while NOTE_MARK.search(rest):
        rest = NOTE_MARK.sub('', rest)
    if re.match(r'(?:[–—\-/,]|to\b)\s*\d', rest) or ';' in rest:
        return None, None
    value = float(m.group(2).replace(',', '').replace('−', '-')) * 10 ** int((m.group(3) or '0').replace('−', '-'))
    return value, rest.strip() or None


def series_of(patient, cells=None):
    """Measurement series; a point the pipeline did not parse takes its number from the literal cell."""
    out, cells = [], cells or {}
    for s in patient.get('measurement_series') or []:
        points = []
        for p in s.get('points') or []:
            parsed = p.get('parsed') or {}
            try:
                value, unit = float(parsed.get('magnitude')), parsed.get('unit')
            except (TypeError, ValueError):
                value, unit = cell_number(cells.get(p.get('value_cell_id')))
            raw = parsed.get('raw_text') or SPAN.sub('', cells.get(p.get('value_cell_id')) or '') or None
            points.append({'label': (p.get('time') or {}).get('time_text'), 'value': value,
                           'raw': raw, 'unit': unit, 'cell': p.get('value_cell_id'),
                           'timeCell': (p.get('time') or {}).get('time_cell_id')})
        out.append({'id': s['series_id'], 'name': s.get('measurement_name'), 'kind': s.get('measurement_kind'),
                    'nameCell': s.get('name_cell_id'), 'points': points})
    return out


def timeline_of(patient):
    t = patient.get('relative_timeline') or patient.get('timeline') or {}
    events = {e['event_id']: e for e in t.get('events') or []}
    order = [i for i in t.get('ordered_event_ids') or [] if i in events]
    order += [i for i in events if i not in order]
    return [{'id': i, 'kind': events[i].get('kind'), 'text': events[i].get('description'),
             'evidence': [{'seg': e.get('segment_id'), 'quote': e.get('quote')} for e in events[i].get('evidence') or []
                          if e.get('segment_id') and e.get('quote')]} for i in order]


def summary_of(patient):
    claims = (patient.get('summary') or {}).get('claims') or []
    return [{'text': c.get('text'), 'evidence': [{'seg': e.get('segment_id'), 'quote': e.get('quote')}
                                                 for e in c.get('evidence') or []]} for c in claims]


CONTEXT = ('case_kind', 'index_subject_description', 'species', 'multiple_index_patients', 'subject_state', 'care_setting',
           'chief_complaint')


def case_context_of(patient):
    """The case-context section is a set of fields, not a list of facts."""
    cc = (patient.get('sections') or {}).get('case_context') or {}
    fields = {k: cc[k] for k in CONTEXT if cc.get(k) not in (None, '', 'unknown', [])}
    if not fields:
        return None
    return {'fields': fields, 'limitations': cc.get('limitations') or [],
            'evidence': [{'seg': e.get('source_section'), 'quote': e.get('quote')} for e in cc.get('evidence') or []
                         if e.get('source_section') and e.get('quote')]}


# What an article offers beyond text, for the article list's theme filter.
THEMES = [('Serial measurements', lambda k, n, f: n['series'] >= 2), ('Imaging', lambda k, n, f: k['observations', 'imaging'] > 0),
          ('Pathology', lambda k, n, f: k['observations', 'pathology'] > 0), ('Microbiology', lambda k, n, f: k['observations', 'microbiology'] > 0),
          ('Vital signs', lambda k, n, f: k['observations', 'vital'] >= 3), ('Clinical scores', lambda k, n, f: k['symptoms_function', 'performance_score'] > 0),
          ('Genetic testing', lambda k, n, f: k['family_genetics', 'genetic_test'] > 0),
          ('Several patients', lambda k, n, f: n['patients'] > 1), ('Figures', lambda k, n, f: f > 0)]


# Age ranges for the filters, from the model's age at presentation.
AGES = [('Under 1 year', 0, 1), ('1–17 years', 1, 18), ('18–39 years', 18, 40), ('40–64 years', 40, 65),
        ('65–79 years', 65, 80), ('80 years and over', 80, 1000)]
YEARS = {'year': 1, 'month': 1 / 12, 'week': 1 / 52, 'day': 1 / 365, 'hour': 1 / 8760}


def demographic(patient, attribute):
    items = ((patient.get('sections') or {}).get('demographics') or {}).get('items') or []
    return next((i for i in items if i.get('attribute') == attribute), None)


def age_years(patient):
    """The model's age at presentation, in years."""
    age = demographic(patient, 'age_at_presentation') or {}
    unit = next((v for k, v in YEARS.items() if (age.get('unit') or '').lower().startswith(k)), None)
    if age.get('numeric_value') is None or unit is None:
        return None
    return float(age['numeric_value']) * unit


def age_group(patient):
    years = age_years(patient)
    return None if years is None else next(label for label, lo, hi in AGES if lo <= years < hi)


def sex_of(patient):
    """The model's documented sex."""
    text = ' '.join(str((demographic(patient, a) or {}).get(k) or '') for a in ('documented_sex', 'sex') for k in ('text_value', 'name')).lower()
    return 'Female' if re.search(r'\b(female|woman|girl)\b', text) else 'Male' if re.search(r'\b(male|man|boy)\b', text) else None


def themes_of(patients, figures):
    from collections import Counter
    kinds = Counter((s['key'], i['fields'].get('kind')) for p in patients for s in p['sections'] for i in s['items'])
    counts = {'patients': len(patients),
              'series': sum(1 for p in patients for x in p['series'] if sum(pt['value'] is not None for pt in x['points']) >= 3)}
    return [name for name, test in THEMES if test(kinds, counts, figures)]


# ---------------------------------------------------------------- FHIR

def slim_bundle(bundle):
    """The released bundle minus the base64 extraction packets attached as DocumentReferences."""
    for entry in bundle.get('entry') or []:
        if entry['resource']['resourceType'] != 'DocumentReference':
            continue
        for content in entry['resource'].get('content') or []:
            attachment = content.get('attachment') or {}
            if 'data' in attachment:
                attachment['size'] = len(attachment.pop('data')) * 3 // 4
                attachment['title'] = 'Attachment omitted in the viewer; it is in the dataset row.'
    return bundle


def conditions_of(bundle):
    """The bundle's conditions that were not ruled out, with the ICD-10-CM code the model chose, if any."""
    out = []
    for entry in bundle.get('entry') or []:
        r = entry['resource']
        if r['resourceType'] != 'Condition':
            continue
        if ((r.get('verificationStatus') or {}).get('coding') or [{}])[0].get('code') == 'refuted':
            continue
        code = next((c.get('code') for c in (r.get('code') or {}).get('coding') or [] if c.get('system') == ICD), None)
        out.append({'name': (r.get('code') or {}).get('text'), 'code': code})
    return out


def resource_counts(bundle):
    counts = {}
    for entry in bundle.get('entry') or []:
        counts[entry['resource']['resourceType']] = counts.get(entry['resource']['resourceType'], 0) + 1
    return counts


# ---------------------------------------------------------------- walkthrough

def coding_for(article_dir, name):
    """The ICD-10-CM request (fact and candidates) and the model's decision for a condition name."""
    packet = article_dir / 'fhir/packet'
    requests = [r for r in read_jsonl(packet / 'requests.jsonl') if r.get('task') == 'conditions'
                and norm((r.get('fact') or {}).get('name')) == norm(name)]
    for request in requests:
        path = packet / 'decisions' / f'{request["id"]}.json'
        if not path.exists():
            continue
        decision = json.loads(path.read_text())['decision']
        call = next((t for t in map(lambda p: json.loads(p.read_text()), (packet / 'coding-calls/batch/tasks').glob('*.json'))
                     if any(d.get('request_id') == request['id'] for d in (t.get('data') or {}).get('decisions') or [])), None)
        return {'fact': {k: request['fact'].get(k) for k in ('name', 'assertion', 'verification_status', 'clinical_status',
                                                             'severity', 'body_site')},
                'candidates': [{'id': c.get('candidate_id'), 'code': c.get('code'), 'display': c.get('display'),
                                'score': c.get('retrieval_score')} for c in request.get('candidates') or []],
                'decision': decision, 'reasoning': excerpt(reasoning_of(call) if call else None, [name, request['id'][:8]])}
    return None


def tour(args, article, source, patient, bundle, report, tasks):
    """Facts from one article followed through every stage."""
    aid = article['id']
    segs = {s['segment_id']: s for s in source['segments']}
    condition = next(i for s in patient['sections'] for i in s['items'] if s['key'] == 'conditions')
    first = condition['evidence'][0]
    roster = next((t for t in tasks if t['task'] == 'roster'), None)
    roster_data = (roster or {}).get('data') or {}
    series = next((s for s in patient['series'] if len([p for p in s['points'] if p['value'] is not None]) >= 3), None)
    resource = next((e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'Condition'
                     and norm(e['resource'].get('code', {}).get('text')) == norm(condition['name'])), None)
    if resource:
        resource = json.loads(json.dumps(resource))
        for ext in resource.get('extension') or []:
            if ext.get('valueString', '').startswith('{'):
                ext['valueString'] = ext['valueString'][:160] + '…'
        resource.pop('text', None)
    return {
        'article': {k: article[k] for k in ('id', 'title', 'citation', 'url', 'license')},
        'outline': [{'id': s['segment_id'], 'kind': s['kind'], 'heading': s.get('heading'), 'chars': len(s.get('text') or '')}
                    for s in source['segments']],
        'counts': {'segments': len(source['segments']),
                   'tableRows': sum(s['kind'] == 'table_row' for s in source['segments']),
                   'figures': len(source.get('figures') or []), 'words': (source.get('lengths') or {}).get('words')},
        'segment': {'id': first['seg'], 'text': segs[first['seg']]['text'], 'heading': segs[first['seg']].get('heading')},
        'roster': {'disposition': roster_data.get('disposition'), 'count': roster_data.get('reported_individual_count'),
                   'patients': [{'id': p.get('patient_id'), 'label': p.get('label'),
                                 'evidence': [{'seg': e.get('segment_id'), 'quote': e.get('quote')}
                                              for e in p.get('identity_evidence') or []],
                                 'segments': p.get('source_segment_ids') or []} for p in roster_data.get('patients') or []],
                   'reasoning': excerpt(reasoning_of(roster) if roster else None, ['patient', 'case'])},
        'fact': condition,
        'series': series,
        'timeline': patient['timeline'][:7],
        'coding': coding_for(Path(args.run) / 'articles' / aid, condition['name']),
        'resource': resource,
        'validation': report,
        'bundleCounts': resource_counts(bundle)}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True, help='run folder: inputs/<article>/source.jsonl and articles/<article>/')
    ap.add_argument('--dataset', required=True, help='exported dataset folder (data/*.jsonl, manifest.json)')
    ap.add_argument('--out', default='public/data')
    ap.add_argument('--tour', default='PMC12592069.1', help='article followed through the walkthrough')
    ap.add_argument('--featured', default='PMC12817846.1', help='article the site opens on')
    ap.add_argument('--article', action='append', help='build only these articles (repeatable)')
    args = ap.parse_args()
    run, dataset, out = Path(args.run), Path(args.dataset), Path(args.out)

    records = {r['article_id']: r for r in read_jsonl(dataset / 'data/extraction.jsonl')
               if not args.article or r['article_id'] in args.article}
    if not args.article:  # a full build replaces everything; a partial one updates in place
        for folder in ('articles', 'records'):
            shutil.rmtree(out / folder, ignore_errors=True)
    bundles = {}
    for row in read_jsonl(dataset / 'data/coded.jsonl'):
        bundles.setdefault(row['article_id'], {})[row['patient_id']] = row
    index = {'articles': [], 'totals': {}}
    for aid, row in sorted(records.items()):
        source = json.loads((run / 'inputs' / aid / 'source.jsonl').read_text().splitlines()[0])
        record = json.loads(row['record'])
        article_dir = run / 'articles' / aid
        tasks = model_tasks(article_dir)
        found = task_index(tasks)
        report_path = article_dir / 'fhir/experimental-coded/report.json'
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        meta = {'id': aid, 'title': row['title'], 'doi': row['doi'], 'url': row['source_url'],
                'citation': (source.get('metadata') or {}).get('citation'), **attribution(source),
                'license': row['license'], 'licenseUrl': row['license_url'], 'type': source.get('article_type'),
                'pmcid': source.get('pmcid')}
        validations = {v.get('patient_id'): v.get('validation') or {} for v in report.get('patients') or []}
        # Literal cells behind the series points: the article's tables, plus the series sidecar when the run has it.
        cells = pipeline_cells(source)
        sidecar = article_dir / 'ehr/articles' / aid / 'measurement_series.json'
        for c in (json.loads(sidecar.read_text()).get('cells') if sidecar.exists() else None) or []:
            cells.setdefault(c['cell_id'], c.get('raw_text'))
        for c in (record.get('measurement_series') or {}).get('cells') or []:
            cells.setdefault(c['cell_id'], c.get('raw_text'))
        patients, listed = [], []
        for p in record['patients']:
            entry = {'id': p['patient_id'], 'label': p.get('label'), 'summary': summary_of(p),
                     'sections': facts(p, found, source.get('text') or ''), 'series': series_of(p, cells),
                     'timeline': timeline_of(p), 'caseContext': case_context_of(p)}
            patients.append(entry)
            coded = bundles.get(aid, {}).get(p['patient_id'])
            if not coded:
                continue
            bundle = slim_bundle(json.loads(coded['bundle']))
            counts = resource_counts(bundle)
            v = validations.get(p['patient_id'], {})
            validation = {'passed': v.get('passed'), 'official': v.get('official_validator_run'),
                          'errors': len(v.get('errors') or []), 'scope': v.get('scope')}
            write_gz(out / 'records' / f'{coded["bundle_id"]}.json.gz',
                     {'article': meta, 'patient': {'id': p['patient_id'], 'label': p.get('label')},
                      'validation': validation, 'bundle': bundle})
            listed.append({'id': p['patient_id'], 'label': p.get('label'), 'bundle': coded['bundle_id'],
                           'resources': sum(counts.values()), 'counts': counts, 'passed': validation['passed'],
                           'age': age_group(p), 'sex': sex_of(p), 'conditions': conditions_of(bundle)})
            if aid == args.tour and p is record['patients'][0]:
                write_gz(out / 'tour.json.gz', tour(args, meta, source, entry, bundle, validation, tasks))
        write_gz(out / 'articles' / f'{aid}.json.gz',
                 {'article': meta, 'blocks': article_blocks(source), 'patients': patients})
        index['articles'].append({**{k: meta[k] for k in ('id', 'title', 'citation', 'license')},
                                  'patients': listed, 'facts': sum(len(s['items']) for p in patients for s in p['sections']),
                                  'figures': len(source.get('figures') or []),
                                  'themes': themes_of(patients, len(source.get('figures') or [])),
                                  'ages': [label for label, _, _ in AGES if label in {age_group(p) for p in record['patients']}],
                                  'sexes': sorted({x for x in map(sex_of, record['patients']) if x})})
    if args.article and (out / 'index.json').exists():  # keep the articles this partial build did not touch
        built = {a['id'] for a in index['articles']}
        kept = [a for a in json.loads((out / 'index.json').read_text())['articles'] if a['id'] not in built]
        index['articles'] = sorted(kept + index['articles'], key=lambda a: a['id'])
    arts = index['articles']
    ids = [a['id'] for a in arts]
    index['featured'] = next((x for x in (args.featured, args.tour) if x in ids), ids[0] if ids else None)
    index['totals'] = {'articles': len(arts), 'patients': sum(len(a['patients']) for a in arts),
                       'facts': sum(a['facts'] for a in arts), 'figures': sum(a['figures'] for a in arts),
                       'resources': sum(p['resources'] for a in arts for p in a['patients'])}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(json.dumps(index['totals']))


if __name__ == '__main__':
    main()
