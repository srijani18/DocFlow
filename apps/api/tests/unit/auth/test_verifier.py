import time
from typing import Any

import jwt
import pytest

from app.auth.errors import UnauthenticatedError, UnknownSigningKeyError
from app.auth.verifier import TokenVerifier
from tests.support.jwt import (
    TEST_ISSUER,
    StaticKeys,
    make_es256_key,
    make_rs256_key,
    supabase_claims,
)

ES = make_es256_key("es-1")
RS = make_rs256_key("rs-1")
OTHER = make_es256_key("es-1")  # same kid, different private key: a forged signature


@pytest.fixture
def verifier() -> TokenVerifier:
    return TokenVerifier(StaticKeys(ES, RS), issuer=TEST_ISSUER)


async def _rejected(verifier: TokenVerifier, token: str) -> UnauthenticatedError:
    with pytest.raises(UnauthenticatedError) as exc_info:
        await verifier.verify(token)
    return exc_info.value


@pytest.mark.parametrize("key", [ES, RS], ids=["ES256", "RS256"])
async def test_valid_tokens_are_accepted_for_both_algorithms(
    verifier: TokenVerifier, key: Any
) -> None:
    claims = supabase_claims()

    verified = await verifier.verify(key.sign(claims))

    assert verified.subject == claims["sub"]
    assert verified.email == "ada@example.com"
    assert verified.display_name == "Ada Lovelace"
    assert verified.session_id == claims["session_id"]


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"full_name": "  Ada Lovelace "}, "Ada Lovelace"),
        ({"name": "Ada"}, "Ada"),
        ({"full_name": "", "name": "Ada"}, "Ada"),
        ({}, None),
        (None, None),
    ],
)
async def test_display_name_comes_from_user_metadata(
    verifier: TokenVerifier, metadata: Any, expected: str | None
) -> None:
    verified = await verifier.verify(ES.sign(supabase_claims(user_metadata=metadata)))

    assert verified.display_name == expected


async def test_token_without_email_is_accepted(verifier: TokenVerifier) -> None:
    verified = await verifier.verify(ES.sign(supabase_claims(email=...)))

    assert verified.email is None


async def test_ac11_malformed_token_is_rejected(verifier: TokenVerifier) -> None:
    error = await _rejected(verifier, "not-a-jwt")
    assert "malformed" in error.reason


async def test_ac11_expired_token_is_rejected(verifier: TokenVerifier) -> None:
    now = int(time.time())
    error = await _rejected(verifier, ES.sign(supabase_claims(iat=now - 7200, exp=now - 31)))
    assert "expired" in error.reason


async def test_ac11_token_within_clock_skew_leeway_is_accepted(verifier: TokenVerifier) -> None:
    now = int(time.time())
    await verifier.verify(ES.sign(supabase_claims(iat=now - 3600, exp=now - 20)))


async def test_ac11_bad_signature_is_rejected(verifier: TokenVerifier) -> None:
    error = await _rejected(verifier, OTHER.sign(supabase_claims()))
    assert "signature" in error.reason


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"iss": "https://evil.example/auth/v1"}, "issuer"),
        ({"aud": "someone-else"}, "audience"),
        ({"role": "anon"}, "role"),
        ({"role": ...}, "role"),
        ({"is_anonymous": True}, "anonymous"),
        ({"sub": ...}, "sub"),
        ({"sub": ""}, "sub"),
        ({"exp": ...}, "exp"),
        ({"iat": ...}, "iat"),
    ],
)
async def test_ac11_wrong_or_missing_claims_are_rejected(
    verifier: TokenVerifier, override: dict[str, Any], reason: str
) -> None:
    error = await _rejected(verifier, ES.sign(supabase_claims(**override)))
    assert reason in error.reason


async def test_ac11_hs256_is_rejected_even_with_a_known_kid(verifier: TokenVerifier) -> None:
    # Algorithm confusion: an HMAC "signed" with public material must never verify.
    secret = "a-shared-secret-that-is-long-enough!"
    token = jwt.encode(supabase_claims(), secret, algorithm="HS256", headers={"kid": "es-1"})

    error = await _rejected(verifier, token)
    assert "algorithm" in error.reason


async def test_ac11_unsigned_alg_none_is_rejected(verifier: TokenVerifier) -> None:
    token = jwt.encode(supabase_claims(), "", algorithm="none", headers={"kid": "es-1"})

    error = await _rejected(verifier, token)
    assert "algorithm" in error.reason


async def test_ac11_header_algorithm_must_match_the_key(verifier: TokenVerifier) -> None:
    # An RS256 header pointing at an EC key: refuse rather than guess.
    token = RS.sign(supabase_claims(), headers={"kid": "es-1"})

    error = await _rejected(verifier, token)
    assert "algorithm" in error.reason


async def test_ac11_missing_kid_is_rejected(verifier: TokenVerifier) -> None:
    token = jwt.encode(supabase_claims(), ES.private_key, algorithm="ES256")

    error = await _rejected(verifier, token)
    assert "kid" in error.reason


async def test_ac11_unknown_kid_is_rejected(verifier: TokenVerifier) -> None:
    token = make_es256_key("not-published").sign(supabase_claims())

    with pytest.raises(UnknownSigningKeyError):
        await verifier.verify(token)
