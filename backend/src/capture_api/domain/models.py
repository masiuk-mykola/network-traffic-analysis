from collections.abc import Iterator
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from capture_api.domain.base import Opt, RequestModel, Scalar, UtcDateTime, WireModel
from capture_api.settings import ChaosProfile

type Role = Literal["analyst", "observer"]
type Permission = Literal[
    "sessions:read",
    "pcap:download",
    "files:download",
    "hunts:write",
    "cases:write",
    "imports:create",
    "live:read",
]
type ProtocolName = Literal["dns", "http", "tls", "smtp", "smb2", "ssh", "ntp", "tcp"]
type Transport = Literal["udp", "tcp"]
type RiskBand = Literal["low", "medium", "high"]
type Severity = Literal["low", "medium", "high"]
type SortKey = Literal["ts", "-ts", "bytes", "-bytes", "risk", "-risk"]
type FilterOp = Literal["eq", "in", "cidr", "glob", "gte", "lte", "between", "exists"]
type SearchState = Literal["queued", "running", "done", "failed", "cancelled"]
type SensorKind = Literal["tap", "span", "import"]
type SensorStatus = Literal["online", "lagging", "offline"]
type DecoderVersion = Literal["v1", "v2"]
type FieldType = Literal[
    "ip",
    "cidr",
    "port",
    "number",
    "bytes",
    "string",
    "enum",
    "country",
    "ja3",
    "duration_ms",
    "sensor",
]
type ColumnType = Literal[
    "ts",
    "ip_port",
    "bytes",
    "risk",
    "protocol",
    "duration",
    "text",
    "country",
    "sensor",
    "id",
]
type HealthStatus = Literal["ok", "degraded"]
type EnumName = Literal[
    "protocol",
    "country",
    "risk_band",
    "detection_rule",
    "dns_query_type",
    "dns_rcode",
    "http_method",
    "tls_version",
    "smb2_status",
]
type SearchWarningCode = Literal["capture_gap", "sensor_lagging"]
type PcapUnavailableReason = Literal["expired", "not_captured"]
type FileSource = Literal["smtp_attachment", "http_body"]
type HuntPreset = Literal["1h", "6h", "24h", "72h"]
type CaseStatus = Literal["open", "in_progress", "closed"]
type ImportState = Literal["received", "indexing", "ready", "failed"]
type ExportState = Literal["queued", "running", "ready", "failed"]
type Reputation = Literal["clean", "suspicious", "malicious", "unknown"]
type GraphNodeKind = Literal["internal", "external"]
type RelatedWindow = Literal["15m", "1h", "6h"]
type CheckStatus = Literal["pass", "warn", "fail", "n/a"]
type LiveChannel = Literal["sessions", "stats"]

COLUMN_TYPES: tuple[str, ...] = (
    "ts",
    "ip_port",
    "bytes",
    "risk",
    "protocol",
    "duration",
    "text",
    "country",
    "sensor",
    "id",
)

MAX_FILTER_DEPTH = 8
MAX_FILTER_CONDITIONS = 64
MAX_IN_VALUES = 50
MAX_FILTER_VALUE_CHARS = 512
MAX_GLOB_WILDCARDS = 16

SessionId = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{1,20}$",
        description="uint64 as a decimal string; larger than 2**53, never parse as a number.",
        examples=["72075232438042624"],
    ),
]


class Endpoint(WireModel):
    ip: str
    port: int
    host: Opt[str] = None
    country: Opt[str] = Field(default=None, description="ISO 3166-1 alpha-2; absent internally.")


class ByteCount(WireModel):
    up: int
    down: int


class RiskReason(WireModel):
    code: str
    label: str
    mitre: Opt[str] = None


class Risk(WireModel):
    score: int = Field(ge=0, le=100)
    band: RiskBand
    reasons: list[RiskReason]


class Intel(WireModel):
    score: int = Field(ge=0, le=100)
    source: str


class Mitre(WireModel):
    technique_id: str
    name: str


