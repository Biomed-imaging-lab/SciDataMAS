/**
 * The data-lake repository: one catalog, many datasets, every artifact behind
 * the storage seam. It owns durable manifests, metadata rows, staging areas,
 * audit events and validation reports. Workflows call this layer; tools call
 * the workflows.
 * @module scidatamas/lake
 */
import { readFile, stat } from 'node:fs/promises'
import { basename, extname, resolve } from 'node:path'
import {
  SYSTEM_FIELDS,
  metadataColumns,
  coerceValue,
  normalizeSchema,
  parseJsonl,
  readTable,
  toCsv,
  toJsonl,
  validateRecord,
} from './metadata.js'
import { KeyedLock, nowIso, randomId, sha256, slugify } from './util.js'

const CATALOG_KEY = 'catalog.json'
const CATALOG_VERSION = 1

/** Raised for expected domain errors that tools should surface verbatim. */
export class LakeError extends Error {
  constructor(message, code = 'SCIDATAMAS_ERROR') {
    super(message)
    this.name = 'LakeError'
    this.code = code
  }
}

/** Dataset repository bound to one storage backend. */
export class SciDataLake {
  /**
   * @param {{storage: object, config: object}} options
   */
  constructor({ storage, config }) {
    this.storage = storage
    this.config = config
    this.lock = new KeyedLock()
    this.catalogCache = undefined
  }

  /** Create the root and a catalog when absent. */
  async init() {
    await this.storage.init()
    if (!(await this.storage.exists(CATALOG_KEY))) {
      const catalog = {
        version: CATALOG_VERSION,
        name: 'SciDataMAS data lake',
        created_at: nowIso(),
        updated_at: nowIso(),
        datasets: [],
      }
      await this.storage.writeJson(CATALOG_KEY, catalog)
      this.catalogCache = catalog
    }
    const datasetsDir = this.key('datasets', '')
    if (!(await this.storage.exists('datasets'))) await this.storage.writeText(`${datasetsDir}.keep`, '')
    if (!(await this.storage.exists('staging'))) await this.storage.writeText('staging/.keep', '')
    if (!(await this.storage.exists('logs'))) await this.storage.writeText('logs/.keep', '')
    return this
  }

  /** Join storage keys under the lake root without a leading slash. */
  key(...parts) {
    return parts.filter((part) => part !== undefined && part !== null && part !== '').join('/')
  }

  datasetKey(datasetId, ...parts) {
    return this.key('datasets', datasetId, ...parts)
  }

  /** Read the catalog, caching the parsed value. */
  async catalog() {
    if (this.catalogCache) return this.catalogCache
    const catalog = await this.storage.readJson(CATALOG_KEY)
    if (!catalog || catalog.version !== CATALOG_VERSION) {
      throw new LakeError(`catalog is missing or has an unsupported version at ${CATALOG_KEY}`, 'SCIDATAMAS_BAD_CATALOG')
    }
    this.catalogCache = catalog
    return catalog
  }

  /** Persist the catalog and refresh the cache. */
  async saveCatalog(catalog) {
    catalog.updated_at = nowIso()
    await this.storage.writeJson(CATALOG_KEY, catalog)
    this.catalogCache = catalog
  }

  /** List dataset summaries, newest first. */
  async listDatasets({ query = '', includeDrafts = true } = {}) {
    const catalog = await this.catalog()
    const needle = String(query ?? '').toLowerCase().trim()
    return catalog.datasets
      .filter((entry) => includeDrafts || entry.status !== 'draft')
      .filter((entry) => {
        if (!needle) return true
        const haystack = `${entry.id} ${entry.name} ${entry.description} ${entry.modality ?? ''} ${entry.layout}`.toLowerCase()
        return needle.split(/\s+/).every((token) => haystack.includes(token))
      })
      .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
  }

  /** Load a manifest or throw a domain error. */
  async getDataset(datasetId) {
    const id = slugify(datasetId, '')
    if (!id) throw new LakeError('dataset_id is empty', 'SCIDATAMAS_BAD_DATASET')
    const manifest = await this.storage.readJson(this.datasetKey(id, 'manifest.json'))
    if (!manifest) throw new LakeError(`dataset "${datasetId}" does not exist`, 'SCIDATAMAS_NOT_FOUND')
    return manifest
  }

  /** Persist one manifest and keep the catalog summary in sync. */
  async saveDataset(manifest) {
    manifest.updated_at = nowIso()
    await this.storage.writeJson(this.datasetKey(manifest.id, 'manifest.json'), manifest)
    await this.syncCatalog(manifest)
    return manifest
  }

