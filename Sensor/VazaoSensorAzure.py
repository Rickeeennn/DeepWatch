# from azure.iot.device import IoTHubDeviceClient, Message
import time
import math
import json
from datetime import datetime
import numpy as np

# ==========================================
# CONFIGURAÇÕES INICIAIS
# ==========================================
vazao_nominal_m3h = 2000.0
vazao_nominal_m3s = vazao_nominal_m3h / 3600.0

tempo_segundos = 0

# ==========================================
# CONFIGURAÇÃO AZURE
# ==========================================
# Definir conexão Azure
AZURE_CONNECTION_STRING = "string_de_conexao_azure"
DEVICE_ID = "device_nivel_sensor_01"


print("==================================================")
print(" SENSOR DE VAZÃO (CORIOLIS) - AZURE STREAMING")
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
        # Ruído da bomba
        pulsacao = 0.005 * math.sin(2 * math.pi * 0.5 * tempo_segundos) + \
                   0.002 * math.sin(2 * math.pi * 1.2 * tempo_segundos)

        # Ruído eletrônico
        ruido = np.random.normal(0, 0.001)

        # Leitura bruta do sensor
        vazao_atual = vazao_nominal_m3s + pulsacao + ruido

        # ==========================================
        # CRIANDO JSON COM DADOS BRUTOS + TIMESTAMP
        # ==========================================
        timestamp = datetime.now().isoformat()
        payload = {
            "value": round(vazao_atual, 6),
            "timestamp": timestamp
        }
        
        # ==========================================
        # ENVIANDO PARA AZURE
        # ==========================================
        print(f"[{timestamp}] Vazão: {vazao_atual:.6f} m³/s")
        print(f"  JSON enviado: {json.dumps(payload)}\n")
        
        # message = Message(json.dumps(payload))
        # client.send_message(message)

        tempo_segundos += 1
        time.sleep(1)

except KeyboardInterrupt:
    print("\n\nStreamming interrompido pelo usuário.")
    # client.disconnect()