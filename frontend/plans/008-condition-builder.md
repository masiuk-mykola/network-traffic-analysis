# Plan 008 — Building the condition

Spec: `specs/008-condition-builder.md`. Its open questions were answered: a flat list of conditions
joined by all-or-any with negation per condition, carried in the address bar in the API's own
`field:op:v1,v2` form, and no text query mode.

## Files to touch

| Path                                                    | Change                                                                                                                                                |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/search/condition.ts` (new)                     | The condition model: a flat list, a join, negation per row; `toFilterNode` builds what the API takes; `describeCondition` reports what is unfinished. |
| `src/lib/search/condition.test.ts` (new)                | Arity per operator, the API shape for each, negation, the join, and every way a row can be incomplete.                                                |
| `src/lib/search/condition-params.ts` (new)              | `f=field:op:v1,v2` in both directions, including values that contain a comma or a colon.                                                              |
| `src/lib/search/condition-params.test.ts` (new)         | Round trip, a hostile or malformed `f`, an unknown field, an operator the field does not allow.                                                       |
| `src/lib/search/query-params.ts`                        | The query state grows a `conditions` array; parse and write delegate to the module above.                                                             |
| `src/lib/search/use-fields.ts` (new)                    | The field catalogue, cached long — it changes about as often as the server is deployed.                                                               |
| `src/lib/search/use-enum.ts` (new)                      | The values of one closed field, fetched only when that field is chosen and keyed by its catalogue name.                                               |
| `src/lib/api/keys.ts`                                   | No change: `fieldsKey()` and `enumKey(name)` already exist.                                                                                           |
| `src/app/(app)/search/condition-builder.tsx` (new)      | The list of rows, the join switch, add and remove.                                                                                                    |
| `src/app/(app)/search/condition-row.tsx` (new)          | One row: field picker, operator picker, the value entry the field and operator call for, negate, remove.                                              |
| `src/app/(app)/search/value-input.tsx` (new)            | The value entry per shape: one value, two bounds, a set, a closed set, or nothing at all.                                                             |
| `src/app/(app)/search/condition-builder.test.tsx` (new) | Field-driven operators, clearing on field change, arity refusals, loading, failure and empty states.                                                  |
| `src/app/(app)/search/query-form.tsx`                   | Hosts the builder, includes its state in the URL mirror, and blocks the search while a row is unfinished.                                             |
| `src/components/form/select.tsx` (new)                  | A Radix select styled like the rest, used by both pickers.                                                                                            |
| `e2e/condition-builder.spec.ts` (new)                   | The real catalogue, real enum values, a reload, and no repeat fetch for the same field.                                                               |
| `CLAUDE.md`                                             | One line: conditions are flat, built from the published catalogue, and travel in the API's own form.                                                  |

## Steps

1. **`condition.ts`** (test first) — a row is `{ id, field, op, values, negated }`. `toFilterNode(rows, join)`
   returns `{ all: [...] }` or `{ any: [...] }`, wrapping a negated row in `{ not: … }`; a row with
   `exists` carries no value, a range carries exactly two, a set one to fifty, everything else one.
   `describeCondition` returns the first thing that is wrong with a row so the UI can point at it.
2. **`condition-params.ts`** (test first) — one `f` per row, `field:op:v1,v2`, values URL-encoded so a
   comma inside a value survives the round trip. Parsing drops a row whose field is not in the
   catalogue or whose operator that field does not allow — a shared link can carry either.
3. **`query-params.ts`** — fold the conditions into the existing state so one place still owns the URL.
4. **`use-fields.ts` / `use-enum.ts`** — two queries over the proxy. The catalogue is fetched once per
   session (`staleTime` long); an enum is fetched on first use of its field and then reused from the
   cache, which is what keeps the builder from asking twice for the same set.
5. **`select.tsx`** — Radix select with the project's tokens and focus ring, used for both pickers.
6. **`value-input.tsx`** — chooses its shape from the field type and the operator: a closed set becomes
   a select over the published values; a range becomes two bounds side by side; a set becomes a
   list-of-values entry; `exists` renders nothing. Types drive the input mode (a port is numeric, an
   address is text).
7. **`condition-row.tsx`** — field picker (grouped by the prefix in the field name, searchable),
   operator picker limited to that field's list, the value entry, a negate toggle and a remove button.
   Changing the field keeps the operator only when the new field allows it.
8. **`condition-builder.tsx`** — the rows, an all/any switch, an add button, and the shared loading,
   error and empty states for the catalogue.
9. **`query-form.tsx`** — renders the builder between the points and the window, includes the rows in
   what it mirrors to the URL, and extends its existing "what is wrong" message to cover an unfinished
   row.
10. **Tests** — unit for the two pure modules and the builder; e2e against the real catalogue.
11. **`CLAUDE.md`** line.

## Risks

- **A stale operator after a field change.** Silently keeping `between` when moving to a field that
  only allows `eq` produces a search the API refuses. The row clears what the new field does not allow,
  and a test covers the pair.
- **Arity.** A range with one bound, a set with none, a value attached to `exists` — each is a rejected
  search rather than an empty one. The model enforces it and the form will not submit until it holds.
- **Values that contain the separators.** A hostname glob or a user agent can contain a comma or a
  colon; encoding each value is what keeps the URL parseable, and the tests use such values.
- **A hostile link.** `f` arrives from strangers: an unknown field, an operator the field forbids, more
  values than allowed, or nonsense. Parsing drops what it cannot trust instead of throwing.
- **Fetching the same enum twice.** The builder can hold several rows on the same closed field. One
  query key per catalogue name, and no refetch on focus, keeps it to one request — this is the check
  the backend scores as duplicate GETs.
- **Fetching the catalogue on every keystroke.** The field picker filters what it already has; it never
  asks the server per search term.
- **Chaos.** Under `storm` the catalogue request can fail; the builder shows the shared error state with
  a retry rather than rendering an empty field list, which would read as "this server has no fields".
- **The URL growing.** Every keystroke in a value would otherwise rewrite the address bar; the mirror
  stays on `router.replace` and the rows are held locally, exactly as the window already is.

## Verification

| #   | Acceptance criterion                             | How it is proven                                                                                                                                         |
| --- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The field list comes from the server             | E2E: the picker holds the catalogue's own names, including a protocol-specific one.                                                                      |
| 2   | Only the declared operators are offered          | Builder test with a stubbed catalogue: an address field offers its three, a port field its four.                                                         |
| 3   | Changing the field clears an impossible operator | Builder test: set `between` on a port, switch to a field without it, and the operator is empty.                                                          |
| 4   | A closed field offers its values                 | Builder test: choosing it renders a select of the published values, not a text box. E2E against the real enum.                                           |
| 5   | Wrong arity is refused before sending            | Unit: one bound, empty set, too many values. Builder test: the search stays blocked with a reason.                                                       |
| 6   | A no-value operator shows no value entry         | Builder test: choosing `exists` removes the value control.                                                                                               |
| 7   | Conditions combine and negate                    | Unit: the built node for all, any and a negated row matches the API's shape.                                                                             |
| 8   | An unfinished row blocks the search and says why | Builder test: an empty value disables the button and names the row.                                                                                      |
| 9   | The condition survives a reload                  | E2E: build two rows, reload, both are there with their values.                                                                                           |
| 10  | The same closed field is not fetched twice       | E2E: count requests for that enum across two rows on the same field — exactly one. Then `capture-api report` with `http.get_dedupe` not FAIL.            |
| —   | Nothing else regressed                           | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL. |
