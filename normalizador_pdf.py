# -*- coding: utf-8 -*-
"""
Normalización de folios HETEROGÉNEOS a PDF canónico + localización por coordenadas.

La ingesta recibe documentos en cualquier formato (.md, .txt, .docx, imágenes, .pdf)
y los convierte a un PDF canónico. Sobre ese PDF se extraen las coordenadas (bounding box)
de cada fragmento, lo que habilita el Deep Linking forense (recuadro sobre la línea exacta).
"""
import re
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


def _candidatos_aguja(fragmento):
    """Candidatos de búsqueda del fragmento, de más a menos distintivo: números (N.H.C.,
    episodio, valores) y líneas con contenido. La unicidad se decide luego contra el PDF."""
    txt = fragmento or ""
    cands = []
    for n in re.findall(r"\d{4,}", txt):
        if n not in cands:
            cands.append(n)
    for l in txt.split("\n"):
        l = l.strip()
        if len(l) > 18 and l[:45] not in cands:
            cands.append(l[:45])
    return cands or [txt[:40]]


def localizar_en_pdf(ruta_pdf, fragmento):
    """Localiza el fragmento en el PDF canónico eligiendo el candidato MÁS ÚNICO
    (el que aparece menos veces en el documento), para no caer en datos repetidos
    como el NIF o cabeceras. Devuelve (n_pagina, [bbox...]) con coordenadas reales."""
    import fitz
    doc = fitz.open(str(ruta_pdf))
    resultados = []  # (total_coincidencias, pagina, rects)
    for ag in _candidatos_aguja(fragmento):
        total, primera = 0, None
        for i in range(doc.page_count):
            rects = doc[i].search_for(ag)
            if rects:
                if primera is None:
                    primera = (i, [tuple(r) for r in rects])
                total += len(rects)
        if primera:
            resultados.append((total, primera[0], primera[1]))
            if total == 1:  # único → no hay nada más seguro
                break
    if resultados:
        resultados.sort(key=lambda x: x[0])  # el menos repetido = el más específico
        return resultados[0][1], resultados[0][2]
    return 0, []


def generar_pdfs_paciente(nif, ruta_expedientes="datos/expedientes", ruta_pdf="datos/expedientes_pdf", forzar=False):
    """Convierte TODOS los folios de un paciente a PDF canónico (idempotente).
    Devuelve (ok, total). Pensado para llamarse en la ingesta y como batch del demo."""
    src_dir = Path(ruta_expedientes) / nif
    out_dir = Path(ruta_pdf) / nif
    if not src_dir.exists():
        return 0, 0
    ok = total = 0
    for f in sorted(src_dir.glob("*")):
        if f.suffix.lower() not in (".md", ".txt", ".pdf", ".docx", ".doc",
                                    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif"):
            continue
        total += 1
        destino = out_dir / (f.stem + ".pdf")
        if destino.exists() and not forzar:
            ok += 1
            continue
        if normalizar_a_pdf(f, destino):
            ok += 1
    return ok, total
