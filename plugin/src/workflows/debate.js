/**
 * Debate-based schema validation.
 *
 * Each run invents a concrete experiment from the dataset description and
 * purpose, creates independent reviewer roles, lets them ask the owner
 * questions, and records which questions the exact schema can answer. Fields
 * that answer questions are useful; unanswered questions become clarification
 * requests for the researcher.
 * @module scidatamas/workflows/debate
 */
import {
  debateOwnerSystem,
  debateOwnerUser,
  debateQuestionsSystem,
  debateQuestionsUser,
  debateScenarioSystem,
  debateScenarioUser,
  debateSynthesisSystem,
  debateSynthesisUser,
} from '../prompts.js'
import { fold, mapLimit } from '../util.js'

/** Render the authoritative schema for the owner prompt. */
export function schemaText(schema) {
  return (schema?.fields ?? [])
    .map((field) => {
      const system = field.system ? ' [system]' : ''
      const unit = field.unit ? `, unit: ${field.unit}` : ''
      return `- ${field.name} (${field.type}${unit})${system}: ${field.description}`
    })
    .join('\n')
}

/** Deterministic clarifications when the synthesis call fails. */
export function fallbackClarifications(unanswered, limit = 12) {
  return unanswered.slice(0, limit).map((item) => ({
    question: item.text,
    why: `Unanswered in ${item.count} review run(s); reviewers need this to reuse the dataset.`,
    asked_in_runs: item.count,
    suggested_field: null,
  }))
}

/** Generate one scenario with reviewer roles. */
export async function generateScenario({ llm, config, exec, dataset }) {
  const answer = await llm.json({
    system: debateScenarioSystem(),
    user: debateScenarioUser({
      name: dataset.name,
      description: dataset.description,
      purpose: dataset.purpose,
      roleCount: config.debateRoles,
    }),
    exec,
    purpose: 'debate.scenario',
    maxTokens: 4096,
  })
  const roles = Array.isArray(answer.value?.roles) ? answer.value.roles : []
  if (roles.length === 0) throw new Error('debate scenario returned no roles')
  return {
    scenario: String(answer.value?.scenario ?? ''),
    roles: roles.slice(0, config.debateRoles).map((role, index) => ({
      id: String(role.id ?? `role_${index + 1}`),
      title: String(role.title ?? `Reviewer ${index + 1}`),
      background: String(role.background ?? ''),
      goal: String(role.goal ?? ''),
    })),
  }
}

/** Generate questions for one role. */
export async function generateRoleQuestions({ llm, config, exec, scenario, role }) {
  const answer = await llm.json({
    system: debateQuestionsSystem(),
    user: debateQuestionsUser({
      scenario,
      role,
      count: config.debateQuestionsPerRole,
    }),
    exec,
    purpose: `debate.questions.${role.id}`,
    maxTokens: 3072,
  })
  const questions = Array.isArray(answer.value?.questions)
    ? answer.value.questions
    : Array.isArray(answer.value)
      ? answer.value
      : []
  return questions
    .map((question) => String(question ?? '').trim())
    .filter((question) => question.length > 0)
    .slice(0, config.debateQuestionsPerRole)
}

/** Ask the owner to answer all questions from one run. */
export async function answerQuestions({ llm, exec, dataset, scenario, questions }) {
  if (questions.length === 0) return []
  const answer = await llm.json({
    system: debateOwnerSystem(),
    user: debateOwnerUser({
      scenario,
      schemaText: schemaText(dataset.schema),
      questions,
    }),
    exec,
    purpose: 'debate.owner',
    maxTokens: 8192,
  })
  const source = Array.isArray(answer.value?.answers)
    ? answer.value.answers
    : Array.isArray(answer.value)
      ? answer.value
      : []
  const byId = new Map()
  for (const item of source) {
    const id = item?.question_id ?? item?.id
    if (id) byId.set(String(id), item)
  }
  return questions.map((question) => {
    const item = byId.get(question.id) ?? {}
    const fields = Array.isArray(item.fields) ? item.fields.map(String) : []
    return {
      question_id: question.id,
      text: question.text,
      role: question.role,
      answerable: item.answerable === true,
      fields,
      answer: String(item.answer ?? ''),
      missing: String(item.missing ?? ''),
    }
  })
}

/**
 * Run the complete debate validation and persist its report.
 * @param {object} options
 */
