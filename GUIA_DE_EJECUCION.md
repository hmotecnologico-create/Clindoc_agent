# Guía de ejecución — ClinDoc Agent

Cómo poner en marcha el sistema tras clonarlo desde GitHub. Pensada para un evaluador que parte de cero.

> **Importante (privacidad):** el repositorio **no incluye datos clínicos** ni informes generados (están excluidos por `.gitignore`). Al clonar obtienes **solo el código**. Los datos se generan o se aportan localmente (ver Paso 4).

---

## 1. Requisitos previos

| Requisito | Versión | Notas |
|---|---|---|
| **Python** | 3.10 o superior | `python --version` |
| **Git** | cualquiera reciente | para clonar |
| **Ollama** | última | servidor de modelos local — https://ollama.com/download |
| **RAM** | ~8 GB recomendado | el modelo `gemma3:4b` ocupa ~3,3 GB |

El sistema corre **100 % en local**: ningún dato sale del equipo.

---

## 2. Clonar el repositorio

```bash
git clone https://github.com/hmotecnologico-create/Clindoc_agent.git
cd Clindoc_agent
```

## 3. Entorno e instalación de dependencias

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. Instalar el modelo de lenguaje (Ollama)

Con Ollama instalado y en ejecución:

```bash
ollama pull gemma3:4b
```

> El sistema usa **`gemma3:4b`** (redacción) y **`all-MiniLM-L6-v2`** (embeddings, se descarga solo la primera vez). Si `gemma3:4b` no está, el sistema cae a otro modelo local disponible, pero **los resultados documentados corresponden a `gemma3:4b`**.

## 5. Datos: usar los de prueba o aportar los tuyos

Tienes dos opciones:

- **Opción A — arranque inmediato (datos de prueba):** no hagas nada. Al ejecutar el pipeline por primera vez, si no hay expedientes, el sistema **crea automáticamente dos pacientes de prueba** mínimos.
- **Opción B — tus propios expedientes:** coloca los documentos de cada paciente en una carpeta con su NIF:
  ```
  datos/expedientes/<NIF>/  →  documento1.md, analitica.txt, informe.pdf, ...
  ```
  Formatos admitidos: `.md`, `.txt`, `.pdf`, `.docx` e imágenes (los exámenes por imagen no se interpretan: revisión manual del facultativo).

---

## 6. Ejecución (en dos pasos, en este orden)

### Paso 1 — Procesar los expedientes (genera `dashboard_data.json`)

```bash
python run_clindoc.py
```

Esto ejecuta la orquestación multiagente (LangGraph): ingesta → identidad → vigencia → redacción guiada por el guion YAML → autocorrección → ensamblado. Procesa **todos** los pacientes de `datos/expedientes/` y escribe `dashboard_data.json`.

> Para procesar **un solo paciente**: `python run_clindoc.py <NIF>` (p. ej. `python run_clindoc.py 12345678Z`). Tarda ~5–7 min por expediente grande.

### Paso 2 — Lanzar la interfaz (dashboard del facultativo)

```bash
streamlit run app_clindoc.py
```

Se abre en el navegador (normalmente http://localhost:8501). Si ves *"No hay pacientes procesados"*, es que falta ejecutar el **Paso 1** primero.

---

## 7. Variante dirigida explícitamente por el guion YAML (opcional)

El demo principal ya carga `guiones/baja_laboral.yaml`. Existe además una variante separada:

```bash
python v5_option2/run_clindoc_option2.py
```

---

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Error en IA local` / respuestas vacías | Ollama no está en ejecución o falta el modelo | Abre Ollama y ejecuta `ollama pull gemma3:4b`; comprueba con `ollama list` |
| La app dice *"No hay pacientes procesados"* | No se ha generado `dashboard_data.json` | Ejecuta primero `python run_clindoc.py` (Paso 1) |
| `LLM Activo` muestra otro modelo | `gemma3:4b` no instalado | `ollama pull gemma3:4b` y recarga |
| Puerto 8501 ocupado | otra instancia de Streamlit | `streamlit run app_clindoc.py --server.port 8502` |
| Error al abrir Qdrant (lock) | otra ejecución usa la BD vectorial | cierra el otro proceso; la BD se recrea por paciente |
| Descarga lenta de dependencias | `docling`/`torch` son grandes | espera; es de una sola vez |

---

## 9. Estructura del repositorio (código)

```
run_clindoc.py              Orquestador (LangGraph) + los 5 agentes
app_clindoc.py              Interfaz / dashboard (Streamlit)
chat_asistente_medico.py    Asistente que busca en los folios del paciente
historial_clinico_visual.py Visor de historial + trazabilidad
modulo_auditoria.py         Módulo de auditoría
guiones/baja_laboral.yaml   Guion del informe (contrato semántico)
v5_option2/                 Variante dirigida por guion YAML
docs/                       Manuales (facultativo y revisor técnico)
datos/                      (vacía al clonar; aquí van los expedientes locales)
requirements.txt            Dependencias
```

---

**Resumen en 4 líneas:**
```bash
git clone https://github.com/hmotecnologico-create/Clindoc_agent.git && cd Clindoc_agent
python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt   # (Linux/mac: source venv/bin/activate)
ollama pull gemma3:4b
python run_clindoc.py  &&  streamlit run app_clindoc.py
```
