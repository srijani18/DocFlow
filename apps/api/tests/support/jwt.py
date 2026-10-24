"""Real signing keys and tokens for auth tests: no Supabase needed (F1 plan §10)."""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from app.auth.errors import UnknownSigningKeyError

TEST_SUPABASE_URL = "https://test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"
TEST_JWKS_URL = f"{TEST_ISSUER}/.well-known/jwks.json"


@dataclass(frozen=True)
class SigningKey:
    kid: str
    alg: str
    private_key: Any = field(repr=False)
    public_jwk: dict[str, Any] = field(repr=False)

    def sign(self, claims: dict[str, Any], *, headers: dict[str, Any] | None = None) -> str:
        return jwt.encode(
            claims,
            self.private_key,
            algorithm=self.alg,
            headers={"kid": self.kid, **(headers or {})},
        )


def make_es256_key(kid: str = "es-1") -> SigningKey:
    private = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    return SigningKey(
        kid, "ES256", private, {**public_jwk, "kid": kid, "alg": "ES256", "use": "sig"}
    )


def make_rs256_key(kid: str = "rs-1") -> SigningKey:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    return SigningKey(
        kid, "RS256", private, {**public_jwk, "kid": kid, "alg": "RS256", "use": "sig"}
    )


def jwks_document(*keys: SigningKey) -> dict[str, Any]:
    return {"keys": [key.public_jwk for key in keys]}


class StaticKeys:
    """KeyProvider for tests: a fixed set of keys, no HTTP."""

    def __init__(self, *keys: SigningKey) -> None:
        self._keys = {key.kid: jwt.PyJWK(key.public_jwk) for key in keys}

    async def get_key(self, kid: str) -> jwt.PyJWK:
        try:
            return self._keys[kid]
        except KeyError:
            raise UnknownSigningKeyError(kid) from None


def supabase_claims(**overrides: Any) -> dict[str, Any]:
    """Claims shaped like a Supabase access token for a signed-in user."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": TEST_ISSUER,
        "aud": "authenticated",
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 3600,
        "role": "authenticated",
        "is_anonymous": False,
        "email": "ada@example.com",
        "session_id": str(uuid.uuid4()),
        "user_metadata": {"full_name": "Ada Lovelace"},
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not ...}


# The key the integration-test app trusts (see `db_client`).
TEST_SIGNING_KEY = make_es256_key("test-key")


def bearer(**claim_overrides: Any) -> dict[str, str]:
    """Authorization header for a signed-in user; pass `sub=` to act as a known user."""
    return {"Authorization": f"Bearer {TEST_SIGNING_KEY.sign(supabase_claims(**claim_overrides))}"}
