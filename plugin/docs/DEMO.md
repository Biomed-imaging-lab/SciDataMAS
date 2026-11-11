# Conference demo script

**English** · [Русский](DEMO.ru.md)

A 7-minute live demo of the SciDataMAS DSH plugin, plus a 3-minute fallback if the model is slow or the network is unreliable.

## Before the demo

- [ ] DSH Web starts with the **Data** panel visible; the lake is seeded with one draft dataset.
- [ ] The sample folder contains a few small files, so schema generation is fast.
- [ ] The model route is selected and responds; run `scidatamas_status`.
- [ ] A Zenodo record is open in a second tab (optional).
- [ ] The panel is already scrolled to the dataset you will show; do not rely on live refresh during the talk.
- [ ] Font size is readable from the back of the room.

Keep a second terminal with `dsh --profile web` ready. Do not run the demo on a lake containing confidential data.

## 7-minute script

### 0:00–0:40 — The problem

> A dataset is more than files. To reuse it six months later, a colleague needs preparation, acquisition parameters, units, provenance, and licensing. Usually that lives in a README, a notebook, and someone’s memory. SciDataMAS makes the metadata schema a first-class object in the agent session.

Show the **Data** panel with the seeded dataset.

### 0:40–2:00 — Create with evidence

Prompt:

> Create a dataset `demo_cells` from `demo-data/`. Description: confocal z-stacks of fixed cells, 40×, one stack per field. Purpose: segmentation. Use the compact schema and show me the fields.

While it runs, explain:

- the tool inspects images and tables, not just the prompt;
- the schema is normalized and gets reserved organizational fields;
- the dataset is a **draft**, not active.

Point at 2–3 generated fields and ask the audience: “Would you add a unit? Is this field reusable?”

### 2:00–3:30 — Debate validation

Prompt:

> Validate the schema with three debate runs and show the questions it cannot answer.

Explain the mechanics:

- each run invents a concrete experiment;
- reviewer roles do not see the schema; the owner does;
- fields that answer questions are useful; unanswered questions become clarifications;
- the schema is not changed automatically — the researcher decides.

Show coverage, useful fields, and one clarification. This is the conceptual core of the demo.

### 3:30–5:00 — Staged ingestion

Prompt:

> Add `demo-data/extra/` but do not commit. Note: 4% PFA, 40×/1.3 oil, pixel size 100 nm.

Show:

- the stage with proposed values;
- a missing required field (if the fixture has one);
- the fact that no files were copied.

Prompt:

> The missing fixation is “4% PFA for 15 min at RT”. Commit the stage with that value.

Show the active status and the event log. Emphasize: a wrong value is worse than a missing value.

### 5:00–6:00 — Retrieval

Prompt:

> Find all stacks with pixel size below 150 nm and show the file paths.

Explain:

- the planner selects a dataset and emits a JSON filter, not SQL;
- field names are validated before execution;
- the panel links to the actual artifacts.

### 6:00–7:00 — Panel and roadmap

Open the **Data** panel and switch to **Schema → Validation → Samples → Events** in a few seconds.

Close with the boundary:

> This is a research prototype. The panel is read-only today; writes go through agent tools with staging and audit. Storage is local-first; S3 and Synology are the next step along the same seam.

Mention the user-testing protocol and invite participants to try a task.

## 3-minute fallback

If the model is slow or offline:

1. Open a pre-created draft dataset in the panel.
2. Show **Schema** and explain single-call vs DAG fields.
3. Show **Validation** and read one clarification aloud.
4. Show **Samples** and **Events**.
5. Explain the staged-ingestion invariant with a screenshot or the stage JSON.
6. Open `docs/ARCHITECTURE.md` and show the diagram.

Do not apologize for the fallback; say explicitly that the live model is optional for the architectural story.

## Questions to expect

**Is this a database?**  
No. It is a file-based lake with a catalog, manifests, and JSONL metadata. A database or object store can replace the storage backend without changing the workflows.

**Does the model see my data?**  
It sees descriptions, file names, formats, sizes, image dimensions, table headers, and short text excerpts. Binary content is not sent as data.

**How do you know the metadata is correct?**  
You do not, automatically. The debate surfaces gaps; the researcher reviews the stage; every change is logged. The tool is designed to make review cheap, not to remove it.

**What about FAIR?**  
The schema and provenance fields support findability and reusability, but the prototype does not claim FAIR certification. Harmonization with community standards is future work.

**Why a DSH plugin?**  
The agent already has the session, model, tools, and UI. The plugin adds a data-management discipline to that environment instead of building another silo.
