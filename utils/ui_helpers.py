import streamlit as st
import json
import re
import os
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF

def _chunking_folio(texto):
    """Réplica del chunking del pipeline (run_clindoc._semantic_chunking) para localizar
    el fragmento citado dentro del folio."""
    parrafos = (texto or "").split('\n\n')
    frags, cur = [], ""
    for p in parrafos:
        if len(cur) + len(p) < 1000:
            cur += p + "\n\n"
        else:
            if cur:
                frags.append(cur.strip())
            cur = p + "\n\n"
    if cur:
        frags.append(cur.strip())
    return frags if frags else [texto or ""]


@st.cache_data(show_spinner=False)
def render_folio_resaltado(ruta_str, chunk_idx, pdf_str=None):
    """DEEP LINKING FORENSE: abre el PDF canónico del folio, va a la PÁGINA del fragmento
    citado y dibuja un recuadro visual sobre la LÍNEA exacta, localizada por sus coordenadas.
    Devuelve (PNG, encontrado, n_pagina, total_paginas). Si no hay PDF canónico, renderiza el fragmento."""
    texto = Path(ruta_str).read_text(encoding="utf-8", errors="ignore")
    frags = _chunking_folio(texto)
    idx = chunk_idx if 0 <= chunk_idx < len(frags) else (len(frags) - 1 if frags else 0)
    fragmento = (frags[idx] if frags else texto).strip()

    pdf = Path(pdf_str) if pdf_str else None
    if pdf and pdf.exists():
        from normalizador_pdf import localizar_en_pdf
        pagina, rects = localizar_en_pdf(str(pdf), fragmento)
        d = fitz.open(str(pdf))
        pg = d[pagina]
        for r in rects:
            rr = fitz.Rect(r)
            linea = fitz.Rect(pg.rect.x0 + 26, rr.y0 - 1.5, pg.rect.x1 - 26, rr.y1 + 1.5)
            pg.draw_rect(linea, color=(0.85, 0, 0), width=1.6)
            pg.add_highlight_annot(linea)
        return pg.get_pixmap(dpi=120).tobytes("png"), bool(rects), pagina + 1, d.page_count

    # Fallback (sin PDF canónico): render del fragmento citado en su propia página
    n_lineas = fragmento.count('\n') + max(2, int(len(fragmento) / 95)) + 4
    alto = float(min(70 + n_lineas * 13.5, 1500))
    doc = fitz.open()
    page = doc.new_page(width=595, height=alto)
    page.insert_textbox(fitz.Rect(38, 30, 558, alto - 20), fragmento, fontsize=10, fontname="helv")
    pg = fitz.open(stream=doc.tobytes(), filetype="pdf")[0]
    encontrado = False
    for aguja in [l.strip() for l in fragmento.split('\n') if len(l.strip()) > 12][:2]:
        for r in pg.search_for(aguja[:80]):
            pg.draw_rect(r, color=(0.85, 0, 0), width=1.6)
            pg.add_highlight_annot(r)
            encontrado = True
    return pg.get_pixmap(dpi=135).tobytes("png"), encontrado, 1, 1


@st.cache_data(show_spinner=False)
def _campos_guion(ruta="guiones/baja_laboral.yaml"):
    """Carga los campos por sección del guion YAML (contrato semántico): {titulo: [campos]}."""
    import yaml
    try:
        y = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        return {s["titulo"]: s.get("campos", []) for s in y.get("secciones", [])}
    except Exception:
        return {}


