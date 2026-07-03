# -*- coding: utf-8 -*-
"""
Comparativa REAL de bases de datos vectoriales locales (Tabla 12 del TFM).
Qdrant vs ChromaDB vs FAISS -- las 3 instaladas y ejecutadas de verdad,
mismo modelo de embeddings (all-MiniLM-L6-v2) y mismos datos/consultas.
Usa una ruta Qdrant temporal (no toca la BD de produccion, que esta en uso).
"""
import time
import shutil
import json
from pathlib import Path

import fitz
import numpy as np
from sentence_transformers import SentenceTransformer

CORPUS = Path("datos/expedientes/25988000R")
N_DOCS = 150  # muestra real representativa (LAB+CONS+ALTA)
QDRANT_TMP = Path("datos/_qdrant_bench_tmp")

# Mismas 12 consultas de la linea base (benchmark_baseline.py) para medir acierto@3
CONSULTAS = [
    ("Hemoglobina", "Hemoglobina"), ("Colesterol", "Colesterol"),
    ("Creatinina", "Creatinina"), ("Ferritina", "Ferritina"),
    ("Hemoglobina", "anemia"), ("Glucosa", "diabetes"),
    ("Colesterol", "dislipemia"), ("TSH", "función tiroidea"),
]


def cargar_corpus():
    # Muestra representativa real: analiticas (donde viven los terminos de las consultas)
    # + otros tipos de folio, para que el indice no sea artificialmente homogeneo
    lab = sorted(CORPUS.glob("LAB_*.pdf"))
    otros = sorted(list(CORPUS.glob("ALTA_*.pdf")) + list(CORPUS.glob("CONS_*.pdf")))[:30]
    archivos = (lab + otros)[:N_DOCS]
    docs = []
    for f in archivos:
        d = fitz.open(f)
        texto = "".join(p.get_text() for p in d)
        if texto.strip():
            docs.append({"id": f.stem, "nombre": f.name, "texto": texto})
    return docs


def ground_truth(termino, docs):
    return {d["nombre"] for d in docs if termino.lower() in d["texto"].lower()}


def acierto_en(nombres_top, gt):
    return any(n in gt for n in nombres_top)


