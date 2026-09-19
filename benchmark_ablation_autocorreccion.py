# -*- coding: utf-8 -*-
"""
ABLACIÓN DEL CICLO DE AUTOCORRECCIÓN (Self-RAG) — PI-2.

Motivación: la memoria del TFM afirma que "el flujo de autocorrección de LangGraph
redujo la tasa de fallos de recuperación del 15% a 0%", pero esa cifra no está
respaldada por ningún log verificable (dashboard_data.json no registra eventos de
crítica/reintento) ni por un commit con medición documentada. Este script mide la
diferencia REAL entre:

  (A) Pipeline CÍCLICO actual (MAX_RETRIES=2, el que corre en producción)
  (B) Pipeline SIN CICLO (MAX_RETRIES=0, ablación — sin ciclo de autocorrección)

sobre el MISMO paciente y el MISMO índice ya construido (la ingesta —el costo
real de tiempo, ~45 min/paciente— se paga UNA sola vez; ambas ramas reutilizan
la misma colección Qdrant ya poblada, así que solo difieren en redact+critique).

IMPORTANTE — lo que este benchmark mide y lo que NO mide:
El único disparador de reintento en el código real es una excepción de la llamada
a Ollama (`return f"Error en IA local: {str(e)}"` en AgenteRedactor), NO un juicio
de calidad semántica ni de formato. Por tanto este benchmark mide RESILIENCIA ANTE
FALLOS TRANSITORIOS DE INFERENCIA LOCAL, no "discrepancias semánticas" como decía
la redacción anterior de PI-2 (que se corrigió en el documento a partir de este
hallazgo).

Uso:  python benchmark_ablation_autocorreccion.py <NIF>
"""
import sys
import io
import copy
import json
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from run_clindoc import OrquestadorLangGraph, cargar_guion_yaml

NIF = sys.argv[1] if len(sys.argv) > 1 else "25988000R"
OUT = Path("benchmark_ablation_autocorreccion_resultado.json")


def resumen_resultados(resultados: dict) -> dict:
    fallidas = [t for t, c in resultados.items() if (not c) or ("Error" in c)]
    abstenciones = [t for t, c in resultados.items() if c and c.startswith("Sin información documental")]
    return {
        "n_secciones": len(resultados),
        "n_fallidas_error": len(fallidas),
        "secciones_fallidas": fallidas,
        "n_abstenciones": len(abstenciones),
        "secciones_abstencion": abstenciones,
        "longitudes": {t: len(c or "") for t, c in resultados.items()},
    }


