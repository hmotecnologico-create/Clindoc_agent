# 🎓 Manual del Revisor Técnico (Tribunal Académico)

Este documento detalla la arquitectura subyacente y las métricas de evaluación del proyecto **ClinDoc Agent**, diseñado para la defensa técnica en el Trabajo Final de Máster (TFM).

## 1. Arquitectura del Sistema (Multi-Agente)

El sistema ha sido estructurado siguiendo el paradigma LangGraph (Grafo de Estado) permitiendo la concurrencia y validación cruzada. Al ingresar al Dashboard bajo el perfil **"🎓 Tribunal Académico"**, podrá auditar la pestaña **"🤖 Arquitectura y Pipeline"** que muestra el estado de 5 agentes principales:

1. **Agente Escáner (Ingesta Híbrida):** Utiliza *Docling* para extracción de PDFs conservando la estructura semántica de tablas, con fallback a PyPDF2.
2. **Agente Verificador de Identidad:** Emplea algoritmos de validación deterministas para asegurar que el NIF del documento coincida y cumpla con el checksum del Ministerio del Interior español.
3. **Agente Verificador de Vigencia:** Análisis regex dinámico para calcular caducidad documental (< 6 meses) o detectar fechas futuras (posible manipulación/fraude).
4. **Agente Redactor (RAG & LLM):** Motor de inferencia utilizando modelos LLM Locales (Ollama - ej. *gemma3:4b*) interactuando con una BBDD vectorial (*Qdrant*). 
5. **Agente Ensamblador:** Compone la información estructurada en un informe PDF certificable.

## 2. Privacidad y Soberanía del Dato (Cumplimiento Legal)

Uno de los hitos principales del TFM es asegurar el cumplimiento del **RGPD** (Reglamento General de Protección de Datos). 
- El sistema es 100% *Air-Gapped* (funciona sin conexión a internet). 
- Los datos de los pacientes (historias clínicas) son indexados en hardware local, sin dependencias de APIs en la nube (como OpenAI), mitigando el riesgo de fuga de datos de salud de nivel alto (Categoría especial).

## 3. Trazabilidad y "Chain of Thought" (XAI)

Para mitigar el riesgo de alucinaciones del LLM y cumplir con los estándares de *Explainable AI* (XAI):
- **Deep Linking:** Todo el conocimiento extraído guarda un `chunk_id` y su archivo de procedencia.
- En la pestaña **"📜 Logs de Ejecución"**, el tribunal puede observar las decisiones algorítmicas tomadas paso a paso por el sistema.
- El chat del facultativo incluye *Feedback Loops*, obligando a la IA a corregirse según la directriz humana, sirviendo como registro legal de responsabilidad médica.

## 4. Métricas de Rendimiento Analítico

En la pestaña **"📊 Métricas Técnicas"**, se evalúa el rendimiento del sistema mediante Visual Analytics:
- **Latencia:** Milisegundos por documento en la ingesta e indexación.
- **Eficiencia del RAG:** Evaluación de confianza (Confidence Score simulado/inferido) de los resultados del LLM.

## Instrucciones de Evaluación
Para testear las capacidades, se han precargado pacientes sintéticos en `datos/expedientes/`. Ejecute el orquestador backend con `python run_clindoc.py` y observe el flujo de procesamiento antes de analizar los KPIs en el Dashboard Streamlit.
