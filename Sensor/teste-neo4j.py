import time
import math
import random
import numpy as np
from collections import deque
from scipy.signal import butter, lfilter, lfilter_zi
from neo4j import GraphDatabase

# ==========================================
# 1. CONFIGURAÇÕES DE CONEXÃO COM O NEO4J (AURA DB)
# ==========================================
URI = "neo4j+ssc://43af67f4.databases.neo4j.io:7687"
AUTH = ("43af67f4", "nr0GaC8cMpiKn7Xkij12_gXJR-WozCiG0VVatF9skCU")
NOME_BANCO = "43af67f4" 

# ==========================================
# 2. PARÂMETROS DA FÍSICA E REGRAS DE NEGÓCIO
# ==========================================
VOLUME_TOTAL_M3 = 54000000.0 
nivel_atual_A = 83.0  
nivel_atual_B = 49.0  

ordem = 4
frequencia_corte = 0.01 
b, a = butter(ordem, frequencia_corte, btype='low', analog=False)
zi = lfilter_zi(b, a)
estado_filtro_A = zi * nivel_atual_A
estado_filtro_B = zi * nivel_atual_B

JANELA_FILTRO = 5
janela_A41 = deque(maxlen=JANELA_FILTRO)
janela_B51 = deque(maxlen=JANELA_FILTRO)

# ==========================================
# 3. ROTINAS CYPHER (AUTOGERENCIÁVEIS)
# ==========================================
def atualizar_vazao_duto(tx, duto_label, tanque_label, plataforma_nome, vazao):
    query = """
    MERGE (p:PLATAFORMA {nome: $plataforma_nome})
    MERGE (t:TANQUE {label: $tanque_label})
    MERGE (d:DUTO {label: $duto_label})
    MERGE (t)-[:TANQUE_DE]->(p)
    MERGE (d)-[:DUTO_DE]->(t)
    
    SET d.vazao_media = $vazao
    
    WITH t, d
    MATCH (todos_dutos:DUTO)-[:DUTO_DE]->(t)
    WITH t, d, sum(todos_dutos.vazao_media) AS vazao_total
    SET t.TTC = CASE 
        WHEN vazao_total > 0 THEN round(($VOLUME_TOTAL * (1.0 - (coalesce(t.nivel_tanque, 0.0) / 100.0))) / (vazao_total * 3600.0), 2)
        ELSE 999.99 
    END
    RETURN t.label AS tanque, t.TTC AS novo_ttc, d.vazao_media AS vazao
    """
    tx.run(query, duto_label=duto_label, tanque_label=tanque_label, 
           plataforma_nome=plataforma_nome, vazao=vazao, VOLUME_TOTAL=VOLUME_TOTAL_M3)

def atualizar_nivel_tanque(tx, tanque_label, par_label, nivel):
    query = """
    MERGE (t1:TANQUE {label: $tanque_label})
    SET t1.nivel_tanque = $nivel
    
    WITH t1
    MERGE (t2:TANQUE {label: $par_label})
    MERGE (t1)-[:PAR_DE]->(t2)
    MERGE (t2)-[:PAR_DE]->(t1)
    
    WITH t1
    OPTIONAL MATCH (d:DUTO)-[:DUTO_DE]->(t1)
    WITH t1, sum(coalesce(d.vazao_media, 0.0)) AS vazao_total
    SET t1.TTC = CASE 
        WHEN vazao_total > 0 THEN round(($VOLUME_TOTAL * (1.0 - (t1.nivel_tanque / 100.0))) / (vazao_total * 3600.0), 2)
        ELSE 999.99 
    END
    
    WITH t1
    MATCH (t1)-[r:PAR_DE]->(vizinho:TANQUE)
    SET r.desnivel = round(t1.nivel_tanque - vizinho.nivel_tanque, 2)
    
    WITH t1
    MATCH (vizinho:TANQUE)-[r:PAR_DE]->(t1)
    SET r.desnivel = round(vizinho.nivel_tanque - t1.nivel_tanque, 2)
    """
    tx.run(query, tanque_label=tanque_label, par_label=par_label, nivel=nivel, VOLUME_TOTAL=VOLUME_TOTAL_M3)

