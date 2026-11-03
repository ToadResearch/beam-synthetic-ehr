"""Pinned local terminology candidates; LLMs may select an ID or abstain.

Catalogs are supplied under their own licenses. We do not redistribute SNOMED,
LOINC or RxNorm releases, guess ICD codes, or treat a lexical match as reviewed.
"""
from difflib import SequenceMatcher
from functools import lru_cache, cached_property
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provenance import json_digest

SYSTEMS = {'http://hl7.org/fhir/sid/icd-10-cm', 'http://hl7.org/fhir/sid/icd-10',
           'http://snomed.info/sct', 'http://loinc.org', 'http://www.nlm.nih.gov/research/umls/rxnorm'}
SYSTEM_TASKS = {
    'http://hl7.org/fhir/sid/icd-10-cm': {'conditions', 'symptoms_function', 'oncology', 'family_genetics'},
    'http://hl7.org/fhir/sid/icd-10': {'conditions', 'symptoms_function', 'oncology', 'family_genetics'},
    'http://loinc.org': {'observations', 'demographics', 'symptoms_function', 'oncology', 'family_genetics'},
    'http://www.nlm.nih.gov/research/umls/rxnorm': {'medications', 'allergies', 'oncology'},
}

STOP_WORDS = {'a', 'an', 'and', 'or', 'of', 'the', 'with', 'without', 'in', 'to', 'due', 'other', 'unspecified'}
# ICD-10-CM conventions: parenthesized words are nonessential modifiers, and
# default qualifiers ("NOS", "site not specified", "unspecified organism") add
# no specificity. Neither may rank a candidate below a narrower one.
NEUTRAL_WORDS = {'nos', 'nec', 'not', 'elsewhere', 'classified', 'specified', 'site', 'organism',
                 'uncomplicated', 'complication'}


# Organ adjectives fold to the noun ICD-10-CM indexes under ("hepatic steatosis" ~
# "Steatosis, liver"); applied to queries and catalog alike, so exact matches stay.
ORGAN_WORDS = {'hepatic': 'liver', 'hepatocellular': 'liver', 'renal': 'kidney', 'nephric': 'kidney',
               'prostatic': 'prostate', 'pulmonary': 'lung', 'cardiac': 'heart', 'gastric': 'stomach',
               'cerebral': 'brain', 'corneal': 'cornea', 'cutaneous': 'skin', 'ocular': 'eye', 'osseous': 'bone',
               'colonic': 'colon', 'rectal': 'rectum', 'uterine': 'uterus', 'ovarian': 'ovary',
               'testicular': 'testis', 'splenic': 'spleen', 'pancreatic': 'pancreas', 'esophageal': 'esophagus',
               'duodenal': 'duodenum', 'intestinal': 'intestine', 'vertebral': 'vertebra', 'nasal': 'nose',
               'mammary': 'breast', 'pleural': 'pleura', 'pericardial': 'pericardium', 'peritoneal': 'peritoneum',
               'tracheal': 'trachea', 'bronchial': 'bronchus', 'laryngeal': 'larynx', 'pharyngeal': 'pharynx',
               'tonsillar': 'tonsil', 'vesical': 'bladder', 'thyroidal': 'thyroid', 'gingival': 'gingiva',
               'labial': 'lip', 'lingual': 'tongue', 'retinal': 'retina', 'aortic': 'aorta', 'venous': 'vein',
               'arterial': 'artery', 'bleeding': 'hemorrhage', 'stone': 'calculus'}


def stem(word):
    """Plural folding only ("veins" ~ "vein"); both query and catalog use it."""
    return word[:-1] if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')) else word


def words(text):
    return {ORGAN_WORDS.get(w, w) for w in map(stem, re.findall(r'[a-z0-9]+', text.casefold()))} - STOP_WORDS


def core_text(text):
    return ' '.join(re.sub(r'\([^()]*\)', ' ', text).split()).casefold()


def match_score(text, query, label):
    """Recall-weighted word F2 (covering the documented words matters most) plus string similarity."""
    core = core_text(label)
    matched = query & words(label)
    f2 = 0.0
    if matched:
        recall = len(matched) / len(query)
        precision = len(matched) / (len(matched) + len(words(core) - query - NEUTRAL_WORDS))
        f2 = 5 * precision * recall / (4 * precision + recall)
    return .75 * f2 + .25 * SequenceMatcher(None, text, core).ratio()


