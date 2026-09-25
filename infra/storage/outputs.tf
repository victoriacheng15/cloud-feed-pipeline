output "table_name" {
  value = aws_dynamodb_table.dedup_table.name
}

output "table_arn" {
  value = aws_dynamodb_table.dedup_table.arn
}

output "config_bucket_name" {
  value = aws_s3_bucket.config_bucket.id
}

output "config_bucket_arn" {
  value = aws_s3_bucket.config_bucket.arn
}
