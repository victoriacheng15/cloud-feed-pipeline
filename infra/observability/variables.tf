variable "project_name" {
  type        = string
  description = "Project name prefix for observability resources"
}

variable "dlq_name" {
  type        = string
  description = "Name of the SQS Dead Letter Queue to monitor"
}

variable "lambda_function_name" {
  type        = string
  description = "Name of the dispatcher Lambda function to monitor"
}

variable "ecs_cluster_arn" {
  type        = string
  description = "ARN of the ECS cluster executing scheduled extraction tasks"
}
