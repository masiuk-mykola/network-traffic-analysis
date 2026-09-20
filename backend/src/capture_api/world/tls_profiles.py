import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from capture_api.world.rng import Stream, stable_int

TLS10 = 0x0301
TLS11 = 0x0302
TLS12 = 0x0303
TLS13 = 0x0304

VERSION_NAMES: Mapping[int, str] = {
    TLS10: "TLS1.0",
    TLS11: "TLS1.1",
    TLS12: "TLS1.2",
    TLS13: "TLS1.3",
}

TLS13_CIPHERS: frozenset[int] = frozenset({0x1301, 0x1302, 0x1303})

CIPHER_NAMES: Mapping[int, str] = {
    0x000A: "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    0x002F: "TLS_RSA_WITH_AES_128_CBC_SHA",
    0x0033: "TLS_DHE_RSA_WITH_AES_128_CBC_SHA",
    0x0035: "TLS_RSA_WITH_AES_256_CBC_SHA",
    0x0039: "TLS_DHE_RSA_WITH_AES_256_CBC_SHA",
    0x003C: "TLS_RSA_WITH_AES_128_CBC_SHA256",
    0x003D: "TLS_RSA_WITH_AES_256_CBC_SHA256",
    0x0067: "TLS_DHE_RSA_WITH_AES_128_CBC_SHA256",
    0x006B: "TLS_DHE_RSA_WITH_AES_256_CBC_SHA256",
    0x009C: "TLS_RSA_WITH_AES_128_GCM_SHA256",
    0x009D: "TLS_RSA_WITH_AES_256_GCM_SHA384",
    0x009E: "TLS_DHE_RSA_WITH_AES_128_GCM_SHA256",
    0x009F: "TLS_DHE_RSA_WITH_AES_256_GCM_SHA384",
    0x00FF: "TLS_EMPTY_RENEGOTIATION_INFO_SCSV",
    0x1301: "TLS_AES_128_GCM_SHA256",
    0x1302: "TLS_AES_256_GCM_SHA384",
    0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0xC008: "TLS_ECDHE_ECDSA_WITH_3DES_EDE_CBC_SHA",
    0xC009: "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA",
    0xC00A: "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA",
    0xC012: "TLS_ECDHE_RSA_WITH_3DES_EDE_CBC_SHA",
    0xC013: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
    0xC014: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
    0xC023: "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256",
    0xC024: "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384",
    0xC027: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256",
    0xC028: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384",
    0xC02B: "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
    0xC02C: "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
    0xC02F: "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
    0xC030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    0xCCA8: "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCA9: "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCAA: "TLS_DHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
}

EXTENSION_NAMES: Mapping[int, str] = {
    0: "server_name",
    5: "status_request",
    10: "supported_groups",
    11: "ec_point_formats",
    13: "signature_algorithms",
    16: "application_layer_protocol_negotiation",
    18: "signed_certificate_timestamp",
    21: "padding",
    22: "encrypt_then_mac",
    23: "extended_master_secret",
    27: "compress_certificate",
    28: "record_size_limit",
    35: "session_ticket",
    43: "supported_versions",
    45: "psk_key_exchange_modes",
    51: "key_share",
    65281: "renegotiation_info",
}

GROUP_NAMES: Mapping[int, str] = {
    23: "secp256r1",
    24: "secp384r1",
    25: "secp521r1",
    29: "x25519",
    30: "x448",
    256: "ffdhe2048",
    257: "ffdhe3072",
    258: "ffdhe4096",
    259: "ffdhe6144",
    260: "ffdhe8192",
}

POINT_FORMAT_NAMES: Mapping[int, str] = {
    0: "uncompressed",
    1: "ansiX962_compressed_prime",
    2: "ansiX962_compressed_char2",
}

SIGNATURE_ALGORITHM_NAMES: Mapping[int, str] = {
    0x0201: "rsa_pkcs1_sha1",
    0x0203: "ecdsa_sha1",
    0x0401: "rsa_pkcs1_sha256",
    0x0403: "ecdsa_secp256r1_sha256",
    0x0501: "rsa_pkcs1_sha384",
    0x0503: "ecdsa_secp384r1_sha384",
    0x0601: "rsa_pkcs1_sha512",
    0x0603: "ecdsa_secp521r1_sha512",
    0x0804: "rsa_pss_rsae_sha256",
    0x0805: "rsa_pss_rsae_sha384",
    0x0806: "rsa_pss_rsae_sha512",
}

