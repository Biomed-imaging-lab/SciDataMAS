/**
 * Dataset-creation workflow. Single-call generation produces a compact schema
 * from a description and file evidence; the rich variant delegates to the DAG
 * workflow in `dag.js`.
 * @module scidatamas/workflows/create
 */
import { inspectSources, inspectSummary } from '../inspect.js'
import { normalizeSchema } from '../metadata.js'
import {
  singleCallSystem,
  singleCallUser,
  tableSchemaSystem,
  tableSchemaUser,
} from '../prompts.js'
import { LakeError } from '../lake.js'
import { readTable } from '../metadata.js'
import { clip, formatBytes } from '../util.js'

/** Build the prompt-visible dossier of a tabular artifact. */
export function tableDossier(table, maxSamples = 5) {
  const samples = table.rows.slice(0, maxSamples)
  return JSON.stringify({
    row_count_scanned: table.rows.length,
    delimiter: table.delimiter ?? 'csv',
    columns: table.columns.map((column) => ({
      name: column.name,
      inferred_type: column.type,
      examples: samples.map((row) => row[column.name]).filter((value) => value !== '' && value !== undefined).slice(0, 3),
    })),
    sample_rows: samples,
  }, null, 2)
}

/** Normalize LLM schema output into the lake's schema object. */
export function schemaFromAnswer(answer, options) {
  const raw = answer?.fields ?? answer?.schema ?? answer?.metadata_schema ?? answer
  const normalized = normalizeSchema(raw, options)
  if (normalized.fields.filter((field) => !field.system).length === 0) {
    throw new LakeError('the model returned no usable metadata fields', 'SCIDATAMAS_EMPTY_SCHEMA')
  }
  return normalized
}

/** Generate a compact schema from a description and optional evidence. */
export async function generateSingleCallSchema({ llm, config, exec, input, evidence, columnsText }) {
  const user = singleCallUser({
    name: input.name,
    description: input.description,
    purpose: input.purpose,
    layout: input.layout,
    columnsText,
    evidence,
  })
  const answer = await llm.json({
    system: singleCallSystem(),
    user,
    exec,
    purpose: 'create.single_call',
    maxTokens: 8192,
  })
  return {
    schema: schemaFromAnswer(answer.value, {
      layout: input.layout,
      maxFields: config.maxSchemaFields,
    }),
    generated: {
      name: answer.value?.name,
      description: answer.value?.description,
    },
  }
}

/** Generate a schema for an existing table by describing its columns. */
export async function generateTableSchema({ llm, config, exec, input, table }) {
  const dossier = tableDossier(table)
  const answer = await llm.json({
    system: tableSchemaSystem(),
    user: tableSchemaUser({
      name: input.name,
      description: input.description,
      purpose: input.purpose,
      tablePath: input.table_path,
      tableDossier: dossier,
    }),
    exec,
    purpose: 'create.table',
    maxTokens: 8192,
  })
  const schema = schemaFromAnswer(answer.value, {
    layout: 'table',
    columns: table.columns,
    maxFields: config.maxSchemaFields,
  })
  return {
    schema,
    generated: {
      description: answer.value?.description,
    },
    table,
  }
}

