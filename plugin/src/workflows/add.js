/**
 * Add-data workflow. Adding is two-phase: a stage proposes metadata for every
 * file (LLM-filled from inspection and the researcher's note, with explicit
 * values winning), and a commit copies the artifacts and writes rows. A stage
 * with missing required fields is deliberately not committed, so the user can
 * clarify the description or correct values first.
 * @module scidatamas/workflows/add
 */
import { extname } from 'node:path'
import {
  inspectFile,
  inspectSources,
  inspectSummary,
  walkSource,
} from '../inspect.js'
import { normalizeField, SYSTEM_FIELD_NAMES } from '../metadata.js'
import { fillSystem, fillUser } from '../prompts.js'
import { LakeError } from '../lake.js'
import { clip, formatBytes, nowIso, randomId, sanitizeRelPath } from '../util.js'
import { schemaText } from './debate.js'

const FILL_BATCH = 6

/** Normalize the many accepted shapes of explicit metadata into a map. */
export function normalizeExplicitMetadata(metadata, items) {
  const map = new Map()
  if (metadata === undefined || metadata === null) return map
  if (Array.isArray(metadata)) {
    for (const [index, entry] of metadata.entries()) {
      if (!entry || typeof entry !== 'object') continue
      const key = entry.file ?? entry.relative ?? entry.path ?? entry.id ?? items[index]?.relative
      if (!key) continue
      const values = { ...entry }
      delete values.file
      delete values.relative
      delete values.path
      map.set(String(key), values)
    }
    return map
  }
  if (typeof metadata === 'object') {
    // A mapping keyed by file name is distinguishable from one record when
    // its values are objects.
    const entries = Object.entries(metadata)
    if (entries.length > 0 && entries.every(([, value]) => value && typeof value === 'object' && !Array.isArray(value))) {
      for (const [key, value] of entries) map.set(String(key), { ...value })
      return map
    }
    for (const item of items) map.set(item.relative, { ...metadata })
  }
  return map
}

/** Pick a non-colliding relative path for a new artifact. */
async function uniqueRelative(lake, dataset, relative) {
  const clean = sanitizeRelPath(relative)
  const extension = extname(clean)
  const stem = clean.slice(0, Math.max(0, clean.length - extension.length))
  let candidate = clean
  let counter = 2
  while (await lake.storage.exists(lake.datasetKey(dataset.id, 'files', candidate))) {
    candidate = `${stem}-${counter}${extension}`
    counter += 1
    if (counter > 999) throw new LakeError(`too many name collisions for ${relative}`, 'SCIDATAMAS_NAME_COLLISION')
  }
  return candidate
}

/** Collect files from one or more file/directory paths. */
export async function collectAddFiles(paths, { maxFiles, maxDepth }) {
  const items = []
  for (const input of paths ?? []) {
    const walked = await walkSource(input, { maxFiles: Math.max(1, maxFiles - items.length), maxDepth })
    for (const file of walked.files) {
      items.push(file)
      if (items.length >= maxFiles) return { items, truncated: true }
    }
  }
  return { items, truncated: false }
}

/** Fill metadata for a batch of files with one model call. */
export async function fillBatch({ llm, exec, dataset, batch, note }) {
  const records = batch.map((item) => ({
    file: item.relative,
    kind: item.inspection.kind,
    media_type: item.inspection.media_type,
    size: item.inspection.size_human,
    ...(item.inspection.image ? { image: item.inspection.image } : {}),
    ...(item.inspection.table ? { table: item.inspection.table } : {}),
    ...(item.inspection.json ? { json: item.inspection.json } : {}),
    ...(item.inspection.text_preview ? { text_preview: clip(item.inspection.text_preview, 1500) } : {}),
  }))
  const answer = await llm.json({
    system: fillSystem(),
    user: fillUser({
      schemaText: schemaText({ fields: (dataset.schema?.fields ?? []).filter((field) => !field.system) }),
      datasetsDescription: dataset.description,
      records,
      note,
    }),
    exec,
    purpose: 'add.fill',
    maxTokens: 6144,
  })
  const source = Array.isArray(answer.value?.records)
    ? answer.value.records
    : Array.isArray(answer.value)
      ? answer.value
      : []
  const byFile = new Map()
  for (const record of source) {
    const key = String(record?.file ?? record?.relative ?? '')
    if (!key) continue
    const values = record?.values && typeof record.values === 'object'
      ? { ...record.values }
      : { ...record }
    delete values.file
    delete values.relative
    delete values.path
    if (record?.confidence !== undefined) values.confidence = record.confidence
    if (record?.evidence !== undefined) values.evidence = record.evidence
    byFile.set(key, values)
  }
  return byFile
}

