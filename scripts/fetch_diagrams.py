import requests
import os

diagrams = {
    "Ilustracion_7_Soberania.png": """
flowchart LR
    classDef hardware fill:#475569,stroke:#94a3b8,stroke-width:2px,color:#fff
    classDef memoria fill:#0f766e,stroke:#5eead4,stroke-width:2px,color:#fff
    classDef nube fill:#be123c,stroke:#fda4af,stroke-width:2px,color:#fff,stroke-dasharray: 5 5

    subgraph Riesgo: Cloud Colonialism
        Gemini[API Gemini 2\nGoogle Cloud]:::nube
        Riesgo[Riesgo Filtracion PHI\nNo cumple RGPD]:::nube
    end

    subgraph Perimetro Seguro Hospitalario (Hardware Local)
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
""",
    "Ilustracion_8_LangGraph.png": """
flowchart TD
    classDef usuario fill:#1f2937,stroke:#3b82f6,stroke-width:2px,color:#fff
    classDef ingesta fill:#0369a1,stroke:#bae6fd,stroke-width:2px,color:#fff
    classDef validacion fill:#b91c1c,stroke:#fca5a5,stroke-width:2px,color:#fff
    classDef rag fill:#15803d,stroke:#bbf7d0,stroke-width:2px,color:#fff
    classDef db fill:#4c1d95,stroke:#ddd6fe,stroke-width:2px,color:#fff

    U((Medico Especialista)):::usuario
    
    subgraph Fase 1: Ingesta Estructural [Middleware Transparente]
        Doc1[PDF Analiticas]
        Doc2[JPG Rayos X]
        Doc3[TXT Notas Clinicas]
        Escaner{Agente Escaner\nDocling}:::ingesta
        JSON[JSON Estructurado\nBBox + Tablas]:::ingesta
    end

    subgraph Fase 2: Auditoria Multi-Agente [Control de Riesgos]
        Orquestador((Orquestador Central)):::validacion
        AgIdentidad[Agente de Identidad\nPydantic]:::validacion
        AgVigencia[Agente de Vigencia\nReglas Temporales]:::validacion
    end

    subgraph Fase 3: Sintesis Soberana [RAG Local]
        Qdrant[(Base Vectorial Qdrant\nEmbeddings)]:::db
        Gemma{Agente Redactor\nGemma 3:4b Local}:::rag
        Output[Historia Clinica Consolidada\nDeep Links]:::rag
    end

    U -->|Sube Expedientes| Doc1
    U --> Doc2
    U --> Doc3
    
    Doc1 --> Escaner
    Doc2 --> Escaner
    Doc3 --> Escaner
    Escaner -->|Extrae Semantica| JSON
    
    JSON --> Orquestador
    Orquestador -->|Paso 1| AgIdentidad
    AgIdentidad -->|Rechaza Juana Perez| Orquestador
    Orquestador -->|Paso 2| AgVigencia
    AgVigencia -->|Etiqueta Folio 1998| Orquestador
    
    Orquestador -->|Contexto Limpio| Qdrant
    Qdrant <-->|Busqueda Semantica| Gemma
    Gemma -->|Genera Resumen RAG| Output
    Output -->|Entrega al Facultativo| U
""",
    "Ilustracion_9_Ingesta.png": """
flowchart LR
    classDef file fill:#f3f4f6,stroke:#9ca3af,stroke-width:2px,color:#000
    classDef agent fill:#0284c7,stroke:#bae6fd,stroke-width:2px,color:#fff
    classDef output fill:#f59e0b,stroke:#fde68a,stroke-width:2px,color:#fff

    RawPDF[PDF Crudo\nLayout Complejo]:::file
    AgEscaner{Agente Escaner\nModelo Docling}:::agent
    
    subgraph Procesamiento Estructural
        OCR[OCR Multimodal]:::agent
        Table[TableFormer\nDetecta Tablas]:::agent
        BBox[Calculo de Coordenadas]:::agent
    end
    
    JSON[JSON Normalizado\nTexto + Semantica]:::output

    RawPDF --> AgEscaner
    AgEscaner --> OCR
    OCR --> Table
    Table --> BBox
    BBox --> JSON
""",
    "Ilustracion_10_RAG.png": """
sequenceDiagram
    participant O as Orquestador
    participant R as Agente Redactor
    participant Q as Qdrant (Memoria)
    participant LLM as Gemma 3:4b (Ollama)

    O->>R: Orden de Redactar Seccion Antecedentes
    R->>Q: Busqueda Vectorial: Cirugias Previas
    Q-->>R: Retorna Chunk + ID Documento
    R->>LLM: Prompt Estricto + Contexto
    LLM-->>R: Texto Sintetizado
    R->>O: Parrafo Final + Deep Link al PDF
"""
}

out_dir = r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Graficas_TFM"

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

for name, code in diagrams.items():
    print(f"Downloading {name}...")
    response = requests.post("https://kroki.io/mermaid/png", data=code.encode('utf-8'), headers={'Content-Type': 'text/plain'})
    if response.status_code == 200:
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(response.content)
        print(f"Saved {name}")
    else:
        print(f"Failed {name}: {response.text}")
