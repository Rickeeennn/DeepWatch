import time
import math
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS
# ==========================================
vazao_nominal_m3h = 2000.0
vazao_nominal_m3s = vazao_nominal_m3h / 3600.0

volume_acumulado = 0.0
tempo_segundos = 0

# Média móvel usará janela de 5 segundos para suavizar leituras brutas
JANELA_FILTRO = 5
janela_movel = deque(maxlen=JANELA_FILTRO)

# ==========================================
# 2. MEMÓRIA PARA OS GRÁFICOS
# ==========================================
historico_tempo = []
historico_vazao_bruta = []
historico_vazao_nominal = []
historico_vazao_tratada = []
historico_volume = []

print("==================================================")
print(" SIMULADOR DE VAZÃO (CORIOLIS) EM TEMPO REAL")
print(" Pressione Ctrl+C para interromper")
print("==================================================\n")

try:
    while True:
        # ==========================================
        # 3. GERANDO O DADO SUJO
        # ==========================================
        # Ruído da bomba
        pulsacao = 0.005 * math.sin(2 * math.pi * 0.5 * tempo_segundos) + \
                   0.002 * math.sin(2 * math.pi * 1.2 * tempo_segundos)

        # Ruído eletrônico
        ruido = np.random.normal(0, 0.001)

        # Leitura bruta do sensor neste exato segundo
        vazao_bruta_atual = vazao_nominal_m3s + pulsacao + ruido

        # ==========================================
        # 4. TRATAMENTO — Média Móvel
        # ==========================================
        janela_movel.append(vazao_bruta_atual)
        vazao_tratada = sum(janela_movel) / len(janela_movel)

        # ==========================================
        # 5. INTEGRAÇÃO — Volume Acumulado
        # ==========================================
        volume_acumulado += vazao_bruta_atual  # Δt = 1s

        # ==========================================
        # 6. SALVANDO HISTÓRICO PARA O GRÁFICO
        # ==========================================
        historico_tempo.append(tempo_segundos)
        historico_vazao_bruta.append(vazao_bruta_atual)
        historico_vazao_nominal.append(vazao_nominal_m3s)
        historico_vazao_tratada.append(vazao_tratada)
        historico_volume.append(volume_acumulado)

        # ==========================================
        # 7. EXIBIÇÃO EM TEMPO REAL
        # ==========================================
        print(
            f"Tempo: {tempo_segundos:03d}s | "
            f"Bruta: {vazao_bruta_atual:.4f} m³/s | "
            f"Tratada: {vazao_tratada:.4f} m³/s | "
            f"Nominal: {vazao_nominal_m3s:.4f} m³/s | "
            f"Volume: {volume_acumulado:.2f} m³"
        )

        tempo_segundos += 1
        time.sleep(1)

except KeyboardInterrupt:
    print("\nSimulação encerrada pelo usuário. Gerando gráficos...\n")

# ==========================================
# 8. GERAÇÃO DOS GRÁFICOS
# ==========================================
fig, axes = plt.subplots(2, 1, figsize=(14, 10))
fig.suptitle("Simulador de Vazão — Coriolis", fontsize=16, fontweight="bold")

# --- Gráfico 1: Comparação de Vazões ---
ax1 = axes[0]
ax1.plot(historico_tempo, historico_vazao_nominal,
         color="green",  linewidth=2,   linestyle="--", label="Valor Real (Nominal)")
ax1.plot(historico_tempo, historico_vazao_bruta,  
         color="red",    linewidth=1,   alpha=0.6,      label="Valor Bruto (Sensor)")
ax1.plot(historico_tempo, historico_vazao_tratada,
         color="blue",   linewidth=2,                   label=f"Valor Tratado (Média Móvel {JANELA_FILTRO}s)")
ax1.set_title("Vazão Instantânea ao Longo do Tempo")
ax1.set_xlabel("Tempo (s)")
ax1.set_ylabel("Vazão (m³/s)")
ax1.legend(loc="upper right")
ax1.grid(True, linestyle="--", alpha=0.5)

# --- Gráfico 2: Volume Acumulado ---
ax2 = axes[1]
ax2.plot(historico_tempo, historico_volume,
         color="purple", linewidth=2, label="Volume Acumulado")
ax2.set_title("Volume Acumulado ao Longo do Tempo")
ax2.set_xlabel("Tempo (s)")
ax2.set_ylabel("Volume (m³)")
ax2.legend(loc="upper left")
ax2.grid(True, linestyle="--", alpha=0.5)

plt.tight_layout()
plt.savefig("grafico_vazao.png", dpi=150)
print("Gráfico salvo como 'grafico_vazao.png'")
plt.show()
