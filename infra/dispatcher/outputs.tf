output "function_name" {
  description = "Name of the dispatcher Lambda function"
  value       = aws_lambda_function.dispatcher.function_name
}

output "function_arn" {
  description = "ARN of the dispatcher Lambda function"
  value       = aws_lambda_function.dispatcher.arn
}
