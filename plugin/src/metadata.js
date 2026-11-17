/**
 * Metadata vocabulary: schema normalization, record validation, tabular
 * parsing, and the reserved organizational fields.
 *
 * A dataset schema is a flat list of fields. Fields describe either a record
 * (`scope: "row"`, the default) or a column of a tabular artifact
 * (`scope: "column"`). System fields are implicit and cannot be redefined.
 *
 * @module scidatamas/metadata
 */
import { readFile } from 'node:fs/promises'
import { extname } from 'node:path'
import { clip, fold, slugify } from './util.js'

/** Reserved organizational fields, present in every dataset. */
export const SYSTEM_FIELDS = Object.freeze([
  {
    name: 'id',
    type: 'string',
    description: 'Stable identifier of one dataset record (for table datasets: the row key).',
    required: true,
    system: true,
    scope: 'row',
  },
  {
    name: 'author',
    type: 'string',
    description: 'Person or system that contributed this record.',
    required: false,
    system: true,
    scope: 'row',
  },
  {
    name: 'uploaded_at',
    type: 'datetime',
    description: 'ISO-8601 timestamp when the record entered the lake.',
    required: false,
    system: true,
    scope: 'row',
  },
  {
    name: 'file_path',
    type: 'string',
    description: 'Storage key of the primary artifact (for table datasets: the table file).',
    required: false,
    system: true,
    scope: 'row',
  },
  {
    name: 'source_url',
    type: 'string',
    description: 'External source URL when the record was imported.',
    required: false,
    system: true,
    scope: 'row',
  },
])

export const SYSTEM_FIELD_NAMES = Object.freeze(SYSTEM_FIELDS.map((field) => field.name))

const TYPE_ALIASES = new Map([
  ['str', 'string'],
  ['text', 'string'],
  ['string', 'string'],
  ['int', 'integer'],
  ['integer', 'integer'],
  ['long', 'integer'],
  ['float', 'number'],
  ['double', 'number'],
  ['number', 'number'],
  ['numeric', 'number'],
  ['bool', 'boolean'],
  ['boolean', 'boolean'],
  ['date', 'datetime'],
  ['datetime', 'datetime'],
  ['timestamp', 'datetime'],
  ['categorical', 'category'],
  ['category', 'category'],
  ['enum', 'category'],
  ['object', 'json'],
  ['dict', 'json'],
  ['json', 'json'],
  ['array', 'json'],
])

/** Normalize one metadata type name. */
export function normalizeType(value) {
  return TYPE_ALIASES.get(fold(value)) ?? 'string'
}

/** Normalize a field name into snake_case. */
export function normalizeFieldName(value) {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  const snake = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return snake || slugify(raw, 'field').replaceAll('-', '_')
}

/**
 * Normalize one field from LLM output or a user-supplied schema object.
 * Accepts `{name, description, type}`, `{field_name, descr, data_type}`, and a
 * mapping entry such as `"field": {"descr": "...", "type": "int"}`.
 */
export function normalizeField(raw, keyHint) {
  if (typeof raw === 'string') {
    return {
      name: normalizeFieldName(keyHint ?? raw),
      type: 'string',
      description: raw.trim(),
      required: false,
      scope: 'row',
    }
  }
  const source = raw && typeof raw === 'object' ? raw : {}
  const name = normalizeFieldName(
    source.name ?? source.field_name ?? source.field ?? source.key ?? keyHint ?? '',
  )
  if (!name) return undefined
  const description = String(
    source.description ?? source.descr ?? source.desc ?? source.definition ?? source.comment ?? '',
  ).trim()
  const type = normalizeType(source.type ?? source.data_type ?? source.datatype ?? source.dtype)
  const examples = source.examples ?? source.example
  const required = source.required === true || source.optional === false
  return {
    name,
    type,
    description: description || `Metadata field "${name}".`,
    required,
    scope: source.scope === 'column' || source.scope === 'table' ? 'column' : 'row',
    ...(source.unit ? { unit: String(source.unit) } : {}),
    ...(source.role ? { role: String(source.role) } : {}),
    ...(source.source || source.column ? { source: String(source.source ?? source.column) } : {}),
    ...(source.node_id ? { node_id: String(source.node_id) } : {}),
    ...(source.node_description ? { node_description: String(source.node_description) } : {}),
    ...(examples ? { examples: Array.isArray(examples) ? examples.slice(0, 5) : [String(examples)] } : {}),
  }
}

