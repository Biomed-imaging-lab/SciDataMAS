/**
 * Best-effort inspection of scientific files and directory trees. The goal is
 * to give the model grounded facts (formats, dimensions, table headers, text
 * excerpts) instead of letting it invent metadata from file names alone.
 *
 * @module scidatamas/inspect
 */
import { open, readdir, stat } from 'node:fs/promises'
import { basename, extname, join, relative, resolve } from 'node:path'
import { clip, formatBytes } from './util.js'
import { detectDelimiter, parseDelimited, parseJsonl } from './metadata.js'

const MEDIA_TYPES = new Map([
  ['.png', 'image/png'], ['.jpg', 'image/jpeg'], ['.jpeg', 'image/jpeg'],
  ['.gif', 'image/gif'], ['.bmp', 'image/bmp'], ['.webp', 'image/webp'],
  ['.tif', 'image/tiff'], ['.tiff', 'image/tiff'], ['.svs', 'image/tiff'],
  ['.csv', 'text/csv'], ['.tsv', 'text/tab-separated-values'], ['.txt', 'text/plain'],
  ['.md', 'text/markdown'], ['.json', 'application/json'], ['.jsonl', 'application/x-ndjson'],
  ['.xml', 'application/xml'], ['.yaml', 'application/yaml'], ['.yml', 'application/yaml'],
  ['.pdf', 'application/pdf'], ['.zip', 'application/zip'], ['.gz', 'application/gzip'],
  ['.tar', 'application/x-tar'], ['.nii', 'application/x-nifti'], ['.npy', 'application/x-npy'],
  ['.h5', 'application/x-hdf5'], ['.hdf5', 'application/x-hdf5'], ['.mat', 'application/x-matlab'],
  ['.fcs', 'application/vnd.isac.fcs'], ['.czi', 'application/x-zeiss-czi'],
  ['.nd2', 'application/x-nikon-nd2'], ['.lif', 'application/x-leica-lif'],
])

const TEXT_EXTENSIONS = new Set([
  '.csv', '.tsv', '.txt', '.md', '.json', '.jsonl', '.ndjson', '.xml', '.yaml', '.yml',
  '.ini', '.cfg', '.log', '.py', '.r', '.m', '.sh', '.tex', '.html', '.htm',
])

/** Guess a media type from the extension. */
export function mediaType(path) {
  return MEDIA_TYPES.get(extname(path).toLowerCase()) ?? 'application/octet-stream'
}

/** Classify a file by extension and content probe. */
export function fileKind(path) {
  const extension = extname(path).toLowerCase()
  if (MEDIA_TYPES.get(extension)?.startsWith('image/')) return 'image'
  if (['.csv', '.tsv', '.tab'].includes(extension)) return 'table'
  if (['.json', '.jsonl', '.ndjson'].includes(extension)) return 'structured-text'
  if (['.pdf'].includes(extension)) return 'document'
  if (['.zip', '.gz', '.tar', '.7z', '.rar'].includes(extension)) return 'archive'
  if (TEXT_EXTENSIONS.has(extension)) return 'text'
  return 'binary'
}

/**
 * Recursively list a source directory without following symlinks.
 * @returns {Promise<{root: string, files: Array<object>, directories: number, truncated: boolean}>}
 */
export async function walkSource(root, options = {}) {
  const maxFiles = options.maxFiles ?? 500
  const maxDepth = options.maxDepth ?? 8
  const absoluteRoot = resolve(root)
  const files = []
  let directories = 0
  let truncated = false
  const skip = new Set(options.skip ?? ['.git', 'node_modules', '__pycache__', '.venv'])

  const walk = async (directory, depth) => {
    if (truncated) return
    let entries
    try {
      entries = await readdir(directory, { withFileTypes: true })
    } catch (error) {
      if (error?.code === 'ENOENT') return
      throw error
    }
    entries.sort((a, b) => a.name.localeCompare(b.name))
    for (const entry of entries) {
      if (truncated) return
      if (skip.has(entry.name)) continue
      const full = join(directory, entry.name)
      const rel = relative(absoluteRoot, full)
      if (entry.isDirectory()) {
        directories += 1
        if (depth >= maxDepth) {
          truncated = true
          return
        }
        await walk(full, depth + 1)
      } else if (entry.isFile()) {
        if (files.length >= maxFiles) {
          truncated = true
          return
        }
        const info = await stat(full)
        files.push({
          path: full,
          relative: rel,
          name: entry.name,
          ext: extname(entry.name).toLowerCase(),
          size: info.size,
          media_type: mediaType(entry.name),
          kind: fileKind(entry.name),
        })
      }
    }
  }

  const rootInfo = await stat(absoluteRoot)
  if (rootInfo.isFile()) {
    files.push({
      path: absoluteRoot,
      relative: basename(absoluteRoot),
      name: basename(absoluteRoot),
      ext: extname(absoluteRoot).toLowerCase(),
      size: rootInfo.size,
      media_type: mediaType(absoluteRoot),
      kind: fileKind(absoluteRoot),
    })
  } else {
    await walk(absoluteRoot, 0)
  }
  return { root: absoluteRoot, files, directories, truncated }
}

