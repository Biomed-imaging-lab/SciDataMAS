# Experiments: LLM-based metadata curation

This directory is the experiment harness behind

> **LLM-Based Metadata Curation for AI-Ready Science: Generation,
> Harmonization, and Debate-Driven Quality Estimation** (2026).

It covers the four tasks of the paper: metadata representation analysis,
generation from a free-text query, generation from papers/Zenodo records, and
schema harmonization. Everything is deterministic Python around LLM calls:
prompts, generators, judges and aggregation are plain files, so a run can be
audited and partially re-executed.

## Environment

Python **3.10** is recommended (the original runs used 3.10.12).

```bash
cd research/experiments
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# The experiment scripts load research/rag_curator/.env
cp ../rag_curator/.env.example ../rag_curator/.env
# edit ../rag_curator/.env and set OPENAI_API_KEY
```

The scripts use OpenAI chat + `text-embedding-3-large`; see each `config.py`
for the exact models, temperatures and thresholds. API usage is billed to your
key.

## Data

The two synthetic generation tables are shipped gzipped. Decompress them once:

```bash
cd knn_evaluation/data
python prepare_data.py
cd ..                      # back to knn_evaluation/
```

See [`knn_evaluation/data/README.md`](knn_evaluation/data/README.md) for
columns, checksums and provenance.

## Directory map

| Path | Role |
|---|---|
| `knn_evaluation/generators/` | `m1` single-call, `m2`, `m3` DAG, `m4` DSL-DAG and `m5` hard-DSL-DAG metadata generators. |
| `knn_evaluation/field_recovery_eval/` | Blind query synthesis → generation → recall judging → aggregation (stages 1–4). |
| `knn_evaluation/metadata_completeness_eval/` | Debate-style probing: reviewer questions, field scoring, gaps and completeness summaries. |
| `knn_evaluation/eval/` | Reusable judges and metrics: semantic comparison, self-repeatness, variability, clustering. |
| `knn_evaluation/ipynb_datagen/` | Notebooks and XLSX tables used to build/inspect the synthetic generation data. |
| `knn_evaluation/ipynb_publ_analysis/` | Publication analysis: per-task metrics, primary results table, clustering and node statistics. |
| `knn_evaluation/prompts/` | Generation and judge prompts (`md_generation/`, `llm_judges/`). |
| `knn_evaluation/queries/` | 16 biomedical queries, cross-domain and real-test query sets. |
| `knn_evaluation/data/` | `m1`/`m4` generation tables (gzipped). |
| `knn_evaluation/*.py` | Plotting and DAG/representation helpers (`plot_dendrogram*.py`, `scatter_blocks.py`, `dag_viz.py`, `tree_labeling.py`). |

## Reproduce the pipeline

Run from `research/experiments/knn_evaluation` unless noted.

```bash
cd field_recovery_eval

# 1. Synthesize blind experiment descriptions from approved metadata tables
python synthesize_queries.py

# 2. Generate m1 and m4 schemas for every (standard, query) cell
python run_generation.py

# 3. Judge directional field recall against the approved tables
python run_recall_eval.py

# 4. Aggregate per (model, generator) and per standard
python aggregate_results.py
```

Then the debate-based completeness experiment:

```bash
cd ../metadata_completeness_eval

# Probing sessions (defaults: all approved standards + m1/m4 bio targets)
python run_probing.py

# Aggregate records into per-target summaries
python aggregate.py
```

The publication tables and figures are in
`knn_evaluation/ipynb_publ_analysis/`; open the notebooks from that directory
so their relative paths resolve. The generation notebooks are in
`knn_evaluation/ipynb_datagen/`.

## What is included

| Artifact | Count / size |
|---|---|
| Generated schemas (`field_recovery_eval/outputs/generations/`) | 324 JSON files, ~14 MB |
| Blind queries (`field_recovery_eval/outputs/queries/`) | 18 JSON files |
| Recall cells (`field_recovery_eval/outputs/results.csv`) | one row per evaluated cell |
| Debate records (`metadata_completeness_eval/outputs/records/`) | 100 JSONL files |
| Per-target summaries (`metadata_completeness_eval/outputs/summary/`) | 50 JSON files |
| Approved ground-truth tables (`research/rag_curator/tmp_res/approved_tables/`) | 18 JSON tables |

## What is intentionally omitted

| Omitted | Why |
|---|---|
| `metadata_completeness_eval/cache/` (13,462 JSON files, ~513 MB) | Raw per-question LLM cache; regenerable by `run_probing.py` and not needed to inspect the published summaries. |
| `ipynb_sandbox/` | Exploratory copies of clustering notebooks; the canonical analysis is `ipynb_publ_analysis/`. |
| `.env` files, `__pycache__/`, `.pytest_cache/` | Secrets and machine-local caches. |
| The crawler source of `rag_curator/` | Maintained separately; the curated tables and extraction outputs needed by these experiments are included. |

## Caveats

- The notebooks contain historical relative paths such as
  `data/md_generations/...`. The canonical tables now live in
  `knn_evaluation/data/`; use `prepare_data.py` and adjust the path at the top
  of a notebook if you re-run it.
- The scripts are resumable at cell/session granularity: completed rows are
  skipped on re-run, so an interrupted API run can be continued.
- Model names in `config.py` are the ones used for the reported runs; change
  them deliberately and record the new configuration if you compare models.
