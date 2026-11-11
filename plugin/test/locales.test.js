import test from 'node:test'
import assert from 'node:assert/strict'

test('Web panel dictionaries cover en, ru and zh with identical keys', async () => {
  const previousWindow = globalThis.window
  let entry
  globalThis.window = { __ModuleLoader__: { load: (value) => { entry = value } } }
  try {
    await import(`../src/client.js?locale-test=${Date.now()}`)
    assert.ok(entry, 'client bundle did not register itself')
    const module = entry.factory((name) => {
      if (name === 'react') return {}
      throw new Error(`unexpected client module request: ${name}`)
    })
    const messages = module.messages
    assert.ok(messages, 'client bundle does not expose dictionaries')
    const locales = Object.keys(messages).sort()
    assert.deepEqual(locales, ['en', 'ru', 'zh'])
    const englishKeys = Object.keys(messages.en).sort()
    for (const locale of locales) {
      assert.deepEqual(Object.keys(messages[locale]).sort(), englishKeys, `${locale} keys differ`)
      for (const key of englishKeys) {
        assert.equal(typeof messages[locale][key], 'string', `${locale}.${key} is not a string`)
        assert.ok(messages[locale][key].trim().length > 0, `${locale}.${key} is empty`)
      }
    }
    assert.match(messages.zh.panel, /[\u4e00-\u9fff]/)
    assert.match(messages.ru.panel, /[А-Яа-я]/)
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})