/**
 * Normalize a complete schema. Duplicate field names are merged, reserved
 * system fields win, and missing table columns receive auto-generated field
 * descriptions so the schema always covers the artifact.
 *
 * @param {unknown} raw - array, `{fields: []}`, or field-name mapping.
 * @param {object} options
 * @param {"files"|"table"} options.layout
 * @param {Array<{name: string, type?: string}>} [options.columns]
 * @param {number} [options.maxFields]
 * @returns {{fields: Array<object>, rejected: Array<object>, warnings: string[]}}
 */
export function normalizeSchema(raw, options = {}) {
  const layout = options.layout === 'table' ? 'table' : 'files'
  const maxFields = Number.isFinite(options.maxFields) ? options.maxFields : 200
  const warnings = []
  const rejected = []
  const list = []
  if (Array.isArray(raw)) {
    list.push(...raw)
  } else if (raw && typeof raw === 'object') {
    if (Array.isArray(raw.fields)) list.push(...raw.fields)
    else for (const [key, value] of Object.entries(raw)) list.push({ ...(value ?? {}), name: key })
  } else if (raw !== undefined && raw !== null) {
    throw new Error('schema must be an array, an object with "fields", or a field mapping')
  }

  const byName = new Map()
  for (const item of list) {
    let field
    if (typeof item === 'string') field = normalizeField(item)
    else field = normalizeField(item, item?.name)
    if (!field) continue
    if (SYSTEM_FIELD_NAMES.includes(field.name)) {
      rejected.push({ name: field.name, reason: 'reserved system field' })
      continue
    }
    const previous = byName.get(field.name)
    if (previous) {
      previous.description = previous.description.length >= field.description.length
        ? previous.description
        : field.description
      previous.required = previous.required || field.required
      previous.type = previous.type === 'string' ? field.type : previous.type
      continue
    }
    byName.set(field.name, field)
  }

  if (layout === 'table' && Array.isArray(options.columns) && options.columns.length > 0) {
    for (const column of options.columns) {
      const name = normalizeFieldName(column.name)
      if (!name || SYSTEM_FIELD_NAMES.includes(name)) continue
      const existing = byName.get(name)
      if (existing) {
        existing.scope = 'column'
        existing.source = column.name
        continue
      }
      byName.set(name, {
        name,
        type: normalizeType(column.type),
        description: `Column "${column.name}" of the tabular artifact (auto-detected; refine with dataset_update).`,
        required: false,
        scope: 'column',
        source: column.name,
      })
    }
  }

  let fields = [...byName.values()]
  if (fields.length > maxFields) {
    warnings.push(`schema was capped at ${maxFields} fields; ${fields.length - maxFields} were dropped`)
    fields = fields.slice(0, maxFields)
  }

  return {
    fields: [...SYSTEM_FIELDS.map((field) => ({ ...field })), ...fields],
    rejected,
    warnings,
  }
}

/** Return only user-defined (non-system) fields. */
export function userFields(schema) {
  return (schema?.fields ?? []).filter((field) => !field.system)
}

/** Find a field definition by name. */
export function findField(schema, name) {
  return (schema?.fields ?? []).find((field) => field.name === name)
}

/** Coerce a raw value to the declared field type; returns `{value, error}`. */
export function coerceValue(value, type) {
  if (value === undefined || value === null || value === '') return { value: undefined }
  if (type === 'json') {
    if (typeof value === 'object') return { value }
    try {
      return { value: JSON.parse(String(value)) }
    } catch {
      return { error: 'is not valid JSON' }
    }
  }
  if (type === 'integer') {
    const number = typeof value === 'number' ? value : Number(String(value).trim())
    if (!Number.isInteger(number)) return { error: 'is not an integer' }
    return { value: number }
  }
  if (type === 'number') {
    const number = typeof value === 'number' ? value : Number(String(value).trim())
    if (!Number.isFinite(number)) return { error: 'is not a number' }
    return { value: number }
  }
  if (type === 'boolean') {
    if (typeof value === 'boolean') return { value }
    const folded = fold(value)
    if (['true', 'yes', '1', 'y'].includes(folded)) return { value: true }
    if (['false', 'no', '0', 'n'].includes(folded)) return { value: false }
    return { error: 'is not a boolean' }
  }
  if (type === 'datetime') {
    const date = value instanceof Date ? value : new Date(String(value))
    if (Number.isNaN(date.getTime())) return { error: 'is not a valid date/time' }
    return { value: date.toISOString() }
  }
  if (type === 'category') return { value: String(value) }
  return { value: String(value) }
}

