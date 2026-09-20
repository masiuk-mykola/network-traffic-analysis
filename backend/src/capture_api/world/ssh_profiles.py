from collections.abc import Mapping
from dataclasses import dataclass

from capture_api.world.tls_profiles import md5_hex


@dataclass(frozen=True, slots=True)
class SshProfile:
    key: str
    version: str
    kex: tuple[str, ...]
    encryption: tuple[str, ...]
    mac: tuple[str, ...]
    compression: tuple[str, ...]
    host_key_types: tuple[str, ...]

    @property
    def hassh_string(self) -> str:
        return ";".join(
            ",".join(values) for values in (self.kex, self.encryption, self.mac, self.compression)
        )

    @property
    def hassh(self) -> str:
        return md5_hex(self.hassh_string)


_MODERN_KEX = (
    "sntrup761x25519-sha512@openssh.com",
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "diffie-hellman-group-exchange-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group14-sha256",
)
_MODERN_ENC = (
    "chacha20-poly1305@openssh.com",
    "aes128-ctr",
    "aes192-ctr",
    "aes256-ctr",
    "aes128-gcm@openssh.com",
    "aes256-gcm@openssh.com",
)
_MODERN_MAC = (
    "umac-64-etm@openssh.com",
    "umac-128-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha1-etm@openssh.com",
    "hmac-sha2-256",
    "hmac-sha2-512",
)

SSH_CLIENT_PROFILES: tuple[SshProfile, ...] = (
    SshProfile(
        key="openssh-9",
        version="SSH-2.0-OpenSSH_9.6",
        kex=_MODERN_KEX,
        encryption=_MODERN_ENC,
        mac=_MODERN_MAC,
        compression=("none", "zlib@openssh.com"),
        host_key_types=("ssh-ed25519", "ecdsa-sha2-nistp256", "rsa-sha2-512", "rsa-sha2-256"),
    ),
    SshProfile(
        key="openssh-8",
        version="SSH-2.0-OpenSSH_8.9p1",
        kex=_MODERN_KEX[1:],
        encryption=_MODERN_ENC,
        mac=_MODERN_MAC,
        compression=("none", "zlib@openssh.com", "zlib"),
        host_key_types=("ssh-ed25519", "rsa-sha2-512", "rsa-sha2-256"),
    ),
    SshProfile(
        key="putty-like",
        version="SSH-2.0-TermClient_0.81",
        kex=(
            "curve25519-sha256",
            "ecdh-sha2-nistp256",
            "diffie-hellman-group-exchange-sha256",
            "diffie-hellman-group14-sha256",
        ),
        encryption=("aes256-ctr", "aes128-ctr", "chacha20-poly1305@openssh.com"),
        mac=("hmac-sha2-256", "hmac-sha2-512", "hmac-sha1"),
        compression=("none", "zlib"),
        host_key_types=("ssh-ed25519", "rsa-sha2-256"),
    ),
    SshProfile(
        key="automation-lib",
        version="SSH-2.0-AutomationLib_3.4",
        kex=("curve25519-sha256", "diffie-hellman-group14-sha256"),
        encryption=("aes128-ctr", "aes256-ctr"),
        mac=("hmac-sha2-256",),
        compression=("none",),
        host_key_types=("rsa-sha2-256",),
    ),
)

SSH_SERVER_PROFILES: tuple[SshProfile, ...] = (
    SshProfile(
        key="openssh-9-server",
        version="SSH-2.0-OpenSSH_9.6",
        kex=_MODERN_KEX,
        encryption=_MODERN_ENC,
        mac=_MODERN_MAC,
        compression=("none", "zlib@openssh.com"),
        host_key_types=("ssh-ed25519",),
    ),
    SshProfile(
        key="openssh-8-server",
        version="SSH-2.0-OpenSSH_8.9p1",
        kex=_MODERN_KEX[1:],
        encryption=_MODERN_ENC,
        mac=_MODERN_MAC,
        compression=("none", "zlib@openssh.com"),
        host_key_types=("rsa-sha2-512",),
    ),
)

_BY_HASSH: Mapping[str, SshProfile] = {p.hassh: p for p in SSH_CLIENT_PROFILES}


def ssh_client_by_hassh(hassh: str) -> SshProfile | None:
    return _BY_HASSH.get(hassh)
