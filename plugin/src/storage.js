/**
 * Storage seam for the scientific data lake.
 *
 * The metadata catalog and dataset blobs are addressed by POSIX-style keys
 * relative to a backend root. The local backend stores them on disk today;
 * object-store backends can implement the same interface without touching the
 * workflows. Keys are never absolute and never contain `..`.
 *
 * @module scidatamas/storage
 */
import { createReadStream } from 'node:fs'
import {
  copyFile,
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { normalizeKey, safeJoin, sha256, writeTextAtomic } from './util.js'

/**
 * Contract every storage backend implements.
 * @abstract
 */
export class StorageBackend {
  /** @param {{root?: string, prefix?: string}} options */
  constructor(options = {}) {
    this.options = options
    this.prefix = String(options.prefix ?? '').replace(/^\/+|\/+$/g, '')
  }

  /** Prepare the backend (create buckets/directories). */
  async init() {}

  /** Human-readable backend kind. */
  get kind() {
    return 'abstract'
  }

  /** Stable URI for a key, recorded in manifests. */
  uri(key) {
    throw new Error('uri() is not implemented')
  }

  /** Absolute local path for a key, or undefined if the backend is remote. */
  localPath(_key) {
    return undefined
  }

  /** Read UTF-8 text. */
  async readText(_key) {
    throw new Error('readText() is not implemented')
  }

  /** Write UTF-8 text. */
  async writeText(_key, _text) {
    throw new Error('writeText() is not implemented')
  }

  /** Write a Buffer. */
  async writeBuffer(_key, _buffer) {
    throw new Error('writeBuffer() is not implemented')
  }

  /** Read a Buffer. */
  async readBuffer(_key) {
    throw new Error('readBuffer() is not implemented')
  }

  /** Copy a host file into the backend. */
  async copyIn(_sourcePath, _key) {
    throw new Error('copyIn() is not implemented')
  }

  /** Check existence. */
  async exists(_key) {
    throw new Error('exists() is not implemented')
  }

  /** Stat one key, or undefined. */
  async stat(_key) {
    throw new Error('stat() is not implemented')
  }

  /** Recursively list keys under a prefix. */
  async list(_prefix = '') {
    throw new Error('list() is not implemented')
  }

  /** Remove a file or directory. */
  async remove(_key) {
    throw new Error('remove() is not implemented')
  }

  /** Read JSON, returning undefined when absent. */
  async readJson(key, fallback = undefined) {
    if (!(await this.exists(key))) return fallback
    const text = await this.readText(key)
    if (!text.trim()) return fallback
    return JSON.parse(text)
  }

  /** Write pretty JSON. */
  async writeJson(key, value) {
    await this.writeText(key, `${JSON.stringify(value, null, 2)}\n`)
  }

  /** Append one JSON line (audit logs). */
  async appendJsonLine(key, value) {
    const previous = (await this.exists(key)) ? await this.readText(key) : ''
    const line = `${JSON.stringify(value)}\n`
    await this.writeText(key, `${previous}${line}`)
  }
}

/** Local-filesystem backend, the default for a single machine. */
export class LocalStorage extends StorageBackend {
  /** @param {{root: string, prefix?: string}} options */
  constructor(options) {
    if (!options?.root) throw new Error('LocalStorage requires a root directory')
    super(options)
    this.root = resolve(options.root)
  }

  get kind() {
    return 'local'
  }

  keyWithPrefix(key) {
    const clean = normalizeKey(key)
    return this.prefix ? `${this.prefix}/${clean}` : clean
  }

  localPath(key) {
    return safeJoin(this.root, this.keyWithPrefix(key))
  }

  uri(key) {
    if (!key) return `local://${this.prefix}`
    return `local://${this.keyWithPrefix(key)}`
  }

  async init() {
    await mkdir(this.root, { recursive: true })
  }

  async readText(key) {
    return readFile(this.localPath(key), 'utf8')
  }

  async writeText(key, text) {
    await writeTextAtomic(this.localPath(key), text)
  }

  async writeBuffer(key, buffer) {
    const target = this.localPath(key)
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, buffer)
  }

  async readBuffer(key) {
    return readFile(this.localPath(key))
  }

  async copyIn(sourcePath, key, options = {}) {
    const sourceInfo = await stat(sourcePath)
    if (!sourceInfo.isFile()) throw new Error(`not a regular file: ${sourcePath}`)
    if (options.maxBytes && sourceInfo.size > options.maxBytes) {
      throw new Error(
        `file is too large: ${sourcePath} (${sourceInfo.size} bytes > ${options.maxBytes})`,
      )
    }
    const target = this.localPath(key)
    await mkdir(dirname(target), { recursive: true })
    const temp = `${target}.${process.pid}.${Date.now()}.tmp`
    await copyFile(sourcePath, temp)
    await rename(temp, target)
    return { key, size: sourceInfo.size, path: target }
  }

  async writeBufferAtomic(key, buffer) {
    const target = this.localPath(key)
    await mkdir(dirname(target), { recursive: true })
    const temp = `${target}.${process.pid}.${Date.now()}.tmp`
    await writeFile(temp, buffer)
    await rename(temp, target)
    return { key, size: buffer.byteLength, path: target }
  }

  async exists(key) {
    try {
      await stat(this.localPath(key))
      return true
    } catch (error) {
      if (error?.code === 'ENOENT' || error?.code === 'ENOTDIR') return false
      throw error
    }
  }

  async stat(key) {
    try {
      const info = await stat(this.localPath(key))
      return {
        key,
        type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other',
        size: info.size,
        mtime: info.mtime.toISOString(),
        path: this.localPath(key),
      }
    } catch (error) {
      if (error?.code === 'ENOENT' || error?.code === 'ENOTDIR') return undefined
      throw error
    }
  }

  async list(prefix = '') {
    const start = prefix ? this.localPath(prefix) : this.root
    const results = []
    const walk = async (directory, relativeKey) => {
      let entries
      try {
        entries = await readdir(directory, { withFileTypes: true })
      } catch (error) {
        if (error?.code === 'ENOENT') return
        throw error
      }
      for (const entry of entries) {
        const key = relativeKey ? `${relativeKey}/${entry.name}` : entry.name
        const full = join(directory, entry.name)
        if (entry.isDirectory()) {
          await walk(full, key)
        } else if (entry.isFile()) {
          const info = await stat(full)
          results.push({ key, size: info.size, mtime: info.mtime.toISOString() })
        }
      }
    }
    await walk(start, prefix ? normalizeKey(prefix) : '')
    return results
  }

  async remove(key) {
    await rm(this.localPath(key), { recursive: true, force: true })
  }

  /** Hash a stored file without loading it into memory. */
  async hashFile(key) {
    const hash = (await import('node:crypto')).createHash('sha256')
    await new Promise((resolvePromise, reject) => {
      const stream = createReadStream(this.localPath(key))
      stream.on('data', (chunk) => hash.update(chunk))
      stream.on('error', reject)
      stream.on('end', resolvePromise)
    })
    return hash.digest('hex')
  }
}

