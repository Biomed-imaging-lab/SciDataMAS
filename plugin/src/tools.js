/**
 * Model-facing tools. Each tool is a thin adapter over {@link SciDataMAS};
 * descriptions tell the agent when to reach for single-call vs DAG creation,
 * when validation is worthwhile, and why a staged add may need clarification.
 * @module scidatamas/tools
 */
import { defineTool as defineToolRaw } from '@deepseek-ai/dsh-tools'
import { clip, jsonSafe } from './util.js'

/** Wrap every tool result so undefined/NaN/Date values cannot fail output validation. */
function defineTool(definition) {
  const execute = definition.execute
  return defineToolRaw({
    ...definition,
    async execute(args, exec) {
      return jsonSafe(await execute(args, exec))
    },
  })
}

const JSON_OUTPUT = {
  schema: { type: 'object', additionalProperties: true },
  render: (_args, value) => [{ type: 'text', text: clip(JSON.stringify(value, null, 2), 120000) }],
}

function textOutput(render) {
  return {
    schema: { type: 'object', additionalProperties: true },
    render: (_args, value) => [{ type: 'text', text: render(value) }],
  }
}

function asArray(value) {
  if (value === undefined || value === null || value === '') return []
  return Array.isArray(value) ? value : [value]
}

/** Register all SciDataMAS tools on the agent-scoped context. */
export function registerTools(ctx, service) {
  ctx.tools.register(defineTool({
    name: 'scidatamas_create_dataset',
    description: `Create a scientific dataset with a compact metadata schema generated in one model call (single-call mode).
Use this for a well-understood experiment where a flat, readable schema is enough. Provide a clear description, the intended reuse (purpose), and optional example file paths; the tool inspects those files (formats, image dimensions, table headers, text excerpts) and generates the metadata table.
The lake automatically adds the organizational fields id, author, uploaded_at, file_path and source_url.
For tabular data use layout="table" and table_path to a CSV/TSV/JSON/JSONL file; the schema then describes columns and the table stays the canonical artifact.
The dataset starts as a draft; run scidatamas_validate_schema and review the schema before activating it.`,
    parameters: {
      name: { type: 'string', required: true, description: 'Human-readable dataset name; also used to derive the id.' },
      description: { type: 'string', required: true, description: 'What the dataset contains, how it was produced, and what one row/element represents.' },
      purpose: { type: 'string', description: 'Planned reuse or research question; improves field selection and later debate validation.' },
      layout: { type: 'string', enum: ['files', 'table'], description: 'files = one metadata row per artifact; table = one row per table row, schema describes columns.' },
      table_path: { type: 'string', description: 'Required for layout="table": path to a CSV/TSV/JSON/JSONL table.' },
      row_key: { type: 'string', description: 'Table column that uniquely identifies a row (default: id-like column, else first unique column, else row index).' },
      example_paths: { type: 'array', items: { type: 'string' }, description: 'Optional files or directories used only as evidence for schema generation; they are not copied.' },
      author: { type: 'string', description: 'Default author for records; defaults to the plugin config.' },
      modality: { type: 'string', description: 'Optional modality, e.g. microscopy, sequencing, spectroscopy, tabular.' },
      tags: { type: 'array', items: { type: 'string' }, description: 'Optional free-form tags.' },
      activate: { type: 'boolean', description: 'Create the dataset as active immediately (default false: draft).' },
      validate: { type: 'boolean', description: 'Run debate-based schema validation right after creation (default false; costs several model calls).' },
      debate_runs: { type: 'integer', description: 'Debate runs when validate=true (default 3, max 5).' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 600000,
    async execute(args, exec) {
      return service.createDataset({
        name: args.name,
        description: args.description,
        purpose: args.purpose ?? '',
        layout: args.layout ?? 'files',
        table_path: args.table_path,
        row_key: args.row_key,
        example_paths: asArray(args.example_paths),
        author: args.author,
        modality: args.modality,
        tags: asArray(args.tags),
        activate: args.activate === true,
        validate: args.validate === true,
        debate_runs: args.debate_runs,
      }, { exec, rich: false })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_create_dataset_dag',
    description: `Create a scientific dataset with rich, DAG-augmented metadata.
Use this when the experiment has a multi-step provenance (sample preparation -> capture -> processing) or when the user explicitly asks for rich/detailed metadata. The tool first designs a provenance DAG (entity, signal, derivative nodes), validates its topology, then generates node-specific fields and merges them into one flat schema with node provenance. It produces more fields than single-call mode and is better suited to automated annotation, but also produces more fields than every reuse needs.
Other arguments and the draft/validation workflow are the same as scidatamas_create_dataset.`,
    parameters: {
      name: { type: 'string', required: true, description: 'Dataset name.' },
      description: { type: 'string', required: true, description: 'What the dataset contains, how it was produced, and what one row/element represents.' },
      purpose: { type: 'string', description: 'Planned reuse; drives the DAG scenario.' },
      layout: { type: 'string', enum: ['files', 'table'], description: 'files (default) or table.' },
      table_path: { type: 'string', description: 'Required for layout="table".' },
      row_key: { type: 'string', description: 'Row key column for table layout.' },
      example_paths: { type: 'array', items: { type: 'string' }, description: 'Files/directories inspected as evidence.' },
      author: { type: 'string', description: 'Default author.' },
      modality: { type: 'string', description: 'Optional modality.' },
      tags: { type: 'array', items: { type: 'string' }, description: 'Optional tags.' },
      activate: { type: 'boolean', description: 'Create as active (default false: draft).' },
      validate: { type: 'boolean', description: 'Run debate validation immediately.' },
      debate_runs: { type: 'integer', description: 'Debate runs when validate=true (default 3).' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 900000,
    async execute(args, exec) {
      return service.createDataset({
        name: args.name,
        description: args.description,
        purpose: args.purpose ?? '',
        layout: args.layout ?? 'files',
        table_path: args.table_path,
        row_key: args.row_key,
        example_paths: asArray(args.example_paths),
        author: args.author,
        modality: args.modality,
        tags: asArray(args.tags),
        activate: args.activate === true,
        validate: args.validate === true,
        debate_runs: args.debate_runs,
      }, { exec, rich: true })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_validate_schema',
    description: `Run debate-based validation of a dataset schema.
For each run the workflow invents a concrete experiment where the dataset could be used, creates reviewer roles with different goals, lets them ask the owner questions, and checks which questions the exact schema can answer. Fields that answer questions are useful; unanswered questions become clarifications and proposed fields.
Returns coverage (share of schema fields used), useful_fields with use counts, unanswered_questions, clarifications (questions to ask the researcher), suggested_fields, and the report path. The schema version is marked validated, but the schema is not changed automatically: use scidatamas_update_dataset to apply clarifications. Default is 3 runs.`,
    parameters: {
      dataset_id: { type: 'string', required: true, description: 'Dataset to validate.' },
      runs: { type: 'integer', description: 'Number of independent debate runs (default 3, max 5).' },
    },
    output: textOutput((value) => {
      const lines = [
        `Schema validation for "${value.dataset_id}" (schema v${value.schema_version})`,
        `Runs: ${value.runs}, coverage: ${(value.coverage * 100).toFixed(1)}%`,
        '',
        `Useful fields (${value.useful_fields.length}):`,
        ...value.useful_fields.slice(0, 25).map((field) => `- ${field.name}: used ${field.uses}x in ${field.runs_used} run(s)`),
        '',
        `Unused fields (${value.unused_fields.length}): ${value.unused_fields.join(', ') || 'none'}`,
        '',
        `Clarifications (${value.clarifications.length}):`,
        ...value.clarifications.slice(0, 15).map((item, index) => `${index + 1}. ${item.question}`),
        '',
        `Report: ${value.report_path}`,
      ]
      return lines.join('\n')
    }),
    timeoutMs: 900000,
    async execute(args, exec) {
      return service.validateSchema(args.dataset_id, { exec, runs: args.runs })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_update_dataset',
    description: `Update a dataset's description, purpose, schema, status, author or tags.
Use this after validation to apply clarifications: add missing fields, improve descriptions, and then set status="active" to put the dataset into work. Changing the schema increments schema_version and clears the validated marker. Removing fields requires allow_removals=true.`,
    parameters: {
      dataset_id: { type: 'string', required: true, description: 'Dataset id.' },
      name: { type: 'string', description: 'New display name.' },
      description: { type: 'string', description: 'Clarified description.' },
      purpose: { type: 'string', description: 'Clarified purpose.' },
      fields: { type: 'json', description: 'Complete replacement field array, e.g. [{name,type,description,unit,required,scope}]. System fields are added automatically.' },
      status: { type: 'string', enum: ['draft', 'active', 'archived'], description: 'New status; active means the dataset is in work.' },
      author: { type: 'string', description: 'Default author.' },
      tags: { type: 'array', items: { type: 'string' }, description: 'Replacement tags.' },
      allow_removals: { type: 'boolean', description: 'Confirm that dropping existing fields is intended.' },
    },
    output: JSON_OUTPUT,
    async execute(args, exec) {
      return service.updateDataset(args.dataset_id, {
        name: args.name,
        description: args.description,
        purpose: args.purpose,
        schema: args.fields,
        status: args.status,
        author: args.author,
        tags: args.tags,
        allow_removals: args.allow_removals === true,
      }, { exec })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_list_datasets',
    description: 'List datasets in the lake with status, layout, schema version, record/file counts and table row key. Use query to filter by words in the id, name, description or modality.',
    parameters: {
      query: { type: 'string', description: 'Optional text filter.' },
      include_drafts: { type: 'boolean', description: 'Include draft datasets (default true).' },
    },
    output: textOutput((value) => {
      if (!value.datasets?.length) return 'The lake has no matching datasets.'
      const lines = [`${value.datasets.length} dataset(s) under ${value.root}:`]
      for (const dataset of value.datasets) {
        lines.push(`- ${dataset.id} [${dataset.layout}/${dataset.status}] ${dataset.name} — records: ${dataset.counts.records}, files: ${dataset.counts.files}, schema v${dataset.schema_version}${dataset.validated_schema_version ? ` (validated v${dataset.validated_schema_version})` : ''}`)
        if (dataset.description) lines.push(`  ${clip(dataset.description.replace(/\s+/g, ' '), 240)}`)
      }
      return lines.join('\n')
    }),
    async execute(args) {
      const datasets = await service.listDatasets({
        query: args.query,
        includeDrafts: args.include_drafts !== false,
      })
      return { root: service.config.root, datasets }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_inspect_dataset',
    description: 'Inspect one dataset: full schema, organizational fields, counts, table metadata, sample rows, validation summary and recent events. Use this before retrieval or before deciding how to clarify a schema.',
    parameters: {
      dataset_id: { type: 'string', required: true, description: 'Dataset id.' },
      sample_rows: { type: 'integer', description: 'Number of sample rows (default 5, max 50).' },
    },
    output: textOutput((value) => {
      const lines = [
        `Dataset: ${value.dataset.id} — ${value.dataset.name}`,
        `Status: ${value.dataset.status}; layout: ${value.dataset.layout}; records: ${value.dataset.counts.records}; files: ${value.dataset.counts.files}`,
        value.dataset.purpose ? `Purpose: ${value.dataset.purpose}` : '',
        value.dataset.description ? `Description: ${value.dataset.description}` : '',
        '',
        'Schema:',
        value.schema_text,
      ]
      if (value.table) {
        lines.push('', `Table: ${value.table.path} (row key: ${value.table.row_key}, rows: ${value.table.row_count})`)
        lines.push(`Columns: ${value.table.columns.map((column) => column.name).join(', ')}`)
      }
      if (value.validation) {
        lines.push('', `Validation: schema v${value.validation.schema_version}, coverage ${(value.validation.coverage * 100).toFixed(1)}%, ${value.validation.unanswered_questions} unanswered question(s)`)
      }
      if (value.sample_rows?.length) {
        lines.push('', 'Sample rows:', JSON.stringify(value.sample_rows, null, 2))
      }
      return lines.filter((line) => line !== undefined).join('\n')
    }),
    async execute(args) {
      return service.inspectDataset(args.dataset_id, {
        sampleRows: args.sample_rows ?? 5,
      })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_add_data',
    description: `Add data to an existing dataset.
Phase 1 (always): the tool inspects every file/table row, fills the dataset schema from grounded evidence and the researcher's note, and creates a stage. Explicit metadata values override generated ones. If required fields are missing or a value is invalid, the stage is returned and nothing is copied, so the researcher can clarify.
By default, a ready stage is committed immediately. Set dry_run=true (or commit=false) to review first. The file is copied into the lake, the metadata row records id/author/uploaded_at/file_path, and the dataset becomes active unless activate=false.
For table datasets, pass metadata as an array of row records keyed by the table row key to annotate existing rows; the table itself is already registered.
Every stage and commit is logged in the dataset events.`,
    parameters: {
      dataset_id: { type: 'string', required: true, description: 'Target dataset id.' },
      paths: { type: 'array', items: { type: 'string' }, description: 'Files or directories to add (file datasets).' },
      metadata: { type: 'json', description: 'Explicit values: an object applied to all items, an array aligned by file, or a mapping file->values. For table datasets: array of row records with id.' },
      notes: { type: 'string', description: 'Researcher clarification: preparation, acquisition settings, units, what each file is, etc.' },
      dry_run: { type: 'boolean', description: 'Only stage and report; do not copy files or write metadata.' },
      commit: { type: 'boolean', description: 'Commit automatically when the stage is ready (default true).' },
      activate: { type: 'boolean', description: 'Set dataset status=active after a successful commit (default true).' },
      author: { type: 'string', description: 'Author for the new records.' },
      metadata_overrides: { type: 'json', description: 'Values applied at commit time, after the stage proposal. Same shapes as metadata.' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 600000,
    async execute(args, exec) {
      return service.addData(args.dataset_id, {
        paths: asArray(args.paths),
        metadata: args.metadata,
        notes: args.notes,
        dry_run: args.dry_run === true,
        commit: args.commit !== false,
        activate: args.activate !== false,
        author: args.author,
        metadata_overrides: args.metadata_overrides,
      }, { exec })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_commit_add',
    description: `Commit a previously staged add. Use after reviewing a dry-run or after the researcher clarified missing fields.
metadata_overrides may be an object applied to every item, an array matched by file/id, or a mapping keyed by file/id. Commit re-validates every record strictly; if a required field is still missing the commit is refused and nothing is copied.`,
    parameters: {
      dataset_id: { type: 'string', required: true, description: 'Dataset id.' },
      stage_id: { type: 'string', required: true, description: 'Stage id returned by scidatamas_add_data.' },
      metadata_overrides: { type: 'json', description: 'Values to merge into staged metadata.' },
      notes: { type: 'string', description: 'Commit note / clarification for the audit log.' },
      activate: { type: 'boolean', description: 'Set dataset active after commit (default true).' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 300000,
    async execute(args, exec) {
      return service.commitAdd(args.dataset_id, {
        stage_id: args.stage_id,
        metadata_overrides: args.metadata_overrides,
        notes: args.notes,
        activate: args.activate !== false,
      }, { exec })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_get_data',
    description: `Retrieve data by natural-language description.
Selects a dataset (or uses dataset_id), plans a safe JSON filter over the schema, returns matching metadata rows, and resolves file paths. For table datasets rows are table columns merged with sidecar metadata. Set include_preview=true for short text excerpts or image dimensions. No SQL is executed.
If no dataset matches, list the lake and pass dataset_id explicitly.`,
    parameters: {
      query: { type: 'string', required: true, description: 'What data is needed, including scientific conditions.' },
      dataset_id: { type: 'string', description: 'Optional explicit dataset; otherwise the tool selects one.' },
      limit: { type: 'integer', description: 'Maximum rows to return (default 50, max 200).' },
      include_files: { type: 'boolean', description: 'Resolve artifact paths and existence (default true).' },
      include_preview: { type: 'boolean', description: 'Include short text/image facts for returned files (default false).' },
      fields: { type: 'array', items: { type: 'string' }, description: 'Optional field projection.' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 300000,
    async execute(args, exec) {
      return service.getData({
        query: args.query,
        dataset_id: args.dataset_id,
        limit: args.limit ?? 50,
        include_files: args.include_files !== false,
        include_preview: args.include_preview === true,
        fields: asArray(args.fields),
      }, { exec })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_import_external',
    description: `Import a scientific dataset from an external repository (first-class: Zenodo; generic: direct HTTP(S) file URL).
mode="analyze" reads the record and file listing without downloading. mode="import" downloads selected files into lake staging, inspects their formats, generates a metadata schema grounded in the files, creates a dataset (unless dataset_id is supplied), maps record metadata (DOI, license, creators, dates), stages and commits the files. Files are filtered by include/exclude globs and capped by max_files.
Use analyze first for large records. Imported records get provenance fields and the source URL.`,
    parameters: {
      url: { type: 'string', required: true, description: 'Zenodo record URL/DOI or a direct HTTP(S) file URL.' },
      mode: { type: 'string', enum: ['analyze', 'import'], description: 'analyze (default) or import.' },
      dataset_name: { type: 'string', description: 'Name for the new dataset; defaults to the record title.' },
      dataset_id: { type: 'string', description: 'Add imported files to an existing dataset instead of creating one.' },
      description: { type: 'string', description: 'Optional description override; defaults to the record description.' },
      purpose: { type: 'string', description: 'Planned reuse.' },
      rich: { type: 'boolean', description: 'Use DAG-augmented schema generation (default false).' },
      include: { type: 'array', items: { type: 'string' }, description: 'Glob patterns to include, e.g. **/*.tif.' },
      exclude: { type: 'array', items: { type: 'string' }, description: 'Glob patterns to exclude.' },
      max_files: { type: 'integer', description: 'Maximum files to import (default 100).' },
      author: { type: 'string', description: 'Default author.' },
      modality: { type: 'string', description: 'Optional modality.' },
      activate: { type: 'boolean', description: 'Activate the dataset after import (default true).' },
    },
    output: JSON_OUTPUT,
    timeoutMs: 1200000,
    async execute(args, exec) {
      return service.importExternal({
        url: args.url,
        mode: args.mode ?? 'analyze',
        dataset_name: args.dataset_name,
        dataset_id: args.dataset_id,
        description: args.description,
        purpose: args.purpose,
        rich: args.rich === true,
        include: asArray(args.include),
        exclude: asArray(args.exclude),
        max_files: args.max_files,
        author: args.author,
        modality: args.modality,
        activate: args.activate !== false,
      }, { exec })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'scidatamas_status',
    description: 'Show the SciDataMAS data-lake root, storage driver, dataset count, model route availability and configured limits. Use it to diagnose storage or model problems before a long workflow.',
    parameters: {},
    output: JSON_OUTPUT,
    async execute(_args, exec) {
      return service.status({ exec })
    },
  }))
}
