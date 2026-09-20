import hashlib
from itertools import pairwise

import pytest

from capture_api.world.world import SimWorld
from tests.integration.conftest import all_rows, values, world_for

SEEDS = ["demo", "alpha"]


@pytest.fixture(params=SEEDS, scope="module")
def world(request: pytest.FixtureRequest) -> SimWorld:
    seed: str = request.param
    return world_for(seed)


def test_q1_patient_zero_and_first_contact(world: SimWorld) -> None:
    truth = world.truth()
    hits = [
        row
        for row in all_rows(world)
        if row.src_ip == truth.patient_zero_ip
        and (
            any(name.endswith(truth.c2_domain) for name in values(row, "dns.query.name"))
            or any(sni.endswith(truth.c2_domain) for sni in values(row, "tls.sni"))
            or row.dst_ip == truth.c2_ip
        )
    ]
    assert hits
    earliest = min(hits, key=lambda row: (row.start_ms, row.id))
    assert earliest.id == truth.first_c2_session_id
    assert earliest.start_ms == truth.first_c2_start_ms
    assert earliest.sensor_id == "harbor-branch"


def test_q2_c2_fingerprint_is_unique_to_the_beacon(world: SimWorld) -> None:
    truth = world.truth()
    beacons = [row for row in all_rows(world) if row.attr_str("tls.ja3") == truth.c2_ja3]
    assert beacons
    assert {row.attr_str("tls.sni") for row in beacons} == {truth.c2_sni}
    assert truth.c2_sni.endswith(truth.c2_domain)


def test_q3_lookalike_email_keeps_its_file_after_the_pcap_expires(world: SimWorld) -> None:
    truth = world.truth()
    mail = world.row(truth.email_session_id)
    assert mail is not None
    assert mail.protocol == "smtp"
    assert values(mail, "smtp.mail_from") == (f"billing@{truth.lookalike_domain}",)
    assert values(mail, "smtp.attachment.sha256") == (truth.attachment_sha256,)

    status = world.pcap_status(mail)
    assert not status.available
    assert status.reason == "expired"

    files = world.files_for_row(mail)
    assert len(files) == 1
    assert files[0].name == truth.attachment_name
    assert not files[0].purged
    assert hashlib.sha256(world.file_bytes(files[0])).hexdigest() == truth.attachment_sha256


def test_q4_finance_share_collection(world: SimWorld) -> None:
    truth = world.truth()
    rows = list(all_rows(world))
    read = [
        row
        for row in rows
        if row.src_ip == truth.patient_zero_ip
        and any(path.startswith("\\Invoices\\2026\\") for path in values(row, "smb2.path"))
    ]
    assert len(read) == truth.smb_file_count
    assert {row.sensor_id for row in read} == {"dc-east"}
    assert {tree for row in read for tree in values(row, "smb2.tree")} == {truth.smb_tree}

    denied = [
        row
        for row in rows
        if "STATUS_ACCESS_DENIED" in values(row, "smb2.status")
        and truth.denied_share in values(row, "smb2.tree")
    ]
    assert len(denied) == 1


def test_q5_exfiltration_window_and_volume(world: SimWorld) -> None:
    truth = world.truth()
    exfil = [row for row in all_rows(world) if row.tag == "incident.exfil"]
    assert len(exfil) == truth.exfil_session_count
    assert sum(row.bytes_up for row in exfil) == truth.exfil_bytes_up
    assert min(row.start_ms for row in exfil) == truth.exfil_start_ms
    assert max(row.end_ms for row in exfil) == truth.exfil_end_ms
    assert {row.sensor_id for row in exfil} == {"harbor-branch"}


def test_q6_earliest_retained_beacon_pcap(world: SimWorld) -> None:
    truth = world.truth()
    beacons = [row for row in all_rows(world) if row.attr_str("tls.ja3") == truth.c2_ja3]
    retained = [row for row in beacons if world.pcap_status(row).available]
    assert retained
    earliest = min(retained, key=lambda row: (row.start_ms, row.id))
    assert earliest.id == truth.q6_session_id
    assert hashlib.sha256(world.pcap(earliest)).hexdigest() == truth.q6_pcap_sha256


def test_ids_are_unique_and_beyond_double_precision(world: SimWorld) -> None:
    ids = [row.id for row in all_rows(world)]
    assert len(set(ids)) == len(ids)
    assert min(ids) > 2**53


def test_detection_seq_is_a_dense_ordered_prefix(world: SimWorld) -> None:
    detections = world.detections_until(world.capture_now_ms())
    assert detections
    assert [d.seq for d in detections] == list(range(1, len(detections) + 1))
    assert all(a.ts_ms <= b.ts_ms for a, b in pairwise(detections))
