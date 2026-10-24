"""Verify Supabase access tokens (F1 plan §4.1). Pure logic: no web framework imports.

Every failure raises UnauthenticatedError with a specific `reason` for the logs; clients
only ever see a generic 401 (AC11). If keys can't be fetched at all, the key provider
raises AuthUnavailableError (503), which is deliberately not caught here (AC13).
"""

from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from app.auth.errors import UnauthenticatedError

# Asymmetric only. This rules out "none" and HS256, so a public key can never be misused
# as an HMAC secret (algorithm confusion).
ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})
REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud"]
AUTHENTICATED_ROLE = "authenticated"


class KeyProvider(Protocol):
    async def get_key(self, kid: str) -> jwt.PyJWK: ...


@dataclass(frozen=True)
class VerifiedClaims:
    subject: str
    email: str | None
    display_name: str | None
    session_id: str | None


class TokenVerifier:
    def __init__(
        self,
        keys: KeyProvider,
        *,
        issuer: str,
        audience: str = AUTHENTICATED_ROLE,
        leeway_seconds: int = 30,
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway_seconds

    async def verify(self, token: str) -> VerifiedClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise UnauthenticatedError("malformed token") from exc

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise UnauthenticatedError(f"disallowed algorithm {algorithm!r}")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise UnauthenticatedError("token has no kid")

        key = await self._keys.get_key(kid)
        if key.algorithm_name != algorithm:
            raise UnauthenticatedError("token algorithm does not match its key")

        claims = self._decode(token, key, algorithm)
        return self._to_verified_claims(claims)

    def _decode(self, token: str, key: jwt.PyJWK, algorithm: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthenticatedError("token expired") from exc
        except jwt.InvalidSignatureError as exc:
            raise UnauthenticatedError("bad signature") from exc
        except jwt.InvalidIssuerError as exc:
            raise UnauthenticatedError("wrong issuer") from exc
        except jwt.InvalidAudienceError as exc:
            raise UnauthenticatedError("wrong audience") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise UnauthenticatedError(f"missing claim {exc.claim}") from exc
        except jwt.PyJWTError as exc:
            raise UnauthenticatedError(f"invalid token: {type(exc).__name__}") from exc
        return claims

    @staticmethod
    def _to_verified_claims(claims: dict[str, Any]) -> VerifiedClaims:
        if claims.get("role") != AUTHENTICATED_ROLE:
            raise UnauthenticatedError("role is not 'authenticated'")
        if claims.get("is_anonymous") is True:
            raise UnauthenticatedError("anonymous session")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise UnauthenticatedError("empty sub")
        return VerifiedClaims(
            subject=subject,
            email=_optional_str(claims.get("email")),
            display_name=_display_name(claims.get("user_metadata")),
            session_id=_optional_str(claims.get("session_id")),
        )


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _display_name(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    return _optional_str(metadata.get("full_name")) or _optional_str(metadata.get("name"))
