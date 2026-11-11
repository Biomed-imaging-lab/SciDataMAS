import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { DEFAULTS } from '../src/defaults.js'
import { LocalStorage } from '../src/storage.js'
import { SciDataLake } from '../src/lake.js'
import { handleApiRequest } from '../src/web-api.js'

async function listen(handler) {
  const server = createServer(handler)
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  return {
    origin: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  }
}

test('web API serves the catalog, dataset details and artifact bytes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-api-'))
  const storage = new LocalStorage({ root: dir })
  const lake = new SciDataLake({ storage, config: { ...DEFAULTS, root: dir } })
  await lake.init()
  const dataset = await lake.createDataset({
    name: 'API set',
    description: 'API test',
    layout: 'files',
    schema: [{ name: 'modality', type: 'category', description: 'Modality' }],
  })
  await writeFile(join(dir, 'artifact.txt'), 'hello')
  await lake.putFile(dataset, join(dir, 'artifact.txt'), 'artifact.txt')
  await lake.appendRecords(dataset, [{
    id: 'r1',
    modality: 'microscopy',
    file_path: 'files/artifact.txt',
    author: 'tester',
    uploaded_at: new Date().toISOString(),
  }])
  const service = {
    config: { root: dir },
    storage,
    lake,
    async status() { return { root: dir, storage: 'local', datasets: 1 } },
    async listDatasets(options) { return lake.listDatasets(options) },
    async inspectDataset(id) {
      const manifest = await lake.getDataset(id)
      return {
        dataset: lake.summaryOf(manifest),
        schema: manifest.schema,
        sample_rows: await lake.readMetadata(manifest),
        events: await lake.readEvents(manifest),
        validation: null,
        table: null,
      }
    },
  }
  const server = await listen((req, res) => handleApiRequest({
    req,
    res,
    service,
    connection: { admit: () => ({ peer: { principal: { kind: 'owner' } } }) },
  }))
  try {
    const status = await fetch(`${server.origin}/scidatamas/api/status`)
    assert.equal(status.status, 200)
    assert.equal((await status.json()).status.storage, 'local')

    const list = await fetch(`${server.origin}/scidatamas/api/datasets`)
    const listBody = await list.json()
    assert.equal(listBody.datasets.length, 1)
    assert.equal(listBody.datasets[0].id, dataset.id)

    const detail = await fetch(`${server.origin}/scidatamas/api/datasets/${dataset.id}`)
    const detailBody = await detail.json()
    assert.equal(detailBody.dataset.id, dataset.id)
    assert.equal(detailBody.sample_rows[0].modality, 'microscopy')

    const content = await fetch(`${server.origin}/scidatamas/api/datasets/${dataset.id}/content?limit=10`)
    const contentBody = await content.json()
    assert.equal(contentBody.total, 1)
    assert.ok(contentBody.columns.includes('modality'))
    assert.equal(contentBody.rows[0].modality, 'microscopy')

    const csv = await fetch(`${server.origin}/scidatamas/api/datasets/${dataset.id}/content?format=csv`)
    assert.equal(csv.status, 200)
    assert.match(csv.headers.get('content-type'), /text\/csv/)
    const csvText = await csv.text()
    assert.match(csvText, /modality/)
    assert.match(csvText, /microscopy/)

    const file = await fetch(`${server.origin}/scidatamas/api/datasets/${dataset.id}/file?path=${encodeURIComponent('files/artifact.txt')}`)
    assert.equal(file.status, 200)
    assert.equal(await file.text(), 'hello')

    const traversal = await fetch(`${server.origin}/scidatamas/api/datasets/${dataset.id}/file?path=${encodeURIComponent('../catalog.json')}`)
    assert.equal(traversal.status, 403)
  } finally {
    await server.close()
    await rm(dir, { recursive: true, force: true })
  }
})

test('web API rejects non-owner peers', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-api-auth-'))
  const storage = new LocalStorage({ root: dir })
  const lake = new SciDataLake({ storage, config: { ...DEFAULTS, root: dir } })
  await lake.init()
  const service = { config: { root: dir }, storage, lake }
  const server = await listen((req, res) => handleApiRequest({
    req,
    res,
    service,
    connection: { admit: () => ({ rejection: 401 }) },
  }))
  try {
    const response = await fetch(`${server.origin}/scidatamas/api/datasets`)
    assert.equal(response.status, 401)
  } finally {
    await server.close()
    await rm(dir, { recursive: true, force: true })
  }
})
