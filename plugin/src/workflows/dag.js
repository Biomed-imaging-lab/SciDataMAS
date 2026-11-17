/**
 * DAG-augmented metadata generation.
 *
 * A first call designs an experimental provenance DAG (physical entities,
 * captured signals, derived artifacts). Per-node calls then generate fields
 * for that node, and the results are merged into one flat schema with node
 * provenance attached. This is the "rich" mode from the paper: field count
 * scales with the pipeline instead of staying fixed by one prompt.
 * @module scidatamas/workflows/dag
 */
import { normalizeField, normalizeSchema, SYSTEM_FIELD_NAMES } from '../metadata.js'
import {
  dagNodeSystem,
  dagNodeUser,
  dagPlanUser,
  dagSystem,
} from '../prompts.js'
import { LakeError } from '../lake.js'
import { clip, mapLimit } from '../util.js'

const NODE_TYPES = new Set(['entity', 'signal', 'derivative'])
const ACTION_TYPES = new Set(['preparation', 'capture', 'program'])

/** Validate the DAG structure and return normalized errors. */
export function validateDag(dag, { maxNodes = 24 } = {}) {
  const errors = []
  if (!dag || typeof dag !== 'object') return { ok: false, errors: ['DAG is not an object'] }
  const nodes = Array.isArray(dag.nodes) ? dag.nodes : []
  const edges = Array.isArray(dag.edges) ? dag.edges : []
  if (nodes.length === 0) errors.push('DAG has no nodes')
  if (nodes.length > maxNodes) errors.push(`DAG has ${nodes.length} nodes, more than the limit of ${maxNodes}`)
  const ids = new Set()
  for (const node of nodes) {
    if (!node?.id) errors.push('a node has no id')
    else if (ids.has(node.id)) errors.push(`duplicate node id "${node.id}"`)
    else ids.add(node.id)
    if (!NODE_TYPES.has(node?.type)) errors.push(`node "${node?.id}" has invalid type "${node?.type}"`)
    if (!node?.label) errors.push(`node "${node?.id}" has no label`)
  }
  const incoming = new Map([...ids].map((id) => [id, 0]))
  const outgoing = new Map([...ids].map((id) => [id, []]))
  for (const edge of edges) {
    if (!ids.has(edge?.from)) errors.push(`edge from unknown node "${edge?.from}"`)
    if (!ids.has(edge?.to)) errors.push(`edge to unknown node "${edge?.to}"`)
    if (!ACTION_TYPES.has(edge?.action)) errors.push(`edge ${edge?.from}->${edge?.to} has invalid action "${edge?.action}"`)
    if (ids.has(edge?.from) && ids.has(edge?.to)) {
      const from = nodes.find((node) => node.id === edge.from)
      const to = nodes.find((node) => node.id === edge.to)
      if (edge.action === 'preparation' && !(from?.type === 'entity' && to?.type === 'entity')) {
        errors.push(`preparation edge ${edge.from}->${edge.to} must connect entity to entity`)
      }
      if (edge.action === 'capture' && !(from?.type === 'entity' && to?.type === 'signal')) {
        errors.push(`capture edge ${edge.from}->${edge.to} must connect entity to signal`)
      }
      if (edge.action === 'program' && !(['signal', 'derivative'].includes(from?.type) && to?.type === 'derivative')) {
        errors.push(`program edge ${edge.from}->${edge.to} must connect signal/derivative to derivative`)
      }
      incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1)
      outgoing.get(edge.from)?.push(edge.to)
    }
  }
  for (const [id, count] of incoming) {
    if (count === 0 && nodes.length > 1) {
      // Multiple roots are legal (e.g. several samples), but every root must
      // eventually reach a signal or derivative.
    }
  }
  // Kahn's algorithm: detect cycles.
  const indegree = new Map(incoming)
  const queue = [...indegree.entries()].filter(([, count]) => count === 0).map(([id]) => id)
  let visited = 0
  while (queue.length > 0) {
    const id = queue.shift()
    visited += 1
    for (const next of outgoing.get(id) ?? []) {
      indegree.set(next, indegree.get(next) - 1)
      if (indegree.get(next) === 0) queue.push(next)
    }
  }
  if (visited !== ids.size) errors.push('DAG contains a cycle')
  if (nodes.length > 0 && !nodes.some((node) => ['signal', 'derivative'].includes(node.type))) {
    errors.push('DAG has no signal or derivative node; add the data-producing steps')
  }
  return { ok: errors.length === 0, errors }
}