  /** Update one catalog entry from a manifest. */
  async syncCatalog(manifest) {
    await this.lock.run('catalog', async () => {
      const catalog = await this.catalog()
      const index = catalog.datasets.findIndex((entry) => entry.id === manifest.id)
      const summary = this.summaryOf(manifest)
      if (index === -1) catalog.datasets.push(summary)
      else catalog.datasets[index] = summary
      await this.saveCatalog(catalog)
    })
  }

  /** Compact catalog entry for listing. */
  summaryOf(manifest) {
    return {
      id: manifest.id,
      name: manifest.name,
      description: manifest.description,
      purpose: manifest.purpose,
      layout: manifest.layout,
      status: manifest.status,
      modality: manifest.modality,
      provenance: manifest.provenance,
      created_at: manifest.created_at,
      updated_at: manifest.updated_at,
      schema_version: manifest.schema_version,
      validated_schema_version: manifest.validated_schema_version ?? null,
      counts: manifest.counts ?? { records: 0, files: 0, bytes: 0 },
      table: manifest.table ? { path: manifest.table.path, row_key: manifest.table.row_key, row_count: manifest.table.row_count } : null,
      tags: manifest.tags ?? [],
    }
  }

  /**
   * Create a dataset manifest and its empty metadata file.
   * @param {object} input
   */
  async createDataset(input) {
    const id = slugify(input.id ?? input.name)
    if (await this.storage.exists(this.datasetKey(id, 'manifest.json'))) {
      throw new LakeError(`dataset "${id}" already exists`, 'SCIDATAMAS_ALREADY_EXISTS')
    }
    const layout = input.layout === 'table' ? 'table' : 'files'
    const schema = normalizeSchema(input.schema, {
      layout,
      columns: input.columns,
      maxFields: this.config.maxSchemaFields,
    })
    const createdAt = nowIso()
    const manifest = {
      id,
      name: String(input.name ?? id),
      description: String(input.description ?? ''),
      purpose: String(input.purpose ?? ''),
      layout,
      status: input.status === 'active' ? 'active' : 'draft',
      modality: String(input.modality ?? ''),
      provenance: String(input.provenance ?? 'real'),
      author: String(input.author ?? this.config.author ?? ''),
      tags: Array.isArray(input.tags) ? input.tags.slice(0, 30).map(String) : [],
      created_at: createdAt,
      updated_at: createdAt,
      schema_version: 1,
      validated_schema_version: null,
      schema,
      table: input.table ?? null,
      source: input.source ?? null,
      counts: { records: 0, files: 0, bytes: 0 },
      defaults: {
        author: String(input.author ?? this.config.author ?? ''),
        uploaded_at: createdAt,
      },
      storage: {
        driver: this.storage.kind,
        root: this.storage.uri(''),
      },
    }
    await this.storage.writeJson(this.datasetKey(id, 'manifest.json'), manifest)
    await this.storage.writeText(this.datasetKey(id, 'metadata.jsonl'), '')
    await this.storage.writeText(this.datasetKey(id, 'metadata.csv'), toCsv([], metadataColumns(schema)))
    await this.syncCatalog(manifest)
    await this.recordEvent(manifest, 'dataset_created', {
      layout,
      fields: schema.fields.length,
      source: input.source ?? null,
    })
    return manifest
  }

  /** Apply a patch to a manifest, bumping schema_version when fields change. */
  async updateDataset(datasetId, patch) {
    return this.lock.run(`dataset:${slugify(datasetId)}`, async () => {
      const manifest = await this.getDataset(datasetId)
      let schemaChanged = false
      if (patch.schema !== undefined) {
        const normalized = normalizeSchema(patch.schema, {
          layout: manifest.layout,
          columns: manifest.table?.columns,
          maxFields: this.config.maxSchemaFields,
        })
        if (!sameSchema(manifest.schema, normalized)) {
          const removed = (manifest.schema?.fields ?? [])
            .filter((field) => !field.system && !normalized.fields.some((next) => next.name === field.name))
            .map((field) => field.name)
          if (removed.length > 0 && patch.allow_removals !== true) {
            throw new LakeError(
              `updating the schema would remove fields (${removed.join(', ')}); pass allow_removals=true to confirm`,
              'SCIDATAMAS_SCHEMA_REMOVAL',
            )
          }
          manifest.schema = normalized
          manifest.schema_version += 1
          manifest.validated_schema_version = null
          schemaChanged = true
        }
      }
      for (const key of ['name', 'description', 'purpose', 'modality', 'provenance', 'status', 'author']) {
        if (patch[key] !== undefined) manifest[key] = String(patch[key])
      }
      if (patch.tags !== undefined) manifest.tags = Array.isArray(patch.tags) ? patch.tags.map(String) : []
      if (patch.defaults !== undefined) manifest.defaults = { ...manifest.defaults, ...patch.defaults }
      if (patch.status !== undefined && !['draft', 'active', 'archived'].includes(manifest.status)) {
        throw new LakeError('status must be draft, active or archived', 'SCIDATAMAS_BAD_STATUS')
      }
      manifest.updated_at = nowIso()
      await this.saveDataset(manifest)
      await this.recordEvent(manifest, 'dataset_updated', {
        schema_changed: schemaChanged,
        schema_version: manifest.schema_version,
        status: manifest.status,
      })
      return manifest
    })
  }

