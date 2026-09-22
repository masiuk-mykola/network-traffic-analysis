/**
 * Server-sent events, as bytes arrive.
 *
 * Not `server-only`: this is a pure parser with no access to anything, and keeping it free of that
 * import is what lets it be tested on its own. The stream it parses is opened on the server.
 *
 * A stream arrives in chunks that have nothing to do with where frames end — one frame can span
 * three chunks, and one chunk can carry three frames — so the parser holds what it has and hands
 * back only whole frames. A multi-byte character split across a chunk boundary is held too, which
 * is why decoding is streaming rather than per chunk.
 */
export type SseFrame = {
  /** A line starting with `:` — the server opens the feed with one. */
  comment: string | null
  event: string | null
  id: string | null
  data: string
  retryMs: number | null
}

export type SseParser = {
  /** Whole frames completed by these bytes. */
  push: (chunk: Uint8Array) => SseFrame[]
  /** The stream ended: a frame left half-written is dropped, never guessed at. */
  end: () => SseFrame[]
}

export function parseSse(): SseParser {
  const decoder = new TextDecoder()
  let buffer = ''

  function drain(): SseFrame[] {
    const out: SseFrame[] = []
    // A blank line ends a frame. \r\n\r\n and \n\n both count, and so does the mixture.
    const blank = /\r?\n\r?\n/
    let match = blank.exec(buffer)
    while (match) {
      const block = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      const frame = readFrame(block)
      if (frame) out.push(frame)
      match = blank.exec(buffer)
    }
    return out
  }

  return {
    push(chunk) {
      buffer += decoder.decode(chunk, { stream: true })
      return drain()
    },
    end() {
      buffer += decoder.decode()
      // Whatever is left has no blank line after it, so it is half a frame. Drop it.
      buffer = ''
      return []
    },
  }
}

function readFrame(block: string): SseFrame | null {
  if (block.length === 0) return null

  const data: string[] = []
  let comment: string | null = null
  let event: string | null = null
  let id: string | null = null
  let retryMs: number | null = null

  for (const line of block.split(/\r?\n/)) {
    if (line.length === 0) continue
    if (line.startsWith(':')) {
      comment = line.slice(1).trim()
      continue
    }

    const [field, value] = splitField(line)
    if (field === 'data') data.push(value)
    else if (field === 'event') event = value
    else if (field === 'id') id = value
    else if (field === 'retry') retryMs = readRetry(value)
    // Any other field is one this server does not send; ignoring it is what the format asks for.
  }

  return { comment, event, id, data: data.join('\n'), retryMs }
}

/** `field: value`, `field:value` and a bare `field` are all legal. */
function splitField(line: string): [string, string] {
  const colon = line.indexOf(':')
  if (colon === -1) return [line, '']
  const value = line.slice(colon + 1)
  return [line.slice(0, colon), value.startsWith(' ') ? value.slice(1) : value]
}

function readRetry(value: string): number | null {
  const ms = Number(value)
  return Number.isInteger(ms) && ms >= 0 ? ms : null
}
