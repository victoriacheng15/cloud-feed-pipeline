resource "aws_dynamodb_table" "dedup_table" {
  name         = "extractor-dedup-store"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "article_hash"

  attribute {
    name = "article_hash"
    type = "S"
  }
}

resource "aws_s3_bucket" "config_bucket" {
  bucket_prefix = "cloud-feed-pipeline-config-"
}

resource "aws_s3_bucket_public_access_block" "config_bucket_pab" {
  bucket                  = aws_s3_bucket.config_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "config_bucket_versioning" {
  bucket = aws_s3_bucket.config_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "initial_feeds" {
  bucket = aws_s3_bucket.config_bucket.id
  key    = "feeds.json"
  source = "${path.module}/../../feeds.json"
  etag   = filemd5("${path.module}/../../feeds.json")
}