class SessionRow(WireModel):
    id: SessionId
    sensor_id: str
    start: UtcDateTime
    end: UtcDateTime
    duration_ms: int
    protocol: ProtocolName
    transport: Transport
    src: Endpoint
    dst: Endpoint
    bytes: ByteCount
    packets: ByteCount
    risk: Risk
    intel: Opt[Intel] = None
    summary: str
    decoder: str = Field(description='"<protocol>/<1|2>", e.g. "dns/1".')
    files_count: int
    pcap_available: bool


class PcapInfo(WireModel):
    available: bool
    reason: Opt[PcapUnavailableReason] = None
    expired_at: Opt[UtcDateTime] = None


class CarvedFile(WireModel):
    id: str
    name: str = Field(description="Raw carved name; may be non-ASCII or contain separators.")
    mime: str
    size: int
    sha256: str
    source: FileSource
    purged: bool


class SessionDetection(WireModel):
    rule_id: str
    rule: str
    severity: Severity
    mitre: Mitre


class Session(SessionRow):
    decoded: dict[str, Any] = Field(
        description=(
            'Decoded transaction keyed by protocol, e.g. {"dns": {...}}. Shape depends on the '
            "sensor decoder (v1 legacy or v2 canonical); typed loosely on purpose."
        )
    )
    detections: list[SessionDetection]
    files: list[CarvedFile]
    pcap: PcapInfo


class FlowSample(WireModel):
    t: int = Field(description="Bucket start, epoch milliseconds.")
    bytes_up: int
    bytes_down: int
    packets_up: int
    packets_down: int


class SessionFlow(WireModel):
    session_id: SessionId
    bucket_ms: int
    samples: list[FlowSample] = Field(description="Empty buckets are omitted.")


class RelatedSessions(WireModel):
    items: list[SessionRow]
    next_cursor: str | None


class Detection(WireModel):
    seq: int
    id: str
    ts: UtcDateTime
    rule_id: str
    rule: str
    severity: Severity
    mitre: Mitre
    sensor_id: str
    session_id: SessionId
    src: Endpoint
    dst: Endpoint
    summary: str


class DetectionList(WireModel):
    items: list[Detection] = Field(description="Ascending seq.")
    last_seq: int


class DetectionResetEvent(WireModel):
    reason: Literal["resume_point_too_old"]
    oldest_seq: int
    last_seq: int


class ReauthEvent(WireModel):
    reason: Literal["token_expired"]


class Profile(WireModel):
    id: str
    email: str
    display_name: str
    role: Role
    permissions: list[Permission]
    sensor_ids: list[str] = Field(description="Sensors this user may read.")


