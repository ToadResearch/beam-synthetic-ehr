"""Source-window clinical extraction with explicit coverage and attribution receipts.

Coverage decisions are model judgments, not proof of recall. Original source,
responses, non-patient candidates and failed leaves remain available for review.
"""
import asyncio
import copy
import json
import re
from decimal import Decimal
from typing import Literal

from pydantic import Field, create_model

from .data import write_json
from .evidence_ledger import subset_packet
from .evidence_recovery import packet_segments
from .measurement_series import expected_parse
from .measurements import _model_measurement, parse_measurement
from .provenance import json_digest
from .schemas import StrictModel, TASK_MODELS
from .staged_timeline import fits, replaced, source_window, splittable_failure


class SourceDecision(StrictModel):
    segment_id: str
    disposition: Literal['extracted', 'no_patient_fact', 'unresolved']
    reason: str = Field(min_length=1)


class FactScope(StrictModel):
    path: str
    scope: Literal['direct_patient', 'universal_cohort', 'aggregate', 'study_protocol',
                   'secondary_case', 'background', 'uncertain']
    reason: str = Field(min_length=1)


class CellDecision(StrictModel):
    cell_id: str
    disposition: Literal['extracted', 'no_patient_fact', 'unresolved']
    item_indices: list[int]
    reason: str = Field(min_length=1)


def envelope_model(task):
    return create_model('ClinicalWindow_' + task, __base__=StrictModel,
        extraction=(TASK_MODELS[task], ...), source_decisions=(list[SourceDecision], ...),
        fact_scopes=(list[FactScope], ...), cell_decisions=(list[CellDecision], ...))


def fact_paths(value):
    result = {}
    for key in ('items', 'tumors', 'biomarkers', 'treatments'):
        for i, item in enumerate(value.get(key, [])):
            result[f'/{key}/{i}'] = item
    if 'case_kind' in value and value.get('evidence'):
        result['/'] = value
    return result


def partition(segments, *, max_segments=6, max_chars=10000, table_rows=4):
    """Whole source units, never clipped text. Keep table rows in small groups."""
    groups, batch, size = [], [], 0
    for segment in segments:
        length = len(segment['text'])
        table = segment.get('kind') == 'table_row'
        width = min(max_segments, table_rows) if table else max_segments
        if batch and (len(batch) >= width or size + length > max_chars
                      or (batch[-1].get('kind') == 'table_row') != table):
            groups.append(batch); batch, size = [], 0
        batch.append(segment); size += length
    if batch:
        groups.append(batch)
    return groups


# articles.py marks merged cells inline; the marker is layout, not cell content.
SPAN_MARKER = re.compile(r'\s*\[rowspan=\d+,colspan=\d+\]\s*$')
# Dash variants and "not tested" beyond measurement_series.MISSING. Kept local:
# that set also re-derives frozen reference series parses.
EXTRA_MISSING = {'‐', '‒', '−', 'nt', 'not tested'}
# A value with one parenthesised companion number, e.g. FVC "1.80 (67)" (% predicted).
PARENTHETICAL = re.compile(r'(\d+(?:\.\d+)?)\s*\(\s*(\d+(?:\.\d+)?)\s*%?\s*\)')


def cell_core(raw):
    return SPAN_MARKER.sub('', raw).strip()


def valueless(item):
    return item.get('text_value') is None and item.get('numeric_value') is None


