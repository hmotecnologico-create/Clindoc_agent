# -*- coding: utf-8 -*-
"""
NUEVO (2026-09-15): robustez real de Docling frente a OCR/PyMuPDF ante folios
DEGRADADOS (no solo PDFs vectoriales limpios como en benchmark_ingesta_real.py
y benchmark_ingesta_ampliado_v2.py). Responde directamente a la critica de
Marlon sobre PI-3 (evaluacion de ingesta "limitada") con una condicion mas
dura y mas realista: documentos escaneados de baja calidad, no PDFs nativos.

Metodologia: se toma una muestra de folios LAB reales (limpios, vectoriales),
se RASTERIZAN a imagen a una resolucion reducida (150 DPI, tipica de un scanner
de oficina economico) y se les aplica degradacion real -- no simulada en texto,
sino aplicada de verdad a los pixeles -- de 3 tipos:
  1. Rotacion/skew aleatorio (+-3 grados) -- escaneo torcido.
  2. Ruido gaussiano -- sensor de scanner de baja calidad / fotocopia.
  3. Desenfoque gaussiano leve -- enfoque imperfecto.
El resultado se reempaqueta como un PDF SOLO-IMAGEN (sin capa de texto,
igual que un documento realmente escaneado), forzando a ambos motores a
depender de OCR real, no de texto vectorial ya embebido.

Metrica: la misma ya validada en benchmark_ingesta_ampliado_v2.py (lineas con
nombre + valor decimal en la misma linea = asociacion biomarcador-valor
preservada), aplicada aqui sobre el OUTPUT REAL de Docling (con su OCR interno)
y de PyMuPDF (fitz.get_text(), que en un PDF solo-imagen no tiene capa de
texto que leer -- resultado esperado y honesto: 0%, no es un error del script).
"""
import re
import json
import time
import random
from pathlib import Path
from io import BytesIO

import fitz
import numpy as np
from PIL import Image, ImageFilter

BASE = Path("datos/expedientes/25988000R")
N_FOLIOS = 20
DPI_DEGRADADO = 150
OUT_DIR = Path("datos/_degradados_tmp")
PATRON_ASOCIACION = re.compile(r"[A-Za-zÀ-ÿ]{3,}.*\d+[.,]\d+")

random.seed(42)
np.random.seed(42)


def degradar_pdf(origen: Path, destino: Path):
    """Rasteriza la pagina 1 a DPI_DEGRADADO, aplica skew + ruido + blur reales
    a los pixeles, y reempaqueta como PDF de una sola imagen (sin texto)."""
    doc = fitz.open(origen)
    pagina = doc[0]
    zoom = DPI_DEGRADADO / 72.0
    pix = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    # 1) Skew: rotacion real +-3 grados, fondo blanco (como un folio mal alineado)
    angulo = random.uniform(-3.0, 3.0)
    img = img.rotate(angulo, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)

    # 2) Ruido gaussiano real sobre los pixeles (sensor de scanner de baja gama)
    arr = np.array(img).astype(np.float32)
    ruido = np.random.normal(0, 12, arr.shape)
    arr = np.clip(arr + ruido, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    # 3) Desenfoque gaussiano leve (enfoque imperfecto)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

    buf = BytesIO()
    img.save(buf, format="PDF", resolution=DPI_DEGRADADO)
    destino.write_bytes(buf.getvalue())


def con_pymupdf(ruta: Path) -> str:
    doc = fitz.open(ruta)
    texto = "".join(p.get_text() for p in doc)
    doc.close()
    return texto


def con_docling(ruta: Path) -> str:
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    result = conv.convert(str(ruta))
    return result.document.export_to_markdown()


def filas_asociadas(texto: str) -> int:
    return len([l for l in texto.split("\n") if PATRON_ASOCIACION.search(l)])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    muestra = sorted(BASE.glob("LAB_*.pdf"))[:N_FOLIOS]
    print(f"Muestra: {len(muestra)} folios LAB reales de 25988000R\n")

    print("Paso 1/2: degradando folios (rasterizado 150 DPI + skew + ruido + blur reales)...")
    degradados = []
    t0 = time.time()
    for f in muestra:
        dest = OUT_DIR / f"DEGRADADO_{f.name}"
        degradar_pdf(f, dest)
        degradados.append(dest)
    print(f"  {len(degradados)} folios degradados en {time.time()-t0:.1f}s\n")

    print("Paso 2/2: extrayendo con PyMuPDF (sin OCR, esperado bajo) y Docling (con OCR interno)...")
    resultados = []
    t_pymupdf_total = 0.0
    t_docling_total = 0.0
    for f in degradados:
        t0 = time.time()
        texto_pm = con_pymupdf(f)
        t_pymupdf_total += time.time() - t0
        filas_pm = filas_asociadas(texto_pm)

        t0 = time.time()
        try:
            texto_dl = con_docling(f)
            filas_dl = filas_asociadas(texto_dl)
            chars_dl = len(texto_dl)
        except Exception as e:
            texto_dl, filas_dl, chars_dl = "", 0, 0
            print(f"  [AVISO] Docling fallo en {f.name}: {e}")
        t_docling_total += time.time() - t0

        resultados.append({
            "archivo": f.name,
            "pymupdf_chars": len(texto_pm),
            "pymupdf_filas_asociadas": filas_pm,
            "docling_chars": chars_dl,
            "docling_filas_asociadas": filas_dl,
        })
        print(f"  {f.name}: PyMuPDF filas_asoc={filas_pm} (chars={len(texto_pm)}) | "
              f"Docling filas_asoc={filas_dl} (chars={chars_dl})")

    n = len(resultados)
    pm_con_asociacion = sum(1 for r in resultados if r["pymupdf_filas_asociadas"] > 0)
    dl_con_asociacion = sum(1 for r in resultados if r["docling_filas_asociadas"] > 0)

    print(f"\n==== RESULTADO: robustez ante degradacion real (n={n} folios) ====")
    print(f"PyMuPDF (sin OCR):   {pm_con_asociacion}/{n} folios con alguna asociacion biomarcador-valor "
          f"({100*pm_con_asociacion/n:.1f}%) | tiempo medio {t_pymupdf_total/n:.3f}s/folio")
    print(f"Docling (OCR interno): {dl_con_asociacion}/{n} folios con alguna asociacion biomarcador-valor "
          f"({100*dl_con_asociacion/n:.1f}%) | tiempo medio {t_docling_total/n:.2f}s/folio")

    salida = {
        "n_folios": n,
        "condicion": f"degradacion real: rasterizado {DPI_DEGRADADO} DPI + skew aleatorio +-3 grados + "
                     "ruido gaussiano (sigma=12) + desenfoque gaussiano (radio=0.8), PDF solo-imagen sin capa de texto",
        "metrica": "lineas con nombre + valor decimal en la misma linea (asociacion biomarcador-valor preservada)",
        "pymupdf_sin_ocr": {
            "tiempo_medio_s_por_folio": round(t_pymupdf_total / n, 4),
            "n_folios_con_alguna_asociacion": pm_con_asociacion,
            "pct_folios_con_alguna_asociacion": round(100 * pm_con_asociacion / n, 1),
        },
        "docling_con_ocr_interno": {
            "tiempo_medio_s_por_folio": round(t_docling_total / n, 2),
            "n_folios_con_alguna_asociacion": dl_con_asociacion,
            "pct_folios_con_alguna_asociacion": round(100 * dl_con_asociacion / n, 1),
        },
        "detalle": resultados,
    }
    out = Path("benchmark_degradacion_real_resultado.json")
    out.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado en {out}")


if __name__ == "__main__":
    main()
