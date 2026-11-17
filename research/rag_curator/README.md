# Curated metadata standards (data snapshot)

This directory contains the curated metadata tables and FAIRsharing extraction
outputs that the downstream experiments consume. It is a **data snapshot**, not
a runnable package: the crawler/extraction code is maintained in a separate
internal repository and is not part of this public snapshot.

## Why it is here

`field_recovery_eval` and `metadata_completeness_eval` use these tables as
ground truth:

```
research/rag_curator/tmp_res/approved_tables/*.json
```

The path is wired in
`research/experiments/knn_evaluation/field_recovery_eval/config.py` and
`.../metadata_completeness_eval/config.py` (`APPROVED_TABLES_DIR`). Do not move
this directory without updating both configs.

## Contents

| Path | What it is |
|---|---|
| `tmp_res/approved_tables/` | 18 expert-approved metadata tables (one JSON per standard/checklist pair), the ground truth for field-recovery recall. |
| `tmp_res/<standard>/` | Per-standard working tables and intermediate curation artifacts. |
| `outputs/standards_extraction/` | 85 FAIRsharing records extracted into structured JSON (`result.json`, `materials_trace.json`). |
| `outputs/*.jsonl` | Crawl and extraction logs. |
| `outputs/standards_extraction_summary.json` | Run-level extraction summary. |
| `cache/index.json` | Index of fetched sources. |

An approved table has the shape
`{"source_record_dir", "standard_id", "tentative", "standard": {...fields...}}`.
The `standard.fields` list is the ground truth used by the recall judge.

## Licensing

The metadata standards themselves (MIxS, REMBI, LINCS, ISA-Tab, etc.) remain
under their original licences and are referenced here for research
reproducibility. The extracted JSON is provided as experiment input.
