# SciDataMAS DSH Architecture

**English** · [Русский](ARCHITECTURE.ru.md)

A document for the developer: how the plugin is embedded in DSH, which invariants it maintains, and where to extend it.

## 1. DSH integration

The plugin is an ordinary Cordis package:

```js
export const name = 'scidatamas'
export const inject = ['tools', 'systemPrompt']
export const Config = z.object({ ... })
export async function apply(ctx, config) { ... }
```

- `ctx.tools.register(defineTool(...))` registers 11 tools; argument schemas and the output contract are validated by DSH.
- `ctx.systemPrompt.section({ name: 'tool:scidatamas', order: 150, text })` adds the rules for working with the lake to the agent.
- `ctx.llm.stream(...)` is the only path to the model. The default route is `exec.agent.model.current()`; the fallback is `config.provider/model`, then `ctx.agentDefaultModel`.
- `ctx.workingDirectory` is not used: the lake root is set by config rather than by the session's current directory, so that data does not "move" between sessions.
- The plugin registers tools everywhere; a Web profile additionally registers a read-only HTTP API and a client bundle. Headless compositions keep the tool-only surface.

`package.json` declares the bundle:

```json
"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
```

`cordis.patch.yml` inserts a single `scidatamas` line. The user overrides its config in the profile by `id: scidatamas`.

### Why a bundle rather than a set of separate plugins

The service, the workflows and the tools share one `SciDataMAS` instance (lake + LLM client + audit). Splitting them into multiple composition lines without need would mean breeding cross-plugin dependencies and the risk of two lakes in one profile. One line is simpler to install and simpler for HMR.

### Model and audit

Internal calls are not part of the dialogue, but they must be reproducible. Therefore `LlmClient`:

- passes `system` and `messages` to `ctx.llm.stream`;
- assembles the response with `BlockAssembler`;
- checks the terminal `finish` (`error`/`aborted` → exception);
- writes an entry to `logs/llm-calls.jsonl`: `ts`, `purpose`, `provider`, `model`, `duration_ms`, `usage`, `finish`, `system`, `messages`, `response`, `error`.

The entry is truncated by `logMaxChars` (200k characters per field by default). This is not the DSH session log but a separate lake audit log; it outlives the session and lives next to the data. If policy requires a strict "model-visible ⟺ session log", an event could be added to the session via `ctx.on`/`session.append`; the current version deliberately does not inflate the dialogue history with giant DAG prompts.

## 2. Layers

```text
tools.js            model contracts, descriptions, rendering
  ↓
service.js          facade: init, create, validate, add, query, import
  ↓
workflows/*.js      business processes, prompts, LLM calls
  ↓
lake.js             catalog, manifests, metadata.jsonl, staging, events
  ↓
storage.js          StorageBackend (local today; s3/synology — extension points)
```

`metadata.js`, `inspect.js`, `filter.js`, `util.js` are deterministic utilities with no DSH dependencies. Thanks to this, the 31 tests run with plain `node --test` without a profile.

## 3. Dataset states

```text
create ──► draft ──(update status=active | commit add)──► active ──► archived
              │
              └── validate_schema: schema_version is marked validated,
                  but the schema itself does not change
```

Invariants:

- `schema_version` increases only when user fields actually change.
- `validated_schema_version` is reset when the schema changes.
- `status` changes only through an explicit `update_dataset` or a successful data commit.
- Removing fields requires `allow_removals=true`.
- The schema always contains the system fields; user fields cannot occupy their names.

## 4. Dataset manifest

```json
{
  "id": "confocal_cells_2026",
  "name": "Confocal cells 2026",
  "description": "...",
  "purpose": "...",
  "layout": "files",
  "status": "draft",
  "modality": "microscopy",
  "provenance": "real",
  "author": "A. Sachuk",
  "created_at": "...",
  "updated_at": "...",
  "schema_version": 1,
  "validated_schema_version": null,
  "schema": {
    "fields": [
      { "name": "id", "type": "string", "system": true, "required": true },
      { "name": "pixel_size_nm", "type": "number", "description": "...", "required": true }
    ],
    "rejected": [],
    "warnings": []
  },
  "table": null,
  "source": null,
  "counts": { "records": 0, "files": 0, "bytes": 0 },
  "defaults": { "author": "...", "uploaded_at": "..." },
  "storage": { "driver": "local", "root": "local://" }
}
```

