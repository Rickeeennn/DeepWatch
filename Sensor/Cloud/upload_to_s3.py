"""
DeepWatch — Upload Local → S3 Raw
===================================
Limpa todo o conteúdo do bucket raw na AWS e envia
os arquivos da pasta Local/1raw para o S3.

Uso:
  python upload_to_s3.py

Pré-requisitos:
  pip install boto3
  Credenciais AWS configuradas em ~/.aws/credentials

Variáveis de ambiente opcionais (sobrescrevem os defaults):
  RAW_BUCKET   — nome do bucket raw (default: deepwatch-stage-raw-dev)
  AWS_REGION   — região AWS (default: us-east-1)
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError

# ==========================================
# CONFIGURAÇÃO
# ==========================================

RAW_BUCKET = os.environ.get("RAW_BUCKET", "deepwatch-stage-raw-dev")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Caminho da pasta 1raw relativo a este script
# Sensor/Cloud/upload_to_s3.py → Sensor/Local/1raw/
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
LOCAL_RAW = os.path.join(BASE_DIR, "..", "Local", "1raw")

# ==========================================
# HELPERS
# ==========================================

def get_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)

def clear_bucket(s3, bucket):
    """Remove todos os objetos do bucket."""
    print(f"\n  Limpando bucket s3://{bucket} ...")
    paginator = s3.get_paginator("list_objects_v2")
    pages     = paginator.paginate(Bucket=bucket)

    deleted = 0
    for page in pages:
        if "Contents" not in page:
            continue
        objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        deleted += len(objects)

    print(f"  {deleted} objeto(s) removido(s).")

def upload_directory(s3, bucket, local_dir):
    """
    Faz upload de todos os arquivos em local_dir para o bucket,
    preservando a estrutura de pastas como prefixo S3.

    Ex: Local/1raw/FPSO-01/TK-01/nivel.csv
      → s3://bucket/FPSO-01/TK-01/nivel.csv
    """
    if not os.path.exists(local_dir):
        print(f"[ERRO] Pasta local não encontrada: {local_dir}")
        sys.exit(1)

    uploaded = 0
    errors   = 0

    for root, _, files in os.walk(local_dir):
        for filename in sorted(files):
            if not filename.endswith(".csv"):
                continue

            local_path = os.path.join(root, filename)

            # Gera a chave S3 relativa à pasta 1raw
            relative   = os.path.relpath(local_path, local_dir)
            s3_key     = relative.replace("\\", "/")  # Windows → Unix path

            try:
                s3.upload_file(local_path, bucket, s3_key)
                print(f"  ✓ {s3_key}")
                uploaded += 1
            except ClientError as e:
                print(f"  ✗ {s3_key} — {e}")
                errors += 1

    return uploaded, errors

# ==========================================
# MAIN
# ==========================================

def main():
    print("=" * 55)
    print(" DeepWatch — Upload Local → S3 Raw")
    print("=" * 55)

    # Verifica se a pasta local existe e tem dados
    if not os.path.exists(LOCAL_RAW):
        print(f"[ERRO] Pasta 1raw não encontrada em: {LOCAL_RAW}")
        sys.exit(1)

    total_local = sum(
        1 for _, _, files in os.walk(LOCAL_RAW)
        for f in files if f.endswith(".csv")
    )
    if total_local == 0:
        print("[AVISO] Nenhum CSV encontrado em 1raw. Rode o mock_sensores.py primeiro.")
        sys.exit(0)

    print(f"\n  Origem  : {LOCAL_RAW}")
    print(f"  Destino : s3://{RAW_BUCKET}")
    print(f"  Arquivos: {total_local} CSVs encontrados")

    # Confirmação
    resp = input("\n  Isso vai APAGAR todo o conteúdo do bucket raw. Continuar? [s/N] ")
    if resp.strip().lower() != "s":
        print("  Cancelado.")
        sys.exit(0)

    s3 = get_s3_client()

    # Limpa bucket
    clear_bucket(s3, RAW_BUCKET)

    # Faz upload
    print(f"\n  Enviando arquivos para s3://{RAW_BUCKET} ...")
    uploaded, errors = upload_directory(s3, RAW_BUCKET, LOCAL_RAW)

    # Relatório
    print(f"\n  Arquivos enviados : {uploaded}")
    print(f"  Erros             : {errors}")

    if errors == 0:
        print(f"\n  Upload concluído. Bucket raw pronto para a Lambda ETL1.")
    else:
        print(f"\n  Upload concluído com erros. Verifique as credenciais AWS.")

    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
