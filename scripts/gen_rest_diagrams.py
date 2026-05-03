import requests
import os

diagrams = {
    "Ilustracion_ERD_ClinDoc.png": """
erDiagram
    PACIENTE ||--o{ DOCUMENTO : "posee"
    DOCUMENTO ||--o{ FRAGMENTO : "segmentado"
    FRAGMENTO ||--|| VECTOR : "representado"
    DOCUMENTO {
        string uuid_doc
        datetime fecha_auditoria
        string status_vigencia
    }
    PACIENTE {
        string hash_id
        string nif_masked
        date fecha_nacimiento
    }
""",
    "Ilustracion_Clases_Pydantic.png": """
classDiagram
    class ClinicalChunk {
        +UUID point_id
        +str content_text
        +list coordinates
        +dict audit_metadata
        +validate_schema()
    }
    class PatientContext {
        +str patient_hash
        +datetime session_start
        +bool identity_confirmed
    }
    ClinicalChunk --> PatientContext : "pertenece"
""",
    "Ilustracion_Secuencia_Auditoria.png": """
sequenceDiagram
    participant M as Medico
    participant O as Orquestador
    participant I as Agente Ingesta
    participant V as Agente Verificador
    participant R as Agente Redactor

    M->>O: Cargar PDF Clinico
    O->>I: Solicitar Normalizacion
    I-->>O: JSON Estructural + Bboxes
    loop Validacion de Identidad
        O->>V: Comparar NIF y Datos Maestros
        V-->>O: Confianza < 90% (Solicita Re-scan)
        O->>I: Extraccion de Alta Resolucion
        I-->>O: Datos Corregidos
        O->>V: Re-validacion
        V-->>O: Confianza > 95% (OK)
    end
    O->>R: Generar Sintesis con Deep Links
    R-->>O: Informe Tecnico Final
    O->>M: Visualizacion en Dashboard
"""
}

out_dirs = [
    r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Graficas_TFM",
    r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\DOC_TFM\Graficas_TFM"
]

for name, code in diagrams.items():
    print(f"Generando {name}...")
    r = requests.post('https://kroki.io/mermaid/png', data=code.encode('utf-8'), headers={'Content-Type': 'text/plain'})
    if r.status_code == 200:
        for d in out_dirs:
            if not os.path.exists(d): os.makedirs(d)
            with open(os.path.join(d, name), 'wb') as f:
                f.write(r.content)
    else:
        print(f"Error {name}: {r.status_code}")
