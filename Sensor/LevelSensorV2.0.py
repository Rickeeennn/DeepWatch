import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

# ==========================================
# 1. PARÂMETROS DO TANQUE (Baseado em FPSO)
# ==========================================
comprimento = 35.0  # metros
largura = 20.0      # metros
altura_total = 30.0 # metros
area_base = comprimento * largura # 700 m²
volume_maximo = area_base * altura_total # 21.000 m³

# ==========================================
# 2. PARÂMETROS DA SIMULAÇÃO (Sensores)
# ==========================================
fs = 1.0 # Frequência de amostragem: 1 Hz (1 leitura de sensor por segundo)
tempo_simulacao_minutos = 20
t = np.arange(0, tempo_simulacao_minutos * 60, 1/fs) # Vetor de tempo em segundos

# ==========================================
# 3. GERANDO O NÍVEL REAL (O "Gabarito")
# ==========================================
# Supondo que a bomba envia uma vazão constante de 2000 m³/hora
vazao_m3_h = 2000.0
vazao_m3_s = vazao_m3_h / 3600.0

# O nível sobe baseado no volume acumulado dividido pela área da base
nivel_inicial = 15.0 # Supondo que o tanque começa com 15 metros cheios
volume_acumulado = vazao_m3_s * t
nivel_real = nivel_inicial + (volume_acumulado / area_base)

# ==========================================
# 4. GERANDO O EFEITO SLOSHING E RUÍDO
# ==========================================
# Sloshing: Soma de ondas senoidais simulando o balanço do mar (frequências de 0.08 a 0.12 Hz)
onda1 = 0.8 * np.sin(2 * np.pi * 0.08 * t)         # Amplitude 0.8m, período ~12.5s
onda2 = 0.5 * np.sin(2 * np.pi * 0.12 * t + np.pi/4) # Amplitude 0.5m, período ~8.3s
sloshing = onda1 + onda2

# Ruído Eletrônico do Sensor de Nível (Radar/Ultrassônico)
ruido_sensor = np.random.normal(0, 0.05, len(t))

# Sinal Bruto lido pelo sistema do navio
nivel_sensor_bruto = nivel_real + sloshing + ruido_sensor

# ==========================================
# 5. APLICANDO O FILTRO PASSA-BAIXA (BUTTERWORTH)
# ==========================================
# O enchimento do tanque é muito lento (próximo a 0 Hz)
# O sloshing é rápido (> 0.05 Hz). Vamos cortar tudo acima de 0.01 Hz
frequencia_corte = 0.01 # Hz
ordem_filtro = 4
nyquist = 0.5 * fs
corte_normalizado = frequencia_corte / nyquist

# Criando o filtro
b, a = butter(ordem_filtro, corte_normalizado, btype='low', analog=False)

# Aplicando o filtro com filtfilt (isso garante fase zero, sem atrasar o sinal)
nivel_filtrado = filtfilt(b, a, nivel_sensor_bruto)

# ==========================================
# 6. PLOTANDO O GRÁFICO "ANTES E DEPOIS"
# ==========================================
plt.figure(figsize=(12, 6))

# Plotamos apenas os primeiros 10 minutos (600 segundos) para enxergar as ondas melhor
limite = 600

# Antes (Sinal do Sensor Sujo)
plt.plot(t[:limite], nivel_sensor_bruto[:limite], color='lightgray',
         label='Sensor Bruto (Sloshing + Ruído)', alpha=0.8)

# Depois (Sinal Filtrado)
plt.plot(t[:limite], nivel_filtrado[:limite], color='blue', linewidth=2,
         label='Sinal Filtrado (Butterworth Passa-Baixa)')

# Real (Tendência Pura)
plt.plot(t[:limite], nivel_real[:limite], color='red', linestyle='--', linewidth=2,
         label='Nível Real Perfeito (Taxa de Enchimento)')

# Configurações do gráfico
plt.title('Simulação de Monitoramento do Tanque FPSO\nFiltro de Sloshing com Butterworth', fontsize=14, fontweight='bold')
plt.xlabel('Tempo (Segundos)', fontsize=12)
plt.ylabel('Nível do Tanque (Metros)', fontsize=12)
plt.legend(loc='upper left', fontsize=10)
plt.grid(True, linestyle=':', alpha=0.7)

plt.tight_layout()
plt.show()