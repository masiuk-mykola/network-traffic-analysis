from collections.abc import Mapping, Sequence

from capture_api.domain.models import DecoderVersion, ProtocolName, ProtocolSchema, SchemaField

ALL_DECODERS: tuple[DecoderVersion, ...] = ("v1", "v2")


def _f(
    path: str,
    title: str,
    type_: str,
    *,
    unit: str | None = None,
    sensitive: bool = False,
) -> SchemaField:
    return SchemaField(
        path=path,
        title=title,
        type=type_,
        unit=unit,
        sensitive=True if sensitive else None,
    )


def _record_fields(prefix: str, title_prefix: str) -> list[SchemaField]:
    return [
        _f(f"{prefix}.name", f"{title_prefix} name", "string"),
        _f(f"{prefix}.type", f"{title_prefix} type", "string"),
        _f(f"{prefix}.ttl", f"{title_prefix} TTL", "number", unit="seconds"),
        _f(f"{prefix}.data", f"{title_prefix} data", "string"),
    ]


def _body_fields(prefix: str, title_prefix: str) -> list[SchemaField]:
    return [
        _f(f"{prefix}.length", f"{title_prefix} length", "number", unit="bytes"),
        _f(f"{prefix}.content_type", f"{title_prefix} content type", "string"),
        _f(f"{prefix}.preview", f"{title_prefix} preview", "string"),
        _f(f"{prefix}.truncated", f"{title_prefix} truncated", "boolean"),
    ]


def _header_fields(prefix: str, title_prefix: str) -> list[SchemaField]:
    return [
        _f(f"{prefix}.name", f"{title_prefix} name", "string"),
        _f(f"{prefix}.value", f"{title_prefix} value", "string", sensitive=True),
    ]


_DNS_FIELDS: list[SchemaField] = [
    _f("dns.transaction_id", "Transaction id", "number"),
    _f("dns.query.name", "Query name", "string"),
    _f("dns.query.type", "Query type", "string"),
    _f("dns.query.class", "Query class", "string"),
    _f("dns.rcode.code", "Response code", "number"),
    _f("dns.rcode.name", "Response code name", "string"),
    _f("dns.flags.qr", "Response flag", "boolean"),
    _f("dns.flags.aa", "Authoritative answer", "boolean"),
    _f("dns.flags.tc", "Truncated", "boolean"),
    _f("dns.flags.rd", "Recursion desired", "boolean"),
    _f("dns.flags.ra", "Recursion available", "boolean"),
    *_record_fields("dns.answers[]", "Answer"),
    *_record_fields("dns.authority[]", "Authority"),
    *_record_fields("dns.additional[]", "Additional"),
]

_HTTP_FIELDS: list[SchemaField] = [
    _f("http.method", "Method", "string"),
    _f("http.host", "Host", "string"),
    _f("http.path", "Path", "string"),
    _f("http.version", "Protocol version", "string"),
    _f("http.status", "Status code", "number"),
    *_header_fields("http.request_headers[]", "Request header"),
    *_header_fields("http.response_headers[]", "Response header"),
    *_body_fields("http.request_body", "Request body"),
    *_body_fields("http.response_body", "Response body"),
    _f("http.user_agent", "User agent", "string"),
    _f("http.file_ids[]", "Carved file id", "string"),
]

_TLS_FIELDS: list[SchemaField] = [
    _f("tls.version", "Negotiated version", "string"),
    _f("tls.sni", "Server name", "string"),
    _f("tls.alpn[]", "ALPN protocol", "string"),
    _f("tls.ja3", "JA3", "hash"),
    _f("tls.ja3s", "JA3S", "hash"),
    _f("tls.ja3_string", "JA3 string", "string"),
    _f("tls.ciphers_offered[]", "Cipher offered", "string"),
    _f("tls.cipher_chosen", "Cipher chosen", "string"),
    _f("tls.certificate_chain[].subject_cn", "Certificate subject CN", "string"),
    _f("tls.certificate_chain[].subject", "Certificate subject", "string"),
    _f("tls.certificate_chain[].issuer", "Certificate issuer", "string"),
    _f("tls.certificate_chain[].serial", "Certificate serial", "string"),
    _f("tls.certificate_chain[].not_before", "Valid from", "string"),
    _f("tls.certificate_chain[].not_after", "Valid until", "string"),
    _f("tls.certificate_chain[].self_signed", "Self-signed", "boolean"),
    _f("tls.certificate_chain[].sha256", "Certificate SHA-256", "hash"),
    _f("tls.resumed", "Session resumed", "boolean"),
]

