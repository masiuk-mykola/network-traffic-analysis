import hashlib

import pytest

from capture_api.world.rng import Stream
from capture_api.world.tls_profiles import (
    BACKGROUND_CLIENT_PROFILES,
    KNOWN_CLIENT_PROFILES,
    SERVER_STACKS,
    TLS12,
    TLS13,
    TlsClientProfile,
    cipher_name,
    derive_c2_client_profile,
    ja3_string,
    ja3s_string,
    md5_hex,
    profile_index,
    server_hello,
    stack_for_host,
    version_name,
)

README_EXAMPLE = "769,47-53-5-10-49161-49162-49171-49172-50-56-19-4,0-10-11,23-24-25,0"


def test_ja3_of_a_known_string_is_its_md5() -> None:
    assert md5_hex(README_EXAMPLE) == hashlib.md5(README_EXAMPLE.encode()).hexdigest()  # noqa: S324
    assert md5_hex(README_EXAMPLE) == "ada70206e40642a3e4461f35503241d5"
    assert md5_hex("769,4-5-10-9-100-98-3-6-19-18-99,,,") == "de350869b8c85de67a350c8d186f11e6"


def test_ja3_string_layout() -> None:
    built = ja3_string(
        769,
        (47, 53, 5, 10, 49161, 49162, 49171, 49172, 50, 56, 19, 4),
        (0, 10, 11),
        (23, 24, 25),
        (0,),
    )
    assert built == README_EXAMPLE
    assert ja3_string(769, (4,), (), (), ()) == "769,4,,,"
    assert ja3s_string(771, 49199, (65281, 11, 23)) == "771,49199,65281-11-23"


def test_profile_ja3_matches_its_components() -> None:
    profile = BACKGROUND_CLIENT_PROFILES[0]
    expected = ja3_string(
        profile.legacy_version,
        profile.ciphers,
        profile.extensions,
        profile.curves,
        profile.point_formats,
    )
    assert profile.ja3_string == expected
    assert profile.ja3 == hashlib.md5(expected.encode()).hexdigest()  # noqa: S324
    assert profile.max_version == TLS13
    assert profile.cipher_names[0] == "TLS_AES_128_GCM_SHA256"


def test_about_eight_distinct_background_profiles() -> None:
    assert 7 <= len(BACKGROUND_CLIENT_PROFILES) <= 9
    ja3s = {p.ja3 for p in KNOWN_CLIENT_PROFILES}
    assert len(ja3s) == len(KNOWN_CLIENT_PROFILES)
    assert set(profile_index()) == ja3s


def test_every_client_gets_a_compatible_server_hello() -> None:
    c2 = derive_c2_client_profile(Stream("demo", "incident"))
    for client in (*KNOWN_CLIENT_PROFILES, c2):
        for stack in SERVER_STACKS.values():
            hello = server_hello(client, stack)
            assert hello.cipher in client.ciphers
            assert set(hello.extensions) <= set(client.extensions) | {43, 51}
            if hello.selected_version == TLS13:
                assert TLS13 in client.supported_versions
                assert hello.extensions == stack.tls13_extension_order
            else:
                assert hello.selected_version <= TLS12
            assert hello.ja3s == md5_hex(hello.ja3s_string)
            assert hello.version_name in {"TLS1.2", "TLS1.3"}


def test_c2_profile_is_deterministic_unique_and_tls12() -> None:
    a = derive_c2_client_profile(Stream("demo", "incident"))
    b = derive_c2_client_profile(Stream("demo", "incident"))
    other = derive_c2_client_profile(Stream("alpha", "incident"))
    assert a == b
    assert a.ja3 != other.ja3
    assert a.ja3 not in {p.ja3 for p in KNOWN_CLIENT_PROFILES}
    assert a.supported_versions == ()
    assert a.extensions[0] == 0
    hello = server_hello(a, SERVER_STACKS["srv-minimal"])
    assert hello.version_name == "TLS1.2"
    avoided = derive_c2_client_profile(Stream("demo", "incident"), avoid_ja3={a.ja3})
    assert avoided.ja3 != a.ja3
    assert profile_index([a])[a.ja3] is a


def test_stack_for_host_is_stable() -> None:
    assert stack_for_host("demo", "Docs.Example.org") == stack_for_host("demo", "docs.example.org")
    chosen = {stack_for_host("demo", f"h{i}.example.com").key for i in range(40)}
    assert len(chosen) > 1
    assert "srv-minimal" not in chosen


def test_invalid_profiles_are_rejected() -> None:
    base = BACKGROUND_CLIENT_PROFILES[0]
    with pytest.raises(ValueError, match="GREASE"):
        TlsClientProfile("g", "g", TLS12, (0x0A0A, 47), (0, 10, 11), (29,), (0,))
    with pytest.raises(ValueError, match="unsupported"):
        TlsClientProfile("u", "u", TLS12, (47,), (0, 99), (), ())
    with pytest.raises(ValueError, match="go together"):
        TlsClientProfile("a", "a", TLS12, (47,), (0,), (), (), alpn=("h2",))
    with pytest.raises(ValueError, match="server_name"):
        TlsClientProfile("s", "s", TLS12, (47,), (23,), (), ())
    with pytest.raises(ValueError, match="key_share"):
        TlsClientProfile("k", "k", TLS12, (4865,), (0, 43), (), (), supported_versions=(TLS13,))
    assert base.key == "browser-chromium"


def test_display_names() -> None:
    assert cipher_name(0xC02F) == "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
    assert cipher_name(0x1234) == "0x1234"
    assert version_name(TLS12) == "TLS1.2"
    assert version_name(0x9999) == "0x9999"
