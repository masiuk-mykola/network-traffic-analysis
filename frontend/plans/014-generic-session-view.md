# 014 — The generic session view (implementation plan)

Read this before implementing. The spec is `specs/014-generic-session-view.md`.

## Decisions taken (the spec's open questions, answered)

- A field marked sensitive is **shown with a marker**, not hidden behind a control.
- Values from the older decoder that do not sit where the published description says are **shown as
  undescribed**, not guessed into a published label.

## What the live server actually returns (probed 2026-09-21)

| Observation                                                           | Consequence for the renderer                                                            |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `dns` v2: `rcode: {code, name}`, `authority` is a list                | The published paths (`dns.rcode.code`, `dns.authority[].name`) describe this shape.     |
| `dns` v1: `rcode: "2"`, `authority` is a single object                | Those paths resolve to nothing; the values surface as undescribed.                      |
| `tls` v2 `alpn: ["h2"]` vs v1 `alpn: "h2"`                            | A path may hold a list where it held a scalar; both must render.                        |
| `smb2.operations[]`, `tcp.first_payload_hex`                          | Decoded content the description does not mention exists in the seed data.               |
| `tcp.first_payload_hex` has type `hex`                                | A value kind outside the documented vocabulary; render as text (the `geo_hint` lesson). |
| `intel` absent, `detections`/`files` empty, `pcap: {available: true}` | Every optional block needs its own "nothing here" wording.                              |
| ids like `216172827537047572`                                         | uint64 as a string; nothing may parse it.                                               |

## Files to touch