def cell_item_correspondence(cell, item):
    """Verify a value association, not its patient, analyte, unit source or time.

    A whole row quotation cannot stand in for extracting each column's value.
    Decimal comparisons do not convert units; ambiguous notation stays literal.
    The caller preserves both the original decision and all model fields.
    """
    raw = cell_core(cell['raw_text'])
    status, parsed = expected_parse(raw)
    if raw.casefold() in EXTRA_MISSING:
        status, parsed = 'missing_cell', None
    text, number = item.get('text_value'), item.get('numeric_value')
    if status == 'missing_cell':
        # A dash does not establish zero, normality, a negative result, or why
        # the value is missing. Keep such cells explicitly unassessed.
        return False, 'missing_cell_has_no_extractable_result_value'
    if status != 'parsed' or 'magnitude' not in parsed:
        if text in (raw, cell['raw_text']) and number is None:
            return True, 'exact_literal_nonscalar_result'
        pair = PARENTHETICAL.fullmatch(raw)
        if pair and item.get('comparator') == '=':
            # Either number may be the item; the full cell stays in the evidence quote.
            for literal in pair.groups():
                if ((number is None or Decimal(str(number)) == Decimal(literal))
                        and text in (None, raw, literal) and (number is not None or text == literal)):
                    return True, 'one_number_of_value_with_parenthetical'
        return False, 'nonscalar_cell_requires_exact_text_without_numeric_guess'

    if item.get('comparator') != parsed['comparator']:
        return False, 'cell_and_observation_comparator_disagree'
    item_unit = _model_measurement({**item, 'numeric_value': 1}) if item.get('unit') else None
    if parsed['unit'] is not None and item.get('unit') is not None and (
            item_unit is None or item_unit.unit != parsed['unit']):
        return False, 'cell_and_observation_unit_disagree'

    def same_value(other, *, missing_unit_ok=False):
        return bool(other and 'magnitude' in other
            and Decimal(parsed['magnitude']) == Decimal(other['magnitude'])
            and parsed['comparator'] == other['comparator']
            and (parsed['unit'] is None or parsed['unit'] == other.get('unit')
                 or missing_unit_ok and other.get('unit') is None))

    if text is not None:
        text_status, text_parse = expected_parse(text)
        separately_recorded_unit = bool(item_unit and item_unit.unit == parsed['unit'])
        if text_status != 'parsed' or not same_value(text_parse, missing_unit_ok=separately_recorded_unit):
            return False, 'cell_and_text_value_disagree_or_are_ambiguous'
        if text_parse.get('unit') is not None and item.get('unit') is not None and (
                item_unit is None or item_unit.unit != text_parse['unit']):
            return False, 'text_value_and_observation_unit_disagree'
    if number is not None:
        modeled = _model_measurement(item)
        candidates = [modeled.model_dump()] if modeled else []
        if parsed['unit'] is None:
            # Numeric-only cells may have units/scales in their column header.
            # Check the literal numeric field as well, without claiming the
            # header unit has been verified by this value-only association.
            comparator = item.get('comparator')
            literal = parse_measurement((comparator if comparator in {'<', '<=', '>', '>='} else '') + str(number))
            if literal:
                candidates.append(literal.model_dump())
        if item.get('comparator') == 'unknown' or not any(same_value(v) for v in candidates):
            return False, 'cell_and_numeric_value_comparator_or_unit_disagree'
    if text is None and number is None:
        return False, 'cell_value_not_represented_in_observation'
    return True, 'scalar_result_corresponds_without_unit_conversion'


