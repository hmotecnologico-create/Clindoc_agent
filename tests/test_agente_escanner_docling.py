# -*- coding: utf-8 -*-
"""Test: AgenteEscanner debe extraer texto REAL de un PDF via Docling.
Falla hoy porque _procesar_pdf() lee json_data.get("text", "") y esa clave
no existe en el esquema actual de Docling (texts/body/tables), devolviendo
siempre cadena vacia -> NIF/vigencia/RAG reciben texto vacio para el 77% del corpus."""
from agentes.agente_escanner import AgenteEscanner


def test_procesar_pdf_extrae_texto_no_vacio():
    ag = AgenteEscanner("datos/expedientes/25988000R")
    doc = ag._procesar_pdf(ag.ruta / "LAB_005.pdf")
    assert doc["texto"].strip() != "", "El texto extraido esta vacio (bug de clave 'text' en Docling)"
    assert "25988000R" in doc["texto"] or "NIF" in doc["texto"], "El texto extraido no contiene el contenido real del documento"


if __name__ == "__main__":
    test_procesar_pdf_extrae_texto_no_vacio()
    print("PASS")
