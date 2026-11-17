#!/usr/bin/env node
/**
 * Check local Markdown links and image references. External URLs and pure
 * anchors are ignored; a link pointing at a missing local file fails.
 */
import { readFile, readdir, stat } from 'node:fs/promises'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const files = []

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '.git' || entry.name === 'node_modules' || entry.name === '.testweb' || entry.name === '.testdata') continue
    const full = join(directory, entry.name)
    if (entry.isDirectory()) await walk(full)
    else if (entry.isFile() && ['.md', '.cff'].includes(extname(entry.name))) files.push(full)
  }
}

await walk(root)
const failures = []
for (const file of files) {
  const text = await readFile(file, 'utf8')
  for (const match of text.matchAll(/!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const target = match[1]
    if (/^(https?:|mailto:|tel:|#)/i.test(target)) continue
    const clean = target.split('#')[0]
    if (!clean) continue
    const absolute = resolve(dirname(file), clean)
    try {
      await stat(absolute)
    } catch {
      failures.push(`${file.slice(root.length + 1)} -> ${target}`)
    }
  }
}

if (failures.length > 0) {
  console.error(`Broken local links (${failures.length}):`)
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}
console.log(`Checked ${files.length} Markdown/CFF files: no broken local links.`)