  /** Read all metadata rows (sidecar rows for table datasets). */
  async readMetadata(dataset) {
    const key = this.datasetKey(dataset.id, 'metadata.jsonl')
    if (!(await this.storage.exists(key))) return []
    const text = await this.storage.readText(key)
    const { records, errors } = parseJsonl(text)
    if (errors.length > 0) {
      throw new LakeError(
        `metadata file contains ${errors.length} malformed line(s); first at line ${errors[0].line}`,
        'SCIDATAMAS_BAD_METADATA',
      )
    }
    return records
  }

  /** Atomically replace metadata rows and refresh CSV/counts. */
  async writeMetadata(dataset, records) {
    await this.lock.run(`dataset:${dataset.id}`, async () => {
      const sorted = [...records].sort((a, b) => String(a.id).localeCompare(String(b.id)))
      await this.storage.writeText(this.datasetKey(dataset.id, 'metadata.jsonl'), toJsonl(sorted))
      await this.storage.writeText(
        this.datasetKey(dataset.id, 'metadata.csv'),
        toCsv(sorted, metadataColumns(dataset.schema)),
      )
      dataset.counts = { ...(dataset.counts ?? {}), records: sorted.length }
      await this.saveDataset(dataset)
    })
  }

  /** Append or upsert records; table datasets upsert by row key. */
  async appendRecords(dataset, records, { mode = 'append' } = {}) {
    const existing = await this.readMetadata(dataset)
    const byId = new Map(existing.map((record) => [record.id, record]))
    const added = []
    for (const record of records) {
      if (!record.id) throw new LakeError('every metadata record needs an id', 'SCIDATAMAS_BAD_RECORD')
      if (mode === 'upsert' && byId.has(record.id)) {
        byId.set(record.id, { ...byId.get(record.id), ...record })
      } else if (byId.has(record.id)) {
        throw new LakeError(`duplicate record id "${record.id}"`, 'SCIDATAMAS_DUPLICATE_RECORD')
      } else {
        byId.set(record.id, record)
      }
      added.push(record)
    }
    await this.writeMetadata(dataset, [...byId.values()])
    return added
  }

  /** Validate raw metadata against the dataset schema and add system fields. */
  validateRecords(dataset, rawRecords, { filePath, partial = false, author } = {}) {
    const prepared = []
    const missing = []
    const errors = []
    for (const [index, raw] of rawRecords.entries()) {
      const record = { ...raw }
      if (!record.id) record.id = randomId('rec')
      record.author = record.author ?? author ?? dataset.defaults?.author ?? this.config.author ?? 'unknown'
      record.uploaded_at = record.uploaded_at ?? nowIso()
      if (filePath && !record.file_path) record.file_path = filePath
      const validated = validateRecord(record, dataset.schema, {
        partial,
        tableLayout: dataset.layout === 'table',
      })
      const systemValues = {}
      for (const field of SYSTEM_FIELDS) {
        if (record[field.name] !== undefined) systemValues[field.name] = record[field.name]
      }
      const merged = { ...validated.record, ...systemValues }
      if (validated.errors.length > 0) {
        errors.push({ index, id: record.id, issues: validated.errors })
        continue
      }
      if (validated.missing.length > 0) missing.push({ index, id: record.id, fields: validated.missing })
      prepared.push({ record: merged, unknown: validated.unknown, missing: validated.missing })
    }
    return { prepared, missing, errors }
  }

  /** Append one audit event for a dataset. */
  async recordEvent(dataset, type, payload = {}) {
    const entry = { ts: nowIso(), type, ...payload }
    await this.storage.appendJsonLine(this.datasetKey(dataset.id, 'events.jsonl'), entry)
    return entry
  }

