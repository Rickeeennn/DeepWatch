"""
DeepWatch – sensor_validator.py
Camada de validação física dos dados dos sensores.

Propósito de segurança:
  Um atacante que consiga acesso à borda (ou ao pipeline de envio)
  pode injetar leituras falsas para manipular o estado dos tanques
  e enganar operadores. Este módulo detecta leituras fisicamente
  impossíveis dado o estado anterior do sistema.

Conecta com:
  CVE-2024-20961 (MySQL): prepared statements protegem queries
  IoT Attack Detection: valida antes de persistir qualquer leitura
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("deepwatch.validator")

# ─── Limites físicos dos sensores ────────────────────────────────
NIVEL_MIN  = 0.0
NIVEL_MAX  = 100.0
VAZAO_MIN  = 0.0
VAZAO_MAX  = 5000.0        # m³/h — limite físico das tubulações FPSO

# Taxa máxima de variação física do nível por minuto
# Um tanque de 10.000 m³ com vazão máxima de 5.000 m³/h
# sobe no máximo 5000/10000/60 * 100 = 0.833 %/min
MAX_VARIACAO_NIVEL_POR_MINUTO = 1.0   # margem de segurança 20%

# Taxa máxima de variação da vazão entre leituras consecutivas
# Uma bomba industrial não muda mais de 30% em 1 minuto
MAX_VARIACAO_VAZAO_RELATIVA   = 0.35  # 35%

# Janela temporal: leitura com timestamp muito antigo ou futuro é suspeita
MAX_ATRASO_SEGUNDOS  = 300  # 5 minutos
MAX_FUTURO_SEGUNDOS  = 30   # 30 segundos no futuro


@dataclass
class ResultadoValidacao:
    valida: bool
    motivo: Optional[str] = None
    tipo_evento: Optional[str] = None   # para log de segurança


@dataclass
class EstadoAnterior:
    """Mantém o último estado conhecido de cada tanque para comparação."""
    nivel:     float
    vazao:     float
    timestamp: datetime


# ─── Validações individuais ───────────────────────────────────────

def validar_faixa_fisica(nivel: float, vazao: float) -> ResultadoValidacao:
    """Verifica se os valores estão dentro dos limites físicos do sensor."""
    if not (NIVEL_MIN <= nivel <= NIVEL_MAX):
        return ResultadoValidacao(
            valida=False,
            motivo=f"Nível {nivel}% fora da faixa física [{NIVEL_MIN}, {NIVEL_MAX}]",
            tipo_evento="VALOR_FORA_RANGE_FISICO"
        )
    if not (VAZAO_MIN <= vazao <= VAZAO_MAX):
        return ResultadoValidacao(
            valida=False,
            motivo=f"Vazão {vazao} m³/h fora da faixa física [{VAZAO_MIN}, {VAZAO_MAX}]",
            tipo_evento="VALOR_FORA_RANGE_FISICO"
        )
    return ResultadoValidacao(valida=True)


def validar_timestamp(timestamp: datetime) -> ResultadoValidacao:
    """Detecta timestamps no futuro ou excessivamente atrasados."""
    agora = datetime.now()
    delta = (agora - timestamp).total_seconds()

    if delta < -MAX_FUTURO_SEGUNDOS:
        return ResultadoValidacao(
            valida=False,
            motivo=f"Timestamp {delta:.0f}s no futuro — possível replay attack",
            tipo_evento="TIMESTAMP_FUTURO"
        )
    if delta > MAX_ATRASO_SEGUNDOS:
        return ResultadoValidacao(
            valida=False,
            motivo=f"Timestamp com atraso de {delta:.0f}s — sensor offline ou replay",
            tipo_evento="TIMESTAMP_ATRASADO"
        )
    return ResultadoValidacao(valida=True)


def validar_variacao_fisica(
    nivel_atual: float,
    vazao_atual: float,
    estado: EstadoAnterior,
    delta_minutos: float
) -> ResultadoValidacao:
    """
    Verifica se a variação entre leituras é fisicamente possível.
    Esta é a validação mais importante para detectar injeção de dados.

    Exemplo: nível pulando de 62% para 89% em 1 minuto é impossível
    fisicamente — indica dado injetado por atacante.
    """
    if delta_minutos <= 0:
        return ResultadoValidacao(
            valida=False,
            motivo="Delta temporal zero ou negativo — possível duplicata ou replay",
            tipo_evento="DELTA_TEMPORAL_INVALIDO"
        )

    # Variação de nível
    variacao_nivel = abs(nivel_atual - estado.nivel)
    variacao_max_esperada = MAX_VARIACAO_NIVEL_POR_MINUTO * delta_minutos

    if variacao_nivel > variacao_max_esperada:
        return ResultadoValidacao(
            valida=False,
            motivo=(
                f"Variação de nível impossível: {variacao_nivel:.2f}% em {delta_minutos:.1f}min "
                f"(máximo físico: {variacao_max_esperada:.2f}%)"
            ),
            tipo_evento="VARIACAO_NIVEL_IMPOSSIVEL"
        )

    # Variação de vazão
    if estado.vazao > 0:
        variacao_vazao_relativa = abs(vazao_atual - estado.vazao) / estado.vazao
        if variacao_vazao_relativa > MAX_VARIACAO_VAZAO_RELATIVA:
            return ResultadoValidacao(
                valida=False,
                motivo=(
                    f"Variação de vazão suspeita: {variacao_vazao_relativa:.1%} "
                    f"({estado.vazao:.1f} → {vazao_atual:.1f} m³/h)"
                ),
                tipo_evento="VARIACAO_VAZAO_SUSPEITA"
            )

    return ResultadoValidacao(valida=True)


def validar_leitura_completa(
    nivel: float,
    vazao: float,
    timestamp: datetime,
    estado_anterior: Optional[EstadoAnterior] = None
) -> ResultadoValidacao:
    """
    Validação completa de uma leitura.
    Chamada pelo simulador antes de enviar e pelo ETL Bronze→Silver.
    """
    # 1. Faixa física
    resultado = validar_faixa_fisica(nivel, vazao)
    if not resultado.valida:
        return resultado

    # 2. Timestamp
    resultado = validar_timestamp(timestamp)
    if not resultado.valida:
        return resultado

    # 3. Variação física (só se tiver estado anterior)
    if estado_anterior is not None:
        delta_min = (timestamp - estado_anterior.timestamp).total_seconds() / 60
        resultado = validar_variacao_fisica(nivel, vazao, estado_anterior, delta_min)
        if not resultado.valida:
            return resultado

    return ResultadoValidacao(valida=True)


def calcular_balanco_massa(
    delta_nivel_real: float,       # variação medida pelo sensor de nível (%)
    vazao_entrada: float,          # m³/h pelo sensor de vazão
    vazao_saida: float,            # m³/h (0 se não houver saída)
    capacidade_tanque_m3: float,   # m³
    delta_minutos: float           # intervalo de tempo
) -> float:
    """
    Calcula o desvio do balanço de massa entre os dois sensores.

    Princípio físico:
      Δnível_esperado = (vazão_entrada - vazão_saída) × Δt / capacidade × 100

    O desvio entre o esperado e o real indica:
      < 1%  → normal (ruído dos sensores)
      1-2%  → atenção (investigar)
      > 2%  → inconsistência — possível vazamento, falha ou dado injetado

    Retorna: desvio em percentual absoluto
    """
    if delta_minutos <= 0 or capacidade_tanque_m3 <= 0:
        return 0.0

    delta_horas = delta_minutos / 60
    volume_liquido_m3 = (vazao_entrada - vazao_saida) * delta_horas
    delta_nivel_esperado = (volume_liquido_m3 / capacidade_tanque_m3) * 100

    if abs(delta_nivel_esperado) < 0.001:
        return 0.0

    desvio = abs(delta_nivel_real - delta_nivel_esperado)
    desvio_pct = (desvio / abs(delta_nivel_esperado)) * 100
    return round(min(desvio_pct, 100.0), 4)   # cap em 100%
