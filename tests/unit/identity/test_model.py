from datetime import UTC, datetime, timedelta

import pytest

from kinetic.identity.domain.errors import InvalidEmail, WeakPassword
from kinetic.identity.domain.model import SESSION_LIFETIME, Account, Email, Person, Session, hash_token
from kinetic.shared_kernel import new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


class FakeHasher:
    """Stands in for argon2 so the domain is tested without the library."""

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class TestEmail:
    def test_parse_normalizes_case_and_whitespace(self):
        assert Email.parse("  Maya@Example.COM ") == Email("maya@example.com")

    @pytest.mark.parametrize("raw", ["", "maya", "maya@", "maya@example", "ma ya@example.com"])
    def test_rejects_malformed_addresses(self, raw):
        with pytest.raises(InvalidEmail):
            Email.parse(raw)

    def test_constructor_rejects_unnormalized_value(self):
        with pytest.raises(InvalidEmail):
            Email("Maya@example.com")


class TestPerson:
    def test_register_assigns_a_fresh_person_id(self):
        a = Person.register("Maya", Email("maya@example.com"), T0)
        b = Person.register("Maya", Email("maya@example.com"), T0)
        assert a.id != b.id


class TestAccount:
    def test_stores_the_hash_not_the_password(self):
        account = Account.open(new_person_id(), "correct horse", FakeHasher(), T0)
        assert account.password_hash != "correct horse"
        assert account.verify("correct horse", FakeHasher())
        assert not account.verify("wrong password", FakeHasher())

    def test_rejects_short_passwords(self):
        with pytest.raises(WeakPassword):
            Account.open(new_person_id(), "short", FakeHasher(), T0)


class TestSession:
    def test_stores_only_the_hash_of_the_token(self):
        session, token = Session.start(new_person_id(), T0)
        assert session.token_hash == hash_token(token)
        assert token not in session.token_hash

    def test_tokens_are_unique(self):
        person = new_person_id()
        assert Session.start(person, T0)[1] != Session.start(person, T0)[1]

    def test_valid_until_lifetime_ends(self):
        session, _ = Session.start(new_person_id(), T0)
        assert session.is_valid_at(T0)
        assert session.is_valid_at(T0 + SESSION_LIFETIME - timedelta(seconds=1))
        assert not session.is_valid_at(T0 + SESSION_LIFETIME)
