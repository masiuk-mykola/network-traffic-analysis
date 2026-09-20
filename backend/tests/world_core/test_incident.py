import hashlib
from fnmatch import fnmatchcase
from itertools import pairwise

import pytest

from capture_api.world.catalog import DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.incident import (
    BEACON_DEDUPE_MS,
    BEACON_DETECTION_FROM,
    DENIED_TREE,
    FINANCE_TREE,
    LOOKALIKE_BASE,
    LOOKALIKE_DOMAINS,
)
from capture_api.world.types import Row
from capture_api.world.world import SimWorld

from .conftest import SEEDS, history, world_for

INVOICE_GLOB = "\\Invoices\\2026\\*"


def tuple_attr(row: Row, key: str) -> tuple[str, ...]:
    value = row.attrs.get(key)
    return value if isinstance(value, tuple) else ()


def rules_of(row: Row) -> tuple[str, ...]:
    return tuple_attr(row, "detection.rule")


def paths_of(row: Row) -> tuple[str, ...]:
    return tuple_attr(row, "smb2.path")


def beacons(world: SimWorld) -> list[Row]:
    sni = world.truth().c2_sni
    return sorted(
        (r for r in history(world, HARBOR_BRANCH) if r.attrs.get("tls.sni") == sni),
        key=lambda r: r.start_ms,
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_q1_first_contact_is_the_earliest_c2_session(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    lookups = sorted(
        (r for r in history(world, HARBOR_BRANCH) if r.attrs.get("dns.query.name") == truth.c2_sni),
        key=lambda r: r.start_ms,
    )
    assert lookups
    first = lookups[0]
    assert first.id == truth.first_c2_session_id
    assert first.start_ms == truth.first_c2_start_ms
    assert first.src_ip == truth.patient_zero_ip
    assert first.attrs["dns.rcode"] == "NOERROR"
    assert first.attrs["dns.answer"] == (truth.c2_ip,)
    assert first.attrs["dns.ttl"] == 60
    assert first.start_ms < beacons(world)[0].start_ms
    nxdomain = [
        r
        for r in history(world, HARBOR_BRANCH)
        if r.attrs.get("dns.rcode") == "NXDOMAIN"
        and str(r.attrs.get("dns.query.name", "")).endswith(truth.c2_domain)
    ]
    assert len(nxdomain) == 2


@pytest.mark.parametrize("seed", SEEDS)
def test_q2_the_beacon_is_one_unique_fingerprint_against_one_address(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    sessions = beacons(world)
    assert len(sessions) > 100
    assert {r.dst_ip for r in sessions} == {truth.c2_ip}
    assert {r.attrs["tls.ja3"] for r in sessions} == {truth.c2_ja3}
    assert {r.attrs["tls.version"] for r in sessions} == {"TLS1.2"}
    assert {r.src_ip for r in sessions} == {truth.patient_zero_ip}
    certificate = {str(r.attrs["tls.cert_cn"]) for r in sessions}
    assert len(certificate) == 1
    assert certificate.pop().endswith(".invalid")
    assert all(r.attrs["tls.cert_cn"] == r.attrs["tls.cert_issuer"] for r in sessions)
    assert all(r.attrs["tls.cert_cn"] != r.attrs["tls.sni"] for r in sessions)
    others = [r for r in history(world, HARBOR_BRANCH) if r.attrs.get("tls.ja3") == truth.c2_ja3]
    assert {r.id for r in others} >= {r.id for r in sessions}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_beacon_detection_starts_at_the_twelfth_and_backs_off(seed: str) -> None:
    world = world_for(seed)
    sessions = beacons(world)
    flagged = [
        index for index, row in enumerate(sessions) if "periodic_tls_beacon" in rules_of(row)
    ]
    assert flagged
    assert min(flagged) == BEACON_DETECTION_FROM - 1
    assert sessions[BEACON_DETECTION_FROM - 1].id == world.truth().twelfth_beacon_session_id
    times = [sessions[index].start_ms for index in flagged]
    assert all(b - a >= BEACON_DEDUPE_MS for a, b in pairwise(times))


@pytest.mark.parametrize("seed", SEEDS)
def test_q3_the_lookalike_mail_carries_the_carved_attachment(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    assert truth.lookalike_domain in LOOKALIKE_DOMAINS
    assert truth.lookalike_domain != LOOKALIKE_BASE
    assert abs(len(truth.lookalike_domain) - len(LOOKALIKE_BASE)) <= 1
    assert truth.lookalike_domain.endswith(".example")
    mails = [
        r
        for r in history(world, HQ_CORE)
        if r.attrs.get("smtp.mail_from") == f"billing@{truth.lookalike_domain}"
    ]
    assert len(mails) == 1
    mail = mails[0]
    assert mail.id == truth.email_session_id
    assert mail.attrs["smtp.rcpt_to"] == (f"{truth.patient_zero_user}@quillmere.example",)
    assert not str(mail.attrs["smtp.subject"]).isascii()
    files = world.files_for_row(mail)
    assert len(files) == 1
    assert files[0].name == truth.attachment_name
    assert files[0].sha256 == truth.attachment_sha256
    assert mail.attrs["smtp.attachment.sha256"] == (truth.attachment_sha256,)
    assert not files[0].purged
    status = world.pcap_status(mail)
    assert not status.available
    assert status.reason == "expired"
    assert status.expired_at_ms is not None


@pytest.mark.parametrize("seed", SEEDS)
def test_q4_the_finance_share_collection_is_countable(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    reads = [
        row
        for row in history(world, DC_EAST)
        if row.src_ip == truth.patient_zero_ip
        and any(fnmatchcase(p, INVOICE_GLOB) for p in paths_of(row))
    ]
    assert len(reads) == truth.smb_file_count
    assert 1_100 <= truth.smb_file_count <= 1_700
    assert {r.attrs["smb2.tree"] for r in reads} == {FINANCE_TREE}
    assert truth.smb_tree == FINANCE_TREE
    span = max(r.start_ms for r in reads) - min(r.start_ms for r in reads)
    assert span <= 21 * 60_000
    denied = [
        row
        for row in history(world, DC_EAST)
        if row.src_ip == truth.patient_zero_ip
        and row.attrs.get("smb2.status") == "STATUS_ACCESS_DENIED"
    ]
    assert len(denied) == 1
    assert denied[0].attrs["smb2.tree"] == DENIED_TREE == truth.denied_share


@pytest.mark.parametrize("seed", SEEDS)
def test_q5_the_exfiltration_totals_match_the_truth(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    params = world.incident()
    if truth.exfil_channel == "https_upload":
        found = [
            r
            for r in history(world, HARBOR_BRANCH)
            if r.attrs.get("tls.sni") == params.c2_upload_host
        ]
        assert {r.dst_ip for r in found} == {params.c2_upload_ip}
        assert 300 <= len(found) <= 420
        assert 1_500_000_000 <= truth.exfil_bytes_up <= 2_300_000_000
    else:
        found = [
            r
            for r in history(world, HARBOR_BRANCH)
            if r.attrs.get("http.method") == "PUT" and r.dst_ip == params.http_put_ip
        ]
        assert all(str(r.attrs["http.path"]).startswith("/bkt/") for r in found)
        assert 200 <= len(found) <= 300
        assert 900_000_000 <= truth.exfil_bytes_up <= 1_500_000_000
    assert len(found) == truth.exfil_session_count
    assert sum(r.bytes_up for r in found) == truth.exfil_bytes_up
    assert {r.src_ip for r in found} == {truth.patient_zero_ip}
    assert truth.exfil_start_ms <= min(r.start_ms for r in found)
    assert max(r.start_ms for r in found) <= truth.exfil_end_ms
    assert not any("detection.rule" in r.attrs for r in found)


@pytest.mark.parametrize("seed", SEEDS)
def test_q6_the_earliest_retained_beacon_pcap(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    retained = [row for row in beacons(world) if world.pcap_available(row)]
    assert retained
    assert retained[0].id == truth.q6_session_id
    assert retained[0].start_ms >= world.epoch_ms - 48 * 3_600_000
    assert hashlib.sha256(world.pcap(retained[0])).hexdigest() == truth.q6_pcap_sha256
    expired = [row for row in beacons(world) if not world.pcap_available(row)]
    assert expired
    assert max(r.start_ms for r in expired) < retained[0].start_ms


@pytest.mark.parametrize("seed", SEEDS)
def test_the_capture_gap_makes_the_beacon_look_stopped(seed: str) -> None:
    world = world_for(seed)
    truth = world.truth()
    outages = world.outages(HARBOR_BRANCH)
    assert len(outages) == 1
    gap = outages[0]
    assert (gap.start_ms, gap.end_ms) == (truth.capture_gap_start_ms, truth.capture_gap_end_ms)
    assert gap.end_ms - gap.start_ms == 15 * 60_000
    inside = [r for r in history(world, HARBOR_BRANCH) if gap.start_ms <= r.start_ms < gap.end_ms]
    assert inside == []
    around = [
        r
        for r in history(world, HARBOR_BRANCH)
        if gap.start_ms - 20 * 60_000 <= r.start_ms < gap.start_ms
    ]
    assert around
    assert world.outages(HQ_CORE) == []
    assert world.outages(DC_EAST) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_the_stages_keep_their_order_and_stay_inside_the_history(seed: str) -> None:
    world = world_for(seed)
    params = world.incident()
    moments = (
        params.email_ms,
        params.first_contact_ms,
        params.beacon_start_ms,
        params.smb_start_ms,
        params.exfil_start_ms,
        params.exfil_end_ms,
        params.capture_gap_start_ms,
    )
    assert list(moments) == sorted(moments)
    assert world.data_start_ms <= moments[0]
    assert moments[-1] <= world.epoch_ms
    assert params.beacon_interval_s in range(240, 421)
    assert params.patient_zero_ip.startswith("10.20.40.")
    assert params.c2_ip.startswith("203.0.113.")
    assert params.lookalike_sender_ip.startswith("198.51.100.")
    assert params.c2_domain.endswith(".test")