/** Build the proposal for one item and validate it partially. */
export function proposeItem({ lake, dataset, item, values, author }) {
  const plannedPath = item.relative
  const cleaned = {}
  const unknown = []
  const fieldNames = new Set((dataset.schema?.fields ?? []).map((field) => field.name))
  for (const [key, value] of Object.entries(values ?? {})) {
    if (key === 'file_path') continue
    if (!fieldNames.has(key)) {
      unknown.push(key)
      continue
    }
    if (value !== undefined && value !== null && value !== '') cleaned[key] = value
  }
  const validated = lake.validateRecords(
    dataset,
    [{ ...cleaned, file_path: plannedPath }],
    { author, partial: true },
  )
  const prepared = validated.prepared[0]
  const missing = prepared?.missing ?? []
  return {
    relative: plannedPath,
    source_path: item.path,
    size: item.size,
    size_human: formatBytes(item.size),
    media_type: item.inspection.media_type,
    kind: item.inspection.kind,
    metadata: prepared?.record ?? { ...cleaned, file_path: plannedPath },
    missing,
    unknown,
    confidence: values?.confidence,
    evidence: values?.evidence,
    error: validated.errors[0]?.issues?.map((issue) => `${issue.field} ${issue.error}`).join('; '),
  }
}

/** Stage an add operation without copying artifacts. */
export async function stageAddWorkflow({ lake, llm, config, exec, dataset, input }) {
  const paths = Array.isArray(input.paths) ? input.paths.filter(Boolean) : input.paths ? [input.paths] : []
  const note = String(input.notes ?? '')
  const author = input.author ?? dataset.defaults?.author ?? config.author
  const stageId = randomId('stage')
  const warnings = []

  if (dataset.layout === 'table') {
    return stageTableMetadata({ lake, config, dataset, input, author, stageId, note })
  }

  if (paths.length === 0) {
    throw new LakeError('paths is required: point to one or more files or directories to add', 'SCIDATAMAS_BAD_INPUT')
  }
  const collected = await collectAddFiles(paths, { maxFiles: config.maxFilesPerAdd, maxDepth: 8 })
  if (collected.items.length === 0) throw new LakeError('no files found in the supplied paths', 'SCIDATAMAS_NO_FILES')
  if (collected.truncated) warnings.push(`only the first ${config.maxFilesPerAdd} files were considered`)

  const explicit = normalizeExplicitMetadata(input.metadata, collected.items)
  const items = []
  for (const [index, file] of collected.items.entries()) {
    let inspection
    try {
      inspection = await inspectFile(file.path)
    } catch (error) {
      inspection = {
        path: file.path,
        name: file.name,
        kind: 'binary',
        media_type: 'application/octet-stream',
        size: file.size,
        size_human: formatBytes(file.size),
        error: error.message,
      }
    }
    const relative = await uniqueRelative(lake, dataset, file.relative ?? file.name)
    items.push({ ...file, relative, inspection, index })
  }

  const filledByFile = new Map()
  for (let offset = 0; offset < items.length; offset += FILL_BATCH) {
    const batch = items.slice(offset, offset + FILL_BATCH)
    try {
      const filled = await fillBatch({ llm, exec, dataset, batch, note })
      for (const [file, values] of filled) filledByFile.set(file, values)
    } catch (error) {
      warnings.push(`metadata fill failed for ${batch.length} file(s): ${error.message}`)
    }
  }

  const proposed = []
  for (const item of items) {
    const explicitValues = explicit.get(item.relative) ?? explicit.get(item.name) ?? explicit.get(item.path) ?? {}
    const filled = filledByFile.get(item.relative) ?? {}
    const values = { ...filled, ...explicitValues }
    proposed.push(proposeItem({ lake, dataset, item, values, author }))
  }
  const ready = proposed.every((item) => !item.error && item.missing.length === 0)
  const stage = {
    stage_id: stageId,
    dataset_id: dataset.id,
    created_at: nowIso(),
    layout: 'files',
    note,
    author,
    ready,
    items: proposed,
    warnings,
  }
  await lake.saveStage(dataset, stage)
  await lake.recordEvent(dataset, 'data_staged', {
    stage_id: stageId,
    files: proposed.length,
    ready,
    missing: proposed.reduce((sum, item) => sum + item.missing.length, 0),
  })
  return stage
}

