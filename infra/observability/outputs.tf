output "alerts_topic_arn" {
  description = "ARN of the SNS topic receiving operational SLO violation alerts"
  value       = aws_sns_topic.alerts.arn
}

output "dlq_alarm_arn" {
  description = "ARN of the CloudWatch alarm monitoring Dead Letter Queue messages"
  value       = aws_cloudwatch_metric_alarm.dlq_messages.arn
}

output "latency_alarm_arn" {
  description = "ARN of the CloudWatch alarm monitoring dispatcher latency"
  value       = aws_cloudwatch_metric_alarm.dispatcher_latency.arn
}

output "errors_alarm_arn" {
  description = "ARN of the CloudWatch alarm monitoring dispatcher error count"
  value       = aws_cloudwatch_metric_alarm.dispatcher_errors.arn
}