/** Read at most `bytes` from the start of a file. */
async function readHead(path, bytes) {
  const handle = await open(path, 'r')
  try {
    const buffer = Buffer.alloc(bytes)
    const { bytesRead } = await handle.read(buffer, 0, bytes, 0)
    return buffer.subarray(0, bytesRead)
  } finally {
    await handle.close()
  }
}

/** Decide whether a byte sample is probably UTF-8 text. */
export function isProbablyText(buffer) {
  if (buffer.length === 0) return true
  if (buffer.includes(0)) return false
  const decoded = buffer.toString('utf8')
  const replacement = (decoded.match(/\uFFFD/g) ?? []).length
  return replacement / Math.max(1, decoded.length) < 0.02
}

/** Parse image dimensions from common scientific/raster formats. */
export function imageSize(buffer) {
  try {
    if (buffer.length >= 24 && buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
      return {
        format: 'png',
        width: buffer.readUInt32BE(16),
        height: buffer.readUInt32BE(20),
        bit_depth: buffer[24],
        channels: pngChannels(buffer[25]),
      }
    }
    if (buffer.length >= 10 && (buffer.subarray(0, 6).toString('ascii') === 'GIF87a' || buffer.subarray(0, 6).toString('ascii') === 'GIF89a')) {
      return {
        format: 'gif',
        width: buffer.readUInt16LE(6),
        height: buffer.readUInt16LE(8),
        bit_depth: (buffer[10] & 0x07) + 1,
        channels: 3,
      }
    }
    if (buffer.length >= 26 && buffer.subarray(0, 2).toString('ascii') === 'BM') {
      return {
        format: 'bmp',
        width: buffer.readInt32LE(18),
        height: Math.abs(buffer.readInt32LE(22)),
        bit_depth: buffer.readUInt16LE(28),
        channels: 3,
      }
    }
    if (buffer.length >= 12 && buffer.subarray(0, 4).toString('ascii') === 'RIFF' && buffer.subarray(8, 12).toString('ascii') === 'WEBP') {
      return webpSize(buffer)
    }
    if (buffer.length >= 4 && buffer[0] === 0xFF && buffer[1] === 0xD8) return jpegSize(buffer)
    if (buffer.length >= 8 && (buffer.subarray(0, 2).toString('ascii') === 'II' || buffer.subarray(0, 2).toString('ascii') === 'MM')) {
      return tiffSize(buffer)
    }
    return undefined
  } catch {
    return undefined
  }
}

function pngChannels(colorType) {
  if (colorType === 0) return 1
  if (colorType === 2) return 3
  if (colorType === 3) return 1
  if (colorType === 4) return 2
  if (colorType === 6) return 4
  return undefined
}

function jpegSize(buffer) {
  let offset = 2
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xFF) {
      offset += 1
      continue
    }
    const marker = buffer[offset + 1]
    if (marker === 0xD8 || marker === 0xD9) {
      offset += 2
      continue
    }
    const length = buffer.readUInt16BE(offset + 2)
    if (marker >= 0xC0 && marker <= 0xCF && ![0xC4, 0xC8, 0xCC].includes(marker)) {
      return {
        format: 'jpeg',
        bit_depth: buffer[offset + 4],
        height: buffer.readUInt16BE(offset + 5),
        width: buffer.readUInt16BE(offset + 7),
        channels: buffer[offset + 9],
      }
    }
    offset += 2 + length
  }
  return undefined
}

function webpSize(buffer) {
  const chunk = buffer.subarray(12, 16).toString('ascii')
  if (chunk === 'VP8 ' && buffer.length >= 30) {
    return {
      format: 'webp',
      width: buffer.readUInt16LE(26) & 0x3FFF,
      height: buffer.readUInt16LE(28) & 0x3FFF,
      channels: 3,
    }
  }
  if (chunk === 'VP8L' && buffer.length >= 25) {
    const bits = buffer.readUInt32LE(21)
    return {
      format: 'webp',
      width: (bits & 0x3FFF) + 1,
      height: ((bits >> 14) & 0x3FFF) + 1,
      channels: 4,
    }
  }
  if (chunk === 'VP8X' && buffer.length >= 30) {
    return {
      format: 'webp',
      width: buffer.readUIntLE(24, 3) + 1,
      height: buffer.readUIntLE(27, 3) + 1,
      channels: 4,
    }
  }
  return undefined
}

function tiffSize(buffer) {
  const little = buffer.subarray(0, 2).toString('ascii') === 'II'
  const read16 = (offset) => (little ? buffer.readUInt16LE(offset) : buffer.readUInt16BE(offset))
  const read32 = (offset) => (little ? buffer.readUInt32LE(offset) : buffer.readUInt32BE(offset))
  if (read16(2) !== 42) return undefined
  const ifd = read32(4)
  if (ifd + 2 > buffer.length) return undefined
  const count = read16(ifd)
  let width
  let height
  let bitDepth
  let channels
  for (let index = 0; index < count; index += 1) {
    const entry = ifd + 2 + index * 12
    if (entry + 12 > buffer.length) break
    const tag = read16(entry)
    const type = read16(entry + 2)
    const valueCount = read32(entry + 4)
    const size = type === 3 ? 2 : type === 4 ? 4 : 1
    const valueOffset = size * valueCount <= 4 ? entry + 8 : read32(entry + 8)
    const readValue = (position) => (type === 3 ? read16(position) : type === 4 ? read32(position) : buffer[position])
    if (tag === 256) width = readValue(valueOffset)
    else if (tag === 257) height = readValue(valueOffset)
    else if (tag === 258) bitDepth = readValue(valueOffset)
    else if (tag === 277) channels = readValue(valueOffset)
  }
  if (!width || !height) return undefined
  return { format: 'tiff', width, height, bit_depth: bitDepth, channels }
}

