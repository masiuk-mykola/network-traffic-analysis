from capture_api.world.files import (
    ATTACHMENT_NAMES,
    DOWNLOAD_NAMES,
    EXTRACTION_FAILED_BODY,
    EXTRACTION_FAILED_MIME,
    PATH_SEPARATOR_NAME,
    PURGE_RATE,
    ascii_fallback_name,
    choose_trap_session,
    file_spec,
    file_specs,
    files_for_row,
    is_purged,
    mime_for_name,
    trap_payload,
)

from .factories import SEED, make_row


def test_names_include_non_ascii() -> None:
    assert any(not name.isascii() for name in ATTACHMENT_NAMES)
    assert any(not name.isascii() for name in DOWNLOAD_NAMES)


def test_the_path_separator_name_carries_both_separators() -> None:
    assert "\\" in PATH_SEPARATOR_NAME
    assert "/" in PATH_SEPARATOR_NAME
    specs = file_specs(SEED, 7, "http_body", 1, path_separator_name=True)
    assert specs[0].name == PATH_SEPARATOR_NAME
    assert specs[0].mime == "application/pdf"


def test_ascii_fallback_strips_separators_and_accents() -> None:
    assert ascii_fallback_name(PATH_SEPARATOR_NAME) == ".._Rechnungen_Q3.pdf"
    assert ascii_fallback_name("Fährzeiten.csv") == "F_hrzeiten.csv"
    assert ascii_fallback_name("") == "download"


def test_mime_follows_the_suffix() -> None:
    assert mime_for_name("a.pdf") == "application/pdf"
    assert mime_for_name("a.XLSM") == "application/vnd.ms-excel.sheet.macroEnabled.12"
    assert mime_for_name("a.bin") == "application/octet-stream"


def test_specs_are_deterministic() -> None:
    first = file_spec(SEED, 4242, 0, "smtp_attachment")
    second = file_spec(SEED, 4242, 0, "smtp_attachment")
    assert first == second
    assert first.name in ATTACHMENT_NAMES
    assert 18_000 <= first.size <= 920_000


def test_purge_rate_is_about_three_percent() -> None:
    purged = sum(is_purged(SEED, session, 0) for session in range(20_000))
    assert abs(purged / 20_000 - PURGE_RATE) < 0.01


def test_the_trap_file_is_flagged_and_never_purged() -> None:
    specs = file_specs(SEED, 99, "http_body", 2, trap=True)
    assert specs[0].trap is True
    assert specs[0].purged is False
    assert specs[1].trap is False


def test_trap_session_choice_is_stable() -> None:
    candidates = [5, 9, 11, 33]
    assert choose_trap_session(SEED, candidates) in candidates
    reversed_order = list(reversed(candidates))
    assert choose_trap_session(SEED, candidates) == choose_trap_session(SEED, reversed_order)
    assert choose_trap_session(SEED, []) is None


def test_trap_payload_is_the_json_error() -> None:
    mime, body = trap_payload()
    assert mime == EXTRACTION_FAILED_MIME == "application/json"
    assert body == EXTRACTION_FAILED_BODY == b'{"error":"extraction_failed"}'


def test_files_for_row_carries_identity_and_hashes() -> None:
    row = make_row("smtp", files=file_specs(SEED, 4242, "smtp_attachment", 1))
    carved = files_for_row(SEED, row)
    assert len(carved) == 1
    assert carved[0].id == f"f{row.id}-0"
    assert len(carved[0].sha256) == 64
    assert carved[0].source == "smtp_attachment"
