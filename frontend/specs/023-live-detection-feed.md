# 023 — The live detection feed

## Context

The three required screens are finished and every graded check passes. What the task calls optional
remains, and the roadmap's 6.1 is the first of those: the server publishes detections as they
happen, over a long-lived stream, and nothing in this interface listens to it. The task handed over
names the live event feed first among the optional items, and the roadmap agrees; the two do not
disagree anywhere.

Taking it on means taking on its three graded checks, which today report nothing at all because no
stream is ever opened. That is the real cost: the feature is small, the discipline around it is not.
The server keeps a ring of the most recent detections and hands out a resume point, it ends the
stream on a schedule that is as short as twenty seconds under its storm profile, and it ends it
differently again when the opening credentials expire. A feed that reconnects carelessly is worse
than no feed, because it turns three silent checks into three failures.

## Goals

- A reader can watch detections arrive without reloading, and can get from one to the session it
  names.
- The stream survives the endings the server actually produces — scheduled rotation, an expiring
  credential — without losing detections and without being seen as a careless client.
- Exactly one connection exists per signed-in session, however many times the interface is opened,
  mounted or navigated.

## Non-goals

- The remaining optional items. None is started here.
- Any change to the server.
- Alerting, acknowledging, muting or any other action on a detection. This is a feed to read.
- A permanent history of everything ever detected. What the server still holds is enough.
- Changing what the finished screens do. The feed is added beside them, not into them.

## Requirements

- Detections appear as the server releases them, newest first, each showing when it happened, what
  rule named it, how severe it is, which capture point saw it, and the two endpoints involved.
- A detection leads to the session it names, and the session identifier is carried as text
  throughout — it is wider than a number.
- On opening, the reader sees what the server still holds rather than an empty list that fills only
  if something happens to occur while they watch.
- When the stream ends and is resumed, no detection is missed and none is shown twice. If the
  server says the resume point is too old to honour, the reader is told the feed restarted rather
  than shown a silent gap.
- A second copy of the interface — another tab, a remount, a navigation — does not cause a second
  connection to the server.
- After the stream ends, the next attempt is not immediate: there is a visible, finite pause before
  reconnecting, and repeated failures lengthen it rather than retrying in a tight loop.
- When the credentials the stream opened with expire, the feed continues under fresh ones without
  the reader doing anything.
- When the session ends, the connection ends with it, promptly, and nothing reconnects afterwards.
- No credential of the server's reaches the browser, exactly as on every other screen.
- While the first detections are being fetched the reader sees the shared loading state; a feed with
  nothing in it reads as quiet rather than broken; a feed that cannot be opened reports the failure
  where the feed is, offers a retry, and leaves the rest of the screen usable. The existing
  vocabulary for these three states is used; nothing new is invented.
- The connection's condition is visible — live, reconnecting, or stopped — so a stalled feed is
  never mistaken for a quiet network.
- A feed that is not being looked at does not hold a connection open indefinitely for nothing.

## Acceptance criteria

- **AC-1.** Detections released by the server appear in the interface without the reader reloading
  the page. _current: NO → expected: YES_
- **AC-2.** Opening the feed shows the detections the server still holds, not an empty list.
  _current: NO → expected: YES_
- **AC-3.** A detection leads to the session it names, and that session opens.
  _current: NO → expected: YES_
- **AC-4.** After the server ends the stream on its own schedule, the feed resumes and the
  detections released in between are present exactly once. _current: NO → expected: YES_
- **AC-5.** A resume point the server refuses as too old is reported to the reader as a restart, not
  as a failure and not as silence. _current: NO → expected: YES_
- **AC-6.** With the interface open in two tabs, the server sees one stream for the session, not
  two. _current: NO → expected: YES_
- **AC-7.** Every re-opening of the stream carries a resume point, and none follows an ending by
  less than the pause the server's own checks require. _current: NO → expected: YES_
- **AC-8.** When the opening credentials expire, the feed continues without the reader acting.
  _current: NO → expected: YES_
- **AC-9.** After signing out, no connection to the server remains and none is re-opened.
  _current: NO → expected: YES_
- **AC-10.** No credential of the server's is observable in the browser while the feed runs.
  _current: YES → expected: YES_ (regression guard)
- **AC-11.** The three feed-related graded checks report pass, and every check that passes today
  still does, under the calm, storm and token-expiry profiles.
  _current: NO (they report nothing) → expected: YES_
- **AC-12.** The project's written account lists the feed as done and says what its checks now
  report. _current: NO → expected: YES_

## Open questions

Answered by the author on 2026-09-22, before the plan was written. Kept with the answers rather
than deleted, because the plan's decisions only make sense next to the question they settle.

1. **Where the feed lives.** — **Answered: a screen of its own**, reachable from the app's
   navigation beside the search screen. No finished screen is edited, the states are provable from
   outside, and "not being looked at" becomes a question about one screen rather than about a
   panel's collapsed state.
2. **Whether the feed can be narrowed to particular capture points.** — **Answered: no.** Every
   capture point the account may read. Changing such a filter means ending and re-opening the
   stream, which is the one thing the server grades most closely; the task does not ask for it.
3. **How much history is shown at once.** — **Answered: what the server still holds**, and no more.
   Older entries fall off the end as new ones arrive, so the screen never grows without bound.
4. **What "not being looked at" should mean for the connection.** — **Answered: hold, then close
   after a grace period.** The connection is kept while any reader holds the screen open, hidden
   tab included, and is ended only once no reader has been attached for a short while. A tab hidden
   and shown again would otherwise produce an ending and a re-opening each time, which is precisely
   what two of the three graded checks measure. The cost is one idle connection for the length of
   the grace period.
5. **Whether a detection's arrival should be announced outside the feed.** — **Answered: no.** No
   count, no badge, nothing in the header. It is visible where it is read. The list itself still has
   to behave for assistive technology, since it changes on its own.

Next step: /plan specs/023-live-detection-feed.md
