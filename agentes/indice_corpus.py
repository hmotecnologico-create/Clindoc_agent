import uuid
import re
import hashlib
import qdrant_client
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _extraer_fecha_documento(texto: str) -> Optional[str]:
    """Extrae la última fecha mencionada en el texto COMPLETO del documento (antes
    de fragmentar en chunks), con el mismo criterio de regex que
    VerificadorVigencia._validar_fecha. Se guarda como metadato estructurado en
    Qdrant para poder identificar el documento más reciente de un tipo (ej. ALTA)
    sin depender de similitud semántica -- los ~180 informes de alta de un mismo
    paciente comparten estructura y encabezado casi idénticos, por lo que sus
    puntajes de similitud quedan demasiado cercanos entre sí (diferencias
    <0,005 medidas en la práctica) para distinguir de forma fiable cuál es el
    episodio vigente solo por relevancia semántica. Devuelve la fecha en formato
    ISO (YYYY-MM-DD) para que ordene correctamente como texto, o None si no se
    encontró ninguna fecha reconocible.
    """
    fechas = re.findall(r'(\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b)', texto)
    if not fechas:
        return None
    fecha_str = fechas[-1].replace('-', '/')
    partes = fecha_str.split('/')
    try:
        if len(partes[0]) == 4:
            año, mes, dia = int(partes[0]), int(partes[1]), int(partes[2])
        else:
            dia, mes, año = int(partes[0]), int(partes[1]), int(partes[2])
            if año < 100:
                año += 2000
        return datetime(año, mes, dia).date().isoformat()
    except (ValueError, IndexError):
        return None