DEFAULT_SIGNATURE_ALGORITHMS: tuple[int, ...] = (
    0x0403,
    0x0804,
    0x0401,
    0x0503,
    0x0805,
    0x0501,
    0x0806,
    0x0601,
)


def cipher_name(code: int) -> str:
    return CIPHER_NAMES.get(code, f"0x{code:04X}")


def version_name(code: int) -> str:
    return VERSION_NAMES.get(code, f"0x{code:04X}")


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def _join(values: Iterable[int]) -> str:
    return "-".join(str(v) for v in values)


def ja3_string(
    version: int,
    ciphers: Iterable[int],
    extensions: Iterable[int],
    curves: Iterable[int],
    point_formats: Iterable[int],
) -> str:
    return ",".join(
        (str(version), _join(ciphers), _join(extensions), _join(curves), _join(point_formats))
    )


def ja3s_string(version: int, cipher: int, extensions: Iterable[int]) -> str:
    return f"{version},{cipher},{_join(extensions)}"


def _is_grease(value: int) -> bool:
    return value & 0x0F0F == 0x0A0A and value >> 8 == value & 0xFF


@dataclass(frozen=True, slots=True)
class TlsClientProfile:
    key: str
    label: str
    legacy_version: int
    ciphers: tuple[int, ...]
    extensions: tuple[int, ...]
    curves: tuple[int, ...]
    point_formats: tuple[int, ...]
    supported_versions: tuple[int, ...] = ()
    signature_algorithms: tuple[int, ...] = DEFAULT_SIGNATURE_ALGORITHMS
    alpn: tuple[str, ...] = ()
    _ja3_string: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = (*self.ciphers, *self.extensions, *self.curves)
        if any(_is_grease(v) for v in values):
            raise ValueError(f"{self.key}: GREASE values are not allowed")
        unknown = [e for e in self.extensions if e not in EXTENSION_NAMES]
        if unknown:
            raise ValueError(f"{self.key}: unsupported extensions {unknown}")
        if len(set(self.extensions)) != len(self.extensions):
            raise ValueError(f"{self.key}: duplicate extensions")
        pairs = (
            (43, bool(self.supported_versions), "supported_versions"),
            (16, bool(self.alpn), "alpn"),
            (10, bool(self.curves), "curves"),
            (11, bool(self.point_formats), "point_formats"),
        )
        for ext, present, name in pairs:
            if (ext in self.extensions) != present:
                raise ValueError(f"{self.key}: extension {ext} and {name} must go together")
        if TLS13 in self.supported_versions and 51 not in self.extensions:
            raise ValueError(f"{self.key}: TLS 1.3 needs key_share (51)")
        if 0 not in self.extensions:
            raise ValueError(f"{self.key}: server_name (0) is required")
        object.__setattr__(
            self,
            "_ja3_string",
            ja3_string(
                self.legacy_version, self.ciphers, self.extensions, self.curves, self.point_formats
            ),
        )

    @property
    def ja3_string(self) -> str:
        return self._ja3_string

    @property
    def ja3(self) -> str:
        return md5_hex(self._ja3_string)

    @property
    def max_version(self) -> int:
        return max(self.supported_versions) if self.supported_versions else self.legacy_version

    @property
    def cipher_names(self) -> tuple[str, ...]:
        return tuple(cipher_name(c) for c in self.ciphers)


@dataclass(frozen=True, slots=True)
class TlsServerProfile:
    stack: str
    legacy_version: int
    cipher: int
    extensions: tuple[int, ...]
    selected_version: int
    alpn: str | None

    @property
    def ja3s_string(self) -> str:
        return ja3s_string(self.legacy_version, self.cipher, self.extensions)

    @property
    def ja3s(self) -> str:
        return md5_hex(self.ja3s_string)

    @property
    def version_name(self) -> str:
        return version_name(self.selected_version)

    @property
    def cipher_name(self) -> str:
        return cipher_name(self.cipher)


