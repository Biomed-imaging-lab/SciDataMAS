import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { DEFAULTS } from '../src/defaults.js'
import { LocalStorage } from '../src/storage.js'
import { SciDataLake, LakeError, chooseRowKey } from '../src/lake.js'
import {
  normalizeSchema,
  validateRecord,
  parseDelimited,
  detectDelimiter,
  toCsv,
  readTable,
  coerceValue,
} from '../src/metadata.js'
import { runQuery, validateFilter, matches } from '../src/filter.js'
import { extractJson, slugify, normalizeKey, jsonSafe } from '../src/util.js'

function testConfig(root) {
  return { ...DEFAULTS, root, maxFileBytes: 10 * 1024 * 1024, maxRowsScan: 1000 }
}

test('jsonSafe removes undefined and normalizes JSON-lossless values', () => {
  const value = jsonSafe({ a: 1, b: undefined, c: Number.NaN, d: new Date('2026-01-02T03:04:05Z'), e: [1, undefined] })
  assert.deepEqual(value, { a: 1, c: null, d: '2026-01-02T03:04:05.000Z', e: [1, null] })
  const circular = { ok: true }; circular.self = circular
  assert.equal(jsonSafe(circular).self, '[circular]')
})

test('slugify handles Cyrillic and unsafe names', () => {
  assert.equal(slugify('Микроскопия 2026!'), 'mikroskopiya-2026')
  assert.equal(slugify('  '), 'dataset')
})

test('normalizeKey rejects traversal', () => {
  assert.equal(normalizeKey('a/b.txt'), 'a/b.txt')
  assert.throws(() => normalizeKey('../x'), /escapes/)
  assert.throws(() => normalizeKey('/abs'), /relative/)
})

test('extractJson tolerates fences, prose and trailing commas', () => {
  assert.deepEqual(extractJson('Here:\n```json\n{"a": 1,}\n```\ndone'), { a: 1 })
  assert.deepEqual(extractJson('x [1, 2] y'), [1, 2])
  assert.throws(() => extractJson('not json'), /could not extract JSON/)
})

test('normalizeSchema adds system fields, dedupes, and maps table columns', () => {
  const schema = normalizeSchema([
    { name: 'Pixel size', type: 'float', description: 'nm per pixel' },
    { name: 'pixel_size', type: 'int', description: 'duplicate' },
    { name: 'id', type: 'string', description: 'reserved' },
  ], { layout: 'table', columns: [{ name: 'Pixel size', type: 'number' }, { name: 'age', type: 'integer' }] })
  const names = schema.fields.map((field) => field.name)
  assert.equal(names[0], 'id')
  assert.ok(names.includes('pixel_size'))
  assert.equal(names.filter((name) => name === 'pixel_size').length, 1)
  assert.equal(schema.rejected[0].name, 'id')
  const pixel = schema.fields.find((field) => field.name === 'pixel_size')
  assert.equal(pixel.scope, 'column')
  assert.equal(pixel.source, 'Pixel size')
  assert.ok(schema.fields.find((field) => field.name === 'age'))
})

test('validateRecord coerces and reports missing/unknown', () => {
  const schema = normalizeSchema([
    { name: 'age', type: 'integer', description: 'years', required: true },
    { name: 'ok', type: 'boolean', description: 'flag' },
  ])
  const result = validateRecord({ age: '42', ok: 'yes', extra: 1 }, schema)
  assert.deepEqual(result.record, { age: 42, ok: true })
  assert.deepEqual(result.unknown, ['extra'])
  assert.deepEqual(result.missing, [])
  const missing = validateRecord({}, schema)
  assert.deepEqual(missing.missing, ['age'])
  assert.equal(coerceValue('abc', 'integer').error, 'is not an integer')
})

test('CSV parser handles quotes, embedded newlines and delimiters', () => {
  const text = 'a,b\r\n"x,1","line\nbreak"\r\n2,3\r\n'
  const parsed = parseDelimited(text, ',')
  assert.deepEqual(parsed.header, ['a', 'b'])
  assert.deepEqual(parsed.rows, [['x,1', 'line\nbreak'], ['2', '3']])
  assert.equal(detectDelimiter('a\tb\tc\n1\t2\t3'), '\t')
  const csv = toCsv([{ a: 'x,1', b: 'q"q' }], ['a', 'b'])
  assert.match(csv, /"x,1"/)
})

