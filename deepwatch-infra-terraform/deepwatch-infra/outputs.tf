###############################################################
# DeepWatch – Outputs
###############################################################

output "vpc_id" {
  description = "ID da VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "ID da subnet pública"
  value       = aws_subnet.public.id
}

output "ec2_instance_id" {
  description = "ID da instância EC2"
  value       = aws_instance.analytics.id
}

output "ec2_public_ip" {
  description = "IP público da EC2 (muda a cada novo deploy)"
  value       = aws_instance.analytics.public_ip
}

output "jupyter_url" {
  description = "URL de acesso ao Jupyter Notebook"
  value       = "http://${aws_instance.analytics.public_ip}:8888"
}

output "spark_ui_url" {
  description = "URL da Spark Web UI (disponível durante jobs)"
  value       = "http://${aws_instance.analytics.public_ip}:4040"
}

output "grafana_url" {
  description = "URL de acesso ao Grafana"
  value       = "http://${aws_instance.analytics.public_ip}:3000"
}

output "s3_raw_bucket" {
  description = "Nome do bucket Raw (Bronze)"
  value       = aws_s3_bucket.stage_raw.bucket
}

output "s3_trusted_bucket" {
  description = "Nome do bucket Trusted (Silver)"
  value       = aws_s3_bucket.trusted.bucket
}

output "s3_refined_bucket" {
  description = "Nome do bucket Refined (Gold)"
  value       = aws_s3_bucket.client.bucket
}

output "s3_athena_results_bucket" {
  description = "Nome do bucket de resultados do Athena"
  value       = aws_s3_bucket.athena_results.bucket
}

output "lambda_etl1_name" {
  description = "Nome da Lambda ETL1 (Raw → Trusted)"
  value       = aws_lambda_function.etl1.function_name
}

output "lambda_etl2_name" {
  description = "Nome da Lambda ETL2 (Trusted → Refined)"
  value       = aws_lambda_function.etl2.function_name
}

output "glue_database" {
  description = "Nome do banco de dados no Glue Catalog"
  value       = aws_glue_catalog_database.deepwatch.name
}

output "glue_crawler_trusted" {
  description = "Nome do Glue Crawler da camada Trusted"
  value       = aws_glue_crawler.trusted.name
}

output "glue_crawler_refined" {
  description = "Nome do Glue Crawler da camada Refined"
  value       = aws_glue_crawler.refined.name
}

output "athena_workgroup" {
  description = "Nome do Athena Workgroup"
  value       = aws_athena_workgroup.deepwatch.name
}

output "iam_role_arn" {
  description = "ARN da IAM Role (LabRole do AWS Academy)"
  value       = data.aws_iam_role.lab_role.arn
}

output "security_group_id" {
  description = "ID do Security Group da EC2"
  value       = aws_security_group.ec2_sg.id
}
