# Dataset builder

Turns open-access PubMed Central case reports into HL7 FHIR R4 patient records in which every
clinical fact cites the sentence or table cell it came from. An LLM reads; deterministic code
checks every answer against the source and compiles the FHIR.

Defaults: **Reflection Beam 1.0** (501B-A23B, NVFP4) with **DFlash2** speculative decoding on vLLM,
one server per 4 GPUs (B200 or B300), and the 30 articles in `configs/articles/diverse30.yaml`. Any
model served by vLLM works: edit `serving` and `extraction` in `configs/beam.yaml`.

## Pipeline

```
 PMC article ID (PMC12345678.1)
      │ prepare: license check (CC BY, CC0, BY-SA) → JATS XML → numbered segments and table cells
      ▼
 source packet ─────────────────────────────────────────────────────────────┐
      │ run: every step is LLM call → strict validator → bounded repair      │
      ▼                                                                      │
  1 patient roster        who the article describes; cited cases kept apart  │  every fact
  2 clinical facts        14 sections over source windows, quoted evidence   │  cites its
  3 measurement series    tables read cell by cell                           │  segment or
  4 timeline, summary     relative events and before/after/during relations  │  table cell
      ▼                                                                      │
 extraction record (one per article) ◄───────────────────────────────────────┘
      │ 5 ICD-10-CM: up to 8 candidates from the FY2027 tabular + index → LLM selects or abstains
      │ 6 FHIR: deterministic compiler → R4 schema check → official HL7 validator → bounded repair
      ▼
 one FHIR Bundle per patient (uncoded, and with model-selected codes)
      │ export
      ▼
 Hugging Face dataset folder: data/{uncoded,coded,extraction}.jsonl + dataset card
```

Extraction is text-only: tables and figure captions are read; figure images are not. Each
`extraction` row lists its figures with captions and public PubMed Central image links.

## Quick start

```bash
uv sync
uv run ehr-dataset prepare --config configs/beam.yaml --articles configs/articles/diverse30.yaml --run runs/diverse30
uv run --extra weights ehr-dataset weights --config configs/beam.yaml --dest weights
uv run ehr-dataset serve --config configs/beam.yaml --weights weights --gpus 0,1,2,3 --port 8000 &
uv run ehr-dataset run --run runs/diverse30 --endpoint http://127.0.0.1:8000/v1
uv run ehr-dataset export --run runs/diverse30 --out hf-dataset
```

Pass `--endpoint` once per server, and `--per-endpoint N` to let each server work on N articles at
once (the release used 3). `run` resumes: finished articles are skipped. `ehr-dataset stats` adds
the run record and the dataset's token count to the card. Java is needed for the HL7 validator
(`--no-official-validator` skips it). To publish the folder, run
`hf upload <user>/beam-synthetic-ehr hf-dataset . --repo-type dataset` (`pip install -U huggingface_hub`).

- Modal: `runners/modal_app.py` (one server per container with 4× B200, or 4× B300 when no B200s
  are free). The released dataset was built this way; see the
  [main README](../README.md#how-the-released-dataset-was-built) for the configuration.
- Slurm (HiPerGator): `runners/hipergator/run.sbatch`

## Outputs

`runs/<run>/articles/<article>/` keeps every prompt, response, reasoning trace and validator
result (`extraction/`, `ehr/`, `fhir/packet/`), the extraction record (`ehr/data/unified.jsonl`),
the bundles (`fhir/uncoded/`, `fhir/experimental-coded/`) and a `receipt.json`.

## Code map

| Stage | Modules |
|---|---|
| CLI, run folder, serving | `cli`, `pipeline`, `run_files`, `serving`, `export` |
| Sources | `acquire`, `corpus`, `literature_client`, `articles`, `license_policy`, `jats_links`, `pmc_media`, `glued_text`, `source_views`, `provenance` |
| Model calls | `client`, `config`, `output_parser`, `prompts` (+ `prompts/`), `prompt_payloads`, `schemas`, `annotation_rules` (+ `rules/`) |
| Extraction | `pilot_extract` (task runner), `article_tasks`, `patient_context`, `bounded_roster`, `bounded_clinical`, `clinical_normalization`, `extraction_contracts`, `evidence_recovery`, `evidence_ledger`, `episode_ledger`, `targeted_repair`, `pilot_review`, `semantic_rules`, `validation`, `measurements`, `longitudinal`, `staged_timeline`, `sparse_timeline`, `overnight_repairs`, `reasoning_lineage`, `gepa_feedback` |
| Extraction record | `ehr_pipeline`, `ehr_tasks`, `measurement_series`, `bounded_series`, `unified_record`, `unified_record_flags`, `figure_attribution`, `figure_ehr`, `figure_privacy`, `figure_visuals`, `pilot_media`, `supplement_manifest`, `supplement_peek`, `dense_store` |
| Coding and FHIR | `terminology` (+ `terminology/`), `fhir_campaign`, `fhir_pipeline`, `fhir_export`, `fhir_measurements`, `fhir_validation`, `fhir_repair`, `fhir_campaign_repair` |

## Limits

Records are model output checked against the source, not clinically reviewed. Model-selected
codes are research normalization. Times stay relative to the case; nothing is invented.
