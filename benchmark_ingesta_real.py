# -*- coding: utf-8 -*-
"""
Comparativa REAL de motores de ingesta sobre el mismo corpus (Tabla 13 del TFM).
Docling vs PyMuPDF (fitz) -- ambos instalados y ejecutados de verdad.
Mide: tiempo de extraccion, preservacion de estructura de tabla (deteccion de
la asociacion biomarcador-valor-unidad), longitud de texto extraido.
"""
import time
import json
from pathlib import Path

CORPUS = Path("datos/expedientes/25988000R")
MUESTRA = sorted(CORPUS.glob("LAB_*.pdf"))[:15]  # folios analiticos: tienen tablas reales
MUESTRA_PEQUENA = MUESTRA[:5]  # para Tesseract/Marker (mas lentos)


def con_docling():
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    resultados = []
    t0 = time.time()
    for f in MUESTRA:
        r = conv.convert(f)
        md = r.document.export_to_markdown()
        # Deteccion de estructura de tabla markdown (pipe-tables preservan biomarcador|valor|unidad)
        filas_tabla = [l for l in md.split("\n") if l.strip().startswith("|")]
        resultados.append({"archivo": f.name, "chars": len(md), "filas_tabla_detectadas": len(filas_tabla)})
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def con_pymupdf():
    import fitz
    resultados = []
    t0 = time.time()
    for f in MUESTRA:
        doc = fitz.open(f)
        texto = "".join(p.get_text() for p in doc)
        # PyMuPDF linealiza: no hay marcador de tabla, solo texto plano por lineas
        filas_tabla = [l for l in texto.split("\n") if "|" in l]
        resultados.append({"archivo": f.name, "chars": len(texto), "filas_tabla_detectadas": len(filas_tabla)})
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def con_tesseract():
    import os
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    os.environ["TESSDATA_PREFIX"] = str(Path("datos/_tessdata").resolve())
    resultados = []
    t0 = time.time()
    for f in MUESTRA_PEQUENA:
        doc = __import__("fitz").open(f)
        pix = doc[0].get_pixmap(dpi=200)
        img_path = Path(f"datos/_tmp_ocr_{f.stem}.png")
        pix.save(img_path)
        from PIL import Image
        texto = pytesseract.image_to_string(Image.open(img_path), lang="spa")
        img_path.unlink(missing_ok=True)
        filas_tabla = [l for l in texto.split("\n") if "|" in l]
        resultados.append({"archivo": f.name, "chars": len(texto), "filas_tabla_detectadas": len(filas_tabla)})
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def con_marker():
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    modelos = create_model_dict()
    conv = PdfConverter(artifact_dict=modelos)
    resultados = []
    t0 = time.time()
    for f in MUESTRA_PEQUENA:
        rendered = conv(str(f))
        texto, _, _ = text_from_rendered(rendered)
        filas_tabla = [l for l in texto.split("\n") if l.strip().startswith("|")]
        resultados.append({"archivo": f.name, "chars": len(texto), "filas_tabla_detectadas": len(filas_tabla)})
    return {"tiempo_total": round(time.time() - t0, 2), "resultados": resultados}


def main():
    print(f"=== Comparativa real de ingesta: Docling vs PyMuPDF ({len(MUESTRA)} folios analiticos) ===\n")

    print("[Docling] procesando...")
    doc_docling = con_docling()
    print(f"  tiempo total: {doc_docling['tiempo_total']}s | "
          f"{round(doc_docling['tiempo_total']/len(MUESTRA), 3)}s/folio")
    total_filas_docling = sum(r["filas_tabla_detectadas"] for r in doc_docling["resultados"])
    print(f"  filas de tabla detectadas (total): {total_filas_docling}")

    print("\n[PyMuPDF] procesando...")
    doc_pymupdf = con_pymupdf()
    print(f"  tiempo total: {doc_pymupdf['tiempo_total']}s | "
          f"{round(doc_pymupdf['tiempo_total']/len(MUESTRA), 3)}s/folio")
    total_filas_pymupdf = sum(r["filas_tabla_detectadas"] for r in doc_pymupdf["resultados"])
    print(f"  filas de tabla detectadas (total): {total_filas_pymupdf}")

    print(f"\n[Tesseract OCR] procesando {len(MUESTRA_PEQUENA)} folios (muestra reducida, mas lento)...")
    doc_tess = con_tesseract()
    print(f"  tiempo total: {doc_tess['tiempo_total']}s | "
          f"{round(doc_tess['tiempo_total']/len(MUESTRA_PEQUENA), 3)}s/folio")
    total_filas_tess = sum(r["filas_tabla_detectadas"] for r in doc_tess["resultados"])
    print(f"  filas de tabla detectadas (total): {total_filas_tess}")

    print(f"\n[Marker] procesando {len(MUESTRA_PEQUENA)} folios (muestra reducida, descarga modelos la 1a vez)...")
    doc_marker = con_marker()
    print(f"  tiempo total: {doc_marker['tiempo_total']}s | "
          f"{round(doc_marker['tiempo_total']/len(MUESTRA_PEQUENA), 3)}s/folio")
    total_filas_marker = sum(r["filas_tabla_detectadas"] for r in doc_marker["resultados"])
    print(f"  filas de tabla detectadas (total): {total_filas_marker}")

    print(f"\n=== RESUMEN ===")
    print(f"  Velocidad: Docling {round(len(MUESTRA)/doc_docling['tiempo_total'],2)} folios/s | "
          f"PyMuPDF {round(len(MUESTRA)/doc_pymupdf['tiempo_total'],2)} folios/s | "
          f"Tesseract {round(len(MUESTRA_PEQUENA)/doc_tess['tiempo_total'],2)} folios/s | "
          f"Marker {round(len(MUESTRA_PEQUENA)/doc_marker['tiempo_total'],2)} folios/s")
    print(f"  Estructura de tabla preservada (15 folios Docling/PyMuPDF, 5 folios Tesseract/Marker):")
    print(f"    Docling={total_filas_docling} | PyMuPDF={total_filas_pymupdf} | Tesseract={total_filas_tess} | Marker={total_filas_marker}")

    out = {"muestra": len(MUESTRA), "docling": doc_docling, "pymupdf": doc_pymupdf,
           "tesseract": doc_tess, "marker": doc_marker,
           "filas_tabla_totales": {"docling": total_filas_docling, "pymupdf": total_filas_pymupdf,
                                    "tesseract": total_filas_tess, "marker": total_filas_marker}}
    Path("benchmark_ingesta_real_resultado.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado: benchmark_ingesta_real_resultado.json")


if __name__ == "__main__":
    main()
