from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from capture_api.world.background import (
    EPHEMERAL_HIGH,
    EPHEMERAL_LOW,
    HOUR_MS,
    MINUTE_MS,
    RowDraft,
    log_int,
    packets_for,
)
from capture_api.world.catalog import DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.network import (
    C2_IP_FIRST,
    C2_IP_LAST,
    SENDER_IP_FIRST,
    SENDER_IP_LAST,
    Network,
)
from capture_api.world.rng import Stream
from capture_api.world.tls_profiles import derive_c2_client_profile
from capture_api.world.types import AttrValue, FileSpec, IncidentParams, Outage, RowTag
from capture_api.world.users import mailbox

LOOKALIKE_BASE = "quillmere-freight.example"
LOOKALIKE_DOMAINS: tuple[str, ...] = (
    "quillmere-frieght.example",
    "quillrnere-freight.example",
    "quillmere-freiqht.example",
    "quilmere-freight.example",
    "quillmere-freighl.example",
)
C2_DOMAINS: tuple[str, ...] = (
    "cdn-metrics.test",
    "telemetry-sync.test",
    "static-assets-cdn.test",
    "update-check.test",
    "metrics-edge.test",
)
ATTACHMENT_NAMES: tuple[str, ...] = (
    "Frachtraten-Q3-Übersicht.xlsm",
    "Rechnung_Überfällig_2025.xlsm",
    "Tarifänderung-Oktober.xlsm",
    "Zollbescheid_Nachzahlung.xlsm",
)
XLSM_MIME = "application/vnd.ms-excel.sheet.macroEnabled.12"
MAIL_SUBJECT = "Überfällige Rechnung 20261 - Zahlungsaufforderung"

FINANCE_TREE = "\\\\FS01\\finance$"
DENIED_TREE = "\\\\FS01\\hr$"
INVOICE_FOLDER = "\\Invoices\\2026"
INVOICE_NAMES: tuple[str, ...] = (
    "rate-sheet",
    "invoice",
    "credit-note",
    "manifest",
    "clearance",
    "berth-fee",
    "demurrage",
)

BEACON_MIN_S, BEACON_MAX_S = 240, 420
BEACON_JITTER = 0.10
BEACON_DETECTION_FROM = 12
"""The beacon's periodicity is only confident from the 12th observation onward."""
BEACON_DEDUPE_MS = 30 * MINUTE_MS

CAPTURE_GAP_MINUTES = 15
CAPTURE_GAP_REASON = "capture card reset"

EXFIL_UPLOAD_SESSIONS = (300, 420)
EXFIL_UPLOAD_BYTES = (4_000_000, 6_000_000)
EXFIL_PUT_SESSIONS = (200, 300)
EXFIL_PUT_BYTES = (4_200_000, 5_600_000)

_HOUR = HOUR_MS