/**
 * Extension point for S3-compatible object storage.
 * Implement the StorageBackend methods with `@aws-sdk/client-s3` (or a
 * compatible client) and return this class from `createStorage()`.
 */
export class S3Storage extends StorageBackend {
  get kind() {
    return 's3'
  }

  uri(key) {
    return `s3://${this.options.bucket ?? 'bucket'}/${this.prefix ? `${this.prefix}/${key}` : key}`
  }

  async init() {
    throw new Error(
      'S3 storage is not implemented in 0.1. Implement StorageBackend in src/storage.js and select storageDriver="s3".',
    )
  }
}

/**
 * Extension point for Synology DiskStation storage (WebDAV or SMB mount).
 * A mounted SMB/WebDAV path can already be used through LocalStorage; this
 * class exists for a native API implementation.
 */
export class SynologyStorage extends StorageBackend {
  get kind() {
    return 'synology'
  }

  uri(key) {
    return `synology://${this.options.host ?? 'nas'}/${this.prefix ? `${this.prefix}/${key}` : key}`
  }

  async init() {
    throw new Error(
      'Synology storage is not implemented in 0.1. Mount the share and use storageDriver="local", or implement StorageBackend here.',
    )
  }
}

/** Build the configured backend. */
export function createStorage(config) {
  const driver = String(config.storageDriver ?? 'local').toLowerCase()
  if (driver === 'local') return new LocalStorage({ root: config.root, prefix: config.storagePrefix })
  if (driver === 's3') return new S3Storage({ root: config.root, prefix: config.storagePrefix, ...config.storageOptions })
  if (driver === 'synology' || driver === 'diskstation') {
    return new SynologyStorage({ root: config.root, prefix: config.storagePrefix, ...config.storageOptions })
  }
  throw new Error(`unknown storageDriver "${config.storageDriver}"; expected local, s3 or synology`)
}

/** Compute a SHA-256 of in-memory data. */
export function hashBuffer(buffer) {
  return sha256(buffer)
}
