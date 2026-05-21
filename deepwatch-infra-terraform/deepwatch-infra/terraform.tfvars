###############################################################
# DeepWatch – Exemplo de valores (renomeie para terraform.tfvars)
###############################################################

aws_region        = "us-east-1"
project_name      = "deepwatch"
environment       = "dev"

# Rede
vpc_cidr            = "10.0.0.0/16"
public_subnet_cidr  = "10.0.1.0/24"

# ATENÇÃO: em produção, substitua pelo seu IP: ["SEU_IP/32"]
allowed_cidr_blocks = ["0.0.0.0/0"]

# EC2 – coloque o nome do seu Key Pair criado na AWS
key_pair_name     = "deepwatch-key"
ec2_instance_type = "t3.large"
ec2_volume_size   = 30

# S3
s3_force_destroy  = true  # false em produção!

# Tags
tags = {
  Project   = "DeepWatch"
  ManagedBy = "Terraform"
  Course    = "CCO"
  Semester  = "5"
}
