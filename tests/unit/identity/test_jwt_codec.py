from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from kinetic.identity.domain.errors import InvalidAccessToken
from kinetic.identity.domain.tokens import AccessClaims
from kinetic.identity.infrastructure.jwt_codec import JwtAccessTokenCodec
from kinetic.shared_kernel import new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
SECRET = "test-secret-that-is-at-least-32-characters-long"


@pytest.fixture
def codec() -> JwtAccessTokenCodec:
    return JwtAccessTokenCodec(SECRET)


@pytest.fixture
def claims() -> AccessClaims:
    return AccessClaims(person_id=new_person_id(), session_id=uuid4(), expires_at=T0 + timedelta(minutes=15))


def test_round_trip(codec, claims):
    assert codec.read(codec.issue(claims), at=T0) == claims


def test_payload_holds_identity_only(codec, claims):
    payload = jwt.decode(codec.issue(claims), options={"verify_signature": False})
    assert set(payload) == {"sub", "sid", "exp"}


def test_rejected_from_the_moment_it_expires(codec, claims):
    token = codec.issue(claims)
    assert codec.read(token, at=claims.expires_at - timedelta(seconds=1))
    with pytest.raises(InvalidAccessToken, match="expired"):
        codec.read(token, at=claims.expires_at)


def test_rejects_token_signed_with_another_secret(codec, claims):
    forged = JwtAccessTokenCodec("another-secret-that-is-also-32-characters").issue(claims)
    with pytest.raises(InvalidAccessToken):
        codec.read(forged, at=T0)


def test_rejects_tampered_payload(codec, claims):
    header, _, signature = codec.issue(claims).split(".")
    other = jwt.encode({"sub": str(new_person_id()), "sid": str(uuid4()), "exp": claims.expires_at}, SECRET)
    tampered = f"{header}.{other.split('.')[1]}.{signature}"
    with pytest.raises(InvalidAccessToken):
        codec.read(tampered, at=T0)


def test_rejects_unsigned_alg_none_token(codec, claims):
    unsigned = jwt.encode({"sub": str(claims.person_id), "sid": str(claims.session_id), "exp": claims.expires_at}, None, algorithm="none")
    with pytest.raises(InvalidAccessToken):
        codec.read(unsigned, at=T0)


def test_rejects_garbage(codec):
    with pytest.raises(InvalidAccessToken):
        codec.read("not-a-jwt", at=T0)
