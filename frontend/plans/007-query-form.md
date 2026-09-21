# Plan 007 — The query form

Spec: `specs/007-query-form.md`. Its open questions were answered: the default window ends at the
latest packet the chosen points reported and opens some hours before it, the points are a checkbox
list, and the choices live in the address bar from the start — so item 2.7 extends this rather than
rewriting it.

## Files to touch

| Path                                             | Change                                                                                                                |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `src/lib/search/query-params.ts` (new)           | Reading and writing the query state in the URL: sensors, `from`, `to`. Parse is total — anything unusable falls back. |
| `src/lib/search/query-params.test.ts` (new)      | Round trip, missing and malformed values, too many sensors, a reversed window.                                        |
| `src/lib/search/window.ts` (new)                 | `defaultWindow(sensors)` from the latest `last_packet_at`, and `describeWindow` for the hint under the fields.        |
| `src/lib/search/window.test.ts` (new)            | Latest packet wins, a lagging point does not shorten it, no sensors at all, malformed timestamps.                     |
| `src/lib/api/keys.ts`                            | Nothing new — `sensorsKey()` already exists and is reused.                                                            |
| `src/lib/search/use-sensors.ts` (new)            | The React Query hook over the proxy, typed from the generated schema.                                                 |
| `src/app/(app)/search/page.tsx`                  | Server component: reads the query state from `searchParams`, renders the form.                                        |
| `src/app/(app)/search/query-form.tsx` (new)      | `'use client'`: the sensor list, the two window fields, validation, and the URL write on change.                      |
| `src/app/(app)/search/query-form.test.tsx` (new) | Loading, empty, error, the two limits, a reversed window, and that choices reach the URL.                             |
| `src/app/(app)/search/sensor-option.tsx` (new)   | One row: name, site, status, and the lag when it is behind.                                                           |
| `src/components/form/checkbox.tsx` (new)         | Radix checkbox styled like the rest, so the list is keyboard-reachable and labelled.                                  |
| `e2e/query-form.spec.ts` (new)                   | The real list from the API, the limits, the default window, and a reload keeping the choices.                         |
| `CLAUDE.md`                                      | One line: query state lives in the URL.                                                                               |

## Steps

1. **`query-params.ts`** (test first) — `parseQuery(searchParams)` → `{ sensorIds, from, to }`, where
   sensors come from a repeated or comma-joined parameter, are de-duplicated, clipped to the five the
   API accepts, and filtered against the ones this account may read; `from`/`to` are kept only when
   they parse as instants and `from < to`. `toQueryString(state)` writes them back. Nothing throws.
2. **`window.ts`** (test first) — `defaultWindow(sensors)`: end = the latest `last_packet_at` among the
   given points (all readable ones when none are chosen yet), start = end minus six hours. A point
   that is behind does not drag the end backwards; it only earns a marker in the list. Returns null
   when no point has ever reported, so the form can say so instead of inventing a window.
3. **`use-sensors.ts`** — `useQuery({ queryKey: sensorsKey(), queryFn: () => fetchJson('sensors') })`,
   typed as the generated `SensorList`. No polling: the list changes rarely, and the backend scores
   chatter.
4. **`checkbox.tsx`** — Radix `Checkbox` with the project's tokens, an accessible label association,
   and the same focus ring as the other controls.
5. **`sensor-option.tsx`** — one row per point: name, site, a status chip, and, when the point is
   behind, how far behind in words (the existing duration formatter).
6. **`query-form.tsx`** — client component holding the choices in React state seeded from the URL. On
   every change it replaces the URL (`router.replace`, no history entry per keystroke). Validation is
   local: at least one point, at most five, `from` before `to`, both present. The submit control is
   present but does nothing yet — starting a search is item 2.4 — and is disabled while the list is
   loading or the form is invalid.
7. **`page.tsx`** — server component that reads `searchParams`, parses them, and hands the result to
   the form as its initial state. The page stays a server component; only the form is client.
8. **States** — loading: the list area shows the shared loading state and the submit is disabled;
   empty: when the account may read no points, an empty state explaining that, and no picker; error:
   the shared error state with a retry that refetches.
9. **Tests** — unit for the two pure modules and the form; e2e against the real API.
10. **`CLAUDE.md`** line.

## Risks

- **The URL as the source of truth.** Writing on every keystroke either floods the history or fights
  the input. `router.replace` plus keeping the fields in local state and syncing outward is the shape;
  syncing inward on every render would make the fields jump while typing.
- **Sensor list and permissions.** The observer account may read fewer points. Filtering the parsed
  sensor ids against the list this account actually gets is what stops a shared link from asking for a
  point the reader cannot see — which the API would refuse with a 403 the person cannot act on.
- **Five is a hard limit.** The API refuses six. The form must refuse locally, or the first thing a
  new user sees is a server error. The clip in the parser covers links that carry more.
- **A window that means nothing.** The data ends in the past. A default built from "now" returns an
  empty result that looks like a bug, which is exactly what the default window rule avoids — but it
  also means the hint under the field has to say why the dates are not today.
- **Timezones.** The points publish their own zones and one field arrives as a local string; the form
  works in UTC like everything else, and says so. Reading `last_packet_at` is safe — it is an instant.
- **Duplicate requests.** The form and a future estimate will both want the sensor list; one query key
  and no polling keeps it to a single request (`http.get_dedupe`).
- **Chaos.** Under `storm` the list request can fail or be slow; the error state with a retry covers it,
  and the retry must not be offered while a stated wait is pending — the shared state already handles
  that.

## Verification

| #   | Acceptance criterion                         | How it is proven                                                                                                                                                                                                    |
| --- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The picker lists exactly the readable points | E2E: the analyst sees three, the observer sees what the API gives that account, and the two differ.                                                                                                                 |
| 2   | No point chosen is refused in place          | Form test: clearing the last one disables submit and shows the reason, with no request.                                                                                                                             |
| 3   | More than the API accepts is refused         | Unit: the parser clips a link carrying six. Form test: the sixth cannot be selected and says why.                                                                                                                   |
| 4   | A point that is behind is marked             | E2E: the lagging point in the fixture shows its status and how far behind it is.                                                                                                                                    |
| 5   | A reversed window is refused                 | Unit: the parser drops it. Form test: the message appears and submit is disabled.                                                                                                                                   |
| 6   | The default window covers real traffic       | Unit: the end equals the latest packet among the chosen points. E2E: the fields are not today's date.                                                                                                               |
| 7   | While loading, the form cannot be submitted  | Form test with a pending query: the submit is disabled and the loading state is announced.                                                                                                                          |
| 8   | A failed list offers a retry                 | Form test with a failing query: the error state renders and retry refetches.                                                                                                                                        |
| 9   | A reload keeps the choices                   | E2E: choose, reload, and the same points and window are there.                                                                                                                                                      |
| —   | Nothing else regressed                       | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL — this item reads from the API, so it moves the data layer. |