  /** Read recent dataset events. */
  async readEvents(dataset, limit = 50) {
    const key = this.datasetKey(dataset.id, 'events.jsonl')
    if (!(await this.storage.exists(key))) return []
    const lines = (await this.storage.readText(key)).trim().split(/\r?\n/).filter(Boolean)
    return lines.slice(-limit).map((line) => {
      try { return JSON.parse(line) } catch { return { raw: line } }
    })
  }

  /** Save a debate validation report and mark the schema version as reviewed. */
  async saveValidation(dataset, report) {
    const version = dataset.schema_version
    const stored = {
      ...report,
      dataset_id: dataset.id,
      schema_version: version,
      created_at: nowIso(),
    }
    await this.storage.writeJson(this.datasetKey(dataset.id, 'validation', 'latest.json'), stored)
    const historyKey = this.datasetKey(dataset.id, 'validation', 'history.jsonl')
    await this.storage.appendJsonLine(historyKey, {
      created_at: stored.created_at,
      schema_version: version,
      coverage: stored.coverage,
      runs: stored.runs,
      useful_fields: stored.useful_fields?.length ?? 0,
      unanswered: stored.unanswered_questions?.length ?? 0,
    })
    dataset.validated_schema_version = version
    await this.saveDataset(dataset)
    await this.recordEvent(dataset, 'schema_validated', {
      schema_version: version,
      coverage: stored.coverage,
      runs: stored.runs,
    })
    return stored
  }

  /** Persist a staged add for later confirmation/commit. */
  async saveStage(dataset, stage) {
    await this.storage.writeJson(this.datasetKey(dataset.id, 'staging', `${stage.stage_id}.json`), stage)
    return stage
  }

  /** Load a stage or throw. */
  async getStage(dataset, stageId) {
    const stage = await this.storage.readJson(this.datasetKey(dataset.id, 'staging', `${stageId}.json`))
    if (!stage) throw new LakeError(`stage "${stageId}" does not exist in dataset "${dataset.id}"`, 'SCIDATAMAS_NO_STAGE')
    return stage
  }

  /** Remove a committed stage. */
  async deleteStage(dataset, stageId) {
    await this.storage.remove(this.datasetKey(dataset.id, 'staging', `${stageId}.json`))
  }

  /** Read the tabular artifact of a table-layout dataset. */
  async readTableArtifact(dataset) {
    if (dataset.layout !== 'table' || !dataset.table?.path) {
      throw new LakeError(`dataset "${dataset.id}" is not a table dataset`, 'SCIDATAMAS_NOT_TABLE')
    }
    const localPath = this.storage.localPath(dataset.table.path)
    if (!localPath) {
      throw new LakeError('remote table storage needs a local materialization layer (not implemented yet)', 'SCIDATAMAS_REMOTE_TABLE')
    }
    return readTable(localPath, { maxRows: this.config.maxRowsScan })
  }

  /**
   * Build the effective rows of a table dataset: table columns mapped to
   * normalized field names, merged with sidecar metadata by row key.
   */
  async tableRecords(dataset) {
    const table = await this.readTableArtifact(dataset)
    const sidecar = await this.readMetadata(dataset)
    const sideById = new Map(sidecar.map((record) => [String(record.id), record]))
    const sourceByField = new Map()
    for (const field of dataset.schema?.fields ?? []) {
      if (field.scope === 'column') sourceByField.set(field.name, field.source ?? field.name)
    }
    const rowKey = dataset.table.row_key
    return table.rows.map((row, index) => {
      const normalized = {}
      for (const field of dataset.schema?.fields ?? []) {
        if (field.scope !== 'column') continue
        const source = field.source ?? field.name
        const coerced = coerceValue(row[source], field.type)
        normalized[field.name] = coerced.error ? row[source] : coerced.value
      }
      const id = String(row[rowKey] ?? index)
      const side = sideById.get(id) ?? {}
      return {
        ...normalized,
        ...side,
        id,
        author: side.author ?? dataset.defaults?.author ?? this.config.author ?? 'unknown',
        uploaded_at: side.uploaded_at ?? dataset.defaults?.uploaded_at ?? dataset.created_at,
        file_path: side.file_path ?? dataset.table.path,
      }
    })
  }

  /** Recompute file/byte counts from the storage listing. */
  async refreshCounts(dataset) {
    const prefix = this.datasetKey(dataset.id, 'files')
    const files = await this.storage.list(prefix)
    dataset.counts = {
      ...(dataset.counts ?? {}),
      files: files.length,
      bytes: files.reduce((sum, file) => sum + (file.size ?? 0), 0),
    }
    await this.saveDataset(dataset)
    return dataset.counts
  }