@dataclass(frozen=True, slots=True)
class TlsServerStack:
    key: str
    label: str
    allow_tls13: bool
    cipher_preference: tuple[int, ...]
    tls12_extension_order: tuple[int, ...]
    tls13_extension_order: tuple[int, ...] = (43, 51)
    alpn_preference: tuple[str, ...] = ("h2", "http/1.1")


def server_hello(client: TlsClientProfile, stack: TlsServerStack) -> TlsServerProfile:
    offered = set(client.ciphers)
    alpn = next((p for p in stack.alpn_preference if p in client.alpn), None)
    if stack.allow_tls13 and TLS13 in client.supported_versions:
        tls13 = [c for c in stack.cipher_preference if c in TLS13_CIPHERS and c in offered]
        tls13 = tls13 or [c for c in client.ciphers if c in TLS13_CIPHERS]
        if tls13:
            return TlsServerProfile(
                stack=stack.key,
                legacy_version=TLS12,
                cipher=tls13[0],
                extensions=stack.tls13_extension_order,
                selected_version=TLS13,
                alpn=alpn,
            )
    legacy = [c for c in stack.cipher_preference if c not in TLS13_CIPHERS and c in offered]
    legacy = legacy or [c for c in client.ciphers if c not in TLS13_CIPHERS and c != 0x00FF]
    if not legacy:
        raise ValueError(f"{client.key} offers no cipher {stack.key} can use")
    version = min(client.legacy_version, TLS12)
    sent = set(client.extensions)
    extensions = tuple(
        e for e in stack.tls12_extension_order if e in sent and (e != 16 or alpn is not None)
    )
    return TlsServerProfile(
        stack=stack.key,
        legacy_version=version,
        cipher=legacy[0],
        extensions=extensions,
        selected_version=version,
        alpn=alpn if 16 in extensions else None,
    )


_CHROMIUM_CIPHERS = (
    0x1301,
    0x1302,
    0x1303,
    0xC02B,
    0xC02F,
    0xC02C,
    0xC030,
    0xCCA9,
    0xCCA8,
    0xC013,
    0xC014,
    0x009C,
    0x009D,
    0x002F,
    0x0035,
)
_OPENSSL_CIPHERS = (
    0x1302,
    0x1303,
    0x1301,
    0xC02C,
    0xC030,
    0x009F,
    0xCCA9,
    0xCCA8,
    0xCCAA,
    0xC02B,
    0xC02F,
    0x009E,
    0xC024,
    0xC028,
    0x006B,
    0xC023,
    0xC027,
    0x0067,
    0xC00A,
    0xC014,
    0x0039,
    0xC009,
    0xC013,
    0x0033,
    0x009D,
    0x009C,
    0x003D,
    0x003C,
    0x0035,
    0x002F,
    0x00FF,
)

