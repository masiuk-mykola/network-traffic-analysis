# Capture — traffic forensics

A web interface for the capture API in `../backend`. Three screens: sign in, search, session.

## The compromised machine

**`ws-hb-009.quillmere.example` (10.20.40.18), seen at the `harbor-branch` capture point.**

It starts at **2025-10-25 03:11:38.456 UTC**, fifteen minutes before anything else happens: the
machine resolves `telemetry.static-assets-cdn.test`, a name that appears nowhere else in the capture
before that moment.

- [The first lookup](http://localhost:3000/sessions/216172823837671425) — `A
telemetry.static-assets-cdn.test → 203.0.113.201`, answered with a sixty-second time to live. The
  server scores it 46 and gives one reason: _rarely seen domain_.
- Ten and twenty-five seconds later, two more lookups under the same parent with random-looking
  labels — `71dbe240.static-assets-cdn.test`, `96a10af4.static-assets-cdn.test` — both answered
  _no such name_.
- [The first call home](http://localhost:3000/sessions/216172823853400065), at **03:26:56.200 UTC**:
  TLS 1.2 to `203.0.113.201:443` (Austria), 4.3 kB, 1.5 s. The server's reasons: _self-signed
  certificate_, _certificate name does not match SNI_, _rarely seen domain_.
- [Every call home, oldest first](http://localhost:3000/search?sensor=hq-core&sensor=dc-east&sensor=harbor-branch&from=2025-10-24T00%3A00%3A00.000Z&to=2025-10-28T00%3A00%3A00.000Z&f=tls.sni%3Aeq%3Atelemetry.static-assets-cdn.test&sort=ts)
  — press **Run search**. 668 sessions across the three days of the capture, all from this one
  machine, one every five to six minutes, each around four kilobytes, from 03:26 on 25 October until
  the capture ends.

What the server asserts is quoted above. **Our conclusion** is the shape: one host, one destination,
a fixed small payload at a fixed short interval, through a certificate that does not match the name
it claims — traffic that keeps a channel open rather than doing anything a person asked for. The
capture shows traffic, not intent; nothing here says what was taken.

### How it was found

1. Searched the whole capture across all three points and ordered by the server's own risk. The top
   of that list is a SYN sweep — loud, but see below.
2. Excluded that one host from the same query. What surfaced was `10.20.40.18` calling
   `telemetry.static-assets-cdn.test` over and over, scoring 70–84 every time.
3. Opened one of those sessions and walked _around this session_ — the neighbours the server relates
   to it — which showed the same pair of machines every few minutes, all day.
4. Narrowed the window backwards until the pattern stopped: nothing before 2025-10-25 03:26, and one
   quiet DNS lookup of the same name fifteen minutes earlier. That lookup is where it starts.

### What was ruled out

- **The port scanner, `scan-it-01.quillmere.example` (10.20.9.250).** It owns the highest scores in
  the capture — the server calls it _port-scan pattern · T1046_, 86 out of 100 — and it sweeps
  hundreds of hosts across dozens of ports. It is also entirely internal: every connection is
  128–148 bytes with no payload, from a machine whose name says what it is, and nothing it touches
  ever leaves the network. Loud, scheduled, and not the answer.
- **The random-looking DNS names.** Lookups like `c81e40ba.packages.example.net` answered _no such
  name_ look exactly like a domain-generation algorithm, and the server flags the bursts
  (_burst of NXDOMAIN answers · T1568.002_). Searching for them across the capture returns roughly
  twenty different machines at all three capture points, against many unrelated parent domains, most
  scoring in single digits. A pattern that names twenty machines names none of them — background
  noise. (The compromised host makes two such lookups of its own, which is why the pattern is worth
  checking rather than dismissing on sight.)

### A gap this investigation found in the interface

When conditions are joined with **any**, the estimate shown next to the run control is wrong: the
estimate endpoint only accepts conditions that are ANDed together, so a query like _source is X or
destination is X_ is estimated as _source is X **and** destination is X_ — which is impossible, and
the line reads "No sessions match this query" for a query that in fact matches hundreds. The search
itself is correct; only the estimate is. It is not worked around: it is written down here, and the
honest fix is to say the estimate cannot be given for an any-joined query rather than to show a
number that is not true.
