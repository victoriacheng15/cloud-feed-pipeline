resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-ops-alerts"
}

resource "aws_sns_topic_policy" "alerts_policy" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgePublish"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.alerts.arn
    }]
  })
}

# ------------------------------------------------------------------------------
# SLI 1 / SLO: Pipeline Latency (99% of events processed in < 45s)
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "dispatcher_latency" {
  alarm_name          = "${var.project_name}-dispatcher-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  extended_statistic  = "p99"
  threshold           = 45000 # 45 seconds in milliseconds
  alarm_description   = "SLO Violation: Dispatcher p99 execution duration exceeded 45 seconds."
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

# ------------------------------------------------------------------------------
# SLI 2 / SLO: DLQ Invariant (0 messages in Dead Letter Queue)
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.project_name}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "SLO Invariant: Messages detected in SQS Dead Letter Queue. Processing failures exceeded retry threshold."
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = var.dlq_name
  }
}

# ------------------------------------------------------------------------------
# Availability SLO: Dispatcher Error Rate (0 unhandled runtime errors)
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "dispatcher_errors" {
  alarm_name          = "${var.project_name}-dispatcher-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "SLO Violation: Dispatcher Lambda unhandled runtime exceptions detected."
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

# ------------------------------------------------------------------------------
# SLI 3 / SLO: Extractor Task Reliability (Non-zero exit code monitoring)
# ------------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "ecs_task_failure" {
  name        = "${var.project_name}-ecs-task-failure"
  description = "Captures extractor ECS task failures, crashes, or abnormal exit codes"

  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [var.ecs_cluster_arn]
      lastStatus = ["STOPPED"]
      containers = {
        exitCode = [{ "anything-but" : 0 }]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "ecs_failure_target" {
  rule      = aws_cloudwatch_event_rule.ecs_task_failure.name
  target_id = "${var.project_name}-ecs-failure-sns"
  arn       = aws_sns_topic.alerts.arn
}
