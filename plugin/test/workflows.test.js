import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { DEFAULTS } from '../src/defaults.js'
import { LocalStorage } from '../src/storage.js'
import { SciDataLake } from '../src/lake.js'
import { createDatasetWorkflow } from '../src/workflows/create.js'
import { generateDagSchema, validateDag } from '../src/workflows/dag.js'
import { validateSchemaWorkflow } from '../src/workflows/debate.js'
import { addDataWorkflow, commitStageWorkflow } from '../src/workflows/add.js'
import { getDataWorkflow } from '../src/workflows/query.js'

class FakeLlm {
  constructor(handlers) {
    this.handlers = handlers
    this.calls = []
  }

  async json({ system, user, purpose }) {
    this.calls.push({ system, user, purpose })
    const entry = Object.entries(this.handlers)
      .sort((a, b) => b[0].length - a[0].length)
      .find(([prefix]) => purpose === prefix || purpose.startsWith(`${prefix}.`) || purpose.startsWith(prefix))
    if (!entry) throw new Error(`no fake handler for purpose ${purpose}`)
    const value = typeof entry[1] === 'function'
      ? await entry[1]({ system, user, purpose })
      : entry[1]
    return { value, raw: JSON.stringify(value), usage: {}, route: { provider: 'fake', model: 'fake' } }
  }
}

function config(root) {
  return {
    ...DEFAULTS,
    root,
    maxFileBytes: 10 * 1024 * 1024,
    maxRowsScan: 1000,
    maxSchemaFields: 50,
    maxDagNodes: 10,
    debateRoles: 2,
    debateQuestionsPerRole: 2,
    debateRuns: 2,
    maxDebateRuns: 3,
    dagConcurrency: 2,
  }
}

async function makeLake(root) {
  const storage = new LocalStorage({ root })
  const lake = new SciDataLake({ storage, config: config(root) })
  await lake.init()
  return lake
}

test('single-call creation stores a schema with organizational fields', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-create-'))
  try {
    const lake = await makeLake(dir)
    const sample = join(dir, 'image.png')
    // A minimal PNG header is enough for the inspector to read dimensions.
    const png = Buffer.alloc(33)
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(png, 0)
    png.writeUInt32BE(640, 16)
    png.writeUInt32BE(480, 20)
    png[24] = 8
    png[25] = 2
    await writeFile(sample, png)
    const llm = new FakeLlm({
      'create.single_call': {
        name: 'microscopy',
        description: 'Images',
        fields: [
          { name: 'modality', type: 'category', description: 'Imaging modality', required: true },
          { name: 'width_px', type: 'integer', description: 'Image width in pixels', unit: 'px' },
        ],
      },
    })
    const result = await createDatasetWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      input: {
        name: 'Microscopy 2026',
        description: 'Fluorescence images of fixed cells.',
        purpose: 'Compare staining protocols.',
        layout: 'files',
        example_paths: [sample],
      },
    })
    assert.equal(result.dataset.id, 'microscopy-2026')
    assert.equal(result.dataset.status, 'draft')
    const names = result.schema.fields.map((field) => field.name)
    for (const name of ['id', 'author', 'uploaded_at', 'file_path', 'source_url', 'modality', 'width_px']) {
      assert.ok(names.includes(name), `missing ${name}`)
    }
    assert.equal(result.schema.fields.find((field) => field.name === 'width_px').unit, 'px')
    const manifest = await lake.getDataset(result.dataset.id)
    assert.equal(manifest.schema_version, 1)
    assert.equal(manifest.counts.records, 0)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('table creation keeps the table and describes columns', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-createtable-'))
  try {
    const lake = await makeLake(dir)
    const tablePath = join(dir, 'measurements.csv')
    await writeFile(tablePath, 'id,age,group\np1,10,control\np2,20,treatment\n')
    const llm = new FakeLlm({
      'create.table': {
        description: 'Measurements',
        fields: [{ name: 'age', type: 'integer', description: 'Age in years', scope: 'column' }],
      },
    })
    const result = await createDatasetWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      input: {
        name: 'Measurements',
        description: 'Tabular measurements per participant.',
        layout: 'table',
        table_path: tablePath,
      },
    })
    assert.equal(result.dataset.layout, 'table')
    assert.equal(result.table.row_key, 'id')
    assert.equal(result.table.rows, 2)
    const manifest = await lake.getDataset(result.dataset.id)
    assert.equal(manifest.table.path, 'datasets/measurements/files/measurements.csv')
    assert.ok(manifest.schema.fields.find((field) => field.name === 'group').scope === 'column')
    const rows = await lake.tableRecords(manifest)
    assert.equal(rows[1].age, 20)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('DAG validation rejects illegal edges and cycles', () => {
  const valid = {
    experiment_summary: 'x',
    nodes: [
      { id: 'e1', type: 'entity', label: 'Sample' },
      { id: 's1', type: 'signal', label: 'Image' },
      { id: 'd1', type: 'derivative', label: 'Mask' },
    ],
    edges: [
      { from: 'e1', to: 's1', action: 'capture' },
      { from: 's1', to: 'd1', action: 'program' },
    ],
  }
  assert.equal(validateDag(valid).ok, true)
  const cycle = {
    ...valid,
    edges: [
      { from: 'e1', to: 's1', action: 'capture' },
      { from: 's1', to: 'd1', action: 'program' },
      { from: 'd1', to: 's1', action: 'program' },
    ],
  }
  assert.equal(validateDag(cycle).ok, false)
  assert.match(validateDag(cycle).errors.join(' '), /cycle/)
  const badEdge = {
    ...valid,
    edges: [{ from: 'e1', to: 'd1', action: 'capture' }],
  }
  assert.equal(validateDag(badEdge).ok, false)
})

