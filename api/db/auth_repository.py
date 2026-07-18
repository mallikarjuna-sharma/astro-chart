"""DynamoDB persistence for users and email OTP challenges."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import bcrypt
from botocore.exceptions import ClientError

from api.db.users_dynamo import get_users_table

OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5


class AuthRepositoryError(RuntimeError):
    """Domain error for auth persistence."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def _otp_pepper() -> bytes:
    return os.getenv("AUTH_OTP_PEPPER", "dev-otp-pepper-change-me").encode("utf-8")


def _hash_otp(email: str, otp: str) -> str:
    digest = hmac.new(
        _otp_pepper(),
        f"{_normalize_email(email)}:{otp}".encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()


def _user_pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _email_pk(email: str) -> str:
    return f"EMAIL#{_normalize_email(email)}"


def generate_otp_code() -> str:
    fixed = os.getenv("AUTH_FIXED_OTP", "").strip()
    if fixed:
        return fixed
    return f"{secrets.randbelow(10_000):04d}"


def save_otp_challenge(email: str, purpose: str = "signup") -> str:
    normalized = _normalize_email(email)
    code = generate_otp_code()
    now = datetime.now(timezone.utc)
    ttl = int(now.timestamp()) + OTP_TTL_SECONDS
    item = {
        "PK": _email_pk(normalized),
        "SK": f"OTP#{purpose}",
        "entity_type": "otp",
        "email": normalized,
        "otp_hash": _hash_otp(normalized, code),
        "attempts": 0,
        "max_attempts": OTP_MAX_ATTEMPTS,
        "created_at": _utc_now(),
        "expires_at": ttl,
        "ttl": ttl,
    }
    get_users_table().put_item(Item=item)
    return code


def verify_otp_challenge(email: str, otp: str, purpose: str = "signup") -> None:
    normalized = _normalize_email(email)
    otp = otp.strip()
    table = get_users_table()
    key = {"PK": _email_pk(normalized), "SK": f"OTP#{purpose}"}
    resp = table.get_item(Key=key)
    item = resp.get("Item")
    if not item:
        raise AuthRepositoryError("OTP expired or not found. Request a new code.")

    attempts = int(item.get("attempts", 0)) + 1
    if attempts > int(item.get("max_attempts", OTP_MAX_ATTEMPTS)):
        table.delete_item(Key=key)
        raise AuthRepositoryError("Too many invalid attempts. Request a new code.")

    if _hash_otp(normalized, otp) != item.get("otp_hash"):
        table.update_item(
            Key=key,
            UpdateExpression="SET attempts = :attempts",
            ExpressionAttributeValues={":attempts": attempts},
        )
        raise AuthRepositoryError("Invalid OTP.")

    table.delete_item(Key=key)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    resp = get_users_table().query(
        IndexName="by_email",
        KeyConditionExpression="email = :email",
        ExpressionAttributeValues={":email": _normalize_email(email)},
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    resp = get_users_table().query(
        IndexName="by_username",
        KeyConditionExpression="username = :username",
        ExpressionAttributeValues={":username": _normalize_username(username)},
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def create_user(email: str, username: str, password: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    normalized_username = _normalize_username(username)

    if get_user_by_email(normalized_email):
        raise AuthRepositoryError("An account with this email already exists.")
    if get_user_by_username(normalized_username):
        raise AuthRepositoryError("This username is already taken.")

    user_id = str(uuid4())
    now = _utc_now()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    item = {
        "PK": _user_pk(user_id),
        "SK": "PROFILE",
        "entity_type": "user",
        "user_id": user_id,
        "email": normalized_email,
        "username": normalized_username,
        "password_hash": password_hash,
        "email_verified": True,
        "created_at": now,
        "updated_at": now,
    }
    get_users_table().put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(PK)",
    )
    return _public_user(item)


def verify_password(user: dict[str, Any], password: str) -> bool:
    stored = user.get("password_hash", "")
    if not stored:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    resp = get_users_table().get_item(Key={"PK": _user_pk(user_id), "SK": "PROFILE"})
    item = resp.get("Item")
    return _public_user(item) if item else None


def update_password(user_id: str, new_password: str) -> None:
    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    table = get_users_table()
    key = {"PK": _user_pk(user_id), "SK": "PROFILE"}
    try:
        table.update_item(
            Key=key,
            UpdateExpression="SET password_hash = :ph, updated_at = :ua",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues={":ph": password_hash, ":ua": _utc_now()},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise AuthRepositoryError("User not found.") from exc
        raise


def _public_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": item["user_id"],
        "email": item["email"],
        "username": item["username"],
        "email_verified": bool(item.get("email_verified", False)),
        "created_at": item.get("created_at", ""),
    }
