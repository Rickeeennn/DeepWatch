import time
import random
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Simulação do sensor Coriolis
# -----------------------------

def simular_fluxo(t):
    
    # fluxo base da linha (m³/h)
    fluxo_base = 220

    # pequena oscilação natural do processo
    oscilacao = 25 * np.sin(t/6)

    # ruído do sensor (precisão ±0.05%)
    ruido = random.uniform(-0.12, 0.12)

    fluxo = fluxo_base + oscilacao + ruido

    return fluxo


# -----------------------------
# Simulação nível do tanque
# -----------------------------

def calcular_nivel(nivel_atual, fluxo):

    # conversão aproximada para enchimento
    taxa = fluxo / 5000

    nivel_novo = nivel_atual + taxa

    return min(nivel_novo, 100)


# -----------------------------
# Simulação de dados
# -----------------------------

tempo = []
fluxo_dados = []
nivel_dados = []

nivel = 35

for t in range(120):

    fluxo = simular_fluxo(t)

    nivel = calcular_nivel(nivel, fluxo)

    tempo.append(t)
    fluxo_dados.append(fluxo)
    nivel_dados.append(nivel)

    time.sleep(0.02)


# -----------------------------
# Dashboard
# -----------------------------

plt.figure(figsize=(12,6))

plt.subplot(2,1,1)
plt.plot(tempo, fluxo_dados, marker='o')
plt.title("Sensor Coriolis - Vazão de Transferência de Petróleo")
plt.ylabel("Fluxo (m³/h)")
plt.grid(True)


plt.subplot(2,1,2)
plt.plot(tempo, nivel_dados, marker='x')
plt.title("Estimativa de Nível do Tanque")
plt.xlabel("Tempo (s)")
plt.ylabel("Nível (%)")
plt.grid(True)

plt.tight_layout()
plt.show()