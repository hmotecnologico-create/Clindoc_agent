import sys
import os
import re
import yaml
import uuid
import time
import ollama
import qdrant_client
from typing import List, Optional, Dict, Any, TypedDict, Literal
from datetime import date, timedelta, datetime
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from sentence_transformers import SentenceTransformer
from qdrant_client.http import models

import json

# Forzar salida en UTF-8 para evitar errores de codificación en consola Windows
if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- MODELOS DE DATOS (Pydantic v2) ---
class Campo(BaseModel):
    """Modelo para campos de validación del guión"""
    nombre: str
    regla: str
    tipo: str = "texto"

class Seccion(BaseModel):
    """Modelo para secciones del informe"""
    titulo: str
    instruccion: str
    campos: List[Campo] = []

class GuionInforme(BaseModel):
    titulo: str
    secciones: List[Seccion]

# --- MOTOR SEMÁNTICO (Qdrant) ---
class IndiceCorpus:
    """Motor de indexación y búsqueda vectorial con Qdrant local"""
    def __init__(self, ruta_db: str = "datos/qdrant_db", collection: str = "clinica"):
        self.ruta_db = ruta_db
        self.collection = collection
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.client = qdrant_client.QdrantClient(path=ruta_db)
        self._init_collection()
    
    def _init_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
            )
    
    def indexar(self, chunk_id: str, texto: str, metadata: dict = {}):
        vector = self.model.encode(texto).tolist()
        point_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(
                id=point_id, vector=vector,
                payload={"chunk_id": chunk_id, "texto": texto, **metadata}
            )]
        )
    
    def buscar(self, query: str, top_k: int = 5) -> List[Dict]:
        vector = self.model.encode(query).tolist()
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector, limit=top_k
        )
        return [{"score": r.score, **r.payload} for r in results]

if __name__ == "__main__":
    print("ClinDoc Agent - Pipeline de Ingesta v0.1")
    print("Motor semántico Qdrant inicializado correctamente.")
