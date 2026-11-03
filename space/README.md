---
title: Beam Synthetic EHR
emoji: 📄
colorFrom: gray
colorTo: gray
sdk: static
app_file: index.html
pinned: false
short_description: Case reports to FHIR R4, every fact traced to its sentence
---

# Beam Synthetic EHR

A static site with two views of the `beam-synthetic-ehr` dataset (extraction by Reflection Beam):

- **Articles**: each case report beside the facts extracted from it, tables drawn as printed.
  Selecting a fact marks the words or table cells it came from and shows Beam's reason for
  keeping it. *How it works* follows one article through extraction, ICD-10-CM coding and FHIR.
- **Records**: each patient's FHIR R4 bundle, explained: what the bundle holds, every resource in
  the order the article tells the case beside the passage it was compiled from, and each resource
  field by field, with its JSON one click away. From the Records list you can build a cohort by
  condition or ICD-10-CM code, age and sex, and download its bundles as NDJSON.

Both views also open files dropped onto the page: FHIR R4 bundles or resources (JSON or NDJSON),
dataset rows, or an extraction record with its source packet. Files are read in the browser and not uploaded.

## How Beam was used

Reflection Beam 1.0 (NVFP4, with DFlash2 speculative decoding, served by vLLM on Modal) read all 30
case reports in 3,826 calls. It found the patients each article describes, extracted facts in 14
sections with quoted evidence, read the tables cell by cell, ordered each patient's timeline, wrote
the case summaries and chose ICD-10-CM codes. Code checked every answer against the article and
compiled the FHIR. On the site, each fact shows Beam's stated reason for keeping it and, for nearly
all facts, an excerpt of its reasoning.

## Build

```bash
python scripts/build_data.py --run ../dataset/runs/diverse30 --dataset ../dataset/hf-dataset
npm install
npm run dev      # http://localhost:5173
npm run build    # static site in dist/
```

`build_data.py` writes `public/data` (2.6 MB, committed), so the site builds without the run folder.

## Deploy

Create a static Hugging Face Space, then upload the built site with this README
(`pip install -U huggingface_hub` for the `hf` command):

```bash
npm run build && cp README.md dist/
hf upload <user>/beam-synthetic-ehr dist . --repo-type space
```
