"""DynamoDB client for PyJHoraBirthCharts."""
from __future__ import annotations

import os
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError


class DynamoDBNotConfiguredError(RuntimeError):
    """Raised when required DynamoDB environment variables are missing."""


def _table_name() -> str:
    name = os.getenv("DYNAMODB_TABLE_NAME", "").strip()
    if not name:
        raise DynamoDBNotConfiguredError(
            "Set DYNAMODB_TABLE_NAME (e.g. PyJHoraBirthCharts)."
        )
    return name


@lru_cache(maxsize=1)
def get_table():
    region = os.getenv("AWS_REGION", "ap-south-1").strip() or "ap-south-1"
    kwargs: dict = {"region_name": region}
    endpoint = os.getenv("AWS_ENDPOINT_URL", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    resource = boto3.resource("dynamodb", **kwargs)
    return resource.Table(_table_name())


def dynamo_client_error(exc: ClientError) -> str:
    err = exc.response.get("Error", {})
    return err.get("Message") or err.get("Code") or str(exc)
