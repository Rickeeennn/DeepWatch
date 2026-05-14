# DeepWatch – IaC Terraform

Infraestrutura completa do ambiente de processamento de dados na AWS,
fiel ao diagrama da entrega acadêmica.

## Arquitetura provisionada

```
VPC (10.0.0.0/16)
└── Public Subnet (10.0.1.0/24)
    ├── Internet Gateway
    ├── Route Table (172.16.0.0 / 172.16.1.0 / 172.16.2.0)
    ├── Security Group (portas 22, 8888, 4040)
    └── EC2 t3.large
        ├── JupyterLab  → :8888
        ├── PySpark     → Spark UI :4040
        ├── Matplotlib
        └── IAM Role ──→ S3 (leitura/escrita)

S3 Medallion
├── deepwatch-stage-raw-dev   (Bronze)
├── deepwatch-trusted-dev     (Silver)
└── deepwatch-client-dev      (Gold)
```

## Pré-requisitos

- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/downloads)
- [AWS CLI](https://aws.amazon.com/cli/) configurado (`aws configure`)
- Um **Key Pair** criado no console AWS (para SSH na EC2)

## Como usar

```bash
# 1. Clone/entre na pasta
cd deepwatch-infra

# 2. Copie e edite as variáveis
cp terraform.tfvars.example terraform.tfvars
# Edite terraform.tfvars com seu key_pair_name e região

# 3. Inicialize
terraform init

# 4. Visualize o plano
terraform plan

# 5. Aplique
terraform apply
```

Após o apply, o output mostrará a URL do Jupyter:
```
jupyter_url = "http://<IP_PUBLICO>:8888"
```

> ⏱️ Aguarde ~3 minutos após o apply para o setup.sh terminar na EC2.

## Acesso ao Jupyter

```
URL:   http://<ec2_public_ip>:8888
Senha: deepwatch2024  ← ALTERE no primeiro acesso!
```

## Destruir a infraestrutura

```bash
terraform destroy
```

## Estrutura dos arquivos

```
deepwatch-infra/
├── main.tf                   # Recursos principais (VPC, EC2, S3, IAM)
├── variables.tf              # Declaração de variáveis
├── outputs.tf                # Outputs úteis pós-deploy
├── terraform.tfvars.example  # Exemplo de valores
└── scripts/
    └── setup.sh              # User data: instala Jupyter, PySpark, Matplotlib
```

## Segurança (atenção em produção)

| Configuração | Dev | Produção |
|---|---|---|
| `allowed_cidr_blocks` | `0.0.0.0/0` | `SEU_IP/32` |
| `s3_force_destroy` | `true` | `false` |
| Senha Jupyter | `deepwatch2024` | Senha forte |
| EC2 em subnet | Pública | Privada + Bastion |
