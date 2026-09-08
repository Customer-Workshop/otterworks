output "table_name" {
  value = aws_dynamodb_table.projects.name
}

output "table_arn" {
  value = aws_dynamodb_table.projects.arn
}

output "role_name" {
  value = aws_iam_role.app.name
}

output "role_arn" {
  value = aws_iam_role.app.arn
}
