/**
 * High-level SciDataMAS service. Tools are thin adapters over these methods,
 * which keeps the workflows testable without a DSH runtime.
 * @module scidatamas/service
 */
import { createStorage } from './storage.js'
import { SciDataLake, LakeError } from './lake.js'
import { LlmClient } from './llm.js'
import { commitStageWorkflow, addDataWorkflow, stageAddWorkflow } from './workflows/add.js'
import { createDatasetWorkflow } from './workflows/create.js'
import { generateDagSchema } from './workflows/dag.js'
import { validateSchemaWorkflow } from './workflows/debate.js'
import { getDataWorkflow } from './workflows/query.js'
import { importExternalWorkflow } from './workflows/external.js'
import { clip } from './util.js'

/** Service owning one data lake and the model workflow bindings. */
export class SciDataMAS {
  /**
   * @param {{ctx: object, config: object}} options
   */
  constructor({ ctx, config }) {
    this.ctx = ctx
    this.config = config
    this.storage = createStorage(config)
    this.lake = new SciDataLake({ storage: this.storage, config })
    this.llm = new LlmClient({ ctx, config, storage: this.storage })
    this.ready = this.lake.init()
  }

  /** Wait for storage/catalog initialization. */
  async init() {
    await this.ready
    return this
  }

  /** Create a dataset with single-call or DAG schema generation. */
  async createDataset(input, { exec, rich = false } = {}) {
    await this.init()
    return createDatasetWorkflow({
      lake: this.lake,
      llm: this.llm,
      config: this.config,
      exec,
      input,
      rich,
      createDagSchema: (options) => generateDagSchema(options),
      validateSchema: (options) => validateSchemaWorkflow(options),
    })
  }

  /** Run debate validation against a stored dataset. */
  async validateSchema(datasetId, { exec, runs } = {}) {
    await this.init()
    const dataset = await this.lake.getDataset(datasetId)
    return validateSchemaWorkflow({
      lake: this.lake,
      llm: this.llm,
      config: this.config,
      exec,
      dataset,
      runs,
    })
  }

  /** List datasets, optionally filtered by a text query. */
  async listDatasets({ query, includeDrafts = true } = {}) {
    await this.init()
    return this.lake.listDatasets({ query, includeDrafts })
  }

  /** Inspect a dataset: schema, counts, recent events, sample rows. */
  async inspectDataset(datasetId, { sampleRows = 5, includeEvents = true } = {}) {
    await this.init()
    const dataset = await this.lake.getDataset(datasetId)
    let sample = []
    let table = null
    if (dataset.layout === 'table') {
      const rows = await this.lake.tableRecords(dataset)
      sample = rows.slice(0, Math.max(0, Math.min(sampleRows, 50)))
      table = dataset.table
        ? {
          path: dataset.table.path,
          row_key: dataset.table.row_key,
          row_count: dataset.table.row_count,
          columns: dataset.table.columns,
        }
        : null
    } else {
      const rows = await this.lake.readMetadata(dataset)
      sample = rows.slice(0, Math.max(0, Math.min(sampleRows, 50)))
    }
    let validation
    try {
      validation = await this.storage.readJson(this.lake.datasetKey(dataset.id, 'validation', 'latest.json'))
    } catch {
      validation = undefined
    }
    return {
      dataset: this.lake.summaryOf(dataset),
      schema: dataset.schema,
      schema_text: (dataset.schema?.fields ?? [])
        .map((field) => `- ${field.name} (${field.type}${field.unit ? `, ${field.unit}` : ''})${field.system ? ' [system]' : ''}: ${field.description}`)
        .join('\n'),
      table,
      sample_rows: sample,
      validation: validation
        ? {
          schema_version: validation.schema_version,
          created_at: validation.created_at,
          runs: validation.runs ?? 0,
          coverage: validation.coverage,
          useful_fields: validation.useful_fields?.length ?? 0,
          unused_fields: validation.unused_fields?.length ?? 0,
          unanswered_questions: validation.unanswered_questions?.length ?? 0,
          useful_fields_detail: (validation.useful_fields ?? []).slice(0, 50),
          unused_fields_detail: (validation.unused_fields ?? []).slice(0, 50),
          unanswered_questions_detail: (validation.unanswered_questions ?? []).slice(0, 50),
          clarifications: validation.clarifications ?? [],
          report_path: `datasets/${dataset.id}/validation/latest.json`,
        }
        : null,
      events: includeEvents ? await this.lake.readEvents(dataset, 20) : [],
    }
  }

