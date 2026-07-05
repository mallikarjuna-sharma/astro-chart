"""DynamoDB client for the JyotishUsers auth table."""
from __future__ import annotations

import os
from functools import lru_cache

import boto3

from api.db.dynamo import DynamoDBNotConfiguredError


def _users_table_name() -> str:
    name = os.getenv("DYNAMODB_USERS_TABLE_NAME", "").strip()
    if not name:
        raise DynamoDBNotConfiguredError(
            "Set DYNAMODB_USERS_TABLE_NAME (e.g. JyotishUsers)."
        )
    return name


@lru_cache(maxsize=1)
def get_users_table():
    region = os.getenv("AWS_REGION", "ap-south-1").strip() or "ap-south-1"
    kwargs: dict = {"region_name": region}
    endpoint = os.getenv("AWS_ENDPOINT_URL", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    resource = boto3.resource("dynamodb", **kwargs)
    return resource.Table(_users_table_name())
