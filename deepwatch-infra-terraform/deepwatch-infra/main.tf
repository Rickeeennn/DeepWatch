###############################################################
# DeepWatch – Infraestrutura de Processamento de Dados na AWS
# Arquitetura: VPC + EC2 (Jupyter/PySpark) + S3 Medallion
###############################################################

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

##########################
# VPC
##########################
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.project_name}-vpc" })
}

##########################
# Internet Gateway
##########################
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, { Name = "${var.project_name}-igw" })
}

##########################
# Public Subnet
##########################
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = merge(var.tags, { Name = "${var.project_name}-public-subnet" })
}

##########################
# Route Table
##########################
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(var.tags, { Name = "${var.project_name}-route-table" })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

##########################
# Security Group
# Adicionada porta 3000 para Grafana
##########################
resource "aws_security_group" "ec2_sg" {
  name        = "${var.project_name}-ec2-sg"
  description = "Security group para EC2 com Jupyter/PySpark/Grafana"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Jupyter Notebook"
    from_port   = 8888
    to_port     = 8888
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "Spark Web UI"
    from_port   = 4040
    to_port     = 4040
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.project_name}-ec2-sg" })
}

##########################
# IAM – AWS Academy usa LabRole pré-existente
##########################
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

data "aws_iam_instance_profile" "lab_profile" {
  name = "LabInstanceProfile"
}

##########################
# EC2 – Jupyter + PySpark + Grafana
##########################
resource "aws_instance" "analytics" {
  ami                    = var.ec2_ami
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  iam_instance_profile   = data.aws_iam_instance_profile.lab_profile.name
  key_name               = var.key_pair_name

  root_block_device {
    volume_size = var.ec2_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/scripts/setup.sh", {
    project_name    = var.project_name
    raw_bucket      = aws_s3_bucket.stage_raw.bucket
    trusted_bucket  = aws_s3_bucket.trusted.bucket
    client_bucket   = aws_s3_bucket.client.bucket
    aws_region      = var.aws_region
  }))

  tags = merge(var.tags, { Name = "${var.project_name}-analytics-ec2" })
}

##########################
# S3 – Stage/Raw (Bronze)
##########################
resource "aws_s3_bucket" "stage_raw" {
  bucket        = "${var.project_name}-stage-raw-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, { Name = "${var.project_name}-stage-raw", Layer = "bronze" })
}

resource "aws_s3_bucket_versioning" "stage_raw" {
  bucket = aws_s3_bucket.stage_raw.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "stage_raw" {
  bucket = aws_s3_bucket.stage_raw.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "stage_raw" {
  bucket                  = aws_s3_bucket.stage_raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

##########################
# S3 – Trusted (Silver)
##########################
resource "aws_s3_bucket" "trusted" {
  bucket        = "${var.project_name}-trusted-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, { Name = "${var.project_name}-trusted", Layer = "silver" })
}

resource "aws_s3_bucket_versioning" "trusted" {
  bucket = aws_s3_bucket.trusted.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "trusted" {
  bucket = aws_s3_bucket.trusted.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "trusted" {
  bucket                  = aws_s3_bucket.trusted.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

##########################
# S3 – Client/Refined (Gold)
##########################
resource "aws_s3_bucket" "client" {
  bucket        = "${var.project_name}-client-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, { Name = "${var.project_name}-client", Layer = "gold" })
}

resource "aws_s3_bucket_versioning" "client" {
  bucket = aws_s3_bucket.client.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "client" {
  bucket = aws_s3_bucket.client.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "client" {
  bucket                  = aws_s3_bucket.client.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

##########################
# S3 – Athena Query Results
##########################
resource "aws_s3_bucket" "athena_results" {
  bucket        = "${var.project_name}-athena-results-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, { Name = "${var.project_name}-athena-results" })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

##########################
# Lambda – Empacotamento dos ZIPs
##########################

# ETL1: raw → trusted
data "archive_file" "etl1_zip" {
  type        = "zip"
  source_file = "${path.module}/../../Sensor/Cloud/etl_raw_to_trusted_lambda.py"
  output_path = "${path.module}/lambda_packages/etl1.zip"
}

# ETL2: trusted → refined
data "archive_file" "etl2_zip" {
  type        = "zip"
  source_file = "${path.module}/../../Sensor/Cloud/etl_trusted_to_refined_lambda.py"
  output_path = "${path.module}/lambda_packages/etl2.zip"
}

##########################
# Lambda – ETL1: Raw → Trusted
##########################
resource "aws_lambda_function" "etl1" {
  function_name    = "${var.project_name}-etl1-raw-to-trusted"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "etl_raw_to_trusted_lambda.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.etl1_zip.output_path
  source_code_hash = data.archive_file.etl1_zip.output_base64sha256
  timeout          = 300   # 5 minutos — suficiente para processar vários tanques
  memory_size      = 512   # pandas precisa de memória razoável

  environment {
    variables = {
      RAW_BUCKET     = aws_s3_bucket.stage_raw.bucket
      TRUSTED_BUCKET = aws_s3_bucket.trusted.bucket
    }
  }

  layers = [var.pandas_lambda_layer_arn]

  tags = merge(var.tags, { Name = "${var.project_name}-etl1" })
}

##########################
# Lambda – ETL2: Trusted → Refined
##########################
resource "aws_lambda_function" "etl2" {
  function_name    = "${var.project_name}-etl2-trusted-to-refined"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "etl_trusted_to_refined_lambda.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.etl2_zip.output_path
  source_code_hash = data.archive_file.etl2_zip.output_base64sha256
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      TRUSTED_BUCKET = aws_s3_bucket.trusted.bucket
      REFINED_BUCKET = aws_s3_bucket.client.bucket
    }
  }

  layers = [var.pandas_lambda_layer_arn]

  tags = merge(var.tags, { Name = "${var.project_name}-etl2" })
}

##########################
# Glue – Database
##########################
resource "aws_glue_catalog_database" "deepwatch" {
  name        = "${var.project_name}_${var.environment}"
  description = "Catálogo de dados DeepWatch — camadas Trusted e Refined"
}

##########################
# Glue – Crawler: Trusted
##########################
resource "aws_glue_crawler" "trusted" {
  name          = "${var.project_name}-crawler-trusted"
  role          = data.aws_iam_role.lab_role.arn
  database_name = aws_glue_catalog_database.deepwatch.name
  description   = "Cataloga os CSVs da camada Trusted (schema wide por tanque)"

  s3_target {
    path = "s3://${aws_s3_bucket.trusted.bucket}/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
      Tables     = { AddOrUpdateBehavior = "MergeNewColumns" }
    }
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  tags = var.tags
}

##########################
# Glue – Crawler: Refined
##########################
resource "aws_glue_crawler" "refined" {
  name          = "${var.project_name}-crawler-refined"
  role          = data.aws_iam_role.lab_role.arn
  database_name = aws_glue_catalog_database.deepwatch.name
  description   = "Cataloga os CSVs da camada Refined (particionado por platform_id/tank_id)"

  s3_target {
    path = "s3://${aws_s3_bucket.client.bucket}/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
      Tables     = { AddOrUpdateBehavior = "MergeNewColumns" }
    }
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  tags = var.tags
}

##########################
# Athena – Workgroup
##########################
resource "aws_athena_workgroup" "deepwatch" {
  name        = "${var.project_name}-${var.environment}"
  description = "Workgroup DeepWatch — consultas no Data Lake"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/query-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = var.tags
}
