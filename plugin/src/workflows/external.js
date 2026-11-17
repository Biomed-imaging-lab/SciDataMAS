/**
 * External-source import. Zenodo is the first-class source (record API, file
 * tree, record metadata); a direct HTTP(S) file URL is the generic fallback.
 * Files are downloaded into a staging directory, inspected, and only then
 * turned into a dataset, so the schema is grounded in the actual artifacts.
 * @module scidatamas/workflows/external
 */
import { createWriteStream } from 'node:fs'
import { mkdir, rm, stat } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'
import { Readable, Transform } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { inspectSources, inspectSummary } from '../inspect.js'
import { LakeError } from '../lake.js'
import { externalMappingSystem, externalMappingUser } from '../prompts.js'
import { normalizeSchema, SYSTEM_FIELD_NAMES } from '../metadata.js'
import { clip, randomId, sanitizeRelPath, slugify } from '../util.js'
import { schemaText } from './debate.js'

const USER_AGENT = 'SciDataMAS-DSH/0.1 (+https://github.com/Biomed-imaging-lab/SciDataMAS)'
const JSON_LIMIT = 8 * 1024 * 1024

/** Parse a supported external URL. */
export function parseExternalUrl(input) {
  const raw = String(input ?? '').trim()
  if (!raw) throw new LakeError('url is required', 'SCIDATAMAS_BAD_URL')
  const doi = /10\.5281\/zenodo\.(\d+)/i.exec(raw)
  if (doi) {
    return {
      kind: 'zenodo',
      id: doi[1],
      api: `https://zenodo.org/api/records/${doi[1]}`,
      canonical: `https://zenodo.org/records/${doi[1]}`,
    }
  }
  let url
  try {
    url = new URL(raw)
  } catch {
    throw new LakeError(`invalid URL: ${raw}`, 'SCIDATAMAS_BAD_URL')
  }
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new LakeError('only http(s) URLs are supported', 'SCIDATAMAS_BAD_URL')
  }
  if (/(^|\.)zenodo\.org$/i.test(url.hostname)) {
    const match = /\/(?:records?|api\/records)\/(\d+)/.exec(url.pathname)
    if (match) {
      return {
        kind: 'zenodo',
        id: match[1],
        api: `https://zenodo.org/api/records/${match[1]}`,
        canonical: `https://zenodo.org/records/${match[1]}`,
      }
    }
  }
  return { kind: 'url', url: url.href, canonical: url.href }
}

/** Reject loopback/private hosts unless explicitly allowed. */
export function assertHostAllowed(input, config) {
  if (!config.allowNetwork) throw new LakeError('network access is disabled by config (allowNetwork=false)', 'SCIDATAMAS_NETWORK_DISABLED')
  const url = new URL(input)
  const host = url.hostname.toLowerCase()
  if (config.allowPrivateHosts) return
  if (host === 'localhost' || host === '::1' || host.endsWith('.local') || host.endsWith('.internal')) {
    throw new LakeError(`private host "${host}" is blocked; set allowPrivateHosts=true to import from it`, 'SCIDATAMAS_PRIVATE_HOST')
  }
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    const [a, b] = host.split('.').map(Number)
    if (a === 10 || a === 127 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)) {
      throw new LakeError(`private IP "${host}" is blocked; set allowPrivateHosts=true to import from it`, 'SCIDATAMAS_PRIVATE_HOST')
    }
  }
}

/** Fetch with timeout and caller cancellation. */
async function request(url, { config, signal, method = 'GET', headers = {} } = {}) {
  assertHostAllowed(url, config)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error(`request timed out after ${config.requestTimeoutMs} ms`)), config.requestTimeoutMs)
  const onAbort = () => controller.abort(signal?.reason)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  try {
    const response = await fetch(url, {
      method,
      redirect: 'follow',
      signal: controller.signal,
      headers: { 'user-agent': USER_AGENT, ...headers },
    })
    return response
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

async function fetchJson(url, options) {
  const response = await request(url, options)
  if (!response.ok) throw new LakeError(`HTTP ${response.status} for ${url}`, 'SCIDATAMAS_HTTP')
  const text = await response.text()
  if (text.length > JSON_LIMIT) throw new LakeError(`response is too large (${text.length} bytes)`, 'SCIDATAMAS_HTTP_TOO_LARGE')
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new LakeError(`invalid JSON from ${url}: ${error.message}`, 'SCIDATAMAS_BAD_JSON')
  }
}

