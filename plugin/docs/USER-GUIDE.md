# SciDataMAS user guide

**English** · [Русский](USER-GUIDE.ru.md) · [中文](USER-GUIDE.zh.md)

This guide is for researchers and demo facilitators who will use the DSH plugin, not for plugin developers. It covers installation, the first dataset, every main workflow, and the things that usually go wrong.

- [1. What this tool is](#1-what-this-tool-is)
- [2. Before you start](#2-before-you-start)
- [3. Install and configure](#3-install-and-configure)
- [4. The Data panel](#4-the-data-panel)
- [5. Create a dataset](#5-create-a-dataset)
- [6. Validate a schema](#6-validate-a-schema)
- [7. Refine and activate](#7-refine-and-activate)
- [8. Add data](#8-add-data)
- [9. Retrieve data](#9-retrieve-data)
- [10. Import from Zenodo or a URL](#10-import-from-zenodo-or-a-url)
- [11. Tabular datasets](#11-tabular-datasets)
- [12. Where the data lives](#12-where-the-data-lives)
- [13. Troubleshooting](#13-troubleshooting)
- [14. FAQ](#14-faq)

## 1. What this tool is

SciDataMAS is a DSH plugin that keeps a **scientific data lake** on your machine. A lake contains datasets. A dataset has:

- a name, description, purpose, status, and provenance;
- a metadata schema (fields with types, descriptions, units, and whether they are required);
- metadata rows, one per file or per table row;
- the artifacts themselves;
- an audit log and, optionally, a validation report.

You work through the agent in chat and observe the lake in the **Data** panel. The agent uses tools; the panel is read-only in this version.

## 2. Before you start

You need:

- a working DSH profile (`web` is the default for the panel);
- a configured model route in DSH (the plugin uses the session model);
- a directory for the lake with enough disk space;
- sample files for a realistic test (a few images, a CSV, or a small folder).

The plugin does not store API keys. Model calls go through `ctx.llm`, so the same provider settings as the rest of DSH apply.

Recommended test root:

```text
/home/<you>/data/scidatamas
```

Do not point the root at `/`, at your home directory, or at a directory containing unrelated files. The plugin creates `datasets/`, `logs/`, `staging/`, and `_imports/` below it.

## 3. Install and configure

### Option A: plugin manager

```bash
dsh plugin --profile web add file:$PWD
```

`pnpm` must be available. The bundle is enabled automatically.

### Option B: manual symlink (no build step)

```bash
mkdir -p "$DSH_HOME/profiles/web/node_modules"
ln -sfn "$PWD" \
  "$DSH_HOME/profiles/web/node_modules/scidatamas-dsh-plugin"
```

Add to `$DSH_HOME/profiles/web/cordis.patch.yml`:

```yaml
- insert:
    - id: scidatamas
      name: scidatamas-dsh-plugin
      config:
        root: /home/alex/data/scidatamas
        author: Your Name
```

### `dsh` is not on PATH (Linux)

DSH may be launched from the npx cache or a desktop bundle, so a bare `dsh` command can be missing — the `dsh` package from apt is unrelated. Find the real CLI:

```bash
find "$HOME/.npm/_npx" -path '*/node_modules/.bin/dsh' -print
```

Use it by absolute path, or define an alias:

```bash
alias dsh="$(find "$HOME/.npm/_npx" -path '*/node_modules/.bin/dsh' -print -quit)"
dsh --version
```

The plugin-manager path also needs `pnpm`. If `pnpm` is missing, run the symlink installer, which edits the profile patch safely and creates the lake root:

```bash
./scripts/install-local.sh
```

Set `DSH_HOME` and `DSH_PROFILE` first if your profile is not `~/.dsh/profiles/web`.

Restart the Web profile (or let HMR apply the patch). Ask the agent:

> Show `scidatamas_status`.

You should see the root, storage driver, dataset count, model availability, and limits.

### Configuration reference

| Field | Default | Meaning |
|---|---|---|
| `root` | `.scidatamas` | Lake directory, absolute or relative to the process cwd. |
| `author` | empty | Default author recorded in metadata rows. |
| `provider`, `model` | empty | Optional model route override. Empty means “use the session model”. |
| `maxSchemaFields` | `200` | Hard cap on generated fields. |
| `maxDagNodes` | `24` | Hard cap on DAG nodes. |
| `dagConcurrency` | `3` | Parallel per-node generation calls. |
| `debateRuns` | `3` | Default debate runs. |
| `debateRoles` | `4` | Reviewer roles per run. |
| `debateQuestionsPerRole` | `4` | Questions per role per run. |
| `maxFileBytes` | `512 MiB` | Largest file copied into the lake. |
| `maxDownloadBytes` | `2 GiB` | Largest total external import. |
| `maxFilesPerAdd` | `200` | Files per add/import call. |
| `maxRowsScan` | `200000` | Rows scanned from a table. |
| `allowNetwork` | `true` | Enable external imports. |
| `allowPrivateHosts` | `false` | Permit localhost/private IP imports. |
| `storageDriver` | `local` | `local`, `s3`, `synology` (the last two are extension points). |
| `logLlmCalls` | `true` | Write prompts/responses to `logs/llm-calls.jsonl`. |

## 4. The Data panel

The sidebar entry **Data** opens a panel with:

- a searchable dataset list;
- dataset metrics (records, files, schema version, layout);
- **Schema** — field name, type, scope, required/optional, unit, description;
- **Validation** — coverage, useful/unused fields, unanswered questions, clarifications, suggested fields;
- **Samples** — metadata rows and links to artifacts;
- **Content** — the full metadata table with column headers, row count, pagination, and CSV download;
- **Events** — creation, staging, commit, validation, retrieval, import;
- **Refresh** and **Copy id**.

To keep the conversation visible, click **Open beside chat** in the panel header (or pick Data from the right sidebar's add control). The panel docks into the right sidebar and the main column returns to the conversation.

The panel reads through `/scidatamas/api` and is available only to the same owner peer as the rest of the Web GUI. If the panel shows **model unavailable**, storage still works; only generation and validation are unavailable.

## 5. Create a dataset

Ask in natural language. The agent chooses the tool. A good request contains:

- a name;
- what one row/element represents;
- how the data was produced;
- the intended reuse;
- example paths, if they exist.

Example:

> Create a dataset `confocal_cells_2026` from `/data/exp1`. Description: confocal z-stacks of PFA-fixed HeLa cells, 40×, one stack per field of view. Purpose: reuse for cell segmentation. Use the compact schema and show me the fields.

The tool inspects the examples and returns a draft with a schema. The dataset is **draft** by default.

For a multi-step experiment, ask for rich metadata:

> The experiment has sample preparation, confocal acquisition, and Cellpose segmentation. Create the dataset with the rich DAG workflow.

`scidatamas_create_dataset_dag` produces more fields and attaches `node_id`/`node_description`; expect more fields than every reuse needs.

## 6. Validate a schema

> Run a three-run debate validation of `confocal_cells_2026` and show the questions the schema cannot answer.

The report contains:

- **coverage** — the share of user fields that answered a reviewer question;
- **useful fields** — how many times each was used and in how many runs;
- **unused fields** — candidates for removal or better description;
- **unanswered questions** — the gap pool;
- **clarifications** — concrete questions for the researcher;
- **suggested fields** — proposed additions with names/types.

The schema is not changed. Use the clarifications to decide what to add.

## 7. Refine and activate

> Add `pixel_size_nm`, `objective`, and `fixation`; improve the description with “PFA-fixed, permeabilized”; set status to active.

`scidatamas_update_dataset` increments `schema_version`, clears `validated_schema_version`, and records the change. Removing fields requires `allow_removals=true`.

A dataset should be activated only after the schema has been reviewed. The panel shows `draft`, `active`, or `archived`.

## 8. Add data

### Review first

> Add `/data/exp2` to `confocal_cells_2026`. Do not commit yet. Note: 4% PFA, objective 40×/1.3 oil, pixel size 100 nm.

`scidatamas_add_data` with `dry_run=true` or `commit=false` returns a **stage**: proposed metadata for each file, missing required fields, and warnings. Nothing is copied.

### Commit

> Commit the stage with those values.

`scidatamas_commit_add` re-validates every record strictly. If a required field is still missing, the commit is refused and no files are copied.

### Explicit values

You can pass a value object applied to all files, an array aligned with files, or a mapping `file → values`. Values given by the user win over model-filled values.

### If the agent cannot annotate a field

This is expected. Answer in text:

> The missing `fixation` value is “4% PFA for 15 min at RT”; `z_slices` is 31.

Then commit with `metadata_overrides`; the audit log keeps the clarification.

## 9. Retrieve data

> Find all confocal stacks with pixel size below 150 nm, created after March, and show the file paths.

The retrieval workflow selects a dataset, plans a JSON filter, validates field names, and returns rows plus resolved paths. If the plan fails, a lexical fallback is used; the response says so in `plan.used_fallback`.

Set `include_preview=true` to get short text excerpts or image dimensions. The panel’s Samples tab links to the artifact itself.

## 10. Import from Zenodo or a URL

Start with analysis:

> Analyze Zenodo record 5512749. How many files, what formats, what license?

Then import with filters:

> Import `**/*.tif` from that record, at most 20 files. Create a dataset from the record metadata and activate it.

What happens:

1. the record is read through the Zenodo API;
2. selected files are downloaded to `_imports/<id>/`;
3. files are inspected and a schema is generated;
4. a dataset is created (or an existing `dataset_id` is used);
5. DOI/license/creators/publication date are mapped onto the schema;
6. files are staged and committed;
7. staging is removed on success and kept on failure for inspection.

Direct HTTP(S) file URLs use the same path. Private hosts are blocked unless `allowPrivateHosts: true`.

## 11. Tabular datasets

Use `layout="table"` when the primary artifact is a table:

> Create a table dataset from `/data/measurements.csv`; the first column is `participant_id`. Describe every column.

Rules:

- the table stays the canonical artifact in `files/`;
- the schema describes columns (`scope: "column"`) and optional row-level fields;
- one sidecar metadata row per table row is stored in `metadata.jsonl`, keyed by the row key;
- `get_data` merges columns and sidecar rows;
- the row key is chosen from `id`/`row_id`/`row`/`index`/`sample_id`/`key`, then the first unique column, then the row index;
- annotating existing rows is supported; appending new rows is not yet.

## 12. Where the data lives

```text
<root>/
  catalog.json
  datasets/<id>/
    manifest.json
    metadata.jsonl
    metadata.csv
    files/...
    events.jsonl
    validation/latest.json
    validation/history.jsonl
    staging/<stage_id>.json
  logs/llm-calls.jsonl
  _imports/<import_id>/
```

`manifest.json` is the source of truth for the schema and dataset state. `metadata.jsonl` is the row store. `metadata.csv` is a flat export. `events.jsonl` is the audit trail. `logs/llm-calls.jsonl` contains internal prompts/responses when `logLlmCalls` is enabled.

Back up the whole root; do not edit `manifest.json` by hand while a session is writing.

## 13. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `SCIDATAMAS_NO_MODEL` / “model unavailable” | No session model selected and no provider/model configured | Select a model in DSH or set `provider`/`model` in the plugin config. |
| `SCIDATAMAS_NO_LLM` | The profile has no `ctx.llm` service | Use a base-backed Web profile. Storage-only tools still work. |
| Panel shows “No datasets yet” | Empty lake or stale catalog in a long-running server | Create a dataset, then press Refresh. |
| `SCIDATAMAS_MISSING_FIELDS` | Commit with required fields missing | Read the missing list; provide `metadata_overrides` or a clarification note. |
| `SCIDATAMAS_FILE_TOO_LARGE` | File exceeds `maxFileBytes` or `maxDownloadBytes` | Raise the limit or narrow the import. |
| `SCIDATAMAS_PRIVATE_HOST` | Import from localhost/private IP | Set `allowPrivateHosts: true` if you trust the source. |
| `SCIDATAMAS_BAD_JSON` | Model did not return valid JSON after retries | Retry; if it persists, use a stronger model or lower the field limit. |
| `SCIDATAMAS_NO_DATASET_MATCH` | Retrieval could not choose a dataset | Pass `dataset_id` explicitly. |
| `SCIDATAMAS_TABLE_REQUIRED` | `layout="table"` without `table_path` | Provide a CSV/TSV/JSON/JSONL path. |
| `SCIDATAMAS_SCHEMA_REMOVAL` | Update drops fields | Confirm with `allow_removals=true` if intended. |

More codes are listed in [TOOLS.md](TOOLS.md).

## 14. FAQ

**Does the model see my raw files?**  
No. The plugin sends file names, formats, sizes, image dimensions, table headers, JSON shape, and short text excerpts. Binary content is not sent to the model.

**Where are my API keys?**  
Nowhere in the plugin. It uses the DSH LLM service and the profile’s credentials.

**Can I use this without the Web panel?**  
Yes. The tools work in headless and other profiles; the client half is Web-only.

**Can multiple people write to one lake?**  
Not safely yet. The catalog lock is in-process. Use one DSH process per lake; cross-process locking is on the roadmap.

**Can I move the lake?**  
Yes, if no DSH process is writing. Copy the whole root and update `root`. Manifest keys are relative, so the copy is portable.

**Does it work with S3 or Synology now?**  
No. The storage seam and stubs exist; real drivers are the next development step.

**Is the metadata schema stored as CSV or JSON?**  
The schema lives in `manifest.json`; rows live in `metadata.jsonl`; `metadata.csv` is an export for convenience.
