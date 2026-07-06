# -*- coding: utf-8 -*-
"""
Regresión: _node_validate_vigency() debe registrar un evento "validacion_vigencia"
por documento. Bug real encontrado probando la app en vivo: el nodo validaba la
vigencia de cada documento (usado para poblar state["errores"]/state["trace"]) pero
nunca llamaba a self.recorder.record_event(...), a diferencia de _node_validate_identity
que si lo hace. Consecuencia real: la pestaña "Tramite de Incapacidad Temporal
(RD 1060/2022)" de app_clindoc.py siempre mostraba "No se encontraron eventos de
validacion de vigencia", aunque el pipeline si detectaba folios sin vigencia.
"""
from run_clindoc import OrquestadorLangGraph
from agentes.verificadores import VerificadorVigencia


class _FalsoOrquestador:
    verificador_vigencia = VerificadorVigencia()
    recorder = None


class _RecorderFalso:
    def __init__(self):
        self.eventos = []

    def record_event(self, tipo, detalles):
        self.eventos.append((tipo, detalles))


def test_node_validate_vigency_registra_un_evento_por_documento():
    falso = _FalsoOrquestador()
    falso.recorder = _RecorderFalso()

    state = {
        "trace": [],
        "errores": [],
        "documentos": [
            {"nombre": "doc_reciente.pdf", "texto": "Fecha: 01/06/2026 informe reciente"},
            {"nombre": "doc_viejo.pdf", "texto": "Fecha: 01/01/2015 informe antiguo"},
        ],
    }

    OrquestadorLangGraph._node_validate_vigency(falso, state)

    assert len(falso.recorder.eventos) == 2
    assert all(tipo == "validacion_vigencia" for tipo, _ in falso.recorder.eventos)
    nombres = {d["documento"] for _, d in falso.recorder.eventos}
    assert nombres == {"doc_reciente.pdf", "doc_viejo.pdf"}


if __name__ == "__main__":
    test_node_validate_vigency_registra_un_evento_por_documento()
    print("OK: _node_validate_vigency registra validacion_vigencia por documento")
