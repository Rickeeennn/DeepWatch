#!/bin/bash
# DeepWatch – run_pipeline.sh
# Orquestra o pipeline completo na EC2:
#   Bronze → Silver → Gold → Monitor
#
# Uso:
#   ./run_pipeline.sh              # processa todos os dados disponíveis
#   ./run_pipeline.sh --data 2026/05/14   # filtra por data
#   ./run_pipeline.sh --monitor-only      # só roda o monitor
#
# Para agendar no cron (a cada 5 minutos):
#   */5 * * * * /opt/deepwatch/run_pipeline.sh >> /var/log/deepwatch.log 2>&1

set -e  # para se qualquer comando falhar

# ─── Variáveis de ambiente ────────────────────────────────────────
export AWS_REGION="${AWS_REGION:-us-east-1}"
export BRONZE_BUCKET="${BRONZE_BUCKET:-deepwatch-stage-raw-dev}"
export SILVER_BUCKET="${SILVER_BUCKET:-deepwatch-trusted-dev}"
export GOLD_BUCKET="${GOLD_BUCKET:-deepwatch-client-dev}"
export TANK_CAPACITY_M3="${TANK_CAPACITY_M3:-10000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
LOG_FILE="${LOG_DIR}/pipeline_${TIMESTAMP}.log"

# ─── Argumentos ──────────────────────────────────────────────────
DATA_PREFIX=""
MONITOR_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --data)
      DATA_PREFIX="--data $2"
      shift 2
      ;;
    --monitor-only)
      MONITOR_ONLY=true
      shift
      ;;
    *)
      echo "Argumento desconhecido: $1"
      exit 1
      ;;
  esac
done

# ─── Funções ─────────────────────────────────────────────────────
log() {
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*" | tee -a "$LOG_FILE"
}

run_step() {
  local nome="$1"
  local script="$2"
  shift 2

  log "▶ Iniciando: $nome"
  if python3 "${SCRIPT_DIR}/${script}" "$@" >> "$LOG_FILE" 2>&1; then
    log "✓ Concluído: $nome"
  else
    log "✗ ERRO em: $nome (código $?)"
    exit 1
  fi
}

# ─── Pipeline ────────────────────────────────────────────────────
log "======================================================="
log "  DeepWatch Pipeline  |  Início: $TIMESTAMP"
log "  Bronze: $BRONZE_BUCKET"
log "  Silver: $SILVER_BUCKET"
log "  Gold:   $GOLD_BUCKET"
log "======================================================="

if [ "$MONITOR_ONLY" = false ]; then

  # Passo 1: Bronze → Silver (com validação de segurança)
  run_step "Bronze → Silver" "bronze_to_silver_s3.py" $DATA_PREFIX

  # Passo 2: Silver → Gold (com insights preditivos)
  run_step "Silver → Gold" "silver_to_gold_s3.py"

fi

# Passo 3: Monitor de saúde do pipeline
log "▶ Executando monitor de pipeline..."
python3 "${SCRIPT_DIR}/pipeline_monitor.py" | tee -a "$LOG_FILE"
MONITOR_EXIT=${PIPESTATUS[0]}

log "======================================================="
log "  Pipeline concluído. Log: $LOG_FILE"
log "======================================================="

# Retorna exit code do monitor (0=normal, 1=atenção, 2=crítico)
exit $MONITOR_EXIT