class LoginRequest(RequestModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(RequestModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class TokenPair(WireModel):
    access_token: str
    token_type: Literal["bearer"]
    access_expires_in: int = Field(description="Seconds until the access token expires.")
    refresh_token: str
    refresh_expires_in: int = Field(description="Seconds until the refresh token idles out.")
    user: Profile


class ComponentStatus(WireModel):
    status: HealthStatus
    detail: Opt[str] = None


class HealthComponents(WireModel):
    index: ComponentStatus
    decoder: ComponentStatus
    pcap_store: ComponentStatus
    live_feed: ComponentStatus


class Health(WireModel):
    status: HealthStatus
    components: HealthComponents
    server_time: UtcDateTime = Field(description="The capture clock.")
    version: str


class SensorRetention(WireModel):
    metadata_days: int
    pcap_hours: int
    files_days: int


class Sensor(WireModel):
    id: str
    name: str
    site: str
    kind: SensorKind
    status: SensorStatus
    decoder_version: DecoderVersion
    tz: str
    retention: SensorRetention
    last_packet_at: UtcDateTime
    lag_seconds: int
    last_packet_local: str = Field(
        description="Legacy 'DD/MM/YYYY HH:mm:ss' in the sensor's tz.",
        examples=["27/10/2025 12:00:00"],
    )


class SensorList(WireModel):
    items: list[Sensor]


class FieldDef(WireModel):
    name: str
    label: str
    type: FieldType
    operators: list[FilterOp]
    enum: Opt[list[str]] = None
    enum_name: Opt[str] = Field(
        default=None,
        description=(
            "The `/v1/meta/enums/{name}` catalogue that carries display labels for this "
            "field's values. Absent when the field has no catalogue entry (`sensor`), so "
            "the route name is never guessed from the field name."
        ),
    )
    pattern: Opt[str] = None
    example: str


class FieldList(WireModel):
    items: list[FieldDef]


class ColumnDef(WireModel):
    key: str
    label: str
    type: Annotated[
        str,
        WithJsonSchema(
            {
                "type": "string",
                "enum": list(COLUMN_TYPES),
                "description": "Documented column types. Render any other value as text.",
            }
        ),
    ]
    default_visible: bool
    sortable: bool
    width_hint: int


class ColumnList(WireModel):
    items: list[ColumnDef]


class EnumValue(WireModel):
    value: str
    label: str


class EnumResponse(WireModel):
    name: EnumName
    values: list[EnumValue]


class SchemaField(WireModel):
    path: str = Field(description='Dotted path inside `decoded`, e.g. "dns.query.name".')
    title: str
    type: str
    unit: Opt[str] = None
    sensitive: Opt[bool] = None


class ProtocolSchema(WireModel):
    protocol: ProtocolName
    decoder_versions: list[DecoderVersion]
    fields: list[SchemaField]


class FilterCond(RequestModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "A leaf condition. Arity: in -> values (1..50); between -> exactly 2 "
                "values; exists -> neither; every other op -> value."
            )
        }
    )

    field: str = Field(min_length=1, max_length=64)
    op: FilterOp
    value: Opt[Scalar] = None
    values: Opt[Annotated[list[Scalar], Field(max_length=MAX_IN_VALUES)]] = None

    @model_validator(mode="after")
    def _check_arity(self) -> "FilterCond":
        has_value = self.value is not None
        has_values = self.values is not None
        if self.op == "exists":
            if has_value or has_values:
                raise ValueError("'exists' takes neither 'value' nor 'values'")
        elif self.op == "in":
            if has_value or not self.values:
                raise ValueError(f"'in' needs 'values' with 1..{MAX_IN_VALUES} items")
        elif self.op == "between":
            if has_value or self.values is None or len(self.values) != 2:
                raise ValueError("'between' needs exactly 2 'values'")
        elif not has_value or has_values:
            raise ValueError(f"'{self.op}' needs a single 'value'")
        for operand in self._operands():
            if isinstance(operand, str) and len(operand) > MAX_FILTER_VALUE_CHARS:
                raise ValueError(
                    f"a filter value may hold at most {MAX_FILTER_VALUE_CHARS} characters"
                )
            if self.op == "glob" and isinstance(operand, str):
                wildcards = sum(1 for char in operand if char in "*?")
                if wildcards > MAX_GLOB_WILDCARDS:
                    raise ValueError(
                        f"a glob may hold at most {MAX_GLOB_WILDCARDS} wildcards; "
                        f"this one has {wildcards}"
                    )
        return self

    def _operands(self) -> list[Scalar]:
        operands: list[Scalar] = [] if self.value is None else [self.value]
        operands.extend(self.values or ())
        return operands


class FilterAll(RequestModel):
    all: list["FilterNode"] = Field(max_length=MAX_FILTER_CONDITIONS)


class FilterAny(RequestModel):
    any: list["FilterNode"] = Field(max_length=MAX_FILTER_CONDITIONS)


class FilterNot(RequestModel):
    not_: "FilterNode" = Field(alias="not")


