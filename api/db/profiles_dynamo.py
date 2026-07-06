"""DynamoDB client for the JyotishProfiles table."""
from __future__ import annotations

import os
from functools import lru_cache

import boto3

from api.db.dynamo import DynamoDBNotConfiguredError


def _profiles_table_name() -> str:
    name = os.getenv("DYNAMODB_PROFILES_TABLE_NAME", "").strip()
    if not name:
        raise DynamoDBNotConfiguredError(
            "Set DYNAMODB_PROFILES_TABLE_NAME (e.g. JyotishProfiles)."
        )
    return name


@lru_cache(maxsize=1)
def get_profiles_table():
    region = os.getenv("AWS_REGION", "ap-south-1").strip() or "ap-south-1"
    kwargs: dict = {"region_name": region}
    endpoint = os.getenv("AWS_ENDPOINT_URL", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    resource = boto3.resource("dynamodb", **kwargs)
    return resource.Table(_profiles_table_name())