/** Table datasets: annotate rows by row key rather than copying a new table. */
async function stageTableMetadata({ lake, config, dataset, input, author, stageId, note }) {
  if (!dataset.table) {
    throw new LakeError(
      'this table dataset has no registered table; create it with scidatamas_create_dataset and table_path',
      'SCIDATAMAS_NO_TABLE',
    )
  }
  const raw = input.metadata ?? input.row_metadata
  const rows = []
  if (Array.isArray(raw)) rows.push(...raw)
  else if (raw && typeof raw === 'object') {
    if (raw.rows && Array.isArray(raw.rows)) rows.push(...raw.rows)
    else {
      for (const [key, value] of Object.entries(raw)) {
        if (value && typeof value === 'object') rows.push({ id: key, ...value })
      }
    }
  }
  if (rows.length === 0) {
    return {
      stage_id: stageId,
      dataset_id: dataset.id,
      created_at: nowIso(),
      layout: 'table',
      note,
      author,
      ready: true,
      items: [],
      warnings: [
        'The table is already registered and its rows are queryable. Pass metadata as an array of row records (each with the row key field id) to annotate specific rows.',
      ],
    }
  }
  const items = rows.map((row) => {
    const id = row.id ?? row[dataset.table.row_key]
    if (id === undefined || id === null || String(id).trim() === '') {
      throw new LakeError('every table row annotation needs an id equal to the table row key', 'SCIDATAMAS_BAD_ROW')
    }
    const values = { ...row, id: String(id) }
    const validated = lake.validateRecords(dataset, [values], { author, partial: true })
    const prepared = validated.prepared[0]
    return {
      id: String(id),
      metadata: prepared?.record ?? values,
      missing: prepared?.missing ?? [],
      unknown: validated.prepared[0]?.unknown ?? [],
      error: validated.errors[0]?.issues?.map((issue) => `${issue.field} ${issue.error}`).join('; '),
    }
  })
  const ready = items.every((item) => !item.error && item.missing.length === 0)
  const stage = {
    stage_id: stageId,
    dataset_id: dataset.id,
    created_at: nowIso(),
    layout: 'table',
    note,
    author,
    ready,
    items,
    warnings: [],
  }
  await lake.saveStage(dataset, stage)
  await lake.recordEvent(dataset, 'row_metadata_staged', {
    stage_id: stageId,
    rows: items.length,
    ready,
  })
  return stage
}

/** Apply override values from a commit call to one staged item. */
function overridesFor(overrides, item, index) {
  if (!overrides) return {}
  if (Array.isArray(overrides)) {
    const byKey = overrides.find((entry) => {
      if (!entry || typeof entry !== 'object') return false
      const key = entry.file ?? entry.relative ?? entry.id
      return key !== undefined && [item.relative, item.id, item.source_path].includes(String(key))
    })
    if (byKey) {
      const copy = { ...byKey }
      delete copy.file
      delete copy.relative
      return copy
    }
    return overrides[index] && typeof overrides[index] === 'object' ? overrides[index] : {}
  }
  if (typeof overrides === 'object') {
    if (item.id && overrides[item.id] && typeof overrides[item.id] === 'object') return overrides[item.id]
    if (item.relative && overrides[item.relative] && typeof overrides[item.relative] === 'object') return overrides[item.relative]
    return overrides
  }
  return {}
}