def build_params(seed: str, network: Network, epoch_ms: int) -> IncidentParams:
    stream = Stream(seed, "incident")
    patient_zero = stream.choice(network.branch_workstations)
    shift = int(stream.uniform(-4 * _HOUR, 4 * _HOUR))
    email_ms = epoch_ms - 61 * _HOUR + shift + _jitter(stream, 30)
    first_contact_ms = max(
        email_ms + 12 * MINUTE_MS, epoch_ms - 60 * _HOUR + shift + _jitter(stream, 30)
    )
    beacon_start_ms = first_contact_ms + stream.randint(2 * MINUTE_MS, 20 * MINUTE_MS)
    smb_start_ms = max(
        beacon_start_ms + 4 * _HOUR, epoch_ms - 40 * _HOUR + shift + _jitter(stream, 30)
    )
    exfil_start_ms = max(
        smb_start_ms + 40 * MINUTE_MS, epoch_ms - 38 * _HOUR + shift + _jitter(stream, 30)
    )
    exfil_end_ms = exfil_start_ms + int(stream.uniform(1.5 * _HOUR, 2.5 * _HOUR))
    gap_start_ms = max(
        exfil_end_ms + 4 * _HOUR, epoch_ms - 20 * _HOUR + shift + _jitter(stream, 60)
    )
    c2_ips = list(network.free_ips("203.0.113", C2_IP_FIRST, C2_IP_LAST))
    sender_ips = list(network.free_ips("198.51.100", SENDER_IP_FIRST, SENDER_IP_LAST))
    c2_ip, c2_upload_ip = stream.sample(c2_ips, 2)
    sender_ip, put_ip = stream.sample(sender_ips, 2)
    channel: Literal["https_upload", "http_put"] = (
        "https_upload" if stream.chance(0.5) else "http_put"
    )
    sessions, target_bytes = _exfil_size(stream, channel)
    return IncidentParams(
        seed=seed,
        patient_zero_ip=patient_zero.ip,
        patient_zero_host=patient_zero.hostname or patient_zero.ip,
        patient_zero_user=patient_zero.user or "unknown.user",
        lookalike_domain=stream.choice(LOOKALIKE_DOMAINS),
        lookalike_sender_ip=sender_ip,
        c2_domain=stream.choice(C2_DOMAINS),
        c2_ip=c2_ip,
        c2_upload_ip=c2_upload_ip,
        c2_client_profile=derive_c2_client_profile(stream),
        cert_cn=f"{stream.hex(4)}.invalid",
        beacon_interval_s=stream.randint(BEACON_MIN_S, BEACON_MAX_S),
        beacon_jitter=BEACON_JITTER,
        email_ms=email_ms,
        first_contact_ms=first_contact_ms,
        beacon_start_ms=beacon_start_ms,
        smb_start_ms=smb_start_ms,
        exfil_start_ms=exfil_start_ms,
        exfil_end_ms=exfil_end_ms,
        smb_file_count=stream.randint(1_100, 1_700),
        exfil_channel=channel,
        exfil_sessions=sessions,
        exfil_target_bytes=target_bytes,
        http_put_ip=put_ip,
        attachment_name=stream.choice(ATTACHMENT_NAMES),
        capture_gap_start_ms=gap_start_ms,
        capture_gap_end_ms=gap_start_ms + CAPTURE_GAP_MINUTES * MINUTE_MS,
    )


def _jitter(stream: Stream, minutes: int) -> int:
    return int(stream.uniform(-minutes * MINUTE_MS, minutes * MINUTE_MS))