_BROWSER_GECKO_CIPHERS: tuple[int, ...] = (
    0x1301,
    0x1303,
    0x1302,
    0xC02B,
    0xC02F,
    0xCCA9,
    0xCCA8,
    0xC02C,
    0xC030,
    0xC00A,
    0xC009,
    0xC013,
    0xC014,
    0x009C,
    0x009D,
    0x002F,
    0x0035,
)
_BROWSER_GECKO_SIGALGS: tuple[int, ...] = (
    0x0403,
    0x0503,
    0x0603,
    0x0804,
    0x0805,
    0x0806,
    0x0401,
    0x0501,
    0x0601,
    0x0203,
    0x0201,
)
_BROWSER_WEBKIT_CIPHERS: tuple[int, ...] = (
    0x1301,
    0x1302,
    0x1303,
    0xC02C,
    0xC02B,
    0xCCA9,
    0xC030,
    0xC02F,
    0xCCA8,
    0xC00A,
    0xC009,
    0xC014,
    0xC013,
    0x009D,
    0x009C,
    0x0035,
    0x002F,
    0xC008,
    0xC012,
    0x000A,
)
_APP_JVM_CLIENT_CIPHERS: tuple[int, ...] = (
    0x1302,
    0x1301,
    0x1303,
    0xC02C,
    0xC02B,
    0xCCA9,
    0xC030,
    0xCCA8,
    0xC02F,
    0x009F,
    0xCCAA,
    0x009E,
    0xC024,
    0xC028,
    0xC023,
    0xC027,
    0xC00A,
    0xC014,
    0xC009,
    0xC013,
    0x009D,
    0x009C,
    0x003D,
    0x003C,
    0x0035,
    0x002F,
    0x00FF,
)
_OS_SYSTEM_TLS_CIPHERS: tuple[int, ...] = (
    0xC02C,
    0xC02B,
    0xC030,
    0xC02F,
    0x009F,
    0x009E,
    0xC024,
    0xC023,
    0xC028,
    0xC027,
    0xC00A,
    0xC009,
    0xC014,
    0xC013,
    0x009D,
    0x009C,
    0x003D,
    0x003C,
    0x0035,
    0x002F,
    0x000A,
)
_OS_SYSTEM_TLS_SIGALGS: tuple[int, ...] = (
    0x0804,
    0x0805,
    0x0806,
    0x0401,
    0x0501,
    0x0601,
    0x0403,
    0x0503,
    0x0603,
    0x0201,
    0x0203,
)
_SCRIPT_PYTHON_CIPHERS: tuple[int, ...] = (
    0x1302,
    0x1303,
    0x1301,
    0xC02C,
    0xC030,
    0xC02B,
    0xC02F,
    0xCCA9,
    0xCCA8,
    0x009F,
    0x009E,
    0xCCAA,
    0xC024,
    0xC028,
    0xC023,
    0xC027,
    0xC00A,
    0xC014,
    0xC009,
    0xC013,
    0x009D,
    0x009C,
    0x003D,
    0x003C,
    0x0035,
    0x002F,
    0x00FF,
)
_SRV_REVERSE_PROXY_CIPHERS: tuple[int, ...] = (
    0x1301,
    0x1302,
    0x1303,
    0xC02F,
    0xC02B,
    0xC030,
    0xC02C,
    0xCCA8,
    0xCCA9,
    0xC013,
    0xC014,
    0x009C,
    0x009D,
    0x002F,
    0x0035,
)
_SRV_WINDOWS_WEB_CIPHERS: tuple[int, ...] = (
    0xC030,
    0xC02F,
    0xC02C,
    0xC02B,
    0x009F,
    0x009E,
    0xC028,
    0xC027,
    0x009D,
    0x009C,
    0x003D,
    0x003C,
    0x0035,
    0x002F,
)
_SRV_CDN_EDGE_CIPHERS: tuple[int, ...] = (
    0x1301,
    0x1303,
    0x1302,
    0xC02B,
    0xC02F,
    0xCCA9,
    0xCCA8,
    0xC02C,
    0xC030,
    0xC013,
    0xC014,
    0x009C,
    0x002F,
)
_SRV_APP_JVM_CIPHERS: tuple[int, ...] = (
    0x1302,
    0x1301,
    0x1303,
    0xC030,
    0xC02F,
    0xC02C,
    0xC02B,
    0x009F,
    0x009E,
    0xC014,
    0xC013,
    0x009D,
    0x009C,
    0x0035,
    0x002F,
)
_SRV_MINIMAL_CIPHERS: tuple[int, ...] = (
    0xC02F,
    0xC030,
    0xC02B,
    0xC02C,
    0xCCA8,
    0xCCA9,
    0xC013,
    0xC014,
    0x009C,
    0x009D,
    0x002F,
    0x0035,
)

