/**
 * Safe JSON filter DSL used for retrieval. No SQL is generated or executed;
 * the planner chooses fields/operators and this module evaluates them against
 * already-loaded records.
 * @module scidatamas/filter
 */
import { fold } from './util.js'

const OPS = new Set([
  'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'contains',
  'starts_with', 'ends_with', 'exists', 'between',
])

/** Throw when a filter references an unknown field or operator. */
export function validateFilter(filter, allowedFields) {
  if (filter === null || filter === undefined) return
  if (typeof filter !== 'object') throw new Error('filter must be an object or null')
  if (Array.isArray(filter)) throw new Error('filter must be a single object, not an array')
  if (filter.and !== undefined || filter.or !== undefined) {
    const key = filter.and !== undefined ? 'and' : 'or'
    const list = filter[key]
    if (!Array.isArray(list) || list.length === 0) throw new Error(`"${key}" must be a non-empty array`)
    for (const item of list) validateFilter(item, allowedFields)
    return
  }
  if (filter.not !== undefined) {
    validateFilter(filter.not, allowedFields)
    return
  }
  if (!filter.field) throw new Error('filter leaf must have a "field"')
  if (!OPS.has(filter.op)) throw new Error(`unknown filter operator "${filter.op}"`)
  if (allowedFields && !allowedFields.includes(filter.field)) {
    throw new Error(`filter uses unknown field "${filter.field}"; available: ${allowedFields.join(', ')}`)
  }
  if (['gt', 'gte', 'lt', 'lte', 'contains', 'starts_with', 'ends_with', 'eq', 'ne', 'between'].includes(filter.op) && filter.value === undefined) {
    throw new Error(`filter operator "${filter.op}" needs a value`)
  }
  if (filter.op === 'between') {
    if (!Array.isArray(filter.value) || filter.value.length !== 2) {
      throw new Error('"between" expects a two-element value array')
    }
  }
  if (filter.op === 'in' && !Array.isArray(filter.value)) {
    throw new Error('"in" expects an array value')
  }
}

/** Evaluate a validated filter against one record. */
export function matches(record, filter) {
  if (!filter) return true
  if (filter.and) return filter.and.every((item) => matches(record, item))
  if (filter.or) return filter.or.some((item) => matches(record, item))
  if (filter.not) return !matches(record, filter.not)

  const value = record?.[filter.field]
  const target = filter.value
  switch (filter.op) {
    case 'exists':
      return target === false ? value === undefined || value === null : value !== undefined && value !== null && value !== ''
    case 'eq':
      return compareEqual(value, target)
    case 'ne':
      return !compareEqual(value, target)
    case 'gt':
      return compareOrder(value, target) > 0
    case 'gte':
      return compareOrder(value, target) >= 0
    case 'lt':
      return compareOrder(value, target) < 0
    case 'lte':
      return compareOrder(value, target) <= 0
    case 'in':
      return target.some((item) => compareEqual(value, item))
    case 'contains':
      if (Array.isArray(value)) return value.some((item) => fold(item).includes(fold(target)))
      return fold(value).includes(fold(target))
    case 'starts_with':
      return fold(value).startsWith(fold(target))
    case 'ends_with':
      return fold(value).endsWith(fold(target))
    case 'between':
      return compareOrder(value, target[0]) >= 0 && compareOrder(value, target[1]) <= 0
    default:
      return false
  }
}

function compareEqual(left, right) {
  if (left === right) return true
  if (left === undefined || left === null || right === undefined || right === null) return false
  const leftNumber = Number(left)
  const rightNumber = Number(right)
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && String(left).trim() !== '' && String(right).trim() !== '') {
    return leftNumber === rightNumber
  }
  return fold(left) === fold(right)
}

function compareOrder(left, right) {
  if (left === undefined || left === null) return Number.NaN
  const leftNumber = Number(left)
  const rightNumber = Number(right)
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && String(left).trim() !== '' && String(right).trim() !== '') {
    return leftNumber - rightNumber
  }
  const leftDate = new Date(left).getTime()
  const rightDate = new Date(right).getTime()
  if (!Number.isNaN(leftDate) && !Number.isNaN(rightDate)) return leftDate - rightDate
  return fold(left).localeCompare(fold(right))
}

/** Filter, project, sort and limit rows. */
export function runQuery(records, { filter, fields, limit = 50, sort } = {}) {
  const matched = (records ?? []).filter((record) => matches(record, filter))
  let rows = matched
  if (sort?.field) {
    const direction = sort.order === 'desc' ? -1 : 1
    rows = [...rows].sort((a, b) => direction * compareOrder(a[sort.field], b[sort.field]))
  }
  const sliced = rows.slice(0, Math.max(0, Math.min(limit, 1000)))
  const projected = Array.isArray(fields) && fields.length > 0
    ? sliced.map((record) => Object.fromEntries(fields.filter((field) => field in record).map((field) => [field, record[field]])))
    : sliced
  return { rows: projected, matched: matched.length, returned: projected.length }
}

/** Rank datasets by simple lexical overlap when no model is available. */
export function rankDatasets(datasets, request) {
  const tokens = fold(request).split(/[^a-z0-9а-яё_]+/).filter((token) => token.length > 2)
  return datasets
    .map((dataset) => {
      const haystack = fold(`${dataset.id} ${dataset.name} ${dataset.description} ${dataset.purpose ?? ''} ${dataset.modality ?? ''}`)
      let score = 0
      for (const token of tokens) if (haystack.includes(token)) score += 1
      return { dataset, score }
    })
    .sort((a, b) => b.score - a.score)
}

/** Rank rows by lexical overlap for a fallback search. */
export function rankRecords(records, request) {
  const tokens = fold(request).split(/[^a-z0-9а-яё_]+/).filter((token) => token.length > 2)
  return records
    .map((record) => {
      const haystack = fold(Object.values(record).map((value) => (typeof value === 'object' ? JSON.stringify(value) : value)).join(' '))
      let score = 0
      for (const token of tokens) if (haystack.includes(token)) score += 1
      return { record, score }
    })
    .sort((a, b) => b.score - a.score)
}
