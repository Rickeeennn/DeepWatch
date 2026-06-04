#!/bin/bash
# DeepWatch – setup_ec2.sh
# Instala dependências e inicia os simuladores com nohup na EC2.
#
# Uso:
#   chmod +x setup_ec2.sh
#   ./setup_ec2.sh
#
# Para múltiplos tanques, rode o script mais de uma vez
# com variáveis de ambiente diferentes:
#   TANK_ID=T-02 ./setup_ec2.sh

set -e

DEEPWATCH_DIR="/home/ec2-user/deepwatch"
LOG_DIR="$DEEPWATCH_DIR/logs"

echo "=================================================="
echo "  DeepWatch – Setup EC2"
echo "  Diretório: $DEEPWATCH_DIR"
echo "=================================================="

# ── 1. Cria estrutura de diretórios ───────────────────────────────
mkdir -p "$DEEPWATCH_DIR"
mkdir -p "$LOG_DIR"
echo "[1/4] Diretórios criados."

# ── 2. Instala dependências Python ────────────────────────────────
echo "[2/4] Instalando dependências..."
pip install --quiet boto3 scipy numpy pandas

echo "  Versões instaladas:"
python3 -c "import boto3, scipy, numpy, pandas; print(f'  boto3={boto3.__version__} scipy={scipy.__version__} numpy={numpy.__version__} pandas={pandas.__version__}')"

# ── 3. Copia os scripts para o diretório da aplicação ─────────────
echo "[3/4] Copiando scripts..."

# Se estiver rodando do diretório onde os scripts estão:
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/NivelSensor_s3.py"      "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/VazaoSensor_s3.py"      "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/sensor_validator.py"    "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/bronze_to_silver_s3.py" "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/silver_to_gold_s3.py"   "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/pipeline_monitor.py"    "$DEEPWATCH_DIR/"
cp "$SCRIPT_DIR/run_pipeline.sh"        "$DEEPWATCH_DIR/"
chmod +x "$DEEPWATCH_DIR/run_pipeline.sh"

echo "  Scripts copiados para $DEEPWATCH_DIR"

# ── 4. Define variáveis de ambiente ──────────────────────────────
export AWS_REGION="${AWS_REGION:-us-east-1}"
export BRONZE_BUCKET="deepwatch-sptech-stage-raw-dev"
export SILVER_BUCKET="deepwatch-sptech-trusted-dev"
export GOLD_BUCKET="deepwatch-sptech-client-dev"
export PLATFORM_ID="${PLATFORM_ID:-FPSO-P67}"
export TANK_ID="${TANK_ID:-T-01}"
export TANK_CAPACITY_M3="${TANK_CAPACITY_M3:-10000}"

echo ""
echo "  Configuração:"
echo "  PLATFORM_ID  = $PLATFORM_ID"
echo "  TANK_ID      = $TANK_ID"
echo "  BRONZE_BUCKET= $BRONZE_BUCKET"
echo ""

# ── 5. Para simuladores anteriores (se já estiverem rodando) ──────
echo "[4/4] Iniciando simuladores com nohup..."

NIVEL_PID_FILE="$LOG_DIR/nivel_${TANK_ID}.pid"
VAZAO_PID_FILE="$LOG_DIR/vazao_${TANK_ID}.pid"

# Encerra instância anterior do mesmo tanque se existir
if [ -f "$NIVEL_PID_FILE" ]; then
    OLD_PID=$(cat "$NIVEL_PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "  Sensor nível anterior (PID $OLD_PID) encerrado."
fi
if [ -f "$VAZAO_PID_FILE" ]; then
    OLD_PID=$(cat "$VAZAO_PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "  Sensor vazão anterior (PID $OLD_PID) encerrado."
fi

# Inicia sensor de nível
nohup python3 "$DEEPWATCH_DIR/NivelSensor_s3.py" \
    > "$LOG_DIR/nivel_${TANK_ID}.log" 2>&1 &
NIVEL_PID=$!
echo $NIVEL_PID > "$NIVEL_PID_FILE"

# Aguarda 2s e inicia sensor de vazão
sleep 2
nohup python3 "$DEEPWATCH_DIR/VazaoSensor_s3.py" \
    > "$LOG_DIR/vazao_${TANK_ID}.log" 2>&1 &
VAZAO_PID=$!
echo $VAZAO_PID > "$VAZAO_PID_FILE"

# Aguarda cron do pipeline (roda a cada 5 minutos)
CRON_LINE="*/5 * * * * cd $DEEPWATCH_DIR && bash run_pipeline.sh >> $LOG_DIR/pipeline.log 2>&1"
( crontab -l 2>/dev/null | grep -v "run_pipeline.sh"; echo "$CRON_LINE" ) | crontab -

echo ""
echo "=================================================="
echo "  Simuladores iniciados!"
echo ""
echo "  Sensor Nível  → PID $NIVEL_PID"
echo "    Log: $LOG_DIR/nivel_${TANK_ID}.log"
echo ""
echo "  Sensor Vazão  → PID $VAZAO_PID"
echo "    Log: $LOG_DIR/vazao_${TANK_ID}.log"
echo ""
echo "  Pipeline ETL  → cron a cada 5 minutos"
echo "    Log: $LOG_DIR/pipeline.log"
echo ""
echo "  Comandos úteis:"
echo "    Ver nível em tempo real  : tail -f $LOG_DIR/nivel_${TANK_ID}.log"
echo "    Ver vazão em tempo real  : tail -f $LOG_DIR/vazao_${TANK_ID}.log"
echo "    Ver pipeline             : tail -f $LOG_DIR/pipeline.log"
echo "    Parar nível              : kill \$(cat $NIVEL_PID_FILE)"
echo "    Parar vazão              : kill \$(cat $VAZAO_PID_FILE)"
echo "=================================================="