For a table dataset, `table` contains `path`, `row_key`, `row_key_fallback`, `columns` (with `source`), `row_count`, `format`, `size`. The schema contains fields with `scope: "column"` and a `source` — the original column name, when normalization changed the name.

## 5. Flows

### 5.1 Single-call

```text
tool args ──► inspect examples ──► prompt ──► llm.json ──► normalizeSchema
                                                   │
                                                   └──► createDataset
```

If `layout=table`, `tableSchemaSystem` plus the table dossier is used instead of the generic single call; then `registerTable` copies the table and adds the missing columns to the schema.

### 5.2 DAG

```text
description ──► planDag ──► validateDag ──(bad)──► repair call
                                  │(ok)
                                  ▼
                    per-node field generation (bounded concurrency)
                                  │
                                  ▼
                    merge + node_id/node_description + normalize
```

The validator checks:

- unique ids, allowed types `entity|signal|derivative`;
- `preparation`: entity→entity; `capture`: entity→signal; `program`: signal/derivative→derivative;
- acyclicity (Kahn);
- the presence of at least one signal/derivative;
- the `maxDagNodes` limit.

Parallel per-node calls do not see each other's fields (except for the `existingNames` snapshot taken at start), so duplicates are possible. They are collapsed by name with a warning; this is a deliberate speed/completeness trade-off.

### 5.3 Debate

```text
for run in 1..N:
  scenario+roles (no schema)
  parallel: role questions
  owner answers (exact schema)
  score fields, collect unanswered
aggregate:
  coverage, useful fields, unused fields, dedup unanswered
synthesis:
  clarifications + suggested fields
persist validation/latest.json, mark schema validated
```

The evaluation is deliberately asymmetric: the roles do not see the schema, the owner sees only the schema. This catches fields that "are in the schema but do not answer real questions", and questions for which the metadata is insufficient. The owner cannot invent a field: `validFields` are filtered by the exact set of names, otherwise the answer is counted as unanswered + warning.

### 5.4 Stage/commit

```text
collect files ──► inspect ──► fill batches (LLM) ──► merge explicit
                                                   │
                                                   ▼
                                      partial validation + missing
                                                   │
                              ready? ──no──► return stage (no copy)
                                 │yes
                                 ▼
                    strict validation of all records
                                 │
                                 ▼
                    copy files ──► append metadata ──► event ──► active
```

The copy starts only after all records have passed strict validation. This is not a filesystem-level transaction: if the copy fails midway, some files remain. The production version needs dataset-level staging-then-rename or a transaction manifest; noted in the roadmap.

### 5.5 Retrieval

```text
query ──► select dataset (LLM / lexical) ──► plan filter (LLM)
      ──► validateFilter ──► runQuery ──► resolve files/previews
```

The filter is a JSON DSL, not SQL. This eliminates a whole class of attacks and allows fields to be validated before execution. If the planner fails, a lexical ranker is used rather than an "empty result".

### 5.6 External import

```text
url ──► parse (Zenodo/DOI/URL) ──► analyze (API + file list)
                                 │
                    mode=analyze └──► return plan
                                 │mode=import
                                 ▼
                  download to _imports/<id> (limits, globs)
                                 ▼
                  inspect ──► create/choose dataset ──► map record metadata
                                 ▼
                  stage ──► commit ──► event ──► delete staging on success
```

The Zenodo API returns `files[].links.self` (often `/api/records/<id>/files/<key>/content`), which is what is used for downloading. For a direct URL — HEAD; if the server does not support HEAD, a GET fallback should be added (roadmap).

## 6. Tabular data: why a sidecar

The alternatives that were considered:

| Variant | Pros | Cons |
|---|---|---|
| Store a JSON blob of metadata in the schema | simple | does not scale, breaks the tabular format, hard to filter |
| Duplicate the CSV with added columns | familiar | two copies of the data, desynchronization, large volume |
| A row id from the CSV + sidecar JSONL | the table is canonical, row metadata is added in parts, filters over both layers | requires a row key and a merge on output |

The third was chosen. `row_key` is determined as follows: an explicit `row_key` → the columns `id/row_id/row/index/sample_id/key` with unique non-empty values → the first unique column → `__row_index__` (row index). If uniqueness is lost, `row_key_fallback=true`; row ids become positional and unstable when the table is reordered — this is recorded in the manifest.

