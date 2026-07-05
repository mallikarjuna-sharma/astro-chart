"""Signup/login business logic: OTP, JWT, SES email."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
import jwt
from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.db import auth_repository
from api.db.auth_repository import AuthRepositoryError
from api.db.dynamo import DynamoDBNotConfiguredError
from api.schemas.auth import (
    AuthResponse,
    AuthUser,
    LoginRequest,
    MeResponse,
    SendOtpRequest,
    SendOtpResponse,
    SignupRequest,
    VerifyOtpRequest,
    VerifyOtpResponse,
)

logger = logging.getLogger(__name__)

VERIFICATION_TOKEN_MINUTES = 15
ACCESS_TOKEN_DAYS = 7


class AuthServiceError(RuntimeError):
    """Recoverable auth failure surfaced as HTTP 400/409."""


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        raise AuthServiceError("JWT_SECRET is not configured on the server.")
    return secret


def _issue_token(payload: dict, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    body = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(body, _jwt_secret(), algorithm="HS256")


def _decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthServiceError("Invalid or expired token.") from exc
    if payload.get("type") != expected_type:
        raise AuthServiceError("Invalid token type.")
    return payload


def _dev_expose_otp() -> bool:
    if os.getenv("AUTH_FIXED_OTP", "0000").strip():
        return True
    return os.getenv("AUTH_DEV_EXPOSE_OTP", "").strip().lower() in {"1", "true", "yes"}


def _send_otp_email(email: str, otp: str) -> None:
    from_email = os.getenv("SES_FROM_EMAIL", "").strip()
    if not from_email:
        logger.warning("SES_FROM_EMAIL not set — OTP for %s: %s", email, otp)
        return

    region = os.getenv("SES_REGION", os.getenv("AWS_REGION", "ap-south-1")).strip()
    client = boto3.client("ses", region_name=region)
    subject = "Your JyotishAI verification code"
    body = (
        f"Your verification code is {otp}.\n\n"
        f"It expires in {auth_repository.OTP_TTL_SECONDS // 60} minutes.\n"
        "If you did not request this, you can ignore this email."
    )
    try:
        client.send_email(
            Source=from_email,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
    except ClientError as exc:
        logger.exception("SES send failed for %s", email)
        raise AuthServiceError("Could not send verification email. Try again later.") from exc


def send_signup_otp(body: SendOtpRequest) -> SendOtpResponse:
    email = body.email.strip().lower()
    try:
        if auth_repository.get_user_by_email(email):
            raise AuthServiceError("An account with this email already exists. Try logging in.")
        otp = auth_repository.save_otp_challenge(email)
    except DynamoDBNotConfiguredError as exc:
        raise AuthServiceError(str(exc)) from exc
    except AuthRepositoryError as exc:
        raise AuthServiceError(str(exc)) from exc

    _send_otp_email(email, otp)
    return SendOtpResponse(
        message="Verification code sent to your email.",
        expires_in_seconds=auth_repository.OTP_TTL_SECONDS,
        dev_otp=otp if _dev_expose_otp() else None,
    )


def verify_signup_otp(body: VerifyOtpRequest) -> VerifyOtpResponse:
    email = body.email.strip().lower()
    try:
        auth_repository.verify_otp_challenge(email, body.otp)
    except DynamoDBNotConfiguredError as exc:
        raise AuthServiceError(str(exc)) from exc
    except AuthRepositoryError as exc:
        raise AuthServiceError(str(exc)) from exc

    token = _issue_token(
        {"type": "email_verification", "email": email},
        timedelta(minutes=VERIFICATION_TOKEN_MINUTES),
    )
    return VerifyOtpResponse(verification_token=token)


def complete_signup(body: SignupRequest) -> AuthResponse:
    email = body.email.strip().lower()
    try:
        payload = _decode_token(body.verification_token, "email_verification")
    except AuthServiceError as exc:
        raise AuthServiceError("Email verification expired. Verify your OTP again.") from exc

    if payload.get("email") != email:
        raise AuthServiceError("Verification token does not match this email.")

    try:
        user = auth_repository.create_user(email, body.username, body.password)
    except DynamoDBNotConfiguredError as exc:
        raise AuthServiceError(str(exc)) from exc
    except AuthRepositoryError as exc:
        raise AuthServiceError(str(exc)) from exc

    access_token = _issue_token(
        {
            "type": "access",
            "sub": user["user_id"],
            "email": user["email"],
            "username": user["username"],
        },
        timedelta(days=ACCESS_TOKEN_DAYS),
    )
    return AuthResponse(access_token=access_token, user=AuthUser.model_validate(user))


def login(body: LoginRequest) -> AuthResponse:
    identifier = body.identifier.strip()
    try:
        if "@" in identifier:
            user_record = auth_repository.get_user_by_email(identifier)
        else:
            user_record = auth_repository.get_user_by_username(identifier)
    except DynamoDBNotConfiguredError as exc:
        raise AuthServiceError(str(exc)) from exc

    if not user_record or not auth_repository.verify_password(user_record, body.password):
        raise AuthServiceError("Invalid email/username or password.")

    user = {
        "user_id": user_record["user_id"],
        "email": user_record["email"],
        "username": user_record["username"],
        "email_verified": bool(user_record.get("email_verified", False)),
        "created_at": user_record.get("created_at", ""),
    }
    access_token = _issue_token(
        {
            "type": "access",
            "sub": user["user_id"],
            "email": user["email"],
            "username": user["username"],
        },
        timedelta(days=ACCESS_TOKEN_DAYS),
    )
    return AuthResponse(access_token=access_token, user=AuthUser.model_validate(user))


def get_current_user(authorization: str | None) -> MeResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = _decode_token(token, "access")
    except AuthServiceError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = payload.get("sub", "")
    try:
        user = auth_repository.get_user_by_id(user_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return MeResponse(user=AuthUser.model_validate(user))


def auth_http_error(exc: AuthServiceError) -> HTTPException:
    message = str(exc)
    status = 409 if "already" in message.lower() or "taken" in message.lower() else 400
    return HTTPException(status_code=status, detail=message)
