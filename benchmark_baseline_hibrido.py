# -*- coding: utf-8 -*-
"""
Evalúa un TERCER método sobre la misma línea base (benchmark_baseline.py): fusión
híbrida keyword+semántica por Reciprocal Rank Fusion (RRF), técnica estándar de
recuperación de información (Cormack et al., 2009). Motivación real medida esta
sesión: contra la colección de producción (Docling + paraphrase-multilingual-
mpnet-base-v2), keyword gana en consultas EXACTAS (50,0% vs 16,7%) y semántica
gana en CONCEPTUALES (50,0% vs 33,3%) — ninguna domina a la otra. RRF combina el
ranking completo (no solo el top-3) de ambos métodos para ver si la unión supera
a cada uno por separado.

NO modifica la app en producción (chat_asistente_medico / IndiceCorpus siguen
usando su método actual); esto es una evaluación para decidir si vale la pena
incorporar fusión híbrida como mejora futura.
"""
import re
import json
import hashlib
from pathlib import Path

import pypdf
from docx import Document as DocxDocument

NIF = "25988000R"
FOLDER = Path("datos/expedientes") / NIF
TOPK = 3
POOL = 20  # candidatos considerados de cada método para la fusion (no solo el top-3)

CONSULTAS = [
    ("Hemoglobina", "Hemoglobina", "exacta", None),
    ("Colesterol", "Colesterol", "exacta", None),
    ("artroscopia", "artroscopia de rodilla", "exacta", None),
    ("epidural", "infiltración epidural", "exacta", None),
    ("Creatinina", "Creatinina", "exacta", None),
    ("Ferritina", "Ferritina", "exacta", None),
    ("Hemoglobina", "anemia", "conceptual", "anemia"),
    ("Glucosa", "diabetes", "conceptual", "diabetes"),
    ("Colesterol", "dislipemia", "conceptual", "dislipemia"),
    ("TSH", "función tiroidea", "conceptual", "tiroide"),
    ("Leucocitos", "infección con glóbulos blancos elevados", "conceptual", "leucocit"),
    ("Ferritina", "déficit de hierro", "conceptual", "hierro"),
]


def _texto_de(f):
    ext = f.suffix.lower()
    try:
        if ext == ".pdf":
            with open(f, "rb") as fh:
                reader = pypdf.PdfReader(fh)
                return "".join(p.extract_text() or "" for p in reader.pages)
        if ext == ".docx":
            return "\n".join(p.text for p in DocxDocument(f).paragraphs)
        return f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def main():
    folios = [f for f in FOLDER.glob("*") if f.suffix.lower() in (".pdf", ".docx", ".md", ".txt")]
    cache = {f.name: _texto_de(f).lower() for f in folios}

    def ground_truth(termino_lab, termino_dx):
        rel = set()
        for nombre, txt in cache.items():
            if termino_lab.lower() in txt:
                rel.add(nombre)
            if termino_dx and termino_dx.lower() in txt:
                rel.add(nombre)
        return rel

    def ranking_keyword(consulta, k=POOL):
        terminos = [t.lower() for t in re.findall(r"\w+", consulta) if len(t) > 3]
        res = []
        for nombre, txt in cache.items():
            score = sum(txt.count(t) for t in terminos)
            if score > 0:
                res.append((score, nombre))
        res.sort(reverse=True)
        return [n for _, n in res[:k]]

    from run_clindoc import IndiceCorpus
    idx = IndiceCorpus(ruta_db="datos/qdrant_db")
    idx.nombre_coleccion = "expediente_" + hashlib.sha256(NIF.encode()).hexdigest()

    def ranking_semantica(consulta, k=POOL):
        return [e["archivo"] for e in idx.buscar_evidencias(consulta, n=k)]

    def rrf(rank_kw, rank_sem, k_rrf=60, top=TOPK):
        """Reciprocal Rank Fusion: score(d) = sum(1/(k_rrf + rango)) por lista donde aparece."""
        scores = {}
        for i, doc in enumerate(rank_kw):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k_rrf + i + 1)
        for i, doc in enumerate(rank_sem):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k_rrf + i + 1)
        return [d for d, _ in sorted(scores.items(), key=lambda x: -x[1])[:top]]

    agg = {"keyword": {"exacta": [], "conceptual": []},
           "semantica": {"exacta": [], "conceptual": []},
           "hibrida": {"exacta": [], "conceptual": []}}

    print(f"=== LÍNEA BASE + FUSIÓN HÍBRIDA (RRF), paciente {NIF} ===\n")
    for termino, consulta, tipo, dx in CONSULTAS:
        gt = ground_truth(termino, dx)
        rk_kw = ranking_keyword(consulta)
        rk_sem = ranking_semantica(consulta)
        rk_hib = rrf(rk_kw, rk_sem)

        hit_kw = any(x in gt for x in rk_kw[:TOPK])
        hit_sem = any(x in gt for x in rk_sem[:TOPK])
        hit_hib = any(x in gt for x in rk_hib)

        agg["keyword"][tipo].append(hit_kw)
        agg["semantica"][tipo].append(hit_sem)
        agg["hibrida"][tipo].append(hit_hib)

        print(f"[{tipo:10}] '{consulta:42}' | KW {'OK' if hit_kw else 'NO'} | SEM {'OK' if hit_sem else 'NO'} | HIB {'OK' if hit_hib else 'NO'}  top-hib={rk_hib}")

    def pct(lst):
        return round(100 * sum(lst) / len(lst), 1) if lst else 0.0

    print(f"\n==== ACIERTO@{TOPK} ====")
    print(f"{'Metodo':12}| {'Exactas':>9} | {'Conceptuales':>13} | {'Global':>8}")
    print("-" * 50)
    resumen = {}
    for m in ("keyword", "semantica", "hibrida"):
        ex, co = pct(agg[m]["exacta"]), pct(agg[m]["conceptual"])
        gl = pct(agg[m]["exacta"] + agg[m]["conceptual"])
        resumen[m] = {"exacta": ex, "conceptual": co, "global": gl}
        print(f"{m:12}| {ex:>8}% | {co:>12}% | {gl:>7}%")

    Path("benchmark_baseline_hibrido_resultado.json").write_text(
        json.dumps({"nif": NIF, "resumen": resumen}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado: benchmark_baseline_hibrido_resultado.json")


if __name__ == "__main__":
    main()
