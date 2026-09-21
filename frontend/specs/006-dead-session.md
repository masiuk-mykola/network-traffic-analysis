# 006 — When the session dies mid-use

## Context

A session here does not last. Access is short-lived and renewed behind the scenes, but the family
behind it can end at any moment: it idles out, it hits its maximum age, or it is revoked outright —
and the screens that are coming will sit there for a long time, polling a running search. So the
question is not whether a session will die while someone is looking at the app, but what happens when
it does.

Today the plumbing recognises the case and stops short of acting on it. A call whose session is gone
comes back marked as exactly that, it is not retried, and the shared failure vocabulary already words
it as "your session ended, sign in again". But nothing acts: whatever else is in flight stays in
flight, anything on a timer keeps firing, the cache keeps its contents, and the person is left looking
at an error where their data used to be, with no way forward except finding the address bar.

That last part is not only a usability problem. The API watches for exactly this and counts any
authorised call made more than five seconds after a session was revoked against the client. A screen
that keeps polling through a dead session fails that check — and the screens in the next phase are
built around polling.

## Goals / Non-goals

**Goals**

- The moment the app learns its session is gone, it stops asking for anything else.
- The person is returned to sign in, understands why, and can get back to what they were doing.
- Nothing from the dead session survives into the next one.
- A session that is merely being renewed, or a server that is merely struggling, triggers none of this.

**Non-goals**

- No attempt to keep a session alive longer, no background renewal beyond what already happens.
- No preserving of unsaved form input across the interruption.
- No change to how the guard behaves on a fresh navigation — that is already settled.
- No warning before the session ends; the API gives no signal one is coming.

## Requirements

- When any request reports that the session is gone, the app cancels what is in flight, stops anything
  scheduled, and makes no further authorised request — within the few seconds the API allows.
- Several requests failing at the same instant cause one reaction, not one per request.
- The person is taken to the sign-in screen and told, there, why they are looking at it.
- Where they were is remembered, so signing in again puts them back rather than at a default screen.
- Nothing cached under the old session is shown afterwards — in particular after signing in as a
  different account, which sees different data.
- A failure that does not mean the session is gone — a timeout, a server error, a rate limit — leaves
  the session alone and is handled as it is today.
- The transition is not mistaken for a crash: the person should not be left staring at an error page
  that never resolves.

## Acceptance criteria

1. A request reporting a dead session takes the person to sign in → current: NO → expected: YES.
2. No authorised request is made more than five seconds after the session was revoked → current:
   unverified → expected: YES.
3. Several simultaneous failures produce a single return to sign in → current: NO → expected: YES.
4. The sign-in screen explains why it appeared → current: NO → expected: YES.
5. Signing in again returns to the screen that was interrupted → current: NO → expected: YES.
6. Data fetched by the previous account is not visible after signing in as the other one → current: NO
   → expected: YES.
7. A server error or a rate limit does not send anyone to sign in → current: NO → expected: YES.

## Open questions

1. **What about work that outlives the session?** A search runs on the server; the session dying does
   not stop it. After signing in again, should the app try to pick that job back up, or is returning to
   the same screen enough for now?
2. **How is the reason shown on the sign-in screen?** A brief message that disappears, or a line on the
   form that stays until the next attempt? The first is lighter; the second survives a reload.
3. **Does a dead session need the same treatment when it is discovered by a background refresh rather
   than by something the person did?** Nothing polls yet, so there is no way to tell how intrusive an
   unprompted jump to sign in would feel.
