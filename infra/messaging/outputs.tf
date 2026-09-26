output "topic_arn" {
  value = aws_sns_topic.extractor_events.arn
}

output "queue_arn" {
  value = aws_sqs_queue.pipeline_queue.arn
}

output "queue_url" {
  value = aws_sqs_queue.pipeline_queue.id
}

output "dlq_name" {
  value = aws_sqs_queue.dlq.name
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

