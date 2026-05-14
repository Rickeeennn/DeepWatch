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
  description = "IP público da EC2"
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

output "s3_stage_raw_bucket" {
  description = "Nome do bucket Stage/Raw (Bronze)"
  value       = aws_s3_bucket.stage_raw.bucket
}

output "s3_trusted_bucket" {
  description = "Nome do bucket Trusted (Silver)"
  value       = aws_s3_bucket.trusted.bucket
}

output "s3_client_bucket" {
  description = "Nome do bucket Client (Gold)"
  value       = aws_s3_bucket.client.bucket
}

output "iam_role_arn" {
  description = "ARN da IAM Role associada à EC2 (LabRole do AWS Academy)"
  value       = data.aws_iam_role.lab_role.arn
}

output "security_group_id" {
  description = "ID do Security Group da EC2"
  value       = aws_security_group.ec2_sg.id
}
