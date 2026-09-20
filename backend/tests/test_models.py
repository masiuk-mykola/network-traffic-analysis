from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from capture_api.domain.base import from_epoch_ms, iso_ms, ms_to_iso, to_epoch_ms
from capture_api.domain.models import (
    ByteCount,
    CasePatch,
    ColumnDef,
    Endpoint,
    FilterAll,
    FilterCond,
    FilterNot,
    HuntCreate,
    HuntPatch,
    HuntQuery,
    HuntWindowPreset,
    HuntWindowRange,
    ImportMeta,
    ObserverSummary,
    Risk,
    SearchCreate,
    SearchResults,
    SearchWarning,
    SessionRow,
    filter_depth,
    iter_conditions,
)

T0 = "2025-10-27T09:00:00Z"
T1 = "2025-10-27T10:00:00Z"


def _search(filter_: Any) -> dict[str, Any]:
    return {"sensor_ids": ["hq-core"], "from": T0, "to": T1, "filter": filter_}


def _row(**extra: Any) -> SessionRow:
    return SessionRow(
        id="72075232438042624",
        sensor_id="hq-core",
        start=datetime(2025, 10, 27, 9, 14, 3, 120456, tzinfo=UTC),
        end=datetime(2025, 10, 27, 11, 14, 3, tzinfo=timezone(timedelta(hours=2))),
        duration_ms=0,
        protocol="dns",
        transport="udp",
        src=Endpoint(ip="10.20.4.10", port=53000),
        dst=Endpoint(ip="10.20.0.53", port=53, host="ns1.quillmere.example"),
        bytes=ByteCount(up=70, down=120),
        packets=ByteCount(up=1, down=1),
        risk=Risk(score=5, band="low", reasons=[]),
        summary="A static.example.com → 192.0.2.10",
        decoder="dns/2",
        files_count=0,
        pcap_available=True,
        **extra,
    )


def test_optional_fields_are_absent_not_null() -> None:
    dumped = _row().model_dump(mode="json")
    assert "intel" not in dumped
    assert "host" not in dumped["src"]
    assert "country" not in dumped["dst"]
    assert dumped["dst"]["host"] == "ns1.quillmere.example"
    assert '"intel"' not in _row().model_dump_json()


def test_optional_fields_declare_no_null_default_in_the_schema() -> None:
    schema = SessionRow.model_json_schema()
    intel = schema["properties"]["intel"]
    assert "default" not in intel
    assert "anyOf" not in intel
    assert "intel" not in schema["required"]