BACKGROUND_CLIENT_PROFILES: tuple[TlsClientProfile, ...] = (
    TlsClientProfile(
        key="browser-chromium",
        label="Chromium-based browser",
        legacy_version=TLS12,
        ciphers=_CHROMIUM_CIPHERS,
        extensions=(0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43, 27, 21),
        curves=(29, 23, 24),
        point_formats=(0,),
        supported_versions=(TLS13, TLS12),
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="browser-gecko",
        label="Gecko-based browser",
        legacy_version=TLS12,
        ciphers=_BROWSER_GECKO_CIPHERS,
        extensions=(0, 23, 65281, 10, 11, 35, 16, 5, 51, 43, 13, 45, 28, 21),
        curves=(29, 23, 24, 25, 256, 257),
        point_formats=(0,),
        supported_versions=(TLS13, TLS12),
        signature_algorithms=_BROWSER_GECKO_SIGALGS,
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="browser-webkit",
        label="WebKit-based browser",
        legacy_version=TLS12,
        ciphers=_BROWSER_WEBKIT_CIPHERS,
        extensions=(0, 23, 65281, 10, 11, 16, 5, 13, 18, 51, 45, 43, 21),
        curves=(29, 23, 24, 25),
        point_formats=(0,),
        supported_versions=(TLS13, TLS12, TLS11, TLS10),
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="app-desktop-chat",
        label="Desktop chat app (embedded browser runtime)",
        legacy_version=TLS12,
        ciphers=_CHROMIUM_CIPHERS,
        extensions=(0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43, 21),
        curves=(29, 23, 24),
        point_formats=(0,),
        supported_versions=(TLS13, TLS12),
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="app-jvm-client",
        label="JVM HTTP client",
        legacy_version=TLS12,
        ciphers=_APP_JVM_CLIENT_CIPHERS,
        extensions=(5, 10, 11, 13, 23, 43, 45, 51, 65281, 0),
        curves=(29, 23, 24, 25, 30, 256, 257),
        point_formats=(0,),
        supported_versions=(TLS13, TLS12),
    ),
    TlsClientProfile(
        key="os-system-tls",
        label="Operating-system TLS stack",
        legacy_version=TLS12,
        ciphers=_OS_SYSTEM_TLS_CIPHERS,
        extensions=(0, 5, 10, 11, 13, 35, 16, 23, 65281),
        curves=(29, 23, 24),
        point_formats=(0,),
        signature_algorithms=_OS_SYSTEM_TLS_SIGALGS,
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="tool-cli-openssl",
        label="Command-line HTTP tool (OpenSSL)",
        legacy_version=TLS12,
        ciphers=_OPENSSL_CIPHERS,
        extensions=(0, 11, 10, 35, 16, 22, 23, 13, 43, 45, 51, 21),
        curves=(29, 23, 30, 25, 24),
        point_formats=(0, 1, 2),
        supported_versions=(TLS13, TLS12),
        alpn=("h2", "http/1.1"),
    ),
    TlsClientProfile(
        key="script-python",
        label="Scripted client (Python)",
        legacy_version=TLS12,
        ciphers=_SCRIPT_PYTHON_CIPHERS,
        extensions=(0, 11, 10, 35, 22, 23, 13, 43, 45, 51),
        curves=(29, 23, 30, 25, 24, 256, 257, 258, 259, 260),
        point_formats=(0, 1, 2),
        supported_versions=(TLS13, TLS12, TLS11, TLS10),
    ),
)
"""The ~8 background client stacks (browser-like and app-like)."""

VENDOR_UPDATER_PROFILE = TlsClientProfile(
    key="vendor-updater",
    label="Vendor update agent",
    legacy_version=TLS12,
    ciphers=(0xC02F, 0xC030, 0xC013, 0xC014, 0x009C, 0x009D, 0x002F, 0x0035),
    extensions=(0, 10, 11, 13, 23, 65281),
    curves=(23, 24),
    point_formats=(0,),
    signature_algorithms=(0x0401, 0x0501, 0x0601, 0x0804, 0x0403),
)
"""Shared by the ~40 HQ hosts beaconing to the (benign) vendor update service."""

