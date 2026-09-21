# 016 — The flow timeline

## Context

A session screen now says what a session is and, for DNS, what was exchanged. What it cannot show is
_how the traffic moved while the session was open_: whether the bytes went up in one push or trickled
both ways, where the quiet stretches were, whether the two directions are wildly lopsided. The server
publishes exactly that — the session's traffic summed into time buckets, each with bytes and packets
in both directions — and nothing in the interface reads it yet.

Two properties of that data shape this screen. The server omits a bucket in which nothing happened,
so consecutive samples are not necessarily consecutive moments: a picture that simply lines them up
side by side would silently compress a minute of silence into nothing. And the bucket width is ours
to ask for within a narrow range, so the same session can come back as three columns or as two
hundred, depending on what we ask — and asking for a width outside that range is refused outright.

The sessions in this capture make both matter: one runs for two minutes and is nearly all upload,
another lasts fifty-eight milliseconds and can only ever be a single bucket.

## Goals / Non-goals

**Goals**

- Show how a session's traffic was distributed over its own lifetime, in both directions.
- Choose a bucket width that suits the session rather than a fixed one, and let the reader change it.
- Be honest about silence: a stretch with no traffic looks like a gap, not like adjacent traffic.
- Make the numbers behind the picture readable, including without a mouse.

**Non-goals**

- Traffic across sessions, or comparing one session with another.
- Zooming or panning, selecting a range, or exporting the series.
- Per-packet detail; the server publishes sums per bucket and that is what is shown.
- Any change to the other protocol views.

## Requirements

- The session screen shows a compact timeline of the session's traffic, with both directions
  distinguishable and the direction of each visible at a glance.
- The reader can switch between bytes and packets; the shape of the traffic is shown for whichever is
  chosen.
- The bucket width is chosen from the session's own duration, so a two-minute session and a
  fifty-millisecond one both produce a readable picture rather than one column or two hundred.
- The reader can change the bucket width among widths the server accepts; the interface never asks
  for one it would refuse.
- A bucket the server omitted is drawn as absent, so a quiet stretch reads as quiet.
- The totals of the series are stated in words next to the picture, and each bucket's moment and its
  numbers are readable as text, reachable by keyboard as well as by pointer.
- A session too short to have more than one bucket says that plainly instead of drawing a single bar
  and pretending it is a trend.
- While the series loads, the screen says so and the rest of the session stays usable; a session with
  no series at all says there is nothing recorded; a failure explains itself and offers one retry.
- Reading the series costs one request per session and per chosen width — not one per redraw — and
  changing the width does not re-read a width already read.

## Acceptance criteria

1. Opening a session shows a timeline of its traffic with both directions — current: NO → expected:
   YES.
2. The timeline's bucket width differs between a two-minute session and a fifty-millisecond one —
   current: NO → expected: YES.
3. Changing the bucket width redraws the timeline, and the interface never sends a width the server
   rejects — current: NO → expected: YES.
4. A session whose series has gaps shows those gaps rather than a continuous run of columns —
   current: NO → expected: YES.
5. Switching between bytes and packets changes what is drawn — current: NO → expected: YES.
6. Each bucket's moment and numbers are readable as text and reachable by keyboard — current: NO →
   expected: YES.
7. A session with one bucket or none says so instead of drawing a chart — current: NO → expected:
   YES.
8. A failure to read the series leaves the rest of the session on screen and offers a retry —
   current: NO → expected: YES.
9. Re-reading the same width twice in quick succession does not happen; the backend's verdict stays
   clean while the timeline is used — current: unknown → expected: YES.

## Open questions

- How to scale two directions that differ by orders of magnitude — one shared scale makes the smaller
  direction invisible, separate scales make the two incomparable. Proposed: one shared scale with the
  directions mirrored around a baseline, and the totals stated in text so the smaller direction is
  never lost.
- Whether the bucket width should be offered as a few named widths or as a free number within the
  allowed range. Proposed: a few widths derived from the session's duration, all inside the range the
  server accepts.
