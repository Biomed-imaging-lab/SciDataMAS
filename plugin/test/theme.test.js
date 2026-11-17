import test from 'node:test'
import assert from 'node:assert/strict'

test('Web panel uses DSH theme tokens and a system-color fallback', async () => {
  let entry
  const previousWindow = globalThis.window
  globalThis.window = { __ModuleLoader__: { load: (value) => { entry = value } } }
  try {
    await import(`../src/client.js?theme-test=${Date.now()}`)
    const module = entry.factory((name) => {
      if (name === 'react') return {}
      throw new Error(`unexpected client module request: ${name}`)
    })
    const css = module.CSS
    assert.ok(css, 'client bundle does not expose its stylesheet')
    // DSH theme variables that are actually defined by @deepseek-ai/dsh-client-ui-theme.
    for (const token of ['--dsw-alias-bg-base', '--dsw-alias-bg-layer-2', '--dsw-alias-bg-layer-3', '--dsw-alias-label-primary', '--dsw-alias-border-l1']) {
      assert.ok(css.includes(token), `missing theme token ${token}`)
    }
    // The old misspelled aliases silently fell back to white.
    assert.equal(css.includes('--dsw-alias-bg-l1'), false)
    assert.equal(css.includes('--dsw-alias-fill-l1'), false)
    assert.match(css, /color-scheme:light dark/)
    assert.match(css, /var\(--dsw-alias-bg-base,Canvas\)/)
    assert.match(css, /var\(--dsw-alias-label-primary,CanvasText\)/)
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})
