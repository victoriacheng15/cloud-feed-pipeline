terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "OpenTofu"
      Repository  = "victoriacheng15/serverless-ingestion-engine"
      Environment = var.environment
    }
  }
}

locals {
  namespaced_project_name = "${var.project_name}-${var.environment}"
}

module "messaging" {
  source       = "./messaging"
  project_name = local.namespaced_project_name
}

module "storage" {
  source       = "./storage"
  project_name = local.namespaced_project_name
}

module "extractor" {
  source              = "./extractor"
  project_name        = local.namespaced_project_name
  aws_region          = var.aws_region
  vpc_id              = var.vpc_id
  public_subnet_ids   = var.public_subnet_ids
  ecr_repository_url  = var.ecr_repository_url
  sns_topic_arn       = module.messaging.topic_arn
  config_bucket_name  = module.storage.config_bucket_name
  config_bucket_arn   = module.storage.config_bucket_arn
  is_schedule_enabled = var.environment == "prod"
}

module "dispatcher" {
  source              = "./dispatcher"
  project_name        = local.namespaced_project_name
  queue_arn           = module.messaging.queue_arn
  dynamodb_table_name = module.storage.table_name
  dynamodb_table_arn  = module.storage.table_arn
  discord_webhook_url = var.discord_webhook_url
}

module "observability" {
  source               = "./observability"
  project_name         = local.namespaced_project_name
  dlq_name             = module.messaging.dlq_name
  lambda_function_name = module.dispatcher.function_name
  ecs_cluster_arn      = module.extractor.cluster_arn
}