/**
 * Validate and coerce one metadata record against a schema.
 * System fields are validated but never required from the caller.
 */
export function validateRecord(record, schema, options = {}) {
  const result = {}
  const missing = []
  const errors = []
  const unknown = []
  const definitions = new Map((schema?.fields ?? []).map((field) => [field.name, field]))

  for (const [key, rawValue] of Object.entries(record ?? {})) {
    if (!definitions.has(key)) {
      unknown.push(key)
      continue
    }
    const field = definitions.get(key)
    const coerced = coerceValue(rawValue, field.type)
    if (coerced.error) errors.push({ field: key, value: rawValue, error: coerced.error })
    else if (coerced.value !== undefined) result[key] = coerced.value
  }

  for (const field of schema?.fields ?? []) {
    if (field.system) continue
    const has = Object.hasOwn(result, field.name)
    if (field.required && !has && !(options.tableLayout && field.scope === 'column')) missing.push(field.name)
    if (field.type === 'json' && has && result[field.name] === null) delete result[field.name]
  }

  return { record: result, missing, errors, unknown }
}

/** Merge records left-to-right, ignoring `undefined`. */
export function mergeRecords(...records) {
  const merged = {}
  for (const record of records) {
    if (!record) continue
    for (const [key, value] of Object.entries(record)) {
      if (value !== undefined) merged[key] = value
    }
  }
  return merged
}

/** Infer a metadata type from observed values. */
export function inferType(values) {
  const sample = values.filter((value) => value !== undefined && value !== null && value !== '')
  if (sample.length === 0) return 'string'
  if (sample.every((value) => typeof value === 'boolean' || ['true', 'false'].includes(fold(value)))) {
    return 'boolean'
  }
  if (sample.every((value) => Number.isInteger(Number(value)))) return 'integer'
  if (sample.every((value) => Number.isFinite(Number(value)))) return 'number'
  if (sample.every((value) => !Number.isNaN(new Date(value).getTime()) && /[-/:T]/.test(String(value)))) {
    return 'datetime'
  }
  return 'string'
}

/** Serialize records as JSON Lines. */
export function toJsonl(records) {
  return records.map((record) => JSON.stringify(record)).join('\n') + (records.length ? '\n' : '')
}

/** Parse JSON Lines, skipping blank lines and collecting bad lines. */
export function parseJsonl(text) {
  const records = []
  const errors = []
  const lines = String(text ?? '').split(/\r?\n/)
  lines.forEach((line, index) => {
    if (!line.trim()) return
    try {
      records.push(JSON.parse(line))
    } catch (error) {
      errors.push({ line: index + 1, error: error.message })
    }
  })
  return { records, errors }
}

/** RFC-4180-style delimited text parser, tolerant of embedded newlines. */
export function parseDelimited(text, delimiter = ',', options = {}) {
  const source = String(text ?? '').replace(/^\uFEFF/, '')
  const maxRows = options.maxRows ?? Infinity
  const rows = []
  let row = []
  let field = ''
  let inQuotes = false
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (inQuotes) {
      if (char === '"') {
        if (source[index + 1] === '"') {
          field += '"'
          index += 1
        } else {
          inQuotes = false
        }
      } else {
        field += char
      }
      continue
    }
    if (char === '"') {
      inQuotes = true
    } else if (char === delimiter) {
      row.push(field)
      field = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && source[index + 1] === '\n') index += 1
      row.push(field)
      field = ''
      if (row.some((cell) => cell.trim() !== '')) rows.push(row)
      row = []
      if (rows.length >= maxRows + 1) break
    } else {
      field += char
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    if (row.some((cell) => cell.trim() !== '')) rows.push(row)
  }
  const header = rows.shift() ?? []
  return { header: header.map((cell) => cell.trim()), rows: rows.slice(0, maxRows) }
}

