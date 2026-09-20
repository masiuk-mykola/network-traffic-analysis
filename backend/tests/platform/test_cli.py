import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from capture_api.__main__ import build_parser
from capture_api.__main__ import main as cli_main
from capture_api.cli import admin as admin_cli
from capture_api.cli import doctor as doctor_cli
from capture_api.cli import report as report_cli
from capture_api.cli import samples as samples_cli

REPORT = {
    "generated_at": "2025-10-27T12:00:00.000Z",
    "seed": "demo",
    "profile": "flaky",
    "full_history": False,
    "families": [
        {
            "family_id": "fam_ab12cd",
            "user": "ana@quillmere.example",
            "requests": 42,
            "checks": [
                {
                    "id": "http.get_dedupe",
                    "label": "Requests are de-duplicated",
                    "value": 5,
                    "threshold": "at most 2 identical GETs within 100 ms",
                    "status": "fail",
                    "evidence": [
                        {
                            "t": "2025-10-27T12:00:00.000Z",
                            "method": "GET",
                            "path": "/v1/detections",
                            "status": 200,
                            "note": "5 identical GETs within 100 ms",
                        }
                    ],
                },
                {
                    "id": "auth.refresh_reuse",
                    "label": "No refresh reuse",
                    "threshold": "0 refresh_reused",
                    "status": "n/a",
                    "evidence": [],
                },
            ],
        }
    ],
    "summary": {"pass": 12, "warn": 1, "fail": 1},
}


class FakeHttp:
    def __init__(self, status: int = 200, payload: Any = None) -> None:
        self.status = status
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(
            self.status,
            json=self.payload,
            request=httpx.Request(method, url),
        )


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    http = FakeHttp(payload={"profile": "storm", "overrides": {}})
    monkeypatch.setattr(httpx, "request", http)
    return http


def test_every_command_is_registered() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for name in (
        "serve",
        "openapi",
        "admin",
        "report",
        "doctor",
        "make-samples",
        "export-fixtures",
    ):
        assert name in help_text


def test_admin_chaos_sets_the_profile(
    fake_http: FakeHttp, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["admin", "chaos", "storm", "--live-burst", "5"]) == 0
    call = fake_http.calls[0]
    assert call["method"] == "PUT"
    assert call["url"].endswith("/v1/__admin/chaos")
    assert call["json"] == {"profile": "storm", "overrides": {"live_burst": 5}}
    assert call["headers"]["X-Admin-Token"] == "lf-dev-admin"
    assert "storm" in capsys.readouterr().out


def test_admin_chaos_without_a_profile_reads_the_configuration(fake_http: FakeHttp) -> None:
    assert cli_main(["admin", "chaos"]) == 0
    assert fake_http.calls[0]["method"] == "GET"


def test_admin_latency_override_is_a_pair(fake_http: FakeHttp) -> None:
    cli_main(["admin", "chaos", "calm", "--latency-ms", "10", "20"])
    assert fake_http.calls[0]["json"]["overrides"] == {"latency_ms": [10, 20]}


def test_admin_url_and_token_can_be_overridden(fake_http: FakeHttp) -> None:
    cli_main(["admin", "--url", "http://10.20.0.9:9000/", "--token", "s3cret", "reset"])
    call = fake_http.calls[0]
    assert call["url"] == "http://10.20.0.9:9000/v1/__admin/reset"
    assert call["headers"]["X-Admin-Token"] == "s3cret"


def test_admin_expire_and_revoke_and_touch(fake_http: FakeHttp) -> None:
    cli_main(["admin", "expire-tokens", "--email", "ana@quillmere.example"])
    cli_main(["admin", "revoke", "--email", "ana@quillmere.example"])
    cli_main(["admin", "touch-hunt", "hnt_7f2a"])
    assert [call["url"].rsplit("/v1", 1)[-1] for call in fake_http.calls] == [
        "/__admin/expire-tokens",
        "/__admin/revoke",
        "/__admin/hunts/hnt_7f2a/touch",
    ]
    assert fake_http.calls[0]["json"] == {"email": "ana@quillmere.example"}


def test_admin_reports_a_refused_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        httpx, "request", FakeHttp(401, {"detail": "nope", "code": "admin_token_invalid"})
    )
    assert cli_main(["admin", "reset"]) == admin_cli.EXIT_REFUSED
    assert "CAP_ADMIN_TOKEN" in capsys.readouterr().err


