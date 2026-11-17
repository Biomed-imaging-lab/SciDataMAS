/**
 * Retrieval workflow. The planner chooses a dataset and a safe JSON filter;
 * this module evaluates it, resolves artifact paths, and optionally returns
 * short text previews.
 * @module scidatamas/workflows/query
 */
import { inspectFile } from '../inspect.js'
import { runQuery, rankDatasets, rankRecords, validateFilter } from '../filter.js'
import { querySystem, queryUser, selectDatasetSystem, selectDatasetUser } from '../prompts.js'
import { LakeError } from '../lake.js'
import { clip } from '../util.js'

/** Compact catalog used for model-based dataset selection. */
export async function datasetCatalog(lake, limit = 25) {
  const summaries = await lake.listDatasets({ includeDrafts: true })
  const catalog = []
  for (const summary of summaries.slice(0, limit)) {
    try {
      const manifest = await lake.getDataset(summary.id)
      catalog.push({
        id: manifest.id,
        name: manifest.name,
        description: clip(manifest.description, 1200),
        purpose: clip(manifest.purpose, 500),
        layout: manifest.layout,
        status: manifest.status,
        fields: (manifest.schema?.fields ?? [])
          .filter((field) => !field.system)
          .slice(0, 80)
          .map((field) => `${field.name}:${field.type}`),
        table: manifest.table ? { row_key: manifest.table.row_key, row_count: manifest.table.row_count } : null,
      })
    } catch {
      // a broken manifest should not block retrieval from healthy datasets
    }
  }
  return catalog
}

/** Select a dataset with the model, falling back to lexical ranking. */
export async function selectDataset({ lake, llm, exec, request, datasetId }) {
  if (datasetId) {
    const manifest = await lake.getDataset(datasetId)
    return { dataset: manifest, reason: 'dataset_id supplied by the caller', confidence: 1 }
  }
  const summaries = await lake.listDatasets({ includeDrafts: true })
  if (summaries.length === 0) throw new LakeError('the lake has no datasets yet', 'SCIDATAMAS_EMPTY_LAKE')
  if (summaries.length === 1) {
    return { dataset: await lake.getDataset(summaries[0].id), reason: 'only one dataset exists', confidence: 1 }
  }
  const catalog = await datasetCatalog(lake)
  try {
    const answer = await llm.json({
      system: selectDatasetSystem(),
      user: selectDatasetUser({ datasets: catalog, request }),
      exec,
      purpose: 'query.select_dataset',
      maxTokens: 1024,
    })
    const id = answer.value?.dataset_id
    if (id && summaries.some((summary) => summary.id === id)) {
      return {
        dataset: await lake.getDataset(id),
        reason: String(answer.value?.reason ?? ''),
        confidence: Number(answer.value?.confidence ?? 0.5),
      }
    }
  } catch {
    // fall through to lexical selection
  }
  const ranked = rankDatasets(summaries, request)
  if (!ranked[0] || ranked[0].score === 0) {
    throw new LakeError(
      `could not choose a dataset for this request. Available: ${summaries.map((summary) => summary.id).join(', ')}. Pass dataset_id explicitly.`,
      'SCIDATAMAS_NO_DATASET_MATCH',
    )
  }
  return {
    dataset: await lake.getDataset(ranked[0].dataset.id),
    reason: `lexical match (score ${ranked[0].score})`,
    confidence: 0.3,
  }
}

/** Plan a filter, validating field names and repairing one bad answer. */
export async function planQuery({ lake, llm, exec, dataset, request, limit }) {
  const allowed = (dataset.schema?.fields ?? []).map((field) => field.name)
  const summary = {
    id: dataset.id,
    name: dataset.name,
    description: dataset.description,
    purpose: dataset.purpose,
    layout: dataset.layout,
    fields: (dataset.schema?.fields ?? []).map((field) => ({
      name: field.name,
      type: field.type,
      scope: field.scope,
      description: clip(field.description, 240),
    })),
    table: dataset.table ? { row_key: dataset.table.row_key, row_count: dataset.table.row_count } : null,
    sample: dataset.layout === 'files' ? 'one row per artifact' : 'one row per table row',
  }
  let correction = ''
  let lastError
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const answer = await llm.json({
        system: querySystem(),
        user: `${queryUser({ datasets: [summary], request, defaultLimit: limit })}${correction ? `\n\n${correction}` : ''}`,
        exec,
        purpose: 'query.plan',
        maxTokens: 3072,
      })
      const value = answer.value ?? {}
      const filter = value.filter === undefined ? null : value.filter
      validateFilter(filter, allowed)
      const fields = Array.isArray(value.fields)
        ? value.fields.map(String).filter((field) => allowed.includes(field))
        : undefined
      return {
        filter,
        fields: fields && fields.length > 0 ? fields : undefined,
        limit: Number.isFinite(value.limit) ? value.limit : limit,
        reasoning: String(value.reasoning ?? ''),
      }
    } catch (error) {
      lastError = error
      correction = `The previous plan was rejected: ${error.message}\nUse only fields listed in the schema and the documented filter grammar.`
    }
  }
  throw lastError
}