def _filter_kind(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("all", "any", "not"):
            if key in value:
                return key
        return "cond"
    if isinstance(value, FilterAll):
        return "all"
    if isinstance(value, FilterAny):
        return "any"
    if isinstance(value, FilterNot):
        return "not"
    return "cond"


type FilterNode = Annotated[
    Annotated[FilterAll, Tag("all")]
    | Annotated[FilterAny, Tag("any")]
    | Annotated[FilterNot, Tag("not")]
    | Annotated[FilterCond, Tag("cond")],
    Discriminator(_filter_kind),
]
"""Recursive filter tree: ``{all:[…]} | {any:[…]} | {not: …} | FilterCond``."""


def filter_children(node: FilterNode) -> list[tuple[tuple[str | int, ...], FilterNode]]:
    if isinstance(node, FilterAll):
        return [(("all", i), child) for i, child in enumerate(node.all)]
    if isinstance(node, FilterAny):
        return [(("any", i), child) for i, child in enumerate(node.any)]
    if isinstance(node, FilterNot):
        return [(("not",), node.not_)]
    return []


def iter_conditions(
    node: FilterNode, loc: tuple[str | int, ...] = ()
) -> Iterator[tuple[tuple[str | int, ...], FilterCond]]:
    if isinstance(node, FilterCond):
        yield loc, node
        return
    for suffix, child in filter_children(node):
        yield from iter_conditions(child, loc + suffix)


def filter_depth(node: FilterNode) -> int:
    children = filter_children(node)
    return 1 + max((filter_depth(child) for _, child in children), default=0)


def validate_filter_tree(node: FilterNode) -> FilterNode:
    depth = filter_depth(node)
    if depth > MAX_FILTER_DEPTH:
        raise ValueError(f"filter depth {depth} exceeds {MAX_FILTER_DEPTH}")
    conditions = sum(1 for _ in iter_conditions(node))
    if conditions > MAX_FILTER_CONDITIONS:
        raise ValueError(
            f"filter has {conditions} conditions; the limit is {MAX_FILTER_CONDITIONS}"
        )
    return node


RootFilter = Annotated[FilterNode, AfterValidator(validate_filter_tree)]
"""Use for every field holding a filter ROOT (search, hunt query, subscription)."""


class SearchCreate(RequestModel):
    sensor_ids: list[str] = Field(min_length=1, max_length=5)
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    filter: RootFilter
    sort: SortKey = "-ts"


class SearchProgress(WireModel):
    scanned_sessions: int
    total_sessions_estimate: int
    matched: int
    matched_is_estimate: bool
    percent: float = Field(ge=0, le=100)


class SearchStats(WireModel):
    matched_bytes_up: int
    matched_bytes_down: int


class SearchWarning(WireModel):
    code: SearchWarningCode
    sensor_id: str
    from_: Opt[UtcDateTime] = Field(default=None, alias="from")
    to: Opt[UtcDateTime] = None
    detail: str


class Search(WireModel):
    id: str
    state: SearchState
    sensor_ids: list[str]
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    filter: FilterNode
    sort: SortKey
    created_at: UtcDateTime
    finished_at: Opt[UtcDateTime] = None
    progress: SearchProgress
    stats: SearchStats
    warnings: list[SearchWarning]


class SearchResults(WireModel):
    items: list[SessionRow]
    next_cursor: str | None = Field(
        description="null + complete=false: caught up (more may come); null + complete=true: end."
    )
    complete: bool
    matched_so_far: int


class EstimateResponse(WireModel):
    estimated_matches: int
    estimated_sessions_scanned: int
    is_estimate: Literal[True]


class HuntWindowPreset(RequestModel):
    preset: HuntPreset


class HuntWindowRange(RequestModel):
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime


def _window_kind(value: Any) -> str:
    if isinstance(value, dict):
        return "preset" if "preset" in value else "range"
    return "preset" if isinstance(value, HuntWindowPreset) else "range"


type HuntWindow = Annotated[
    Annotated[HuntWindowPreset, Tag("preset")] | Annotated[HuntWindowRange, Tag("range")],
    Discriminator(_window_kind),
]


class HuntQuery(RequestModel):
    sensor_ids: list[str] = Field(min_length=1, max_length=5)
    window: HuntWindow
    filter: RootFilter
    sort: SortKey


class Hunt(WireModel):
    id: str
    owner_id: str
    name: str
    description: Opt[str] = None
    query: HuntQuery
    created_at: UtcDateTime
    updated_at: UtcDateTime
    version: int


class HuntCreate(RequestModel):
    name: str = Field(min_length=1, max_length=80)
    description: Opt[Annotated[str, Field(max_length=500)]] = None
    query: HuntQuery


def _reject_nulls(model: RequestModel, *names: str) -> None:
    for name in names:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"'{name}' cannot be null")


class HuntPatch(RequestModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "JSON merge-patch: omitted keys are unchanged; description: null removes it."
            )
        }
    )

    name: Opt[Annotated[str, Field(min_length=1, max_length=80)]] = None
    description: str | None = Field(default=None, max_length=500)
    query: Opt[HuntQuery] = None

    @model_validator(mode="after")
    def _no_null_required(self) -> "HuntPatch":
        _reject_nulls(self, "name", "query")
        return self


