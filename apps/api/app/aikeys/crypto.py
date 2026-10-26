"""Encryption for workspaces' own AI provider keys (ADR-0008).

AES-256-GCM with a random 12-byte nonce per encryption and the workspace id as associated
data, under a versioned master key from `BYOK_MASTER_KEYS` ("v1:<base64 32 bytes>,v2:…").
The highest version encrypts; every listed version can decrypt, which allows rotation.
"""

import base64
import os
import re
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENTRY = re.compile(r"^v([0-9]+):([A-Za-z0-9+/=_-]+)$")
NONCE_BYTES = 12


class KeyBoxError(Exception):
    """A stored key can't be decrypted (tampered, wrong workspace or unknown master key)."""


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    nonce: bytes
    key_version: int


def parse_master_keys(value: str) -> dict[int, bytes]:
    keys: dict[int, bytes] = {}
    for raw in filter(None, (part.strip() for part in value.split(","))):
        match = _ENTRY.match(raw)
        if match is None:
            raise ValueError("BYOK_MASTER_KEYS entries look like v1:<base64 of 32 bytes>")
        key = base64.b64decode(match.group(2) + "=" * (-len(match.group(2)) % 4))
        if len(key) != 32:
            raise ValueError("each BYOK master key must be 32 bytes")
        keys[int(match.group(1))] = key
    if not keys:
        raise ValueError("BYOK_MASTER_KEYS has no keys")
    return keys


def generate_master_key(version: int = 1) -> str:
    return f"v{version}:{base64.b64encode(os.urandom(32)).decode()}"


class KeyBox:
    def __init__(self, master_keys: dict[int, bytes]) -> None:
        self._keys = master_keys
        self.current_version = max(master_keys)

    @classmethod
    def from_setting(cls, value: str) -> "KeyBox":
        return cls(parse_master_keys(value))

    def seal(self, workspace_id: uuid.UUID, plaintext: str) -> Sealed:
        nonce = os.urandom(NONCE_BYTES)
        aead = AESGCM(self._keys[self.current_version])
        ciphertext = aead.encrypt(nonce, plaintext.encode(), workspace_id.bytes)
        return Sealed(ciphertext=ciphertext, nonce=nonce, key_version=self.current_version)

    def open(self, workspace_id: uuid.UUID, sealed: Sealed) -> str:
        key = self._keys.get(sealed.key_version)
        if key is None:
            raise KeyBoxError(f"no master key version {sealed.key_version}")
        try:
            # The workspace id is authenticated: a ciphertext moved to another workspace's
            # row fails here instead of decrypting (ADR-0008).
            return AESGCM(key).decrypt(sealed.nonce, sealed.ciphertext, workspace_id.bytes).decode()
        except InvalidTag as exc:
            raise KeyBoxError("stored key failed authentication") from exc
