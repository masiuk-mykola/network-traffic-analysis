# 003 — Value formatting

## Context

The screens ahead are mostly tables and detail views over the same handful of value kinds: moments in
time, durations, byte counts, network endpoints, identifiers, risk scores. The API sends all of them in
machine form — timestamps as ISO strings with milliseconds, durations as integer milliseconds, byte
counts as a pair of integers, endpoints as an address plus a port and sometimes a hostname and a
country, identifiers as decimal strings wider than a JavaScript number can hold. None of that is
readable in a table meant to be scanned quickly, and the result screen is explicitly judged on being
comfortable to scan.

The API also tells us what kind each column is, and says to fall back to plain text for kinds it has
not documented. So the presentation vocabulary is not ours to invent: it already exists, and what is
missing is one shared implementation of it. Building that before the first table means every screen
renders a duration the same way, and — more importantly — that the identifiers which must never be
treated as numbers are handled correctly in one place instead of three.

There is a real hazard here beyond tidiness. This data exists in several time zones at once: the API
answers in UTC, each capture point has its own zone, and one field is a legacy local string in a
different format entirely. An interface that quietly mixes them would make a forensic timeline wrong in
a way nobody notices until they are reading it as evidence.

## Goals / Non-goals

**Goals**

- One shared presentation for every value kind the server names, with a documented fallback for kinds
  it does not.
- Values that are absent read as explicitly absent, not as something that failed to load.
- Identifiers survive the round trip untouched — never rounded, never reformatted.
- A compact form for a dense table cell and a full form for a detail view, where the two differ.

**Non-goals**

- No table, no column configuration, no sorting — this is the vocabulary those will use.
- No localisation or user-selectable units.
- No charts or any visual encoding of magnitude.
- No parsing in the other direction; nothing here turns user input into API values.

## Requirements

- Every value kind the server publishes for a column has exactly one way of being rendered, and an
  undocumented kind renders as plain text rather than failing.
- A byte count reads at a glance at any magnitude, from a handful of bytes to gigabytes, and makes
  clear that it is a pair of directions rather than one number.
- A duration reads in units suited to its size, and stays honest for the very short ones that this
  traffic is full of.
- A moment in time is shown to the precision the API provides, and the zone it is shown in is
  unambiguous to the reader.
- A network endpoint shows the address and port together, adds a hostname or country only when the API
  provided them, and never invents them.
- An identifier is displayed exactly as received.
- An absent optional value renders as a consistent marker that cannot be mistaken for a loading state
  or a failure.
- No value, however unexpected, causes a render to fail; the fallback is the raw text.

## Acceptance criteria

1. The same magnitude renders identically wherever it appears → current: NO → expected: YES.
2. A byte pair shows both directions and is not collapsed into a single ambiguous number → current: NO
   → expected: YES.
3. A sub-second duration is distinguishable from a multi-second one at a glance → current: NO →
   expected: YES.
4. A timestamp states which zone it is in → current: NO → expected: YES.
5. An endpoint without a hostname renders without an empty gap where the hostname would be → current:
   NO → expected: YES.
6. A wide identifier is shown character-for-character as the API sent it → current: NO → expected: YES.
7. An absent value renders as an explicit marker, distinct from a zero and from an empty cell →
   current: NO → expected: YES.
8. An unexpected or malformed value renders as text instead of throwing → current: NO → expected: YES.

## Open questions

1. **Which zone do we show?** The API answers in UTC; every capture point also has its own zone, and
   one field arrives as a legacy local string in a third format. Showing UTC everywhere is the
   defensible default for evidence, showing the viewer's local zone is friendlier, and showing the
   capture point's zone is what an analyst on site would expect. This decision affects every screen, so
   it is worth making once, now.
2. **How is a byte pair laid out in a dense cell?** Both directions inline costs width in a table that
   already has many columns; showing the total with the split revealed on demand costs an interaction.
3. **How exact are durations?** Rounding to a readable unit is easier to scan; keeping milliseconds
   matters when the question is whether two sessions overlapped.