## 7. Storage extension

`StorageBackend` is deliberately small and has no "smart" operations. For S3:

- `readText/writeText/readBuffer/writeBuffer` → `GetObject/PutObject`;
- `copyIn` → `PutObject` from a file (stream);
- `list(prefix)` → `ListObjectsV2` with pagination;
- `localPath(key)` → a path in the materialization cache (download when necessary);
- `uri(key)` → `s3://bucket/key`.

The catalog (`catalog.json`, manifests) can be left in the local control plane or moved to a database; the keys are already relative. For Synology, a sensible first step is a mounted SMB/WebDAV plus the `LocalStorage`; a native client is the same interface.

What needs to be added before a real remote:

- materialization cache and invalidation;
- transactionality of the manifest and metadata under network failures;
- distributed catalog locking;
- integrity check (size/hash) after writing.

## 8. Error handling

- `LakeError` with a code (`SCIDATAMAS_NOT_FOUND`, `SCIDATAMAS_MISSING_FIELDS`, ...) — expected domain errors; the text is suitable for the user.
- `ModelError` with a code (`SCIDATAMAS_NO_MODEL`, `SCIDATAMAS_BAD_JSON`, ...) — routing/response problems.
- `defineTool` validates the arguments itself; tool exceptions become an error result rather than a session crash.
- `exec.signal` is propagated to the LLM and HTTP; long-running tools declare `timeoutMs`.
- A corrupt manifest of one dataset does not block `list_datasets` (read errors are skipped), but `get_data` on it returns an error.

## 9. Verification in DSH

1. `node --test test/*.test.js` — 31 tests without DSH.
2. Smoke registration: import `src/index.js`, call `apply` with a minimal fake ctx (`tools.register`, `systemPrompt.section`) and check the 11 tools.
3. Loading in a real profile:

```bash
export DSH_HOME=/path/to/test-home
dsh --profile scitest --from-default-profile headless --dump-config
# add the scidatamas line to cordis.patch.yml
dsh --profile scitest --dump-config-schema | grep scidatamas
```

`--dump-config-schema` imports the module and reads `Config` without running the model. A full run requires a provider key and a session.

## 10. Web panel

The panel is the second (browser) half of the same package. The host half and the client half do not share code: the host serves the API, the client draws the UI.

### 10.1. How the client gets into the browser

`package.json` declares:

```json
"exports": { "./client": "./src/client.js" },
"dsh": {
  "bundle": { "patch": "./cordis.patch.yml" },
  "client": { "platform": "web" }
}
```

`dsh-client-modules` scans the active Loader lines, reads `dsh.client`, builds the boot graph and serves `src/client.js` as a bundle under `/plugins`. The file format is not regular ESM but a module-loader factory:

```js
window.__ModuleLoader__.load({
  id: 'scidatamas-dsh-plugin',
  factory: (require) => {
    const React = require('react')
    ...
    exports.apply = apply
    return module.exports
  }
})
```

React, `react/jsx-runtime` and the services (`ctx.slots`, `ctx.locale`) are part of the platform seed; therefore the bundle does not pull in its own dependencies and requires no build. This is a deliberate choice for a "boxed" plugin: `src/client.js` is read and edited as a regular file, and `pnpm run build` is not needed. If the panel grows, it can be migrated to TS/tsdown without changing the `dsh.client` contract.

### 10.2. Slots

Client-side `apply(ctx)`:

```js
ctx.effect(() => ctx.locale.register('scidatamas', { en, ru }), '...')
const t = ctx.locale.bind('scidatamas')

ctx.slots.inject('main', () => ctx.slots.register({
  name: 'main', key: 'scidatamas', locale: 'scidatamas',
}, Page))

ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
  name: 'sidebar.panellist', id: 'scidatamas', order: 20,
  locale: 'scidatamas', label: () => t('panel'),
}, DataIcon))
```

`sidebar.panellist` adds a row to the left panel; a click calls `layout.selectPanel('scidatamas')`. `main` with the same `key` is the page itself. `slots.inject` waits for the slot declaration and unregisters when the plugin unloads. `ctx.locale` provides the en/ru dictionaries.

### 10.2.1. Side-by-side mode