function creatorNames(metadata) {
  const creators = metadata?.creators ?? metadata?.creators_and_contributors ?? []
  if (Array.isArray(creators)) return creators.map((creator) => creator?.name ?? String(creator)).filter(Boolean)
  return []
}

/** Normalize one Zenodo record into the plugin's source shape. */
export function normalizeZenodoRecord(record, fallbackId) {
  const metadata = record?.metadata ?? {}
  const recordId = String(record?.id ?? fallbackId)
  const files = (record?.files ?? []).map((file) => {
    const key = String(file.key ?? file.filename ?? 'file')
    const download = file?.links?.self
      ?? `https://zenodo.org/records/${recordId}/files/${encodeURIComponent(key)}?download=1`
    return {
      key,
      name: basename(key),
      size: Number(file.size ?? 0),
      checksum: file.checksum ?? file?.links?.checksum ?? null,
      download_url: download,
    }
  })
  return {
    kind: 'zenodo',
    record_id: recordId,
    doi: record?.doi ?? metadata?.doi ?? null,
    title: String(metadata?.title ?? `Zenodo record ${recordId}`),
    description: String(metadata?.description ?? ''),
    creators: creatorNames(metadata),
    publication_date: metadata?.publication_date ?? null,
    license: metadata?.license?.id ?? metadata?.license ?? null,
    keywords: Array.isArray(metadata?.keywords) ? metadata.keywords.map(String) : [],
    resource_type: metadata?.resource_type?.title ?? metadata?.resource_type?.type ?? null,
    related_identifiers: Array.isArray(metadata?.related_identifiers) ? metadata.related_identifiers.slice(0, 30) : [],
    files,
    total_bytes: files.reduce((sum, file) => sum + (file.size || 0), 0),
    url: `https://zenodo.org/records/${recordId}`,
    raw: {
      record_id: recordId,
      doi: record?.doi,
      metadata: {
        title: metadata?.title,
        publication_date: metadata?.publication_date,
        license: metadata?.license,
        keywords: metadata?.keywords,
        resource_type: metadata?.resource_type,
      },
    },
  }
}

/** Analyze a Zenodo record or a direct file URL without downloading payloads. */
export async function analyzeExternal({ url, config, signal }) {
  const parsed = parseExternalUrl(url)
  if (parsed.kind === 'zenodo') {
    const record = await fetchJson(parsed.api, { config, signal })
    return normalizeZenodoRecord(record, parsed.id)
  }
  const response = await request(parsed.url, { config, signal, method: 'HEAD' })
  if (!response.ok) throw new LakeError(`HTTP ${response.status} for ${parsed.url}`, 'SCIDATAMAS_HTTP')
  const contentType = response.headers.get('content-type') ?? 'application/octet-stream'
  const length = Number(response.headers.get('content-length') ?? 0)
  const disposition = response.headers.get('content-disposition') ?? ''
  const dispositionName = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition)?.[1]
  const name = dispositionName ? decodeURIComponent(dispositionName) : basename(new URL(parsed.url).pathname) || 'download'
  return {
    kind: 'url',
    record_id: null,
    doi: null,
    title: name,
    description: '',
    creators: [],
    publication_date: null,
    license: null,
    keywords: [],
    resource_type: contentType,
    related_identifiers: [],
    files: [{
      key: name,
      name,
      size: length,
      checksum: null,
      download_url: parsed.url,
      content_type: contentType,
    }],
    total_bytes: length,
    url: parsed.url,
    raw: { content_type: contentType },
  }
}

/** Very small glob matcher for include/exclude patterns. */
export function matchesGlob(name, pattern) {
  if (!pattern) return false
  const escaped = String(pattern)
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replaceAll('**', '\u0000')
    .replaceAll('*', '[^/]*')
    .replaceAll('?', '[^/]')
    .replaceAll('\u0000', '.*')
  return new RegExp(`^${escaped}$`).test(name)
}

/** Filter the source file list. */
export function filterSourceFiles(files, { include, exclude, maxFiles }) {
  let selected = files
  const includePatterns = Array.isArray(include) ? include.filter(Boolean) : include ? [include] : []
  if (includePatterns.length > 0) {
    selected = selected.filter((file) => includePatterns.some((pattern) => matchesGlob(file.key, pattern) || matchesGlob(file.name, pattern)))
  }
  const excludePatterns = Array.isArray(exclude) ? exclude.filter(Boolean) : exclude ? [exclude] : []
  if (excludePatterns.length > 0) {
    selected = selected.filter((file) => !excludePatterns.some((pattern) => matchesGlob(file.key, pattern) || matchesGlob(file.name, pattern)))
  }
  return {
    selected: selected.slice(0, maxFiles),
    skipped: files.length - Math.min(selected.length, maxFiles),
  }
}

