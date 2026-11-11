/**
 * Small dependency-free helpers shared by the SciDataMAS plugin.
 * @module scidatamas/util
 */
import { createHash, randomBytes } from 'node:crypto'
import { mkdir, rename, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, normalize, relative, sep } from 'node:path'

const CYRILLIC = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
  и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
  с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh',
  щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
}

/** Produce a filesystem- and URL-safe identifier. */
export function slugify(value, fallback = 'dataset') {
  const transliterated = String(value ?? '')
    .toLowerCase()
    .replace(/[а-яё]/g, (char) => CYRILLIC[char] ?? char)
  const slug = transliterated
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
  return slug || fallback
}

/** Short random identifier with a readable prefix. */
export function randomId(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${randomBytes(4).toString('hex')}`
}

/** ISO timestamp for durable records. */
export function nowIso() {
  return new Date().toISOString()
}

/** Truncate text without splitting surrogate pairs. */
export function clip(value, maxChars) {
  const text = String(value ?? '')
  if (!Number.isFinite(maxChars) || maxChars <= 0 || text.length <= maxChars) return text
  return `${text.slice(0, maxChars)}\n…[truncated ${text.length - maxChars} chars]`
}

/** Human-readable byte count. */
export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return 'unknown'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

/** Content hash used for provenance and duplicate detection. */
export function sha256(data) {
  return createHash('sha256').update(data).digest('hex')
}

/** True when child is inside parent (or equal to it). */
export function isInside(parent, child) {
  const rel = relative(parent, child)
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !isAbsolute(rel))
}

/**
 * Resolve a relative storage key under a root and reject traversal.
 * Keys always use POSIX separators in manifests, regardless of host OS.
 */
export function safeJoin(root, key) {
  const normalizedKey = normalizeKey(key)
  const target = join(root, ...normalizedKey.split('/'))
  if (!isInside(root, target)) throw new Error(`path escapes the storage root: ${key}`)
  return target
}

/** Validate and normalize a storage key (relative POSIX path). */
export function normalizeKey(key) {
  const raw = String(key ?? '').replaceAll('\\', '/')
  if (!raw || raw === '.' || raw === '/') throw new Error('storage key must be a non-empty relative path')
  if (raw.startsWith('/') || /^[a-zA-Z]:/.test(raw)) throw new Error(`storage key must be relative: ${key}`)
  const normalized = normalize(raw).replaceAll('\\', '/')
  if (normalized === '.' || normalized.startsWith('../') || normalized === '..') {
    throw new Error(`storage key escapes its root: ${key}`)
  }
  return normalized
}

/** Sanitize a user-provided relative file name while keeping subdirectories. */
export function sanitizeRelPath(value) {
  const parts = String(value ?? '')
    .replaceAll('\\', '/')
    .split('/')
    .filter((part) => part !== '' && part !== '.')
  const safe = parts.map((part) => (part === '..' ? '__up__' : part.replace(/[\0-\x1f]/g, '_')))
  if (safe.length === 0) return 'file'
  return safe.join('/')
}

/** Atomic text write: write a sibling temp file, then rename. */
export async function writeTextAtomic(path, text) {
  await mkdir(dirname(path), { recursive: true })
  const temp = `${path}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`
  await writeFile(temp, text, 'utf8')
  try {
    await rename(temp, path)
  } catch (error) {
    // Windows cannot replace an existing file with rename; fall back once.
    if (error && (error.code === 'EEXIST' || error.code === 'EPERM')) {
      const { rm } = await import('node:fs/promises')
      await rm(path, { force: true })
      await rename(temp, path)
      return
    }
    throw error
  }
}

/** Atomic JSON write. */
export async function writeJsonAtomic(path, value) {
  await writeTextAtomic(path, `${JSON.stringify(value, null, 2)}\n`)
}

/** Parse JSON with a readable error. */
export function parseJson(text, label = 'JSON') {
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new Error(`${label} is not valid JSON: ${error.message}`)
  }
}

/** Per-key serial queue, enough for one plugin process updating a lake. */
export class KeyedLock {
  constructor() {
    this.tails = new Map()
  }

  /** Run op after all earlier operations on the same key settle. */
  async run(key, op) {
    const previous = this.tails.get(key) ?? Promise.resolve()
    let release
    const current = new Promise((resolve) => { release = resolve })
    const tail = previous.then(() => current)
    this.tails.set(key, tail)
    await previous
    try {
      return await op()
    } finally {
      release()
      if (this.tails.get(key) === tail) this.tails.delete(key)
    }
  }
}

/** Run an async mapper with bounded concurrency, preserving order. */
export async function mapLimit(items, limit, mapper) {
  const source = [...items]
  const results = new Array(source.length)
  let next = 0
  const workers = Array.from({ length: Math.max(1, Math.min(limit, source.length)) }, async () => {
    while (true) {
      const index = next
      next += 1
      if (index >= source.length) return
      results[index] = await mapper(source[index], index)
    }
  })
  await Promise.all(workers)
  return results
}

/** Sleep with cancellation support (used for retry backoff). */
export function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(new Error('aborted'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/** Stable, locale-independent lowercase for comparisons. */
export function fold(value) {
  return String(value ?? '').toLowerCase().normalize('NFKC').trim()
}

/**
 * Extract the first balanced JSON value from an LLM answer.
 * Handles fenced blocks, prose before/after the value, and trailing commas.
 */
export function extractJson(text) {
  const source = String(text ?? '')
  const fenced = /```(?:json|JSON)?\s*([\s\S]*?)```/.exec(source)
  const candidates = []
  if (fenced) candidates.push(fenced[1])
  const start = source.search(/[[{]/)
  if (start !== -1) {
    const balanced = sliceBalanced(source, start)
    if (balanced) candidates.push(balanced)
  }
  candidates.push(source)
  for (const candidate of candidates) {
    const trimmed = candidate.trim()
    if (!trimmed) continue
    for (const variant of [trimmed, trimmed.replace(/,\s*([}\]])/g, '$1')]) {
      try {
        return JSON.parse(variant)
      } catch {
        // try next candidate
      }
    }
  }
  throw new Error(`could not extract JSON from model answer: ${clip(source, 800)}`)
}

/** Return the balanced JSON object/array starting at `start`, respecting strings. */
function sliceBalanced(source, start) {
  const opener = source[start]
  const closer = opener === '{' ? '}' : ']'
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = start; index < source.length; index += 1) {
    const char = source[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') inString = true
    else if (char === opener) depth += 1
    else if (char === closer) {
      depth -= 1
      if (depth === 0) return source.slice(start, index + 1)
    }
  }
  return undefined
}

/** Percent-decode safely, used by URL parsers. */
export function safeDecode(value) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

/** Convert a value into a compact, single-line description for logs. */
export function oneLine(value, max = 300) {
  return clip(String(value ?? '').replace(/\s+/g, ' ').trim(), max)
}

/**
 * Convert an arbitrary tool result into lossless JSON: drop undefined object
 * keys, use null for undefined array entries, stringify bigint, serialize
 * Date, and replace non-finite numbers with null. Tool outputs are validated
 * against a canonical JSON schema, and an accidental `undefined` property
 * would otherwise make an otherwise valid result fail.
 */
export function jsonSafe(value, seen = new WeakSet()) {
  if (value === undefined || value === null) return value
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'bigint') return String(value)
  if (value instanceof Date) return value.toISOString()
  if (typeof value !== 'object') return value
  if (seen.has(value)) return '[circular]'
  seen.add(value)
  if (Array.isArray(value)) {
    return value.map((item) => (item === undefined ? null : jsonSafe(item, seen)))
  }
  const result = {}
  for (const [key, item] of Object.entries(value)) {
    const safe = jsonSafe(item, seen)
    if (safe !== undefined) result[key] = safe
  }
  return result
}
