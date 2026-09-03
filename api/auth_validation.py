"""Shared auth validation rules and user-facing error messages."""
from __future__ import annotations

from typing import Any

PASSWORD_MIN_LENGTH = 7
PASSWORD_MAX_LENGTH = 128
USERNAME_MIN_LENGTH = 7
USERNAME_MAX_LENGTH = 32
OTP_LENGTH = 4
IDENTIFIER_MIN_LENGTH = 3

FIELD_LABELS: dict[str, str] = {
    "email": "Email",
    "otp": "Verification code",
    "username": "Username",
    "password": "Password",
    "confirm_password": "Confirm password",
    "identifier": "Email or username",
    "verification_token": "Verification token",
    "new_password": "New password",
    "confirm_new_password": "Confirm new password",
    "reset_token": "Reset token",
}


def _field_label(loc: tuple[Any, ...] | list[Any]) -> str:
    field = str(loc[-1]) if loc else "field"
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def format_validation_error(err: dict[str, Any]) -> str:
    loc = err.get("loc") or ()
    label = _field_label(tuple(loc))
    err_type = str(err.get("type", ""))
    ctx = err.get("ctx") or {}

    if err_type == "string_too_short":
        min_len = ctx.get("min_length", "")
        return f"{label} must be at least {min_len} characters."
    if err_type == "string_too_long":
        max_len = ctx.get("max_length", "")
        return f"{label} must be at most {max_len} characters."
    if err_type == "value_error":
        msg = str(err.get("msg", ""))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        return msg if msg else f"{label} is invalid."
    if err_type in {"missing", "value_error.missing"}:
        return f"{label} is required."

    msg = str(err.get("msg", ""))
    if msg.startswith("String should have at least"):
        min_len = ctx.get("min_length", "")
        return f"{label} must be at least {min_len} characters."
    if msg:
        return f"{label}: {msg}"
    return f"{label} is invalid."


def format_validation_errors(errors: list[dict[str, Any]]) -> list[str]:
    return [format_validation_error(err) for err in errors]
