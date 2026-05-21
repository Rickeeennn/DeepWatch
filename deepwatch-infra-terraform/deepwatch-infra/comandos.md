# deepwatch – comandos

## 1. credenciais
pega no AWS Academy > AWS Details > Show, cola em `~/.aws/credentials`
```
[default]
aws_access_key_id = ...
aws_secret_access_key = ...
aws_session_token = ...
```

## 2. key pair
```bash
aws ec2 create-key-pair --key-name deepwatch-key --query 'KeyMaterial' --output text > ~/.ssh/deepwatch-key.pem
chmod 400 ~/.ssh/deepwatch-key.pem
```

## 3. terraform
```bash
cd DeepWatch/deepwatch-infra-terraform/deepwatch-infra
terraform init
terraform apply -auto-approve
```

## 4. subir dados
```bash
cd ../../../..
python Sensor/Cloud/upload_to_s3.py
```

## 5. rodar as lambdas
```bash
aws lambda invoke --function-name deepwatch-etl1-raw-to-trusted --payload '{}' --cli-binary-format raw-in-base64-out r1.json && cat r1.json

aws lambda invoke --function-name deepwatch-etl2-trusted-to-refined --payload '{}' --cli-binary-format raw-in-base64-out r2.json && cat r2.json
```

## 6. crawlers
```bash
aws glue start-crawler --name deepwatch-crawler-trusted
aws glue start-crawler --name deepwatch-crawler-refined

while true; do
  T=$(aws glue get-crawler --name deepwatch-crawler-trusted --query 'Crawler.State' --output text)
  R=$(aws glue get-crawler --name deepwatch-crawler-refined --query 'Crawler.State' --output text)
  echo "$T | $R"
  [ "$T" = "READY" ] && [ "$R" = "READY" ] && break
  sleep 10
done
```

## 7. athena
console AWS > Athena > Settings > output location:
```
s3://deepwatch-athena-results-dev/query-results/
```
database: `deepwatch_dev`
```sql
SELECT * FROM fpso_01 LIMIT 10;
```