export async function validateSchemaWorkflow({ lake, llm, config, exec, dataset, runs }) {
  const requested = Number.isFinite(runs) ? Math.round(runs) : config.debateRuns
  const totalRuns = Math.max(1, Math.min(requested, config.maxDebateRuns))
  const warnings = []
  const runReports = []
  const fieldUses = new Map()
  const fieldRuns = new Map()
  const unansweredMap = new Map()
  const schemaNames = new Set((dataset.schema?.fields ?? []).filter((field) => !field.system).map((field) => field.name))

  for (let runIndex = 0; runIndex < totalRuns; runIndex += 1) {
    const { scenario, roles } = await generateScenario({ llm, config, exec, dataset })
    const questions = []
    const roleQuestions = await mapLimit(roles, 2, async (role, roleIndex) => {
      try {
        const asked = await generateRoleQuestions({ llm, config, exec, scenario, role })
        return asked.map((text, questionIndex) => ({
          id: `r${runIndex + 1}_role${roleIndex + 1}_q${questionIndex + 1}`,
          text,
          role: role.title,
        }))
      } catch (error) {
        warnings.push(`run ${runIndex + 1}, role ${role.title}: ${error.message}`)
        return []
      }
    })
    for (const list of roleQuestions) questions.push(...list)
    if (questions.length === 0) {
      warnings.push(`run ${runIndex + 1} produced no questions`)
      continue
    }
    const answers = await answerQuestions({ llm, exec, dataset, scenario, questions })
    const usedInRun = new Set()
    const unansweredInRun = []
    for (const answer of answers) {
      const validFields = answer.answerable ? answer.fields.filter((name) => schemaNames.has(name)) : []
      if (answer.answerable && validFields.length === 0) {
        warnings.push(`run ${runIndex + 1}: owner claimed an answer without a valid schema field for "${answer.text}"`)
      }
      if (validFields.length > 0) {
        for (const name of validFields) {
          fieldUses.set(name, (fieldUses.get(name) ?? 0) + 1)
          usedInRun.add(name)
        }
      } else {
        unansweredInRun.push(answer)
      }
      answer.fields = validFields
      answer.answerable = validFields.length > 0
    }
    for (const name of usedInRun) {
      if (!fieldRuns.has(name)) fieldRuns.set(name, new Set())
      fieldRuns.get(name).add(runIndex + 1)
    }
    for (const answer of unansweredInRun) {
      const key = fold(answer.text)
      const previous = unansweredMap.get(key) ?? {
        text: answer.text,
        count: 0,
        roles: new Set(),
        runs: new Set(),
      }
      previous.count += 1
      previous.roles.add(answer.role)
      previous.runs.add(runIndex + 1)
      unansweredMap.set(key, previous)
    }
    runReports.push({
      run: runIndex + 1,
      scenario,
      roles: roles.map((role) => role.title),
      question_count: questions.length,
      answered: answers.length - unansweredInRun.length,
      unanswered: unansweredInRun.length,
      used_fields: [...usedInRun],
    })
  }

  const unanswered = [...unansweredMap.values()]
    .map((item) => ({
      text: item.text,
      count: item.count,
      roles: [...item.roles],
      runs: [...item.runs],
    }))
    .sort((a, b) => b.count - a.count || a.text.localeCompare(b.text))

  let clarifications
  if (unanswered.length > 0) {
    try {
      const synthesis = await llm.json({
        system: debateSynthesisSystem(),
        user: debateSynthesisUser({
          schemaNames: [...schemaNames],
          unanswered: unanswered.slice(0, 40),
          runs: runReports.length,
        }),
        exec,
        purpose: 'debate.synthesis',
        maxTokens: 6144,
      })
      clarifications = Array.isArray(synthesis.value?.clarifications)
        ? synthesis.value.clarifications
        : []
    } catch (error) {
      warnings.push(`clarification synthesis failed: ${error.message}`)
    }
  }
  if (!clarifications || clarifications.length === 0) {
    clarifications = fallbackClarifications(unanswered)
  }

  const useful = [...fieldUses.entries()]
    .map(([name, uses]) => {
      const field = dataset.schema.fields.find((item) => item.name === name)
      return {
        name,
        uses,
        runs_used: fieldRuns.get(name)?.size ?? 0,
        description: field?.description ?? '',
        type: field?.type,
      }
    })
    .sort((a, b) => b.uses - a.uses || a.name.localeCompare(b.name))

  const coverage = schemaNames.size > 0
    ? Math.round((useful.length / schemaNames.size) * 1000) / 1000
    : 0
  const report = {
    dataset_id: dataset.id,
    dataset_name: dataset.name,
    schema_version: dataset.schema_version,
    runs: runReports.length,
    requested_runs: requested,
    coverage,
    useful_fields: useful,
    unused_fields: [...schemaNames].filter((name) => !fieldUses.has(name)),
    unanswered_questions: unanswered,
    clarifications,
    suggested_fields: clarifications
      .map((item) => item.suggested_field)
      .filter(Boolean)
      .map((field) => ({ ...field, scope: 'row' })),
    run_details: runReports,
    warnings,
  }
  const stored = await lake.saveValidation(dataset, report)
  return {
    ...stored,
    report_path: `datasets/${dataset.id}/validation/latest.json`,
  }
}
