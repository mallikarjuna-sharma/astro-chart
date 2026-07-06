"""DynamoDB client for JyotishProfilesCharts (legacy alias: PyJHoraBirthCharts)."""
from __future__ import annotations

from api.db.dynamo_common import DynamoDBNotConfiguredError, dynamo_client_error
from api.db.profiles_charts_dynamo import get_profiles_charts_table

# Backward-compatible alias used by legacy chart_repository.
get_table = get_profiles_charts_table

__all__ = ["DynamoDBNotConfiguredError", "dynamo_client_error", "get_table", "get_profiles_charts_table"]
