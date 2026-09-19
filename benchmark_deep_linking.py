# -*- coding: utf-8 -*-
"""Medicion REAL del anclaje del Deep Linking (Tabla 10, requisito de trazabilidad).
Para cada linea con cita [Fuente: folio] de las secciones finales de los informes de los 5
pacientes (dashboard_data.json), reproduce lo que hace el visor (app_clindoc.mostrar_documento):
localizar_en_pdf(PDF canonico del folio citado, linea) y comprueba que devuelve coordenadas.
Uso: python benchmark_deep_linking.py"""
import json, re
from pathlib import Path
from normalizador_pdf import localizar_en_pdf

PDFS = Path("datos/expedientes")
RE_CITA = r'\[Fuente:\s*([^\]#]+?)\s*(?:#[^\]]+)?\]'

def main():
    data = json.load(open("dashboard_data.json", encoding="utf-8"))["pacientes"]
    filas, por_paciente = [], {}
    for nif, p in data.items():
        ultimas = {}
        for e in p["events"]:
            if e["type"] == "analisis_seccion":
                ultimas[e["details"]["seccion"]] = e["details"]["texto"]
        n = ok = 0
        for seccion, texto in ultimas.items():
            for linea in texto.split("\n"):
                for arch in sorted(set(re.findall(RE_CITA, linea))):
                    pdf = PDFS / nif / arch
                    n += 1
                    if not pdf.exists():
                        filas.append({"nif": nif, "seccion": seccion, "folio": arch, "anclado": False, "motivo": "sin PDF canonico"})
                        continue
                    pagina, rects = localizar_en_pdf(str(pdf), linea)
                    hit = bool(rects)
                    ok += hit
                    filas.append({"nif": nif, "seccion": seccion, "folio": arch, "pagina": pagina + 1 if hit else None,
                                  "n_rects": len(rects), "anclado": hit})
        por_paciente[nif] = {"aserciones_citadas": n, "ancladas": ok}
    tot = sum(v["aserciones_citadas"] for v in por_paciente.values())
    okt = sum(v["ancladas"] for v in por_paciente.values())
    res = {"metrica": "lineas con cita [Fuente: folio] cuyo fragmento localizar_en_pdf localiza (devuelve bbox) en el PDF canonico",
           "total_citas": tot, "ancladas": okt, "pct": round(100 * okt / tot, 1) if tot else None,
           "por_paciente": por_paciente, "detalle": filas}
    Path("benchmark_deep_linking_resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "detalle"}, ensure_ascii=False, indent=2))
    for f in filas:
        if not f["anclado"]: print("NO ANCLADO:", f)

if __name__ == "__main__":
    main()
