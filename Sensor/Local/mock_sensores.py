"""
DeepWatch — Mock de Sensores Local
===================================
Gera dados simulados de sensores de nível e vazão para 2 FPSOs,
cada um com 4 tanques e 3–5 sensores de vazão por tanque.

Saída: Sensor/Local/1raw/<platform_id>/<tank_id>/nivel.csv
                                                   PIPE-IN-01.csv
                                                   PIPE-IN-02.csv
                                                   ...

Frequência: 1 leitura a cada 2 segundos por sensor (append no CSV).
Entupimento: 3% de chance de iniciar por hora de operação por cano.
             Queda progressiva ao longo de ~30 minutos (curva sigmoidal).
Vazamento:   0.05% de chance por ciclo de avaliação por tanque.
"""

import os
import csv
import math
import time
import random
import numpy as np
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO GERAL
# ==========================================

BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "1raw"
)

INTERVALO_SEGUNDOS = 2          # Leitura a cada 2 segundos
AREA_TANQUE_M2     = 700.0      # Área da base do tanque em m²
NIVEL_INICIAL_PCT  = 20.0       # Nível inicial de cada tanque em %
NIVEL_MAXIMO_M     = 30.0       # Altura máxima do tanque em metros
VAZAO_NOMINAL      = 120.0      # Vazão nominal por cano de entrada (m³/h)

# Limites de alerta de nível
NIVEL_ATENCAO  = 75.0
NIVEL_CRITICO  = 90.0

# Probabilidades
# Entupimento de cano: 0.04% por ciclo
PROB_ENTUPIMENTO_POR_CICLO = 0.0004

# Vazamento de tanque: 0.02% por ciclo
PROB_VAZAMENTO_POR_CICLO = 0.0002

# ==========================================
# DEFINIÇÃO DAS PLATAFORMAS
# ==========================================

def gerar_configuracao():
    """
    Gera a configuração fixa de 2 FPSOs com 4 tanques cada.
    O número de sensores de vazão por tanque varia de 3 a 5.
    O lado (PAR/IMPAR) alterna por tanque dentro de cada FPSO.
    """
    plataformas = {}
    for fpso_num in range(1, 3):
        platform_id = f"FPSO-{fpso_num:02d}"
        tanques = {}
        for tk_num in range(1, 5):
            tank_id      = f"TK-{tk_num:02d}"
            num_sensores = random.randint(3, 5)
            lado         = "PAR" if tk_num % 2 == 0 else "IMPAR"
            tanques[tank_id] = {
                "lado":         lado,
                "num_sensores": num_sensores,
            }
        plataformas[platform_id] = tanques
    return plataformas

# ==========================================
# ESTADO DE CADA SENSOR / TANQUE
# ==========================================

def inicializar_estado(config):
    """
    Cria o estado inicial de cada tanque e cada sensor de vazão.
    Estado do tanque: nível atual, modo (normal/vazamento).
    Estado do cano:   vazão atual, modo (normal/entupimento), progresso.
    """
    estado = {}
    for platform_id, tanques in config.items():
        estado[platform_id] = {}
        for tank_id, info in tanques.items():
            sensores = {}
            for i in range(1, info["num_sensores"] + 1):
                pipe_id = f"PIPE-IN-{i:02d}"
                sensores[pipe_id] = {
                    "vazao_atual":        VAZAO_NOMINAL,
                    "modo":               "NORMAL",   # NORMAL | ENTUPIMENTO
                    "fator_entupimento":  1.0,        # 1.0 = livre, ~0.2 = quase bloqueado
                    "tempo_entupimento":  0,           # segundos desde início do entupimento
                }
            estado[platform_id][tank_id] = {
                "nivel_pct":   NIVEL_INICIAL_PCT,
                "modo":        "NORMAL",   # NORMAL | VAZAMENTO
                "sensores":    sensores,
                "lado":        info["lado"],
            }
    return estado

# ==========================================
# CRIAÇÃO DOS ARQUIVOS CSV
# ==========================================

HEADER_NIVEL = [
    "timestamp", "platform_id", "tank_id",
    "side", "tank_level_percent", "status"
]

HEADER_VAZAO = [
    "timestamp", "platform_id", "tank_id",
    "pipe_id", "pipe_type", "flow_rate_m3_h", "status"
]

