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
