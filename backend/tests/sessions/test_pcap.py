import hashlib
from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.domain.base import ms_to_iso
from capture_api.world.world import SimWorld
from tests.conftest import OBSERVER, LoggedIn

from .conftest import PCAP_RETENTION_MS, Catalog, parse_content_disposition, set_chaos

LIBPCAP_MAGIC = (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1")
"""Classic libpcap, either byte order."""


def test_streams_a_real_capture_with_its_digest(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    row = rows.pcap_retained

    response = client.get(f"/v1/sessions/{row.id}/pcap", headers=login().headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.tcpdump.pcap"
    assert "content-length" not in response.headers
    assert response.content[:4] in LIBPCAP_MAGIC
    assert response.content == world.pcap(row)
    assert response.headers["x-content-sha256"] == hashlib.sha256(response.content).hexdigest()


def test_the_file_name_carries_the_sensor_name(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.pcap_retained

    response = client.get(f"/v1/sessions/{row.id}/pcap", headers=login().headers)

    names = parse_content_disposition(response.headers["content-disposition"])
    assert row.sensor_id == "hq-core"
    assert names["filename*"] == f"capture_api-HQ-Core-{row.id}.pcap"
    assert names["filename"] == names["filename*"]


def test_the_harbor_branch_name_needs_the_encoded_form(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.harbor_with_pcap

    response = client.get(f"/v1/sessions/{row.id}/pcap", headers=login().headers)

    header = response.headers["content-disposition"]
    names = parse_content_disposition(header)
    assert names["filename*"] == f"capture_api-Hafenbüro-Nord-{row.id}.pcap"
    assert "%C3%BC" in header, "the raw name is percent-encoded in filename*"
    assert names["filename"] == f"capture_api-Hafenb_ro-Nord-{row.id}.pcap"
    assert names["filename"].isascii()


def test_packets_older_than_48_hours_are_gone(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    row = rows.pcap_expired

    response = client.get(f"/v1/sessions/{row.id}/pcap", headers=login().headers)

    assert response.status_code == 410
    body = response.json()
    assert body["code"] == "pcap_expired"
    assert body["expired_at"] == ms_to_iso(row.start_ms + PCAP_RETENTION_MS)
    assert row.start_ms < world.epoch_ms - PCAP_RETENTION_MS


def test_the_retention_boundary_is_48_hours_before_the_epoch(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    headers = login().headers
    cut = world.epoch_ms - PCAP_RETENTION_MS

    assert rows.pcap_expired.start_ms < cut <= rows.pcap_retained.start_ms
    expired = client.get(f"/v1/sessions/{rows.pcap_expired.id}/pcap", headers=headers)
    retained = client.get(f"/v1/sessions/{rows.pcap_retained.id}/pcap", headers=headers)

    assert expired.status_code == 410
    assert retained.status_code == 200


def test_the_session_detail_agrees_with_the_download(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    row = rows.pcap_expired

    pcap_info = client.get(f"/v1/sessions/{row.id}", headers=headers).json()["pcap"]
    download = client.get(f"/v1/sessions/{row.id}/pcap", headers=headers).json()

    assert pcap_info["available"] is False
    assert pcap_info["reason"] == "expired"
    assert pcap_info["expired_at"] == download["expired_at"]


def test_an_observer_may_not_download_packets(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    response = client.get(
        f"/v1/sessions/{rows.pcap_retained.id}/pcap", headers=login(*OBSERVER).headers
    )

    assert response.status_code == 403
    assert response.json()["required"] == "pcap:download"


def test_a_degraded_packet_store_answers_503(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    set_chaos(client, "degraded-pcap")

    response = client.get(f"/v1/sessions/{rows.pcap_retained.id}/pcap", headers=headers)
    detail = client.get(f"/v1/sessions/{rows.pcap_retained.id}", headers=headers)

    assert response.status_code == 503
    assert response.json()["code"] == "pcap_store_degraded"
    assert response.headers["retry-after"] == "30"
    assert detail.status_code == 200, "only the packet store is degraded"


def test_the_download_limit_is_shared_with_carved_files(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    file = rows.plain_file

    for _ in range(10):
        response = client.get(
            f"/v1/sessions/{file.session_id}/files/{file.file_id}", headers=headers
        )
        assert response.status_code == 200

    refused = client.get(f"/v1/sessions/{rows.pcap_retained.id}/pcap", headers=headers)

    assert refused.status_code == 429
    assert refused.json()["code"] == "download_rate_limited"


def test_404_and_403_match_the_detail_route(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    assert client.get("/v1/sessions/nope/pcap", headers=login().headers).status_code == 404
    forbidden = client.get(f"/v1/sessions/{rows.dc_east.id}/pcap", headers=login(*OBSERVER).headers)
    assert forbidden.status_code == 403
