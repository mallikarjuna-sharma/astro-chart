"""Pydantic models for email OTP signup and password login."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from api.auth_validation import (
    OTP_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    IDENTIFIER_MIN_LENGTH,
)


class SendOtpRequest(BaseModel):
    email: EmailStr


class SendOtpResponse(BaseModel):
    message: str
    expires_in_seconds: int = 600
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=OTP_LENGTH, max_length=OTP_LENGTH)

    @field_validator("otp")
    @classmethod
    def otp_digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Verification code must be 4 digits.")
        return value


class VerifyOtpResponse(BaseModel):
    verification_token: str
    message: str = "Email verified. Complete your account setup."


class SignupRequest(BaseModel):
    email: EmailStr
    verification_token: str
    username: str = Field(min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("username")
    @classmethod
    def username_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) < USERNAME_MIN_LENGTH:
            raise ValueError(f"Username must be at least {USERNAME_MIN_LENGTH} characters.")
        if not normalized.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, dots, and underscores.")
        return normalized

    @field_validator("password")
    @classmethod
    def password_length(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return value

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password is not None and value != password:
            raise ValueError("Passwords do not match.")
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=IDENTIFIER_MIN_LENGTH, max_length=254)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class AuthUser(BaseModel):
    user_id: str
    email: str
    username: str
    email_verified: bool = True
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


class MeResponse(BaseModel):
    user: AuthUser
