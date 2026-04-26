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

## Estructura del Proyecto (Self-Contained)
El repositorio ha sido organizado para ser totalmente portable, incluyendo código, scripts de soporte y datos de prueba:

- **`run_clindoc.py`**: Orquestador principal del sistema y punto de entrada.
- **`app_clindoc.py`**: Interfaz de usuario/Dashboard (Streamlit).
- **`scripts/`**: Utilidades para la generación de diagramas técnicos (ERD, Secuencia) y gráficas estadísticas para la tesis.
- **`sinteticos_master_run/`**: Datos clínicos sintéticos y evidencias de ejecución para auditoría.
- **`guiones/`**: Configuraciones YAML de los informes.
- **`datos/`**: Base de datos vectorial local (Qdrant).

## Metodología y Apoyo de IA
Este proyecto integra metodologías de desarrollo ágil asistido por **IA Generativa**. El uso de asistentes de IA (como Antigravity/Gemini) ha sido fundamental en:
- **Optimización de Código**: Refactorización de lógica multi-agente y manejo de concurrencia.
- **Visual Analytics**: Automatización de scripts para la generación de gráficas de rendimiento.
- **Documentación Técnica**: Estructuración de especificaciones y diagramas arquitectónicos.

Esta simbiosis humano-IA permite un desarrollo robusto, permitiendo al autor centrarse en la arquitectura de alto nivel y la validación clínica de los resultados.

## Requisitos
- **Ollama**: Servidor local de LLM (configurado con modelos `gemma2` o similar).
- **Python 3.10+** (instalar dependencias con `pip install -r requirements.txt`).

## Ejecución
1. Asegúrate de tener Ollama corriendo localmente.
2. Ejecuta el orquestador principal:
   ```bash
   python run_clindoc.py
   ```
3. Para visualizar el dashboard:
   ```bash
   streamlit run app_clindoc.py
   ```

---
*Este proyecto forma parte de un Trabajo Final de Máster (TFM) enfocado en Visual Analytics y Big Data.*