The same page is also registered as the right-sidebar page type `scidatamas-data` (`ctx.sidebarRightTabs.register`) with a body under the `sidebar.right.pane.tab` slot. The **Open beside chat** button switches the main slot back to the conversation (`layout.selectPanel(null)`) and opens the page through `ctx.sidebarRight.openTab('scidatamas-data')`. The page type also contributes a guide card, so the right sidebar's add control can open it directly. The compact layout changes the grid to list-above-detail for the narrower column.

The **Content** tab requests `/datasets/<id>/content?limit=&offset=` and renders the returned column order and rows as a scrollable table. **Download CSV** points at the same endpoint with `format=csv`, which streams a `text/csv` attachment. `has_more` controls the Load more button.

### 10.3. API and authorization

`src/web-api.js` registers the prefix route `/scidatamas/api` on `webServer` and checks:

```js
const admission = connection.admit(req)
if (admission.rejection) → 401/403
if (admission.peer.principal.kind !== 'owner') → 403
```

That is, the panel is available only to the same owner peer as the rest of the Web GUI; there is no separate token/login. The route is registered only if the profile has `webServer` and `connection` (Web), so a headless profile does not open an HTTP port.

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/scidatamas/api/status` | root, storage, number of datasets, model availability, limits |
| GET | `/scidatamas/api/datasets?query=` | catalog |
| GET | `/scidatamas/api/datasets/<id>` | details: schema, samples, validation summary, events |
| GET | `/scidatamas/api/datasets/<id>/content?limit=&offset=` | paginated metadata rows for the **Content** tab |
| GET | `/scidatamas/api/datasets/<id>/content?format=csv` | the same rows as a downloadable CSV |
| GET | `/scidatamas/api/datasets/<id>/validation` | full validation report |
| GET | `/scidatamas/api/datasets/<id>/file?path=` | artifact from `datasets/<id>/files/...` |

File serving:

- only a key inside `datasets/<id>/files/` is accepted;
- `..` and absolute keys are rejected both by the prefix check and by `StorageBackend`;
- `Content-Type` from the extension, `Content-Disposition: inline` for images/text/PDF, otherwise `attachment`;
- `X-Content-Type-Options: nosniff`; HTML/JS artifacts are not executed in the GUI context;
- the remote backend needs a materialization cache; for now a 501 is returned.

### 10.4. Theme

The panel has no private palette. It consumes the DSH theme aliases (`--dsw-alias-bg-base`, `--dsw-alias-bg-layer-2/3`, `--dsw-alias-label-*`, `--dsw-alias-border-*`, state colors) and falls back to CSS system colors (`Canvas`, `CanvasText`, `ButtonFace`, `Field`, `GrayText`). `color-scheme: light dark` keeps native inputs and focus rings consistent with the active theme. The earlier version used misspelled `--dsw-alias-bg-l1` / `fill-l1` aliases, which silently fell back to white and produced white-on-white text in dark mode; `test/theme.test.js` now guards the real token names.

### 10.5. Why read-only

Writing from the panel would mean a second path for creating/adding data that bypasses staging, strict validation and confirmation. In the first version the panel is an observation window: catalog, schema, validation, samples, events. All changes go through the agent's tools, where auditing and human-in-the-loop apply. The next stage is to add safe actions from the panel: activate, editing the description/schema, running a debate, committing a ready stage; each action must call the same workflow functions rather than write to the lake directly.

### 10.6. Verification

- `test/web-api.test.js` starts a real `node:http` server and checks the status, the catalog, details, file serving, traversal rejection and 401 for a non-owner.
- Registration of the client bundle is checked by a smoke script (a stub for `window.__ModuleLoader__` and React), and in a live Web profile by loading the page: `scidatamas-dsh-plugin/client.js` is present in the boot graph, and the **Data** panel appears in the sidebar.
- The UI was checked with headless Chromium (Playwright): catalog, Schema, Validation, Samples, Events; the screenshots are in `docs/assets/`.

## 11. Roadmap

1. S3/Synology backends + materialization cache.
2. Actions from the Web panel: activate, editing the description/schema, running a debate, committing a stage.
3. Harmonizing schemas across datasets (top-k + LLM, as in the paper).
4. Adding new rows to a table dataset (append + row key recalculation).
5. Parquet/Excel/HDF5 inspection.
6. Transactional commit (staging dir → atomic rename).
7. Pagination/cursors for large result sets.
8. Session events for LLM calls (strict model-visible ⟺ session log).
9. Import deduplication by checksum.
10. Export to RO-Crate/BIDS-like formats.
