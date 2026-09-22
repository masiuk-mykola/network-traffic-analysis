import { describe, expect, it } from 'vitest'

import { parseSse, type SseFrame } from './sse'

const encoder = new TextEncoder()

/** Feeds the parser the given chunks and collects every frame it produced. */
function frames(...chunks: string[]): SseFrame[] {
  const parser = parseSse()
  const out: SseFrame[] = []
  for (const chunk of chunks) out.push(...parser.push(encoder.encode(chunk)))
  out.push(...parser.end())
  return out
}

describe('parseSse', () => {
  it('reads the frame the server opens with', () => {
    // `: open last_seq=12` and `retry: 3000` — a comment and a hint, not a detection.
    expect(frames(': open last_seq=12\nretry: 3000\n\n')).toEqual([
      { comment: 'open last_seq=12', event: null, id: null, data: '', retryMs: 3_000 },
    ])
  })

  it('reads a detection with its id and event name', () => {
    expect(frames('id: 41\nevent: detection\ndata: {"seq":41}\n\n')).toEqual([
      { comment: null, event: 'detection', id: '41', data: '{"seq":41}', retryMs: null },
    ])
  })

  it('joins a data field split over several lines', () => {
    expect(frames('event: reset\ndata: {"a":1,\ndata: "b":2}\n\n')[0]?.data).toBe('{"a":1,\n"b":2}')
  })

  it('holds a frame split across chunks until it is whole', () => {
    const parser = parseSse()
    expect(parser.push(encoder.encode('id: 7\nevent: det'))).toEqual([])
    expect(parser.push(encoder.encode('ection\ndata: x\n'))).toEqual([])

    const done = parser.push(encoder.encode('\n'))
    expect(done).toHaveLength(1)
    expect(done[0]).toMatchObject({ id: '7', event: 'detection', data: 'x' })
  })

  it('holds a multi-byte character split across chunks', () => {
    // A detection summary can carry any UTF-8; a naive per-chunk decode would corrupt it.
    const bytes = encoder.encode('data: ä\n\n')
    const parser = parseSse()
    parser.push(bytes.slice(0, 7))
    const rest = parser.push(bytes.slice(7))

    expect(rest[0]?.data).toBe('ä')
  })

  it('accepts CRLF as well as LF', () => {
    expect(frames('id: 3\r\nevent: detection\r\ndata: x\r\n\r\n')[0]).toMatchObject({
      id: '3',
      event: 'detection',
      data: 'x',
    })
  })

  it('accepts a field with no space after the colon, and one with no value', () => {
    expect(frames('event:detection\ndata:x\n\n')[0]).toMatchObject({
      event: 'detection',
      data: 'x',
    })
    expect(frames('data\n\n')[0]?.data).toBe('')
  })

  it('reads several frames out of one chunk', () => {
    const out = frames('id: 1\ndata: a\n\nid: 2\ndata: b\n\n')
    expect(out.map((frame) => frame.id)).toEqual(['1', '2'])
  })

  it('ignores a retry that is not a number', () => {
    expect(frames('retry: soon\ndata: x\n\n')[0]?.retryMs).toBeNull()
  })

  it('gives up a partial frame at the end of the stream rather than inventing one', () => {
    // A rotation can cut the stream mid-frame. Half a detection is not a detection.
    const parser = parseSse()
    parser.push(encoder.encode('id: 9\nevent: detection\ndata: {"seq"'))

    expect(parser.end()).toEqual([])
  })

  it('produces nothing from an empty stream', () => {
    expect(frames('')).toEqual([])
  })

  it('ignores a field the server never sends', () => {
    expect(frames('unknown: x\ndata: y\n\n')[0]).toMatchObject({ data: 'y' })
  })
})
