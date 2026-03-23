# 🛡️ ClinDoc Agent
> **Plataforma Multi-Agente Clínica para la Auditoría y Generación de Informes con LLM Local**

## Descripción
ClinDoc Agent es un sistema avanzado de inteligencia documental diseñado para automatizar la revisión de expedientes clínicos. Utiliza un pipeline multi-agente para validar la identidad de los pacientes, la vigencia de los documentos y sintetizar informes técnicos especializados sin necesidad de conexión a la nube, garantizando el cumplimiento de la normativa RGPD y LOPDGDD.

## Arquitectura del Sistema
El sistema se organiza en los siguientes módulos core:

1.  **Agente Escáner**: Ingesta y análisis de layout con Docling/OCR.
2.  **Agente Verificador de Identidad**: Validación cruzada de NIF/Nombre.
3.  **Agente de Vigencia**: Control de caducidad y períodos de referencia.
4.  **Agente Redactor (RAG)**: Búsqueda semántica y síntesis de lenguaje natural citando fuentes.
5.  **Agente Ensamblador**: Generación de documentos finales en PDF.

## Estructura del Proyecto (Versión Jupyter)
El sistema ha sido consolidado en cuadernos interactivos para facilitar su auditoría y presentación:

- **`ClinDoc_Agent_Master.ipynb`**: Cuaderno principal que contiene toda la lógica de los agentes, modelos de datos y el motor vectorial Qdrant.
- **`ClinDoc_Agent_Demo.ipynb`**: Guía rápida de ejecución del pipeline paso a paso.
- `guiones/`: Configuraciones YAML de los informes.
- `datos/`: Expedientes clínicos y base de datos vectorial local.

## Requisitos
- **Jupyter Notebook / VS Code**
- **Ollama**: Servidor local de LLM.
- **Python 3.10+** (con las dependencias de `requirements.txt`).

## Ejecución
1. Abre VS Code en la carpeta `ClinDoc_Agent`.
2. Abre `ClinDoc_Agent_Master.ipynb`.
3. Ejecuta todas las celdas para inicializar el sistema y generar un informe de prueba.

---
*Este proyecto forma parte de un Trabajo Final de Máster enfocado en Visual Analytics y Big Data.*