SERVER_STACKS: Mapping[str, TlsServerStack] = {
    stack.key: stack
    for stack in (
        TlsServerStack(
            key="srv-reverse-proxy",
            label="Reverse proxy (OpenSSL)",
            allow_tls13=True,
            cipher_preference=_SRV_REVERSE_PROXY_CIPHERS,
            tls12_extension_order=(65281, 0, 11, 35, 16, 23),
        ),
        TlsServerStack(
            key="srv-windows-web",
            label="Windows web server",
            allow_tls13=False,
            cipher_preference=_SRV_WINDOWS_WEB_CIPHERS,
            tls12_extension_order=(65281, 23, 16, 11),
        ),
        TlsServerStack(
            key="srv-cdn-edge",
            label="CDN edge",
            allow_tls13=True,
            cipher_preference=_SRV_CDN_EDGE_CIPHERS,
            tls12_extension_order=(65281, 11, 16, 23),
            tls13_extension_order=(51, 43),
        ),
        TlsServerStack(
            key="srv-app-jvm",
            label="Application server (JVM)",
            allow_tls13=True,
            cipher_preference=_SRV_APP_JVM_CIPHERS,
            tls12_extension_order=(65281, 23, 11, 0),
        ),
        TlsServerStack(
            key="srv-minimal",
            label="Minimal TLS 1.2 server",
            allow_tls13=False,
            cipher_preference=_SRV_MINIMAL_CIPHERS,
            tls12_extension_order=(65281, 11, 23),
        ),
    )
}
"""Server TLS stacks. ``srv-minimal`` is meant for the C2 server; the rest are general."""

GENERAL_SERVER_STACKS: tuple[str, ...] = (
    "srv-reverse-proxy",
    "srv-windows-web",
    "srv-cdn-edge",
    "srv-app-jvm",
)


def stack_for_host(seed: str, host: str) -> TlsServerStack:
    index = stable_int(seed, "tls-server-stack", host.lower()) % len(GENERAL_SERVER_STACKS)
    return SERVER_STACKS[GENERAL_SERVER_STACKS[index]]


KNOWN_CLIENT_PROFILES: tuple[TlsClientProfile, ...] = (
    *BACKGROUND_CLIENT_PROFILES,
    VENDOR_UPDATER_PROFILE,
)

_C2_CIPHER_POOL: tuple[int, ...] = (
    0xC02B,
    0xC02F,
    0xC02C,
    0xC030,
    0xCCA8,
    0xCCA9,
    0xC013,
    0xC014,
    0xC009,
    0xC00A,
    0x009C,
    0x009D,
    0x002F,
    0x0035,
    0x003C,
    0x003D,
    0x000A,
    0xC027,
    0xC028,
)
_C2_OPTIONAL_EXTENSIONS: tuple[int, ...] = (23, 35, 65281, 5, 22)
_C2_CURVES: tuple[int, ...] = (29, 23, 24, 25)
_C2_SIGNATURE_ALGORITHMS: tuple[int, ...] = (0x0401, 0x0501, 0x0601, 0x0403, 0x0503, 0x0804)


def derive_c2_client_profile(stream: Stream, avoid_ja3: Iterable[str] = ()) -> TlsClientProfile:
    avoid = set(avoid_ja3) | {p.ja3 for p in KNOWN_CLIENT_PROFILES}
    for attempt in range(64):
        s = stream.fork("c2-client-profile", attempt)
        ciphers = s.sample(_C2_CIPHER_POOL, s.randint(7, 12))
        if 0xC02F not in ciphers and 0xC030 not in ciphers:
            ciphers.insert(s.randbelow(len(ciphers) + 1), 0xC02F)
        optional = s.sample(_C2_OPTIONAL_EXTENSIONS, s.randint(1, 4))
        tail = [10, 11, 13, *optional]
        s.shuffle(tail)
        curves = s.sample(_C2_CURVES, s.randint(2, 4))
        profile = TlsClientProfile(
            key="c2-client",
            label="Unidentified client",
            legacy_version=TLS12,
            ciphers=tuple(ciphers),
            extensions=(0, *tail),
            curves=tuple(curves),
            point_formats=(0,),
            signature_algorithms=_C2_SIGNATURE_ALGORITHMS,
        )
        if profile.ja3 not in avoid:
            return profile
    raise RuntimeError("could not derive a unique C2 client profile")  # pragma: no cover


def profile_index(
    extra: Iterable[TlsClientProfile] = (),
) -> dict[str, TlsClientProfile]:
    return {p.ja3: p for p in (*KNOWN_CLIENT_PROFILES, *extra)}
