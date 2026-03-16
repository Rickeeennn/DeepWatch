import time
import math
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter, lfilter_zi

# ==========================================
# 1. CONFIGURAÇÕES DO TANQUE E DA FÍSICA
# ==========================================
area_tanque = 700.0 # m²
vazao_nominal_m3s = 2000.0 / 3600.0
taxa_subida_por_segundo = vazao_nominal_m3s / area_tanque # Metros por segundo
nivel_inicial = 15.0 # Metros

# ==========================================
# 2. CONFIGURAÇÃO DO FILTRO PASSA-BAIXA (STATEFUL)
# ==========================================
ordem = 4
frequencia_corte = 0.01 # Hz
b, a = butter(ordem, frequencia_corte, btype='low', analog=False)

zi = lfilter_zi(b, a)
estado_filtro = zi * nivel_inicial

# ==========================================
# 3. MEMÓRIA PARA O GRÁFICO (LISTAS)
# ==========================================
historico_tempo = []
historico_bruto = []
historico_limpo =[]
historico_real =[]

tempo_segundos = 0

print("==================================================")
print(" SIMULADOR DE NÍVEL (SLOSHING + FILTRO) TEMPO REAL")
print(" Pressione Ctrl+C para parar e GERAR O GRÁFICO")
print("==================================================\n")

try:
    while True:
        # GERANDO O DADO SUJO
        nivel_real = nivel_inicial + (taxa_subida_por_segundo * tempo_segundos)
       
        onda1 = 0.8 * math.sin(2 * math.pi * 0.08 * tempo_segundos)
        onda2 = 0.5 * math.sin(2 * math.pi * 0.12 * tempo_segundos + math.pi/4)
        sloshing = onda1 + onda2
        ruido = np.random.normal(0, 0.05)
       
        nivel_bruto_atual = nivel_real + sloshing + ruido
       
        # O MILAGRE DA COMPUTAÇÃO (Filtro lfilter)
        resultado_filtro, novo_estado = lfilter(b, a, [nivel_bruto_atual], zi=estado_filtro)
        estado_filtro = novo_estado
        nivel_limpo_atual = resultado_filtro[0]
       
        # SALVANDO NA MEMÓRIA PARA O GRÁFICO
        historico_tempo.append(tempo_segundos)
        historico_real.append(nivel_real)
        historico_bruto.append(nivel_bruto_atual)
        historico_limpo.append(nivel_limpo_atual)
       
        # EXIBIÇÃO NO TERMINAL
        print(f"Tempo {tempo_segundos:03d}s | Bruto (Ondas): {nivel_bruto_atual:06.2f}m | Limpo (Filtro): {nivel_limpo_atual:06.2f}m | Real Teórico: {nivel_real:06.2f}m")
       
        tempo_segundos += 1
        time.sleep(1) # Espera 1 segundo real

except KeyboardInterrupt:
    # ==========================================
    # 4. GERAÇÃO DO GRÁFICO APÓS INTERRUPÇÃO
    # ==========================================
    print("\n\nSimulação interrompida!")
    print("Gerando o gráfico de resultados com os dados coletados...")
   
    plt.figure(figsize=(12, 6))
   
    # Linha dos dados sujos (fundo cinza para não atrapalhar a visão)
    plt.plot(historico_tempo, historico_bruto, color='lightgray', label='Sensor Bruto (Ondas + Ruído)', alpha=0.8)
   
    # Linha dos dados limpos pelo seu algoritmo
    plt.plot(historico_tempo, historico_limpo, color='blue', linewidth=2.5, label='Sinal Tratado (Filtro em Tempo Real)')
   
    # Linha de onde a água realmente estava (o gabarito)
    plt.plot(historico_tempo, historico_real, color='red', linestyle='--', linewidth=2, label='Nível Real Perfeito')
   
    plt.title('Eficácia do Filtro Passa-Baixa em Tempo Real (Sloshing)', fontsize=14, fontweight='bold')
    plt.xlabel('Tempo da Simulação (Segundos)', fontsize=12)
    plt.ylabel('Nível do Tanque (Metros)', fontsize=12)
    plt.legend(loc='upper left', fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.7)
   
    plt.tight_layout()
    plt.show()