def _es_accidente_trabajo(texto: str) -> bool:
    """Detecta si un documento corresponde a un episodio de accidente de trabajo,
    por la presencia literal de la terminología administrativa que exige el
    art. 156 LGSS (RD Legislativo 8/2015) y el art. 16.3 de la Ley 31/1995: todo
    accidente de trabajo real se tramita con un "Parte de Accidente de Trabajo"
    notificado a una Mutua, lenguaje fijo y no clínico-narrativo libre. Por eso
    una búsqueda de frase literal es fiable aquí (a diferencia del diagnóstico,
    que sí requiere comprensión semántica): la ley estandariza el lenguaje, no
    lo deja a la libre redacción del médico. Se guarda como metadato estructurado
    en vez de recalcularse cada vez con búsqueda semántica (ver documentos_por_tipo).
    """
    texto_low = texto.lower()
    return "accidente de trabajo" in texto_low or "parte de accidente" in texto_low


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

        # Fusionar fragmentos que no contienen NINGÚN contenido clínico real (solo
        # encabezado/datos demográficos: "## INFORME...", "Paciente: X | NIF: Y |
        # Fecha: ...") con el fragmento siguiente. Un umbral de longitud (usado
        # antes) es frágil: el encabezado renderizado en PDF varía de tamaño según
        # la longitud del nombre/teléfono/dirección de cada paciente, así que a
        # veces supera el umbral y queda como chunk propio SIN diagnóstico. Caso
        # real confirmado: ALTA_107.pdf de 33445566R generó un chunk_0 de ~115
        # caracteres que era solo el encabezado -- al redactarlo de forma aislada
        # (un chunk = un prompt, ver AgenteRedactor), el modelo fabricó un
        # diagnóstico ("Dolor lumbar") que no existe en el documento, en vez de
        # abstenerse, porque no tenía ninguna información real que citar. La
        # fusión ahora se decide por CONTENIDO (¿aparece algún marcador de sección
        # real?), no por longitud, así que un encabezado nunca queda aislado
        # sin importar cuántos caracteres tenga.
        MARCADORES_SECCION = (
            "MOTIVO DE INGRESO", "MOTIVO DE CONSULTA", "ANTECEDENTES PERSONALES",
            "EVOLUCION CLINICA", "PLAN Y TRATAMIENTO", "PLAN:", "HALLAZGOS",
            "TECNICA:", "CONCLUSION", "PRUEBA REALIZADA", "DATOS DEL ACCIDENTE",
            "DATOS DE LA EMPRESA", "DATOS DEL TRABAJADOR", "DECLARACION",
            "PARAMETRO", "OBSERVACIONES",
        )
        fusionados = []
        pendiente = ""
        for frag in fragmentos:
            pendiente = (pendiente + "\n\n" + frag).strip() if pendiente else frag
            frag_mayus = pendiente.upper()
            if any(marcador in frag_mayus for marcador in MARCADORES_SECCION):
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
        # Fecha extraída UNA VEZ del texto completo (no por chunk, para que todos los
        # fragmentos de un mismo documento compartan la misma fecha aunque el chunk
        # concreto recuperado no incluya el encabezado). Ver documento_mas_reciente().
        fecha_doc = _extraer_fecha_documento(texto)
        # Tipo de episodio por METADATO, no por búsqueda semántica repetida: se
        # calcula una vez por documento (misma lógica que fecha_documento) para
        # que la sección de baja laboral pueda filtrar de forma determinista si
        # el episodio activo es un accidente de trabajo, en vez de depender de
        # una búsqueda semántica que puede traer ruido (ver AgenteRedactor.redactar).
        tipo_episodio = "accidente_trabajo" if _es_accidente_trabajo(texto) else "comun"
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
                    "tipo_documento": tipo_documento,  # prefijo (ALTA/CONS/LAB/RAD/PAT) para filtrar por fuente_preferente
                    "doc_id": doc_id,
                    "fecha_documento": fecha_doc,  # ISO o None; ver documento_mas_reciente()
                    "tipo_episodio": tipo_episodio,  # comun / accidente_trabajo; ver documentos_por_tipo()
                    "patient_hash": self.patient_hash  # seudonimización SHA-256 del NIF (RGPD)
                }
            ))
        self.cliente.upsert(collection_name=self.nombre_coleccion, points=points)

    def documento_mas_reciente(self, tipo_documento: str) -> List[Dict]:
        """Identifica el documento de un tipo (ej. 'ALTA') con la fecha más reciente
        POR METADATO, no por similitud semántica. A diferencia de buscar_evidencias(),
        no hay ambigüedad de puntajes cercanos entre sí: se compara la fecha real
        extraída de cada documento al indexar (fecha_documento), determinista.

        Devuelve todos los chunks del documento más reciente encontrado, en el mismo
        formato que buscar_evidencias() (texto/archivo/chunk_id/score), para que
        AgenteRedactor los procese exactamente igual. Si ningún documento del tipo
        indicado tiene fecha reconocible, devuelve lista vacía (el llamador debe
        recurrir a buscar_evidencias() como respaldo).
        """
        query_filter = models.Filter(
            must=[models.FieldCondition(key="tipo_documento", match=models.MatchValue(value=tipo_documento))]
        )
        puntos = []
        offset = None
        while True:
            lote, offset = self.cliente.scroll(
                collection_name=self.nombre_coleccion, scroll_filter=query_filter,
                limit=256, offset=offset, with_payload=True, with_vectors=False,
            )
            puntos.extend(lote)
            if offset is None:
                break

        con_fecha = [p for p in puntos if p.payload.get("fecha_documento")]
        if not con_fecha:
            return []
        doc_id_reciente = max(con_fecha, key=lambda p: p.payload["fecha_documento"]).payload["doc_id"]

        return [{
            "texto": p.payload["texto"],
            "archivo": p.payload["nombre_archivo"],
            "chunk_id": p.payload.get("chunk_id", "unknown"),
            "score": 1.0,  # no aplica score semántico; selección por fecha, no por similitud
            "tipo_episodio": p.payload.get("tipo_episodio", "comun"),
        } for p in puntos if p.payload.get("doc_id") == doc_id_reciente]

    def documento_accidente_trabajo(self, tipo_documento: str) -> List[Dict]:
        """Localiza, por METADATO exacto (tipo_documento + tipo_episodio), el
        documento de accidente de trabajo del paciente activo si existe alguno,
        sin importar si es o no el episodio más reciente (un accidente de ayer
        no debe desaparecer solo porque hoy hubo una consulta por otro motivo).
        Devuelve lista vacía si el paciente no tiene ningún episodio de este tipo.
        """
        query_filter = models.Filter(must=[
            models.FieldCondition(key="tipo_documento", match=models.MatchValue(value=tipo_documento)),
            models.FieldCondition(key="tipo_episodio", match=models.MatchValue(value="accidente_trabajo")),
        ])
        puntos = []
        offset = None
        while True:
            lote, offset = self.cliente.scroll(
                collection_name=self.nombre_coleccion, scroll_filter=query_filter,
                limit=256, offset=offset, with_payload=True, with_vectors=False,
            )
            puntos.extend(lote)
            if offset is None:
                break
        return [{
            "texto": p.payload["texto"],
            "archivo": p.payload["nombre_archivo"],
            "chunk_id": p.payload.get("chunk_id", "unknown"),
            "score": 1.0,
            "tipo_episodio": "accidente_trabajo",
        } for p in puntos]

    def documentos_por_tipo(self, tipo_documento: str) -> List[Dict]:
        """Devuelve TODOS los chunks de un tipo de documento (ej. 'PAT'), por
        METADATO exacto, no por similitud semántica. Reemplaza a la búsqueda
        semántica complementaria que usaba AgenteRedactor para intentar
        localizar el Parte de Accidente de Trabajo: esa búsqueda demostró traer
        ruido (ver caso real 48991234S, donde una consulta semántica sobre
        "accidente de trabajo, empresa, mutua" también trajo un ALTA de Cólico
        Nefrítico sin relación alguna). Un documento de tipo PAT es siempre y
        únicamente el Parte de Accidente de Trabajo del paciente activo -- no
        hay ambigüedad que resolver con similitud, así que un filtro exacto
        por tipo_documento es estrictamente más fiable.
        """
        query_filter = models.Filter(
            must=[models.FieldCondition(key="tipo_documento", match=models.MatchValue(value=tipo_documento))]
        )
        puntos = []
        offset = None
        while True:
            lote, offset = self.cliente.scroll(
                collection_name=self.nombre_coleccion, scroll_filter=query_filter,
                limit=256, offset=offset, with_payload=True, with_vectors=False,
            )
            puntos.extend(lote)
            if offset is None:
                break
        return [{
            "texto": p.payload["texto"],
            "archivo": p.payload["nombre_archivo"],
            "chunk_id": p.payload.get("chunk_id", "unknown"),
            "score": 1.0,
        } for p in puntos]

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

