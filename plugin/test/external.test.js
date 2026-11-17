import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { DEFAULTS } from '../src/defaults.js'
import { LocalStorage } from '../src/storage.js'
import { SciDataLake } from '../src/lake.js'
import { createDatasetWorkflow } from '../src/workflows/create.js'
import { stageAddWorkflow, commitStageWorkflow } from '../src/workflows/add.js'
import {
  parseExternalUrl,
  normalizeZenodoRecord,
  filterSourceFiles,
  matchesGlob,
  analyzeExternal,
  importExternalWorkflow,
} from '../src/workflows/external.js'

class FakeLlm {
  constructor(handlers) {
    this.handlers = handlers
  }

  async json({ user, purpose }) {
    const entry = Object.entries(this.handlers)
      .sort((a, b) => b[0].length - a[0].length)
      .find(([prefix]) => purpose === prefix || purpose.startsWith(prefix))
    if (!entry) throw new Error(`no fake handler for ${purpose}`)
    const value = typeof entry[1] === 'function' ? await entry[1]({ user, purpose }) : entry[1]
    return { value, raw: JSON.stringify(value), usage: {}, route: { provider: 'fake', model: 'fake' } }
  }
}

function config(root) {
  return {
    ...DEFAULTS,
    root,
    maxFileBytes: 10 * 1024 * 1024,
    maxDownloadBytes: 10 * 1024 * 1024,
    maxRowsScan: 1000,
    maxSchemaFields: 50,
    requestTimeoutMs: 5000,
    allowNetwork: true,
  }
}

function zenodoPayload() {
  return {
    id: 123,
    doi: '10.5281/zenodo.123',
    metadata: {
      title: 'Example measurements',
      description: 'A small tabular example.',
      creators: [{ name: 'A. Author' }],
      publication_date: '2026-01-02',
      license: { id: 'CC-BY-4.0' },
      keywords: ['example'],
      resource_type: { title: 'Dataset' },
    },
    files: [{
      key: 'data/data.csv',
      size: 26,
      checksum: 'md5:abc',
      links: { self: 'https://zenodo.org/records/123/files/data.csv?download=1' },
    }],
  }
}

test('external URL parsing supports Zenodo pages, API and DOI', () => {
  assert.equal(parseExternalUrl('https://zenodo.org/records/123').id, '123')
  assert.equal(parseExternalUrl('https://zenodo.org/api/records/123').id, '123')
  assert.equal(parseExternalUrl('https://doi.org/10.5281/zenodo.123').id, '123')
  assert.equal(parseExternalUrl('https://example.org/data.csv').kind, 'url')
  assert.throws(() => parseExternalUrl('ftp://example.org/x'), /http/)
})

test('Zenodo records normalize into source files and metadata', () => {
  const source = normalizeZenodoRecord(zenodoPayload(), '123')
  assert.equal(source.kind, 'zenodo')
  assert.equal(source.title, 'Example measurements')
  assert.equal(source.files.length, 1)
  assert.equal(source.files[0].key, 'data/data.csv')
  assert.equal(source.total_bytes, 26)
  assert.deepEqual(source.creators, ['A. Author'])
})

test('include/exclude globs filter source files', () => {
  assert.equal(matchesGlob('data/data.csv', '**/*.csv'), true)
  assert.equal(matchesGlob('data/data.csv', '*.csv'), false)
  assert.equal(matchesGlob('data/data.csv', '**/*.tif'), false)
  const files = [
    { key: 'a/x.csv', name: 'x.csv' },
    { key: 'a/y.tif', name: 'y.tif' },
    { key: 'README.txt', name: 'README.txt' },
  ]
  const result = filterSourceFiles(files, { include: ['**/*.csv', '**/*.tif'], maxFiles: 10 })
  assert.equal(result.selected.length, 2)
  assert.equal(result.skipped, 1)
  // Empty arrays from a tool call mean "no filter", not "match nothing".
  assert.equal(filterSourceFiles(files, { include: [], maxFiles: 10 }).selected.length, 3)
  assert.equal(filterSourceFiles(files, { include: [], exclude: [], maxFiles: 10 }).selected.length, 3)
})

test('analyzeExternal reads a Zenodo record through the API', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url) => {
    assert.match(String(url), /api\/records\/123/)
    return new Response(JSON.stringify(zenodoPayload()), { status: 200, headers: { 'content-type': 'application/json' } })
  }
  try {
    const source = await analyzeExternal({
      url: 'https://zenodo.org/records/123',
      config: config('/tmp/never-used'),
    })
    assert.equal(source.record_id, '123')
    assert.equal(source.files[0].download_url, 'https://zenodo.org/records/123/files/data.csv?download=1')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('importExternalWorkflow downloads, creates, annotates and commits', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-import-'))
  const originalFetch = globalThis.fetch
  try {
    const csv = 'id,age\np1,10\np2,20\n'
    globalThis.fetch = async (url) => {
      const href = String(url)
      if (href.includes('/api/records/123')) {
        return new Response(JSON.stringify({ ...zenodoPayload(), files: [{ ...zenodoPayload().files[0], size: Buffer.byteLength(csv) }] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
      if (href.includes('data.csv')) {
        return new Response(csv, { status: 200, headers: { 'content-type': 'text/csv' } })
      }
      throw new Error(`unexpected fetch ${href}`)
    }
    const storage = new LocalStorage({ root: dir })
    const lake = new SciDataLake({ storage, config: config(dir) })
    await lake.init()
    const llm = new FakeLlm({
      'create.single_call': {
        fields: [{ name: 'age', type: 'integer', description: 'Age in years' }],
      },
      'external.map': {
        values: { license: 'CC-BY-4.0', creator: 'A. Author', doi: '10.5281/zenodo.123' },
      },
      'add.fill': { records: [] },
    })
    const result = await importExternalWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      input: { url: 'https://zenodo.org/records/123', mode: 'import', max_files: 1 },
      createDataset: (options) => createDatasetWorkflow({
        lake,
        llm,
        config: config(dir),
        exec: {},
        input: options.input,
        rich: options.rich,
      }),
      stageAdd: (options) => stageAddWorkflow({
        lake,
        llm,
        config: config(dir),
        exec: {},
        dataset: options.dataset,
        input: options.input,
      }),
      commitStage: (options) => commitStageWorkflow({
        lake,
        config: config(dir),
        dataset: options.dataset,
        stage: options.stage,
        overrides: options.overrides,
        notes: options.notes,
        activate: options.activate,
      }),
    })
    assert.equal(result.mode, 'import')
    assert.equal(result.committed, 1)
    const manifest = await lake.getDataset(result.dataset.id)
    assert.equal(manifest.provenance, 'external')
    assert.equal(manifest.source.doi, '10.5281/zenodo.123')
    assert.equal(manifest.counts.files, 1)
    const rows = await lake.readMetadata(manifest)
    assert.equal(rows[0].license, 'CC-BY-4.0')
    assert.equal(rows[0].source_url, 'https://zenodo.org/records/123')
    assert.equal((await readFile(join(dir, 'datasets', manifest.id, 'files', 'data', 'data.csv'), 'utf8')), csv)
  } finally {
    globalThis.fetch = originalFetch
    await rm(dir, { recursive: true, force: true })
  }
})
