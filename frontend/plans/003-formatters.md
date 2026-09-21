# Plan 003 — Value formatting

Spec: `specs/003-formatters.md`. Its open questions were answered: timestamps are shown in **UTC**
everywhere with the zone stated, a byte pair shows the **total plus both directions**, and durations are
**milliseconds under a second, readable units above**.

## Files to touch

| Path                               | Change                                                                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/format/bytes.ts` (new)    | `formatBytes(n)` and `formatByteCount({ up, down })` → `{ total, up, down }`, all as strings.                                         |
| `src/lib/format/duration.ts` (new) | `formatDuration(ms)`: `840 ms`, `2.4 s`, `1 m 12 s`, `3 h 05 m`.                                                                      |
| `src/lib/format/time.ts` (new)     | `formatTimestamp(iso)` → `2025-10-27 09:14:03.120 UTC`; `formatTimeOfDay(iso)` → `09:14:03.120` for dense cells; both fixed to UTC.   |
| `src/lib/format/endpoint.ts` (new) | `formatEndpoint({ ip, port, host, country })` → `{ address, host, country }`, omitting what the API did not send.                     |
| `src/lib/format/value.ts` (new)    | `EMPTY` marker plus `formatByColumnType(type, value)`, covering the kinds the server documents and falling back to text for the rest. |
| `src/lib/format/*.test.ts` (new)   | One test file per module, edge cases first.                                                                                           |
| `src/lib/format/index.ts` (new)    | Barrel, so screens import one path.                                                                                                   |
| `CLAUDE.md`                        | One line under Conventions: formatting lives in one place, ids are never parsed.                                                      |

## Steps

1. **`bytes.ts`** — binary-ish readable units (`B`, `kB`, `MB`, `GB`, `TB`) with one decimal above
   `kB` and none for whole bytes; `formatByteCount` returns the three strings the table needs so the
   caller does not add them up itself. Negative or non-finite input returns the empty marker rather
   than `NaN`.
2. **`duration.ts`** — under 1000 ms → `N ms` (integer); under a minute → one decimal second; under an
   hour → `M m SS s`; above → `H h MM m`. Zero is `0 ms`, not empty; negative is the empty marker.
3. **`time.ts`** — format from the ISO string with `Intl.DateTimeFormat` pinned to `timeZone: 'UTC'`,
   `hour12: false`, and milliseconds preserved by formatting the fractional part explicitly (the API
   always sends three digits). An unparseable string returns the raw input, never `Invalid Date`. The
   sensor's own zone and the legacy local string are deliberately ignored — see the risk below.
4. **`endpoint.ts`** — `address` is `ip:port`, IPv6 wrapped in brackets; `host` and `country` are
   returned only when present, so the caller renders no empty gap.
5. **`value.ts`** — a `formatByColumnType` switch over the documented column kinds (`ts`, `ip_port`,
   `bytes`, `risk`, `protocol`, `duration`, `text`, `country`, `sensor`, `id`): `id` is passed through
   character-for-character, `risk` renders its score with its band, enums are shown as the API spells
   them, and anything else — including an undocumented kind — is coerced to a plain string. Null and
   undefined always produce the shared empty marker.
6. **Tests** — one file per module. Each covers: a typical value, the boundary between units, zero,
   absent, and a malformed input.
7. **Barrel + `CLAUDE.md`** line.

## Risks

- **Silently mixing zones.** The API answers in UTC, each capture point publishes its own zone, and one
  field arrives as a legacy local string in a different format. Pinning everything to UTC is the
  decision; the danger is a later screen reading that legacy string as if it were UTC. The time module
  only accepts ISO input, and the tests assert that the formatted output carries the `UTC` label, so
  the mistake is visible rather than silent.
- **Identifiers through numeric code paths.** Session ids exceed `Number.MAX_SAFE_INTEGER`. The `id`
  kind must not touch `Number()`, `parseInt` or any arithmetic; the test uses a real 20-digit id and
  asserts the exact string survives.
- **Locale drift.** `Intl` with an implicit locale formats differently on a CI runner than on a laptop
  and would make snapshots flap. Every formatter pins its locale and zone explicitly.
- **An empty marker that reads as a bug.** Using an empty string for absent values makes a table look
  broken. One shared marker, used everywhere, and a test that it is distinct from a formatted zero.
- **Rounding that hides evidence.** A duration rounded to `1 m` loses the milliseconds that tell whether
  two sessions overlapped. The rounding rule keeps full precision below a second, which is where this
  traffic lives; the detail view can show the raw value later if it needs to.
- Nothing here touches the data layer, so no backend check can move.

## Verification

| #   | Acceptance criterion                          | How it is proven                                                                                                  |
| --- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 1   | Same magnitude renders identically everywhere | Unit: one module owns each kind; `formatByColumnType` delegates to it rather than reimplementing.                 |
| 2   | A byte pair keeps both directions             | Unit: `formatByteCount` returns total, up and down; the total equals the sum.                                     |
| 3   | Sub-second durations stand out                | Unit: `840` → `840 ms`, `2400` → `2.4 s`, and the boundary at exactly 1000 ms.                                    |
| 4   | A timestamp states its zone                   | Unit: the full form ends with `UTC`; the compact form is asserted against a fixed input.                          |
| 5   | An endpoint without a hostname has no gap     | Unit: `host` is absent from the result, not an empty string.                                                      |
| 6   | A wide id survives exactly                    | Unit: a 20-digit id in, the same string out; asserted against the value the API documents.                        |
| 7   | An absent value is an explicit marker         | Unit: null, undefined and an empty string all produce the marker, and a zero does not.                            |
| 8   | A malformed value renders as text             | Unit: a broken timestamp, a non-numeric byte count and an unknown column kind each return a string, no throw.     |
| —   | Nothing else regressed                        | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`. |
