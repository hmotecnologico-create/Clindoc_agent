# -*- coding: utf-8 -*-
"""
Ampliación real de benchmark_ingesta_real.py (Tabla 13) para responder a la
observación de Marlon sobre PI-3: "la superioridad de Docling frente a OCR
lineal se apoya en una evaluación limitada, no en un conjunto suficientemente
amplio de documentos". El benchmark original comparó 15 folios LAB de un solo
paciente; este amplía a 100 folios LAB repartidos entre los 5 pacientes del
corpus (20 por paciente), para cubrir variabilidad entre expedientes, no solo
dentro de uno. Compara Docling vs PyMuPDF (fitz) -- ambos instalados y
ejecutados de verdad -- midiendo tiempo de extracción y preservación de
estructura de tabla (filas markdown con separador '|', proxy de la asociación
biomarcador-valor-unidad).
"""
import time
import json
from pathlib import Path

BASE = Path("datos/expedientes")
PACIENTES = ["25988000R", "33445566R", "48991234S", "52880483X", "75114422X"]
N_POR_PACIENTE = 20

MUESTRA = []
for nif in PACIENTES:
    archivos = sorted((BASE / nif).glob("LAB_*.pdf"))[:N_POR_PACIENTE]
    MUESTRA.extend(archivos)

print(f"Muestra total: {len(MUESTRA)} folios LAB ({N_POR_PACIENTE} x {len(PACIENTES)} pacientes)")


def con_docling():
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    resultados = []
    t0 = time.time()
    for idx, f in enumerate(MUESTRA, start=1):
        r = conv.convert(f)
        md = r.document.export_to_markdown()
        filas_tabla = [l for l in md.split("\n") if l.strip().startswith("|")]
        resultados.append({"archivo": f.name, "chars": len(md), "filas_tabla_detectadas": len(filas_tabla)})
        if idx % 10 == 0 or idx == len(MUESTRA):
            print(f"  [Docling {idx}/{len(MUESTRA)}] {time.time()-t0:.0f}s transcurridos")
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def con_pymupdf():
    import fitz
    resultados = []
    t0 = time.time()
    for f in MUESTRA:
        doc = fitz.open(f)
        texto = "".join(p.get_text() for p in doc)
        filas_tabla = [l for l in texto.split("\n") if "|" in l]
        resultados.append({"archivo": f.name, "chars": len(texto), "filas_tabla_detectadas": len(filas_tabla)})
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def main():
    print(f"\n{'='*60}\n  BENCHMARK INGESTA AMPLIADO -- {len(MUESTRA)} folios\n{'='*60}")

    print("\n[1/2] Ejecutando Docling...")
    res_docling = con_docling()
    ok_docling = sum(1 for r in res_docling["resultados"] if r["filas_tabla_detectadas"] > 0)
    print(f"  Docling: {res_docling['tiempo_total']}s total "
          f"({res_docling['tiempo_total']/len(MUESTRA):.2f}s/folio), "
          f"{ok_docling}/{len(MUESTRA)} folios con estructura de tabla detectada")

    print("\n[2/2] Ejecutando PyMuPDF...")
    res_pymupdf = con_pymupdf()
    ok_pymupdf = sum(1 for r in res_pymupdf["resultados"] if r["filas_tabla_detectadas"] > 0)
    print(f"  PyMuPDF: {res_pymupdf['tiempo_total']}s total "
          f"({res_pymupdf['tiempo_total']/len(MUESTRA):.3f}s/folio), "
          f"{ok_pymupdf}/{len(MUESTRA)} folios con estructura de tabla detectada")

    salida = {
        "n_folios": len(MUESTRA),
        "n_pacientes": len(PACIENTES),
        "folios_por_paciente": N_POR_PACIENTE,
        "docling": {
            "tiempo_total_s": res_docling["tiempo_total"],
            "tiempo_por_folio_s": round(res_docling["tiempo_total"] / len(MUESTRA), 3),
            "folios_con_tabla_ok": ok_docling,
            "pct_preservacion_estructura": round(100 * ok_docling / len(MUESTRA), 1),
            "detalle": res_docling["resultados"],
        },
        "pymupdf": {
            "tiempo_total_s": res_pymupdf["tiempo_total"],
            "tiempo_por_folio_s": round(res_pymupdf["tiempo_total"] / len(MUESTRA), 4),
            "folios_con_tabla_ok": ok_pymupdf,
            "pct_preservacion_estructura": round(100 * ok_pymupdf / len(MUESTRA), 1),
            "detalle": res_pymupdf["resultados"],
        },
    }

    out = Path("benchmark_ingesta_ampliado_resultado.json")
    out.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}\n  RESULTADO FINAL ({len(MUESTRA)} folios, {len(PACIENTES)} pacientes)\n{'='*60}")
    print(f"  Docling:  {salida['docling']['pct_preservacion_estructura']}% preservación de estructura "
          f"({salida['docling']['tiempo_por_folio_s']}s/folio)")
    print(f"  PyMuPDF:  {salida['pymupdf']['pct_preservacion_estructura']}% preservación de estructura "
          f"({salida['pymupdf']['tiempo_por_folio_s']}s/folio)")
    print(f"\nGuardado en {out}")


if __name__ == "__main__":
    main()
