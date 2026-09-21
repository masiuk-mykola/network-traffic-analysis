// Refreshes the generated API types and zod schemas before the dev server starts.
// Prefers the running API (its document is the truth), falls back to the copy in the repo.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const bin = (name) => join(ROOT, 'node_modules', '.bin', name)

const FALLBACK = '../backend/openapi.json'
const PROBE_TIMEOUT_MS = 2_000

async function liveDocument() {
  const base = (process.env.CAPTURE_API_URL ?? 'http://localhost:8700').replace(/\/+$/, '')
  const url = `${base}/openapi.json`
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) })
    return res.ok ? url : null
  } catch {
    return null
  }
}

function generate(input) {
  const steps = [
    ['openapi-typescript', [input, '-o', 'src/lib/api/schema.d.ts']],
    ['openapi-ts', ['-i', input]],
  ]
  for (const [name, args] of steps) {
    const run = spawnSync(bin(name), args, { stdio: 'inherit', cwd: ROOT })
    if (run.error) console.error(`api-schema: ${name} failed to start — ${run.error.message}`)
    if (run.status !== 0) return false
  }
  return true
}

const input = (await liveDocument()) ?? FALLBACK

if (input === FALLBACK && !existsSync(FALLBACK)) {
  console.error(`api-schema: the API is not running and ${FALLBACK} is missing — skipping.`)
  process.exit(0)
}

console.log(`api-schema: generating from ${input}`)
if (!generate(input)) {
  // A stale schema must not block the dev server; the committed files still work.
  console.error('api-schema: generation failed, keeping the committed files.')
}
