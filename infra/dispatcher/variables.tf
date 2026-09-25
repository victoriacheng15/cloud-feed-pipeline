variable "queue_arn" {
  type = string
}

variable "dynamodb_table_name" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
}

variable "discord_webhook_url" {
  type      = string
  sensitive = true
}
