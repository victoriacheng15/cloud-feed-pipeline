variable "aws_region" {
  type        = string
  default     = "ca-central-1"
  description = "Target AWS region"
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