_SMTP_FIELDS: list[SchemaField] = [
    _f("smtp.helo", "HELO/EHLO name", "string"),
    _f("smtp.mail_from", "Envelope sender", "string"),
    _f("smtp.rcpt_to[]", "Envelope recipient", "string", sensitive=True),
    _f("smtp.subject", "Subject", "string"),
    *_header_fields("smtp.headers[]", "Message header"),
    _f("smtp.attachments[].file_id", "Attachment file id", "string"),
    _f("smtp.attachments[].name", "Attachment name", "string"),
    _f("smtp.attachments[].size", "Attachment size", "number", unit="bytes"),
    _f("smtp.attachments[].sha256", "Attachment SHA-256", "hash"),
    _f("smtp.starttls", "STARTTLS used", "boolean"),
]

_SMB2_FIELDS: list[SchemaField] = [
    _f("smb2.dialect", "Dialect", "string"),
    _f("smb2.user", "User", "string", sensitive=True),
    _f("smb2.domain", "Domain", "string"),
    _f("smb2.tree", "Tree", "string"),
    _f("smb2.operations[].cmd", "Command", "string"),
    _f("smb2.operations[].path", "Path", "string"),
    _f("smb2.operations[].status", "NT status", "string"),
    _f("smb2.operations[].bytes", "Bytes", "string", unit="bytes"),
    _f("smb2.operations[].request_ts", "Request time", "timestamp"),
    _f("smb2.operations[].response_ts", "Response time", "timestamp"),
]

_SSH_FIELDS: list[SchemaField] = [
    _f("ssh.client_version", "Client version", "string"),
    _f("ssh.server_version", "Server version", "string"),
    _f("ssh.hassh", "HASSH", "hash"),
    _f("ssh.hassh_server", "HASSH server", "hash"),
    _f("ssh.kex_algorithms[]", "Key exchange algorithm", "string"),
    _f("ssh.host_key_type", "Host key type", "string"),
    _f("ssh.auth_attempts", "Authentication attempts", "number"),
]

_NTP_FIELDS: list[SchemaField] = [
    _f("ntp.version", "Version", "number"),
    _f("ntp.mode", "Mode", "number"),
    _f("ntp.stratum", "Stratum", "number"),
    _f("ntp.ref_id", "Reference id", "string"),
    _f("ntp.poll", "Poll interval", "number"),
]

_TCP_FIELDS: list[SchemaField] = [
    _f("tcp.flags_seen[]", "TCP flag seen", "string"),
    _f("tcp.first_payload_hex", "First payload bytes", "hex"),
    _f("tcp.retransmits", "Retransmissions", "number"),
]

_FIELDS: Mapping[ProtocolName, Sequence[SchemaField]] = {
    "dns": _DNS_FIELDS,
    "http": _HTTP_FIELDS,
    "tls": _TLS_FIELDS,
    "smtp": _SMTP_FIELDS,
    "smb2": _SMB2_FIELDS,
    "ssh": _SSH_FIELDS,
    "ntp": _NTP_FIELDS,
    "tcp": _TCP_FIELDS,
}

UNDECLARED_PATHS: tuple[str, ...] = (
    "tls.ja4",
    "http.x_forwarded_for",
    "dns.edns.client_subnet",
)
"""Emitted by the decoder, absent from every schema — on purpose."""

SCHEMA_PROTOCOLS: tuple[ProtocolName, ...] = (
    "dns",
    "http",
    "tls",
    "smtp",
    "smb2",
    "ssh",
    "ntp",
    "tcp",
)

PROTOCOL_SCHEMAS: Mapping[str, ProtocolSchema] = {
    protocol: ProtocolSchema(
        protocol=protocol,
        decoder_versions=list(ALL_DECODERS),
        fields=list(_FIELDS[protocol]),
    )
    for protocol in SCHEMA_PROTOCOLS
}


def protocol_schema(protocol: str) -> ProtocolSchema | None:
    return PROTOCOL_SCHEMAS.get(protocol)


def declared_paths(protocol: str) -> tuple[str, ...]:
    schema = PROTOCOL_SCHEMAS.get(protocol)
    return tuple(item.path for item in schema.fields) if schema else ()
