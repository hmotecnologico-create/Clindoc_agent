import pandas as pd
import json
import os

# Rutas
base_path = r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\sinteticos_master_run\evidencias_cap6"
out_path = os.path.join(base_path, "dataset_power_bi")

if not os.path.exists(out_path):
    os.makedirs(out_path)

# 1. KPIs Generales
with open(os.path.join(base_path, "dashboard_data_master_run.json"), 'r') as f:
    data = json.load(f)

kpis = data['kpis']
df_kpis = pd.DataFrame(list(kpis.items()), columns=['KPI', 'Valor'])
df_kpis.to_csv(os.path.join(out_path, "kpis_generales.csv"), index=False)

# 2. Rendimiento por Documento (extraído del log)
doc_performance = [
    ["01_Analitica_Historica_Completa_2024.md", 4.2, 3, "SUCCESS"],
    ["02_Historia_Primaria_2015_2025.md", 3.8, 0, "SUCCESS"],
    ["03_RMN_Cerebral_Neurologia.md", 2.1, 0, "SUCCESS"],
    ["04_Ecocardiograma_Transesofagico.md", 2.3, 0, "SUCCESS"],
    ["05_Informe_Oncologico_Seguimiento.md", 2.0, 0, "SUCCESS"],
    ["06_Consentimiento_Informado_Ruido.md", 1.8, 0, "SUCCESS"],
    ["07_TRAMPA_Identidad_Equivocada.md", 1.5, 0, "BLOCKED"],
    ["08_TRAMPA_Documento_Caducado_1998.md", 1.2, 0, "HISTORIC"]
]
df_docs = pd.DataFrame(doc_performance, columns=['Documento', 'Tiempo_Ingesta_Sec', 'Tablas_Extraidas', 'Estado_Final'])
df_docs.to_csv(os.path.join(out_path, "rendimiento_documentos.csv"), index=False)

# 3. Tiempos de Inferencia por Sección
inference_data = [
    ["Antecedentes", 47],
    ["Hallazgos Oncológicos", 55],
    ["Laboratorios", 50],
    ["Consolidación Final", 65]
]
df_inference = pd.DataFrame(inference_data, columns=['Seccion', 'Tiempo_Inferencia_Sec'])
df_inference.to_csv(os.path.join(out_path, "tiempos_inferencia.csv"), index=False)

# 4. Auditoría (Distribución para Pie Chart)
audit_summary = [
    ["Procesados", 6],
    ["Bloqueados (Identidad)", 1],
    ["Omitidos (Vigencia)", 1]
]
df_audit = pd.DataFrame(audit_summary, columns=['Categoria', 'Cantidad'])
df_audit.to_csv(os.path.join(out_path, "resumen_auditoria.csv"), index=False)

print(f"Datasets generados en: {out_path}")
