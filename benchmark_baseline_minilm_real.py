# -*- coding: utf-8 -*-
"""
NUEVO (2026-09-15): resuelve una ambigüedad real encontrada en auditoría "desde cero":
el historial del proyecto tiene 3 versiones DISTINTAS y mutuamente contradictorias del
resultado de acierto@3 con el modelo de embeddings antiguo (all-MiniLM-L6-v2), ninguna
verificable con confianza:
  (a) benchmark_baseline_resultado.json tal como quedó en el commit 2f82b66 (julio):
      semantica = 16,7% exacta / 50,0% conceptual / 33,3% global.
  (b) El propio docstring de IndiceCorpus (mismo commit): "empatada con keyword,
      41,7% ambas" -- una cifra global distinta (41,7%, no 33,3%) sin desglose.
  (c) Tabla 22 del TFM (ya publicada): 50,0% / 33,3% / 41,7% -- coincide con el
      GLOBAL de (b) pero no es trazable a ningun JSON existente.

En vez de adivinar cual de las 3 es la correcta, este script MIDE la respuesta HOY,
con datos 100% reales: reutiliza los fragmentos de texto YA EXTRAIDOS POR DOCLING en
la coleccion Qdrant de PRODUCCION (paciente 25988000R, modelo actual mpnet) -- sin
volver a correr OCR/ingesta, que tomaria ~20-45 min -- y los reindexa con
all-MiniLM-L6-v2 en una coleccion Qdrant TEMPORAL Y AISLADA (no toca produccion).
Corre exactamente la misma metodologia y las mismas 12 consultas de
benchmark_baseline.py (keyword recalculado igual, para servir de control interno:
si el keyword da tambien 50,0/33,3/41,7 aqui, confirma que el ground truth y el
corpus no cambiaron desde el ultimo benchmark_baseline.py).

Uso:  python benchmark_baseline_minilm_real.py
"""
import re
import json
import shutil
import hashlib
from pathlib import Path

import qdrant_client
from qdrant_client.http import models as qm
from sentence_transformers import SentenceTransformer

NIF = "25988000R"
FOLDER = Path("datos/expedientes") / NIF
TOPK = 3
TMP_DB = Path("datos/_qdrant_minilm_real_tmp")
TMP_COLLECTION = "expediente_minilm_real"

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


def _folios():
    return [f for f in FOLDER.glob("*") if f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")]


def _texto_de(f):
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
    rel = set()
    for f in _folios():
        txt = _texto_de(f).lower()
        if termino.lower() in txt:
            rel.add(f.name)
        if termino_dx and termino_dx.lower() in txt:
            rel.add(f.name)
    return rel


def buscar_keyword(consulta, k=TOPK):
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

    print("Paso 1/3: leyendo fragmentos REALES (ya extraidos por Docling) de la coleccion de produccion...")
    idx_prod = IndiceCorpus(ruta_db="datos/qdrant_db")
    idx_prod.nombre_coleccion = "expediente_" + hashlib.sha256(NIF.encode()).hexdigest()

    puntos = []
    offset = None
    while True:
        lote, offset = idx_prod.cliente.scroll(
            collection_name=idx_prod.nombre_coleccion, limit=256, offset=offset,
            with_payload=True, with_vectors=False,
        )
        puntos.extend(lote)
        if offset is None:
            break
    print(f"  {len(puntos)} chunks reales leidos de produccion (modelo actual: mpnet, sin re-OCR)")
    if not puntos:
        raise SystemExit("ERROR: coleccion de produccion vacia, no se puede reembeber sin datos reales")

    print("\nPaso 2/3: reembediendo esos MISMOS textos reales con all-MiniLM-L6-v2 en coleccion temporal aislada...")
    if TMP_DB.exists():
        shutil.rmtree(TMP_DB)
    cliente_tmp = qdrant_client.QdrantClient(path=str(TMP_DB))
    modelo_minilm = SentenceTransformer("all-MiniLM-L6-v2")
    dim = modelo_minilm.get_sentence_embedding_dimension()
    cliente_tmp.create_collection(
        collection_name=TMP_COLLECTION,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )
    lote_puntos = []
    for i, p in enumerate(puntos):
        texto = p.payload["texto"]
        vector = modelo_minilm.encode(texto).tolist()
        lote_puntos.append(qm.PointStruct(
            id=i, vector=vector,
            payload={"texto": texto, "nombre_archivo": p.payload["nombre_archivo"]},
        ))
        if len(lote_puntos) >= 128:
            cliente_tmp.upsert(collection_name=TMP_COLLECTION, points=lote_puntos)
            lote_puntos = []
    if lote_puntos:
        cliente_tmp.upsert(collection_name=TMP_COLLECTION, points=lote_puntos)
    print(f"  {len(puntos)} chunks reindexados con MiniLM (384d) en coleccion temporal")

    def buscar_semantica_minilm(consulta, k=TOPK):
        vector = modelo_minilm.encode(consulta).tolist()
        res = cliente_tmp.query_points(collection_name=TMP_COLLECTION, query=vector, limit=k).points
        return [r.payload["nombre_archivo"] for r in res]

    print("\nPaso 3/3: ejecutando las 12 consultas (mismo metodo, keyword como control interno)...")
    filas = []
    agg = {"keyword": {"exacta": [], "conceptual": []},
           "semantica_minilm": {"exacta": [], "conceptual": []}}

    for termino, consulta, tipo, dx in CONSULTAS:
        gt = folios_con(termino, dx)
        kw = buscar_keyword(consulta)
        sm = buscar_semantica_minilm(consulta)
        hit_kw = any(x in gt for x in kw)
        hit_sm = any(x in gt for x in sm)
        agg["keyword"][tipo].append(hit_kw)
        agg["semantica_minilm"][tipo].append(hit_sm)
        filas.append({"consulta": consulta, "tipo": tipo, "ground_truth_folios": len(gt),
                      "keyword_top": kw, "keyword_acierto": hit_kw,
                      "semantica_minilm_top": sm, "semantica_minilm_acierto": hit_sm})
        print(f"[{tipo:10}] '{consulta:42}' | KW {'OK ' if hit_kw else 'NO '} {kw[:2]} | SEM-MiniLM {'OK ' if hit_sm else 'NO '} {sm[:2]}")

    def pct(lst):
        return round(100 * sum(lst) / len(lst), 1) if lst else 0.0

    print(f"\n==== ACIERTO@{TOPK} REAL (con datos reales reembebidos hoy) ====")
    resumen = {}
    for m in ("keyword", "semantica_minilm"):
        ex, co = pct(agg[m]["exacta"]), pct(agg[m]["conceptual"])
        gl = pct(agg[m]["exacta"] + agg[m]["conceptual"])
        resumen[m] = {"exacta": ex, "conceptual": co, "global": gl}
        print(f"{m:20}| exacta={ex}% | conceptual={co}% | global={gl}%")

    out = {"nif": NIF, "topk": TOPK, "n_consultas": len(CONSULTAS),
           "metodologia": "fragmentos reales ya extraidos por Docling en produccion (mismo texto que benchmark_baseline.py), reembebidos con all-MiniLM-L6-v2 en coleccion temporal aislada; keyword recalculado igual como control interno",
           "resumen_acierto": resumen, "detalle": filas}
    Path("benchmark_baseline_minilm_real_resultado.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado: benchmark_baseline_minilm_real_resultado.json")

    shutil.rmtree(TMP_DB, ignore_errors=True)


if __name__ == "__main__":
    main()
