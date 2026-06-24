# ClinDoc Agent

> Sistema multiagente **local** para la validación documental y la generación guiada de informes de expedientes de incapacidad temporal.

ClinDoc Agent ingiere expedientes clínicos heterogéneos, **verifica la identidad** del paciente y la **vigencia** de los documentos, y redacta informes técnicos **trazables** guiados por un guion — **100 % en local**, sin enviar la información clínica a la nube. Está pensado para apoyar al facultativo en la auditoría documental de procesos de incapacidad temporal.

## Arquitectura

Orquestación de cinco agentes especializados sobre un **grafo de estados (LangGraph)** con un **ciclo de autocorrección** (si una sección falla, se reintenta su redacción):

```
ingestion → validate_identity → validate_vigency → redact → critique ⟳ → assemble
```

| Agente | Función | Tecnología |
|---|---|---|
| **Escáner** | Ingesta y extracción layout-aware (multiformato) | Docling (+ fallback PyPDF2), MD/TXT/DOCX |
| **Verificador de Identidad** | Validación cruzada de NIF/NIE con algoritmo oficial español | regex + dígito de control |
| **Verificador de Vigencia** | Control de fechas y caducidad documental | reglas deterministas |
| **Redactor (RAG)** | Recuperación semántica + síntesis citando fuentes (Deep Linking) | Qdrant local (all-MiniLM-L6-v2, 384-d) + Ollama / `gemma3:4b` |
| **Ensamblador** | Informe técnico en PDF + anexos | ReportLab + pypdf |

La validación (identidad, contratos de datos) se apoya en **Pydantic**; toda la traza queda registrada como *chain-of-thought* para auditoría.

## Contribución central: el guion como contrato semántico

Los informes se estructuran según un **guion en YAML** (`guiones/baja_laboral.yaml`) que actúa como contrato semántico: define secciones, campos y criterios. La variante **`v5_option2/`** ejecuta el sistema dirigido por ese guion.

## Requisitos

- **Python 3.10+** — `pip install -r requirements.txt`
- **Ollama** corriendo en local con el modelo `gemma3:4b` — `ollama pull gemma3:4b`

## Uso

```bash
# Pipeline completo (orquestación LangGraph)
python run_clindoc.py

# Variante dirigida por el guion YAML
python v5_option2/run_clindoc_option2.py

# Interfaz / dashboard
streamlit run app_clindoc.py
```

Los expedientes a procesar se colocan en `datos/expedientes/<NIF>/`. Los informes se generan en `docs/informes/`.

## Estructura del repositorio (solo aplicativo)

```
run_clindoc.py              Orquestador (LangGraph) + los 5 agentes
app_clindoc.py              Interfaz / dashboard (Streamlit)
chat_asistente_medico.py    Asistente médico sobre el expediente (RAG)
historial_clinico_visual.py Visor de historial + Deep Linking
modulo_auditoria.py         Módulo de auditoría
dashboard_medico.py         Panel del facultativo
guiones/baja_laboral.yaml   Guion de informe (contrato semántico)
v5_option2/                 Variante dirigida por guion YAML
docs/                       Manuales de usuario y revisor técnico
requirements.txt            Dependencias
```

## Documentación

- **Manual de usuario (facultativo):** [`docs/MANUAL_FACULTATIVO.md`](docs/MANUAL_FACULTATIVO.md)
- **Manual del revisor técnico:** [`docs/MANUAL_REVISOR_TECNICO.md`](docs/MANUAL_REVISOR_TECNICO.md)

## Privacidad

La ejecución es **íntegramente local**: los datos clínicos no salen del equipo. Por ello, los **datos de pacientes** (`datos/`) y los **informes generados** (`docs/informes/`) **no se versionan** en este repositorio.

## Contexto

Aplicativo desarrollado en el marco de un Trabajo Fin de Máster (UNIR). El corpus de evaluación es **sintético** (generado para pruebas), por privacidad.
