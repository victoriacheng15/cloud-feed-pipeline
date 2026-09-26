#!/usr/bin/env bash
set -ex

echo "=== Initializing LocalStack resources for Serverless Ingestion Engine ==="

export AWS_DEFAULT_REGION="ca-central-1"

# 1. S3 Configuration Bucket & Feed Registry
echo "--> Creating S3 configuration bucket..."
awslocal s3 mb s3://serverless-ingestion-engine-feeds
if [ -f /tmp/feeds.json ]; then
    awslocal s3 cp /tmp/feeds.json s3://serverless-ingestion-engine-feeds/feeds.json
    echo "--> Uploaded feeds.json to S3"
fi

# 2. SQS Dead-Letter Queue & Main Pipeline Queue
echo "--> Creating SQS queues..."
awslocal sqs create-queue --queue-name serverless-ingestion-engine-dlq
awslocal sqs create-queue --queue-name serverless-ingestion-engine-queue

# 3. SNS Ingestion Topic
echo "--> Creating SNS topic..."
awslocal sns create-topic --name serverless-ingestion-engine-topic

# 4. Subscribe SQS to SNS
echo "--> Subscribing SQS queue to SNS topic..."
awslocal sns subscribe \
    --topic-arn arn:aws:sns:ca-central-1:000000000000:serverless-ingestion-engine-topic \
    --protocol sqs \
    --notification-endpoint arn:aws:sqs:ca-central-1:000000000000:serverless-ingestion-engine-queue

# 5. DynamoDB Idempotency Table
echo "--> Creating DynamoDB articles table..."
awslocal dynamodb create-table \
    --table-name serverless-ingestion-engine \
    --attribute-definitions AttributeName=article_hash,AttributeType=S \
    --key-schema AttributeName=article_hash,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

echo "=== LocalStack initialization complete! ==="