test('DAG generation attaches node provenance to fields', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-dag-'))
  try {
    const lake = await makeLake(dir)
    const llm = new FakeLlm({
      'dag.plan': {
        experiment_summary: 'Fix sample, capture image, segment it.',
        nodes: [
          { id: 'e1', type: 'entity', label: 'Fixed sample', description: 'PFA-fixed cells' },
          { id: 's1', type: 'signal', label: 'Microscopy stack', description: 'Confocal z-stack' },
          { id: 'd1', type: 'derivative', label: 'Segmentation', description: 'Cell masks' },
        ],
        edges: [
          { from: 'e1', to: 's1', action: 'capture', description: 'Confocal acquisition' },
          { from: 's1', to: 'd1', action: 'program', description: 'Cellpose segmentation' },
        ],
      },
      'dag.node.e1': { fields: [{ name: 'fixation', type: 'category', description: 'Fixative' }] },
      'dag.node.s1': { fields: [{ name: 'objective', type: 'string', description: 'Objective lens' }] },
      'dag.node.d1': { fields: [{ name: 'segmentation_model', type: 'string', description: 'Model used' }] },
    })
    const result = await createDatasetWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      input: {
        name: 'DAG dataset',
        description: 'A fixed sample imaged and segmented.',
        layout: 'files',
      },
      rich: true,
      createDagSchema: (options) => generateDagSchema(options),
    })
    const fields = result.schema.fields
    assert.ok(fields.find((field) => field.name === 'fixation').node_id === 'e1')
    assert.ok(fields.find((field) => field.name === 'objective').node_id === 's1')
    assert.ok(fields.find((field) => field.name === 'segmentation_model').node_id === 'd1')
    assert.equal(result.generated.nodes, 3)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('debate validation finds useful fields and clarifications', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-debate-'))
  try {
    const lake = await makeLake(dir)
    const manifest = await lake.createDataset({
      name: 'Debate set',
      description: 'Confocal images of fixed cells.',
      purpose: 'Reuse for segmentation.',
      layout: 'files',
      schema: [
        { name: 'modality', type: 'category', description: 'Imaging modality' },
        { name: 'pixel_size_nm', type: 'number', description: 'Pixel size in nm' },
      ],
    })
    const llm = new FakeLlm({
      'debate.scenario': {
        scenario: 'A lab wants to reuse the images for segmentation.',
        roles: [
          { id: 'role_1', title: 'Imaging scientist', background: 'Microscopy', goal: 'Check acquisition' },
          { id: 'role_2', title: 'Data engineer', background: 'Pipelines', goal: 'Check formats' },
        ],
      },
      'debate.questions': () => ({ questions: ['What modality was used?', 'What was the pixel size?'] }),
      'debate.owner': ({ user }) => {
        const ids = [...user.matchAll(/^(r\d+_role\d+_q\d+):/gm)].map((match) => match[1])
        return {
          answers: ids.map((id, index) => (index === 0
            ? { question_id: id, answerable: true, fields: ['modality'], answer: 'confocal' }
            : { question_id: id, answerable: false, fields: [], answer: '', missing: 'pixel size' })),
        }
      },
      'debate.synthesis': {
        clarifications: [{
          question: 'What is the pixel size in nm?',
          why: 'Reviewers need it for segmentation.',
          asked_in_runs: 2,
          suggested_field: { name: 'pixel_size_nm', type: 'number', description: 'Pixel size in nm' },
        }],
      },
    })
    const report = await validateSchemaWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      dataset: manifest,
      runs: 2,
    })
    assert.equal(report.runs, 2)
    assert.ok(report.coverage > 0)
    assert.ok(report.useful_fields.some((field) => field.name === 'modality'))
    assert.ok(report.unanswered_questions.length > 0)
    assert.equal(report.clarifications[0].suggested_field.name, 'pixel_size_nm')
    const stored = await lake.getDataset(manifest.id)
    assert.equal(stored.validated_schema_version, stored.schema_version)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('add stages, commits, copies files and activates; query retrieves them', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-add-'))
  try {
    const lake = await makeLake(dir)
    const manifest = await lake.createDataset({
      name: 'Add set',
      description: 'Images',
      layout: 'files',
      schema: [
        { name: 'modality', type: 'category', description: 'Modality', required: true },
        { name: 'width_px', type: 'integer', description: 'Width' },
      ],
    })
    const first = join(dir, 'a.txt')
    const second = join(dir, 'b.txt')
    await writeFile(first, 'alpha')
    await writeFile(second, 'beta')
    const llm = new FakeLlm({
      'add.fill': {
        records: [
          { file: 'a.txt', values: { modality: 'microscopy', width_px: 512 }, evidence: 'name' },
          { file: 'b.txt', values: { modality: 'microscopy', width_px: 256 }, evidence: 'name' },
        ],
      },
      'query.plan': {
        dataset_id: manifest.id,
        reasoning: 'filter by modality',
        filter: { field: 'modality', op: 'eq', value: 'microscopy' },
        fields: ['id', 'modality', 'width_px', 'file_path'],
        limit: 10,
      },
    })
    const added = await addDataWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      dataset: manifest,
      input: { paths: [first, second], notes: 'Two images', commit: true },
    })
    assert.equal(added.committed, true)
    assert.equal(added.committed, true)
    const updated = await lake.getDataset(manifest.id)
    assert.equal(updated.status, 'active')
    assert.equal(updated.counts.records, 2)
    assert.equal(updated.counts.files, 2)
    assert.equal((await readFile(join(dir, 'datasets', manifest.id, 'files', 'a.txt'), 'utf8')), 'alpha')
    const retrieved = await getDataWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      input: { query: 'microscopy images', dataset_id: manifest.id, limit: 10 },
    })
    assert.equal(retrieved.matched, 2)
    assert.equal(retrieved.returned, 2)
    assert.equal(retrieved.rows[0].modality, 'microscopy')
    assert.ok(retrieved.files.length >= 1)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('add with missing fields stages without copying and commits after overrides', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'scidatamas-addmissing-'))
  try {
    const lake = await makeLake(dir)
    const manifest = await lake.createDataset({
      name: 'Needs clarification',
      description: 'Images',
      layout: 'files',
      schema: [{ name: 'modality', type: 'category', description: 'Modality', required: true }],
    })
    const source = join(dir, 'c.bin')
    await writeFile(source, 'data')
    const llm = new FakeLlm({ 'add.fill': { records: [] } })
    const result = await addDataWorkflow({
      lake,
      llm,
      config: config(dir),
      exec: {},
      dataset: manifest,
      input: { paths: [source], commit: true },
    })
    assert.equal(result.committed, false)
    assert.equal(result.stage.ready, false)
    assert.equal((await lake.getDataset(manifest.id)).counts.files, 0)
    const committed = await commitStageWorkflow({
      lake,
      config: config(dir),
      dataset: await lake.getDataset(manifest.id),
      stage: result.stage,
      overrides: { modality: 'microscopy' },
      notes: 'Clarified by the researcher',
    })
    assert.equal(committed.committed, 1)
    const rows = await lake.readMetadata(await lake.getDataset(manifest.id))
    assert.equal(rows[0].modality, 'microscopy')
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})
