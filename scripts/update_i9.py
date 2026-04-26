import requests
import os

code = """
flowchart LR
    classDef his fill:#1e293b,stroke:#334155,stroke-width:2px,color:#fff
    classDef agent fill:#0369a1,stroke:#bae6fd,stroke-width:2px,color:#fff
    classDef process fill:#f3f4f6,stroke:#9ca3af,stroke-width:2px,color:#000
    classDef output fill:#15803d,stroke:#bbf7d0,stroke-width:2px,color:#fff

    HIS[(HIS / Repositorio\\nHospitalario)]:::his
    AgEscaner{Agente Escaner\\nDocling Runtime}:::agent
    
    subgraph "Motor de Ingesta Bionico (Docling Core)"
        Layout[Analisis de Layout\\nVLM / Doc-ResNet]:::process
        Tables[TableFormer\\nExtraccion de Tablas]:::process
        MD[Generador de\\nMarkdown Semantico]:::process
    end
    
    JSON[JSON Estructurado\\n+ BBoxes]:::output
    Markdown[Markdown Limpio\\npara RAG]:::output

    HIS -->|Deteccion de Archivos| AgEscaner
    AgEscaner --> Layout
    Layout --> Tables
    Tables --> MD
    MD --> JSON
    MD --> Markdown
"""

out_paths = [
    r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Graficas_TFM\Ilustracion_9_Ingesta.png",
    r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\DOC_TFM\Graficas_TFM\Ilustracion_9_Ingesta.png"
]

r = requests.post('https://kroki.io/mermaid/png', data=code.encode('utf-8'), headers={'Content-Type': 'text/plain'})
if r.status_code == 200:
    for p in out_paths:
        with open(p, 'wb') as f:
            f.write(r.content)
    print("Actualizada Ilustracion 9")
else:
    print(f"Error: {r.status_code}")
