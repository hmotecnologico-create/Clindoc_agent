# -*- coding: utf-8 -*-
"""
NUEVO (2026-09-15): fallo de inferencia INDUCIDO REAL para PI-2.

Motivacion: benchmark_ablation_autocorreccion.py ya midio el comportamiento del
ciclo de autocorreccion bajo condiciones NORMALES -- y dio un resultado NULO
honesto (0% de fallos en ambas ramas, ciclica y sin ciclo) porque Ollama no lanzo
ninguna excepcion real durante esa corrida. Un resultado nulo demuestra que no
hay diferencia EN ESAS CONDICIONES, pero no demuestra que el ciclo de
autocorreccion realmente recupere de un fallo cuando SI ocurre uno real.

Este script fuerza un fallo REAL y reproducible (no simulado en texto): en el
PRIMER intento de redaccion se apunta `sistema.redactor.modelo` a un nombre de
modelo Ollama que NO EXISTE, por lo que `ollama.chat(...)` lanza una excepcion
real de verdad (capturada por AgenteRedactor como "Error en IA local: ..."),
igual que ocurriria si el modelo real se hubiera descargado, la conexion a
Ollama hubiera caido, o el proceso hubiera muerto a mitad de inferencia -- son
fallos transitorios reales de la infraestructura de inferencia local. Justo
antes de que el ciclo de autocorreccion dispare el reintento, se restaura el
nombre de modelo correcto, simulando que el fallo transitorio se resolvio por
si solo (el escenario real que MAX_RETRIES esta pensado para cubrir).

Comparacion:
  (A) CICLICO (MAX_RETRIES=2): primer intento falla (modelo invalido) -> el
      ciclo de critica detecta el fallo -> reintenta -> segundo intento usa el
      modelo correcto -> deberia recuperar.
  (B) SIN CICLO (MAX_RETRIES=0): primer intento falla igual -> no hay reintento ->
      el fallo queda permanente en el informe final.

Reutiliza la MISMA ingesta/indice ya construido que benchmark_ablation_autocorreccion.py
(no se re-ingesta el expediente completo).

Uso:  python benchmark_fallo_inducido_autocorreccion.py <NIF>
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
OUT = Path("benchmark_fallo_inducido_autocorreccion_resultado.json")
MODELO_INVALIDO = "modelo-inexistente-para-forzar-fallo-real"


def resumen_resultados(resultados: dict) -> dict:
    fallidas = [t for t, c in resultados.items() if (not c) or ("Error" in c)]
    return {
        "n_secciones": len(resultados),
        "n_fallidas_error": len(fallidas),
        "secciones_fallidas": fallidas,
        "longitudes": {t: len(c or "") for t, c in resultados.items()},
    }


def redact_con_fallo_primer_intento(sistema, state, modelo_real):
    """Ejecuta _node_redact con el modelo INVALIDO forzado (fallo real de
    ollama.chat), luego restaura el modelo real antes de devolver el control
    -- el propio ciclo de critica/reintento del sistema decide si vuelve a
    llamar a _node_redact (con el modelo ya restaurado) o no."""
    sistema.redactor.modelo = MODELO_INVALIDO
    state = sistema._node_redact(state)
    sistema.redactor.modelo = modelo_real  # el "fallo transitorio" se resuelve solo
    return state


def main():
    print(f"{'=' * 60}\n  FALLO INDUCIDO REAL EN AUTOCORRECCION — paciente {NIF}\n{'=' * 60}")

    config = cargar_guion_yaml("guiones/baja_laboral.yaml")
    sistema = OrquestadorLangGraph(config)
    modelo_real = sistema.redactor.modelo
    print(f"Modelo real: {modelo_real} | Modelo invalido forzado en 1er intento: {MODELO_INVALIDO}")
    paciente = {"nombre": f"Paciente {NIF}", "nif": NIF}

    print("\n[INGESTA] Escaneando + indexando expediente (reutilizable, se paga una vez)...")
    t_ingesta = time.time()
    sistema.escanner.ruta = Path("datos/expedientes") / NIF
    sistema.indice.usar_coleccion_paciente(NIF)
    try:
        from normalizador_pdf import generar_pdfs_paciente
        generar_pdfs_paciente(NIF)
    except Exception as e:
        print(f"  [aviso] normalizador_pdf: {e}")

    state_base = {
        "documentos": [], "paciente": paciente, "resultados": {}, "errores": [],
        "retry_count": 0, "trace": [], "needs_retry": False,
    }
    state_base = sistema._node_ingestion(state_base)
    state_base = sistema._node_validate_identity(state_base)
    state_base = sistema._node_validate_vigency(state_base)
    dt_ingesta = time.time() - t_ingesta
    print(f"[INGESTA] Completada en {dt_ingesta:.1f}s. {len(state_base['documentos'])} documentos indexados.")

    resultados_finales = {"nif": NIF, "tiempo_ingesta_s": round(dt_ingesta, 1),
                           "modelo_real": modelo_real, "modelo_invalido_forzado": MODELO_INVALIDO}

    # --- Rama A: CICLICO ---
    print(f"\n{'=' * 60}\n  RAMA A: CICLICO (MAX_RETRIES={sistema.MAX_RETRIES}) -- 1er intento con modelo INVALIDO\n{'=' * 60}")
    state_a = copy.deepcopy(state_base)
    t0 = time.time()
    state_a = redact_con_fallo_primer_intento(sistema, state_a, modelo_real)
    resumen_1er_intento_a = resumen_resultados(state_a["resultados"])
    print(f"  [1er intento, modelo invalido] {resumen_1er_intento_a['n_fallidas_error']}/{resumen_1er_intento_a['n_secciones']} fallidas (esperado: todas)")
    state_a = sistema._node_critique(state_a)
    n_ciclos_a = 0
    while state_a.get("needs_retry"):
        n_ciclos_a += 1
        state_a = sistema._node_redact(state_a)  # ya con modelo_real restaurado
        state_a = sistema._node_critique(state_a)
    dt_a = time.time() - t0
    resumen_a = resumen_resultados(state_a["resultados"])
    resumen_a["tiempo_s"] = round(dt_a, 1)
    resumen_a["n_ciclos_autocorreccion"] = n_ciclos_a
    resumen_a["fallidas_tras_1er_intento_modelo_invalido"] = resumen_1er_intento_a["n_fallidas_error"]
    print(f"[RAMA A] TRAS {n_ciclos_a} ciclo(s) de autocorreccion: {resumen_a['n_fallidas_error']}/{resumen_a['n_secciones']} fallidas (final)")
    resultados_finales["ciclico_max_retries_2"] = resumen_a

    # --- Rama B: SIN CICLO ---
    print(f"\n{'=' * 60}\n  RAMA B: SIN CICLO (MAX_RETRIES=0) -- 1er intento con modelo INVALIDO, SIN reintento\n{'=' * 60}")
    sistema.MAX_RETRIES = 0
    state_b = copy.deepcopy(state_base)
    t0 = time.time()
    state_b = redact_con_fallo_primer_intento(sistema, state_b, modelo_real)
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
    print(f"[RAMA B] SIN autocorreccion (MAX_RETRIES=0): {resumen_b['n_fallidas_error']}/{resumen_b['n_secciones']} fallidas (final, permanente)")
    resultados_finales["sin_ciclo_max_retries_0"] = resumen_b
    sistema.MAX_RETRIES = 2

    tasa_a = resumen_a["n_fallidas_error"] / resumen_a["n_secciones"] if resumen_a["n_secciones"] else 0
    tasa_b = resumen_b["n_fallidas_error"] / resumen_b["n_secciones"] if resumen_b["n_secciones"] else 0
    resultados_finales["tasa_fallo_final_ciclico"] = round(tasa_a * 100, 1)
    resultados_finales["tasa_fallo_final_sin_ciclo"] = round(tasa_b * 100, 1)

    print(f"\n{'=' * 60}\n  RESULTADO — recuperacion real ante un fallo de inferencia inducido\n{'=' * 60}")
    print(f"  Tasa de fallo FINAL, CICLICO (con autocorreccion): {resultados_finales['tasa_fallo_final_ciclico']}%")
    print(f"  Tasa de fallo FINAL, SIN CICLO (sin autocorreccion): {resultados_finales['tasa_fallo_final_sin_ciclo']}%")

    OUT.write_text(json.dumps(resultados_finales, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados guardados en {OUT}")


if __name__ == "__main__":
    main()