class Catalog(dict):
    """Cached retrieval metadata is an attribute, never part of frozen JSON."""
    @cached_property
    def digest(self):
        return json_digest(self)

    @cached_property
    def index(self):
        index = defaultdict(set)
        for i, c in enumerate(self['concepts']):
            for word in words(' '.join([c['display'], *c['aliases']])):
                index[word].add(i)
        return dict(index)


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    system: str
    version: str = Field(min_length=1)
    code: str = Field(min_length=1)
    display: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(min_length=1)
    context: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def system_known(self):
        from .schemas import TASK_MODELS
        if self.system not in SYSTEMS:
            raise ValueError('Use a supported canonical coding system URI')
        if set(self.tasks) - TASK_MODELS.keys():
            raise ValueError('Catalog tasks must use the extraction schema task names')
        if self.system in SYSTEM_TASKS and set(self.tasks) - SYSTEM_TASKS[self.system]:
            raise ValueError('Terminology system is inappropriate for the requested clinical task')
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['select', 'abstain']
    candidate_id: str | None
    relation: Literal['equivalent', 'broader'] | None
    rationale: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def consistent(self):
        if self.decision == 'select' and (not self.candidate_id or not self.relation):
            raise ValueError('Selection requires candidate_id and relation')
        if self.decision == 'abstain' and (self.candidate_id is not None or self.relation is not None):
            raise ValueError('Abstention cannot attach a code')
        return self


def load_catalog(path=None):
    if path is None:
        return Catalog(format='synthetic-ehr-terminology-catalog/1', source='none', license='none', concepts=[])
    path = Path(path).resolve()
    stat = path.stat()
    return _load_catalog(str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=2)
def _load_catalog(path, size, modified_ns):
    raw = Path(path).read_bytes()
    catalog = Catalog(json.loads(gzip.decompress(raw) if path.endswith('.gz') else raw))
    if catalog.get('format') != 'synthetic-ehr-terminology-catalog/1' or not catalog.get('source') or not catalog.get('license'):
        raise ValueError('Catalog requires format, source and license provenance')
    catalog['concepts'] = [Candidate.model_validate(c).model_dump() for c in catalog['concepts']]
    identities = [(c['system'], c['version'], c['code']) for c in catalog['concepts']]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate terminology concept in catalog')
    return catalog


def candidates(catalog, task, text, limit=8, system=None):
    text = text.casefold().strip()
    catalog = catalog if isinstance(catalog, Catalog) else Catalog(catalog)
    query = words(text)
    overlaps = defaultdict(float)
    # An inverted token shortlist avoids 75k SequenceMatcher calls per fact.
    # Missing/abbreviated vocabulary stays an explicit retrieval miss, not a guessed code.
    for token in query:
        postings = catalog.index.get(token, set())
        weight = math.log(1 + len(catalog['concepts']) / (1 + len(postings)))
        for i in postings:
            overlaps[i] += weight
    scored = []
    fallback = []
    # Among equal overlaps the shortest descriptions (the general codes) are shortlisted first.
    for i in sorted(overlaps, key=lambda i: (-overlaps[i], len(catalog['concepts'][i]['display']), i))[:512]:
        concept = catalog['concepts'][i]
        if task not in concept['tasks'] or system is not None and concept['system'] != system:
            continue
        score = max(match_score(text, query, t) for t in [concept['display'], *concept['aliases']])
        candidate = {**concept, 'candidate_id': json_digest(concept), 'retrieval_score': score}
        if score >= .45:
            scored.append(candidate)
        else:
            # Retrieval only: a distinctive literal overlap can expose longer
            # official descriptions. The model must still select or abstain.
            overlap = query & words(' '.join([concept['display'], *concept['aliases']]))
            distinctive = any(len(token) >= 4 and len(catalog.index.get(token, ())) <=
                              max(1, len(catalog['concepts']) * .01) for token in overlap)
            if distinctive and len(overlap) / max(1, len(query)) >= .5:
                fallback.append({**candidate, 'retrieval_method': 'distinctive-token-fallback'})
    if not scored:
        scored = fallback
    return sorted(scored, key=lambda c: (-c['retrieval_score'], c['candidate_id']))[:limit]


def validate_decision(request, value):
    decision = Decision.model_validate(value).model_dump()
    if decision['decision'] == 'select' and decision['candidate_id'] not in {c['candidate_id'] for c in request['candidates']}:
        raise ValueError('Terminology decision chose a code outside its pinned candidate set')
    return decision


def selected_coding(request, receipt, *, allow_unreviewed=False):
    if receipt is None:
        return None
    if receipt.get('request_sha256') != json_digest(request):
        raise ValueError('Terminology decision refers to a different fact/catalog/request')
    value = validate_decision(request, receipt['decision'])
    if value['decision'] == 'abstain' or value['relation'] != 'equivalent':
        return None  # broader classifications remain in audit, not equivalent codings
    if receipt.get('review_status') != 'approved' and not allow_unreviewed:
        return None
    if receipt.get('review_status') == 'approved' and not receipt.get('reviewer'):
        raise ValueError('Approved terminology decisions require reviewer attribution')
    candidate = next(c for c in request['candidates'] if c['candidate_id'] == value['candidate_id'])
    return {k: candidate[k] for k in ('system', 'version', 'code', 'display')}