def con_qdrant(docs, vectores, modelo):
    import qdrant_client
    from qdrant_client.http import models
    if QDRANT_TMP.exists():
        shutil.rmtree(QDRANT_TMP)
    cli = qdrant_client.QdrantClient(path=str(QDRANT_TMP))
    cli.create_collection("bench", vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
    t0 = time.time()
    cli.upsert("bench", points=[models.PointStruct(id=i, vector=v.tolist(), payload={"nombre": docs[i]["nombre"]})
                                for i, v in enumerate(vectores)])
    t_index = time.time() - t0

    t0 = time.time()
    aciertos = 0
    for termino, q in CONSULTAS:
        qv = modelo.encode(q).tolist()
        res = cli.query_points("bench", query=qv, limit=3).points
        nombres = [r.payload["nombre"] for r in res]
        if acierto_en(nombres, ground_truth(termino, docs)): aciertos += 1
    t_query = time.time() - t0
    cli.close()
    shutil.rmtree(QDRANT_TMP, ignore_errors=True)
    return {"t_index": round(t_index, 3), "t_query": round(t_query, 3), "acierto3": round(100*aciertos/len(CONSULTAS), 1)}


def con_chromadb(docs, vectores, modelo):
    import chromadb
    cli = chromadb.Client()
    try: cli.delete_collection("bench")
    except Exception: pass
    col = cli.create_collection("bench")
    t0 = time.time()
    col.add(ids=[str(i) for i in range(len(docs))], embeddings=[v.tolist() for v in vectores],
            metadatas=[{"nombre": d["nombre"]} for d in docs])
    t_index = time.time() - t0

    t0 = time.time()
    aciertos = 0
    for termino, q in CONSULTAS:
        qv = modelo.encode(q).tolist()
        res = col.query(query_embeddings=[qv], n_results=3)
        nombres = [m["nombre"] for m in res["metadatas"][0]]
        if acierto_en(nombres, ground_truth(termino, docs)): aciertos += 1
    t_query = time.time() - t0
    return {"t_index": round(t_index, 3), "t_query": round(t_query, 3), "acierto3": round(100*aciertos/len(CONSULTAS), 1)}


def con_faiss(docs, vectores, modelo):
    import faiss
    vecs = np.array([v for v in vectores]).astype("float32")
    faiss.normalize_L2(vecs)
    t0 = time.time()
    index = faiss.IndexFlatIP(384)
    index.add(vecs)
    t_index = time.time() - t0

    t0 = time.time()
    aciertos = 0
    for termino, q in CONSULTAS:
        qv = modelo.encode(q).astype("float32").reshape(1, -1)
        faiss.normalize_L2(qv)
        _, idxs = index.search(qv, 3)
        nombres = [docs[i]["nombre"] for i in idxs[0] if i >= 0]
        if acierto_en(nombres, ground_truth(termino, docs)): aciertos += 1
    t_query = time.time() - t0
    return {"t_index": round(t_index, 3), "t_query": round(t_query, 3), "acierto3": round(100*aciertos/len(CONSULTAS), 1)}


def con_milvus(docs, vectores, modelo):
    from pymilvus import MilvusClient
    import uuid
    db_path = Path(f"datos/_milvus_bench_{uuid.uuid4().hex[:8]}.db")
    cli = MilvusClient(uri=str(db_path))
    if cli.has_collection("bench"): cli.drop_collection("bench")
    cli.create_collection(collection_name="bench", dimension=384, metric_type="COSINE")

    t0 = time.time()
    data = [{"id": i, "vector": v.tolist(), "nombre": docs[i]["nombre"]} for i, v in enumerate(vectores)]
    cli.insert(collection_name="bench", data=data)
    t_index = time.time() - t0

    t0 = time.time()
    aciertos = 0
    for termino, q in CONSULTAS:
        qv = modelo.encode(q).tolist()
        res = cli.search(collection_name="bench", data=[qv], limit=3, output_fields=["nombre"])
        nombres = [r["entity"]["nombre"] for r in res[0]]
        if acierto_en(nombres, ground_truth(termino, docs)): aciertos += 1
    t_query = time.time() - t0
    resultado = {"t_index": round(t_index, 3), "t_query": round(t_query, 3), "acierto3": round(100*aciertos/len(CONSULTAS), 1)}
    try:
        cli.close()
        db_path.unlink(missing_ok=True)
    except Exception:
        pass
    return resultado


def main():
    print("=== Comparativa REAL: Qdrant vs ChromaDB vs FAISS ===\n")
    print("Cargando corpus real (PyMuPDF, misma extraccion validada antes)...")
    docs = cargar_corpus()
    print(f"  {len(docs)} documentos cargados\n")

    print("Generando embeddings (all-MiniLM-L6-v2, una sola vez, mismo modelo para las 3)...")
    modelo = SentenceTransformer("all-MiniLM-L6-v2")
    t0 = time.time()
    vectores = modelo.encode([d["texto"][:2000] for d in docs], show_progress_bar=False)
    print(f"  {len(vectores)} embeddings generados en {time.time()-t0:.2f}s\n")

    resultados = {}
    for nombre, fn in (("Qdrant", con_qdrant), ("ChromaDB", con_chromadb), ("FAISS", con_faiss), ("Milvus", con_milvus)):
        print(f"[{nombre}] indexando y consultando...")
        r = fn(docs, vectores, modelo)
        resultados[nombre] = r
        print(f"  indexacion: {r['t_index']}s | consultas (8): {r['t_query']}s | acierto@3: {r['acierto3']}%\n")

    print("=== RESUMEN ===")
    for k, v in resultados.items():
        print(f"  {k:10} | indexar {len(docs)} docs: {v['t_index']}s | 8 consultas: {v['t_query']}s | acierto@3: {v['acierto3']}%")

    Path("benchmark_vectordb_real_resultado.json").write_text(
        json.dumps({"n_docs": len(docs), "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado: benchmark_vectordb_real_resultado.json")


if __name__ == "__main__":
    main()