/** Create a dataset (single-call or DAG). */
export async function createDatasetWorkflow({
  lake,
  llm,
  config,
  exec,
  input,
  rich = false,
  createDagSchema,
  validateSchema,
}) {
  const layout = input.layout === 'table' ? 'table' : 'files'
  if (!input.name?.trim()) throw new LakeError('dataset name is required', 'SCIDATAMAS_BAD_INPUT')
  if (!input.description?.trim()) throw new LakeError('dataset description is required', 'SCIDATAMAS_BAD_INPUT')
  if (layout === 'table' && !input.table_path) {
    throw new LakeError(
      'layout="table" requires table_path pointing to a CSV/TSV/JSON/JSONL file. Create a files dataset and add the table later if the artifact is not ready yet.',
      'SCIDATAMAS_TABLE_REQUIRED',
    )
  }

  const examplePaths = Array.isArray(input.example_paths)
    ? input.example_paths.filter(Boolean)
    : input.example_paths ? [input.example_paths] : []
  const inspection = examplePaths.length > 0 ? await inspectSources(examplePaths, { maxFiles: 60 }) : { groups: [], files: [] }
  let table
  if (layout === 'table') {
    table = await readTable(input.table_path, { maxRows: config.maxRowsScan })
    if (table.columns.length === 0) throw new LakeError('table has no columns', 'SCIDATAMAS_EMPTY_TABLE')
    inspection.files.push({
      path: input.table_path,
      name: input.table_path.split('/').pop(),
      kind: 'table',
      size: 0,
      size_human: formatBytes(0),
      table: {
        columns: table.columns.map((column) => column.name),
        sample_rows: table.rows.slice(0, 3).map((row) => Object.fromEntries(table.columns.map((column) => [column.name, row[column.name]]))),
      },
    })
  }
  const evidence = inspection.files.length > 0 ? inspectSummary(inspection) : ''

  let schema
  let generated = {}
  if (rich) {
    if (typeof createDagSchema !== 'function') throw new Error('rich generation is not wired')
    const dagResult = await createDagSchema({
      llm,
      config,
      exec,
      input: { ...input, layout },
      evidence,
    })
    schema = dagResult.schema
    generated = dagResult.generated
  } else if (layout === 'table') {
    const result = await generateTableSchema({
      llm,
      config,
      exec,
      input: { ...input, layout },
      table,
    })
    schema = result.schema
    generated = result.generated
  } else {
    const result = await generateSingleCallSchema({
      llm,
      config,
      exec,
      input: { ...input, layout },
      evidence,
    })
    schema = result.schema
    generated = result.generated
  }

  const dataset = await lake.createDataset({
    id: input.id ?? input.name,
    name: input.name,
    description: input.description,
    purpose: input.purpose,
    layout,
    modality: input.modality,
    provenance: input.provenance ?? (input.source_url ? 'external' : 'real'),
    author: input.author,
    tags: input.tags,
    schema,
    status: input.activate ? 'active' : 'draft',
    source: input.source_url ? { kind: 'url', url: input.source_url } : null,
  })

  if (layout === 'table') {
    const registered = await lake.registerTable(dataset, input.table_path, { rowKey: input.row_key })
    dataset.table = registered
    dataset.schema = normalizeSchema(dataset.schema, {
      layout: 'table',
      columns: registered.columns,
      maxFields: config.maxSchemaFields,
    })
    dataset.counts = { ...(dataset.counts ?? {}), records: registered.row_count }
    await lake.saveDataset(dataset)
    schema = dataset.schema
  }

  let validation
  if (input.validate && typeof validateSchema === 'function') {
    validation = await validateSchema({
      lake,
      llm,
      config,
      exec,
      dataset,
      runs: input.debate_runs,
    })
  }

  await lake.recordEvent(dataset, 'schema_generated', {
    rich,
    layout,
    fields: schema.fields.length,
    examples: examplePaths.length,
  })

  return {
    dataset: lake.summaryOf(dataset),
    schema,
    system_fields: schema.fields.filter((field) => field.system),
    generated,
    evidence: clip(evidence, 6000),
    table: dataset.table
      ? {
        path: dataset.table.path,
        row_key: dataset.table.row_key,
        rows: dataset.table.row_count,
        columns: dataset.table.columns.map((column) => column.name),
        row_key_fallback: dataset.table.row_key_fallback,
      }
      : null,
    validation,
    next_steps: [
      'Review the schema; refine it with scidatamas_update_dataset if needed.',
      'Run scidatamas_validate_schema (debate) to discover missing fields and clarification questions.',
      'Add data with scidatamas_add_data, then activate the dataset.',
    ],
  }
}
