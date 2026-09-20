import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate
from typing import Any

from capture_api.domain.base import ms_to_iso
from capture_api.domain.models import ProtocolSchema
from capture_api.world import der, schemas
from capture_api.world import files as carved
from capture_api.world import pcap as pcap_writer
from capture_api.world.catalog import DNS_RCODES
from capture_api.world.enrich_data import enrich_ip
from capture_api.world.flows import flow_samples
from capture_api.world.rng import Stream
from capture_api.world.ssh_profiles import (
    SSH_CLIENT_PROFILES,
    SSH_SERVER_PROFILES,
    SshProfile,
    ssh_client_by_hassh,
)
from capture_api.world.tls_profiles import (
    BACKGROUND_CLIENT_PROFILES,
    GENERAL_SERVER_STACKS,
    SERVER_STACKS,
    TLS13,
    TlsClientProfile,
    TlsServerProfile,
    server_hello,
    stack_for_host,
)
from capture_api.world.types import (
    DecodeContext,
    EnrichData,
    EvidenceEngine,
    FlowSampleData,
    Role,
    Row,
)

REDACTED: Mapping[str, bool] = {"redacted": True}

JA4_UNDECLARED_RATE = 0.5
XFF_UNDECLARED_RATE = 0.25
EDNS_UNDECLARED_RATE = 0.1

MAX_BODY_PREVIEW = 2048
MAX_TCP_PAYLOAD_BYTES = 64

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "set-cookie"})

_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/141.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0 Safari/537.36",
    "FreightSync/2.4 (+https://quillmere.example/agent)",
    "curl/8.9.1",
)

_NTP_REF_IDS: tuple[str, ...] = ("GPS", "PPS", "DCFa", "PTP0", "NIST")
_TCP_FLAG_SETS: tuple[tuple[str, ...], ...] = (
    ("SYN", "SYN-ACK", "ACK", "PSH", "FIN"),
    ("SYN", "SYN-ACK", "ACK", "RST"),
    ("SYN", "ACK", "PSH", "ACK", "FIN", "ACK"),
)


def openssl_date(ms: int) -> str:
    moment = datetime.fromtimestamp(ms // 1000, UTC)
    return (
        f"{_MONTHS[moment.month - 1]} {moment.day:2d} "
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d} {moment.year} GMT"
    )


def ja4_fingerprint(profile: TlsClientProfile, *, sni_present: bool = True) -> str:
    version = profile.max_version
    version_code = {0x0304: "13", 0x0303: "12", 0x0302: "11", 0x0301: "10"}.get(version, "12")
    alpn = profile.alpn[0] if profile.alpn else ""
    alpn_code = f"{alpn[0]}{alpn[-1]}" if alpn else "00"
    head = (
        f"t{version_code}{'d' if sni_present else 'i'}"
        f"{min(99, len(profile.ciphers)):02d}{min(99, len(profile.extensions)):02d}{alpn_code}"
    )
    ciphers = ",".join(f"{code:04x}" for code in sorted(profile.ciphers))
    declared = (code for code in sorted(profile.extensions) if code not in {0, 16})
    extensions = ",".join(f"{code:04x}" for code in declared)
    signatures = ",".join(f"{code:04x}" for code in profile.signature_algorithms)
    digest_b = hashlib.sha256(ciphers.encode()).hexdigest()[:12]
    digest_c = hashlib.sha256(f"{extensions}_{signatures}".encode()).hexdigest()[:12]
    return f"{head}_{digest_b}_{digest_c}"


def _attr_tuple(row: Row, key: str) -> tuple[str, ...]:
    value = row.attr(key)
    return value if isinstance(value, tuple) else ()


