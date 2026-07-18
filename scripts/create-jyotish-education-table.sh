#!/usr/bin/env bash
# Create JyotishEducationAnalysis DynamoDB table for the /education-analysis page.
#
# One item per birth profile (partition key = profile_id). Stores the four LLM
# report payloads (results / macro_clusters / report / chart_facts) plus the
# rendered HTML, all gzip+base64 encoded so the ~660 KB results payload fits
# inside DynamoDB's 400 KB per-item limit. A GSI on user_id lets us list every
# analysis owned by a logged-in user.
#
# Usage: ./scripts/create-jyotish-education-table.sh [aws-region]
set -euo pipefail

REGION="${1:-${AWS_REGION:-ap-south-1}}"
TABLE_NAME="${DYNAMODB_EDUCATION_TABLE_NAME:-JyotishEducationAnalysis}"

echo "Creating table ${TABLE_NAME} in ${REGION}..."

aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${TABLE_NAME}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=profile_id,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
  --key-schema \
    AttributeName=profile_id,KeyType=HASH \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "by_user",
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]'

echo "Waiting for table to become ACTIVE..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${TABLE_NAME}"

echo "Done. Table ${TABLE_NAME} is ready in ${REGION}."
echo "Add DYNAMODB_EDUCATION_TABLE_NAME=${TABLE_NAME} to your .env."
