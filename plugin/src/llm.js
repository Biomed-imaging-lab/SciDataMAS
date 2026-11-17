/**
 * Internal model calls for the SciDataMAS workflows.
 *
 * The plugin uses the profile's provider-neutral `ctx.llm` service. The route
 * defaults to the calling session's selected model, so an internal workflow
 * runs on the same model the researcher is talking to. Every call is written
 * to a durable audit log under the data-lake root (when enabled), which keeps
 * generated schemas reproducible even though these are auxiliary calls.
 *
 * @module scidatamas/llm
 */
import { BlockAssembler } from '@deepseek-ai/dsh-llm'
import { clip, extractJson, nowIso, oneLine } from './util.js'

const AUDIT_KEY = 'logs/llm-calls.jsonl'

/** Error with a stable code for callers that want to react to route problems. */
export class ModelError extends Error {
  constructor(message, code = 'SCIDATAMAS_MODEL_ERROR', cause) {
    super(message, cause ? { cause } : undefined)
    this.name = 'ModelError'
    this.code = code
  }
}

/** Resolve the model route for one tool call. */
export function resolveModelRoute(ctx, config, exec) {
  const selected = exec?.agent?.model?.current?.()
  if (selected?.provider && selected?.model) {
    return { provider: selected.provider, model: selected.model, reasoningEffort: selected.reasoningEffort }
  }
  if (config.provider && config.model) {
    return { provider: config.provider, model: config.model }
  }
  const fallback = typeof ctx?.get === 'function' ? ctx.get('agentDefaultModel')?.currentSelection?.() : undefined
  if (fallback?.provider && fallback?.model) return fallback
  throw new ModelError(
    'No model route is available. Select a session model or set provider/model in the scidatamas config.',
    'SCIDATAMAS_NO_MODEL',
  )
}

/** Combine caller cancellation with an internal timeout. */
function withTimeout(signal, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error(`model call timed out after ${timeoutMs} ms`)), timeoutMs)
  const onAbort = () => controller.abort(signal.reason)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  return {
    signal: controller.signal,
    dispose() {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
    },
  }
}

/** Extract visible text from assembled blocks. */
function blocksText(blocks) {
  return (blocks ?? [])
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('')
}

/** Provider-neutral model client bound to one plugin instance. */
export class LlmClient {
  /**
   * @param {object} deps
   * @param {object} deps.ctx - Cordis context with the llm service.
   * @param {object} deps.config - resolved plugin config.
   * @param {object} deps.storage - StorageBackend for the audit log.
   * @param {(key: string) => Promise<void>} [deps.lock] - optional audit lock.
   */
  constructor({ ctx, config, storage }) {
    this.ctx = ctx
    this.config = config
    this.storage = storage
    this.auditQueue = Promise.resolve()
  }

  /** Resolve and validate the route. */
  route(exec) {
    return resolveModelRoute(this.ctx, this.config, exec)
  }

  /**
   * Stream one model call and return assembled text/usage.
   * @param {object} request
   * @param {string} request.system
   * @param {Array<{role: string, content: Array<object>}>} request.messages
   * @param {object} [request.exec]
   * @param {number} [request.temperature]
   * @param {number} [request.maxTokens]
   * @param {string} [request.purpose]
   */
  async complete({ system, messages, exec, temperature = 0.25, maxTokens, purpose = 'workflow' }) {
    if (!this.ctx?.llm?.stream) {
      throw new ModelError(
        'The llm service is not mounted in this profile, so metadata generation and debate are unavailable. Storage-only tools still work.',
        'SCIDATAMAS_NO_LLM',
      )
    }
    const route = this.route(exec)
    const started = Date.now()
    const timeout = withTimeout(exec?.signal, this.config.requestTimeoutMs)
    const assembler = new BlockAssembler()
    let streamError
    try {
      for await (const chunk of this.ctx.llm.stream({
        provider: route.provider,
        model: route.model,
        ...(route.reasoningEffort ? { reasoningEffort: route.reasoningEffort } : {}),
        system,
        messages,
        temperature,
        ...(maxTokens ? { maxTokens } : {}),
        signal: timeout.signal,
      })) {
        assembler.push(chunk)
      }
    } catch (error) {
      streamError = error
    } finally {
      timeout.dispose()
    }

    const finish = assembler.finish
    const text = blocksText(assembler.blocks())
    const usage = assembler.usage
    const durationMs = Date.now() - started
    const failure = streamError
      ?? (finish.kind === 'error' || finish.kind === 'aborted'
        ? new ModelError(
          `Model request failed (${finish.failure?.code ?? finish.kind}): ${finish.failure?.message ?? 'unknown failure'}`,
          finish.failure?.code ?? 'SCIDATAMAS_MODEL_FAILED',
        )
        : undefined)

    await this.audit({
      purpose,
      route,
      system,
      messages,
      response: text,
      finish: finish.kind,
      usage,
      duration_ms: durationMs,
      error: failure?.message,
      error_code: failure?.code,
    })

    if (failure) throw failure
    return { text, finish, usage, route, durationMs }
  }

  /**
   * Call the model and parse one JSON value. Malformed answers are retried
   * with the parser error appended; provider failures are not retried here.
   */
  async json({ system, user, exec, temperature = 0.25, maxTokens, purpose = 'json', retries }) {
    const attempts = 1 + (retries ?? this.config.llmRetries)
    let correction = ''
    let lastError
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const messages = [{
        role: 'user',
        content: [{ type: 'text', text: correction ? `${user}\n\n${correction}` : user }],
      }]
      const answer = await this.complete({ system, messages, exec, temperature, maxTokens, purpose })
      try {
        return { value: extractJson(answer.text), raw: answer.text, usage: answer.usage, route: answer.route }
      } catch (error) {
        lastError = error
        correction = `Your previous answer could not be parsed as JSON: ${error.message}\nReturn ONLY the requested JSON object, with no markdown fence or prose.`
      }
    }
    throw new ModelError(`The model did not return valid JSON after ${attempts} attempt(s): ${lastError?.message}`, 'SCIDATAMAS_BAD_JSON')
  }

  /** Append one audit record, serialized to keep the JSONL valid. */
  async audit(record) {
    if (!this.config.logLlmCalls || !this.storage) return
    const max = this.config.logMaxChars
    const entry = {
      ts: nowIso(),
      purpose: record.purpose,
      provider: record.route?.provider,
      model: record.route?.model,
      duration_ms: record.duration_ms,
      finish: record.finish,
      usage: record.usage,
      error: record.error,
      error_code: record.error_code,
      system: clip(record.system, max),
      messages: (record.messages ?? []).map((message) => ({
        role: message.role,
        content: (message.content ?? []).map((block) => (block.type === 'text'
          ? { type: 'text', text: clip(block.text, max) }
          : block)),
      })),
      response: clip(record.response, max),
    }
    this.auditQueue = this.auditQueue
      .then(() => this.storage.appendJsonLine(AUDIT_KEY, entry))
      .catch(() => { /* an audit failure must not break the scientific workflow */ })
    await this.auditQueue
  }

  /** Short status used by tools that report model availability. */
  async status(exec) {
    try {
      const route = this.route(exec)
      return { available: true, provider: route.provider, model: route.model }
    } catch (error) {
      return { available: false, error: oneLine(error.message) }
    }
  }
}
