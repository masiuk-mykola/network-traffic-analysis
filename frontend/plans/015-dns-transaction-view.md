# 015 — A first-class DNS view (implementation plan)

Read this before implementing. The spec is `specs/015-dns-transaction-view.md`.

## Decisions taken (the spec's open questions, answered)

- Anomalies are **the server's words only**: the risk reasons and any rule it says fired. A query
  name that looks machine-generated is not marked by us.
- Copying is proven by a **component test for the value** and by the **control's presence** in the
  end-to-end flow; no clipboard permissions are granted to the e2e browser.

## What the payload actually looks like (probed 2026-09-21)

The contract types `decoded` as a free-form object — there is no DNS schema to generate from, so the
reader normalises it and is tested against the real thing:

| Field            | Canonical decoder (`dns/2`)   | Older decoder (`dns/1`) |
| ---------------- | ----------------------------- | ----------------------- |
| `transaction_id` | `46419`                       | `"56926"`               |
| `rcode`          | `{code: 3, name: "NXDOMAIN"}` | `"3"`                   |
| `flags`          | `qr, aa, tc, rd, ra`          | `qr, rd, ra` only       |
| `answers`        | list                          | list                    |
| `authority`      | list of records               | **one record object**   |
| `ttl`            | `3600`                        | `"3600"`                |

The riskiest sessions in this capture are DNS: `nxdomain_burst` — "Burst of NXDOMAIN answers",
MITRE `T1568.002`, carried in the session's risk reasons (their `detections` list is empty). Query
types seen: A, AAAA, HTTPS, SRV, PTR, MX.

## Files to touch

| File                                                 | Change                                                                                                                                                                                    |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/session/dns.ts` (new)                       | `readDnsExchange(decoded)`: one normalised exchange or `null` — question, response code with its name, the flags that are set, and the three record sets, from either decoder generation. |
| `src/lib/session/dns.test.ts` (new)                  | Both generations; a single record where a list belongs; a numeric string time to live; a response code with no known name; a payload with no DNS in it; an empty payload.                 |
| `src/components/ui/copy-button.tsx` (new)            | A small control that copies a raw string and says it did. Silent when the browser refuses.                                                                                                |
| `src/components/ui/copy-button.test.tsx` (new)       | The raw value reaches the clipboard, not the formatted one; a refusal does not break the screen.                                                                                          |
| `src/components/ui/index.ts`                         | Export it.                                                                                                                                                                                |
| `src/app/(app)/sessions/[id]/dns-exchange.tsx` (new) | The layout: the question on one side, the response on the other, records beneath, flags in words, and the server's risk reasons and rules against the transaction.                        |
| `src/app/(app)/sessions/[id]/session-view.tsx`       | When the exchange reads, render it above the generic list; the generic list stays, so nothing decoded is lost.                                                                            |
| `src/app/(app)/sessions/[id]/session-view.test.tsx`  | A DNS session shows the exchange; a non-DNS session does not; the generic list is still there in both cases.                                                                              |
| `e2e/session-view.spec.ts`                           | Open a real DNS session from the results: the exchange is on screen, the copy control is there, and no request goes out that the generic view did not make.                               |
| `CLAUDE.md`, `plans/000-roadmap.md`                  | One convention line; mark 3.2 done. At the end, not during.                                                                                                                               |

Not touched: the summary header, the generic renderer, the API layer — this step adds no read.

## Steps

1. **The reader first, test-first.** `dns.ts` is pure and is where both decoder generations are
   reconciled: numbers coerced from strings, a lone record wrapped into a list, a bare response code
   given its name from a small table, absent flags simply absent. It returns `null` when the payload
   holds no DNS at all, which is what keeps every other protocol untouched.
2. **The response-code table** lives with the reader: the handful of codes the capture can produce,
   and an unknown code rendered as its number rather than dropped.
3. **The copy control**, test-first: it copies the value it was given, not what the screen shows, and
   swallows a refusal (a browser without clipboard access must not break a forensic screen).
4. **The layout.** Question and response side by side at the top; the record sets beneath, each with
   name, type, time to live and data; flags as the names of the ones set; and the server's risk
   reasons and rules stated in its own words with the technique it names.
5. **Wire it in** `session-view.tsx`: the exchange renders above the generic list, and the generic
   list is unchanged — that is what satisfies "nothing is lost by specialising" without a second
   copy of the data.
6. **Component tests** over the two real payloads already used in this suite's fixtures, plus a
   non-DNS one to prove the generic path is untouched.
7. **E2E**: a DNS row from a real search, then the two documentation lines.

## Risks

- **A second read sneaking in.** The exchange must be derived from the session already on screen. If
  it grew its own query, a DNS session would cost an extra request per visit and `http.get_dedupe`
  would eventually notice. The e2e counts requests on the session screen to keep this honest.
- **Coercion that lies.** Turning `"3600"` into `3600` is right; turning an identifier into a number
  is not. The session id never passes through this reader, and the reader coerces only the fields it
  names.
- **A payload that is DNS-shaped but not DNS.** The reader keys off the protocol's own branch, and
  returns `null` rather than rendering half an exchange.
- **Clipboard in a test environment.** jsdom has no clipboard; the control must degrade instead of
  throwing, and the component test stubs it rather than assuming it.
- **Duplicated data on screen.** The exchange and the generic list show the same values twice by
  design. The generic list stays complete on purpose — the alternative is hiding fields the layout
  does not know about, which is exactly what this screen must not do.
- **Chaos and sessions.** Nothing changes in the data layer, so `storm` and `expiring-tokens`
  behave as they did for 3.1; the session read and its retry are untouched.

## Verification

| Spec criterion                                  | Proof                                                                                                     |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 1 — reads as a transaction                      | Component test: the exchange region exists with the question and the response. E2E on a real DNS session. |
| 2 — a bare code is named                        | Unit test on the reader for `"3"` → NXDOMAIN, and for an unknown code number.                             |
| 3 — a single authority record shows             | Unit test with the observed `dns/1` payload; component test asserts the record is on screen.              |
| 4 — a quoted time to live reads the same        | Unit test comparing both generations' normalised records.                                                 |
| 5 — flags read as names                         | Unit test (set flags only) and component test.                                                            |
| 6 — the server's reason is with the transaction | Component test with `nxdomain_burst` in the session's risk reasons.                                       |
| 7 — copying gives the raw value                 | Component test on the control with a stubbed clipboard.                                                   |
| 8 — nothing decoded is lost                     | Component test: the generic list is still rendered for a DNS session.                                     |
| 9 — other protocols unchanged                   | Component test with a non-DNS payload: no exchange region, generic list as before.                        |
| 10 — no new requests                            | E2E counts requests while opening a DNS session; `capture-api report` after the run shows no FAIL.        |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