def _exfil_size(stream: Stream, channel: Literal["https_upload", "http_put"]) -> tuple[int, int]:
    if channel == "https_upload":
        count = stream.randint(*EXFIL_UPLOAD_SESSIONS)
        return count, count * ((EXFIL_UPLOAD_BYTES[0] + EXFIL_UPLOAD_BYTES[1]) // 2)
    count = stream.randint(*EXFIL_PUT_SESSIONS)
    return count, count * ((EXFIL_PUT_BYTES[0] + EXFIL_PUT_BYTES[1]) // 2)


@dataclass(frozen=True, slots=True)
class BeaconSchedule:
    times: tuple[int, ...]
    firing: frozenset[int]


class Incident:
    __slots__ = (
        "_beacon_times",
        "_epoch_ms",
        "_firing",
        "_last_fire_ms",
        "_net",
        "_outage",
        "_params",
        "_seed",
        "_static",
    )

    def __init__(self, seed: str, network: Network, epoch_ms: int) -> None:
        self._seed = seed
        self._net = network
        self._epoch_ms = epoch_ms
        self._params = build_params(seed, network, epoch_ms)
        self._outage = Outage(
            sensor_id=HARBOR_BRANCH,
            start_ms=self._params.capture_gap_start_ms,
            end_ms=self._params.capture_gap_end_ms,
            reason=CAPTURE_GAP_REASON,
        )
        self._beacon_times: list[int] = []
        self._firing: set[int] = set()
        self._last_fire_ms = 0
        self._static: dict[tuple[str, int], list[RowDraft]] = {}
        for draft, sensor_id in (
            *((d, HQ_CORE) for d in self._email_rows()),
            *((d, HARBOR_BRANCH) for d in self._first_contact_rows()),
            *((d, DC_EAST) for d in self._smb_rows()),
            *((d, HARBOR_BRANCH) for d in self._exfil_rows()),
        ):
            hour = (draft.start_ms - epoch_ms) // _HOUR
            self._static.setdefault((sensor_id, hour), []).append(draft)

    @property
    def params(self) -> IncidentParams:
        return self._params

    def outages(self) -> Sequence[Outage]:
        return (self._outage,)

    def rows_for(self, sensor_id: str, hour_start_ms: int, hour_end_ms: int) -> list[RowDraft]:
        hour = (hour_start_ms - self._epoch_ms) // _HOUR
        drafts = list(self._static.get((sensor_id, hour), ()))
        if sensor_id == HARBOR_BRANCH:
            drafts.extend(self._beacon_rows(hour_start_ms, hour_end_ms))
        return drafts

    def beacons(self, until_ms: int) -> BeaconSchedule:
        self._extend_beacons(until_ms)
        return BeaconSchedule(tuple(self._beacon_times), frozenset(self._firing))

    def _extend_beacons(self, until_ms: int) -> None:
        params = self._params
        if not self._beacon_times:
            self._beacon_times.append(params.beacon_start_ms)
            self._consider_fire(0, params.beacon_start_ms)
        while self._beacon_times[-1] <= until_ms:
            index = len(self._beacon_times)
            stream = Stream(self._seed, "incident", "beacon", index)
            gap = stream.jitter(params.beacon_interval_s * 1000, params.beacon_jitter)
            self._beacon_times.append(self._beacon_times[-1] + int(gap))
            self._consider_fire(index, self._beacon_times[-1])

    def _consider_fire(self, index: int, ts_ms: int) -> None:
        if index < BEACON_DETECTION_FROM - 1:
            return
        if self._last_fire_ms and ts_ms - self._last_fire_ms < BEACON_DEDUPE_MS:
            return
        self._last_fire_ms = ts_ms
        self._firing.add(index)

    def _beacon_rows(self, hour_start_ms: int, hour_end_ms: int) -> list[RowDraft]:
        params = self._params
        if hour_end_ms <= params.beacon_start_ms:
            return []
        schedule = self.beacons(hour_end_ms)
        drafts: list[RowDraft] = []
        for index, start in enumerate(schedule.times):
            if not hour_start_ms <= start < hour_end_ms:
                continue
            stream = Stream(self._seed, "incident", "beacon-row", index)
            up = stream.randint(1_000, 1_250)
            down = stream.randint(2_900, 3_500)
            draft = RowDraft(
                start_ms=start,
                end_ms=start + stream.randint(700, 2_400),
                protocol="tls",
                transport="tcp",
                src_ip=params.patient_zero_ip,
                src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                dst_ip=params.c2_ip,
                dst_port=443,
                bytes_up=up,
                bytes_down=down,
                packets_up=packets_for(up, overhead=6),
                packets_down=packets_for(down, overhead=6),
                risk_score=stream.randint(70, 84),
                risk_reasons=("self_signed_cert", "cn_mismatch", "rare_domain"),
                summary=f"TLS1.2 {params.c2_sni}",
                attrs=self._c2_tls_attrs(params.c2_sni),
                tag="incident.beacon",
            )
            if index in schedule.firing:
                draft.attrs["detection.rule"] = ("periodic_tls_beacon",)
            drafts.append(draft)
        return drafts

    def _c2_tls_attrs(self, sni: str) -> dict[str, AttrValue]:
        params = self._params
        return {
            "tls.sni": sni,
            "tls.ja3": params.c2_client_profile.ja3,
            "tls.version": "TLS1.2",
            "tls.cert_cn": params.cert_cn,
            "tls.cert_issuer": params.cert_cn,
        }

    def _email_rows(self) -> list[RowDraft]:
        params = self._params
        stream = Stream(self._seed, "incident", "email")
        recipient = mailbox(params.patient_zero_user)
        spec = FileSpec(
            name=params.attachment_name,
            mime=XLSM_MIME,
            size=stream.randint(180_000, 420_000),
            source="smtp_attachment",
        )
        up = spec.size + stream.randint(3_400, 9_000)
        return [
            RowDraft(
                start_ms=params.email_ms,
                end_ms=params.email_ms + stream.randint(2_000, 9_000),
                protocol="smtp",
                transport="tcp",
                src_ip=params.lookalike_sender_ip,
                src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                dst_ip=self._net.mail_gateway.ip,
                dst_port=25,
                bytes_up=up,
                bytes_down=stream.randint(500, 1_400),
                packets_up=packets_for(up),
                packets_down=6,
                risk_score=stream.randint(58, 72),
                risk_reasons=("lookalike_domain",),
                summary=f"SMTP {params.sender} → {recipient} (1 attachment)",
                attrs={
                    "smtp.mail_from": params.sender,
                    "smtp.rcpt_to": (recipient,),
                    "smtp.subject": MAIL_SUBJECT,
                    "smtp.attachment.sha256": (),
                    "detection.rule": ("lookalike_sender",),
                },
                files=(spec,),
                tag="incident.email",
            )
        ]

    def _first_contact_rows(self) -> list[RowDraft]:
        params = self._params
        stream = Stream(self._seed, "incident", "first-contact")
        rows = [
            self._dns_row(stream, params.first_contact_ms, params.c2_sni, answers=(params.c2_ip,))
        ]
        for offset in (stream.randint(6_000, 14_000), stream.randint(18_000, 40_000)):
            label = Stream(self._seed, "incident", "nx", offset).hex(8)
            rows.append(
                self._dns_row(
                    stream,
                    params.first_contact_ms + offset,
                    f"{label}.{params.c2_domain}",
                    rcode="NXDOMAIN",
                )
            )
        return rows

    def _dns_row(
        self,
        stream: Stream,
        start_ms: int,
        name: str,
        *,
        qtype: str = "A",
        rcode: str = "NOERROR",
        answers: tuple[str, ...] = (),
        ttl: int = 60,
    ) -> RowDraft:
        up = stream.randint(64, 96)
        reasons = ("rare_domain",) if rcode == "NOERROR" else ("rare_domain", "nxdomain_burst")
        return RowDraft(
            start_ms=start_ms,
            end_ms=start_ms + stream.randint(4, 60),
            protocol="dns",
            transport="udp",
            src_ip=self._params.patient_zero_ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=self._net.resolver.ip,
            dst_port=53,
            bytes_up=up,
            bytes_down=up + stream.randint(12, 60),
            packets_up=1,
            packets_down=1,
            risk_score=stream.randint(46, 64),
            risk_reasons=reasons,
            summary=f"{qtype} {name} → {answers[0]}" if answers else f"{rcode} {name}",
            attrs={
                "dns.query.name": name,
                "dns.query.type": qtype,
                "dns.rcode": rcode,
                "dns.answer": answers,
                "dns.ttl": ttl,
            },
            tag="incident.first_contact",
        )

    def _smb_rows(self) -> list[RowDraft]:
        params = self._params
        stream = Stream(self._seed, "incident", "smb")
        fs01 = self._net.server("fs01")
        window = 20 * MINUTE_MS
        drafts: list[RowDraft] = []
        for index in range(params.smb_file_count):
            start = params.smb_start_ms + index * window // params.smb_file_count
            size = log_int(stream, 60_000, 4_000_000)
            up = stream.randint(900, 2_400)
            name = f"{stream.choice(INVOICE_NAMES)}-{stream.hex(6)}.pdf"
            draft = RowDraft(
                start_ms=start,
                end_ms=start + stream.randint(40, 900),
                protocol="smb2",
                transport="tcp",
                src_ip=params.patient_zero_ip,
                src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                dst_ip=fs01.ip,
                dst_port=445,
                bytes_up=up,
                bytes_down=size,
                packets_up=packets_for(up),
                packets_down=packets_for(size),
                risk_score=stream.randint(38, 58),
                risk_reasons=("smb_mass_read",),
                summary=f"SMB2 READ {FINANCE_TREE}{INVOICE_FOLDER}\\{name}",
                attrs={
                    "smb2.tree": FINANCE_TREE,
                    "smb2.path": (f"{INVOICE_FOLDER}\\{name}",),
                    "smb2.status": "STATUS_SUCCESS",
                },
                tag="incident.smb",
            )
            if index == 0:
                draft.attrs["detection.rule"] = ("smb_mass_read",)
                draft.risk_score = stream.randint(74, 88)
            drafts.append(draft)
        drafts.append(self._denied_row(stream, fs01.ip))
        return drafts

    def _denied_row(self, stream: Stream, fs01_ip: str) -> RowDraft:
        start = self._params.smb_start_ms + stream.randint(30 * 1000, 18 * MINUTE_MS)
        return RowDraft(
            start_ms=start,
            end_ms=start + stream.randint(20, 300),
            protocol="smb2",
            transport="tcp",
            src_ip=self._params.patient_zero_ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=fs01_ip,
            dst_port=445,
            bytes_up=520,
            bytes_down=310,
            packets_up=5,
            packets_down=5,
            risk_score=stream.randint(52, 66),
            risk_reasons=("smb_mass_read",),
            summary=f"SMB2 TREE_CONNECT {DENIED_TREE} → STATUS_ACCESS_DENIED",
            attrs={
                "smb2.tree": DENIED_TREE,
                "smb2.path": (),
                "smb2.status": "STATUS_ACCESS_DENIED",
            },
            tag="incident.smb_denied",
        )

    def _exfil_rows(self) -> list[RowDraft]:
        params = self._params
        stream = Stream(self._seed, "incident", "exfil")
        span = max(1, params.exfil_end_ms - params.exfil_start_ms)
        drafts: list[RowDraft] = []
        for index in range(params.exfil_sessions):
            start = params.exfil_start_ms + index * span // params.exfil_sessions
            if params.exfil_channel == "https_upload":
                drafts.append(self._upload_row(stream, start))
            else:
                drafts.append(self._put_row(stream, start))
        return drafts

    def _upload_row(self, stream: Stream, start: int) -> RowDraft:
        params = self._params
        up = stream.randint(*EXFIL_UPLOAD_BYTES)
        down = stream.randint(1_200, 4_800)
        return RowDraft(
            start_ms=start,
            end_ms=start + stream.randint(9_000, 26_000),
            protocol="tls",
            transport="tcp",
            src_ip=params.patient_zero_ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=params.c2_upload_ip,
            dst_port=443,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up, overhead=10),
            packets_down=packets_for(down, overhead=10),
            risk_score=stream.randint(58, 72),
            risk_reasons=("high_volume_out", "self_signed_cert"),
            summary=f"TLS1.2 {params.c2_upload_host}",
            attrs=self._c2_tls_attrs(params.c2_upload_host),
            tag="incident.exfil",
        )

    def _put_row(self, stream: Stream, start: int) -> RowDraft:
        params = self._params
        up = stream.randint(*EXFIL_PUT_BYTES)
        key = f"{stream.hex(8)}/{stream.hex(12)}.bin"
        path = f"/bkt/{key}"
        return RowDraft(
            start_ms=start,
            end_ms=start + stream.randint(8_000, 24_000),
            protocol="http",
            transport="tcp",
            src_ip=params.patient_zero_ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=params.http_put_ip,
            dst_port=80,
            bytes_up=up,
            bytes_down=stream.randint(180, 420),
            packets_up=packets_for(up, overhead=10),
            packets_down=6,
            risk_score=stream.randint(58, 72),
            risk_reasons=("high_volume_out", "cleartext_auth"),
            summary=f"PUT {params.http_put_ip}{path} → 200",
            attrs={
                "http.host": params.http_put_ip,
                "http.method": "PUT",
                "http.status": 200,
                "http.path": path,
                "http.user_agent": "SyncAgent/1.0",
            },
            tag="incident.exfil",
        )

    def exfil_totals(self) -> tuple[int, int, int, int]:
        drafts = [d for block in self._static.values() for d in block if d.tag == "incident.exfil"]
        return (
            sum(d.bytes_up for d in drafts),
            len(drafts),
            min(d.start_ms for d in drafts),
            max(d.end_ms for d in drafts),
        )

    def stage_hours(self, tag: RowTag) -> tuple[tuple[str, int], ...]:
        return tuple(key for key, drafts in self._static.items() if drafts[0].tag == tag)

    def hour_of(self, ts_ms: int) -> int:
        return (ts_ms - self._epoch_ms) // _HOUR
