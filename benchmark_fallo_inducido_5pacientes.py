# -*- coding: utf-8 -*-
"""Fallo de inferencia INDUCIDO REAL repetido en los 5 pacientes (PI-2 / OE-4).
Misma prueba que benchmark_fallo_inducido_autocorreccion.py (1er intento con un modelo Ollama inexistente
-> excepcion real; el modelo correcto se restaura antes del reintento), pero sobre los 5 pacientes y
reutilizando las colecciones Qdrant ya construidas (sin repetir la ingesta).
Rama A: ciclo activo (MAX_RETRIES=2). Rama B: sin ciclo (MAX_RETRIES=0).
Uso: python benchmark_fallo_inducido_5pacientes.py [NIF ...]"""
import sys, io, copy, json, time, hashlib
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from run_clindoc import OrquestadorLangGraph, cargar_guion_yaml
from benchmark_fallo_inducido_autocorreccion import redact_con_fallo_primer_intento, resumen_resultados

OUT = Path("benchmark_fallo_inducido_5pacientes_resultado.json")


def main():
    nifs = sys.argv[1:] or list(json.load(open("dashboard_data.json", encoding="utf-8"))["pacientes"])
    sistema = OrquestadorLangGraph(cargar_guion_yaml("guiones/baja_laboral.yaml"))
    modelo_real = sistema.redactor.modelo
    res = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {}
    for nif in nifs:
        if nif in res:
            print("ya medido", nif); continue
        sistema.indice.patient_hash = hashlib.sha256(nif.encode()).hexdigest()
        sistema.indice.nombre_coleccion = f"expediente_{sistema.indice.patient_hash}"
        base = {"documentos": [], "paciente": {"nombre": f"Paciente {nif}", "nif": nif}, "resultados": {},
                "errores": [], "retry_count": 0, "trace": [], "needs_retry": False}
        r = {}
        for rama, retries in (("ciclico_max_retries_2", 2), ("sin_ciclo_max_retries_0", 0)):
            sistema.MAX_RETRIES = retries
            st = copy.deepcopy(base)
            t0 = time.time()
            st = redact_con_fallo_primer_intento(sistema, st, modelo_real)
            primer = resumen_resultados(st["resultados"])
            st = sistema._node_critique(st)
            ciclos = 0
            while st.get("needs_retry"):
                ciclos += 1
                st = sistema._node_redact(st)
                st = sistema._node_critique(st)
            fin = resumen_resultados(st["resultados"])
            fin.update({"tiempo_s": round(time.time() - t0, 1), "n_ciclos_autocorreccion": ciclos,
                        "fallidas_tras_1er_intento": primer["n_fallidas_error"]})
            r[rama] = fin
            print(nif, rama, f"1er intento: {primer['n_fallidas_error']}/{primer['n_secciones']} fallidas -> final: "
                  f"{fin['n_fallidas_error']}/{fin['n_secciones']} (ciclos={ciclos}, {fin['tiempo_s']} s)", flush=True)
        sistema.MAX_RETRIES = 2
        res[nif] = r
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