# ==========================================
# 4. LOOP DE EXECUÇÃO EM TEMPO REAL
# ==========================================
print("==================================================")
print(" 🚀 TRANSMISSÃO DE DADOS DO GÊMIO DIGITAL ATIVA")
print(" Conectado com sucesso ao Neo4j Aura DB")
print(" Pressione Ctrl+C para encerrar a transmissão")
print("==================================================\n")

tempo_segundos = 0

try:
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        while True:
            # --------------------------------------------------
            # PASSO A: SIMULAÇÃO + FILTRO DE NÍVEL AMPLIFICADO (Nova Onda Dinâmica)
            # --------------------------------------------------
            # Ampliamos a oscilação para 4.5 e aceleramos a frequência para movimentar a balsa visivelmente
            onda_dinamica = 4.5 * math.sin(2 * math.pi * 0.15 * tempo_segundos) + np.random.normal(0, 0.1)
            
            nivel_sujo_A = nivel_atual_A + onda_dinamica
            nivel_sujo_B = nivel_atual_B + onda_dinamica
            
            # Filtro passa-baixa processando o sinal ruidoso
            res_A, estado_filtro_A = lfilter(b, a, [nivel_sujo_A], zi=estado_filtro_A)
            res_B, estado_filtro_B = lfilter(b, a, [nivel_sujo_B], zi=estado_filtro_B)
            
            valor_A = res_A.item()
            valor_B = res_B.item()
            
            # Efeito Gangorra (Sloshing Inverso): Quando o fluido sobe no Tanque 1, 
            # ele desce proporcionalmente no Tanque 2 do par equilibrado.
            nivel_limpo_A1 = round(valor_A + 1.2 + (onda_dinamica * 0.8), 2)  
            nivel_limpo_A2 = round(valor_A - 1.1 - (onda_dinamica * 0.8), 2)  
            
            nivel_limpo_B1 = round(valor_B + 0.8 + (onda_dinamica * 0.5), 2)  
            nivel_limpo_B2 = round(valor_B - 1.4 - (onda_dinamica * 0.5), 2)  

            with driver.session(database=NOME_BANCO) as session:
                session.execute_write(atualizar_nivel_tanque, "A1", "A2", nivel_limpo_A1)
                session.execute_write(atualizar_nivel_tanque, "A2", "A1", nivel_limpo_A2)
                session.execute_write(atualizar_nivel_tanque, "B1", "B2", nivel_limpo_B1)
                session.execute_write(atualizar_nivel_tanque, "B2", "B1", nivel_limpo_B2)

            # --------------------------------------------------
            # PASSO B: SIMULAÇÃO + FILTRO DE VAZÃO (Média Móvel)
            # --------------------------------------------------
            pulsacao1 = 6.0 * math.sin(2 * math.pi * 0.5 * tempo_segundos) + np.random.normal(0.5, 2.5)
            pulsacao2 = 6.0 * math.sin(2 * math.pi * 0.5 * tempo_segundos) + np.random.normal(0.5, 2.5)
            vazao_bruta_A41 = 715.0 + pulsacao1
            vazao_bruta_B51 = 685.0 + pulsacao2
            
            janela_A41.append(vazao_bruta_A41)
            janela_B51.append(vazao_bruta_B51)
            vazao_tratada_A41 = round(sum(janela_A41) / len(janela_A41), 1)
            vazao_tratada_B51 = round(sum(janela_B51) / len(janela_B51), 1)

            with driver.session(database=NOME_BANCO) as session:
                session.execute_write(atualizar_vazao_duto, "A41", "A4", "Plataforma A", vazao_tratada_A41)
                session.execute_write(atualizar_vazao_duto, "B51", "B5", "Plataforma B", vazao_tratada_B51)

            # --------------------------------------------------
            # EXIBIÇÃO NO CONSOLE
            # --------------------------------------------------
            print(f"⏱️ Tempo: {tempo_segundos:03d}s | 💧 Nível A1: {nivel_limpo_A1}% | 📡 Vazão Duto A41: {vazao_tratada_A41} m³/s")
            print(f"⏱️ Tempo: {tempo_segundos:03d}s | 💧 Nível B1: {nivel_limpo_B1}% | 📡 Vazão Duto B51: {vazao_tratada_B51} m³/s\n")

            tempo_segundos += 1
            time.sleep(1) 

except KeyboardInterrupt:
    print("\n🛑 Transmissão de telemetria desativada com sucesso.")