###############################################################
# DeepWatch – Variáveis
###############################################################

variable "aws_region" {
  description = "Região AWS onde os recursos serão criados"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Nome do projeto (usado como prefixo nos recursos)"
  type        = string
  default     = "deepwatch"
}

variable "environment" {
  description = "Ambiente de deploy (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "O ambiente deve ser dev, staging ou prod."
  }
}

# ── Rede ────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR block da VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block da subnet pública"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_cidr_blocks" {
  description = "CIDRs com permissão de acesso SSH e Jupyter (restrinja em produção!)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ── EC2 ─────────────────────────────────────────────────────
variable "ec2_ami" {
  description = "AMI da instância EC2 (Amazon Linux 2023 padrão)"
  type        = string
  default     = "ami-0c101f26f147fa7fd" # Amazon Linux 2023 – us-east-1
}

variable "ec2_instance_type" {
  description = "Tipo da instância EC2"
  type        = string
  default     = "t3.large" # 2 vCPU / 8 GB – mínimo confortável para PySpark

  validation {
    condition     = can(regex("^(t3|t3a|m5|m6i|r5)\\.", var.ec2_instance_type))
    error_message = "Use instâncias t3, t3a, m5, m6i ou r5 para carga PySpark."
  }
}

variable "ec2_volume_size" {
  description = "Tamanho do disco raiz da EC2 em GB"
  type        = number
  default     = 30
}

variable "key_pair_name" {
  description = "Nome do Key Pair AWS para acesso SSH à EC2"
  type        = string
}

# ── S3 ──────────────────────────────────────────────────────
variable "s3_force_destroy" {
  description = "Permite destruir buckets não-vazios (útil em dev; desabilite em prod)"
  type        = bool
  default     = true
}

# ── Tags ────────────────────────────────────────────────────
variable "tags" {
  description = "Tags padrão aplicadas a todos os recursos"
  type        = map(string)
  default = {
    Project     = "DeepWatch"
    ManagedBy   = "Terraform"
    Course      = "CCO"
  }
}