def test_datetimes_serialise_as_utc_ms_z() -> None:
    dumped = _row().model_dump(mode="json")
    assert dumped["start"] == "2025-10-27T09:14:03.120Z"
    assert dumped["end"] == "2025-10-27T09:14:03.000Z"
    assert iso_ms(datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2025-01-02T03:04:05.000Z"
    ms = to_epoch_ms(datetime(2025, 10, 27, 12, 0, 0, 5000, tzinfo=UTC))
    assert ms == 1_761_566_400_005
    assert from_epoch_ms(ms).microsecond == 5000
    assert ms_to_iso(ms) == "2025-10-27T12:00:00.005Z"


def test_next_cursor_is_an_explicit_null() -> None:
    results = SearchResults(items=[], next_cursor=None, complete=False, matched_so_far=0)
    assert results.model_dump(mode="json")["next_cursor"] is None


def test_keyword_aliases_on_the_wire() -> None:
    warning = SearchWarning.model_validate(
        {"code": "capture_gap", "sensor_id": "harbor-branch", "from": T0, "detail": "gap"}
    )
    assert warning.from_ is not None
    assert set(warning.model_dump(mode="json")) == {"code", "sensor_id", "from", "detail"}
    assert ObserverSummary.model_validate({"pass": 2, "warn": 0, "fail": 1}).pass_ == 2
    node = FilterNot.model_validate(
        {"not": {"field": "src.ip", "op": "eq", "value": "10.20.9.250"}}
    )
    assert node.model_dump(mode="json") == {
        "not": {"field": "src.ip", "op": "eq", "value": "10.20.9.250"}
    }


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchCreate.model_validate({**_search({"all": []}), "from": "2025-10-27T09:00:00"})


def test_search_create_defaults_and_discriminated_filter() -> None:
    body = SearchCreate.model_validate(
        _search({"all": [{"not": {"field": "tls.sni", "op": "exists"}}, {"any": []}]})
    )
    assert body.sort == "-ts"
    assert isinstance(body.filter, FilterAll)
    assert isinstance(body.filter.all[0], FilterNot)


@pytest.mark.parametrize(
    ("cond", "ok"),
    [
        ({"field": "src.ip", "op": "eq", "value": "10.20.0.1"}, True),
        ({"field": "src.port", "op": "gte", "value": 1024}, True),
        ({"field": "src.port", "op": "gte", "value": "1024"}, True),
        ({"field": "risk.score", "op": "between", "values": [40, 100]}, True),
        ({"field": "protocol", "op": "in", "values": ["dns", "tls"]}, True),
        ({"field": "tls.sni", "op": "exists"}, True),
        ({"field": "src.ip", "op": "eq"}, False),
        ({"field": "src.ip", "op": "eq", "values": ["a"]}, False),
        ({"field": "src.ip", "op": "eq", "value": True}, False),
        ({"field": "protocol", "op": "in", "values": []}, False),
        ({"field": "protocol", "op": "in", "values": ["x"] * 51}, False),
        ({"field": "protocol", "op": "in", "value": "dns"}, False),
        ({"field": "risk.score", "op": "between", "values": [1]}, False),
        ({"field": "risk.score", "op": "between", "values": [1, 2, 3]}, False),
        ({"field": "tls.sni", "op": "exists", "value": "x"}, False),
        ({"field": "tls.sni", "op": "like", "value": "x"}, False),
        ({"field": "", "op": "eq", "value": "x"}, False),
        ({"field": "a", "op": "eq", "value": "x", "extra": 1}, False),
    ],
)
def test_condition_arity(cond: dict[str, Any], ok: bool) -> None:
    if ok:
        FilterCond.model_validate(cond)
    else:
        with pytest.raises(ValidationError):
            FilterCond.model_validate(cond)


def test_filter_depth_and_condition_limits() -> None:
    leaf: dict[str, Any] = {"field": "tls.sni", "op": "exists"}
    nested: dict[str, Any] = leaf
    for _ in range(7):
        nested = {"not": nested}
    assert filter_depth(SearchCreate.model_validate(_search(nested)).filter) == 8
    with pytest.raises(ValidationError, match="depth 9"):
        SearchCreate.model_validate(_search({"not": nested}))

    SearchCreate.model_validate(_search({"all": [leaf] * 64}))
    with pytest.raises(ValidationError, match="65 conditions"):
        SearchCreate.model_validate(_search({"all": [leaf] * 33 + [{"any": [leaf] * 32}]}))


def test_iter_conditions_reports_wire_locations() -> None:
    body = SearchCreate.model_validate(
        _search(
            {
                "all": [
                    {"field": "a", "op": "exists"},
                    {"not": {"any": [{"field": "b", "op": "exists"}]}},
                ]
            }
        )
    )
    locs = [(loc, cond.field) for loc, cond in iter_conditions(body.filter)]
    assert locs == [(("all", 0), "a"), (("all", 1, "not", "any", 0), "b")]


def test_hunt_window_union() -> None:
    query = {"sensor_ids": ["hq-core"], "filter": {"all": []}, "sort": "-bytes"}
    preset = HuntQuery.model_validate({**query, "window": {"preset": "24h"}})
    assert isinstance(preset.window, HuntWindowPreset)
    ranged = HuntQuery.model_validate({**query, "window": {"from": T0, "to": T1}})
    assert isinstance(ranged.window, HuntWindowRange)
    with pytest.raises(ValidationError):
        HuntQuery.model_validate({**query, "window": {"preset": "2h"}})


def test_hunt_bodies() -> None:
    query = {
        "sensor_ids": ["hq-core"],
        "window": {"preset": "1h"},
        "filter": {"all": []},
        "sort": "-ts",
    }
    with pytest.raises(ValidationError) as exc:
        HuntCreate.model_validate({"name": "", "query": query})
    assert exc.value.errors()[0]["loc"] == ("name",)
    with pytest.raises(ValidationError) as exc:
        HuntCreate.model_validate({"name": "x", "description": "d" * 501, "query": query})
    assert exc.value.errors()[0]["loc"] == ("description",)

    removal = HuntPatch.model_validate({"description": None})
    assert removal.model_fields_set == {"description"}
    assert removal.description is None
    assert HuntPatch.model_validate({}).model_fields_set == set()
    with pytest.raises(ValidationError, match="cannot be null"):
        HuntPatch.model_validate({"name": None})
    with pytest.raises(ValidationError, match="cannot be null"):
        CasePatch.model_validate({"status": None})
    assert CasePatch.model_validate({"summary": None}).model_fields_set == {"summary"}


def test_import_meta_validation() -> None:
    meta = ImportMeta.model_validate({"label": "Lab", "tz": "Europe/Lisbon", "sha256": "AB" * 32})
    assert meta.sha256 == "ab" * 32
    with pytest.raises(ValidationError, match="IANA"):
        ImportMeta.model_validate({"label": "Lab", "tz": "Mars/Base", "sha256": "ab" * 32})


def test_column_def_accepts_types_outside_the_documented_list() -> None:
    column = ColumnDef(
        key="dst_country",
        label="Geo",
        type="geo_hint",
        default_visible=False,
        sortable=False,
        width_hint=80,
    )
    assert column.model_dump()["type"] == "geo_hint"
