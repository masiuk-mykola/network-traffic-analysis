# 005 — Guarding the app

## Context

Signing in works, but nothing depends on it. The working screens answer to anyone who types their
address, and they will keep answering once they hold real traffic. Today that leaks nothing because
those screens are still placeholders, which makes this the cheapest possible moment to close the door.

There is a second, quieter gap. Once signed in, the interface never says who you are. This API hands
out two very different views of the same data — one account sees every capture point, the other is
read-only with parts withheld — so "which of them am I looking at?" is a question the interface will
have to answer constantly. Without it, a reviewer comparing the two accounts cannot tell whether data
is missing because it does not exist or because this account may not see it.

And there is no way out. A session ends only when its tokens expire, which makes it impossible to
switch accounts, and impossible to check that ending a session actually stops the app from using it —
something the backend scores.

## Goals / Non-goals

**Goals**

- A visitor without a session cannot reach a working screen, and is taken to sign in instead.
- After signing in, that visitor continues to where they were going, not to a fixed landing screen.
- Every signed-in screen shows who is signed in and what kind of access they have.
- Signing out ends the session, returns to sign in, and leaves nothing behind that a later screen
  could use.

**Non-goals**

- No permission-aware hiding of individual controls yet; that belongs with the screens that have
  something to hide.
- No handling of a session that dies mid-use — that is the next item.
- No "remember me", no session extension, no multi-device session list.
- No new data screens; the working screens stay placeholders.

## Requirements

- A request for a protected screen without a valid session ends at the sign-in screen rather than a
  protected one, before any protected content is produced.
- A cookie whose session no longer exists counts as no session.
- After signing in, the visitor lands on the screen they originally asked for; if there was none, the
  main working screen.
- The destination carried through sign-in cannot be used to send someone to another site.
- A signed-in screen shows the account's name and the kind of access it has, in the same place on every
  screen.
- Signing out ends the session on the server, returns the person to sign in, and afterwards no screen
  can be reached again by going back in history.
- After signing out, the app makes no further requests on that session's behalf.
- The guard costs no additional round trip per navigation beyond what is needed to establish identity.
- If the check itself cannot be completed because the API is unreachable, the person is told something
  went wrong — not silently treated as signed out.

## Acceptance criteria

1. Opening a protected screen with no session ends at sign in → current: NO → expected: YES.
2. Opening a protected screen with a cookie whose session is gone ends at sign in → current: NO →
   expected: YES.
3. Signing in from that point lands on the originally requested screen → current: NO → expected: YES.
4. A destination pointing at another site is ignored → current: NO → expected: YES.
5. A signed-in screen shows the account's name and access level → current: NO → expected: YES.
6. Signing out returns to sign in, and going back does not show a protected screen → current: NO →
   expected: YES.
7. No request carrying the old session is made after signing out → current: unverified → expected: YES.
8. When the API is unreachable, the guard shows a failure instead of a sign-in screen → current: NO →
   expected: YES.

## Open questions

1. **What does the guard do when the API is merely struggling?** Under load the API answers with a
   refusal that means "try again", not "you are not signed in". Treating that as signed out would throw
   a working session away; showing an error screen blocks someone whose session is fine. The
   requirement above picks the error screen — worth confirming, because it is the difference between an
   annoying moment and losing your place.
2. **How much of the account's access do we surface?** The name and role are clearly useful. The API
   also lists the exact permissions and the capture points this account may read; showing them would
   explain later absences, but it is detail most users never need.
3. **Should signing out be confirmed?** It is one click away from losing a running search later. A
   confirmation is friction; an accidental sign-out in the middle of a long job is worse.
