"""HTTP request and response shapes. Pydantic validates input before it reaches a use case."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from kinetic.identity.application.services import TokenPair


# Caps the input to argon2, so a huge password can't be used to burn CPU.
MAX_PASSWORD_LENGTH = 128


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    refresh_token: str

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokenResponse":
        return cls(access_token=pair.access_token, expires_at=pair.access_token_expires_at, refresh_token=pair.refresh_token)