test('readTable parses CSV and JSONL into columns', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-table-'))
  try {
    const csv = join(dir, 'data.csv')
    await writeFile(csv, 'subject,age\ns1,10\ns2,20\n')
    const table = await readTable(csv)
    assert.deepEqual(table.columns.map((column) => column.name), ['subject', 'age'])
    assert.equal(table.rows.length, 2)
    assert.equal(table.columns[1].type, 'integer')
    const jsonl = join(dir, 'data.jsonl')
    await writeFile(jsonl, '{"a":1}\n{"a":2,"b":"x"}\n')
    const fromJsonl = await readTable(jsonl)
    assert.deepEqual(fromJsonl.columns.map((column) => column.name).sort(), ['a', 'b'])
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('storage rejects traversal and round-trips JSON', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-store-'))
  try {
    const storage = new LocalStorage({ root: dir })
    await storage.init()
    await storage.writeJson('a/b.json', { ok: true })
    assert.deepEqual(await storage.readJson('a/b.json'), { ok: true })
    assert.equal(await storage.exists('a/b.json'), true)
    assert.throws(() => storage.localPath('../escape'), /escapes/)
    assert.equal((await storage.list('a')).length, 1)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('lake creates, updates and appends file records', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-lake-'))
  try {
    const storage = new LocalStorage({ root: dir })
    const lake = new SciDataLake({ storage, config: testConfig(dir) })
    await lake.init()
    const dataset = await lake.createDataset({
      name: 'Imaging test',
      description: 'Two mock images',
      layout: 'files',
      schema: [
        { name: 'modality', type: 'category', description: 'imaging modality', required: true },
        { name: 'width', type: 'integer', description: 'pixels' },
      ],
    })
    assert.equal(dataset.status, 'draft')
    const validated = lake.validateRecords(dataset, [{ modality: 'microscopy', width: '512' }], { author: 'tester', filePath: 'files/a.tif' })
    assert.equal(validated.errors.length, 0)
    assert.equal(validated.prepared[0].record.width, 512)
    const added = await lake.appendRecords(dataset, [validated.prepared[0].record])
    assert.equal(added.length, 1)
    assert.equal(dataset.counts.records, 1)
    const rows = await lake.readMetadata(dataset)
    assert.equal(rows[0].author, 'tester')
    assert.equal(rows[0].file_path, 'files/a.tif')
    const updated = await lake.updateDataset(dataset.id, {
      description: 'Updated',
      schema: [
        { name: 'modality', type: 'category', description: 'imaging modality', required: true },
        { name: 'pixel_size_nm', type: 'number', description: 'nm per pixel' },
      ],
      allow_removals: true,
    })
    assert.equal(updated.schema_version, 2)
    assert.equal(updated.validated_schema_version, null)
    await assert.rejects(
      () => lake.updateDataset(dataset.id, { schema: [{ name: 'only', type: 'string', description: 'x' }] }),
      (error) => error instanceof LakeError && error.code === 'SCIDATAMAS_SCHEMA_REMOVAL',
    )
    assert.equal((await lake.listDatasets()).length, 1)
    const csv = await readFile(join(dir, 'datasets', dataset.id, 'metadata.csv'), 'utf8')
    assert.match(csv, /modality/)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('lake table datasets keep the table canonical and merge sidecar rows', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-tablelake-'))
  try {
    const tablePath = join(dir, 'measurements.csv')
    await writeFile(tablePath, 'id,age,group\np1,10,control\np2,20,treatment\n')
    const storage = new LocalStorage({ root: dir })
    const lake = new SciDataLake({ storage, config: testConfig(dir) })
    await lake.init()
    const dataset = await lake.createDataset({
      name: 'Measurements',
      description: 'Tabular measurements',
      layout: 'table',
      schema: [{ name: 'age', type: 'integer', description: 'years', required: true }],
    })
    const table = await lake.registerTable(dataset, tablePath)
    assert.equal(table.row_key, 'id')
    assert.equal(table.row_count, 2)
    const fieldNames = dataset.schema.fields.map((field) => field.name)
    assert.ok(fieldNames.includes('age'))
    assert.ok(fieldNames.includes('group'))
    assert.equal(dataset.schema.fields.find((field) => field.name === 'age').scope, 'column')
    // Column fields are satisfied by the table and should not block a sidecar update.
    const validated = lake.validateRecords(dataset, [{ id: 'p1', group: 'control' }], { author: 't', partial: true })
    assert.deepEqual(validated.missing, [])
    await lake.appendRecords(dataset, [{ id: 'p1', id_check: undefined, note_extra: undefined }].map((row) => {
      const clean = { ...row }
      delete clean.id_check
      delete clean.note_extra
      return clean
    }), { mode: 'upsert' })
    const rows = await lake.tableRecords(dataset)
    assert.equal(rows.length, 2)
    assert.equal(rows[0].age, 10)
    assert.equal(rows[0].group, 'control')
    assert.equal(rows[1].group, 'treatment')
    assert.equal(rows[0].file_path, dataset.table.path)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('chooseRowKey falls back on duplicate keys', () => {
  const table = {
    columns: [{ name: 'id' }, { name: 'x' }],
    rows: [{ id: 'a', x: 1 }, { id: 'a', x: 2 }],
  }
  assert.equal(chooseRowKey(table, 'id').name, '__row_index__')
})

test('filter DSL validates and evaluates', () => {
  const rows = [
    { id: 'a', age: 10, group: 'control', note: 'hello' },
    { id: 'b', age: 20, group: 'treatment', note: 'world' },
  ]
  validateFilter({ and: [{ field: 'age', op: 'gte', value: 10 }, { field: 'group', op: 'in', value: ['control'] }] }, ['id', 'age', 'group', 'note'])
  assert.throws(() => validateFilter({ field: 'nope', op: 'eq', value: 1 }, ['age']), /unknown field/)
  assert.equal(matches(rows[0], { field: 'age', op: 'between', value: [5, 15] }), true)
  assert.equal(matches(rows[1], { field: 'note', op: 'contains', value: 'ORL' }), true)
  const result = runQuery(rows, { filter: { field: 'age', op: 'gte', value: 15 }, fields: ['id'] })
  assert.deepEqual(result.rows, [{ id: 'b' }])
  assert.equal(result.matched, 1)
})
