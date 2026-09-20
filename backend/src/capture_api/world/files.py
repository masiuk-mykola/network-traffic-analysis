from collections.abc import Sequence
from urllib.parse import quote

from capture_api.world.filebytes import carve_files
from capture_api.world.rng import Stream, stable_int
from capture_api.world.types import FileData, FileSpec, Row

PURGE_RATE = 0.03
"""Share of carved files flagged ``purged`` (a seeded "quota" clean-up)."""

EXTRACTION_FAILED_MIME = "application/json"
EXTRACTION_FAILED_BODY = b'{"error":"extraction_failed"}'
"""The trap download: HTTP 200 with a JSON error body, not the file."""

PATH_SEPARATOR_NAME = "..\\Rechnungen/Q3.pdf"
"""The one seeded name carrying both path separators."""

ATTACHMENT_NAMES: tuple[str, ...] = (
    "Frachtraten-Q3-Übersicht.xlsm",
    "Rechnung_Überfällig_2025.xlsm",
    "Tarifänderung-Oktober.xlsm",
    "Zollerklärung-Nr-4471.pdf",
    "Lieferschein_Ürgüp_2211.pdf",
    "Frete-Marítimo-Setembro.xlsx",
    "Packliste_Håkon.xlsx",
    "Angebot_Küstenlogistik.docx",
    "quarterly-freight-summary.xlsx",
    "purchase-order-88213.pdf",
    "container-manifest.csv",
    "remittance-advice.pdf",
)

DOWNLOAD_NAMES: tuple[str, ...] = (
    "price-list.pdf",
    "route-map.png",
    "terminal-photo.jpg",
    "driver-handbook.pdf",
    "schedule-export.zip",
    "customs-form.pdf",
    "Übersichtsplan-Hafen.pdf",
    "Fährzeiten.csv",
    "logo-header.png",
    "tariff-2026.xlsx",
    "release-notes.txt",
    "catalogue.zip",
)

_MIME_BY_SUFFIX: dict[str, str] = {
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".gz": "application/gzip",
}

_SIZE_RANGE: dict[str, tuple[int, int]] = {
    "smtp_attachment": (18_000, 920_000),
    "http_body": (4_000, 6_200_000),
}


def mime_for_name(name: str) -> str:
    lowered = name.lower()
    for suffix, mime in _MIME_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            return mime
    return "application/octet-stream"


def is_purged(seed: str, session_id: int, ordinal: int) -> bool:
    return stable_int(seed, "file-purged", session_id, ordinal, bits=20) < int(
        PURGE_RATE * (1 << 20)
    )


def choose_trap_session(seed: str, candidates: Sequence[int]) -> int | None:
    if not candidates:
        return None
    ordered = sorted(candidates)
    return ordered[stable_int(seed, "file-trap", len(ordered)) % len(ordered)]


def file_spec(
    seed: str,
    session_id: int,
    ordinal: int,
    source: str,
    *,
    name: str | None = None,
    size: int | None = None,
    purged: bool | None = None,
    trap: bool = False,
) -> FileSpec:
    if source not in _SIZE_RANGE:
        raise ValueError(f"unknown carved-file source: {source}")
    stream = Stream(seed, "file-spec", session_id, ordinal)
    pool = ATTACHMENT_NAMES if source == "smtp_attachment" else DOWNLOAD_NAMES
    chosen = name if name is not None else stream.choice(pool)
    low, high = _SIZE_RANGE[source]
    chosen_size = size if size is not None else stream.randint(low, high)
    return FileSpec(
        name=chosen,
        mime=mime_for_name(chosen),
        size=max(1, chosen_size),
        source="smtp_attachment" if source == "smtp_attachment" else "http_body",
        purged=is_purged(seed, session_id, ordinal) if purged is None else purged,
        trap=trap,
    )


def file_specs(
    seed: str,
    session_id: int,
    source: str,
    count: int,
    *,
    names: Sequence[str] = (),
    trap: bool = False,
    path_separator_name: bool = False,
) -> tuple[FileSpec, ...]:
    specs: list[FileSpec] = []
    for ordinal in range(max(0, count)):
        pinned: str | None = None
        if ordinal == 0 and path_separator_name:
            pinned = PATH_SEPARATOR_NAME
        elif ordinal < len(names):
            pinned = names[ordinal]
        specs.append(
            file_spec(
                seed,
                session_id,
                ordinal,
                source,
                name=pinned,
                purged=False if (trap and ordinal == 0) else None,
                trap=trap and ordinal == 0,
            )
        )
    return tuple(specs)


def files_for_row(seed: str, row: Row) -> tuple[FileData, ...]:
    return carve_files(seed, row)


def trap_payload() -> tuple[str, bytes]:
    return EXTRACTION_FAILED_MIME, EXTRACTION_FAILED_BODY


def ascii_fallback_name(name: str) -> str:
    return (
        "".join(
            character if 32 <= ord(character) < 127 and character not in '\\/"' else "_"
            for character in name
        )
        or "download"
    )


def content_disposition(name: str) -> str:
    return (
        f'attachment; filename="{ascii_fallback_name(name)}"; '
        f"filename*=UTF-8''{quote(name, safe='')}"
    )