class HuntList(WireModel):
    items: list[Hunt]


class LiveTicketRequest(RequestModel):
    sensor_ids: list[str] = Field(min_length=1, max_length=3)


class LiveTicketResponse(WireModel):
    ticket: str
    expires_in: int
    ws_url: str


class LiveSubscribe(RequestModel):
    type: Literal["subscribe"]
    sub_id: str = Field(min_length=1, max_length=64)
    sensor_ids: list[str] = Field(min_length=1, max_length=3)
    filter: RootFilter | None = None
    channels: list[LiveChannel] = Field(min_length=1)


class LivePause(RequestModel):
    type: Literal["pause"]


class LiveResume(RequestModel):
    type: Literal["resume"]


class LivePong(RequestModel):
    type: Literal["pong"]
    nonce: str


class LiveWatchSearch(RequestModel):
    type: Literal["watch_search"]
    search_id: str


class LiveUnwatchSearch(RequestModel):
    type: Literal["unwatch_search"]
    search_id: str


type LiveClientFrame = Annotated[
    LiveSubscribe | LivePause | LiveResume | LivePong | LiveWatchSearch | LiveUnwatchSearch,
    Field(discriminator="type"),
]
"""Client → server WebSocket frames (parse with ``TypeAdapter(LiveClientFrame)``)."""


class LiveHello(WireModel):
    type: Literal["hello"] = "hello"
    server_time: UtcDateTime
    heartbeat_s: int


class LiveAck(WireModel):
    type: Literal["ack"] = "ack"
    sub_id: str
    generation: int


class LiveSessionFrame(WireModel):
    type: Literal["session"] = "session"
    generation: int
    seq: int
    row: SessionRow
    synthetic: Opt[Literal[True]] = None


class LiveProtocolStats(WireModel):
    sessions: int
    bytes: int


class LiveStats(WireModel):
    type: Literal["stats"] = "stats"
    generation: int
    t: UtcDateTime
    by_protocol: dict[str, LiveProtocolStats]


class LiveLagging(WireModel):
    type: Literal["lagging"] = "lagging"
    generation: int
    dropped: int
    sample_rate: float


class LivePing(WireModel):
    type: Literal["ping"] = "ping"
    nonce: str


class LiveSearchProgress(WireModel):
    type: Literal["search_progress"] = "search_progress"
    search_id: str
    state: SearchState
    progress: SearchProgress


class LiveError(WireModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class ImportMeta(RequestModel):
    label: str = Field(min_length=1, max_length=60)
    tz: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("tz")
    @classmethod
    def _iana_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA time zone '{value}'") from exc
        return value

    @field_validator("sha256")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class Import(WireModel):
    id: str
    state: ImportState
    progress: int = Field(ge=0, le=100)
    sensor_id: str
    sha256: str
    label: str
    sessions_indexed: int


class ImportDuplicate(WireModel):
    duplicate: Literal[True]
    id: str
    sensor_id: str


class EvidencePin(WireModel):
    session_id: SessionId
    stage: Opt[str] = None
    note: Opt[str] = None
    pinned_by: str
    pinned_at: UtcDateTime


class EvidenceCreate(RequestModel):
    session_id: SessionId
    stage: Opt[Annotated[str, Field(min_length=1, max_length=40)]] = None
    note: Opt[Annotated[str, Field(max_length=500)]] = None


class EvidenceDuplicate(WireModel):
    duplicate: Literal[True]


class Note(WireModel):
    id: str
    author_id: str
    body: str
    created_at: UtcDateTime


class NoteCreate(RequestModel):
    body: str = Field(min_length=1, max_length=2000)


class Case(WireModel):
    id: str
    title: str
    status: CaseStatus
    owner_id: str
    severity: Severity
    summary: Opt[str] = None
    evidence: list[EvidencePin]
    notes: list[Note]
    created_at: UtcDateTime
    updated_at: UtcDateTime
    version: int


class CaseSummary(WireModel):
    id: str
    title: str
    status: CaseStatus
    owner_id: str
    severity: Severity
    evidence_count: int
    note_count: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
    version: int


class CaseList(WireModel):
    items: list[CaseSummary]
    next_cursor: str | None


class CaseCreate(RequestModel):
    title: str = Field(min_length=1, max_length=120)
    severity: Severity
    summary: Opt[Annotated[str, Field(max_length=2000)]] = None


class CasePatch(RequestModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "JSON merge-patch: omitted keys are unchanged; summary: null removes it."
        }
    )

    title: Opt[Annotated[str, Field(min_length=1, max_length=120)]] = None
    status: Opt[CaseStatus] = None
    severity: Opt[Severity] = None
    summary: str | None = Field(default=None, max_length=2000)
    owner_id: Opt[Annotated[str, Field(min_length=1)]] = None

    @model_validator(mode="after")
    def _no_null_required(self) -> "CasePatch":
        _reject_nulls(self, "title", "status", "severity", "owner_id")
        return self


