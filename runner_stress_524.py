# -*- coding: utf-8 -*-
"""PRUEBA DE ESTRES REAL sobre el corpus de ~524 folios/paciente (2 pacientes).
Mide el tiempo end-to-end VERDADERO del pipeline ClinDoc en este hardware."""
import sys, io, time, json, glob
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from run_clindoc import OrquestadorLangGraph

OUT = Path(r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Segunda revision\benchmark_real")
config = {"titulo": "Prueba de Estres 524 Folios",
    "secciones": [
        {"id":"A1","titulo":"Antecedentes de Salud","instruccion":"Sintetice hallazgos cardiacos y quirurgicos previos."},
        {"id":"A2","titulo":"Evolucion Clinica Reciente","instruccion":"Evalue la respuesta al tratamiento."},
        {"id":"A3","titulo":"Recomendaciones","instruccion":"Defina pautas de reposo y seguimiento."}]}

BASE = Path("datos/expedientes_524")
pacientes = sorted([d for d in BASE.iterdir() if d.is_dir()])
sistema = OrquestadorLangGraph(config)
try: sistema.recorder.output_file = str(OUT / "dashboard_stress_524.json")
except: pass

resultados = {"por_paciente": [], "hardware": "CPU local sin GPU", "modelo": "gemma3:4b"}
t_global = time.time()
for carpeta in pacientes:
    nif = carpeta.name
    archivos = glob.glob(str(carpeta / "*.md"))
    palabras = sum(len(Path(f).read_text(encoding="utf-8", errors="ignore").split()) for f in archivos)
    folios = palabras // 300
    print(f"\n{'='*55}\n  PACIENTE {nif}: {len(archivos)} archivos, ~{folios} folios ({palabras:,} palabras)\n{'='*55}")
    sistema.escanner.ruta = carpeta
    try: sistema.recorder.set_paciente(nif, f"Paciente {nif}")
    except Exception as e: print("aviso:", e)
    t0 = time.time()
    try:
        sistema.ejecutar({"nombre": f"Paciente {nif}", "nif": nif})
        dt = time.time() - t0
        print(f"\n  >>> {nif} procesado en {dt:.1f}s ({dt/60:.2f} min)")
        resultados["por_paciente"].append({"nif": nif, "archivos": len(archivos), "folios": folios,
                                            "palabras": palabras, "tiempo_s": round(dt,1), "tiempo_min": round(dt/60,2)})
    except Exception as e:
        dt = time.time() - t0
        print(f"\n  !!! ERROR en {nif} tras {dt:.1f}s: {e}")
        resultados["por_paciente"].append({"nif": nif, "folios": folios, "tiempo_s": round(dt,1), "error": str(e)})

resultados["tiempo_total_s"] = round(time.time()-t_global, 1)
resultados["tiempo_total_min"] = round((time.time()-t_global)/60, 2)
(OUT / "stress_524_resultados.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n{'='*55}\n  PRUEBA DE ESTRES COMPLETADA")
print(f"  Tiempo total ({len(pacientes)} pacientes): {resultados['tiempo_total_min']} min")
print(f"{'='*55}")
print(json.dumps(resultados, indent=2, ensure_ascii=False))
