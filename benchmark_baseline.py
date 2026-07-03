# -*- coding: utf-8 -*-
"""
LÍNEA BASE EXPERIMENTAL — Recuperación de evidencia: KEYWORD vs SEMÁNTICA (RAG).

Mide si cada método recupera, en su top-k, un folio RELEVANTE (ground truth = folios que
contienen el término clínico canónico). Demuestra la ventaja de la recuperación semántica
del enfoque ClinDoc frente a una búsqueda por palabra clave, especialmente en consultas
conceptuales (sinónimos), donde el keyword falla por no captar la equivalencia semántica.

Uso:  python benchmark_baseline.py
"""
import re
import json
import hashlib
from pathlib import Path

NIF = "25988000R"
FOLDER = Path("datos/expedientes") / NIF
TOPK = 3

# (término canónico para el ground truth, consulta lanzada, tipo, término diagnóstico adicional o None)
# El término diagnóstico se auditó folio a folio (ver sesión de verificación): algunos informes de
# alta (ALTA_*) mencionan el diagnóstico por su nombre, no solo el biomarcador de laboratorio: un
# ground truth que solo mira el biomarcador subestima folios genuinamente relevantes.
CONSULTAS = [
    # exactas: la palabra aparece literal en los folios
    ("Hemoglobina", "Hemoglobina", "exacta", None),
    ("Colesterol", "Colesterol", "exacta", None),
    ("artroscopia", "artroscopia de rodilla", "exacta", None),
    ("epidural", "infiltración epidural", "exacta", None),
    ("Creatinina", "Creatinina", "exacta", None),
    ("Ferritina", "Ferritina", "exacta", None),
    # conceptuales: sinónimo/diagnóstico que NO aparece literal en el biomarcador (el folio de
    # laboratorio usa el término técnico; el término diagnóstico, cuando existe en el corpus,
    # amplía el ground truth con los informes de alta que lo mencionan explícitamente)
    ("Hemoglobina", "anemia", "conceptual", "anemia"),
    ("Glucosa", "diabetes", "conceptual", "diabetes"),
    ("Colesterol", "dislipemia", "conceptual", "dislipemia"),
    ("TSH", "función tiroidea", "conceptual", "tiroide"),
    ("Leucocitos", "infección con glóbulos blancos elevados", "conceptual", "leucocit"),
    ("Ferritina", "déficit de hierro", "conceptual", "hierro"),
]


def _folios():
    return [f for f in FOLDER.glob("*") if f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")]


def _texto_de(f):
    """Extrae texto segun el formato real (mismo criterio que AgenteEscanner)."""
    ext = f.suffix.lower()
    try:
        if ext == ".pdf":
            import pypdf
            with open(f, "rb") as fh:
                reader = pypdf.PdfReader(fh)
                return "".join(p.extract_text() or "" for p in reader.pages)
        if ext == ".docx":
            from docx import Document as DocxDocument
            return "\n".join(p.text for p in DocxDocument(f).paragraphs)
        return f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def folios_con(termino, termino_dx=None):
    """Ground truth: folios que contienen el término de laboratorio y/o el nombre del
    diagnóstico (substring, insensible a mayúsculas). Auditado: algunos informes de alta
    mencionan el diagnóstico sin citar el biomarcador, así que la unión evita subestimar
    folios relevantes (ver benchmark_baseline_modelo_multilingue.py para el detalle)."""
    rel = set()
    for f in _folios():
        txt = _texto_de(f).lower()
        if termino.lower() in txt:
            rel.add(f.name)
        if termino_dx and termino_dx.lower() in txt:
            rel.add(f.name)
    return rel


def buscar_keyword(consulta, k=TOPK):
    """Baseline: recuperación por palabra clave (conteo de coincidencias de subcadena)."""
    terminos = [t.lower() for t in re.findall(r"\w+", consulta) if len(t) > 3]
    res = []
    for f in _folios():
        tl = _texto_de(f).lower()
        score = sum(tl.count(t) for t in terminos)
        if score > 0:
            res.append((score, f.name))
    res.sort(reverse=True)
    return [n for _, n in res[:k]]


def main():
    from run_clindoc import IndiceCorpus
    idx = IndiceCorpus(ruta_db="datos/qdrant_db")
    idx.nombre_coleccion = "expediente_" + hashlib.sha256(NIF.encode()).hexdigest()

    def buscar_semantica(consulta, k=TOPK):
        return [e["archivo"] for e in idx.buscar_evidencias(consulta, n=k)]

    filas = []
    agg = {"keyword": {"exacta": [], "conceptual": []},
           "semantica": {"exacta": [], "conceptual": []}}

    print(f"=== LÍNEA BASE: recuperación de evidencia (top-{TOPK}), paciente {NIF} ===\n")
    for termino, consulta, tipo, dx in CONSULTAS:
        gt = folios_con(termino, dx)
        kw = buscar_keyword(consulta)
        sm = buscar_semantica(consulta)
        hit_kw = any(x in gt for x in kw)
        hit_sm = any(x in gt for x in sm)
        agg["keyword"][tipo].append(hit_kw)
        agg["semantica"][tipo].append(hit_sm)
        filas.append({"consulta": consulta, "tipo": tipo, "ground_truth_folios": len(gt),
                      "keyword_top": kw, "keyword_acierto": hit_kw,
                      "semantica_top": sm, "semantica_acierto": hit_sm})
        print(f"[{tipo:10}] '{consulta:42}' | KW {'OK ' if hit_kw else 'NO '} {kw[:2]} | SEM {'OK ' if hit_sm else 'NO '} {sm[:2]}")

    def pct(lst):
        return round(100 * sum(lst) / len(lst), 1) if lst else 0.0

    print(f"\n==== ACIERTO@{TOPK} (% de consultas con un folio relevante en el top-{TOPK}) ====")
    print(f"{'Metodo':12}| {'Exactas':>9} | {'Conceptuales':>13} | {'Global':>8}")
    print("-" * 50)
    resumen = {}
    for m in ("keyword", "semantica"):
        ex, co = pct(agg[m]["exacta"]), pct(agg[m]["conceptual"])
        gl = pct(agg[m]["exacta"] + agg[m]["conceptual"])
        resumen[m] = {"exacta": ex, "conceptual": co, "global": gl}
        print(f"{m:12}| {ex:>8}% | {co:>12}% | {gl:>7}%")

    out = {"nif": NIF, "topk": TOPK, "n_consultas": len(CONSULTAS),
           "resumen_acierto": resumen, "detalle": filas}
    Path("benchmark_baseline_resultado.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado: benchmark_baseline_resultado.json")


if __name__ == "__main__":
    main()
