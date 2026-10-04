variable "project_name" {
  type = string
}

variable "aws_region" {
  type = string
}


variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "ecr_repository_url" {
  type = string
}

variable "sns_topic_arn" {
  type = string
}

variable "config_bucket_name" {
  type = string
}

variable "config_bucket_arn" {
  type = string
}

variable "is_schedule_enabled" {
  type        = bool
  default     = true
  description = "Controls whether the EventBridge extractor schedule rule is enabled"
}

variable "max_articles" {
  type        = string
  default     = ""
  description = "Optional limit on articles published per run (useful in dev to send only 1 message)"
}


