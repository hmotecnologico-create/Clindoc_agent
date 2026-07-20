import uuid
import hashlib
import qdrant_client
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class IndiceCorpus:
    """
    Motor de búsqueda semántica local con Qdrant.

    PRUEBAS REALIZADAS:
    - Comparativa keyword vs. semántica (benchmark_baseline.py, 12 consultas,
      524 folios reales, ground truth por biomarcador+diagnóstico): con
      all-MiniLM-L6-v2 (genérico, 384d) la búsqueda semántica quedaba
      EMPATADA con keyword (41,7% acierto@3 ambas). Con un modelo multilingüe
      (paraphrase-multilingual-mpnet-base-v2, 768d) la semántica alcanza
      66,7% global y 83,3% en consultas conceptuales, sin perder precisión
      en consultas exactas (50,0% en ambos modelos). Ver
      benchmark_baseline_modelo_multilingue.py.

    MÉTRICAS DE RENDIMIENTO:
    - Embedding: SentenceTransformer paraphrase-multilingual-mpnet-base-v2
    - Dimensión vectores: 768
    """
    def __init__(self, ruta_db: str = "datos/qdrant_db"):
        self.cliente = qdrant_client.QdrantClient(path=ruta_db)
        self.modelo_emb = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
        self.dim_vectores = self.modelo_emb.get_sentence_embedding_dimension()
        self.nombre_coleccion = "expediente_clinico"
        self.patient_hash = None
        self._setup_qdrant()

    def _setup_qdrant(self):
        colecciones = self.cliente.get_collections().collections
        if not any(c.name == self.nombre_coleccion for c in colecciones):
            self.cliente.create_collection(
                collection_name=self.nombre_coleccion,
                vectors_config=models.VectorParams(size=self.dim_vectores, distance=models.Distance.COSINE),
            )

    def usar_coleccion_paciente(self, nif: str):
        """AISLAMIENTO + SEUDONIMIZACIÓN POR PACIENTE (RGPD): el NIF se reduce a su hash SHA-256
        (patient_hash) y la colección vectorial se nombra con ese hash ('expediente_{hash}'),
        recreada limpia en cada procesamiento. El NIF en claro NUNCA se persiste en la base
        vectorial; además evita mezclar folios entre pacientes y los puntos duplicados al reprocesar.

        La recreación se VERIFICA (no solo se intenta). Causa raíz encontrada en producción:
        qdrant-client en modo local NO cierra la conexión SQLite de la colección antigua dentro
        de su propio delete_collection() (local/qdrant_local.py: hace `del _collection` sin
        `.close()`); en Windows eso deja `storage.sqlite` bloqueado, el `shutil.rmtree(...,
        ignore_errors=True)` posterior falla EN SILENCIO, y la colección "recreada" carga los
        puntos viejos del fichero no borrado bajo la config nueva (crash real visto: "could not
        broadcast input array from shape (768,) into shape (384,)" al cambiar de modelo de
        embeddings). Por eso aquí se cierra explícitamente la colección antigua antes de
        borrarla, y se confirma la dimensión/vacío real tras crear, reintentando si no coincide.
        """
        self.patient_hash = hashlib.sha256(nif.encode("utf-8")).hexdigest()
        self.nombre_coleccion = f"expediente_{self.patient_hash}"

        def _existe():
            return any(c.name == self.nombre_coleccion for c in self.cliente.get_collections().collections)

        for intento in range(3):
            if _existe():
                try:
                    local = getattr(self.cliente, "_client", None)
                    vieja = getattr(local, "collections", {}).get(self.nombre_coleccion) if local else None
                    if vieja is not None:
                        vieja.close()
                except Exception:
                    logger.warning("No se pudo cerrar la colección previa %s antes de borrarla", self.nombre_coleccion)
                try:
                    self.cliente.delete_collection(self.nombre_coleccion)
                except Exception:
                    logger.warning("delete_collection falló para %s (intento %d)", self.nombre_coleccion, intento)
            self.cliente.create_collection(
                collection_name=self.nombre_coleccion,
                vectors_config=models.VectorParams(size=self.dim_vectores, distance=models.Distance.COSINE),
            )
            info = self.cliente.get_collection(self.nombre_coleccion)
            if info.config.params.vectors.size == self.dim_vectores and info.points_count == 0:
                return
            logger.warning(
                "Colección %s no quedó limpia (dim=%s, puntos=%d) tras intento %d; reintentando",
                self.nombre_coleccion, info.config.params.vectors.size, info.points_count, intento,
            )
        raise RuntimeError(
            f"No se pudo recrear limpia la colección {self.nombre_coleccion} tras 3 intentos "
            f"(dimensión esperada {self.dim_vectores}); revisar meta.json/almacenamiento físico."
        )

    def _semantic_chunking(self, texto: str) -> List[str]:
        """Chunking semántico mejorado - respeta párrafos y tablas"""
        # Dividir por párrafos primero
        parrafos = texto.split('\n\n')
        fragmentos = []
        chunk_actual = ""
        
        for parrafo in parrafos:
            if len(chunk_actual) + len(parrafo) < 1000:
                chunk_actual += parrafo + "\n\n"
            else:
                if chunk_actual:
                    fragmentos.append(chunk_actual.strip())
                chunk_actual = parrafo + "\n\n"
        
        if chunk_actual:
            fragmentos.append(chunk_actual.strip())

        # Fusionar fragmentos demasiado pequeños (p.ej. un encabezado "## INFORME..."
        # aislado, sin contenido clínico) con el fragmento siguiente. Un chunk minúsculo
        # compite en la búsqueda semántica por su brevedad/genericidad y puede ganarle
        # al fragmento real que sí contiene el diagnóstico, dejando la sección vacía.
        MIN_CHUNK = 100
        fusionados = []
        pendiente = ""
        for frag in fragmentos:
            pendiente = (pendiente + "\n\n" + frag).strip() if pendiente else frag
            if len(pendiente) >= MIN_CHUNK:
                fusionados.append(pendiente)
                pendiente = ""
        if pendiente:
            if fusionados:
                fusionados[-1] = (fusionados[-1] + "\n\n" + pendiente).strip()
            else:
                fusionados.append(pendiente)

        return fusionados if fusionados else [texto]

    def indexar_documento(self, doc_id: str, texto: str, nombre_original: str):
        """Indexa documento con chunk_id para Deep Linking"""
        fragmentos = self._semantic_chunking(texto)
        tipo_documento = nombre_original.split('_')[0] if '_' in nombre_original else nombre_original
        points = []
        for i, frag in enumerate(fragmentos):
            vector = self.modelo_emb.encode(frag).tolist()
            chunk_id = f"{doc_id}_chunk_{i}"
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),  # UUID válido para Qdrant
                vector=vector,
                payload={
                    "texto": frag,
                    "chunk_id": chunk_id,  # GUARDAR PARA DEEP LINKING
                    "nombre_archivo": nombre_original,
                    "tipo_documento": tipo_documento,  # prefijo (ALTA/CONS/LAB/RAD) para filtrar por fuente_preferente
                    "doc_id": doc_id,
                    "patient_hash": self.patient_hash  # seudonimización SHA-256 del NIF (RGPD)
                }
            ))
        self.cliente.upsert(collection_name=self.nombre_coleccion, points=points)

    def buscar_evidencias(self, consulta: str, n: int = 3, tipo_documento: str = None) -> List[Dict]:
        """Busca evidencias con referencias de chunk.

        tipo_documento: si se indica (ej. "ALTA"), restringe la búsqueda a chunks de ese
        tipo de documento. Evita que, en un corpus de 524 folios/paciente con tipos muy
        heterogéneos (LAB/CONS/RAD), un fragmento irrelevante gane por similitud al
        fragmento correcto de la sección buscada.
        """
        vector = self.modelo_emb.encode(consulta).tolist()
        query_filter = None
        if tipo_documento:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="tipo_documento", match=models.MatchValue(value=tipo_documento))]
            )
        res = self.cliente.query_points(
            collection_name=self.nombre_coleccion, query=vector, limit=n, query_filter=query_filter
        ).points
        return [{
            "texto": r.payload["texto"],
            "archivo": r.payload["nombre_archivo"],
            "chunk_id": r.payload.get("chunk_id", "unknown"),
            "score": r.score,
        } for r in res]