def _attr_int(row: Row, key: str, fallback: int) -> int:
    value = row.attr(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return fallback


def _network_prefix(ip: str) -> str:
    if ":" in ip:
        return f"{':'.join(ip.split(':')[:3])}::/48"
    return f"{'.'.join(ip.split('.')[:3])}.0/24"


def _dns_answer_type(query_type: str, data: str) -> str:
    if ":" in data:
        return "AAAA"
    if data.replace(".", "").isdigit() and data.count(".") == 3:
        return "A" if query_type in {"A", "AAAA"} else query_type
    return "CNAME" if query_type in {"A", "AAAA"} else query_type


def _dns_payload(row: Row, stream: Stream) -> dict[str, Any]:
    name = row.attr_str("dns.query.name") or "unknown.invalid"
    query_type = row.attr_str("dns.query.type") or "A"
    rcode_name = row.attr_str("dns.rcode") or "NOERROR"
    ttl = _attr_int(row, "dns.ttl", 300)
    answers = [
        {
            "name": name,
            "type": _dns_answer_type(query_type, data),
            "ttl": ttl,
            "data": data,
        }
        for data in _attr_tuple(row, "dns.answer")
    ]
    zone = name.split(".", 1)[1] if "." in name else name
    authority: list[dict[str, Any]] = []
    additional: list[dict[str, Any]] = []
    if not answers:
        authority.append(
            {
                "name": zone,
                "type": "SOA",
                "ttl": 3600,
                "data": f"ns1.{zone} hostmaster.{zone} 2025102701 7200 1800 1209600 300",
            }
        )
    elif query_type in {"MX", "NS", "SRV"}:
        glue = stream.fork("glue")
        additional.extend(
            {
                "name": str(answer["data"]).split(" ")[-1],
                "type": "A",
                "ttl": ttl,
                "data": f"192.0.2.{glue.randint(2, 250)}",
            }
            for answer in answers
        )
    payload: dict[str, Any] = {
        "transaction_id": stream.bits(16),
        "query": {"name": name, "type": query_type, "class": "IN"},
        "rcode": {"code": DNS_RCODES.get(rcode_name, 0), "name": rcode_name},
        "flags": {
            "qr": True,
            "aa": stream.chance(0.12),
            "tc": False,
            "rd": True,
            "ra": True,
        },
        "answers": answers,
        "authority": authority,
        "additional": additional,
    }
    if stream.fork("edns").chance(EDNS_UNDECLARED_RATE):
        payload["edns"] = {"client_subnet": _network_prefix(row.src_ip)}
    return payload


def _http_request_headers(row: Row, stream: Stream, host: str, agent: str) -> list[dict[str, str]]:
    headers = [
        {"name": "Host", "value": host},
        {"name": "User-Agent", "value": agent},
        {"name": "Accept", "value": "*/*"},
        {"name": "Accept-Encoding", "value": "gzip, deflate"},
        {"name": "Connection", "value": "keep-alive"},
    ]
    if stream.chance(0.18):
        token = stream.fork("basic").hex(24)
        headers.append({"name": "Authorization", "value": f"Basic {token}"})
    if stream.chance(0.35):
        headers.append({"name": "Cookie", "value": f"sid={stream.fork('sid').hex(32)}"})
    if row.dst_port not in {80, 8080}:
        headers.append({"name": "X-Request-Port", "value": str(row.dst_port)})
    return headers


def _http_response_headers(row: Row, stream: Stream) -> list[dict[str, str]]:
    headers = [
        {"name": "Date", "value": formatdate(row.end_ms / 1000, usegmt=True)},
        {"name": "Server", "value": "edge/1.24"},
        {"name": "Content-Type", "value": "application/octet-stream"},
        {"name": "Content-Length", "value": str(max(0, row.bytes_down - 256))},
    ]
    if stream.chance(0.3):
        session = stream.fork("set-cookie")
        age = session.randint(600, 86400)
        headers.append({"name": "Set-Cookie", "value": f"sid={session.hex(32)}; Path=/; HttpOnly"})
        headers.append({"name": "Set-Cookie", "value": f"lang=en; Path=/; Max-Age={age}"})
    return headers


def _http_body(stream: Stream, length: int, content_type: str) -> dict[str, Any]:
    if length <= 0:
        return {"length": 0, "content_type": content_type, "preview": "", "truncated": False}
    preview_len = min(length, MAX_BODY_PREVIEW)
    preview = stream.hex(min(256, preview_len * 2))
    return {
        "length": length,
        "content_type": content_type,
        "preview": preview,
        "truncated": length > MAX_BODY_PREVIEW,
    }


def _http_payload(ctx: DecodeContext, row: Row, stream: Stream) -> dict[str, Any]:
    host = row.attr_str("http.host") or row.dst_ip
    method = row.attr_str("http.method") or "GET"
    path = row.attr_str("http.path") or "/"
    status = _attr_int(row, "http.status", 200)
    agent = row.attr_str("http.user_agent") or stream.choice(_USER_AGENTS)
    uploads = method in {"POST", "PUT", "PATCH"}
    payload: dict[str, Any] = {
        "method": method,
        "host": host,
        "path": path,
        "version": "HTTP/1.1",
        "status": status,
        "request_headers": _http_request_headers(row, stream, host, agent),
        "response_headers": _http_response_headers(row, stream),
        "request_body": _http_body(
            stream.fork("req-body"),
            max(0, row.bytes_up - 512) if uploads else 0,
            "application/octet-stream" if uploads else "",
        ),
        "response_body": _http_body(
            stream.fork("res-body"),
            max(0, row.bytes_down - 256),
            "application/octet-stream",
        ),
        "user_agent": agent,
        "file_ids": [
            item.id for item in carved.files_for_row(ctx.seed, row) if item.source == "http_body"
        ],
    }
    if stream.fork("xff").chance(XFF_UNDECLARED_RATE):
        payload["x_forwarded_for"] = f"198.51.100.{stream.fork('xff-host').randint(2, 250)}"
    return payload


def _client_profile(ctx: DecodeContext, row: Row, stream: Stream) -> TlsClientProfile:
    ja3 = row.attr_str("tls.ja3")
    profile = ctx.tls_client_profile(ja3) if ja3 else None
    return profile or stream.choice(BACKGROUND_CLIENT_PROFILES)


def _server_profile(
    seed: str, sni: str, client: TlsClientProfile, wanted: str | None
) -> TlsServerProfile:
    try:
        preferred = server_hello(client, stack_for_host(seed, sni))
    except ValueError:
        preferred = server_hello(client, SERVER_STACKS["srv-minimal"])
    if wanted is None or preferred.version_name == wanted:
        return preferred
    for key in (*GENERAL_SERVER_STACKS, "srv-minimal"):
        try:
            candidate = server_hello(client, SERVER_STACKS[key])
        except ValueError:
            continue
        if candidate.version_name == wanted:
            return candidate
    return preferred


@dataclass(frozen=True, slots=True)
class _Certificate:
    view: dict[str, Any]
    der_bytes: bytes


def _certificate(
    row: Row,
    stream: Stream,
    *,
    subject_cn: str,
    issuer_cn: str,
    sni: str,
    days: int,
    is_ca: bool = False,
) -> _Certificate:
    serial = stream.bits(64) | (1 << 63)
    not_before = row.start_ms - stream.randint(1, 30) * 86_400_000
    not_after = not_before + days * 86_400_000
    spec = der.CertificateSpec(
        subject_cn=subject_cn,
        issuer_cn=issuer_cn,
        serial=serial,
        not_before_ms=not_before,
        not_after_ms=not_after,
        modulus=stream.bytes(256),
        signature=stream.bytes(256),
        subject_org=None if is_ca else "Quillmere Freight",
        issuer_org=None if subject_cn == issuer_cn else "Example Trust Services",
        san_dns=() if is_ca else (sni,),
        is_ca=is_ca,
    )
    der_bytes = der.certificate_der(spec)
    subject = f"CN={subject_cn}" if is_ca else f"CN={subject_cn}, O=Quillmere Freight"
    view = {
        "subject_cn": subject_cn,
        "subject": subject,
        "issuer": f"CN={issuer_cn}",
        "serial": f"{serial:016x}",
        "not_before": openssl_date(not_before),
        "not_after": openssl_date(not_after),
        "self_signed": subject_cn == issuer_cn,
        "sha256": hashlib.sha256(der_bytes).hexdigest(),
    }
    return _Certificate(view=view, der_bytes=der_bytes)


def _tls_payload(
    ctx: DecodeContext, row: Row, stream: Stream
) -> tuple[dict[str, Any], pcap_writer.TlsWire]:
    client = _client_profile(ctx, row, stream)
    host = ctx.host(row.dst_ip)
    sni = row.attr_str("tls.sni") or (host.hostname if host is not None else None) or row.dst_ip
    server = _server_profile(ctx.seed, sni, client, row.attr_str("tls.version"))
    subject_cn = row.attr_str("tls.cert_cn") or sni
    issuer_cn = row.attr_str("tls.cert_issuer") or subject_cn
    self_signed = subject_cn == issuer_cn
    leaf = _certificate(
        row,
        stream.fork("cert"),
        subject_cn=subject_cn,
        issuer_cn=issuer_cn,
        sni=sni,
        days=7 if self_signed else 365,
    )
    chain = [leaf]
    if not self_signed:
        chain.append(
            _certificate(
                row,
                stream.fork("cert-ca"),
                subject_cn=issuer_cn,
                issuer_cn=issuer_cn,
                sni=sni,
                days=3650,
                is_ca=True,
            )
        )
    alpn = [server.alpn] if server.alpn else list(client.alpn)
    payload: dict[str, Any] = {
        "version": server.version_name,
        "sni": sni,
        "alpn": alpn,
        "ja3": client.ja3,
        "ja3s": server.ja3s,
        "ja3_string": client.ja3_string,
        "ciphers_offered": list(client.cipher_names),
        "cipher_chosen": server.cipher_name,
        "certificate_chain": [item.view for item in chain],
        "resumed": server.selected_version == TLS13 and stream.fork("resumed").chance(0.2),
    }
    if stream.fork("ja4").chance(JA4_UNDECLARED_RATE):
        payload["ja4"] = ja4_fingerprint(client, sni_present=bool(sni))
    wire = pcap_writer.TlsWire(
        client=client,
        server=server,
        sni=sni,
        certificates=tuple(item.der_bytes for item in chain),
        label=f"tls|{row.id}",
    )
    return payload, wire


def _smtp_payload(ctx: DecodeContext, row: Row, stream: Stream) -> dict[str, Any]:
    mail_from = row.attr_str("smtp.mail_from") or "postmaster@example.org"
    recipients = list(_attr_tuple(row, "smtp.rcpt_to")) or ["postmaster@quillmere.example"]
    subject = row.attr_str("smtp.subject") or "(no subject)"
    domain = mail_from.split("@")[-1] if "@" in mail_from else "example.org"
    attachments = [
        {"file_id": item.id, "name": item.name, "size": item.size, "sha256": item.sha256}
        for item in carved.files_for_row(ctx.seed, row)
        if item.source == "smtp_attachment"
    ]
    headers = [
        {"name": "From", "value": mail_from},
        {"name": "To", "value": ", ".join(recipients)},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": formatdate(row.start_ms / 1000, usegmt=True)},
        {"name": "Message-ID", "value": f"<{stream.hex(24)}@{domain}>"},
        {"name": "MIME-Version", "value": "1.0"},
    ]
    return {
        "helo": f"mail.{domain}",
        "mail_from": mail_from,
        "rcpt_to": recipients,
        "subject": subject,
        "headers": headers,
        "attachments": attachments,
        "starttls": stream.chance(0.6),
    }


def _smb2_operation(
    cmd: str, path: str, status: str, *, size: int, start_ms: int, step_ms: int
) -> dict[str, Any]:
    return {
        "cmd": cmd,
        "path": path,
        "status": status,
        "bytes": str(size),
        "request_ts": ms_to_iso(start_ms),
        "response_ts": ms_to_iso(start_ms + step_ms),
    }


def _smb2_payload(ctx: DecodeContext, row: Row, stream: Stream) -> dict[str, Any]:
    tree = row.attr_str("smb2.tree") or "\\\\FS01\\share$"
    paths = _attr_tuple(row, "smb2.path")
    final_status = row.attr_str("smb2.status") or "STATUS_SUCCESS"
    host = ctx.host(row.src_ip)
    user = (host.user if host is not None and host.user else None) or f"svc.{stream.hex(6)}"
    step = max(1, row.duration_ms // (3 * len(paths) + 2))
    operations = [
        _smb2_operation(
            "TREE_CONNECT",
            tree,
            final_status if not paths else "STATUS_SUCCESS",
            size=0,
            start_ms=row.start_ms,
            step_ms=step,
        )
    ]
    cursor = row.start_ms + 2 * step
    read_bytes = max(1, row.bytes_down // max(1, len(paths)))
    for path in paths:
        for cmd, size in (("CREATE", 0), ("READ", read_bytes), ("CLOSE", 0)):
            operations.append(
                _smb2_operation(
                    cmd, path, "STATUS_SUCCESS", size=size, start_ms=cursor, step_ms=step
                )
            )
            cursor += step
    if paths:
        operations[-1]["status"] = final_status
    return {
        "dialect": "3.1.1",
        "user": user,
        "domain": "QUILLMERE",
        "tree": tree,
        "operations": operations,
    }


def _ssh_payload(row: Row, stream: Stream) -> tuple[dict[str, Any], pcap_writer.SshWire]:
    hassh = row.attr_str("ssh.hassh")
    client: SshProfile = (ssh_client_by_hassh(hassh) if hassh else None) or stream.choice(
        SSH_CLIENT_PROFILES
    )
    banner = row.attr_str("ssh.server_version")
    server = next(
        (profile for profile in SSH_SERVER_PROFILES if profile.version == banner),
        SSH_SERVER_PROFILES[0],
    )
    payload = {
        "client_version": client.version,
        "server_version": banner or server.version,
        "hassh": client.hassh,
        "hassh_server": server.hassh,
        "kex_algorithms": list(client.kex),
        "host_key_type": server.host_key_types[0],
        "auth_attempts": stream.randint(1, 3),
    }
    return payload, pcap_writer.SshWire(client=client, server=server)


def _ntp_payload(stream: Stream) -> dict[str, Any]:
    return {
        "version": 4,
        "mode": 3,
        "stratum": stream.randint(2, 3),
        "ref_id": stream.choice(_NTP_REF_IDS),
        "poll": stream.randint(6, 10),
    }


def _tcp_payload(row: Row, stream: Stream) -> dict[str, Any]:
    size = min(MAX_TCP_PAYLOAD_BYTES, max(4, row.bytes_up // 8))
    return {
        "flags_seen": list(stream.choice(_TCP_FLAG_SETS)),
        "first_payload_hex": stream.bytes(size).hex(),
        "retransmits": stream.randint(0, 3),
    }


def _v1_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, dict):
        return _v1_dict(value)
    if isinstance(value, list):
        items = [_v1_value(item) for item in value]
        return items[0] if len(items) == 1 else items
    return value


def _v1_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _v1_value(item) for key, item in value.items() if item is not False}


def _v1_headers(headers: Sequence[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for header in headers:
        if not isinstance(header, Mapping):
            continue
        name = str(header.get("name", ""))
        item = header.get("value", "")
        if name in out:
            existing = out[name]
            out[name] = [*existing, item] if isinstance(existing, list) else [existing, item]
        else:
            out[name] = item
    return out


def _v1_rewrite(protocol: str, payload: dict[str, Any]) -> dict[str, Any]:
    working = dict(payload)
    if protocol == "dns" and isinstance(working.get("rcode"), Mapping):
        working["rcode"] = str(working["rcode"].get("code", 0))
    if protocol == "http":
        for key in ("request_headers", "response_headers"):
            value = working.get(key)
            if isinstance(value, list):
                working[key] = _v1_headers(value)
    return _v1_dict(working)


def _redact_headers(value: Any) -> Any:
    if isinstance(value, list):
        return [
            {**header, "value": dict(REDACTED)}
            if isinstance(header, Mapping)
            and str(header.get("name", "")).lower() in _SENSITIVE_HEADERS
            else header
            for header in value
        ]
    if isinstance(value, dict):
        return {
            name: dict(REDACTED) if name.lower() in _SENSITIVE_HEADERS else item
            for name, item in value.items()
        }
    return value


def _redact(protocol: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if protocol == "http":
        for key in ("request_headers", "response_headers"):
            if key in out:
                out[key] = _redact_headers(out[key])
    elif protocol == "smtp" and "rcpt_to" in out:
        recipients = out["rcpt_to"]
        out["rcpt_to"] = (
            [dict(REDACTED) for _ in recipients] if isinstance(recipients, list) else dict(REDACTED)
        )
    elif protocol == "smb2" and "user" in out:
        out["user"] = dict(REDACTED)
    return out


@dataclass(frozen=True, slots=True)
class DecodedSession:
    payload: dict[str, Any]
    tls: pcap_writer.TlsWire | None = None
    ssh: pcap_writer.SshWire | None = None


class _Engine:
    __slots__ = ("_ctx",)

    def __init__(self, ctx: DecodeContext) -> None:
        self._ctx = ctx

    def canonical(self, row: Row) -> DecodedSession:
        ctx = self._ctx
        stream = Stream(ctx.seed, "decode", row.id)
        tls: pcap_writer.TlsWire | None = None
        ssh: pcap_writer.SshWire | None = None
        match row.protocol:
            case "dns":
                body: dict[str, Any] = _dns_payload(row, stream)
            case "http":
                body = _http_payload(ctx, row, stream)
            case "tls":
                body, tls = _tls_payload(ctx, row, stream)
            case "smtp":
                body = _smtp_payload(ctx, row, stream)
            case "smb2":
                body = _smb2_payload(ctx, row, stream)
            case "ssh":
                body, ssh = _ssh_payload(row, stream)
            case "ntp":
                body = _ntp_payload(stream)
            case _:
                body = _tcp_payload(row, stream)
        return DecodedSession(payload={row.protocol: body}, tls=tls, ssh=ssh)

    def decode(self, row: Row, role: Role) -> dict[str, Any]:
        body = dict(self.canonical(row).payload[row.protocol])
        sensor = self._ctx.sensor(row.sensor_id)
        if sensor is not None and sensor.decoder_version == "v1":
            body = _v1_rewrite(row.protocol, body)
        if role == "observer":
            body = _redact(row.protocol, body)
        return {row.protocol: body}

    def flow(self, row: Row, bucket_ms: int) -> Sequence[FlowSampleData]:
        return flow_samples(row, bucket_ms, seed=self._ctx.seed)

    def pcap(self, row: Row) -> bytes:
        decoded = self.canonical(row)
        return pcap_writer.build_pcap(row, decoded.payload, tls=decoded.tls, ssh=decoded.ssh)

    def enrich(self, ip: str) -> EnrichData:
        incident = self._ctx.incident()
        flagged = (
            incident.c2_ip,
            incident.c2_upload_ip,
            incident.lookalike_sender_ip,
            incident.http_put_ip,
        )
        return enrich_ip(self._ctx.seed, ip, host=self._ctx.host(ip), flagged=flagged)

    def protocol_schema(self, protocol: str) -> ProtocolSchema | None:
        return schemas.protocol_schema(protocol)


def build_evidence_engine(ctx: DecodeContext) -> EvidenceEngine:
    return _Engine(ctx)