def test_admin_reports_an_unreachable_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", boom)
    assert cli_main(["admin", "reset"]) == admin_cli.EXIT_UNREACHABLE
    assert "capture-api serve" in capsys.readouterr().err


def test_report_renders_a_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "request", FakeHttp(200, REPORT))
    assert cli_main(["report"]) == 0
    out = capsys.readouterr().out
    assert "12 pass / 1 warn / 1 fail" in out
    assert "FAIL  http.get_dedupe" in out
    assert " --   auth.refresh_reuse" in out
    assert "5 identical GETs within 100 ms" in out


def test_report_quiet_hides_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "request", FakeHttp(200, REPORT))
    cli_main(["report", "--quiet"])
    out = capsys.readouterr().out
    assert "FAIL  http.get_dedupe" in out
    assert "/v1/detections" not in out


def test_report_json_is_raw(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(httpx, "request", FakeHttp(200, REPORT))
    cli_main(["report", "--json", "--since", "600"])
    assert json.loads(capsys.readouterr().out)["seed"] == "demo"


def test_report_without_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = {**REPORT, "families": [], "summary": {"pass": 0, "warn": 0, "fail": 0}}
    monkeypatch.setattr(httpx, "request", FakeHttp(200, empty))
    assert "No traffic recorded yet" in report_cli.render(empty)


def test_doctor_checks_the_toolchain(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main(["doctor", "--url", "http://127.0.0.1:8"])
    out = capsys.readouterr().out
    assert "python" in out
    assert "simulator" in out
    assert "not reachable" in out
    assert exit_code in (0, 1)


def test_doctor_reports_a_free_port_and_a_busy_one() -> None:
    import socket  # noqa: PLC0415 - only this test needs a real socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert doctor_cli._port(port, "test").level == "warn"
    assert doctor_cli._port(port, "test").level == "ok"


def test_make_samples_writes_the_bad_capture(tmp_path: Path) -> None:
    size, sha = samples_cli.write_not_a_capture(tmp_path / "not-a-capture.pcap")
    payload = (tmp_path / "not-a-capture.pcap").read_bytes()
    assert size == len(payload)
    assert len(sha) == 64
    assert payload[:4] not in (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1", b"\x0a\x0d\x0d\x0a")


def test_world_backed_commands_degrade_when_the_world_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real = importlib.import_module

    def missing(name: str) -> Any:
        if name == "capture_api.world.world":
            raise ModuleNotFoundError(name)
        return real(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    assert cli_main(["make-samples", "--out", str(tmp_path)]) == samples_cli.EXIT_MISSING_WORLD
    assert "needs the generated world" in capsys.readouterr().out
    assert cli_main(["export-fixtures", "--out", str(tmp_path)]) == samples_cli.EXIT_MISSING_WORLD


def test_make_samples_reports_an_empty_world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class EmptyWorld:
        seed = "samples"

        def capture_now_ms(self) -> int:
            return 0

        @property
        def data_start_ms(self) -> int:
            return 0

        def sensors(self) -> list[Any]:
            return []

    monkeypatch.setattr(samples_cli, "build_world_or_explain", lambda _seed: EmptyWorld())
    assert cli_main(["make-samples", "--out", str(tmp_path)]) == samples_cli.EXIT_MISSING_WORLD
    assert "no sessions" in capsys.readouterr().out


def test_command_parsers_expose_their_options() -> None:
    parser = build_parser()
    args = parser.parse_args(["report", "--json", "--family-id", "fam_1"])
    assert (args.json, args.family_id) == (True, "fam_1")
    args = parser.parse_args(["export-fixtures", "--seed", "fixtures", "--out", "out"])
    assert (args.seed, args.out) == ("fixtures", "out")
    args = parser.parse_args(["make-samples", "--out", "s", "--size-mb", "1"])
    assert args.size_mb == 1
    with pytest.raises(SystemExit):
        parser.parse_args(["admin", "chaos", "hurricane"])
    with pytest.raises(SystemExit):
        parser.parse_args(["admin"])


def test_overrides_are_omitted_when_no_flag_is_given() -> None:
    namespace = argparse.Namespace(
        get_503_rate=None,
        drop_rate=None,
        sse_rotate_s=None,
        access_ttl_s=None,
        live_burst=None,
        latency_ms=None,
    )
    assert admin_cli._overrides(namespace) is None
