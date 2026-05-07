#!/bin/bash
set -euo pipefail

echo "Initializing LocalStack resources..."

# S3 Buckets
awslocal s3 mb s3://otterworks-files
awslocal s3 mb s3://otterworks-data-lake
awslocal s3 mb s3://otterworks-audit-archive

# SQS Queue
awslocal sqs create-queue --queue-name otterworks-notifications
awslocal sqs create-queue --queue-name otterworks-audit-events-queue
awslocal sqs create-queue --queue-name otterworks-search-events

# SNS Topic
awslocal sns create-topic --name otterworks-events
NOTIFICATION_QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/otterworks-notifications \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)
awslocal sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:000000000000:otterworks-events \
  --protocol sqs \
  --notification-endpoint "$NOTIFICATION_QUEUE_ARN"
AUDIT_QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/otterworks-audit-events-queue \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)
awslocal sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:000000000000:otterworks-events \
  --protocol sqs \
  --notification-endpoint "$AUDIT_QUEUE_ARN"
SEARCH_QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/otterworks-search-events \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)
awslocal sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:000000000000:otterworks-events \
  --protocol sqs \
  --notification-endpoint "$SEARCH_QUEUE_ARN"

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
