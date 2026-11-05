"""Ports: services the identity domain needs from outside, described as interfaces.

Infrastructure provides the implementation (argon2); the domain only sees the Protocol.
"""

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...
