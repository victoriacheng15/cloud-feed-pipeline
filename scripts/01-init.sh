#!/usr/bin/env bash
set -ex

echo "=== Initializing LocalStack resources for Cloud Feed Pipeline ==="

export AWS_DEFAULT_REGION="ca-central-1"

# 1. S3 Configuration Bucket & Feed Registry
echo "--> Creating S3 configuration bucket..."
awslocal s3 mb s3://cloud-feed-pipeline-config
if [ -f /tmp/feeds.json ]; then
    awslocal s3 cp /tmp/feeds.json s3://cloud-feed-pipeline-config/feeds.json
    echo "--> Uploaded feeds.json to S3"
fi

# 2. SQS Dead-Letter Queue & Main Pipeline Queue
echo "--> Creating SQS queues..."
awslocal sqs create-queue --queue-name cloud-feed-pipeline-dlq
awslocal sqs create-queue --queue-name cloud-feed-pipeline-queue

# 3. SNS Ingestion Topic
echo "--> Creating SNS topic..."
awslocal sns create-topic --name cloud-feed-pipeline-topic

# 4. Subscribe SQS to SNS
echo "--> Subscribing SQS queue to SNS topic..."
awslocal sns subscribe \
    --topic-arn arn:aws:sns:ca-central-1:000000000000:cloud-feed-pipeline-topic \
    --protocol sqs \
    --notification-endpoint arn:aws:sqs:ca-central-1:000000000000:cloud-feed-pipeline-queue

# 5. DynamoDB Idempotency Table
echo "--> Creating DynamoDB articles table..."
awslocal dynamodb create-table \
    --table-name cloud-feed-pipeline-articles \
    --attribute-definitions AttributeName=article_hash,AttributeType=S \
    --key-schema AttributeName=article_hash,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

echo "=== LocalStack initialization complete! ==="
