# 001 — Cache identity and a structured client error

## Context

The next phases add several screens that read server data, and more than one of them reads the same
data: the capture points, the field catalogue, a running search and its pages. Today nothing in the
browser reads anything yet, so there is no shared answer to two questions that every one of those
screens will ask. First, how a piece of cached server data is identified — if two parts of the UI ask
for the same thing under different identities, the cache holds it twice and the same request goes out
twice, which the backend scores as a defect. Second, what a failed request looks like to the UI — the
retry policy already assumes a failure that carries a status, a stable machine-readable code and the
wait the server advertised, but nothing produces such a failure, so today a failed request is an opaque
error the policy cannot reason about and a screen cannot explain.

Settling both once, before any screen exists, is cheaper than retrofitting them into five screens.

## Goals / Non-goals

**Goals**

- One shared way to identify every piece of cached server data, so identical requests collapse into one.
- One structured failure shape available to every screen, carrying enough to decide what to show and
  whether to retry.
- Both wired into the existing retry policy, so future screens inherit the behaviour without opting in.

**Non-goals**

- No new screens, and no new data being fetched.
- No change to how sessions, tokens or refresh work on the server side.
- No visual design for error or loading states — that is the next item.
- No tuning of cache lifetimes or refetch policy beyond what already exists.

## Requirements

- Two places in the UI that ask for the same resource with the same inputs must share one cache entry
  and one in-flight request; the same resource with different inputs must stay separate.
- A failed request must reach the UI as structured data: the HTTP status, the API's stable error code
  when the response carries one, a message safe to show a person, and the wait the server advertised
  when it advertised one.
- A rate-limited response must not be retried sooner than the advertised wait, whichever of the two
  forms the server used to express it.
- A client error that is not rate limiting must not be retried.
- A revoked or expired session must be distinguishable from any other failure, so a screen can send the
  person to sign in instead of showing a generic error.
- Nothing about tokens or upstream internals may become visible to the browser through the failure.
- Loading and empty behaviour is unchanged: this item adds no fetching surface, so there is nothing new
  for a person to see while data loads or when there is none.

## Acceptance criteria

1. Two independent parts of the UI request the same resource with the same inputs → current: two
   separate requests and two cache entries: NO → expected: one request, one shared entry: YES.
2. The same resource requested with different inputs stays in separate entries → current: NO →
   expected: YES.
3. A rate-limited failure that advertises a wait is retried no earlier than that wait → current: NO →
   expected: YES.
4. A client error that is not rate limiting is never retried → current: NO → expected: YES.
5. A failure exposes the API's stable error code to the screen that triggered it → current: NO →
   expected: YES.
6. A revoked session is reported as its own kind of failure, distinct from a generic one → current: NO
   → expected: YES.
7. The failure shape and the identity rules are covered by tests that fail if either is changed →
   current: NO → expected: YES.

## Open questions

1. The API's error envelope may carry extra machine-readable keys beyond code and message. Do we keep
   them on the structured failure now (useful later for field-level validation), or drop them until
   something needs them?
2. Should a revoked session be handled centrally here — clearing state and sending the person to sign
   in — or is that behaviour part of the sign-in work in the next phase, with this item only making the
   case distinguishable?
3. The current policy stops after three attempts. Keep that number as the shared default, or make it
   per-resource for the long-running search polling?
