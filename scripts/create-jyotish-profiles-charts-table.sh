#!/usr/bin/env bash
# Create JyotishProfilesCharts DynamoDB table (replaces PyJHoraBirthCharts).
# Usage: ./scripts/create-jyotish-profiles-charts-table.sh [aws-region]
set -euo pipefail

REGION="${1:-ap-south-1}"
TABLE_NAME="${DYNAMODB_PROFILES_CHARTS_TABLE_NAME:-JyotishProfilesCharts}"

echo "Creating table ${TABLE_NAME} in ${REGION}..."

aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${TABLE_NAME}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=profile_id,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "by_profile_id",
        "KeySchema": [{"AttributeName": "profile_id", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]'

echo "Waiting for table to become ACTIVE..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${TABLE_NAME}"
echo "Done. Table ${TABLE_NAME} is ready in ${REGION}."
