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

awslocal dynamodb create-table \
  --table-name otterworks-notifications \
  --attribute-definitions \
    AttributeName=id,AttributeType=S \
    AttributeName=userId,AttributeType=S \
    AttributeName=createdAt,AttributeType=S \
  --key-schema \
    AttributeName=id,KeyType=HASH \
  --global-secondary-indexes \
    '[{"IndexName":"userId-createdAt-index","KeySchema":[{"AttributeName":"userId","KeyType":"HASH"},{"AttributeName":"createdAt","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
  --billing-mode PAY_PER_REQUEST

awslocal dynamodb create-table \
  --table-name otterworks-notification-preferences \
  --attribute-definitions AttributeName=userId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

awslocal dynamodb create-table \
  --table-name otterworks-folders \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

awslocal dynamodb create-table \
  --table-name otterworks-file-versions \
  --attribute-definitions \
    AttributeName=file_id,AttributeType=S \
    AttributeName=version,AttributeType=N \
  --key-schema \
    AttributeName=file_id,KeyType=HASH \
    AttributeName=version,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

awslocal dynamodb create-table \
  --table-name otterworks-file-shares \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

echo "LocalStack initialization complete!"
