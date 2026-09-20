---
name: api-layer
description: Wire up a capture-API endpoint in this project — the server-side call, the route handler the browser talks to, and the React Query hook. Use whenever the user mentions adding an API call, a new endpoint, fetching data, a mutation, a query, a proxy route, pagination, or integrating a schema type — even if they don't say "service".
---

# API layer — server-side call → route handler → React Query hook

The API has CORS off and wants a bearer token, so the browser never calls it. Three layers, each with
one job. Read the `http-discipline` skill before writing any of them.

## 1. The server-side call (`src/lib/api/`)

- `client.ts` — `rawFetch`: base URL, timeouts, `ApiError`, `Retry-After` parsing. No retries, no
  refresh, no auth decisions.
- `session-store.ts` — tokens per session id, single-flight refresh per family.
- `server.ts` — `callApi`: resolves the session, injects the token, refreshes once on a 401 and replays
  the request exactly once.

Anything in this folder starts with `import 'server-only'`. Never add a second path to the API, and
never import these modules from a client component.

```ts
const { data } = await callApi<components['schemas']['SessionPage']>({
  path: '/v1/searches/{id}/results'.replace('{id}', searchId),
  query: new URLSearchParams({ limit: '200' }),
})
```

## 2. The route handler (`src/app/api/**`)

- Read-only proxying goes through the catch-all `src/app/api/capture/[...path]/route.ts`.
- Anything with its own semantics gets its own handler (`/api/auth/login`, `/api/auth/logout`).
- A handler returns the upstream `status` and a JSON body; it forwards `Retry-After` and
  `X-Limit-Applied` when they matter, maps `SessionGone` to a 401, and never leaks a token.
- Pass `request.signal` down so a cancelled browser request cancels the upstream one.

For a mutation that must be idempotent (`POST /v1/searches`), generate the `Idempotency-Key` in the
handler and reuse it for the retry of the same logical action.

## 3. The React Query hook (`src/lib/queries/` or next to the feature)

- One `queryKey` shape per resource, exported and reused — duplicate GETs are scored.
- The hook owns loading, empty and error states; the component renders them.
- Retry policy is already centralized in `src/lib/query-retry.ts` — do not override `retry` per hook
  unless the endpoint genuinely differs, and never make it retry a 4xx.
- Paginate with the cursor the server returned, verbatim, through `getNextPageParam`.
- Poll with backoff via `refetchInterval`, and stop polling when the job is done.

```ts
export const searchResultsKey = (id: string, cursor?: string) =>
  ['search-results', id, cursor ?? null] as const
```

## Types

Always `components['schemas'][...]` from `src/lib/api/schema.d.ts`. Regenerate with
`npm run api:types` when `../backend/openapi.json` moves. Never hand-write an API type, never edit the
generated file, never parse a session id as a number — they are uint64 decimal strings.

## Checklist before calling it done

- [ ] No `CAPTURE_API_URL` or `Authorization` reachable from client code
- [ ] One `queryKey` shape, no raw `fetch` past React Query
- [ ] Loading, empty and error states exist and were seen
- [ ] Behaves under `--chaos storm` and `--chaos expiring-tokens`
- [ ] `capture-api report` shows no FAIL
