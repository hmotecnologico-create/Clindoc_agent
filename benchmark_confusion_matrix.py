# -*- coding: utf-8 -*-
"""
MATRIZ DE DETECCION DE ANOMALIAS Y TRAMPAS LOGICAS -- reconstruccion real (Tabla 21 TFM).

80 casos de prueba reales ejecutados contra las clases REALES del pipeline
(VerificadorIdentidad, VerificadorVigencia), exactamente como las invoca
run_clindoc.py (mismos argumentos posicionales, misma regla de vigencia).

- 20 trampas de identidad (NIF de otro paciente intercalado) + 20 controles (NIF correcto)
- 20 trampas de vigencia (documento > 180 dias) + 20 controles (documento reciente)

Nada simulado: se llama directamente a agentes/verificadores.py.
Uso: python benchmark_confusion_matrix.py
"""
import json
import random
from datetime import datetime, timedelta

from agentes.verificadores import VerificadorIdentidad, VerificadorVigencia

NIF_REF = "25988000R"
NOMBRE_REF = "Carlos Valderrama"

OTROS_PACIENTES = [
    ("52880483X", "Laura Gómez"),
    ("33445566G", "David Sánchez"),
    ("48991234F", "Miguel Ángel Torres"),
    ("75114422D", "Elena Martínez"),
]

random.seed(42)


def doc_texto(nif, nombre, fecha_dt, servicio="Medicina Interna", motivo="Revisión clínica"):
    fecha = fecha_dt.strftime("%d/%m/%Y")
    return (f"INFORME DE ALTA - {servicio.upper()}\n"
            f"Paciente: {nombre} | NIF: {nif} | Fecha: {fecha}\n"
            f"Motivo de consulta: {motivo}. Evolución favorable.\n")


def construir_casos_identidad():
    casos = []
    # 20 trampas: NIF de otro paciente intercalado en el expediente del paciente activo
    for i in range(20):
        nif_otro, nombre_otro = OTROS_PACIENTES[i % len(OTROS_PACIENTES)]
        fecha = datetime.now() - timedelta(days=random.randint(1, 400))
        texto = doc_texto(nif_otro, nombre_otro, fecha)
        casos.append({"id": f"ID_TRAMPA_{i+1:02d}", "tipo": "trampa", "texto": texto,
                      "nif_doc_esperado": nif_otro})
    # 20 controles: NIF correcto del paciente activo
    for i in range(20):
        fecha = datetime.now() - timedelta(days=random.randint(1, 400))
        texto = doc_texto(NIF_REF, NOMBRE_REF, fecha)
        casos.append({"id": f"ID_CONTROL_{i+1:02d}", "tipo": "control", "texto": texto,
                      "nif_doc_esperado": NIF_REF})
    return casos


def construir_casos_vigencia():
    casos = []
    # 20 trampas: documento fuera de la ventana regulatoria (> 180 dias)
    for i in range(20):
        dias = random.randint(200, 3000)  # de ~7 meses a ~8 años atras
        fecha = datetime.now() - timedelta(days=dias)
        texto = doc_texto(NIF_REF, NOMBRE_REF, fecha, motivo="Parte de baja laboral")
        casos.append({"id": f"VIG_TRAMPA_{i+1:02d}", "tipo": "trampa", "texto": texto,
                      "dias_antiguedad": dias})
    # 20 controles: documento reciente (dentro de 180 dias)
    for i in range(20):
        dias = random.randint(0, 175)
        fecha = datetime.now() - timedelta(days=dias)
        texto = doc_texto(NIF_REF, NOMBRE_REF, fecha, motivo="Parte de confirmación de baja")
        casos.append({"id": f"VIG_CONTROL_{i+1:02d}", "tipo": "control", "texto": texto,
                      "dias_antiguedad": dias})
    return casos


def metricas(tp, fn, tn, fp):
    sensibilidad = tp / (tp + fn) if (tp + fn) else 0.0
    especificidad = tn / (tn + fp) if (tn + fp) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (2 * precision * sensibilidad / (precision + sensibilidad)) if (precision + sensibilidad) else 0.0
    return {"sensibilidad": round(sensibilidad * 100, 1), "especificidad": round(especificidad * 100, 1),
            "f1": round(f1, 3), "tp": tp, "fn": fn, "tn": tn, "fp": fp}


def evaluar_identidad(casos):
    v = VerificadorIdentidad()
    tp = fn = tn = fp = 0
    detalle = []
    for c in casos:
        r = v.validar(NIF_REF, c["texto"])  # mismos 2 args posicionales que run_clindoc.py
        detectado_invalido = not r["valido"]
        if c["tipo"] == "trampa":
            if detectado_invalido: tp += 1
            else: fn += 1
        else:
            if detectado_invalido: fp += 1
            else: tn += 1
        detalle.append({**c, "resultado": r})
    return metricas(tp, fn, tn, fp), detalle


def evaluar_vigencia(casos):
    v = VerificadorVigencia()
    tp = fn = tn = fp = 0
    detalle = []
    for c in casos:
        r = v.validar(c["texto"], "reciente_6_meses")  # misma regla que run_clindoc.py
        detectado_invalido = not r["valido"]
        if c["tipo"] == "trampa":
            if detectado_invalido: tp += 1
            else: fn += 1
        else:
            if detectado_invalido: fp += 1
            else: tn += 1
        detalle.append({**c, "resultado": r})
    return metricas(tp, fn, tn, fp), detalle


def main():
    print("=== MATRIZ DE DETECCION -- reconstruccion real (80 casos) ===\n")

    casos_id = construir_casos_identidad()
    met_id, det_id = evaluar_identidad(casos_id)
    print(f"[IDENTIDAD] TP={met_id['tp']} FN={met_id['fn']} TN={met_id['tn']} FP={met_id['fp']}")
    print(f"  Sensibilidad: {met_id['sensibilidad']}% | Especificidad: {met_id['especificidad']}% | F1: {met_id['f1']}\n")

    casos_vig = construir_casos_vigencia()
    met_vig, det_vig = evaluar_vigencia(casos_vig)
    print(f"[VIGENCIA]  TP={met_vig['tp']} FN={met_vig['fn']} TN={met_vig['tn']} FP={met_vig['fp']}")
    print(f"  Sensibilidad: {met_vig['sensibilidad']}% | Especificidad: {met_vig['especificidad']}% | F1: {met_vig['f1']}\n")

    if met_id["fn"] > 0:
        print("  Trampas de identidad NO detectadas:")
        for d in det_id:
            if d["tipo"] == "trampa" and d["resultado"]["valido"]:
                print(f"    - {d['id']}: {d['resultado']['detalle']}")
    if met_vig["fn"] > 0:
        print("  Trampas de vigencia NO detectadas:")
        for d in det_vig:
            if d["tipo"] == "trampa" and d["resultado"]["valido"]:
                print(f"    - {d['id']}: {d['resultado']['detalle']}")

    out = {"nif_referencia": NIF_REF, "identidad": met_id, "vigencia": met_vig,
           "detalle_identidad": det_id, "detalle_vigencia": det_vig}
    with open("benchmark_confusion_matrix_resultado.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nGuardado: benchmark_confusion_matrix_resultado.json")


if __name__ == "__main__":
    main()
