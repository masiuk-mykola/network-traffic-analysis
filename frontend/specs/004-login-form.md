# 004 — The sign-in form

## Context

Everything the interface does needs a session, and right now there is no way for a person to start
one. The server side is already built and exercised: a sign-in request reaches the API from our own
server, the tokens are kept there, and the browser receives nothing but an opaque session cookie. What
is missing is the screen — the sign-in route is still a placeholder with a sentence on it.

This is also the first screen of the whole task, so it sets the pattern every later one follows: a form
that validates before it bothers the server, a pending state that cannot be double-submitted, and a
failure rendered through the shared vocabulary rather than a bespoke red box.

Two properties of this particular endpoint shape the work. It is rate limited per email — a handful of
wrong attempts in a minute and it refuses further ones for a stated period — so a form that fires a
request on every keystroke or lets a user hammer the button makes the situation worse for them. And its
stated wait is expressed as a moment in time rather than a number of seconds, which is unusual enough
that treating it like every other wait would silently produce nonsense.

## Goals / Non-goals

**Goals**

- A person can sign in with an email and a password and lands in the app.
- Obvious mistakes are caught before a request is sent, so a rate-limit budget is not spent on an empty
  field.
- Every way the attempt can fail is visible and understandable: wrong credentials, too many attempts,
  the server being unavailable.
- The screen is usable from the keyboard alone and announces what happened.

**Non-goals**

- No protection of the rest of the app yet — redirecting an anonymous visitor away from a screen they
  should not see is the next item.
- No sign-out control, no profile display in the shell.
- No password reset, no account creation, no "remember me", no third-party sign-in.
- No session expiry handling for a session that dies later while the user works.

## Requirements

- The form asks for an email and a password, and both are required; an attempt with either missing is
  rejected locally, with the offending field identified, and nothing is sent.
- Only a plausible email is sent: a value that cannot be one is rejected locally.
- While an attempt is in flight the submit control is unavailable and clearly shows that work is
  happening, so the same attempt cannot be sent twice.
- Wrong credentials produce a message that says the pair was not accepted, without hinting whether the
  email exists.
- When the server refuses further attempts for a period, the screen says so and does not invite another
  attempt until that period has passed.
- A server or network failure is distinguishable from a rejected password, and offers to try again.
- On success the person ends up on the main working screen, and the sign-in screen is not left behind
  in the history as somewhere "back" returns to.
- Nothing about the credentials or the resulting tokens is observable in the browser: not in storage,
  not in a URL, not in a response body the page can read.
- The whole flow works with the keyboard alone, fields are labelled, and both the pending state and the
  failure are announced.

## Acceptance criteria

1. Submitting with an empty email or password shows a field-level message and sends no request →
   current: NO → expected: YES.
2. Submitting a value that cannot be an email shows a field-level message and sends no request →
   current: NO → expected: YES.
3. While the attempt is in flight the submit control cannot be activated again → current: NO →
   expected: YES.
4. A wrong password shows a failure that does not reveal whether the email is known → current: NO →
   expected: YES.
5. After the server refuses further attempts, the screen states the wait and does not offer an
   immediate retry → current: NO → expected: YES.
6. A successful sign-in lands on the main working screen → current: NO → expected: YES.
7. A capture of the browser's traffic and storage after a successful sign-in contains no API token →
   current: unverified → expected: YES.
8. The form can be completed and submitted using only the keyboard → current: NO → expected: YES.

## Open questions

1. **Where does a successful sign-in land?** Always the main working screen, or back to whatever the
   person was trying to reach? The second only matters once the rest of the app is protected, which is
   the next item — but the decision shapes this one.
2. **Do we show the demo accounts on the screen?** The task hands over two sets of credentials, and a
   reviewer opening this app cold would find them useful. A real product would never do it.
3. **What happens if someone already signed in opens this screen?** Send them onward, or let them sign
   in again as somebody else? The second is genuinely useful here, because the two demo accounts see
   different data.