/** Detect the most likely delimiter in the first non-empty line. */
export function detectDelimiter(text) {
  const line = String(text ?? '').split(/\r?\n/).find((candidate) => candidate.trim() !== '') ?? ''
  const candidates = [',', '\t', ';', '|']
  let best = ','
  let bestCount = 0
  for (const delimiter of candidates) {
    let count = 0
    let inQuotes = false
    for (const char of line) {
      if (char === '"') inQuotes = !inQuotes
      else if (char === delimiter && !inQuotes) count += 1
    }
    if (count > bestCount) {
      best = delimiter
      bestCount = count
    }
  }
  return best
}

/** Serialize records to CSV using the given column order. */
export function toCsv(records, columns) {
  const escape = (value) => {
    if (value === undefined || value === null) return ''
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
    return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
  }
  const header = columns.map(escape).join(',')
  const lines = records.map((record) => columns.map((column) => escape(record[column])).join(','))
  return [header, ...lines].join('\n') + '\n'
}

/**
 * Read a tabular artifact (CSV, TSV, JSON array, or JSONL) into columns/rows.
 * Unsupported binary formats fail with a clear message rather than guessing.
 */
export async function readTable(path, options = {}) {
  const maxRows = options.maxRows ?? 200000
  const extension = extname(path).toLowerCase()
  const text = await readFile(path, 'utf8')
  if (extension === '.json') {
    const parsed = JSON.parse(text)
    const rows = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.rows) ? parsed.rows : [parsed]
    return tableFromObjects(rows.slice(0, maxRows), { format: 'json' })
  }
  if (extension === '.jsonl' || extension === '.ndjson') {
    const { records } = parseJsonl(text)
    return tableFromObjects(records.slice(0, maxRows), { format: 'jsonl' })
  }
  if (!['.csv', '.tsv', '.txt', '.tab', ''].includes(extension)) {
    throw new Error(
      `unsupported tabular format "${extension || 'unknown'}"; export the table as CSV, TSV, JSON or JSONL`,
    )
  }
  const delimiter = extension === '.tsv' || extension === '.tab' ? '\t' : detectDelimiter(text)
  const { header, rows } = parseDelimited(text, delimiter, { maxRows })
  const objects = rows.map((cells) => {
    const record = {}
    header.forEach((name, index) => { record[name] = cells[index] ?? '' })
    return record
  })
  return tableFromObjects(objects, { delimiter, format: extension.replace('.', '') || 'csv' })
}

/** Build column descriptions and rows from an array of objects. */
export function tableFromObjects(objects, extra = {}) {
  const columns = []
  const seen = new Set()
  for (const object of objects.slice(0, 500)) {
    for (const key of Object.keys(object ?? {})) {
      if (seen.has(key)) continue
      seen.add(key)
      columns.push(key)
    }
  }
  const columnInfo = columns.map((name) => ({
    name,
    type: inferType(objects.slice(0, 200).map((object) => object?.[name])),
  }))
  return {
    columns: columnInfo,
    rows: objects,
    header: columns,
    ...extra,
  }
}

/** Metadata columns in canonical export order. */
export function metadataColumns(schema) {
  return (schema?.fields ?? []).map((field) => field.name)
}

/** Short human summary of a schema for prompts and tool output. */
export function schemaSummary(schema, maxFields = 40) {
  const fields = (schema?.fields ?? []).filter((field) => !field.system)
  const lines = fields.slice(0, maxFields).map((field) => {
    const unit = field.unit ? `, unit: ${field.unit}` : ''
    const node = field.node_id ? `, node: ${field.node_id}` : ''
    return `- ${field.name} (${field.type}${unit}${node}): ${clip(field.description, 240)}`
  })
  if (fields.length > maxFields) lines.push(`... ${fields.length - maxFields} more fields`)
  return lines.join('\n')
}
