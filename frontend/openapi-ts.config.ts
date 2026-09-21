import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: '../backend/openapi.json',
  output: { path: 'src/lib/api/generated', postProcess: [] },
  plugins: [{ name: 'zod', definitions: true, responses: true, requests: true }],
})