class Export(WireModel):
    id: str
    case_id: str
    state: ExportState
    percent: float = Field(ge=0, le=100)
    expires_at: Opt[UtcDateTime] = None


class LqlParseRequest(RequestModel):
    q: str = Field(max_length=4000)


class LqlParseResponse(WireModel):
    filter: FilterNode
    normalized: str


class HistogramBucket(WireModel):
    t: UtcDateTime
    coverage: float = Field(ge=0, le=1)
    partial: Opt[Literal[True]] = None
    by_protocol: dict[str, int]
    bytes: int


class Histogram(WireModel):
    bucket_s: int
    buckets: list[HistogramBucket] = Field(description="Buckets with no capture are omitted.")


class PivotBucket(WireModel):
    t: UtcDateTime
    count: int


class PivotSeries(WireModel):
    sensor_id: str
    buckets: list[PivotBucket]


class PivotOccurrences(WireModel):
    series: list[PivotSeries]


class GraphNode(WireModel):
    id: str = Field(description="The IP address.")
    label: str
    kind: GraphNodeKind
    sessions: int
    bytes: int


class GraphEdge(WireModel):
    a: str
    b: str
    sessions: int
    bytes: int


class SearchGraph(WireModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    partial: bool


class EnrichRequest(RequestModel):
    ips: list[str] = Field(min_length=1, max_length=100)


class EnrichResult(WireModel):
    country: Opt[str] = None
    asn: Opt[str] = None
    org: Opt[str] = None
    reputation: Reputation


class EnrichResponse(WireModel):
    results: dict[str, EnrichResult]


class ChaosOverrides(RequestModel):
    get_503_rate: Opt[Annotated[float, Field(ge=0, le=1)]] = None
    drop_rate: Opt[Annotated[float, Field(ge=0, le=1)]] = None
    latency_ms: Opt[tuple[int, int]] = None
    sse_rotate_s: Opt[Annotated[int, Field(ge=1)]] = None
    access_ttl_s: Opt[Annotated[int, Field(ge=1)]] = None
    live_burst: Opt[Annotated[int, Field(ge=0)]] = None


class ChaosConfig(RequestModel):
    profile: ChaosProfile
    overrides: Opt[ChaosOverrides] = None


class AdminExpireTokens(RequestModel):
    email: Opt[str] = None


class AdminRevoke(RequestModel):
    email: str


class HuntTouchResponse(WireModel):
    version: int


class AdminState(WireModel):
    families: int
    searches: int
    streams: int
    sockets: int


class ObserverEvidence(WireModel):
    t: str
    method: str
    path: str
    status: int
    note: Opt[str] = None


class ObserverCheck(WireModel):
    id: str
    label: str
    value: Opt[int | float | str] = None
    threshold: str
    status: CheckStatus
    evidence: list[ObserverEvidence] = Field(max_length=5)


class ObserverFamily(WireModel):
    family_id: str
    user: str
    requests: int
    checks: list[ObserverCheck]


class ObserverSummary(WireModel):
    pass_: int = Field(alias="pass")
    warn: int
    fail: int


class ObserverReport(WireModel):
    generated_at: UtcDateTime
    seed: str
    profile: str
    full_history: bool
    families: list[ObserverFamily]
    summary: ObserverSummary
