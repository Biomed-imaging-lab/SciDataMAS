# Tool reference

**English** · [Русский](TOOLS.ru.md)

All tools share the `scidatamas_` prefix. DSH validates arguments before execution; errors are returned as an error result rather than aborting the session. Long-running operations declare `timeoutMs` and listen to `exec.signal`.

## `scidatamas_create_dataset`

Create a dataset with a compact schema (single call).

| Argument | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | name; the id is derived from it |
| `description` | string | yes | what the dataset contains and what a single row is |
| `purpose` | string | no | intended use; affects fields and the debate |
| `layout` | `files` \| `table` | no | defaults to `files` |
| `table_path` | string | for table | CSV/TSV/JSON/JSONL |
| `row_key` | string | no | column that identifies a row |
| `example_paths` | string[] | no | files/directories as evidence only, not copied |
| `author` | string | no | default author |
| `modality` | string | no | for example `microscopy` |
| `tags` | string[] | no | tags |
| `activate` | boolean | no | make active immediately (draft by default) |
| `validate` | boolean | no | run the debate immediately |
| `debate_runs` | integer | no | number of runs when `validate=true` |

Returns: `dataset` (summary), `schema` (with system fields), `system_fields`, `generated`, `evidence`, `table`, `validation`, `next_steps`.

Errors: empty name/description, `layout=table` without `table_path`, duplicate id, empty schema from the model, no model configured.

## `scidatamas_create_dataset_dag`

Same, but in rich mode: DAG planning, topology validation, per-node field generation.

Returns in addition `generated.dag`, `generated.dag_text`, `generated.warnings`, `generated.nodes`, `generated.fields`. Schema fields carry `node_id`/`node_description`.

When to use: a multi-stage experiment, the user asks for "rich/detailed annotation", and the data will be annotated automatically by a pipeline. When not to use: a small flat dataset where readability and a minimum of extra fields matter.

## `scidatamas_validate_schema`

| Argument | Type | Required | Meaning |
|---|---|---|---|
| `dataset_id` | string | yes | dataset |
| `runs` | integer | no | 1–5, defaults to 3 |

Returns:

- `coverage` — share of user fields actually used in the answers;
- `useful_fields[]` — `{name, uses, runs_used, description, type}`;
- `unused_fields[]` — fields that no reviewer needed;
- `unanswered_questions[]` — `{text, count, roles, runs}`;
- `clarifications[]` — `{question, why, asked_in_runs, suggested_field}`;
- `suggested_fields[]` — fields that are ready to be added;
- `run_details[]` — scenario, roles, number of questions/answers;
- `report_path` — `datasets/<id>/validation/latest.json`.

The schema is not modified. `validated_schema_version` becomes equal to the current `schema_version`. If the schema changes later, the marker is reset.

## `scidatamas_update_dataset`

| Argument | Type | Meaning |
|---|---|---|
| `dataset_id` | string | yes |
| `name`, `description`, `purpose`, `author` | string | new values |
| `fields` | json | full replacement of user fields; system fields are added automatically |
| `status` | `draft` \| `active` \| `archived` | status |
| `tags` | string[] | replaces the tags |
| `allow_removals` | boolean | confirm removal of fields |

When the schema changes, `schema_version++`, `validated_schema_version=null`. Without `allow_removals=true`, removal of existing fields is rejected.

## `scidatamas_list_datasets`

`query` (string, optional), `include_drafts` (boolean, defaults to true). Returns `{root, datasets:[summary]}`.

## `scidatamas_inspect_dataset`

`dataset_id`, `sample_rows` (defaults to 5, maximum 50). Returns a summary, the full schema, `schema_text`, table metadata, sample rows, the latest validation, and the last 20 events.

## `scidatamas_add_data`

| Argument | Type | Meaning |
|---|---|---|
| `dataset_id` | string | yes |
| `paths` | string[] | files/directories for a file dataset |
| `metadata` | json | one object for everything, an array per file, a file→values mapping; for table — an array of row records with `id` |
| `notes` | string | user clarification: fixation, objective, units, what is in the file |
| `dry_run` | boolean | stage only |
| `commit` | boolean | auto-commit a ready stage (defaults to true) |
| `activate` | boolean | activate after commit (defaults to true) |
| `author` | string | author of the records |
| `metadata_overrides` | json | values at commit time |

Returns either `{committed:false, stage, ready, message}` or `{committed:true, stage, committed_count, files, dataset}`.

Rules:

- required fields are not invented: a stage with `missing` is not committed automatically;
- one invalid record cancels the whole commit;
- for a table dataset, `metadata` annotates existing rows rather than being a new table;
- every stage/commit is written to `events.jsonl`.

## `scidatamas_commit_add`

`dataset_id`, `stage_id`, `metadata_overrides` (json), `notes`, `activate`. Re-validates strictly and either commits everything or refuses with a list of missing fields.

## `scidatamas_get_data`

| Argument | Type | Meaning |
|---|---|---|
| `query` | string | what needs to be found |
| `dataset_id` | string | explicit dataset (otherwise chosen by the model/lexically) |
| `limit` | integer | 1–200, defaults to 50 |
| `include_files` | boolean | resolve paths (defaults to true) |
| `include_preview` | boolean | text excerpts/image sizes |
| `fields` | string[] | projection |

Returns `dataset`, `selection`, `plan` (filter, fields, reasoning, fallback), `matched`, `returned`, `rows`, `files`, `hints`.

The filter is a JSON DSL; SQL is not executed. If the planner is unavailable, lexical search is used.

## `scidatamas_import_external`

| Argument | Type | Meaning |
|---|---|---|
| `url` | string | Zenodo record/API/DOI or a direct HTTP(S) file |
| `mode` | `analyze` \| `import` | analyze by default |
| `dataset_name` | string | name of the new dataset; defaults to the record title |
| `dataset_id` | string | add to an existing dataset |
| `description`, `purpose` | string | overrides |
| `rich` | boolean | DAG schema |
| `include`, `exclude` | string[] | glob patterns |
| `max_files` | integer | defaults to 100 |
| `author`, `modality` | string | |
| `activate` | boolean | defaults to true |

`analyze` returns `source`, `files`, `total_bytes`, `record` without downloading. `import` additionally creates/selects the dataset, downloads, inspects, maps DOI/license/creators/publication_date, runs stage+commit, and writes `external_imported`.

Limitations: private hosts are blocked if `allowPrivateHosts=false`; the total size is capped by `maxDownloadBytes`; on a staging error, staging is preserved in `_imports/<id>`.

## `scidatamas_status`

No arguments. Returns the root, storage driver, number of datasets, model availability (provider/model), and limits. Convenient for diagnostics before a long workflow.

## Typical errors

| Code | Cause |
|---|---|
| `SCIDATAMAS_NO_MODEL` | no model is selected and no provider/model is set |
| `SCIDATAMAS_NO_LLM` | `ctx.llm` is not mounted in the profile |
| `SCIDATAMAS_BAD_JSON` | the model did not return valid JSON after retries |
| `SCIDATAMAS_MISSING_FIELDS` | commit without required fields |
| `SCIDATAMAS_SCHEMA_REMOVAL` | update removes fields without `allow_removals` |
| `SCIDATAMAS_NOT_FOUND` | no such dataset |
| `SCIDATAMAS_NO_STAGE` | no stage with that id |
| `SCIDATAMAS_FILE_TOO_LARGE` | `maxFileBytes`/`maxDownloadBytes` exceeded |
| `SCIDATAMAS_PRIVATE_HOST` | import from localhost/private IP without permission |
| `SCIDATAMAS_BAD_DAG` | the DAG failed the validator after repair |
| `SCIDATAMAS_TABLE_REQUIRED` | `layout=table` without `table_path` |

## Panel Web API

The route is registered only in the Web profile: `/scidatamas/api`. Access is checked via `connection.admit(req)` and allowed only for the owner peer.

| Method | Path | Response |
|---|---|---|
| GET | `/scidatamas/api/status` | `{status}`: root, storage, datasets, model, limits |
| GET | `/scidatamas/api/datasets?query=&include_drafts=` | `{root, storage, datasets[]}` |
| GET | `/scidatamas/api/datasets/<id>` | `{dataset, schema, schema_text, table, sample_rows, validation, events}` |
| GET | `/scidatamas/api/datasets/<id>/content?limit=&offset=` | paginated metadata rows and column order (the Content tab) |
| GET | `/scidatamas/api/datasets/<id>/content?format=csv` | the same rows as a downloadable CSV |
| GET | `/scidatamas/api/datasets/<id>/validation` | `{validation}` — the full latest report |
| GET | `/scidatamas/api/datasets/<id>/file?path=files/...` | bytes of the artifact |

API limitations:

- only `GET`/`HEAD`;
- a file is served only from `datasets/<id>/files/...`;
- `..` and absolute keys are forbidden;
- the remote backend returns 501 until a materialization cache exists;
- there is no write access through the API: changes go through the agent's tools.
