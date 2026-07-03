# -*- coding: utf-8 -*-
"""
BENCHMARK REAL de inferencia SLM (tokens/segundo) — reproduce la Tabla 14 del TFM.
Mide la velocidad de generacion sostenida de cada modelo via la API de Ollama
(eval_count / eval_duration, que excluye el tiempo de carga). Compara con las cifras
reportadas en el TFM. NADA inventado: cada cifra sale de esta ejecucion.

Uso: python benchmark_slm_tokens.py
Requiere: Ollama corriendo (localhost:11434) con los modelos descargados.
"""
import json, time, urllib.request

MODELOS = ["gemma3:4b", "llama3.1:latest", "phi3:latest", "mistral:latest"]
# cifras del TFM (Tabla 14) para contrastar
TFM = {"gemma3:4b": 6.4, "llama3.1:latest": 3.7, "phi3:latest": 3.2, "mistral:latest": 2.8}

PROMPT = ("Redacta en espanol un resumen clinico breve de una baja laboral por lumbalgia "
          "mecanica: incluye diagnostico, evolucion y una recomendacion. Cita la fuente.")
NUM_PREDICT = 160


def generar(modelo, num_predict, warm=False):
    body = json.dumps({
        "model": modelo, "prompt": PROMPT, "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.2, "seed": 42},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body,
                                 {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    ec = r.get("eval_count", 0)
    ed = r.get("eval_duration", 0) or 1
    ld = r.get("load_duration", 0) / 1e9
    toks = ec / (ed / 1e9)
    return {"eval_count": ec, "tok_s": round(toks, 2), "load_s": round(ld, 1)}


def main():
    print("=== BENCHMARK REAL tok/s (Ollama) — generacion sostenida ===\n")
    filas = []
    for m in MODELOS:
        try:
            generar(m, 12, warm=True)            # warm-up (carga en RAM)
            r = generar(m, NUM_PREDICT)          # medicion real
            ref = TFM.get(m)
            delta = round(r["tok_s"] - ref, 2) if ref else None
            filas.append({"modelo": m, **r, "tfm_tabla14": ref, "delta": delta})
            print(f"{m:18} | medido {r['tok_s']:>5} tok/s  (TFM {ref})  Δ={delta}  "
                  f"[{r['eval_count']} tok, carga {r['load_s']}s]")
        except Exception as e:
            print(f"{m:18} | ERROR: {e}")
            filas.append({"modelo": m, "error": str(e)})

    out = {"prompt": PROMPT, "num_predict": NUM_PREDICT, "resultados": filas}
    with open("benchmark_slm_tokens_resultado.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nGuardado: benchmark_slm_tokens_resultado.json")


if __name__ == "__main__":
    main()