/** Normalize a model-produced DAG into the shape used by prompts and output. */
export function normalizeDag(dag) {
  return {
    experiment_summary: String(dag?.experiment_summary ?? ''),
    nodes: (dag?.nodes ?? []).map((node) => ({
      id: String(node.id),
      type: node.type,
      label: String(node.label ?? node.id),
      description: String(node.description ?? ''),
    })),
    edges: (dag?.edges ?? []).map((edge) => ({
      from: String(edge.from),
      to: String(edge.to),
      action: edge.action,
      description: String(edge.description ?? ''),
      parameters: Array.isArray(edge.parameters) ? edge.parameters.map(String).slice(0, 20) : [],
    })),
  }
}

/** One-line-per-item DAG rendering for prompts and tool output. */
export function dagText(dag) {
  const nodes = (dag?.nodes ?? []).map((node) => `${node.id} [${node.type}] ${node.label}: ${clip(node.description, 240)}`)
  const edges = (dag?.edges ?? []).map((edge) => `${edge.from} -> ${edge.to} (${edge.action})${edge.parameters?.length ? ` [${edge.parameters.join(', ')}]` : ''}: ${clip(edge.description, 200)}`)
  return { nodes, edges }
}

/** Plan a DAG, repairing structural errors once with the validator's feedback. */
export async function planDag({ llm, config, exec, input, evidence }) {
  let correction = ''
  let last
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const user = `${dagPlanUser({
      name: input.name,
      description: input.description,
      purpose: input.purpose,
      evidence,
      maxNodes: config.maxDagNodes,
    })}${correction ? `\n\n${correction}` : ''}`
    const answer = await llm.json({
      system: dagSystem(),
      user,
      exec,
      purpose: 'dag.plan',
      maxTokens: 8192,
    })
    last = normalizeDag(answer.value)
    const validation = validateDag(last, { maxNodes: config.maxDagNodes })
    if (validation.ok) return last
    correction = `The previous DAG was rejected by the structural validator:\n- ${validation.errors.join('\n- ')}\nReturn a corrected DAG. Keep valid nodes and fix only the violations.`
  }
  throw new LakeError(
    `could not build a valid experiment DAG: ${validateDag(last, { maxNodes: config.maxDagNodes }).errors.join('; ')}`,
    'SCIDATAMAS_BAD_DAG',
  )
}

/** Generate fields for one DAG node. */
export async function generateNodeFields({ llm, config, exec, input, dag, node, existingNames }) {
  const answer = await llm.json({
    system: dagNodeSystem(),
    user: dagNodeUser({
      node,
      dag,
      description: input.description,
      existingNames,
    }),
    exec,
    purpose: `dag.node.${node.id}`,
    maxTokens: 6144,
  })
  const rawFields = Array.isArray(answer.value?.fields)
    ? answer.value.fields
    : Array.isArray(answer.value)
      ? answer.value
      : []
  const fields = []
  for (const raw of rawFields) {
    const field = normalizeField(raw, raw?.name)
    if (!field || SYSTEM_FIELD_NAMES.includes(field.name)) continue
    fields.push({
      ...field,
      source: 'dag',
      node_id: node.id,
      node_description: clip(`${node.label} (${node.type}): ${node.description}`, 500),
    })
  }
  return fields
}

/** Full rich-generation workflow. */
export async function generateDagSchema({ llm, config, exec, input, evidence }) {
  const dag = await planDag({ llm, config, exec, input, evidence })
  const existingNames = []
  const byName = new Map()
  const warnings = []
  const generated = await mapLimit(dag.nodes, config.dagConcurrency, async (node) => {
    try {
      return await generateNodeFields({
        llm,
        config,
        exec,
        input,
        dag,
        node,
        existingNames: [...existingNames],
      })
    } catch (error) {
      warnings.push(`node ${node.id} failed: ${error.message}`)
      return []
    }
  })
  for (const fields of generated) {
    for (const field of fields) {
      if (byName.has(field.name)) {
        const previous = byName.get(field.name)
        if (previous.node_id !== field.node_id) {
          warnings.push(`field "${field.name}" appeared in ${previous.node_id} and ${field.node_id}; kept the first`)
        }
        continue
      }
      byName.set(field.name, field)
      existingNames.push(field.name)
    }
  }
  const fields = [...byName.values()]
  if (fields.length === 0) {
    throw new LakeError('the DAG workflow produced no metadata fields', 'SCIDATAMAS_EMPTY_SCHEMA')
  }
  const schema = normalizeSchema(fields, { layout: input.layout, maxFields: config.maxSchemaFields })
  return {
    schema,
    generated: {
      mode: 'dag',
      dag,
      dag_text: dagText(dag),
      warnings,
      nodes: dag.nodes.length,
      fields: fields.length,
    },
  }
}
