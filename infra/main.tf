terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

module "messaging" {
  source = "./messaging"
}

module "storage" {
  source = "./storage"
}

module "extractor" {
  source             = "./extractor"
  aws_region         = var.aws_region
  vpc_id             = var.vpc_id
  public_subnet_ids  = var.public_subnet_ids
  ecr_repository_url = var.ecr_repository_url
  sns_topic_arn      = module.messaging.topic_arn
  config_bucket_name = module.storage.config_bucket_name
  config_bucket_arn  = module.storage.config_bucket_arn
}

module "dispatcher" {
  source              = "./dispatcher"
  queue_arn           = module.messaging.queue_arn
  dynamodb_table_name = module.storage.table_name
  dynamodb_table_arn  = module.storage.table_arn
  discord_webhook_url = var.discord_webhook_url
}
