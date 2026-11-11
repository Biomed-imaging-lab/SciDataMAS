# SciDataMAS — research code, demos and experiments

This is the research half of the repository: the multi-agent system (MAS) that
generates and validates scientific metadata, the demos that exercise it, and
the experiment harness behind the 2026 metadata-curation paper.

> Part of the [SciDataMAS umbrella repository](../README.md). The DeepSeek
> Harness plugin lives in [`../plugin/`](../plugin/).

## What is here

| Path | Contents |
|---|---|
| `src/` | MAS implementation: LangGraph workflows for dataset creation, data insertion, retrieval and orchestration; storage drivers (local, ClearML, NAS); Streamlit GUI. |
| `demos/` | End-to-end notebooks for the local data lake, ClearML, dataset creation, ingestion, retrieval and orchestration. |
| `experiments/` | The metadata-curation experiments: generators, prompts, judges, debate probing, notebooks and outputs. See [`experiments/README.md`](experiments/README.md). |
| `rag_curator/` | Curated metadata standard tables and FAIRsharing extraction outputs used as experiment ground truth. See [`rag_curator/README.md`](rag_curator/README.md). |
| `requirements.txt` | Pinned Python environment for the MAS app. |

## Install and run the MAS

```bash
cd research
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp src/.env.example src/.env
# edit src/.env and add OPENAI_API_KEY / MISTRAL_API_KEY as needed

cd src
streamlit run main.py
```

`src/conf.json` chooses the model and the storage driver. The default is a
local data lake rooted at `research/` (`./../` from `src/`). To use ClearML,
switch `app_model_conf` to the `clearml` driver and fill the `CLEARML_*`
variables in `src/.env`.

## Demos

| Demo | What it shows |
|---|---|
| [local data lake](demos/local_demos/local_science_datalake_demo.ipynb) | create a lake, add files, retrieve them without an external service |
| [creating a dataset](demos/creating_dataset_demo.ipynb) | generate a metadata schema from a description and example files |
| [adding data](demos/adding_data_demo.ipynb) | stage a file, fill missing fields, commit |
| [getting data](demos/getting_data_demo.ipynb) | natural-language retrieval over the lake |
| [orchestration](demos/orch_deciding_check.ipynb) | how the MAS chooses tools and routes a request |
| [ClearML backend](demos/clearml_demos/clearml_science_datalake_demo.ipynb) | the same workflow with a ClearML-hosted lake (needs keys) |

## Reported results

From the AAAI-26 student abstract. Means and standard deviations over 16 runs
per configuration; models were called through their APIs.

### Creating metadata tables

| Model | Fields generated | Non-string fields | Tokens (10³) | Time (s) |
|---|---:|---:|---:|---:|
| GPT-4o | 18.8 ± 2.9 | 10.3 ± 2.4 | **4.3 ± 0.3** | **27.7 ± 6** |
| GPT-5-mini | **70.5 ± 18.6** | **39.8 ± 11** | 17 ± 1.1 | 151 ± 32 |
| Mistral | 44.8 ± 14.9 | 28.43 ± 10 | 10.8 ± 4 | 45 ± 16 |

### Automatic metadata filling during insertion

| Model | Fields generated | Non-string fields | Tokens (10³) | Time (s) |
|---|---:|---:|---:|---:|
| GPT-4o | **10.9 ± 1.9** | **1.1 ± 1.9** | **11.7 ± 2** | 34 ± 7.8 |
| GPT-5-mini | 10.3 ± 2 | 2.1 ± 2 | 17 ± 3 | 139 ± 111 |
| Mistral | 8.8 ± 1.8 | 3.5 ± 1.8 | 23 ± 7.8 | **30 ± 3.8** |

## Experiments

The experiment harness is independent of the Streamlit app and has its own
environment. Start with [`experiments/README.md`](experiments/README.md) for
the data flow, commands and the list of included/omitted artifacts.

## Secrets

Only `.env.example` files are tracked. Copy them to `.env` locally; `.env` is
ignored by git. Never commit API keys, ClearML credentials or FAIRsharing
credentials.

## Citation and licence

Cite the software via [`../CITATION.cff`](../CITATION.cff). Code is released
under the MIT licence ([`../LICENSE`](../LICENSE)); metadata standards bundled
under `rag_curator/` keep their original licences.
