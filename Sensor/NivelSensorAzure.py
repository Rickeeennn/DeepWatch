# from azure.iot.device import IoTHubDeviceClient, Message
import time
import math
import json
from datetime import datetime
import numpy as np

# ==========================================
# CONFIGURAÇÕES DO TANQUE E DA FÍSICA
# ==========================================
area_tanque = 700
vazao_nominal_m3s = 2000 / 3600
taxa_subida_por_segundo = vazao_nominal_m3s / area_tanque
nivel_inicial = 50
nivel_maximo_tanque = 100

tempo_segundos = 0

# ==========================================
# CONFIGURAÇÃO AZURE
# ==========================================
# Definir conexão Azure
AZURE_CONNECTION_STRING = "string_de_conexao_azure"
DEVICE_ID = "device_nivel_sensor_01"


print("==================================================")
print(" SENSOR DE NÍVEL - AZURE STREAMING")
print(" Enviando dados brutos em tempo real para Azure")
print(" Pressione Ctrl+C para interromper")
print("==================================================\n")

try:
    # client = IoTHubDeviceClient.create_from_connection_string(AZURE_CONNECTION_STRING)
    # client.connect()
    
    while True:
        # ==========================================
        # GERANDO O DADO BRUTO
        # ==========================================
        nivel_real = nivel_inicial + (taxa_subida_por_segundo * tempo_segundos)
        
        # Limite máximo físico do tanque
        nivel_real = min(nivel_maximo_tanque, max(0.0, nivel_real))
        
        # ==========================================
        # SLOSHING (PROPORCIONAL AO NÍVEL)
        # ==========================================
        percentual_enchimento = (nivel_real / nivel_maximo_tanque) * 100
        
        amplitude_sloshing = 2.5 * math.exp(-((percentual_enchimento - 60) ** 2) / (2 * 10 ** 2))
        
        # Modo fundamental de ressonância (~0.12 Hz para tanque padrão)
        sloshing_fundamental = amplitude_sloshing * math.sin(2 * math.pi * 0.12 * tempo_segundos)
        
        # Segundo harmônico (~0.25 Hz) com amplitude menor
        sloshing_2harmonica = (amplitude_sloshing * 0.3) * math.sin(2 * math.pi * 0.25 * tempo_segundos + math.pi/3)
        
        sloshing_total = sloshing_fundamental + sloshing_2harmonica
        
        # ==========================================
        # RUÍDO DO SENSOR
        # ==========================================
        ruido = np.random.normal(0, 0.08)
        
        # ==========================================
        # NÍVEL BRUTO
        # ==========================================
        nivel_bruto = max(0.0, min(nivel_maximo_tanque, nivel_real + sloshing_total + ruido))

        # ==========================================
        # CRIANDO JSON COM DADOS + TIMESTAMP
        # ==========================================
        timestamp = datetime.now().isoformat()
        payload = {
            "value": round(nivel_bruto, 4),
            "timestamp": timestamp
        }
        
        # ==========================================
        # ENVIANDO PARA AZURE
        # ==========================================
        print(f"[{timestamp}] Nível: {nivel_bruto:.4f}m | Real: {nivel_real:.4f}m | Sloshing: {sloshing_total:.4f}m")
        print(f"  JSON enviado: {json.dumps(payload)}\n")
        
        # message = Message(json.dumps(payload))
        # client.send_message(message)

        tempo_segundos += 1
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStreamming interrompido pelo usuário.")
    # client.disconnect()