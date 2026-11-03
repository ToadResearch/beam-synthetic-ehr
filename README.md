# beam-synthetic-ehr

Synthetic electronic health records grounded in the published medical literature. Reflection Beam
reads open-access case reports; deterministic code checks every fact against its source sentence or
table cell and compiles each patient into an HL7 FHIR R4 bundle.

| Folder | What it is |
|---|---|
| [`dataset/`](dataset/) | The builder: case reports to source-grounded FHIR R4 records with Beam (any model served by vLLM works) and the Hugging Face export, published as [mkieffer/beam-synthetic-ehr](https://huggingface.co/datasets/mkieffer/beam-synthetic-ehr) |
| [`space/`](space/) | The [Hugging Face Space](https://huggingface.co/spaces/mkieffer/beam-synthetic-ehr): read each article beside the facts Beam extracted, browse the FHIR records, build a cohort, open your own files |

## How the released dataset was built

On [Modal](https://modal.com), with [`dataset/runners/modal_app.py`](dataset/runners/modal_app.py) and the
defaults in [`dataset/configs/beam.yaml`](dataset/configs/beam.yaml):

| Setting | Value |
|---|---|
| Model | [Reflection Beam 1.0 501B-A23B, NVFP4](https://huggingface.co/reflection/Beam-1.0-501B-A23B-NVFP4) |
| Speculative decoding | [DFlash2](https://huggingface.co/reflection/Beam-1.0-501B-A23B-DFlash2) draft model, 7 tokens |
| Serving | vLLM (pinned image), tensor parallel 4, FP8 KV cache, 128K context, up to 32 concurrent requests |
| Hardware | Three Modal containers, each with 4× NVIDIA B300 (B200s were unavailable) and one vLLM server working on up to 3 articles at a time |
| Sampling | Temperature 0.7, top-p 0.99, maximum reasoning effort |
| Articles | 30 CC BY PubMed Central case reports across 26 specialty families ([`diverse30.yaml`](dataset/configs/articles/diverse30.yaml)) |

```bash
cd dataset
modal deploy runners/modal_app.py
python -c "import modal; modal.Function.from_name('ehr-dataset', 'build').spawn(
    open('configs/articles/diverse30.yaml').read(), 'diverse30', False, 2, 3)"
```

## Run record (2–3 November 2026)

| | |
|---|---|
| Articles, patients | 30 articles, 39 patients; all 39 FHIR bundles passed the official HL7 validator |
| Wall clock | 2.1 h on the GPUs |
| GPU-hours | 14.3 on B300 (plus 9.5 on earlier attempts, which produced 2 of the 30 articles) |
| Model calls | 3,826 |
| Model tokens | 47.8M input, 39.1M output (30.5M of it reasoning), repairs included |
| Dataset | 108 rows, 138 MB, 74.5M tokens (Beam tokenizer) |