/**
 * Inspect one file and return model-readable facts.
 * @param {string} path
 * @param {{maxTextChars?: number}} options
 */
export async function inspectFile(path, options = {}) {
  const info = await stat(path)
  const maxTextChars = options.maxTextChars ?? 4000
  const extension = extname(path).toLowerCase()
  const result = {
    path,
    name: basename(path),
    ext: extension,
    size: info.size,
    size_human: formatBytes(info.size),
    media_type: mediaType(path),
    kind: fileKind(path),
    modified_at: info.mtime.toISOString(),
  }

  const head = await readHead(path, Math.min(info.size, 64 * 1024, 64 * 1024))
  const image = imageSize(head)
  if (image) result.image = image

  const probableText = isProbablyText(head.subarray(0, 8192)) && info.size < 64 * 1024 * 1024
  if (probableText && ['table', 'structured-text', 'text', 'document'].includes(result.kind)) {
    const text = head.toString('utf8')
    if (result.kind === 'table') {
      const delimiter = extension === '.tsv' ? '\t' : detectDelimiter(text)
      const parsed = parseDelimited(text, delimiter, { maxRows: 8 })
      result.table = {
        delimiter: delimiter === '\t' ? 'tab' : delimiter,
        columns: parsed.header,
        sample_rows: parsed.rows.slice(0, 5),
      }
    } else if (result.kind === 'structured-text') {
      try {
        if (extension === '.jsonl' || extension === '.ndjson') {
          const { records } = parseJsonl(text.split(/\r?\n/).slice(0, 5).join('\n'))
          result.json = { records: records.slice(0, 3) }
        } else {
          const parsed = JSON.parse(text)
          result.json = Array.isArray(parsed)
            ? { array_length: parsed.length, sample: parsed.slice(0, 2) }
            : { keys: Object.keys(parsed).slice(0, 40), sample: parsed }
        }
      } catch {
        result.text_preview = clip(text, maxTextChars)
      }
    } else {
      result.text_preview = clip(text, maxTextChars)
    }
  } else if (result.kind === 'text' || probableText) {
    result.text_preview = clip(head.toString('utf8'), maxTextChars)
  }

  return result
}

/** Inspect a list of source paths (files or directories). */
export async function inspectSources(paths, options = {}) {
  const maxFiles = options.maxFiles ?? 80
  const groups = []
  const flat = []
  for (const input of paths ?? []) {
    const absolute = resolve(input)
    const walked = await walkSource(absolute, { maxFiles, maxDepth: options.maxDepth })
    const inspectable = walked.files.slice(0, options.maxInspected ?? 40)
    const inspected = []
    for (const file of inspectable) {
      try {
        inspected.push(await inspectFile(file.path, options))
      } catch (error) {
        inspected.push({ path: file.path, name: file.name, error: error.message })
      }
    }
    groups.push({
      root: absolute,
      directories: walked.directories,
      file_count: walked.files.length,
      truncated: walked.truncated,
      files: inspected,
    })
    flat.push(...inspected)
  }
  return { groups, files: flat }
}

/** Compact textual dossier of inspected sources for prompts. */
export function inspectSummary(inspection, maxFiles = 40) {
  const lines = []
  for (const group of inspection?.groups ?? []) {
    lines.push(`Source: ${group.root} (${group.file_count} files, ${group.directories} directories${group.truncated ? ', truncated' : ''})`)
    for (const file of group.files.slice(0, maxFiles)) {
      lines.push(`- ${file.name} | ${file.kind} | ${file.media_type} | ${file.size_human ?? file.size}`)
      if (file.image) {
        lines.push(`  image: ${file.image.width}x${file.image.height} px, ${file.image.channels ?? '?'} channel(s), ${file.image.bit_depth ?? '?'} bit`)
      }
      if (file.table) {
        lines.push(`  table columns: ${file.table.columns.join(', ')}`)
        lines.push(`  sample rows: ${JSON.stringify(file.table.sample_rows.slice(0, 3))}`)
      }
      if (file.json) {
        lines.push(`  json: ${clip(JSON.stringify(file.json), 800)}`)
      }
      if (file.text_preview) {
        lines.push(`  text excerpt: ${clip(file.text_preview.replace(/\s+/g, ' '), 700)}`)
      }
    }
    if (group.files.length > maxFiles) lines.push(`  ... ${group.files.length - maxFiles} more inspected files`)
  }
  return lines.join('\n')
}
