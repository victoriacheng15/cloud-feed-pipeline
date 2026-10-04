output "cluster_arn" {
  value = aws_ecs_cluster.main.arn
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.extractor_task.arn
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "task_definition_family" {
  value = aws_ecs_task_definition.extractor_task.family
}