def _validar_campo(campo, texto):
    """Valida un campo del guion contra el texto de la sección. Devuelve (estado, detalle).
    Estados: ok / aviso / falta / manual."""
    nombre = campo.get("nombre", "")
    patron = campo.get("patron")
    requerido = campo.get("requerido", False)
    falta = "falta" if requerido else "aviso"
    if patron:  # p.ej. CIE-10
        p = patron[1:] if patron.startswith("^") else patron
        p = p[:-1] if p.endswith("$") else p
        m = re.search(p, texto)
        return ("ok", f"patrón cumplido → {m.group(0)}") if m else (falta, "patrón no encontrado")
    if campo.get("tipo") == "fecha" or nombre.startswith("fecha"):
        return ("ok", "fecha presente") if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", texto) else (falta, "sin fecha")
    claves = {
        "num_seguridad_social": [r"seguridad social", r"\bnuss\b", r"n\.?u\.?s\.?s"],
        "empresa": [r"empresa"],
        "nif": [r"\b\d{8}[A-Za-z]\b"],
        "nombre_completo": [r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", r"paciente"],
        "diagnostico_principal": [r"diagn[oó]stic"],
    }
    kws = claves.get(nombre)
    if kws:
        for k in kws:
            if re.search(k, texto, re.IGNORECASE):
                return "ok", "presente"
        return falta, "no detectado"
    return "manual", "verificación del facultativo"


def _periodo_historia(texto):
    """Calcula el período (desde–hasta) a partir de las fechas que aparecen en la historia."""
    fechas = []
    for d_, m_, y_ in re.findall(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', texto or ""):
        try:
            fechas.append(datetime(int(y_), int(m_), int(d_)))
        except Exception:
            pass
    fechas = [f for f in fechas if 1990 <= f.year <= datetime.now().year]
    if not fechas:
        return "no determinado en los documentos"
    return f"{min(fechas):%d/%m/%Y} — {max(fechas):%d/%m/%Y}"


def generar_pdf_historia(nombre, nif, texto, medico):
    """Genera, en memoria, el PDF profesional de la Historia Clínica Consolidada validada por el facultativo."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable)

    def fmt(s):
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        
        # Convertir [Fuente: archivo#chunk] en hipervínculos clickeables en el PDF
        base_path = Path(f"datos/expedientes/{nif}").resolve().as_posix()
        def replacer(match):
            archivo = match.group(1)
            # ReportLab permite <link href="...">...</link>
            # Subrayado y color azul para que parezca un enlace real
            return f'<font color="blue"><u><link href="file:///{base_path}/{archivo}">[Fuente: {archivo}]</link></u></font>'
        
        s = re.sub(r'\[Fuente:\s*([^\]#]+?)(?:#[^\]]+)?\]', replacer, s)
        return s

    AZUL = colors.HexColor("#1e3a8a")
    GRIS = colors.HexColor("#555555")
    ahora = datetime.now()
    periodo = _periodo_historia(texto)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Historia Clínica Consolidada - {nombre}", author=medico or "ClinDoc Agent")
    ss = getSampleStyleSheet()
    s_title = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=16, textColor=AZUL, spaceAfter=1, alignment=TA_CENTER)
    s_sub = ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8.5, textColor=GRIS, alignment=TA_CENTER, spaceAfter=8)
    s_h = ParagraphStyle("h", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, textColor=AZUL, spaceBefore=9, spaceAfter=3)
    s_body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=3)
    s_cell = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    s_foot = ParagraphStyle("f", parent=ss["Normal"], fontName="Helvetica", fontSize=9, textColor=GRIS, leading=13)

    el = [Paragraph("HISTORIA CLÍNICA CONSOLIDADA", s_title),
          Paragraph("Síntesis documental generada por IA local · validada por facultativo · ClinDoc Agent", s_sub),
          HRFlowable(width="100%", thickness=1.2, color=AZUL, spaceAfter=8)]
    cab = Table([[Paragraph(f"<b>Paciente:</b> {nombre}", s_cell), Paragraph(f"<b>NIF:</b> {nif}", s_cell)],
                 [Paragraph(f"<b>Período de la historia:</b> {periodo}", s_cell),
                  Paragraph(f"<b>Tipo:</b> síntesis documental trazable", s_cell)]],
                colWidths=[9.6 * cm, 7.0 * cm])
    cab.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                             ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e6e6e6")),
                             ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7fc")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el += [cab, Spacer(1, 10)]

    for raw in (texto or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            el.append(Spacer(1, 4))
        elif line.lstrip().startswith("## ") or line.lstrip().startswith("### "):
            el.append(Paragraph(fmt(line.lstrip("# ").strip()), s_h))
        else:
            el.append(Paragraph(fmt(line), s_body))

    el += [Spacer(1, 14),
           HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#cccccc"), spaceAfter=6),
           Paragraph(f"<b>Período cubierto por la historia:</b> {periodo}", s_foot),
           Paragraph(f"<b>Historia realizada el:</b> {ahora:%d/%m/%Y} a las {ahora:%H:%M} h", s_foot),
           Spacer(1, 20),
           Paragraph(f"<b>Facultativo responsable:</b> {medico or '________________________'}", s_foot),
           Spacer(1, 6),
           Paragraph("Firma: ______________________________&nbsp;&nbsp;&nbsp;&nbsp;"
                     f"Fecha y hora: {ahora:%d/%m/%Y %H:%M} h", s_foot)]
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()


def registrar_validacion_facultativo(nif, medico, editado, historia=None):
    """Constancia de auditoría (Human-in-the-Loop): registra la validación y guarda la HUELLA de la historia validada."""
    log_path = "datos/validaciones_facultativo.json"
    registros = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                registros = json.load(f)
        except Exception:
            registros = []
    ts = datetime.now()
    registros.append({
        "nif": nif,
        "facultativo": medico or "(sin nombre)",
        "accion": "editado y validado" if editado else "validado (visto bueno)",
        "timestamp": ts.isoformat()
    })
    os.makedirs("datos", exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(registros, f, indent=2, ensure_ascii=False)
    # Huella: la historia validada se guarda CIFRADA (AES-256-GCM) en reposo (RNF-01 / RGPD)
    if historia is not None:
        os.makedirs("datos/historias_validadas", exist_ok=True)
        contenido = (f"# HISTORIA CLÍNICA VALIDADA\n# Facultativo responsable: {medico or '(sin nombre)'}\n"
                     f"# Fecha/hora: {ts:%d/%m/%Y %H:%M:%S}\n"
                     f"# Acción: {'EDITADA y validada' if editado else 'validada (visto bueno, sin cambios)'}\n\n{historia}")
        base = f"datos/historias_validadas/{nif}_{ts:%Y%m%d_%H%M%S}"
        try:
            from cifrado import CifradoClinDoc
            with open(base + ".enc", "w", encoding="utf-8") as f:
                f.write(CifradoClinDoc().cifrar(contenido))
        except Exception as e:
            # Si el cifrado fallara, NO dejar el dato clínico en claro
            with open(base + ".error.txt", "w", encoding="utf-8") as f:
                f.write(f"[huella no guardada: cifrado no disponible: {e}]")