/** Re-validate one item after overrides. */
function revalidate(lake, dataset, item, values, author) {
  const validated = lake.validateRecords(dataset, [values], {
    author,
    partial: false,
    filePath: item.relative ?? values.file_path,
  })
  if (validated.errors.length > 0) {
    throw new LakeError(
      `metadata for "${item.relative ?? item.id}" is invalid: ${validated.errors[0].issues.map((issue) => `${issue.field} ${issue.error}`).join('; ')}`,
      'SCIDATAMAS_BAD_RECORD',
    )
  }
  if (validated.missing.length > 0) {
    throw new LakeError(
      `metadata for "${item.relative ?? item.id}" is missing required field(s): ${validated.missing[0].fields.join(', ')}. Add them with metadata_overrides or clarify the note.`,
      'SCIDATAMAS_MISSING_FIELDS',
    )
  }
  return validated.prepared[0].record
}

/** Commit a stage: copy artifacts and write metadata rows atomically enough. */
export async function commitStageWorkflow({ lake, config, dataset, stage, overrides, notes, activate }) {
  if (!stage.ready && stage.items.some((item) => item.error)) {
    throw new LakeError('the stage contains invalid records; fix them before committing', 'SCIDATAMAS_BAD_STAGE')
  }
  const author = stage.author ?? dataset.defaults?.author ?? config.author
  if (stage.layout === 'table') {
    const records = []
    for (const [index, item] of stage.items.entries()) {
      const override = overridesFor(overrides, item, index)
      const values = { ...(item.metadata ?? {}), ...override, id: item.id }
      records.push(revalidate(lake, dataset, item, values, author))
    }
    const added = await lake.appendRecords(dataset, records, { mode: 'upsert' })
    if (activate !== false) dataset.status = 'active'
    await lake.saveDataset(dataset)
    await lake.recordEvent(dataset, 'data_committed', {
      stage_id: stage.stage_id,
      rows: added.length,
      notes: clip(notes ?? stage.note, 2000),
      overrides: Boolean(overrides),
    })
    await lake.deleteStage(dataset, stage.stage_id)
    return { committed: added.length, layout: 'table', dataset: lake.summaryOf(dataset) }
  }

  const records = []
  for (const [index, item] of stage.items.entries()) {
    const override = overridesFor(overrides, item, index)
    const values = {
      ...(item.metadata ?? {}),
      ...override,
    }
    const record = revalidate(lake, dataset, item, values, author)
    record.file_path = item.relative
    records.push(record)
  }
  // Copy only after every record validated, so a bad row cannot leave a
  // half-added dataset.
  for (const item of stage.items) {
    await lake.putFile(dataset, item.source_path, item.relative)
  }
  const added = await lake.appendRecords(dataset, records, { mode: 'append' })
  await lake.refreshCounts(dataset)
  if (activate !== false) dataset.status = 'active'
  await lake.saveDataset(dataset)
  await lake.recordEvent(dataset, 'data_committed', {
    stage_id: stage.stage_id,
    files: added.length,
    notes: clip(notes ?? stage.note, 2000),
    overrides: Boolean(overrides),
  })
  await lake.deleteStage(dataset, stage.stage_id)
  return {
    committed: added.length,
    layout: 'files',
    files: added.map((record) => ({ id: record.id, file_path: record.file_path, author: record.author })),
    dataset: lake.summaryOf(dataset),
  }
}

/** End-to-end add used by the tool. */
export async function addDataWorkflow({ lake, llm, config, exec, dataset, input }) {
  const stage = await stageAddWorkflow({ lake, llm, config, exec, dataset, input })
  if (stage.items.length === 0) {
    return {
      committed: false,
      stage,
      ready: true,
      message: 'Nothing to stage: the table is already registered. Pass row annotations as metadata to update sidecar rows.',
    }
  }
  const autoCommit = input.commit !== false && input.dry_run !== true
  if (!autoCommit) {
    return {
      committed: false,
      stage,
      ready: stage.ready,
      message: stage.ready
        ? 'Stage is ready. Call scidatamas_commit_add with this stage_id to copy data and write metadata.'
        : 'Stage has missing or invalid fields. Clarify the description or provide metadata, then commit.',
    }
  }
  if (!stage.ready) {
    return {
      committed: false,
      stage,
      ready: false,
      message: 'Data was not committed because some required fields are missing. Supply metadata_overrides or a clarification note, then commit this stage.',
    }
  }
  const result = await commitStageWorkflow({
    lake,
    config,
    dataset,
    stage,
    overrides: input.metadata_overrides,
    notes: input.notes,
    activate: input.activate,
  })
  return { ...result, stage, committed: true }
}
