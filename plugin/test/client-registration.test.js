import test from 'node:test'
import assert from 'node:assert/strict'

test('client plugin registers the main panel and the right-sidebar page', async () => {
  let entry
  const previousWindow = globalThis.window
  globalThis.window = { __ModuleLoader__: { load: (value) => { entry = value } } }
  try {
    await import(`../src/client.js?registration-test=${Date.now()}`)
    const module = entry.factory((name) => {
      if (name === 'react') return {}
      throw new Error(`unexpected client module request: ${name}`)
    })
    const registrations = []
    const tabTypes = []
    const ctx = {
      effect: (fn) => fn(),
      locale: {
        register: () => () => {},
        bind: () => (key) => key,
      },
      slots: {
        inject: (_name, callback) => callback(),
        register: (options, component) => {
          registrations.push({ options, component })
          return () => {}
        },
      },
      layout: { selectPanel: () => {} },
      sidebarRight: { openTab: () => {} },
      sidebarRightTabs: {
        register: (definition) => {
          tabTypes.push(definition)
          return () => {}
        },
      },
    }
    module.apply(ctx)
    assert.equal(tabTypes.length, 1)
    assert.equal(tabTypes[0].kind, 'scidatamas-data')
    assert.equal(tabTypes[0].guide?.[0]?.id, 'data')
    const names = registrations.map(({ options }) => `${options.name}:${options.key ?? options.id ?? ''}`)
    assert.ok(names.includes('main:scidatamas'))
    assert.ok(names.includes('sidebar.panellist:scidatamas'))
    assert.ok(names.includes('sidebar.right.pane.tab:scidatamas-dsh-plugin/data'))
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})
