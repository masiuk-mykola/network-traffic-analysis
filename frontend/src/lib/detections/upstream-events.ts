/**
 * What the feed emits, shared by the side that produces it and the side that reads it.
 *
 * Kept out of `./upstream` because that module is `server-only`: the browser needs these names and
 * must not reach the module that owns the connection and the token.
 */
export type FeedStatus = 'live' | 'reconnecting' | 'stopped'

export type FeedEvent =
  | { kind: 'detection'; seq: number; detection: unknown }
  | { kind: 'reset'; oldestSeq: number; lastSeq: number }
  | { kind: 'status'; status: FeedStatus }