/** Resolve artifact paths for returned records. */
export async function resolveFiles({ lake, dataset, rows, includePreview }) {
  const files = []
  for (const row of rows.slice(0, 50)) {
    const relative = dataset.layout === 'table' ? dataset.table?.path : row.file_path
    if (!relative) continue
    const key = dataset.layout === 'table' ? relative : lake.datasetKey(dataset.id, relative)
    const localPath = lake.storage.localPath(key)
    const info = localPath ? await lake.storage.stat(key) : undefined
    const entry = {
      id: row.id,
      file_path: relative,
      storage_uri: lake.storage.uri(key),
      exists: Boolean(info),
      size: info?.size ?? null,
      absolute_path: localPath ?? null,
    }
    if (includePreview && localPath && info?.type === 'file') {
      try {
        const inspected = await inspectFile(localPath, { maxTextChars: 1500 })
        if (inspected.text_preview) entry.preview = clip(inspected.text_preview, 1500)
        if (inspected.image) entry.image = inspected.image
      } catch {
        // preview is best-effort
      }
    }
    files.push(entry)
  }
  return files
}

/** Full retrieval workflow. */
export async function getDataWorkflow({ lake, llm, config, exec, input }) {
  const limit = Math.max(1, Math.min(Number(input.limit) || 50, 200))
  const selection = await selectDataset({
    lake,
    llm,
    exec,
    request: input.query,
    datasetId: input.dataset_id,
  })
  const dataset = selection.dataset
  const rows = dataset.layout === 'table'
    ? await lake.tableRecords(dataset)
    : await lake.readMetadata(dataset)

  let plan
  let usedFallback = false
  try {
    plan = await planQuery({ lake, llm, exec, dataset, request: input.query, limit })
  } catch (error) {
    usedFallback = true
    const ranked = rankRecords(rows, input.query)
    plan = {
      filter: null,
      fields: undefined,
      limit,
      reasoning: `model planning failed (${error.message}); used lexical ranking`,
      fallback_rows: ranked.filter((item) => item.score > 0).map((item) => item.record),
    }
  }

  if (Array.isArray(input.fields) && input.fields.length > 0) {
    const allowed = new Set((dataset.schema?.fields ?? []).map((field) => field.name))
    const explicit = input.fields.filter((field) => allowed.has(field))
    if (explicit.length > 0) plan.fields = explicit
  }
  let result
  if (plan.fallback_rows) {
    const seen = new Set()
    const unique = plan.fallback_rows.filter((row) => {
      if (seen.has(row.id)) return false
      seen.add(row.id)
      return true
    })
    const projected = plan.fields
      ? unique.slice(0, limit).map((row) => Object.fromEntries(plan.fields.filter((field) => field in row).map((field) => [field, row[field]])))
      : unique.slice(0, limit)
    result = { rows: projected, matched: unique.length, returned: projected.length }
  } else {
    result = runQuery(rows, {
      filter: plan.filter,
      fields: plan.fields,
      limit,
      sort: plan.sort,
    })
  }

  if (input.include_files !== false && plan.fields) {
    for (const required of ['id', 'file_path']) {
      if (!plan.fields.includes(required)) plan.fields.push(required)
    }
  }
  const files = input.include_files === false
    ? []
    : await resolveFiles({
      lake,
      dataset,
      rows: result.rows,
      includePreview: input.include_preview === true,
    })

  await lake.recordEvent(dataset, 'data_retrieved', {
    query: clip(input.query, 2000),
    filter: plan.filter,
    matched: result.matched,
    returned: result.returned,
    fallback: usedFallback,
  })

  return {
    dataset: lake.summaryOf(dataset),
    selection: { reason: selection.reason, confidence: selection.confidence },
    plan: {
      filter: plan.filter,
      fields: plan.fields,
      limit: plan.limit ?? limit,
      reasoning: plan.reasoning,
      used_fallback: usedFallback,
    },
    matched: result.matched,
    returned: result.returned,
    rows: result.rows,
    files,
    hints: result.returned === 0
      ? [
        'No rows matched. Try a broader query, inspect the schema with scidatamas_inspect_dataset, or omit dataset_id.',
      ]
      : [],
  }
}
