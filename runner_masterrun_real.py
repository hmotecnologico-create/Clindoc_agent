# -*- coding: utf-8 -*-
"""Re-ejecuta el Master Run REAL con el pipeline de ClinDoc (run_clindoc.py)
midiendo el tiempo end-to-end verdadero en este hardware. No toca dashboard_data.json."""
import sys, io, time, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from run_clindoc import OrquestadorLangGraph

OUT = Path(r"F:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\ClinDoc_Docs\Segunda revision\benchmark_real")
TEMP_DASH = OUT / "dashboard_masterrun_real.json"

config = {
    "titulo": "Master Run REAL (medicion empirica de tiempo)",
    "secciones": [
        {"id": "A1", "titulo": "Antecedentes de Salud", "instruccion": "Sintetice hallazgos cardiacos y quirurgicos previos."},
        {"id": "A2", "titulo": "Evolucion Clinica Reciente", "instruccion": "Evalue la respuesta al tratamiento post-operatorio."},
        {"id": "A3", "titulo": "Recomendaciones", "instruccion": "Defina pautas de reposo y seguimiento medico."},
    ]
}

corpus = Path("datos/_masterrun_real/12345678Z")
ndocs = len(list(corpus.glob("*.md")))
print(f"Iniciando Master Run REAL sobre {ndocs} documentos...")
print(f"Hardware: este equipo (CPU, sin GPU) | Modelo: gemma3:4b local")

sistema = OrquestadorLangGraph(config)
try:
    sistema.recorder.output_file = str(TEMP_DASH)
except Exception:
    pass
sistema.escanner.ruta = corpus
try:
    sistema.recorder.set_paciente("12345678Z", "Paciente Master Run")
except Exception as e:
    print("aviso recorder:", e)

t0 = time.time()
resultados = sistema.ejecutar({"nombre": "Paciente Master Run", "nif": "12345678Z"})
elapsed = time.time() - t0

print("\n" + "="*55)
print(f"  MASTER RUN REAL COMPLETADO")
print(f"  Documentos procesados: {ndocs}")
print(f"  TIEMPO TOTAL END-TO-END: {elapsed:.1f} s  ({elapsed/60:.2f} min)")
print("="*55)

# Guardar metrica
metric = {"documentos": ndocs, "tiempo_total_s": round(elapsed,1), "tiempo_total_min": round(elapsed/60,2),
          "hardware": "CPU local sin GPU", "modelo": "gemma3:4b", "secciones": len(config["secciones"])}
(OUT / "masterrun_real_tiempo.json").write_text(json.dumps(metric, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(metric, indent=2, ensure_ascii=False))