/** Download one file with a hard byte cap. */
async function downloadFile(file, targetPath, { config, signal }) {
  await mkdir(dirname(targetPath), { recursive: true })
  const response = await request(file.download_url, { config, signal })
  if (!response.ok) throw new LakeError(`HTTP ${response.status} downloading ${file.key}`, 'SCIDATAMAS_HTTP')
  const limit = Math.min(config.maxFileBytes, config.maxDownloadBytes)
  let received = 0
  const limiter = new Transform({
    transform(chunk, _encoding, callback) {
      received += chunk.byteLength
      if (received > limit) {
        callback(new LakeError(`download exceeds maxFileBytes for ${file.key}`, 'SCIDATAMAS_FILE_TOO_LARGE'))
        return
      }
      callback(null, chunk)
    },
  })
  await pipeline(Readable.fromWeb(response.body), limiter, createWriteStream(targetPath))
  return received
}

/** Map external record facts onto the dataset schema. */
export async function mapExternalMetadata({ llm, exec, dataset, source }) {
  try {
    const answer = await llm.json({
      system: externalMappingSystem(),
      user: externalMappingUser({
        schemaText: schemaText({ fields: dataset.schema.fields.filter((field) => !field.system) }),
        record: {
          ...source.raw,
          title: source.title,
          description: clip(source.description, 4000),
          creators: source.creators,
          publication_date: source.publication_date,
          license: source.license,
          doi: source.doi,
          keywords: source.keywords,
          resource_type: source.resource_type,
        },
      }),
      exec,
      purpose: 'external.map',
      maxTokens: 4096,
    })
    const values = {}
    const allowed = new Set(dataset.schema.fields.map((field) => field.name))
    for (const [key, value] of Object.entries(answer.value?.values ?? {})) {
      if (allowed.has(key) && value !== undefined && value !== null && value !== '') values[key] = value
    }
    return values
  } catch {
    return {}
  }
}

/** Extra fields that make provenance explicit in the schema. */
function withProvenanceFields(schema) {
  const existing = new Set(schema.fields.map((field) => field.name))
  const extra = [
    { name: 'doi', type: 'string', description: 'DOI of the external source record.', required: false },
    { name: 'license', type: 'string', description: 'License declared by the source record.', required: false },
    { name: 'creator', type: 'string', description: 'Creator(s) listed in the source record.', required: false },
    { name: 'publication_date', type: 'datetime', description: 'Publication date of the source record.', required: false },
  ].filter((field) => !existing.has(field.name) && !SYSTEM_FIELD_NAMES.includes(field.name))
  return normalizeSchema([...schema.fields, ...extra], { layout: 'files' })
}

/**
 * Import from an external source. `mode: "analyze"` returns the plan without
 * downloading; `mode: "import"` downloads, creates/uses a dataset, stages and
 * commits the files.
 */