def garantir_diretorios_e_headers(config):
    """
    Cria as pastas hierárquicas e escreve os cabeçalhos dos CSVs
    apenas se o arquivo ainda não existir.
    """
    for platform_id, tanques in config.items():
        for tank_id, info in tanques.items():
            pasta = os.path.join(BASE_DIR, platform_id, tank_id)
            os.makedirs(pasta, exist_ok=True)

            # CSV de nível
            path_nivel = os.path.join(pasta, "nivel.csv")
            if not os.path.exists(path_nivel):
                with open(path_nivel, "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(HEADER_NIVEL)

            # CSVs de vazão — um por sensor
            for i in range(1, info["num_sensores"] + 1):
                pipe_id   = f"PIPE-IN-{i:02d}"
                path_vazao = os.path.join(pasta, f"{pipe_id}.csv")
                if not os.path.exists(path_vazao):
                    with open(path_vazao, "w", newline="", encoding="utf-8-sig") as f:
                        csv.writer(f).writerow(HEADER_VAZAO)

# ==========================================
# FÍSICA DO SENSOR DE NÍVEL
# ==========================================

def nivel_status(nivel_pct):
    if nivel_pct >= NIVEL_CRITICO:
        return "CRÍTICO"
    elif nivel_pct >= NIVEL_ATENCAO:
        return "ATENÇÃO"
    return "NORMAL"

def atualizar_nivel(tank_state, vazao_total_m3s, timestamp_str, platform_id, tank_id, pasta):
    """
    Atualiza o nível do tanque com base na vazão total de entrada,
    aplica sloshing e ruído, verifica vazamento e grava no CSV.
    """
    dt = INTERVALO_SEGUNDOS

    # --- Física: variação de nível ---
    # vazao_total_m3s = soma das entradas em m³/s
    # nivel_m = nivel em metros; nivel_pct = 0–100%
    nivel_m = (tank_state["nivel_pct"] / 100.0) * NIVEL_MAXIMO_M

    delta_m = (vazao_total_m3s * dt) / AREA_TANQUE_M2

    # Vazamento: perde volume como se houvesse saída não registrada
    if tank_state["modo"] == "VAZAMENTO":
        taxa_vazamento_m3s = 0.003   # ~10.8 m³/h — vazamento lento
        delta_m -= (taxa_vazamento_m3s * dt) / AREA_TANQUE_M2

    nivel_m = max(0.0, min(NIVEL_MAXIMO_M, nivel_m + delta_m))

    # Sloshing: oscilação da superfície livre
    t = time.monotonic()
    pct_enchimento = (nivel_m / NIVEL_MAXIMO_M) * 100
    amp_sloshing = 0.3 * math.exp(-((pct_enchimento - 60) ** 2) / (2 * 10 ** 2))
    sloshing = (
        amp_sloshing * math.sin(2 * math.pi * 0.12 * t) +
        (amp_sloshing * 0.3) * math.sin(2 * math.pi * 0.25 * t + math.pi / 3)
    )

    ruido     = np.random.normal(0, 0.04)
    nivel_obs = max(0.0, min(NIVEL_MAXIMO_M, nivel_m + sloshing + ruido))
    nivel_pct = round((nivel_obs / NIVEL_MAXIMO_M) * 100, 4)

    tank_state["nivel_pct"] = (nivel_m / NIVEL_MAXIMO_M) * 100  # estado real sem ruído

    # --- Verificar início de vazamento ---
    if tank_state["modo"] == "NORMAL":
        if random.random() < PROB_VAZAMENTO_POR_CICLO:
            tank_state["modo"] = "VAZAMENTO"
            print(f"  ⚠️  VAZAMENTO iniciado em {platform_id}/{tank_id}")

    status = nivel_status(nivel_pct)
    if tank_state["modo"] == "VAZAMENTO":
        status = "CRÍTICO"

    # --- Gravar CSV ---
    row = [
        timestamp_str,
        platform_id,
        tank_id,
        tank_state["lado"],
        nivel_pct,
        status,
    ]
    path = os.path.join(pasta, "nivel.csv")
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(row)

    return nivel_pct, status

# ==========================================
# FÍSICA DO SENSOR DE VAZÃO
# ==========================================

def vazao_status(fator):
    if fator < 0.35:
        return "ENTUPIDO"
    elif fator < 0.80:
        return "DEGRADADO"
    return "NORMAL"

def atualizar_vazao(sensor_state, timestamp_str, platform_id, tank_id, pipe_id, pasta):
    """
    Atualiza a vazão do cano com ruído físico e progressão de entupimento.
    Retorna a vazão em m³/s para uso no cálculo de nível.
    """
    dt = INTERVALO_SEGUNDOS

    # --- Verificar início de entupimento ---
    if sensor_state["modo"] == "NORMAL":
        if random.random() < PROB_ENTUPIMENTO_POR_CICLO:
            sensor_state["modo"] = "ENTUPIMENTO"
            print(f"  🔴 ENTUPIMENTO iniciado em {platform_id}/{tank_id}/{pipe_id}")

    # --- Progressão do entupimento gradual ---
    if sensor_state["modo"] == "ENTUPIMENTO":
        sensor_state["tempo_entupimento"] += dt
        # Declínio sigmoidal: de 1.0 até ~0.20 ao longo de ~30 minutos
        # Ponto de inflexão em 0.5h (30min) — queda mais intensa entre 15 e 45 min
        horas = sensor_state["tempo_entupimento"] / 3600.0
        fator_alvo = 0.20 + 0.80 * (1 / (1 + math.exp(6 * (horas - 0.5))))
        # Suaviza transição para não cair abruptamente
        sensor_state["fator_entupimento"] = min(
            sensor_state["fator_entupimento"],
            fator_alvo + np.random.normal(0, 0.01)
        )
        sensor_state["fator_entupimento"] = max(0.18, sensor_state["fator_entupimento"])

    fator = sensor_state["fator_entupimento"]

    # --- Ruído físico da bomba (pulsação Coriolis) ---
    t = time.monotonic()
    pulsacao = (
        0.005 * math.sin(2 * math.pi * 0.5 * t) +
        0.002 * math.sin(2 * math.pi * 1.2 * t)
    )
    ruido = np.random.normal(0, 0.001)

    # Vazão observada pelo sensor (m³/s)
    vazao_nominal_m3s = VAZAO_NOMINAL / 3600.0
    vazao_m3s = max(0.0, (vazao_nominal_m3s * fator) + pulsacao + ruido)
    vazao_m3h = round(vazao_m3s * 3600.0, 4)

    status = vazao_status(fator)

    # --- Gravar CSV ---
    row = [
        timestamp_str,
        platform_id,
        tank_id,
        pipe_id,
        "ENTRADA",
        vazao_m3h,
        status,
    ]
    path = os.path.join(pasta, f"{pipe_id}.csv")
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(row)

    return vazao_m3s

# ==========================================
# LOOP PRINCIPAL
# ==========================================

def main():
    random.seed()
    config = gerar_configuracao()
    estado = inicializar_estado(config)
    garantir_diretorios_e_headers(config)

    # Exibe configuração gerada
    print("=" * 60)
    print(" DeepWatch — Mock de Sensores Local")
    print(" Pressione Ctrl+C para encerrar")
    print("=" * 60)
    for platform_id, tanques in config.items():
        for tank_id, info in tanques.items():
            print(
                f"  {platform_id}/{tank_id} "
                f"({info['lado']}) — "
                f"{info['num_sensores']} sensores de vazão"
            )
    print(f"\n  Saída: {BASE_DIR}")
    print(f"  Intervalo: {INTERVALO_SEGUNDOS}s por leitura")
    print(f"  P(entupimento): {PROB_ENTUPIMENTO_POR_CICLO*100:.6f}% por ciclo")
    print(f"  P(vazamento):   {PROB_VAZAMENTO_POR_CICLO*100:.4f}% por ciclo")
    print("=" * 60 + "\n")

    ciclo = 0
    try:
        while True:
            ciclo += 1
            timestamp_str = datetime.now().isoformat(timespec="seconds")

            for platform_id, tanques in estado.items():
                for tank_id, tank_state in tanques.items():
                    pasta = os.path.join(BASE_DIR, platform_id, tank_id)

                    # 1. Atualiza todos os sensores de vazão deste tanque
                    vazao_total_m3s = 0.0
                    for pipe_id, sensor_state in tank_state["sensores"].items():
                        vazao_m3s = atualizar_vazao(
                            sensor_state, timestamp_str,
                            platform_id, tank_id, pipe_id, pasta
                        )
                        vazao_total_m3s += vazao_m3s

                    # 2. Atualiza o nível com base na vazão total de entrada
                    nivel_pct, status = atualizar_nivel(
                        tank_state, vazao_total_m3s,
                        timestamp_str, platform_id, tank_id, pasta
                    )

            # Log resumido no terminal a cada 10 ciclos (~20s)
            if ciclo % 10 == 0:
                print(f"[{timestamp_str}] ciclo {ciclo} — dados gravados em {BASE_DIR}")

            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print(f"\n\nSimulação encerrada. {ciclo} ciclos executados.")
        print(f"Dados em: {BASE_DIR}")

if __name__ == "__main__":
    main()