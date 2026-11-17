/**
 * Read-only HTTP API for the SciDataMAS Web panel.
 *
 * The browser plugin fetches the lake catalog, dataset details, validation
 * reports and artifact bytes through this route. Admission uses the existing
 * DSH connection service, so the panel is available only to the same owner
 * peer as the rest of the Web GUI.
 *
 * @module scidatamas/web-api
 */
import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import { mediaType } from './inspect.js'
import { toCsv } from './metadata.js'

export const API_PREFIX = '/scidatamas/api'

function sendJson(res, status, value) {
  const body = JSON.stringify(value)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  })
  res.end(body)
}

function notFound(res) {
  sendJson(res, 404, { error: 'not found' })
}

function sendCsv(res, filename, body) {
  res.writeHead(200, {
    'content-type': 'text/csv; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
    'content-disposition': `attachment; filename="${filename}"`,
    'x-content-type-options': 'nosniff',
  })
  res.end(body)
}

/** Read the effective metadata rows and column order for the Content tab. */
async function loadContentRows({ service, dataset }) {
  const rows = dataset.layout === 'table'
    ? await service.lake.tableRecords(dataset)
    : await service.lake.readMetadata(dataset)
  const columns = []
  const seen = new Set()
  for (const field of dataset.schema?.fields ?? []) {
    if (!seen.has(field.name)) {
      seen.add(field.name)
      columns.push(field.name)
    }
  }
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key)
        columns.push(key)
      }
    }
  }
  return { rows, columns }
}

function admissionOf(connection, req) {
  if (!connection?.admit) return { ok: false, status: 503, message: 'connection service is unavailable' }
  const admission = connection.admit(req)
  if (admission.rejection) return { ok: false, status: admission.rejection, message: 'unauthorized' }
  if (admission.peer?.principal?.kind !== 'owner') return { ok: false, status: 403, message: 'forbidden' }
  return { ok: true }
}

/** Stream one dataset artifact; the requested key must stay inside the dataset. */
async function serveArtifact({ service, datasetId, requestUrl, res }) {
  const dataset = await service.lake.getDataset(datasetId)
  const raw = requestUrl.searchParams.get('path') || ''
  if (!raw) return sendJson(res, 400, { error: 'path is required' })
  let key
  if (raw.startsWith('datasets/')) key = raw
  else key = service.lake.datasetKey(dataset.id, raw)
  if (!key.startsWith(`datasets/${dataset.id}/`)) return sendJson(res, 403, { error: 'path is outside the dataset' })
  if (!key.startsWith(service.lake.datasetKey(dataset.id, 'files'))) {
    return sendJson(res, 403, { error: 'only dataset artifacts can be served' })
  }
  const localPath = service.storage.localPath(key)
  if (!localPath) return sendJson(res, 501, { error: 'remote artifact materialization is not implemented yet' })
  let info
  try {
    info = await stat(localPath)
  } catch {
    return notFound(res)
  }
  if (!info.isFile()) return sendJson(res, 404, { error: 'not a file' })
  const type = mediaType(localPath)
  const inline = type.startsWith('image/') || type.startsWith('text/') || type === 'application/json' || type === 'application/pdf'
  res.writeHead(200, {
    'content-type': type,
    'content-length': info.size,
    'cache-control': 'private, max-age=60',
    'content-disposition': `${inline ? 'inline' : 'attachment'}; filename="${encodeURIComponent(localPath.split('/').pop())}"`,
    'x-content-type-options': 'nosniff',
  })
  createReadStream(localPath).pipe(res)
}

/**
 * Handle one API request. Exported for tests; the route registration passes
 * the live service and connection.
 */
export async function handleApiRequest({ req, res, service, connection }) {
  const admission = admissionOf(connection, req)
  if (!admission.ok) return sendJson(res, admission.status, { error: admission.message })
  if (!['GET', 'HEAD'].includes(req.method ?? 'GET')) {
    res.setHeader('allow', 'GET, HEAD')
    return sendJson(res, 405, { error: 'method not allowed' })
  }

  let requestUrl
  try {
    requestUrl = new URL(req.url ?? '/', 'http://localhost')
  } catch {
    return sendJson(res, 400, { error: 'invalid URL' })
  }
  const pathname = requestUrl.pathname

  try {
    if (pathname === `${API_PREFIX}/status`) {
      const status = await service.status({ exec: {} })
      return sendJson(res, 200, { status })
    }
    if (pathname === `${API_PREFIX}/datasets`) {
      const query = requestUrl.searchParams.get('query') ?? ''
      const includeDrafts = requestUrl.searchParams.get('include_drafts') !== 'false'
      const datasets = await service.listDatasets({ query, includeDrafts })
      return sendJson(res, 200, { root: service.config.root, storage: service.storage.kind, datasets })
    }
    const datasetMatch = new RegExp(`^${API_PREFIX}/datasets/([^/]+)(?:/(validation|file|content))?$`).exec(pathname)
    if (!datasetMatch) return notFound(res)
    const datasetId = decodeURIComponent(datasetMatch[1])
    const action = datasetMatch[2]
    if (action === 'file') {
      return await serveArtifact({ service, datasetId, requestUrl, res })
    }
    if (action === 'content') {
      const dataset = await service.lake.getDataset(datasetId)
      const { rows, columns } = await loadContentRows({ service, dataset })
      if (requestUrl.searchParams.get('format') === 'csv') {
        return sendCsv(res, `${dataset.id}-metadata.csv`, toCsv(rows, columns))
      }
      const requested = Number(requestUrl.searchParams.get('limit') ?? 200)
      const limit = Number.isFinite(requested) && requested > 0 ? Math.min(Math.floor(requested), 1000) : 200
      const requestedOffset = Number(requestUrl.searchParams.get('offset') ?? 0)
      const offset = Number.isFinite(requestedOffset) && requestedOffset > 0 ? Math.floor(requestedOffset) : 0
      const page = rows.slice(offset, offset + limit)
      return sendJson(res, 200, {
        dataset: service.lake.summaryOf(dataset),
        layout: dataset.layout,
        columns,
        rows: page,
        total: rows.length,
        offset,
        limit,
        has_more: offset + page.length < rows.length,
      })
    }
    if (action === 'validation') {
      const dataset = await service.lake.getDataset(datasetId)
      const report = await service.storage.readJson(
        service.lake.datasetKey(dataset.id, 'validation', 'latest.json'),
        null,
      )
      if (!report) return notFound(res)
      return sendJson(res, 200, { validation: report })
    }
    const detail = await service.inspectDataset(datasetId, { sampleRows: 8 })
    return sendJson(res, 200, detail)
  } catch (error) {
    if (error?.code === 'SCIDATAMAS_NOT_FOUND') return sendJson(res, 404, { error: error.message })
    return sendJson(res, 400, { error: error?.message ?? String(error) })
  }
}

/** Register the API route on a Web-enabled context. */
export function registerWebApi(webCtx, service) {
  const route = {
    kind: 'prefix',
    path: API_PREFIX,
    handler: (req, res) => handleApiRequest({
      req,
      res,
      service,
      connection: webCtx.connection,
    }),
  }
  webCtx.effect(() => webCtx.webServer.register(route), 'scidatamas: web api')
}
