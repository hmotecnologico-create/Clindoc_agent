# -*- coding: utf-8 -*-
"""
Prueba de hipotesis: el empate keyword/semantica en benchmark_baseline.py
se debe al modelo de embeddings generico (all-MiniLM-L6-v2)?
Repite la misma linea base con un modelo multilingue mas potente
(paraphrase-multilingual-mpnet-base-v2), mismo corpus, mismas 12 consultas,
mismo ground truth AMPLIADO (biomarcador de laboratorio UNION nombre de
diagnostico) auditado en la sesion anterior. No modifica la coleccion Qdrant
de produccion: indexa en una coleccion temporal.
"""
import re
import time
import shutil
import hashlib
from pathlib import Path

import pypdf
from docx import Document as DocxDocument

NIF = "25988000R"
FOLDER = Path("datos/expedientes") / NIF
TOPK = 3
MODELO = "paraphrase-multilingual-mpnet-base-v2"
QDRANT_TMP = Path("datos/_qdrant_bench_multilingue_tmp")

# (termino_lab, consulta, tipo, termino_diagnostico_o_None) -- ground truth ampliado auditado
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


def _semantic_chunking(texto):
    parrafos = texto.split("\n\n")
    fragmentos, chunk_actual = [], ""
    for parrafo in parrafos:
        if len(chunk_actual) + len(parrafo) < 1000:
            chunk_actual += parrafo + "\n\n"
        else:
            if chunk_actual:
                fragmentos.append(chunk_actual.strip())
            chunk_actual = parrafo + "\n\n"
    if chunk_actual:
        fragmentos.append(chunk_actual.strip())
    return fragmentos if fragmentos else [texto]


def main():
    folios = [f for f in FOLDER.glob("*") if f.suffix.lower() in (".pdf", ".docx", ".md", ".txt")]
    print(f"Cargando y extrayendo texto real de {len(folios)} folios de {NIF}...")
    cache = {f.name: _texto_de(f) for f in folios}
    cache_lower = {k: v.lower() for k, v in cache.items()}

    def ground_truth(termino_lab, termino_dx):
        rel = set()
        for nombre, txt in cache_lower.items():
            if termino_lab.lower() in txt:
                rel.add(nombre)
            if termino_dx and termino_dx.lower() in txt:
                rel.add(nombre)
        return rel

    def buscar_keyword(consulta, k=TOPK):
        terminos = [t.lower() for t in re.findall(r"\w+", consulta) if len(t) > 3]
        res = []
        for nombre, txt in cache_lower.items():
            score = sum(txt.count(t) for t in terminos)
            if score > 0:
                res.append((score, nombre))
        res.sort(reverse=True)
        return [n for _, n in res[:k]]

    print(f"Cargando modelo multilingue: {MODELO} (puede descargar ~1GB la primera vez)...")
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    modelo = SentenceTransformer(MODELO)
    dim = modelo.get_sentence_embedding_dimension()
    print(f"  modelo cargado en {time.time()-t0:.1f}s | dimension={dim}")

    import qdrant_client
    from qdrant_client.http import models as qm
    if QDRANT_TMP.exists():
        shutil.rmtree(QDRANT_TMP)
    cli = qdrant_client.QdrantClient(path=str(QDRANT_TMP))
    cli.create_collection("bench_ml", vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE))

    print(f"Indexando {len(folios)} folios (chunking real, mismo criterio de produccion)...")
    t0 = time.time()
    points = []
    pid = 0
    for f in folios:
        texto = cache[f.name]
        if not texto.strip():
            continue
        for i, frag in enumerate(_semantic_chunking(texto)):
            vec = modelo.encode(frag).tolist()
            points.append(qm.PointStruct(id=pid, vector=vec, payload={"nombre_archivo": f.name, "texto": frag}))
            pid += 1
    cli.upsert("bench_ml", points=points)
    print(f"  {len(points)} chunks indexados en {time.time()-t0:.1f}s")

    def buscar_semantica(consulta, k=TOPK):
        qv = modelo.encode(consulta).tolist()
        res = cli.query_points("bench_ml", query=qv, limit=k).points
        return [r.payload["nombre_archivo"] for r in res]

    agg = {"keyword": {"exacta": [], "conceptual": []}, "semantica": {"exacta": [], "conceptual": []}}
    print(f"\n=== LÍNEA BASE (modelo {MODELO}) top-{TOPK}, ground truth ampliado, paciente {NIF} ===\n")
    for termino, consulta, tipo, dx in CONSULTAS:
        gt = ground_truth(termino, dx)
        kw = buscar_keyword(consulta)
        sm = buscar_semantica(consulta)
        hit_kw = any(x in gt for x in kw)
        hit_sm = any(x in gt for x in sm)
        agg["keyword"][tipo].append(hit_kw)
        agg["semantica"][tipo].append(hit_sm)
        print(f"[{tipo:10}] '{consulta:42}' | GT={len(gt):3} | KW {'OK ' if hit_kw else 'NO '} {kw[:2]} | SEM {'OK ' if hit_sm else 'NO '} {sm[:2]}")

    def pct(lst):
        return round(100 * sum(lst) / len(lst), 1) if lst else 0.0

    print(f"\n==== ACIERTO@{TOPK} (modelo {MODELO}) ====")
    print(f"{'Metodo':12}| {'Exactas':>9} | {'Conceptuales':>13} | {'Global':>8}")
    print("-" * 50)
    for m in ("keyword", "semantica"):
        ex, co = pct(agg[m]["exacta"]), pct(agg[m]["conceptual"])
        gl = pct(agg[m]["exacta"] + agg[m]["conceptual"])
        print(f"{m:12}| {ex:>8}% | {co:>12}% | {gl:>7}%")

    cli.close()
    shutil.rmtree(QDRANT_TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
