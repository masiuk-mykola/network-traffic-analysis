/**
 * One DNS exchange, read out of a decoded transaction.
 *
 * The contract types the decoded payload as a free-form object and the two decoder generations in
 * this capture disagree about shape: the older one quotes numbers as text, gives the response code
 * as a bare number, and carries a single record where the canonical one carries a list. This is the
 * only place that reconciles them; everything downstream sees one shape.
 */
export type DnsRecord = {
  name: string
  type: string
  ttl: number | null
  data: string | null
}

export type DnsExchange = {
  transactionId: string | null
  query: { name: string; type: string; class: string | null } | null
  /** The name where one is known, the number where it is not, and nothing where none was given. */
  responseCode: { code: number | null; name: string }
  /** The names of the flags that are set; a flag the decoder omits is simply not set. */
  flags: string[]
  answers: DnsRecord[]
  authority: DnsRecord[]
  additional: DnsRecord[]
}

const CODES: Record<number, string> = {
  0: 'NOERROR',
  1: 'FORMERR',
  2: 'SERVFAIL',
  3: 'NXDOMAIN',
  4: 'NOTIMP',
  5: 'REFUSED',
  6: 'YXDOMAIN',
  7: 'YXRRSET',
  8: 'NXRRSET',
  9: 'NOTAUTH',
  10: 'NOTZONE',
}

const FLAGS: Array<[string, string]> = [
  ['qr', 'response'],
  ['aa', 'authoritative'],
  ['tc', 'truncated'],
  ['rd', 'recursion desired'],
  ['ra', 'recursion available'],
]

export function readDnsExchange(decoded: unknown): DnsExchange | null {
  const dns = read(decoded, 'dns')
  if (!isRecord(dns)) return null

  return {
    transactionId: asText(dns.transaction_id),
    query: readQuery(dns.query),
    responseCode: readCode(dns.rcode),
    flags: FLAGS.filter(([key]) => read(dns.flags, key) === true).map(([, label]) => label),
    answers: readRecords(dns.answers),
    authority: readRecords(dns.authority),
    additional: readRecords(dns.additional),
  }
}

function readQuery(value: unknown): DnsExchange['query'] {
  if (!isRecord(value)) return null

  const name = asText(value.name)
  if (name === null) return null
  return { name, type: asText(value.type) ?? '', class: asText(value.class) }
}

function readCode(value: unknown): DnsExchange['responseCode'] {
  if (isRecord(value)) {
    const code = asNumber(value.code)
    const named = asText(value.name)
    return { code, name: named ?? (code === null ? '' : nameOf(code)) }
  }

  const code = asNumber(value)
  return code === null ? { code: null, name: '' } : { code, name: nameOf(code) }
}

function nameOf(code: number): string {
  return CODES[code] ?? String(code)
}

/** A record set arrives as a list, or — from the older decoder — as the one record itself. */
function readRecords(value: unknown): DnsRecord[] {
  const items = Array.isArray(value) ? value : isRecord(value) ? [value] : []

  return items.filter(isRecord).map((item) => ({
    name: asText(item.name) ?? '',
    type: asText(item.type) ?? '',
    ttl: asNumber(item.ttl),
    data: asText(item.data),
  }))
}

function read(value: unknown, key: string): unknown {
  return isRecord(value) ? value[key] : undefined
}

function asText(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

/** The older decoder quotes numbers; nothing that is not a number becomes one. */
function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string' || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
