# -*- coding: utf-8 -*-
"""
Regresión: usar_coleccion_paciente() debe recrear limpia una colección aunque ya
exista físicamente con OTRA dimensión de vector (p.ej. tras cambiar de modelo de
embeddings). Bug real encontrado: qdrant-client en modo local no cierra la conexión
SQLite de la colección antigua en su propio delete_collection(); en Windows eso
deja storage.sqlite bloqueado, el rmtree posterior falla en silencio, y la colección
"recreada" carga los puntos viejos bajo la config nueva -> crash en el primer upsert
("could not broadcast input array from shape (768,) into shape (384,)").
"""
import hashlib
import shutil
from pathlib import Path

import qdrant_client
from qdrant_client.http import models

from agentes.indice_corpus import IndiceCorpus

NIF_TEST = "TESTNIF999Z"
TMP = Path("datos/_test_dim_fix_regresion")


def _limpiar():
    if TMP.exists():
        for p in TMP.rglob("*"):
            try:
                p.chmod(0o777)
            except Exception:
                pass
        shutil.rmtree(TMP, ignore_errors=True)


def test_usar_coleccion_paciente_recrea_limpia_con_dimension_distinta():
    _limpiar()
    hash_test = hashlib.sha256(NIF_TEST.encode("utf-8")).hexdigest()
    nombre = f"expediente_{hash_test}"

    # Simula el estado real encontrado en producción: colección existente en 384d con datos.
    cli = qdrant_client.QdrantClient(path=str(TMP))
    cli.create_collection(nombre, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
    cli.upsert(nombre, points=[models.PointStruct(id=1, vector=[0.1] * 384, payload={})])
    cli.close()

    idx = IndiceCorpus.__new__(IndiceCorpus)
    idx.cliente = qdrant_client.QdrantClient(path=str(TMP))
    idx.dim_vectores = 768
    idx.patient_hash = None
    idx.nombre_coleccion = None

    idx.usar_coleccion_paciente(NIF_TEST)

    info = idx.cliente.get_collection(idx.nombre_coleccion)
    assert info.config.params.vectors.size == 768
    assert info.points_count == 0

    # Un upsert con la dimensión nueva no debe fallar.
    idx.cliente.upsert(idx.nombre_coleccion, points=[models.PointStruct(id=2, vector=[0.1] * 768, payload={})])
    idx.cliente.close()
    _limpiar()


if __name__ == "__main__":
    test_usar_coleccion_paciente_recrea_limpia_con_dimension_distinta()
    print("OK: usar_coleccion_paciente recrea limpia tras cambio de dimension")
