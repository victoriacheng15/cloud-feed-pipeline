variable "aws_region" {
  type        = string
  default     = "ca-central-1"
  description = "Target AWS region"
}

variable "environment" {
  type        = string
  description = "Target deployment environment (dev or prod)"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "The environment variable must be either 'dev' or 'prod'."
  }
}

variable "project_name" {
  type        = string
  default     = "serverless-ingestion-engine"
  description = "Project name used as a common prefix for resource identifiers"
}

variable "vpc_id" {
  type        = string
  description = "Target VPC ID where subnets reside"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "List of public subnet IDs for ephemeral Fargate ENI allocation"
}

variable "ecr_repository_url" {
  type        = string
  description = "Repository URL containing the extractor Docker image"
}

variable "discord_webhook_url" {
  type        = string
  sensitive   = true
  description = "Destination Discord channel Webhook URL"
}