def check_envelope(value, task, checker, focus, cells=()):
    checked = envelope_model(task).model_validate(value).model_dump()
    checked['extraction'] = checker(checked['extraction'])
    decisions = checked['source_decisions']
    ids = [r['segment_id'] for r in decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(focus):
        raise ValueError('Every focus segment needs exactly one coverage decision')
    scopes = [r['path'] for r in checked['fact_scopes']]
    facts = fact_paths(checked['extraction'])
    if len(scopes) != len(set(scopes)) or set(scopes) != set(facts):
        raise ValueError('Every extracted fact needs exactly one attribution scope')
    fact_evidence = [e for fact in facts.values() for e in fact.get('evidence', [])]
    for path, fact in facts.items():
        if not any(e.get('source_section') in focus and e.get('quote') for e in fact.get('evidence', [])):
            raise ValueError('Extracted fact needs a focus-support citation: ' + path)
    # A claim to have extracted from a segment needs at least one literal fact
    # citation there. This does not prove that every eligible fact was found.
    for d in decisions:
        if d['disposition'] == 'extracted':
            if not any(e.get('source_section') == d['segment_id'] and e.get('quote') for e in fact_evidence):
                raise ValueError('Extracted coverage decision has no citation in ' + d['segment_id'])
    decisions = checked['cell_decisions']
    ids = [r['cell_id'] for r in decisions]
    by_id = {c['cell_id']: c for c in cells}
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise ValueError('Every focus value cell needs exactly one coverage decision')
    items = checked['extraction'].get('items', [])
    associations = {}
    for d in decisions:
        if d['disposition'] == 'extracted':
            for index in d['item_indices']:
                associations.setdefault(index, set()).add(d['cell_id'])
    def companion(cell, item):
        # A unit or label column the item reads from its row, not a second value.
        core = cell_core(cell['raw_text']).replace(' ', '').casefold()
        unit = (item.get('unit') or '').replace(' ', '').casefold()
        return bool(core) and (core == unit or not any(ch.isdigit() for ch in core)
                               and not cell_item_correspondence(cell, item)[0])
    linkage_audit, companion_audit = [], []
    for d in decisions:
        if len(d['item_indices']) != len(set(d['item_indices'])):
            raise ValueError('Duplicate cell item index')
        if d['disposition'] != 'extracted':
            if d['item_indices']:
                raise ValueError('Unextracted cell cannot claim extracted items')
            continue
        if not d['item_indices']:
            raise ValueError('Extracted cell requires at least one item index')
        cell = by_id[d['cell_id']]
        issues = []
        for index in d['item_indices']:
            if not 0 <= index < len(items):
                raise ValueError('Unknown cell item index')
            item = items[index]
            if not any(e.get('source_section') == cell['segment_id'] and cell['raw_text'] in e.get('quote','')
                       for e in item.get('evidence', [])):
                raise ValueError('Cell extraction lacks literal evidence for its source row and value')
            matched, reason = cell_item_correspondence(cell, item)
            if len(associations[index]) > 1:
                claimed = [by_id[c] for c in sorted(associations[index])]
                values = [c for c in claimed if not companion(c, item)]
                if len(values) == 1 and cell_item_correspondence(values[0], item)[0]:
                    if values[0] is not cell:
                        matched, reason = True, 'unit_or_label_companion_of_matched_value_cell'
                        companion_audit.append({'cell': copy.deepcopy(cell), 'item_index': index,
                                                'value_cell_id': values[0]['cell_id'], 'reason': reason})
                else:
                    matched, reason = False, 'one_item_claimed_for_multiple_value_cells'
            if not matched:
                issues.append({'item_index': index, 'reason': reason,
                    'model_fields': {k: copy.deepcopy(item.get(k)) for k in ('text_value', 'numeric_value', 'comparator', 'unit')}})
        if issues and all(i['reason'] == 'missing_cell_has_no_extractable_result_value'
                          and valueless(items[i['item_index']]) for i in issues):
            # A blank/dash cell paired with a valueless item asserts no result.
            # Record that explicitly instead of leaving coverage unresolved.
            linkage_audit.append({'cell': copy.deepcopy(cell), 'original_decision': copy.deepcopy(d),
                'issues': issues, 'status': 'missing_cell_reclassified', 'clinical_entailment_verified': False,
                'measurement_fields_changed': False})
            d.update(disposition='no_patient_fact', item_indices=[],
                reason='Deterministic: missing-cell token carries no result value')
            continue
        if issues:
            linkage_audit.append({'cell': copy.deepcopy(cell), 'original_decision': copy.deepcopy(d),
                'issues': issues, 'status': 'unresolved', 'clinical_entailment_verified': False,
                'measurement_fields_changed': False})
            d.update(disposition='unresolved', item_indices=[],
                reason='Deterministic cell correspondence unresolved: ' + '; '.join(i['reason'] for i in issues))
    if linkage_audit:
        checked['cell_linkage_audit'] = linkage_audit
    if companion_audit:
        checked['cell_companion_audit'] = companion_audit
    return checked


FACT_ERROR = re.compile(r'^/(items|tumors|biomarkers|treatments)/(\d+)(/\S*)?: ')


def _drop_facts(env, key, drop, quarantine, reasons):
    facts = env['extraction'].get(key, [])
    keep = [i for i in range(len(facts)) if i not in drop]
    remap = {old: new for new, old in enumerate(keep)}
    quarantine.extend({'kind': 'salvage_dropped_fact', 'path': f'/{key}/{i}', 'candidate': copy.deepcopy(facts[i]),
                       'errors': reasons.get(i, []), 'clinical_entailment_verified': False} for i in sorted(drop))
    env['extraction'][key] = [facts[i] for i in keep]
    scopes = []
    for s in env['fact_scopes']:
        match = re.fullmatch(rf'/{key}/(\d+)', str(s.get('path')))
        if not match:
            scopes.append(s)
        elif int(match.group(1)) in remap:
            scopes.append({**s, 'path': f'/{key}/{remap[int(match.group(1))]}'})
    env['fact_scopes'] = scopes
    if key == 'items':
        for d in env['cell_decisions']:
            kept = [remap[i] for i in d['item_indices'] if i in remap]
            if d['disposition'] == 'extracted' and len(kept) != len(d['item_indices']):
                d.update(disposition='unresolved', item_indices=[],
                         reason='Salvage: a linked item failed validation after bounded repair')
            else:
                d['item_indices'] = kept


def _sanitize_decisions(env, focus, cells):
    decisions, seen = [], set()
    for d in env['source_decisions']:
        if d['segment_id'] in focus and d['segment_id'] not in seen:
            seen.add(d['segment_id']); decisions.append(d)
    decisions += [{'segment_id': s, 'disposition': 'unresolved', 'reason': 'Salvage: no coverage decision returned'}
                  for s in sorted(set(focus) - seen)]
    env['source_decisions'] = decisions
    paths = fact_paths(env['extraction'])
    scopes, seen = [], set()
    for s in env['fact_scopes']:
        if s['path'] in paths and s['path'] not in seen:
            seen.add(s['path']); scopes.append(s)
    scopes += [{'path': p, 'scope': 'uncertain', 'reason': 'Salvage: no attribution scope returned'}
               for p in paths if p not in seen]
    env['fact_scopes'] = scopes
    by_id = {c['cell_id']: c for c in cells}
    items = env['extraction'].get('items', [])
    out, seen = [], set()
    for d in env['cell_decisions']:
        if d['cell_id'] not in by_id or d['cell_id'] in seen:
            continue
        seen.add(d['cell_id'])
        cell = by_id[d['cell_id']]
        indices = d['item_indices']
        literal = all(0 <= i < len(items) and any(
            e.get('source_section') == cell['segment_id'] and cell['raw_text'] in e.get('quote', '')
            for e in items[i].get('evidence', [])) for i in indices)
        if d['disposition'] != 'extracted':
            d['item_indices'] = []
        elif not indices or len(set(indices)) != len(indices) or not literal:
            d.update(disposition='unresolved', item_indices=[],
                     reason='Salvage: cell linkage failed validation after bounded repair')
        out.append(d)
    out += [{'cell_id': c, 'disposition': 'unresolved', 'item_indices': [],
             'reason': 'Salvage: no cell decision returned'} for c in by_id if c not in seen]
    env['cell_decisions'] = out


def salvage_envelope(value, task, checker, focus, cells=(), rounds=16):
    """Last resort after the repair rounds: keep every fact that passes the same gate.

    A fact failing only the strict time gate keeps the fact without its time. An
    unverifiable quote is removed when the fact has other evidence. Other failing
    facts, their scopes and cell links go to quarantine with the remaining facts
    re-indexed. An "extracted" claim no surviving fact cites becomes unresolved.
    Nothing is generated. The caller re-checks the result before accepting it.
    """
    from pydantic import ValidationError
    from .targeted_repair import TIME_RULES, quarantine_time
    env, quarantine = copy.deepcopy(value), []
    for _ in range(rounds):
        try:
            env = envelope_model(task).model_validate(env).model_dump()
            break
        except ValidationError as exc:
            # Schema-invalid facts (e.g. a result with no value and no absence reason) are dropped.
            failed = {}
            for error in exc.errors():
                loc = error.get('loc', ())
                if not (len(loc) >= 3 and loc[0] == 'extraction' and loc[1] in ('items', 'tumors', 'biomarkers', 'treatments')
                        and isinstance(loc[2], int)):
                    raise
                failed.setdefault(loc[1], {}).setdefault(loc[2], []).append(error.get('msg', ''))
            for key, reasons in failed.items():
                _drop_facts(env, key, set(reasons), quarantine, reasons)
    for _ in range(rounds):
        try:
            check_envelope(copy.deepcopy(env), task, checker, focus, cells)
            return env, quarantine
        except (ValueError, TypeError, KeyError) as exc:
            message = str(exc)
        if message.startswith('Extracted coverage decision has no citation in '):
            # Whole-source windows can claim many uncited segments; resolve them all at once.
            cited = {e.get('source_section') for fact in fact_paths(env['extraction']).values()
                     for e in fact.get('evidence', []) if e.get('quote')}
            for d in env['source_decisions']:
                if d['disposition'] == 'extracted' and d['segment_id'] not in cited:
                    d.update(disposition='unresolved',
                             reason='Salvage: no validated fact cites this segment after bounded repair')
                    quarantine.append({'kind': 'salvage_coverage_unresolved', 'segment_id': d['segment_id'],
                                       'errors': [message]})
            continue
        if message.startswith('Extracted fact needs a focus-support citation: '):
            key, index = message.rsplit(' ', 1)[-1].strip('/').split('/')
            _drop_facts(env, key, {int(index)}, quarantine, {int(index): [message]})
            continue
        if message.startswith(('Every focus segment', 'Every extracted fact', 'Every focus value cell',
                               'Duplicate cell', 'Unknown cell', 'Extracted cell', 'Unextracted cell',
                               'Cell extraction lacks')):
            _sanitize_decisions(env, focus, cells)
            quarantine.append({'kind': 'salvage_decisions_normalized', 'errors': [message]})
            continue
        errors = [e for e in re.split(r'; (?=/)', message) if e]
        parsed = [FACT_ERROR.match(e) for e in errors]
        if not errors or not all(parsed):
            raise ValueError('Unsalvageable clinical window: ' + message[:500])
        by_fact = {}
        for error, match in zip(errors, parsed):
            by_fact.setdefault((match.group(1), int(match.group(2))), []).append((match.group(3) or '', error))
        drops = {}
        for (key, index), found in by_fact.items():
            fact = env['extraction'][key][index]
            if all(sub.startswith('/time') or any(r in e for r in TIME_RULES) for sub, e in found):
                fact.update(quarantine_time(fact))
                quarantine.append({'kind': 'salvage_time_cleared', 'path': f'/{key}/{index}',
                                   'errors': [e for _, e in found], 'clinical_entailment_verified': False})
                continue
            bad = {int(m.group(1)) for sub, _ in found for m in [re.match(r'/evidence/(\d+)', sub)] if m}
            if bad and all(re.match(r'/evidence/\d+', sub) for sub, _ in found) and len(bad) < len(fact.get('evidence', [])):
                fact['evidence'] = [e for i, e in enumerate(fact['evidence']) if i not in bad]
                quarantine.append({'kind': 'salvage_evidence_removed', 'path': f'/{key}/{index}',
                                   'errors': [e for _, e in found], 'clinical_entailment_verified': False})
                continue
            drops.setdefault(key, {})[index] = [e for _, e in found]
        for key, failed in drops.items():
            _drop_facts(env, key, set(failed), quarantine, failed)
    raise ValueError('Clinical window salvage did not converge')


def patient_only(envelope):
    data = copy.deepcopy(envelope['extraction'])
    scopes = {r['path']: r for r in envelope['fact_scopes']}
    quarantine = [{'candidate': copy.deepcopy(v), **scopes[p], 'clinical_entailment_verified': False}
                  for p, v in fact_paths(data).items() if scopes[p]['scope'] != 'direct_patient']
    if '/' in scopes and scopes['/']['scope'] != 'direct_patient':
        return None, quarantine
    for key in ('items', 'tumors', 'biomarkers', 'treatments'):
        if key in data:
            data[key] = [v for i, v in enumerate(data[key]) if scopes[f'/{key}/{i}']['scope'] == 'direct_patient']
    has_facts = bool(fact_paths(data))
    if has_facts:
        data['documentation_status'] = 'documented'
    elif data['documentation_status'] == 'documented':
        data.update(documentation_status='not_documented', documentation_evidence=[])
    if quarantine:
        data['limitations'].append('Non-direct patient candidates retained separately in attribution quarantine.')
    return data, quarantine


def merge(task, leaves, checker):
    """Union exact facts. Scalar disagreements stay partial; never last-write-wins."""
    parts, part_cells, quarantine, errors = [], [], [], []
    for leaf in leaves:
        if leaf.get('salvaged') and leaf.get('data') is not None:
            # Salvaged after bounded repair: accepted facts passed the same gate;
            # dropped ones stay in the coverage audit and the section stays partial.
            errors.append('salvaged_source_window:' + str(leaf['identity']['source_batch']))
        elif leaf['status'] != 'valid':
            errors.append('failed_source_window:' + str(leaf['identity']['source_batch']))
            continue
        part, excluded = patient_only(leaf['data']); quarantine.extend(excluded)
        if part is not None:
            parts.append(part)
            scopes = {s['path']: s['scope'] for s in leaf['data']['fact_scopes']}
            direct_indices = [i for i in range(len(leaf['data']['extraction'].get('items', [])))
                              if scopes.get(f'/items/{i}') == 'direct_patient']
            part_cells.append({new: sorted(d['cell_id'] for d in leaf['data'].get('cell_decisions', [])
                if d['disposition'] == 'extracted' and old in d['item_indices'])
                for new, old in enumerate(direct_indices)})
        if any(d['disposition'] == 'unresolved' for d in leaf['data']['source_decisions']):
            errors.append('unresolved_source_coverage:' + str(leaf['identity']['source_batch']))
        if any(d['disposition'] == 'unresolved' for d in leaf['data'].get('cell_decisions', [])):
            errors.append('unresolved_cell_coverage:' + str(leaf['identity']['source_batch']))
        if any(d['scope'] == 'uncertain' for d in leaf['data']['fact_scopes']):
            errors.append('unresolved_patient_attribution:' + str(leaf['identity']['source_batch']))
    if not parts:
        return None, quarantine, errors or ['no_valid_patient_section']
    result = copy.deepcopy(parts[0])
    for key in ('items', 'tumors', 'biomarkers', 'treatments', 'documentation_evidence', 'limitations', 'evidence'):
        if key in result:
            # Equal values in different table columns are distinct occurrences,
            # even when their timing remains unknown and their full-row quote
            # is identical. Deduplication must retain that cell identity.
            result[key] = list({json.dumps([v, cells.get(i, [])] if key == 'items' else v, sort_keys=True): v
                for p, cells in zip(parts, part_cells) for i, v in enumerate(p.get(key, []))}.values())
    excluded_keys = {'items', 'tumors', 'biomarkers', 'treatments', 'documentation_evidence',
                     'limitations', 'evidence', 'coverage', 'documentation_status'}
    for key in result.keys() - excluded_keys:
        values = [p[key] for p in parts if p.get(key) is not None and p.get(key) != 'unknown']
        if len({json.dumps(v, sort_keys=True) for v in values}) > 1:
            # Conflicting scalar case context cannot be accepted as a patient fact.
            return None, quarantine, errors + ['conflicting_window_field:' + key]
        result[key] = values[0] if values else result[key]
    if fact_paths(result):
        result['documentation_status'] = 'documented'
    elif all(p['documentation_status'] == 'not_applicable' for p in parts):
        result['documentation_status'] = 'not_applicable'
    elif any(p['documentation_status'] == 'explicitly_unknown' for p in parts):
        result['documentation_status'] = 'explicitly_unknown'
    else:
        result.update(documentation_status='not_documented', documentation_evidence=[])
    result['coverage'] = 'limited' if errors or any(p['coverage'] == 'limited' for p in parts) else 'complete'
    if result['coverage'] == 'limited':
        result['limitations'].append('Some source windows or coverage decisions remain unresolved; see coverage audit.')
    try:
        return checker(result), quarantine, errors
    except (ValueError, TypeError, KeyError) as exc:
        return None, quarantine, errors + ['assembled_clinical_section_invalid:' + str(exc)]


async def extract(runner, task, packet, article, patient, identity, replica):
    full_segments = packet_segments(packet)
    available = {s['segment_id'] for s in full_segments}
    segments = [s for s in article['segments'] if s['segment_id'] in available]
    call_task = 'clinical_window_' + task
    runner.schemas[call_task] = envelope_model(task).model_json_schema()
    leaves = []
    from .ehr_tasks import series_draft
    cells = series_draft(article, [])['cells'] if task == 'observations' else []

    async def run_batch(number, batch, whole=False):
        focus = {s['segment_id'] for s in batch}
        view = article if whole else source_window(article, focus, patient)
        # Original table headers preserve column/unit/time meaning; a header
        # must not become a patient's measurement merely because it is visible.
        table_ids = {s.get('table_id') for s in batch if s.get('kind') == 'table_row'}
        wanted = {s['segment_id'] for s in view['segments']} | {
            s['segment_id'] for s in article['segments'] if s.get('kind') == 'table_caption'
            or s.get('kind') in {'table_header', 'table_footnote'} and s.get('table_id') in table_ids}
        wanted &= available
        local_packet = packet if whole else subset_packet(packet, article, wanted)
        local_segments = packet_segments(local_packet)
        focus_cells = [c for c in cells if c['role'] == 'value' and c.get('segment_id') in focus]
        messages = runner.clinical_messages(task, local_packet)
        messages[-1]['content'] = messages[-1]['content'].split('\nReturn only JSON matching SCHEMA:')[0]
        messages[-1]['content'] += (
            '\nWINDOW CONTRACT: Return {extraction, source_decisions, fact_scopes, cell_decisions} matching the final schema. '
            'extraction has the usual task schema. Only emit facts directly supported in FOCUS_SEGMENTS; '
            'other supplied blocks are identity/header/context. Review every focus block, every named analyte '
            'and each measurement/time column, not just the first rows. coverage refers only to this window. '
            'For EACH focus segment report extracted, no_patient_fact with a reason, or unresolved. '
            'For EACH item (/items/0 etc.; oncology uses /tumors/N, /biomarkers/N, /treatments/N; '
            'documented case_context uses /), report its attribution scope. Never assign cohort averages, '
            'protocols, generic reference ranges or secondary cases to the index patient. Even universal '
            'cohort statements are universal_cohort, not direct_patient. Unknown individual linkage is uncertain. '
            'Missing timestamps never justify dropping a measurement; retain time unknown. '
            'Only direct_patient facts enter the patient record; all others remain in the audit. '
            'For every FOCUS_VALUE_CELL, give a cell_decision with the zero-based extraction.items indices '
            'covering that value, or explicitly no_patient_fact/unresolved with empty item_indices and a reason. '
            'An extracted cell needs an item citation containing that literal value in its source row. '
            'Each item also needs a focus-segment citation; identity/header/neighbor context alone cannot emit a fact. '
            'An extracted cell must correspond to the actual item text_value/numeric_value and comparator, '
            'not merely appear somewhere in a long row quotation. Preserve literal result notation and never '
            'convert units. Different time/value cells need distinct item indices even when their values match. '
            'Use unresolved when the value-to-item correspondence cannot be verified. '
            'Missing cells/dashes are not zeros: mark a blank/dash cell no_patient_fact unless a legend defines it. '
            'A unit or label cell may share the item index of the one value cell it qualifies. '
            'If no focus cells, cell_decisions=[]. '
            '\nFOCUS_SEGMENTS:\n' + json.dumps(sorted(focus)) +
            '\nFOCUS_VALUE_CELLS:\n' + json.dumps([{k:c[k] for k in ('cell_id','segment_id','column_index','raw_text')} for c in focus_cells]) +
            '\nSCHEMA:\n' + json.dumps(runner.schemas[call_task]))
        async def split():
            mid = len(batch)//2
            return await run_batch(number+'.0', batch[:mid]) + await run_batch(number+'.1', batch[mid:])
        if len(batch) > 1 and not await fits(runner, call_task, messages, replica):
            return await split()
        checker = runner.clinical_checker(task, local_packet, local_segments)
        # run-20261101-215258: conditions windows lost every fact when repair rounds
        # oscillated between a few bad items and a coverage claim; salvage keeps the rest.
        result = await runner.call(call_task, messages,
            lambda v: check_envelope(v, task, checker, focus, focus_cells),
            {**identity, 'source_batch': number, 'focus_segment_ids': sorted(focus),
             'included_segment_ids': sorted(wanted)}, replica, local_segments,
            split_on_length=len(batch)>1,
            partial_builder=lambda v: salvage_envelope(v, task, checker, focus, focus_cells))
        # Windows have no item-repair packet, so a checked partial can only come from salvage.
        result['salvaged'] = result.get('status') == 'partial' and result.get('data') is not None
        # One extra subdivision for source-validation failures; never retry transport
        # errors this way and never accept the failed parent as a valid leaf.
        validation_split = (getattr(getattr(runner, 'config', None), 'clinical_validation_split', False)
            and '.' not in number and result.get('status') != 'valid'
            and any(marker in json.dumps(result.get('errors', [])) for marker in
                    ('nonliteral', 'evidence must quote', 'temporal expression',
                     'repair_refused_field_erasure', 'targeted_items_unresolved')))
        if len(batch)>1 and (splittable_failure(result) or validation_split):
            replaced(runner, result)
            return await split()
        return [result]

    if task == 'observations':
        groups = partition(segments, table_rows=getattr(runner.config, 'clinical_table_rows_per_window', 4))
        leaves = [r for group in await asyncio.gather(*(run_batch(str(i), batch) for i,batch in enumerate(groups))) for r in group]
    else:
        leaves = await run_batch('0', segments, whole=True)
    data, quarantine, errors = merge(task, leaves, runner.clinical_checker(task, packet, full_segments))
    covered = {sid for r in leaves for sid in r['identity']['focus_segment_ids']}
    accepted = [r for r in leaves if r['status'] == 'valid' or r.get('salvaged')]
    if covered != available:
        errors.append('source_window_coverage_incomplete')
    audit = {'policy': 'clinical-source-windows/1', 'task': task, 'identity': identity,
             'source_text_sha256': article['text_sha256'], 'all_segments_attempted': covered == available,
             'all_windows_valid': all(r['status']=='valid' for r in leaves),
             'salvage': [q for r in leaves if r.get('salvaged') for q in r.get('quarantine') or []],
             'semantic_coverage_verified': False, 'attribution_quarantine': quarantine,
             'source_decisions': [d for r in accepted for d in r['data']['source_decisions']],
             'cell_decisions': [d for r in accepted for d in r['data']['cell_decisions']],
             'cell_linkage_audit': [d for r in accepted for d in r['data'].get('cell_linkage_audit', [])],
             'cell_companion_audit': [d for r in accepted for d in r['data'].get('cell_companion_audit', [])],
             'batches': [{k:r[k] for k in ('identity','status','errors')} for r in leaves]}
    key = json_digest([identity, task, 'assembled-clinical-windows'])
    result = {'task': task, 'task_key': key, 'identity': identity, 'arm': runner.arm, 'replica': replica,
              'status': 'valid' if data is not None and not errors else 'partial' if data is not None else 'failed',
              'data': data, 'errors': errors, 'attempts': [v for r in leaves for v in r['attempts']],
              'quarantine': quarantine, 'coverage_audit': audit, 'clinical_accuracy_verified': False}
    runner.results.append(result)
    write_json(runner.output/'tasks'/(key+'.json'), result)
    write_json(runner.output/'coverage'/(identity['record_id'].replace(':','-')+'-'+task+'.json'), audit)
    return result
