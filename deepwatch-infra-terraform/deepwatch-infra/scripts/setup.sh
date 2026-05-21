#!/bin/bash
###############################################################
# DeepWatch – Setup EC2: Python, PySpark, Jupyter, Matplotlib
###############################################################
set -euo pipefail
exec > >(tee /var/log/deepwatch-setup.log) 2>&1

echo "==> [1/7] Atualizando sistema..."
dnf update -y
dnf install -y python3 python3-pip java-11-amazon-corretto git wget

echo "==> [2/7] Instalando dependências Python..."
pip3 install --upgrade pip
pip3 install \
  pyspark==3.5.1 \
  jupyter \
  jupyterlab \
  matplotlib \
  pandas \
  boto3 \
  s3fs \
  pyarrow \
  findspark

echo "==> [3/7] Configurando variáveis de ambiente..."
cat >> /etc/environment <<EOF
AWS_DEFAULT_REGION=${aws_region}
DEEPWATCH_RAW_BUCKET=${raw_bucket}
DEEPWATCH_TRUSTED_BUCKET=${trusted_bucket}
DEEPWATCH_CLIENT_BUCKET=${client_bucket}
PYSPARK_PYTHON=python3
PYSPARK_DRIVER_PYTHON=python3
EOF

echo "==> [4/7] Configurando Jupyter..."
mkdir -p /home/ec2-user/.jupyter

# Gera senha padrão: deepwatch2024 (altere após primeiro login!)
JUPYTER_HASH=$(python3 -c "from jupyter_server.auth import passwd; print(passwd('deepwatch2024'))")

cat > /home/ec2-user/.jupyter/jupyter_lab_config.py <<JUPYTEREOF
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = 8888
c.ServerApp.open_browser = False
c.ServerApp.password = '$JUPYTER_HASH'
c.ServerApp.notebook_dir = '/home/ec2-user/notebooks'
c.ServerApp.allow_remote_access = True
JUPYTEREOF

mkdir -p /home/ec2-user/notebooks
chown -R ec2-user:ec2-user /home/ec2-user/.jupyter /home/ec2-user/notebooks

echo "==> [5/7] Criando notebook de exemplo com PySpark + S3..."
cat > /home/ec2-user/notebooks/DeepWatch_Exemplo.ipynb <<'NBEOF'
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": ["# DeepWatch – Pipeline de Dados\n", "Leitura do S3 Raw → Processamento com PySpark → Escrita no Trusted"]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "import os\n",
    "import findspark\n",
    "findspark.init()\n",
    "from pyspark.sql import SparkSession\n",
    "\n",
    "spark = SparkSession.builder \\\n",
    "    .appName('DeepWatch') \\\n",
    "    .config('spark.hadoop.fs.s3a.aws.credentials.provider',\n",
    "            'com.amazonaws.auth.InstanceProfileCredentialsProvider') \\\n",
    "    .getOrCreate()\n",
    "\n",
    "RAW_BUCKET     = os.environ['DEEPWATCH_RAW_BUCKET']\n",
    "TRUSTED_BUCKET = os.environ['DEEPWATCH_TRUSTED_BUCKET']\n",
    "\n",
    "print('Spark version:', spark.version)\n",
    "print('Raw bucket:', RAW_BUCKET)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Leitura da camada Bronze\n",
    "# df = spark.read.json(f's3a://{RAW_BUCKET}/iot/sensor_data/')\n",
    "# df.printSchema()\n",
    "# df.show(5)"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
  "language_info": {"name": "python", "version": "3.9.0"}
 },
 "nbformat": 4,
 "nbformat_minor": 4
}
NBEOF

chown ec2-user:ec2-user /home/ec2-user/notebooks/DeepWatch_Exemplo.ipynb

echo "==> [6/7] Criando serviço systemd para JupyterLab..."
cat > /etc/systemd/system/jupyterlab.service <<SVCEOF
[Unit]
Description=JupyterLab Server – DeepWatch
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/notebooks
ExecStart=/usr/local/bin/jupyter lab --config=/home/ec2-user/.jupyter/jupyter_lab_config.py
Restart=always
RestartSec=10
EnvironmentFile=/etc/environment

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable jupyterlab
systemctl start jupyterlab

echo "==> [7/7] Setup concluído!"
echo "    Jupyter disponível em: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8888"
echo "    Senha padrão: deepwatch2024 (ALTERE imediatamente!)"
