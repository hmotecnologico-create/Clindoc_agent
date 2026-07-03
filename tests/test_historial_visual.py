# -*- coding: utf-8 -*-
"""Test: HistorialClinicoVisual debe cargar eventos desde el corpus real (PDF/DOCX),
no solo desde .md/.txt (formato legado). Falla hoy porque cargar_expediente() usa
read_text() sin distinguir formato -> UnicodeDecodeError silencioso en binarios."""
from historial_clinico_visual import HistorialClinicoVisual


def test_carga_eventos_desde_corpus_pdf_docx():
    h = HistorialClinicoVisual("datos/expedientes/25988000R")
    h.cargar_expediente("25988000R", "Test")
    assert len(h.eventos) > 0, (
        "cargar_expediente() no generó ningún evento sobre el corpus PDF/DOCX real "
        "(esperado >0, ya que hay 524 documentos con fechas parseables)"
    )


if __name__ == "__main__":
    test_carga_eventos_desde_corpus_pdf_docx()
    print("PASS")
