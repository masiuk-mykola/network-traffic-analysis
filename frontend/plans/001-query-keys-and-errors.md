# Plan 001 — Cache identity and a structured client error

Spec: `specs/001-query-keys-and-errors.md`. Resolutions for its open questions: the error body is
passed through whole (already true of `toErrorPayload`), the revoked session is only made
distinguishable here and acted on in 1.3, and the retry limit stays a single shared three.

## Files to touch

| Path                                         | Change                                                                                                                                |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/api/keys.ts` (new)                  | The key factory: one exported function per resource, each returning a readonly tuple. The only place a cache identity is spelled out. |
| `src/lib/api/keys.test.ts` (new)             | Stability, distinctness and prefix-invalidation tests.                                                                                |
| `src/lib/api/http-error.ts` (new)            | `HttpError` (status, code, detail, retryAfterMs, body) and `isHttpError`; the browser-side counterpart of `toErrorPayload`.           |
| `src/lib/api/http-error.test.ts` (new)       | Building an `HttpError` from a proxy response, including the header and the revoked-session code.                                     |
| `src/lib/api/fetch-json.ts` (new)            | The single browser-side fetch used by every query function: calls our proxy, throws `HttpError`, forwards `AbortSignal`.              |
| `src/lib/api/fetch-json.test.ts` (new)       | Error mapping, abort propagation, and that it never sends credentials-bearing headers of its own.                                     |
| `src/lib/query-retry.ts`                     | Replace the local `HttpError` shape with the shared one; keep `MAX_ATTEMPTS = 3`; treat a revoked session as non-retryable.           |
| `src/lib/query-retry.test.ts`                | Add the revoked-session case; keep the existing ones.                                                                                 |
| `src/app/api/capture/[...path]/route.ts`     | Validate the proxied body against a schema resolved from the path, so the generated schemas cover proxied reads too.                  |
| `src/lib/api/response-schemas.ts` (new)      | Path pattern → generated zod schema map used by the proxy.                                                                            |
| `src/lib/api/response-schemas.test.ts` (new) | Pattern matching for concrete and parameterized paths, and the fallthrough for unmapped ones.                                         |
| `CLAUDE.md`                                  | One line in Architecture pointing at the key factory and the shared client error.                                                     |

## Steps

1. **`keys.ts`** — export `sensorsKey()`, `fieldsKey()`, `columnsKey()`, `enumKey(name)`,
   `estimateKey(params)`, `searchKey(id)`, `searchResultsKey(id, cursor)`, `sessionKey(id)`,
   `sessionFlowKey(id, bucketMs)`, `protocolSchemaKey(protocol)`. Each returns
   `['<resource>', ...args] as const`. Ids stay strings. Nested keys start with their parent's prefix
   (`searchResultsKey` begins with `searchKey`'s head) so one `invalidateQueries` can drop a whole
   subtree. Normalize optional arguments to `null` rather than dropping them, so `(id)` and
   `(id, undefined)` cannot produce two entries.
2. **`http-error.ts`** — `class HttpError extends Error` carrying `status`, `code`, `detail`,
   `retryAfterMs` and the whole parsed `body`; a static `fromResponse(res)` that reads the JSON error
   envelope, falls back to the status text when the body is not JSON, and parses `retry-after` (seconds
   or HTTP-date — reuse the existing parser by moving it out of the server-only module into a shared
   one, since it has no server dependencies).
3. **`fetch-json.ts`** — `fetchJson<T>(path, { query, signal })`: builds `/api/capture/<path>`, sends
   `accept: application/json`, no auth headers of any kind, returns parsed JSON on success and throws
   `HttpError.fromResponse(res)` otherwise. Every query function goes through this and nothing else.
4. **`query-retry.ts`** — import `isHttpError` from `http-error.ts`, delete the local structural type,
   and add: a `session_revoked` code is never retried regardless of status. `MAX_ATTEMPTS` stays 3, as
   decided.
5. **`response-schemas.ts`** — a small ordered list of `[RegExp, schema]` built from the generated
   module (`zListSensorsResponse`, `zListFieldsResponse`, `zListColumnsResponse`, `zGetEnumResponse`,
   `zGetEstimateResponse`, `zGetSearchResponse`, `zGetSearchResultsResponse`, `zGetSessionResponse`,
   `zGetSessionFlowResponse`, `zGetProtocolSchemaResponse`, `zGetMeResponse`, `zGetHealthResponse`) plus
   `schemaForPath(path)` returning `undefined` when nothing matches.
6. **Proxy** — resolve the schema for the joined path and pass it to `callApi`; unmapped paths keep
   working unvalidated. A mismatch already becomes a 502 through `toErrorPayload`.
7. **Tests** — the four new test files above, plus the added case in `query-retry.test.ts`.
8. **`CLAUDE.md`** — one line under Architecture: keys live in one module, browser failures are
   `HttpError`, the proxy validates what it can.

## Risks

- **Two identities for one resource.** The whole point of step 1 is defeated if a later hook builds a
  key inline. Mitigation: the factory is the only export that returns a key, and the reviewer checklist
  already flags inline keys. `http.get_dedupe` is the backend's version of this check.
- **Prefix coupling.** Making `searchResultsKey` start with `searchKey` means a careless
  `invalidateQueries(searchKey(id))` also drops every page of results. That is the intent, but it must
  be written down in the module, or someone will invalidate the job on every poll and refetch all pages.
- **Cursor in the key.** Results are paged by cursor; if the cursor lands in the key verbatim we get one
  entry per page, which is correct for infinite queries but means the key must never be built from a
  re-encoded cursor. Pass it through byte-for-byte (`http.invalid_cursor`).
- **`Retry-After` regression.** Moving the parser out of the server-only module risks changing behaviour
  for the login path, where the header is an HTTP-date. The existing tests cover both forms and must
  stay green untouched.
- **Retry amplifying a storm.** Under `--chaos storm` a 503 on every attempt plus three retries triples
  the request count. The delay already honours `Retry-After` and backs off exponentially; nothing here
  may shorten it.
- **Refresh and logout races.** `fetchJson` must forward the caller's `AbortSignal` so that cancelling
  queries on logout actually stops the requests; without it `auth.logout_once` fails once screens exist.
- **Schema drift breaking reads.** Validating proxied bodies means a backend change that our generated
  schemas have not caught up with turns a working screen into a 502. `npm run api:sync` runs before
  every `npm run dev`, which keeps the window small, and unmapped paths stay unvalidated on purpose.
- **Token leakage.** `fetch-json.ts` is browser code: it must import nothing from the server-only
  modules. A stray import would fail the build, which is the check we rely on.

## Verification

| #   | Acceptance criterion                                | How it is proven                                                                                                                                                                                      |
| --- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Same resource, same inputs → one request            | Unit: two calls to the same factory produce deep-equal keys. Runtime: a temporary two-component probe under `npm run dev` shows one network call, then `capture-api report` → `http.get_dedupe` PASS. |
| 2   | Different inputs → separate entries                 | Unit: keys differ for different ids, cursors and normalized optional arguments.                                                                                                                       |
| 3   | Rate-limited failure waits out the advertised delay | Unit: `retryDelay` with an `HttpError` carrying `retryAfterMs` returns at least that value; the HTTP-date form is covered by the existing parser tests.                                               |
| 4   | A non-429 client error is never retried             | Unit: `retry` returns false for 400/403/404 and for `session_revoked`.                                                                                                                                |
| 5   | The API's stable code reaches the screen            | Unit: `HttpError.fromResponse` on a proxy error body exposes `code`; runtime: a bad session id through the proxy surfaces `not_found`.                                                                |
| 6   | A revoked session is its own kind of failure        | Unit: the proxy's payload maps to an `HttpError` with `session_revoked`; the existing `toErrorPayload` test covers the server half.                                                                   |
| 7   | Tests fail if the shape or the rules change         | Reverting any step turns at least one new test red — check by reverting locally before handing over.                                                                                                  |
| —   | Nothing else regressed                              | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`; `npm run test:e2e` (the smoke specs must still pass); `capture-api report` with no FAIL.                |
