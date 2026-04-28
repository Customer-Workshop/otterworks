#!/bin/bash
set -euo pipefail

echo "Initializing LocalStack resources..."

# S3 Buckets
awslocal s3 mb s3://otterworks-files
awslocal s3 mb s3://otterworks-data-lake

# SQS Queue
awslocal sqs create-queue --queue-name otterworks-notifications

# SNS Topic
awslocal sns create-topic --name otterworks-events

# DynamoDB Tables
awslocal dynamodb create-table \
  --table-name otterworks-file-metadata \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

awslocal dynamodb create-table \
  --table-name otterworks-audit-events \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

echo "LocalStack initialization complete!"
