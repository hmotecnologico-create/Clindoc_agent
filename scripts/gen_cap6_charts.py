import requests
import os
import matplotlib.pyplot as plt
import json

# Directorio de salida
out_dir = r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Graficas_TFM"
if not os.path.exists(out_dir):
    os.makedirs(out_dir)

# 1. ARREGLAR ILUSTRACION 7 (Mermaid)
# Cambiamos (Hardware Local) por Hardware Local para evitar el error de Kroki
diagrama_7 = """
flowchart LR
    classDef hardware fill:#475569,stroke:#94a3b8,stroke-width:2px,color:#fff
    classDef memoria fill:#0f766e,stroke:#5eead4,stroke-width:2px,color:#fff
    classDef nube fill:#be123c,stroke:#fda4af,stroke-width:2px,color:#fff,stroke-dasharray: 5 5

    subgraph Riesgo: Cloud Colonialism
        Gemini[API Gemini 2\nGoogle Cloud]:::nube
        Riesgo[Riesgo Filtracion PHI\nNo cumple RGPD]:::nube
    end

    subgraph Perimetro Seguro Hospitalario Hardware Local
        CPU[Procesador Local\ni7/Ryzen]:::hardware
        RAM[Memoria RAM\n32GB]:::memoria
        
        Chunk[Texto Extraido\nDocling]:::hardware
        Embedder{Sentence-Transformers\nall-MiniLM-L6-v2}:::memoria
        Vector[(Vector 384d)]:::memoria
        Qdrant[(Base Qdrant\nLocal)]:::hardware
    end

    Chunk -->|Procesamiento In-Memory| Embedder
    Embedder -->|Genera| Vector
    Vector -->|Almacena| Qdrant
    
    Chunk -.->|Conexion Bloqueada| Gemini
    Gemini -.-> Riesgo
"""

print("Bajando Ilustración 7 corregida...")
r = requests.post("https://kroki.io/mermaid/png", data=diagrama_7.encode('utf-8'), headers={'Content-Type': 'text/plain'})
if r.status_code == 200:
    with open(os.path.join(out_dir, "Ilustracion_7_Soberania.png"), "wb") as f:
        f.write(r.content)
    print("Ilustración 7 guardada.")
else:
    print(f"Fallo Ilustración 7: {r.status_code}")


# 2. GENERAR GRÁFICAS CAPÍTULO 6 (Matplotlib)
data_path = r"f:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\sinteticos_master_run\evidencias_cap6\dashboard_data_master_run.json"
with open(data_path, 'r') as f:
    data = json.load(f)

# Gráfica A: Tiempos por Etapa (Bar Chart)
etapas = ['Ingesta (Docling)', 'Verificación ID', 'Chequeo Vigencia', 'Inferencia LLM (promedio)']
tiempos = [
    data['pipeline_metrics']['docling_extraction']['avg_time_per_doc_sec'],
    data['pipeline_metrics']['identity_verification']['avg_time_per_doc_sec'],
    data['pipeline_metrics']['validity_check']['avg_time_per_doc_sec'],
    data['pipeline_metrics']['llm_synthesis']['avg_inference_sec_per_chunk']
]

plt.figure(figsize=(10, 6))
bars = plt.bar(etapas, tiempos, color=['#0369a1', '#b91c1c', '#4c1d95', '#15803d'])
plt.ylabel('Segundos')
plt.title('Latencia Promedio por Etapa del Pipeline (Master Run)')
plt.grid(axis='y', linestyle='--', alpha=0.7)

# Añadir etiquetas de valor
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 0.2, f'{yval}s', ha='center', va='bottom', fontweight='bold')

plt.savefig(os.path.join(out_dir, "Ilustracion_11_Tiempos_Pipeline.png"), dpi=300)
print("Gráfica 11 guardada.")

# Gráfica B: Distribución de Auditoría (Pie Chart)
labels = ['Válidos', 'Bloqueados (Identidad)', 'Ignorados (Vigencia)']
counts = [
    data['kpis']['valid_docs_processed'],
    data['kpis']['security_blocks'],
    data['kpis']['validity_blocks']
]
colors = ['#15803d', '#b91c1c', '#f59e0b']

plt.figure(figsize=(8, 8))
plt.pie(counts, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors, explode=(0.1, 0, 0))
plt.title('Distribución de Resultados de Auditoría Documental')

plt.savefig(os.path.join(out_dir, "Ilustracion_12_Distribucion_Auditoria.png"), dpi=300)
print("Gráfica 12 guardada.")
