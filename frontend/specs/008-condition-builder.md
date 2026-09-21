# 008 — Building the condition

## Context

The query form now says where and when to look. What it cannot yet say is what to look for, and that
is where a traffic search earns its keep: a hundred thousand sessions over three days is not something
anyone scrolls, and without conditions the only search anyone can run is "everything".

The shape of a condition is not ours to invent. The API publishes its searchable fields — around
thirty of them, from addresses and ports to protocol-specific ones like a TLS fingerprint or a DNS
query name — and for each one it says what type it holds and which comparisons it allows. Ports accept
ranges; addresses accept a network prefix; hostnames accept wildcards; several fields are closed sets
whose allowed values the API will hand over on request. Guessing any of this on the client, or
hard-coding the list, means the interface goes stale the moment the server changes, and the task
explicitly asks for a condition built from the fields the server publishes.

The comparisons also disagree about how many values they take: most want one, a range wants exactly
two, a set wants between one and fifty, and one of them wants none at all. Getting that wrong produces
a rejected search rather than an empty one, which is a worse way to learn.

## Goals / Non-goals

**Goals**

- A person builds a condition out of the fields the server actually publishes, with the comparisons
  that field allows and nothing else.
- Values are entered in a way that matches what the field holds, including picking from a closed set
  when the field has one.
- A condition that the API would reject is caught before it is sent, and explained where it went wrong.
- Conditions combine: several of them at once, or alternatives, and the ability to exclude.
- The condition survives a reload and travels with the rest of the query.

**Non-goals**

- No running the search — still the next item.
- No free-text query language, even though the API offers one; this is the guided path.
- No saved or suggested conditions, no history of what was searched before.
- No validating a value against the data itself (whether any session actually has that address).

## Requirements

- The list of fields comes from the server, grouped so a protocol-specific field is findable without
  reading all thirty, and searchable by name.
- Choosing a field offers only the comparisons that field declares, and changing the field drops a
  comparison the new field does not allow rather than carrying it over silently.
- The value entry matches the field: a closed set is chosen from the values the server publishes, a
  range asks for two bounds, a set accepts several values, and a comparison that takes no value asks
  for none.
- The number of values is enforced before sending: exactly two for a range, at least one and at most
  what the API accepts for a set.
- Conditions can be combined so that all of them must hold, or any of them, and any condition or group
  can be negated.
- A condition that is incomplete is visibly unfinished and blocks the search rather than being dropped
  silently.
- While the field list is loading, the builder shows that and cannot be used; if it fails, it offers to
  try again; if the account may see no fields, it says so.
- The values a closed field allows are fetched only when that field is actually chosen, and not
  repeatedly for the same field.
- The whole condition survives a reload, alongside the points and the window.

## Acceptance criteria

1. The field list matches what the server publishes, not a list baked into the app → current: NO →
   expected: YES.
2. Only the comparisons a field declares are offered for it → current: NO → expected: YES.
3. Changing the field to one that does not allow the current comparison clears it instead of keeping
   an impossible pair → current: NO → expected: YES.
4. A field with a closed set offers its values rather than free text → current: NO → expected: YES.
5. A range with one bound, or a set with none, is refused before sending → current: NO → expected: YES.
6. A comparison that takes no value shows no value entry → current: NO → expected: YES.
7. Several conditions can be required together, offered as alternatives, or negated → current: NO →
   expected: YES.
8. An unfinished condition blocks the search and says what is missing → current: NO → expected: YES.
9. The condition survives a reload → current: NO → expected: YES.
10. Choosing the same closed field twice does not ask the server for its values twice → current: NO →
    expected: YES.

## Open questions

1. **How much nesting do we allow?** The API accepts groups inside groups, up to a large limit. A flat
   list of conditions joined by "all" covers most real searches and is far simpler to build and to
   read; full nesting is more faithful to what the server can do, and is where a builder usually
   becomes unpleasant to use.
2. **How does the condition travel in the address bar?** It is a tree, and the window and points are
   simple values. Encoding it readably is work; encoding it opaquely makes a shared link unreadable
   and harder to debug.
3. **Should the guided builder be able to hand over to the query language later?** The API parses a
   text form of the same thing. Leaving room for it costs nothing now; pretending it does not exist
   may cost a rewrite.
