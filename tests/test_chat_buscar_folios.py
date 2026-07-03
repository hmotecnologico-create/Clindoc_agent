# -*- coding: utf-8 -*-
"""Test: _buscar_en_folios debe encontrar folios reales del corpus PDF/DOCX actual.
Falla hoy porque solo busca en .md/.txt (formato legado, 0 archivos en el corpus real)."""
from chat_asistente_medico import ChatAsistenteMedico


def test_busca_radiografia_en_corpus_real():
    c = ChatAsistenteMedico()
    c.iniciar_conversacion("test", "25988000R", "Carlos Valderrama")
    resultados = c._buscar_en_folios("¿hay una radiografía?")
    assert len(resultados) > 0, (
        "_buscar_en_folios() no encontro ningun folio pese a que existen 120 archivos RAD_*.docx "
        "en el corpus real (bug: solo busca en .md/.txt)"
    )


if __name__ == "__main__":
    test_busca_radiografia_en_corpus_real()
    print("PASS")
