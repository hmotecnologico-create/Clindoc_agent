import ollama
import os
import json
from datetime import datetime, timedelta
import random

# --- CONFIGURACIÓN ---
OUTPUT_DIR = r"f:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Agent\sinteticos_master_run"
MODELO_IA = "gemma2" # Cambiar por el modelo que tengas en Ollama (ej: llama3, mistral)

# Plantillas de casos clínicos para diversidad
CASOS_MAESTROS = [
    {
        "especialidad": "Cardiología",
        "perfil": "Paciente con insuficiencia cardíaca congestiva y post-operatorio de bypass.",
        "riesgo": "Vigencia de tratamiento anticoagulante."
    },
    {
        "especialidad": "Oncología",
        "perfil": "Seguimiento de carcinoma de pulmón con metástasis óseas.",
        "riesgo": "Consistencia en las dosis de quimioterapia."
    },
    {
        "especialidad": "Traumatología",
        "perfil": "Fractura múltiple de fémur tras accidente de tráfico.",
        "riesgo": "Identificación correcta en placas radiográficas."
    }
]

def generar_paciente_sintetico(indice, caso):
    print(f"[*] Generando paciente {indice} ({caso['especialidad']})...")
    
    prompt = f"""
    Eres un generador de datos clínicos sintéticos para investigación médica (TFM).
    Genera una historia clínica detallada en formato MARKDOWN para el siguiente caso:
    Caso: {caso['perfil']}
    Especialidad: {caso['especialidad']}
    
    El documento debe incluir:
    1. CABECERA: ID Paciente (Generar UUID), Nombre Ficticio, Fecha (Generar entre 2024 y 2026).
    2. ANTECEDENTES: Resumen médico previo.
    3. HALLAZGOS: Descripción técnica de la situación actual.
    4. PLAN: Tratamiento o cirugía recomendada.
    5. NOTA DE AUDITORÍA: Un pequeño párrafo sobre {caso['riesgo']}.
    
    Responde ÚNICAMENTE con el contenido del archivo Markdown. No incluyas explicaciones.
    """

    try:
        response = ollama.chat(model=MODELO_IA, messages=[{'role': 'user', 'content': prompt}])
        contenido = response['message']['content']
        
        # Limpiar posibles bloques de código markdown si la IA los pone
        contenido = contenido.replace("```markdown", "").replace("```", "").strip()
        
        filename = f"SINTETICO_{indice:02d}_{caso['especialidad']}.md"
        path = os.path.join(OUTPUT_DIR, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(contenido)
            
        print(f"[OK] Archivo creado: {filename}")
        return path
    except Exception as e:
        print(f"[ERROR] No se pudo generar el paciente: {e}")
        return None

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print("=== GENERADOR DE PACIENTES CLINDOC (Modo TFM) ===")
    print(f"Usando modelo: {MODELO_IA}")
    
    # Generar un set de prueba (uno de cada especialidad)
    for i, caso in enumerate(CASOS_MAESTROS, 1):
        generar_paciente_sintetico(i, caso)
        
    print("\n[FIN] Generación completada. Los archivos están listos para ser procesados por ClinDoc Agent.")
