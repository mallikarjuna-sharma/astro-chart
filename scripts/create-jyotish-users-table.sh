#!/usr/bin/env bash
# Create JyotishUsers DynamoDB table for signup/login auth.
# Usage: ./scripts/create-jyotish-users-table.sh [aws-region]
set -euo pipefail

REGION="${1:-ap-south-1}"
TABLE_NAME="${DYNAMODB_USERS_TABLE_NAME:-JyotishUsers}"

echo "Creating table ${TABLE_NAME} in ${REGION}..."

aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${TABLE_NAME}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=email,AttributeType=S \
    AttributeName=username,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "by_email",
        "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      },
      {
        "IndexName": "by_username",
        "KeySchema": [{"AttributeName": "username", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]'

echo "Waiting for table to become ACTIVE..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${TABLE_NAME}"

echo "Enabling TTL on attribute 'ttl'..."
aws dynamodb update-time-to-live \
  --region "${REGION}" \
  --table-name "${TABLE_NAME}" \
  --time-to-live-specification "Enabled=true, AttributeName=ttl"

echo "Done. Table ${TABLE_NAME} is ready in ${REGION}."
