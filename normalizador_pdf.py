# -*- coding: utf-8 -*-
"""
Normalización de folios HETEROGÉNEOS a PDF canónico + localización por coordenadas.

La ingesta recibe documentos en cualquier formato (.md, .txt, .docx, imágenes, .pdf)
y los convierte a un PDF canónico. Sobre ese PDF se extraen las coordenadas (bounding box)
de cada fragmento, lo que habilita el Deep Linking forense (recuadro sobre la línea exacta).
"""
import html
import shutil
import subprocess
from pathlib import Path

_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def _texto_a_pdf(texto, salida):
    """Renderiza texto (.md/.txt) a un PDF paginado y con texto extraíble (reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    estilo = ParagraphStyle("cuerpo", fontName="Helvetica", fontSize=9, leading=12)
    doc = SimpleDocTemplate(str(salida), pagesize=A4,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    flow = []
    for linea in (texto or "").split("\n"):
        if linea.strip():
            flow.append(Paragraph(html.escape(linea), estilo))
        else:
            flow.append(Spacer(1, 6))
    doc.build(flow or [Paragraph("(documento vacío)", estilo)])


def _imagen_a_pdf(ruta_img, salida):
    """Embebe una imagen (folio escaneado) en una página PDF."""
    import fitz
    imgdoc = fitz.open(str(ruta_img))
    pdfbytes = imgdoc.convert_to_pdf()
    imgdoc.close()
    out = fitz.open("pdf", pdfbytes)
    out.save(str(salida))
    out.close()


def _docx_a_pdf(ruta_docx, salida):
    """Convierte .docx/.doc a PDF con LibreOffice headless."""
    subprocess.run([_SOFFICE, "--headless", "--convert-to", "pdf",
                    "--outdir", str(Path(salida).parent), str(ruta_docx)],
                   check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    generado = Path(salida).parent / (Path(ruta_docx).stem + ".pdf")
    if generado.exists() and generado != Path(salida):
        generado.replace(salida)


def normalizar_a_pdf(ruta_src, ruta_pdf_salida):
    """Convierte un folio de CUALQUIER formato a PDF canónico. Devuelve True si OK."""
    ruta_src = Path(ruta_src)
    salida = Path(ruta_pdf_salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    ext = ruta_src.suffix.lower()
    try:
        if ext == ".pdf":
            shutil.copyfile(ruta_src, salida)
        elif ext in (".md", ".txt"):
            _texto_a_pdf(ruta_src.read_text(encoding="utf-8", errors="ignore"), salida)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif"):
            _imagen_a_pdf(ruta_src, salida)
        elif ext in (".docx", ".doc"):
            _docx_a_pdf(ruta_src, salida)
        else:
            _texto_a_pdf(ruta_src.read_text(encoding="utf-8", errors="ignore"), salida)
        return salida.exists()
    except Exception as e:
        print(f"[normalizar_a_pdf] error con {ruta_src.name}: {e}")
        return False


def localizar_en_pdf(ruta_pdf, fragmento):
    """Localiza un fragmento dentro del PDF canónico.
    Devuelve (n_pagina, [bbox...]) de la primera coincidencia (coordenadas reales del PDF)."""
    import fitz
    lineas = [l.strip() for l in (fragmento or "").split("\n") if len(l.strip()) > 12]
    aguja = (lineas[0] if lineas else (fragmento or "")[:60])[:80]
    if not aguja:
        return 0, []
    doc = fitz.open(str(ruta_pdf))
    for i in range(doc.page_count):
        rects = doc[i].search_for(aguja)
        if rects:
            return i, [tuple(r) for r in rects]
    return 0, []