def main():
    print(f"{'=' * 60}\n  ABLACIÓN CICLO DE AUTOCORRECCIÓN — paciente {NIF}\n{'=' * 60}")

    config = cargar_guion_yaml("guiones/baja_laboral.yaml")
    print(f"Guion cargado: {len(config['secciones'])} secciones -> "
          + ", ".join(s["titulo"] for s in config["secciones"]))

    sistema = OrquestadorLangGraph(config)
    paciente = {"nombre": f"Paciente {NIF}", "nif": NIF}

    # --- Fase única de ingesta (costo real de tiempo, pagado UNA vez) ---
    print("\n[INGESTA] Escaneando + indexando expediente (esto es lo que toma tiempo real)...")
    t_ingesta = time.time()
    sistema.escanner.ruta = Path("datos/expedientes") / NIF
    sistema.indice.usar_coleccion_paciente(NIF)
    try:
        from normalizador_pdf import generar_pdfs_paciente
        generar_pdfs_paciente(NIF)
    except Exception as e:
        print(f"  [aviso] normalizador_pdf: {e}")

    state_base = {
        "documentos": [],
        "paciente": paciente,
        "resultados": {},
        "errores": [],
        "retry_count": 0,
        "trace": [],
        "needs_retry": False,
    }
    state_base = sistema._node_ingestion(state_base)
    state_base = sistema._node_validate_identity(state_base)
    state_base = sistema._node_validate_vigency(state_base)
    dt_ingesta = time.time() - t_ingesta
    print(f"[INGESTA] Completada en {dt_ingesta:.1f}s ({dt_ingesta / 60:.2f} min). "
          f"{len(state_base['documentos'])} documentos indexados.")

    resultados_finales = {"nif": NIF, "tiempo_ingesta_s": round(dt_ingesta, 1)}

    # --- Rama A: pipeline CÍCLICO (MAX_RETRIES=2, comportamiento real de producción) ---
    print(f"\n{'=' * 60}\n  RAMA A: CÍCLICO (MAX_RETRIES={sistema.MAX_RETRIES}, producción)\n{'=' * 60}")
    state_a = copy.deepcopy(state_base)
    t0 = time.time()
    state_a = sistema._node_redact(state_a)
    state_a = sistema._node_critique(state_a)
    n_ciclos_a = 0
    while state_a.get("needs_retry"):
        n_ciclos_a += 1
        state_a = sistema._node_redact(state_a)
        state_a = sistema._node_critique(state_a)
    dt_a = time.time() - t0
    resumen_a = resumen_resultados(state_a["resultados"])
    resumen_a["tiempo_s"] = round(dt_a, 1)
    resumen_a["n_ciclos_autocorreccion"] = n_ciclos_a
    resumen_a["retry_count_final"] = state_a.get("retry_count", 0)
    resumen_a["trace"] = state_a["trace"]
    print(f"[RAMA A] {resumen_a['n_fallidas_error']}/{resumen_a['n_secciones']} fallidas tras "
          f"{n_ciclos_a} ciclo(s) de autocorrección, en {dt_a:.1f}s")
    resultados_finales["ciclico_max_retries_2"] = resumen_a

    # --- Rama B: pipeline SIN CICLO (MAX_RETRIES=0, ablación) ---
    print(f"\n{'=' * 60}\n  RAMA B: SIN CICLO (MAX_RETRIES=0, ablación — sin autocorrección)\n{'=' * 60}")
    sistema.MAX_RETRIES = 0
    state_b = copy.deepcopy(state_base)
    t0 = time.time()
    state_b = sistema._node_redact(state_b)
    state_b = sistema._node_critique(state_b)
    n_ciclos_b = 0
    while state_b.get("needs_retry"):
        n_ciclos_b += 1
        state_b = sistema._node_redact(state_b)
        state_b = sistema._node_critique(state_b)
    dt_b = time.time() - t0
    resumen_b = resumen_resultados(state_b["resultados"])
    resumen_b["tiempo_s"] = round(dt_b, 1)
    resumen_b["n_ciclos_autocorreccion"] = n_ciclos_b
    resumen_b["retry_count_final"] = state_b.get("retry_count", 0)
    resumen_b["trace"] = state_b["trace"]
    print(f"[RAMA B] {resumen_b['n_fallidas_error']}/{resumen_b['n_secciones']} fallidas sin autocorrección, "
          f"en {dt_b:.1f}s")
    resultados_finales["sin_ciclo_max_retries_0"] = resumen_b
    sistema.MAX_RETRIES = 2  # restaurar

    # --- Comparación ---
    tasa_a = resumen_a["n_fallidas_error"] / resumen_a["n_secciones"] if resumen_a["n_secciones"] else 0
    tasa_b = resumen_b["n_fallidas_error"] / resumen_b["n_secciones"] if resumen_b["n_secciones"] else 0
    resultados_finales["tasa_fallo_ciclico"] = round(tasa_a * 100, 1)
    resultados_finales["tasa_fallo_sin_ciclo"] = round(tasa_b * 100, 1)

    print(f"\n{'=' * 60}\n  RESULTADO\n{'=' * 60}")
    print(f"  Tasa de fallo CÍCLICO (con autocorrección): {resultados_finales['tasa_fallo_ciclico']}%")
    print(f"  Tasa de fallo SIN CICLO (sin autocorrección): {resultados_finales['tasa_fallo_sin_ciclo']}%")

    OUT.write_text(json.dumps(resultados_finales, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados guardados en {OUT}")


if __name__ == "__main__":
    main()
