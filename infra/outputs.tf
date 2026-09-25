output "sns_topic_arn" {
  description = "ARN of the SNS topic for feed extraction events"
  value       = module.messaging.topic_arn
}

output "sqs_queue_url" {
  description = "URL of the primary SQS processing queue"
  value       = module.messaging.queue_url
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB deduplication table"
  value       = module.storage.table_name
}

output "config_bucket_name" {
  description = "Name of the S3 bucket hosting feeds.json"
  value       = module.storage.config_bucket_name
}