  /** Copy a host file into the dataset and return its storage key. */
  async putFile(dataset, sourcePath, relativePath, options = {}) {
    const clean = relativePath.replace(/^\/+/, '')
    const key = this.datasetKey(dataset.id, 'files', clean)
    const info = await stat(sourcePath)
    if (!info.isFile()) throw new LakeError(`not a regular file: ${sourcePath}`, 'SCIDATAMAS_NOT_FILE')
    if (info.size > this.config.maxFileBytes) {
      throw new LakeError(
        `file is larger than the configured maxFileBytes (${info.size} > ${this.config.maxFileBytes}): ${sourcePath}`,
        'SCIDATAMAS_FILE_TOO_LARGE',
      )
    }
    const copied = await this.storage.copyIn(sourcePath, key, { maxBytes: this.config.maxFileBytes })
    return { key, size: copied.size, relative: clean }
  }

  /** Write a table artifact and its manifest block. */
  async registerTable(dataset, tablePath, { rowKey } = {}) {
    const info = await stat(tablePath)
    if (!info.isFile()) throw new LakeError(`not a regular file: ${tablePath}`, 'SCIDATAMAS_NOT_FILE')
    if (info.size > this.config.maxFileBytes) {
      throw new LakeError(`table is larger than maxFileBytes: ${tablePath}`, 'SCIDATAMAS_FILE_TOO_LARGE')
    }
    const table = await readTable(tablePath, { maxRows: this.config.maxRowsScan })
    if (table.columns.length === 0) throw new LakeError('table has no columns', 'SCIDATAMAS_EMPTY_TABLE')
    const chosenKey = chooseRowKey(table, rowKey)
    const fileName = basename(tablePath)
    const key = this.datasetKey(dataset.id, 'files', fileName)
    const copied = await this.storage.copyIn(tablePath, key, { maxBytes: this.config.maxFileBytes })
    const columns = table.columns.map((column) => ({ ...column, source: column.name }))
    dataset.table = {
      path: key,
      name: fileName,
      format: extname(fileName).replace('.', '') || 'csv',
      row_key: chosenKey.name,
      row_key_fallback: chosenKey.fallback,
      column_count: columns.length,
      columns,
      row_count: table.rows.length,
      size: copied.size,
      delimiter: table.delimiter ?? null,
      uploaded_at: nowIso(),
    }
    dataset.layout = 'table'
    dataset.schema = normalizeSchema(dataset.schema, {
      layout: 'table',
      columns,
      maxFields: this.config.maxSchemaFields,
    })
    dataset.counts = { ...(dataset.counts ?? {}), bytes: copied.size, files: 1, records: table.rows.length }
    await this.saveDataset(dataset)
    return dataset.table
  }
}

/** Pick a stable row key column; fall back to the 0-based row index. */
export function chooseRowKey(table, requested) {
  const names = table.columns.map((column) => column.name)
  if (requested && names.includes(requested)) {
    if (isUniqueColumn(table.rows, requested)) return { name: requested, fallback: false }
    return { name: '__row_index__', fallback: true }
  }
  const candidates = ['id', 'ID', 'Id', 'row_id', 'row', 'index', 'sample_id', 'key']
  for (const candidate of candidates) {
    if (names.includes(candidate) && isUniqueColumn(table.rows, candidate)) {
      return { name: candidate, fallback: false }
    }
  }
  const first = names[0]
  if (first && isUniqueColumn(table.rows, first)) return { name: first, fallback: false }
  return { name: '__row_index__', fallback: true }
}

function isUniqueColumn(rows, name) {
  const seen = new Set()
  for (const row of rows) {
    const value = String(row[name] ?? '').trim()
    if (!value || seen.has(value)) return false
    seen.add(value)
  }
  return seen.size > 0
}

function sameSchema(a, b) {
  const left = (a?.fields ?? []).filter((field) => !field.system)
  const right = (b?.fields ?? []).filter((field) => !field.system)
  if (left.length !== right.length) return false
  return left.every((field, index) => {
    const other = right[index]
    return field.name === other?.name && field.type === other?.type && field.description === other?.description
  })
}

/** Compute a content hash for a local file (used by import provenance). */
export async function hashFile(path) {
  return sha256(await readFile(path))
}

/** Resolve a user path against a base directory. */
export function resolvePath(path, base = process.cwd()) {
  return resolve(base, path)
}