export async function importExternalWorkflow({
  lake,
  llm,
  config,
  exec,
  input,
  createDataset,
  stageAdd,
  commitStage,
}) {
  const source = await analyzeExternal({ url: input.url, config, signal: exec?.signal })
  const maxFiles = Math.max(1, Math.min(Number(input.max_files) || config.maxFilesPerAdd, config.maxFilesPerAdd))
  const filtered = filterSourceFiles(source.files, {
    include: input.include,
    exclude: input.exclude,
    maxFiles,
  })
  if (filtered.selected.length === 0) throw new LakeError('no files matched the include/exclude patterns', 'SCIDATAMAS_NO_FILES')
  const totalBytes = filtered.selected.reduce((sum, file) => sum + (file.size || 0), 0)
  const plan = {
    source: {
      kind: source.kind,
      title: source.title,
      doi: source.doi,
      record_id: source.record_id,
      url: source.url,
      creators: source.creators,
      license: source.license,
      publication_date: source.publication_date,
      total_files: source.files.length,
      selected_files: filtered.selected.length,
      skipped_files: filtered.skipped,
      total_bytes: totalBytes,
    },
    files: filtered.selected.map((file) => ({ key: file.key, size: file.size, checksum: file.checksum })),
  }
  if (input.mode === 'analyze') {
    return { mode: 'analyze', ...plan, record: source.raw }
  }
  if (totalBytes > config.maxDownloadBytes) {
    throw new LakeError(
      `selected files total ${totalBytes} bytes, more than maxDownloadBytes (${config.maxDownloadBytes}); narrow include patterns or raise the limit`,
      'SCIDATAMAS_IMPORT_TOO_LARGE',
    )
  }

  const importId = randomId('import')
  const stagingRoot = `_imports/${importId}`
  const stagingBase = lake.storage.localPath(stagingRoot)
  if (!stagingBase) throw new LakeError('external import currently requires local storage', 'SCIDATAMAS_REMOTE_IMPORT')
  const downloaded = []
  const warnings = []
  let succeeded = false
  try {
    for (const file of filtered.selected) {
      const relative = sanitizeRelPath(file.key)
      const target = lake.storage.localPath(`${stagingRoot}/files/${relative}`)
      if (!target) throw new LakeError('staging path is not local', 'SCIDATAMAS_REMOTE_IMPORT')
      const size = await downloadFile(file, target, { config, signal: exec?.signal })
      downloaded.push({ ...file, local_path: target, relative, downloaded_size: size })
    }
    const inspection = await inspectSources(downloaded.map((file) => file.local_path), {
      maxFiles: downloaded.length,
      maxDepth: 6,
      maxInspected: 40,
    })
    const evidence = inspectSummary(inspection)
    const description = input.description
      || `${source.title}\n\n${clip(source.description, 4000)}`.trim()
    const purpose = input.purpose || 'Reuse of an externally published scientific dataset.'
    let dataset
    const createdNew = !input.dataset_id
    if (input.dataset_id) {
      dataset = await lake.getDataset(input.dataset_id)
    } else {
      const name = input.dataset_name || source.title || `import-${importId}`
      const result = await createDataset({
        input: {
          name,
          description,
          purpose,
          layout: 'files',
          example_paths: downloaded.map((file) => file.local_path),
          author: input.author,
          modality: input.modality,
          provenance: 'external',
          source_url: source.url,
          activate: false,
          validate: false,
          rich: input.rich === true,
          tags: ['external', source.kind],
        },
        rich: input.rich === true,
      })
      dataset = await lake.getDataset(result.dataset.id)
      dataset.schema = withProvenanceFields(dataset.schema)
      await lake.saveDataset(dataset)
    }

    const mapped = await mapExternalMetadata({ llm, exec, dataset, source })
    const explicit = new Map()
    for (const file of downloaded) {
      explicit.set(file.relative, { ...mapped })
    }
    const stage = await stageAdd({
      dataset,
      input: {
        paths: [join(stagingBase, 'files')],
        notes: `External import from ${source.url}\nRecord title: ${source.title}\n${clip(source.description, 2000)}`,
        metadata: Object.fromEntries(explicit),
        commit: false,
        author: input.author,
      },
    })
    for (const item of stage.items) {
      if (!item.metadata.source_url) item.metadata.source_url = source.url
    }
    await lake.saveStage(dataset, stage)
    dataset.source = {
      kind: source.kind,
      url: source.url,
      doi: source.doi,
      record_id: source.record_id,
      title: source.title,
      creators: source.creators,
      license: source.license,
      imported_at: new Date().toISOString(),
    }
    dataset.provenance = 'external'
    await lake.saveDataset(dataset)
    const committed = await commitStage({
      dataset,
      stage,
      overrides: null,
      notes: `Imported from ${source.url}`,
      activate: input.activate !== false,
    })
    await lake.recordEvent(dataset, 'external_imported', {
      source: source.url,
      record_id: source.record_id,
      doi: source.doi,
      files: downloaded.length,
      bytes: downloaded.reduce((sum, file) => sum + file.downloaded_size, 0),
    })
    succeeded = true
    return {
      mode: 'import',
      ...plan,
      dataset: lake.summaryOf(dataset),
      created_new_dataset: createdNew,
      committed: committed.committed,
      warnings,
      record: source.raw,
    }
  } finally {
    // Keep failed staging material so a failed commit can be inspected or
    // retried; remove it only after a successful import.
    if (succeeded) await rm(stagingBase, { recursive: true, force: true }).catch(() => {})
  }
}

/** Best-effort local size of a staged file. */
export async function stagedSize(path) {
  try {
    return (await stat(path)).size
  } catch {
    return 0
  }
}
