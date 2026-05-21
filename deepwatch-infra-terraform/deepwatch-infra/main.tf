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
# (172.16.0.0 / 172.16.1.0 / 172.16.2.0 conforme diagrama)
##########################
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  # Rota padrão para a internet via IGW
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  # Nota: rotas "local" (172.16.x.0) são criadas automaticamente pela AWS
  # e não podem ser declaradas explicitamente no Terraform.

  tags = merge(var.tags, { Name = "${var.project_name}-route-table" })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

##########################
# Security Group
##########################
resource "aws_security_group" "ec2_sg" {
  name        = "${var.project_name}-ec2-sg"
  description = "Security group para EC2 com Jupyter/PySpark"
  vpc_id      = aws_vpc.main.id

  # Jupyter Notebook
  ingress {
    description = "Jupyter Notebook"
    from_port   = 8888
    to_port     = 8888
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Spark UI
  ingress {
    description = "Spark Web UI"
    from_port   = 4040
    to_port     = 4040
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Tráfego de saída liberado (para S3, pip, etc.)
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
# (voclabs não permite criar IAM Roles)
##########################
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

data "aws_iam_instance_profile" "lab_profile" {
  name = "LabInstanceProfile"
}

##########################
# EC2 – Jupyter + PySpark + Matplotlib
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
# S3 – Camada Stage/Raw (Bronze)
##########################
resource "aws_s3_bucket" "stage_raw" {
  bucket        = "${var.project_name}-stage-raw-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, {
    Name  = "${var.project_name}-stage-raw"
    Layer = "bronze"
  })
}

resource "aws_s3_bucket_versioning" "stage_raw" {
  bucket = aws_s3_bucket.stage_raw.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "stage_raw" {
  bucket = aws_s3_bucket.stage_raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
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
# S3 – Camada Trusted (Silver)
##########################
resource "aws_s3_bucket" "trusted" {
  bucket        = "${var.project_name}-trusted-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, {
    Name  = "${var.project_name}-trusted"
    Layer = "silver"
  })
}

resource "aws_s3_bucket_versioning" "trusted" {
  bucket = aws_s3_bucket.trusted.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "trusted" {
  bucket = aws_s3_bucket.trusted.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
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
# S3 – Camada Client (Gold)
##########################
resource "aws_s3_bucket" "client" {
  bucket        = "${var.project_name}-client-${var.environment}"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, {
    Name  = "${var.project_name}-client"
    Layer = "gold"
  })
}

resource "aws_s3_bucket_versioning" "client" {
  bucket = aws_s3_bucket.client.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "client" {
  bucket = aws_s3_bucket.client.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "client" {
  bucket                  = aws_s3_bucket.client.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
