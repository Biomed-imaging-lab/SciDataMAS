# Changelog

All notable changes to the SciDataMAS DSH plugin are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- The Web panel now follows DSH light/dark theme tokens; the previous misspelled background/fill aliases silently fell back to white and produced white-on-white text in dark mode.
- Empty `include`/`exclude` arrays in `scidatamas_import_external` no longer filter out every file; an empty array now means “no filter”. This blocked `mode="analyze"` on records when the caller did not pass patterns.
- The plugin now declares the `llm` service in its `inject` list. Previously `ctx.llm` access threw `cannot get property "llm" without inject`, so dataset creation, validation, and import failed before the first model call.
- Tool results are normalized to JSON-lossless values. `scidatamas_inspect_dataset` previously returned an `undefined` `table` field for file datasets and failed output validation; `undefined`, `NaN`, `Date`, and bigint values are now normalized at the tool boundary.

### Planned

- S3 and Synology storage backends with a materialization cache.
- Write actions in the Web panel (activate, edit schema, run validation, commit stage).
- New-row append for table datasets.
- Parquet/Excel/HDF5 inspection.
- Schema harmonization between datasets.

## [0.1.0] — 2026-11-07

### Added

- DSH bundle with 11 model-facing tools for scientific data management.
- Local data lake with catalog, manifests, JSONL metadata, CSV export, events, and validation reports.
- Single-call metadata generation grounded in example-file inspection.
- DAG-augmented rich metadata generation (`entity` / `signal` / `derivative` provenance).
- Debate-based schema validation with reviewer roles, owner answers, coverage, unanswered questions, and clarifications.
- Two-phase ingestion: stage with partial validation, then strict commit with metadata overrides.
- Safe JSON-filter retrieval with lexical fallback and resolved artifact paths.
- Zenodo / DOI / direct-URL import with staging, inspection, metadata mapping, and provenance.
- Tabular datasets with column schemas and sidecar row metadata keyed by row key.
- DSH-native **Data** Web panel (read-only) with schema, validation, samples, events, and artifact links.
- Side-by-side mode: **Open beside chat** docks the Data panel into the right sidebar while the conversation stays in the main column.
- **Content** tab in the Data panel: paginated `metadata.csv` view with column headers, row count, and CSV download; the Web API exposes `/datasets/<id>/content`.
- Read-only Web API with owner-peer admission and path-contained artifact serving.
- English, Russian, and Chinese Web-panel dictionaries.
- English, Russian, and Chinese README, user guide, and user-testing protocol.
- Tri-lingual glossary, conference demo script (EN/RU), banner and architecture artwork, CITATION.cff, a documentation link checker, and a no-pnpm local installer (scripts/install-local.sh).
- 31 automated tests covering storage, schemas, filters, workflows, import, Web API, locale parity, theme tokens, right-sidebar registration, plugin service injection, and JSON-safe tool outputs.

### Known limitations

- Web panel is read-only.
- S3 and Synology are extension points, not working drivers.
- No new-row append for table datasets.
- No Parquet/Excel/HDF5 inspection.
- Catalog locking is in-process only.
