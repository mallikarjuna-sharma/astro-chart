"""Shared DynamoDB helpers."""
from __future__ import annotations

from botocore.exceptions import ClientError


class DynamoDBNotConfiguredError(RuntimeError):
    """Raised when required DynamoDB environment variables are missing."""


def dynamo_client_error(exc: ClientError) -> str:
    err = exc.response.get("Error", {})
    return err.get("Message") or err.get("Code") or str(exc)
