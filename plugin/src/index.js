/**
 * SciDataMAS DSH plugin entry.
 *
 * Mounts a local-first scientific data lake and a set of model-facing tools:
 * dataset creation (single-call and DAG), debate-based schema validation,
 * data addition with staged human review, natural-language retrieval, and
 * external import from Zenodo or a direct URL.
 *
 * @module scidatamas
 */
import z from '@deepseek-ai/schemastery'
import { DEFAULTS } from './defaults.js'
import { SciDataMAS } from './service.js'
import { registerTools } from './tools.js'
import { registerWebApi } from './web-api.js'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'scidatamas'

/** Services this plugin needs before it can register tools. */
export const inject = ['tools', 'systemPrompt', 'llm']

/** Loader configuration schema. */
export const Config = z.object({
  root: z.string().default(DEFAULTS.root),
  author: z.string().default(DEFAULTS.author),
  provider: z.string().default(DEFAULTS.provider),
  model: z.string().default(DEFAULTS.model),
  maxSchemaFields: z.number().step(1).min(10).default(DEFAULTS.maxSchemaFields),
  maxDagNodes: z.number().step(1).min(3).default(DEFAULTS.maxDagNodes),
  dagConcurrency: z.number().step(1).min(1).max(8).default(DEFAULTS.dagConcurrency),
  debateRuns: z.number().step(1).min(1).max(5).default(DEFAULTS.debateRuns),
  maxDebateRuns: z.number().step(1).min(1).max(10).default(DEFAULTS.maxDebateRuns),
  debateRoles: z.number().step(1).min(1).max(8).default(DEFAULTS.debateRoles),
  debateQuestionsPerRole: z.number().step(1).min(1).max(10).default(DEFAULTS.debateQuestionsPerRole),
  maxFileBytes: z.number().step(1).min(1024).default(DEFAULTS.maxFileBytes),
  maxDownloadBytes: z.number().step(1).min(1024).default(DEFAULTS.maxDownloadBytes),
  maxFilesPerAdd: z.number().step(1).min(1).max(5000).default(DEFAULTS.maxFilesPerAdd),
  maxRowsScan: z.number().step(1).min(1).default(DEFAULTS.maxRowsScan),
  maxPromptChars: z.number().step(1).min(1000).default(DEFAULTS.maxPromptChars),
  allowNetwork: z.boolean().default(DEFAULTS.allowNetwork),
  allowPrivateHosts: z.boolean().default(DEFAULTS.allowPrivateHosts),
  requestTimeoutMs: z.number().step(1).min(1000).default(DEFAULTS.requestTimeoutMs),
  llmRetries: z.number().step(1).min(0).max(5).default(DEFAULTS.llmRetries),
  logLlmCalls: z.boolean().default(DEFAULTS.logLlmCalls),
  logMaxChars: z.number().step(1).min(1000).default(DEFAULTS.logMaxChars),
  storageDriver: z.union([z.const('local'), z.const('s3'), z.const('synology')]).default(DEFAULTS.storageDriver),
  storagePrefix: z.string().default(DEFAULTS.storagePrefix),
})

/** Instructions appended to the agent's system prompt. */
function instructionText(config) {
  return `## Scientific data lake (SciDataMAS)

A SciDataMAS data lake is available at \`${config.root}\` (storage: ${config.storageDriver}). Use its tools whenever the user works with scientific datasets.

Workflow:
1. **Create** with \`scidatamas_create_dataset\` for a compact single-call schema. Use \`scidatamas_create_dataset_dag\` when the experiment has multi-step provenance (preparation -> capture -> processing) or the user asks for rich/detailed metadata. Both tools inspect supplied example files; pass real paths so the schema is grounded.
2. **Validate** with \`scidatamas_validate_schema\` when metadata quality matters (default 3 debate runs). It returns useful fields, unused fields, unanswered reviewer questions, and clarification requests. Do not silently discard clarifications: summarize them and ask the user which fields to add.
3. **Refine** with \`scidatamas_update_dataset\` (description, purpose, fields, status). A dataset starts as a draft; set status="active" only after review.
4. **Add data** with \`scidatamas_add_data\`. It stages metadata before copying. If required fields are missing, nothing is committed: ask the user for the missing facts (or use \`ask_user_question\`), then call \`scidatamas_commit_add\` with the corrections. Never invent metadata to make a stage ready.
5. **Retrieve** with \`scidatamas_get_data\`. Explain which dataset and fields were used, and share resolved file paths.
6. **Import** with \`scidatamas_import_external\`: \`mode="analyze"\` for a dry look at a Zenodo record, \`mode="import"\` to download, inspect, create/annotate the dataset, and commit. Use include/exclude globs and max_files for large records.

Tabular data: use \`layout="table"\` with \`table_path\`. The table stays the canonical artifact; one metadata row per table row is stored as a sidecar keyed by the row key. Add table row annotations by passing \`metadata\` as an array of row records (each with \`id\` equal to the row key). Do not invent a separate copy of the table.

Reserved organizational fields are added automatically: id, author, uploaded_at, file_path, source_url. Do not generate fields with these names.

Storage is local today. The storage seam supports S3 and Synology backends; do not claim remote storage is active unless \`scidatamas_status\` reports it.

Before a long or expensive workflow, state the plan briefly. After creation or import, show the dataset id, layout, field count, and whether the schema was validated.`
}

/** Activate the plugin. */
export async function apply(ctx, config) {
  const resolved = { ...DEFAULTS, ...config }
  if (!resolved.root || typeof resolved.root !== 'string') throw new Error('scidatamas: root must be a non-empty path')
  if (resolved.provider && !resolved.model) throw new Error('scidatamas: provider and model must be configured together')
  if (resolved.model && !resolved.provider) throw new Error('scidatamas: provider and model must be configured together')

  const service = new SciDataMAS({ ctx, config: resolved })
  await service.init()
  registerTools(ctx, service)

  ctx.inject(['webServer', 'connection'], (webCtx) => {
    registerWebApi(webCtx, service)
  })

  ctx.systemPrompt.section({
    name: 'tool:scidatamas',
    order: 150,
    text: instructionText(resolved),
  })

  ctx.logger?.info?.(`SciDataMAS data lake ready at ${resolved.root} (${resolved.storageDriver})`)
}

export { SciDataMAS }
