resource "aws_sns_topic" "extractor_events" {
  name = "${var.project_name}-topic"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-dlq"
  message_retention_seconds = 1209600 # 14-day retention
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "pipeline_queue" {
  name                       = "${var.project_name}-queue"
  visibility_timeout_seconds = 180 # 6x Lambda timeout (30s)
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_policy" "sqs_sns_policy" {
  queue_url = aws_sqs_queue.pipeline_queue.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.pipeline_queue.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_sns_topic.extractor_events.arn }
      }
    }]
  })
}

resource "aws_sns_topic_subscription" "queue_subscription" {
  topic_arn = aws_sns_topic.extractor_events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.pipeline_queue.arn
}
