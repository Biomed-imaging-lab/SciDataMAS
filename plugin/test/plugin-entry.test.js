import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('plugin entry declares the llm service it calls', async () => {
  const source = await readFile(new URL('../src/index.js', import.meta.url), 'utf8')
  const match = /export const inject = \[([^\]]*)\]/.exec(source)
  assert.ok(match, 'plugin entry has no inject declaration')
  const services = [...match[1].matchAll(/'([^']+)'/g)].map((item) => item[1])
  assert.ok(services.includes('llm'), 'scidatamas calls ctx.llm and must inject llm')
  assert.ok(services.includes('tools'))
  assert.ok(services.includes('systemPrompt'))
})
