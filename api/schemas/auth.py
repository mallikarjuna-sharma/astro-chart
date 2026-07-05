"""Pydantic models for email OTP signup and password login."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class SendOtpRequest(BaseModel):
    email: EmailStr


class SendOtpResponse(BaseModel):
    message: str
    expires_in_seconds: int = 600
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=4)

    @field_validator("otp")
    @classmethod
    def otp_digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP must be 4 digits")
        return value


class VerifyOtpResponse(BaseModel):
    verification_token: str
    message: str = "Email verified. Complete your account setup."


class SignupRequest(BaseModel):
    email: EmailStr
    verification_token: str
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def username_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, dots, and underscores")
        return normalized

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password is not None and value != password:
            raise ValueError("Passwords do not match")
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


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