  /** Update description, purpose, schema, status or tags. */
  async updateDataset(datasetId, patch, { exec } = {}) {
    await this.init()
    if (patch.schema === undefined && Array.isArray(patch.fields)) patch.schema = patch.fields
    const dataset = await this.lake.updateDataset(datasetId, patch)
    if (patch.status === 'active') {
      await this.lake.recordEvent(dataset, 'dataset_activated', { by: 'user' })
    }
    return this.lake.summaryOf(dataset)
  }

  /** Stage an add; optionally auto-commit when ready. */
  async addData(datasetId, input, { exec } = {}) {
    await this.init()
    const dataset = await this.lake.getDataset(datasetId)
    if (input.stage_id) {
      const stage = await this.lake.getStage(dataset, input.stage_id)
      return commitStageWorkflow({
        lake: this.lake,
        config: this.config,
        dataset,
        stage,
        overrides: input.metadata_overrides ?? input.metadata,
        notes: input.notes,
        activate: input.activate,
      })
    }
    return addDataWorkflow({
      lake: this.lake,
      llm: this.llm,
      config: this.config,
      exec,
      dataset,
      input,
    })
  }

  /** Commit an existing stage. */
  async commitAdd(datasetId, input, { exec } = {}) {
    await this.init()
    if (!input.stage_id) throw new LakeError('stage_id is required', 'SCIDATAMAS_BAD_INPUT')
    const dataset = await this.lake.getDataset(datasetId)
    const stage = await this.lake.getStage(dataset, input.stage_id)
    return commitStageWorkflow({
      lake: this.lake,
      config: this.config,
      dataset,
      stage,
      overrides: input.metadata_overrides,
      notes: input.notes,
      activate: input.activate,
    })
  }

  /** Retrieve rows by natural-language query. */
  async getData(input, { exec } = {}) {
    await this.init()
    return getDataWorkflow({
      lake: this.lake,
      llm: this.llm,
      config: this.config,
      exec,
      input,
    })
  }

  /** Analyze or import an external source. */
  async importExternal(input, { exec } = {}) {
    await this.init()
    return importExternalWorkflow({
      lake: this.lake,
      llm: this.llm,
      config: this.config,
      exec,
      input,
      createDataset: (options) => this.createDataset(options.input, { exec, rich: options.rich }),
      stageAdd: (options) => stageAddWorkflow({
        lake: this.lake,
        llm: this.llm,
        config: this.config,
        exec,
        dataset: options.dataset,
        input: options.input,
      }),
      commitStage: (options) => commitStageWorkflow({
        lake: this.lake,
        config: this.config,
        dataset: options.dataset,
        stage: options.stage,
        overrides: options.overrides,
        notes: options.notes,
        activate: options.activate,
      }),
    })
  }

  /** Diagnostics used by tools and humans. */
  async status({ exec } = {}) {
    await this.init()
    return {
      root: this.config.root,
      storage: this.storage.kind,
      datasets: (await this.lake.listDatasets()).length,
      model: await this.llm.status(exec),
      limits: {
        maxFileBytes: this.config.maxFileBytes,
        maxDownloadBytes: this.config.maxDownloadBytes,
        maxSchemaFields: this.config.maxSchemaFields,
        maxDagNodes: this.config.maxDagNodes,
        maxFilesPerAdd: this.config.maxFilesPerAdd,
      },
    }
  }
}

/** Compact human summary used in logs/README examples. */
export function datasetSummaryText(summary) {
  return `${summary.id} [${summary.layout}/${summary.status}] ${summary.name} — ${clip(summary.description, 120)}`
}