| File                                                      | Change                                                                                                                                                           |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/session/decoded-path.ts` (new)                   | Resolve a published path against `decoded`: dotted segments, `[]` meaning "each element", returning a list of values. No mapping, no guessing.                   |
| `src/lib/session/decoded-path.test.ts` (new)              | Nested hit, list expansion, a path into a scalar (the v1 `rcode` case), a missing branch, a path that hits `null`.                                               |
| `src/lib/session/described.ts` (new)                      | Split `decoded` into described rows (in the published order, with title, unit, sensitive flag, values) and leftovers — every leaf the description never claimed. |
| `src/lib/session/described.test.ts` (new)                 | A v2 payload fully described; a v1 payload whose values all land in leftovers; a payload with extra branches; an empty `decoded`.                                |
| `src/lib/format/value.ts`                                 | Add the value kinds this screen needs and the published vocabulary lacks (`hex`, `ja3`, `cidr`, `string`, `enum`), keeping the default as text.                  |
| `src/lib/format/value.test.ts`                            | The new kinds, and an unknown kind still falling through to text.                                                                                                |
| `src/lib/session/use-session.ts` (new)                    | The session read; a 404 becomes a `NOT_FOUND` sentinel rather than an error, as the search screen does with a job that is gone.                                  |
| `src/lib/session/use-session.test.tsx` (new)              | 404 → sentinel, other failures still errors, no read without an id.                                                                                              |
| `src/lib/session/use-protocol-schema.ts` (new)            | The per-protocol description, cached for the session of the app (it changes on the scale of a deploy, not a visit).                                              |
| `src/app/(app)/sessions/[id]/page.tsx`                    | Reads the session on the server (so a cold-opened address answers once, like the search screen does with its job) and hands it to the client view.               |
| `src/app/(app)/sessions/[id]/session-view.tsx` (new)      | The client screen: summary header, transaction, undescribed block, detections/files/capture facts, back link, and the loading/not-found/failed/empty states.     |
| `src/app/(app)/sessions/[id]/session-summary.tsx` (new)   | The header: time and duration, capture point, protocol and transport, endpoints, bytes and packets, risk with its band and reasons, intel when present.          |
| `src/app/(app)/sessions/[id]/transaction.tsx` (new)       | The described rows and the undescribed leftovers, each row label + value(s), sensitive marked.                                                                   |
| `src/app/(app)/sessions/[id]/session-view.test.tsx` (new) | Component tests over the real shapes: a v2 session, a v1 session, an undecoded one, a missing one.                                                               |
| `src/components/ui/*`                                     | Only if a primitive is missing for the label/value rows; prefer plain markup over a new primitive.                                                               |
| `e2e/session-view.spec.ts` (new)                          | Open a row from a finished search; read the header and one published label; open a made-up id; confirm the reads are one apiece.                                 |
| `src/app/dev/session/**`                                  | Delete the temporary probe — this screen replaces the thing it existed to prove (tracked in the roadmap's 2.1 row).                                              |
| `CLAUDE.md`, `plans/000-roadmap.md`                       | One convention line; mark 3.1 done. At the end, not during.                                                                                                      |

Not touched: the flow timeline (3.3), related sessions (3.4), downloads (6.3), and the first-class
protocol layout (3.2) — this screen must stay generic so 3.2 can be written against it.

## Steps

1. **Path resolution first, test-first.** `decoded-path.ts` is the whole feature in miniature and is
   pure: given `dns.answers[].name` and a payload, return every value that path names. A segment that
   is not there ends the walk with nothing; `[]` over a non-list yields nothing rather than throwing,
   which is exactly the v1 `authority` case.
2. **The split.** `described.ts` walks the published fields in order, collects what each path
   resolves to, and separately walks `decoded` collecting every leaf that no published path claimed.
   The leftovers keep their dotted path as their label — that is the honest name for something the
   server never titled.
3. **The value kinds.** Extend the shared formatter rather than formatting inside the screen, so the
   table and this screen keep agreeing about what a byte count or a duration looks like.
4. **The reads.** `use-session` mirrors `use-search`'s shape, including the 404-as-an-ending
   treatment; `use-protocol-schema` is a plain cached read keyed by protocol. Both go through the
   existing proxy, which already validates these two paths.
5. **Server-side first read.** The page reads the session and passes it as the client query's initial
   data, the way the search page now does with its job. This is what keeps a cold-opened address to
   one read, and it is also what makes the not-found case answer once rather than once per mount.
6. **The screen.** Summary, then transaction, then the undescribed block, then the facts about
   detections, carved files and the raw capture. Each block states its own emptiness. The back link
   uses the browser's own history so the results, their order and their rows come back as they were.
7. **Component tests against real shapes.** Copy the actual payloads observed above into fixtures —
   a `dns/2`, a `dns/1`, one with `decoded: {}` — rather than inventing tidy ones.
8. **E2E**, then delete the dev probe, then verify, then the two documentation lines.

## Risks

- **Parsing the id.** The id is a uint64 string. Any `Number()`, `parseInt`, or arithmetic on it
  silently corrupts the link. It is passed through as a string everywhere, and the e2e asserts the
  address it lands on equals the one the row carried.
- **Two reads per visit becoming four.** The screen reads a session and a description. React mounts a
  screen twice in development, so anything not hydrated or cached is asked twice — `http.get_dedupe`
  allows at most two identical GETs per 100 ms, and a 404 asked twice is a scored retry. Hence the
  server-side first read in step 5, and a long `staleTime` on the description.
- **A 404 treated as a failure** would put the shared error state on screen with a retry button,
  which would ask again for something that will never exist. It is an ending, like a job the server
  no longer has.
- **Unbounded rendering.** A decoded payload can carry a long list (`smb2.operations`, DNS answers)
  and a long hex string. Values are rendered as they are but the block is allowed to scroll; nothing
  is truncated silently, because a forensic reader needs the whole value.
- **Cache collision with the search screen.** The session key already exists in the key factory and
  is nested under its own prefix, so nothing here can invalidate a search or its result pages.
- **Chaos.** Under `storm` the session read fails and the screen offers its retry; the shared retry
  policy still refuses to retry a 4xx. Under `expiring-tokens` the read goes through the usual single
  refresh on the server.
- **Deleting the dev probe** removes a route some e2e might reach. Check before removing; if a spec
  uses it, move that spec's assertion onto this screen in the same step.

## Verification

| Spec criterion                                | Proof                                                                                                                  |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1 — the summary is on screen                  | Component test over a real payload; e2e reads the capture point and protocol after opening a row.                      |
| 2 — published labels, published order         | Component test asserts the rendered label sequence equals the description's; e2e checks one label for a real protocol. |
| 3 — the older decoder's values still appear   | Component test with the observed `dns/1` payload: its values are on screen, under the undescribed block.               |
| 4 — undescribed content is visible and marked | Same test asserts the marking, and that a described field is not in that block.                                        |
| 5 — an unknown id says so                     | Unit test: 404 → the sentinel. E2E: open a made-up id, read the sentence, and confirm exactly one read went out.       |
| 6 — nothing decoded says so                   | Component test with `decoded: {}`.                                                                                     |
| 7 — the id is never parsed                    | Unit test with an id above 2^53 round-tripping unchanged; e2e compares the row's target with the landed address.       |
| 8 — the backend's verdict stays clean         | `capture-api report` after the e2e run: no FAIL, watching `http.get_dedupe`, `http.retried_4xx`, `auth.logout_once`.   |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
