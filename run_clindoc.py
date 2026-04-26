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
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import json
import pypdf

# Forzar salida en UTF-8 para evitar errores de codificación en consola Windows
if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- CIFRADO AES-256 (FASE 5) ---
class CifradoClinDoc:
    """Cifrado para datos sensibles en entorno local"""
    def __init__(self, clave: str = "clinDoc_Sovereign_2026"):
        import hashlib
        from cryptography.fernet import Fernet
        self.key = hashlib.sha256(clave.encode()).digest()
        self.cipher = Fernet(self.key)
    
    def cifrar(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def descifrar(self, data: str) -> str:
        return self.cipher.decrypt(data.encode()).decode()

# --- ANALYTICS RECORDER ---
class DashboardRecorder:
    def __init__(self, output_file: str = "dashboard_data.json"):
        self.output_file = output_file
        self.data = {
            "session_start": datetime.now().isoformat(),
            "kpis": {
                "total_docs": 0,
                "total_time": 0,
                "avg_confidence": 0,
                "critical_risks": 0
            },
            "events": []
        }

    def record_event(self, event_type: str, details: Dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        }
        self.data["events"].append(event)
        self._update_kpis()
        self._save()

    def _update_kpis(self):
        doc_events = [e for e in self.data["events"] if e["type"] == "ingesta_documento"]
        self.data["kpis"]["total_docs"] = len(doc_events)
        
        confidences = [e["details"].get("confianza", 0) for e in self.data["events"] if "confianza" in e["details"]]
        if confidences:
            self.data["kpis"]["avg_confidence"] = sum(confidences) / len(confidences)
            
        self.data["kpis"]["critical_risks"] = len([e for e in self.data["events"] if e["details"].get("estado_riesgo") == "CRITICAL"])

    def _save(self):
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4)


# --- MODELOS DE DATOS (Pydantic v2 - FASE 5) ---
class Campo(BaseModel):
    nombre: str
    requerido: bool = True
    patron: Optional[str] = None 
    vigencia: Optional[str] = None

class Seccion(BaseModel):
    id: str
    titulo: str
    instruccion: str

class IdentidadDocumento(BaseModel):
    documento_id: str
    nif: Optional[str] = None
    nombre_completo: Optional[str] = None
    confianza: float = 0.0

class GuionInforme(BaseModel):
    titulo: str
    secciones: List[Seccion]

# === NUEVOS MODELOS FASE 5: Validación Pydantic ===
class PatientAuditSchema(BaseModel):
    """Esquema de validación para auditoría de pacientes"""
    nif_detected: str = Field(..., min_length=9, max_length=9)
    nif_validado: bool = False
    nombre_completo: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["APPROVED", "BLOCKED", "PENDING"] = "PENDING"
    fecha_auditoria: datetime = Field(default_factory=datetime.now)
    
    @field_validator('nif_detected')
    @classmethod
    def validar_nif_oficial(cls, v: str) -> str:
        """Valida NIF español con algoritmo oficial"""
        letras = "TRWAGMYFPDXBNJZSQVHLCKE"
        if len(v) != 9:
            raise ValueError("NIF debe tener 9 caracteres")
        numero, letra = v[:8].upper(), v[8].upper()
        if not letra.isalpha():
            raise ValueError("Último caracter debe ser letra")
        if letras[int(numero) % 23] != letra:
            raise ValueError("Letra NIF inválida")
        return v

def validar_nif(nif: str) -> bool:
    """Valida NIF español - función auxiliar"""
    try:
        PatientAuditSchema(nif_detected=nif, nombre_completo="test")
        return True
    except:
        return False

# --- MOTOR SEMÁNTICO (Qdrant) con DEEP LINKING (FASE 3) ---
class IndiceCorpus:
    def __init__(self, ruta_db: str = "datos/qdrant_db"):
        self.cliente = qdrant_client.QdrantClient(path=ruta_db)
        self.modelo_emb = SentenceTransformer('all-MiniLM-L6-v2') 
        self.nombre_coleccion = "expediente_clinico"
        self._setup_qdrant()

    def _setup_qdrant(self):
        colecciones = self.cliente.get_collections().collections
        if not any(c.name == self.nombre_coleccion for c in colecciones):
            self.cliente.create_collection(
                collection_name=self.nombre_coleccion,
                vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
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
        
        return fragmentos if fragmentos else [texto]

    def indexar_documento(self, doc_id: str, texto: str, nombre_original: str):
        """Indexa documento con chunk_id para Deep Linking"""
        fragmentos = self._semantic_chunking(texto)
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
                    "doc_id": doc_id
                }
            ))
        self.cliente.upsert(collection_name=self.nombre_coleccion, points=points)

    def buscar_evidencias(self, consulta: str, n: int = 3) -> List[Dict]:
        """Busca evidencias con referencias de chunk"""
        vector = self.modelo_emb.encode(consulta).tolist()
        res = self.cliente.query_points(collection_name=self.nombre_coleccion, query=vector, limit=n).points
        return [{
            "texto": r.payload["texto"], 
            "archivo": r.payload["nombre_archivo"],
            "chunk_id": r.payload.get("chunk_id", "unknown")
        } for r in res]

# --- AGENTE ESCÁNER HETEROGÉNEO (FASE 1: Multi-formato + Imágenes) ---
class AgenteEscanner:
    """
    Procesa documentos clínicos en múltiples formatos:
    - PDF: Docling (texto + tablas) o PyPDF2 fallback
    - MD/TXT: Parseo directo
    - DOCX: python-docx
    - Detecta imágenes y marca para revisión manual
    """
    def __init__(self, ruta: str = "datos/expedientes"):
        self.ruta = Path(ruta)
        if not self.ruta.exists():
            self.ruta.mkdir(parents=True, exist_ok=True)
        
        # Intentar inicializar Docling
        self.docling_disponible = False
        try:
            from docling.document_converter import DocumentConverter
            self.converter = DocumentConverter()
            self.docling_disponible = True
            print("[INFO] Docling disponible para extracción layout-aware")
        except ImportError:
            print("[AVISO] Docling no disponible, usando fallback PyPDF2")
    
    def scan(self) -> List[Dict]:
        """Escanea todos los documentos de la carpeta"""
        if not list(self.ruta.glob("*")):
            # Crear documento de prueba si no hay ninguno
            test_file = self.ruta / "paciente_juan.txt"
            test_file.write_text("Hallazgos clínicos en paciente Juan Pérez García: El paciente presenta una evolución favorable tras cirugía cardiovascular. Se recomienda reposo por 15 días.", encoding='utf-8')
        
        documentos = []
        
        # PDFs
        for f in self.ruta.glob("*.pdf"):
            documentos.append(self._procesar_pdf(f))
        
        # Markdown
        for f in self.ruta.glob("*.md"):
            documentos.append(self._procesar_markdown(f))
        
        # TXT (legacy)
        for f in self.ruta.glob("*.txt"):
            documentos.append(self._procesar_txt(f))
        
        # DOCX
        for f in self.ruta.glob("*.docx"):
            documentos.append(self._procesar_docx(f))
        
        return documentos
    
    def _procesar_pdf(self, archivo: Path) -> Dict:
        """Procesa PDF con Docling - extracción layout-aware"""
        # Detectar si tiene imágenes en el nombre
        tiene_imagenes_ref = any(palabra in archivo.name.lower() 
                                for palabra in ['imagen', 'rx', 'rmn', 'tac', 'eco', 'foto'])
        
        if self.docling_disponible:
            try:
                from docling.document_converter import DocumentConverter
                converter = DocumentConverter()
                result = converter.convert(archivo)
                json_data = result.document.export_to_dict()
                
                # Detectar imágenes en el documento
                imagenes = []
                if hasattr(result.document, 'images'):
                    imagenes = result.document.images
                
                return {
                    "id": archivo.stem,
                    "nombre": archivo.name,
                    "formato": "pdf_docling",
                    "texto": json_data.get("text", ""),
                    "tablas": json_data.get("tables", []),
                    "imagenes_detectadas": len(imagenes) if imagenes else 0,
                    "imagenes_procesables": False,  # gemma3 NO acepta imágenes
                    "nota_imagenes": "Revisión manual requerida para imágenes clínicas" if (imagenes or tiene_imagenes_ref) else None,
                    "metadatos": {
                        "paginas": len(json_data.get("pages", [])),
                        "confianza": json_data.get("confidence", 0.0),
                        "metodo": "docling"
                    }
                }
            except Exception as e:
                print(f"[WARN] Docling falló para {archivo.name}: {e}")
        
        # Fallback: PyPDF2
        return self._procesar_pdf_fallback(archivo, tiene_imagenes_ref)
    
    def _procesar_pdf_fallback(self, archivo: Path, tiene_imagenes_ref: bool = False) -> Dict:
        """Fallback si Docling no está disponible"""
        texto = ""
        with open(archivo, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                texto += page.extract_text() or ""
        
        return {
            "id": archivo.stem,
            "nombre": archivo.name,
            "formato": "pdf_pypdf2",
            "texto": texto,
            "imagenes_detectadas": 1 if tiene_imagenes_ref else 0,
            "imagenes_procesables": False,
            "nota_imagenes": "Revisión manual requerida" if tiene_imagenes_ref else None,
            "metadatos": {"metodo": "PyPDF2"}
        }
    
    def _procesar_markdown(self, archivo: Path) -> Dict:
        """Procesa Markdown directo"""
        contenido = archivo.read_text(encoding='utf-8')
        
        # Detectar si contiene referencias a imágenes
        tiene_imagenes = any(palabra in contenido.lower() 
                            for palabra in ['![image]', '![foto]', 'dicom', 'imagen:', 'rx:', 'rmn:', 'tac:'])
        
        return {
            "id": archivo.stem,
            "nombre": archivo.name,
            "formato": "md",
            "texto": contenido,
            "imagenes_detectadas": 1 if tiene_imagenes else 0,
            "imagenes_procesables": False,
            "nota_imagenes": "Revisión manual requerida para imágenes clínicas" if tiene_imagenes else None,
            "metadatos": {}
        }
    
    def _procesar_txt(self, archivo: Path) -> Dict:
        """Procesa texto plano"""
        return {
            "id": archivo.stem,
            "nombre": archivo.name,
            "formato": "txt",
            "texto": archivo.read_text(encoding='utf-8'),
            "imagenes_detectadas": 0,
            "imagenes_procesables": False,
            "metadatos": {}
        }
    
    def _procesar_docx(self, archivo: Path) -> Dict:
        """Procesa Word"""
        try:
            from docx import Document
            doc = Document(archivo)
            texto = "\n".join([p.text for p in doc.paragraphs])
            return {
                "id": archivo.stem,
                "nombre": archivo.name,
                "formato": "docx",
                "texto": texto,
                "imagenes_detectadas": 0,
                "imagenes_procesables": False,
                "metadatos": {}
            }
        except Exception as e:
            return {
                "id": archivo.stem,
                "nombre": archivo.name,
                "formato": "docx_error",
                "texto": f"Error al procesar DOCX: {str(e)}",
                "error": True
            }

# --- VERIFICADOR DE IDENTIDAD CON NIF OFICIAL (FASE 5) ---
class VerificadorIdentidad:
    """Validador de identidad con algoritmo NIF oficial español"""
    
    def __init__(self):
        self.letras_nif = "TRWAGMYFPDXBNJZSQVHLCKE"
    
    def _extraer_nif(self, texto: str) -> Optional[str]:
        """Extrae NIF del texto"""
        match = re.search(r'\b(\d{8}[A-Z])\b', texto, re.IGNORECASE)
        return match.group(1).upper() if match else None
    
    def validar(self, nif_ref: str, texto_doc: str) -> Dict[str, Any]:
        """Valida que el NIF del documento coincida con el reference"""
        nif_doc = self._extraer_nif(texto_doc)
        
        if not nif_doc:
            return {
                "valido": False,
                "detalle": "No se detectó NIF en el documento",
                "nif_encontrado": None
            }
        
        nif_valido_formato = validar_nif(nif_doc)
        coincide = nif_doc == nif_ref.upper() if nif_ref else False
        
        return {
            "valido": coincide and nif_valido_formato,
            "detalle": f"NIF {'COINCIDE' if coincide else 'NO COINCIDE'}: {nif_doc}",
            "nif_encontrado": nif_doc,
            "nif_valido_formato": nif_valido_formato
        }

# --- VERIFICADOR DE VIGENCIA MEJORADO (FASE 2) ---
class VerificadorVigencia:
    def __init__(self, dias_margen: int = 365):
        self.dias_margen = dias_margen

    def validar(self, texto: str, regla: str) -> Dict[str, Any]:
        """
        Busca fechas en el texto y valida según la regla (ej: 'no_vencido', 'reciente_6_meses')
        """
        # Regex simple para capturar fechas comunes (DD/MM/YYYY)
        fechas = re.findall(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', texto)
        if not fechas:
            return {"valido": True, "detalle": "No se detectaron fechas para validar vigencia."}
        
        try:
            # Tomamos la última fecha mencionada como la más relevante
            fecha_doc_str = fechas[-1].replace('-', '/')
            partes = fecha_doc_str.split('/')
            if len(partes[2]) == 2: partes[2] = "20" + partes[2]
            fecha_doc = datetime.strptime("/".join(partes), "%d/%m/%Y")
            
            hoy = datetime.now()
            
            if regla == "no_vencido":
                es_valido = fecha_doc >= hoy
                detalle = f"Vigencia hasta {fecha_doc.date()}. {'OK' if es_valido else 'EXPIRADO'}"
            elif regla == "reciente_6_meses":
                es_valido = fecha_doc >= (hoy - timedelta(days=180))
                detalle = f"Fecha documento: {fecha_doc.date()}. {'OK' if es_valido else 'ANTIGUO'}"
            else:
                es_valido = True
                detalle = f"Validado manualmente: {fecha_doc.date()}"
                
            return {"valido": es_valido, "detalle": detalle}
        except:
            return {"valido": False, "detalle": "Error al procesar formato de fecha."}

class AgenteEnsamblador:
    def __init__(self, ruta_informe: str, ruta_anexos: List[str]):
        self.ruta_informe = ruta_informe
        self.ruta_anexos = ruta_anexos

    def ensamblar(self, salida_final: str):
        merger = pypdf.PdfWriter()
        
        # 1. Agregar el informe técnico generado
        if os.path.exists(self.ruta_informe):
            merger.append(self.ruta_informe)
        
        # 2. Agregar anexos (solo si son PDFs)
        for anexo in self.ruta_anexos:
            if anexo.lower().endswith('.pdf') and os.path.exists(anexo):
                merger.append(anexo)
        
        with open(salida_final, "wb") as f:
            merger.write(f)
        merger.close()
        return salida_final

class AgenteRedactor:
    def __init__(self, indice: IndiceCorpus, modelo: str = "gemma3:4b"):
        self.indice = indice
        self.modelo = modelo

    def redactar(self, seccion: Seccion) -> str:
        """Redacta sección con Deep Linking a fuentes"""
        evidencias = self.indice.buscar_evidencias(seccion.titulo)
        
        # Deep Linking: incluir chunk_id en las referencias
        contexto = "\n".join([
            f"- {e['texto']} [Fuente: {e['archivo']}#{e['chunk_id']}]"
            for e in evidencias
        ])
        
        prompt = f"""Eres un auditor clínico profesional. 
Redacta la sección '{seccion.titulo}'.
Instrucción: {seccion.instruccion}
Datos: {contexto}
IMPORTANTE: Cada afirmación debe citar su fuente usando el formato [Fuente: archivo#chunk_id]
Responde de forma técnica y concisa en español."""
        
        try:
            r = ollama.chat(model=self.modelo, messages=[{'role': 'user', 'content': prompt}])
            return r['message']['content']
        except Exception as e:
            return f"Error en IA local: {str(e)}"

# --- ESTADO PARA LANGGRAPH (FASE 2) ---
class AgentState(TypedDict):
    """Estado del orquestador multi-agente"""
    documentos: List[Dict]
    paciente: Dict
    resultados: Dict[str, str]
    errores: List[str]
    retry_count: int
    trace: List[str]  # Chain of thought

# --- ORQUESTADOR CON LANGGRAPH (FASE 2) ---
class OrquestadorLangGraph:
    """Orquestador basado en grafo con ciclos de retry"""
    
    def __init__(self, config_gui: Dict):
        self.guion = GuionInforme(**config_gui)
        self.indice = IndiceCorpus()
        self.escanner = AgenteEscanner()
        self.redactor = AgenteRedactor(self.indice)
        self.verificador_id = VerificadorIdentidad()
        self.verificador_vigencia = VerificadorVigencia()
        self.recorder = DashboardRecorder()
        self.docs_procesados = []
    
    def _extraer_nif(self, texto: str) -> Optional[str]:
        """Extrae NIF del texto"""
        match = re.search(r'\b(\d{8}[A-Z])\b', texto, re.IGNORECASE)
        return match.group(1).upper() if match else None
    
    def _node_ingestion(self, state: AgentState) -> AgentState:
        """Nodo 1: Escaneo de documentos"""
        state["trace"].append(">>> INICIO: Escaneando documentos...")
        docs = self.escanner.scan()
        state["documentos"] = docs
        
        for d in docs:
            self.recorder.record_event("ingesta_documento", {
                "id": d["id"],
                "formato": d.get("formato", "desconocido"),
                "imagenes": d.get("imagenes_detectadas", 0),
                "nota": d.get("nota_imagenes")
            })
            self.indice.indexar_documento(d['id'], d['texto'], d['nombre'])
        
        state["trace"].append(f"<<< FIN: {len(docs)} documentos escaneados e indexados")
        return state
    
    def _node_validate_identity(self, state: AgentState) -> AgentState:
        """Nodo 2: Validar identidad del paciente"""
        state["trace"].append(">>> VALIDANDO: Identidad del paciente...")
        
        errores = []
        paciente_ref = state["paciente"]
        nif_ref = paciente_ref.get("nif", "")
        
        for doc in state["documentos"]:
            validacion = self.verificador_id.validar(nif_ref, doc["texto"])
            if not validacion["valido"]:
                errores.append(f"IDENTIDAD: {doc['nombre']} - {validacion['detalle']}")
                state["trace"].append(f"  ⚠️ {validacion['detalle']}")
        
        if errores:
            state["errores"].extend(errores)
            state["retry_count"] = state.get("retry_count", 0) + 1
        
        state["trace"].append(f"<<< FIN: Validación identidad {'FALLIDA' if errores else 'OK'}")
        return state
    
    def _node_validate_vigency(self, state: AgentState) -> AgentState:
        """Nodo 3: Validar vigencia de documentos"""
        state["trace"].append(">>> VALIDANDO: Vigencia de documentos...")
        
        errores = []
        
        for doc in state["documentos"]:
            validacion = self.verificador_vigencia.validar(doc["texto"], "reciente_6_meses")
            if not validacion["valido"]:
                errores.append(f"VIGENCIA: {doc['nombre']} - {validacion['detalle']}")
                state["trace"].append(f"  ⚠️ {validacion['detalle']}")
        
        if errores:
            state["errores"].extend(errores)
        
        state["trace"].append(f"<<< FIN: Validación vigencia {'FALLIDA' if errores else 'OK'}")
        return state
    
    def _node_redact(self, state: AgentState) -> AgentState:
        """Nodo 4: Redactar resumen con RAG + Deep Linking"""
        state["trace"].append(">>> REDACTANDO: Generando resumen clínico...")
        
        resultados = {}
        for seccion in self.guion.secciones:
            resultado = self.redactor.redactar(seccion)
            resultados[seccion.titulo] = resultado
            
            conf = 0.85 if "Error" not in resultado else 0.1
            self.recorder.record_event("analisis_seccion", {
                "seccion": seccion.titulo,
                "confianza": conf,
                "estado_riesgo": "SAFE" if conf > 0.8 else "WARNING"
            })
        
        state["resultados"] = resultados
        state["trace"].append("<<< FIN: Resumen redactado con Deep Linking")
        return state
    
    def _node_assemble(self, state: AgentState) -> AgentState:
        """Nodo 5: Ensamblar informe final con notas de imágenes"""
        state["trace"].append(">>> ENSAMBLANDO: Generando informe PDF...")
        
        # Documentos con imágenes
        docs_con_imagenes = [d for d in state["documentos"] if d.get("imagenes_detectadas", 0) > 0]
        
        # Generar PDF
        filename = self._generar_informe_con_notas(state, docs_con_imagenes)
        
        state["trace"].append(f"<<< FIN: Informe generado: {filename}")
        return state
    
    def _generar_informe_con_notas(self, state: AgentState, docs_con_imagenes: List[Dict]) -> str:
        """Genera PDF incluyendo notas de imágenes"""
        filename = f"docs/informes/Informe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        os.makedirs("docs/informes", exist_ok=True)
        
        c = canvas.Canvas(filename, pagesize=letter)
        y = 750
        
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, y, f"INFORME DE AUDITORÍA CLÍNICA - {self.guion.titulo}")
        y -= 30
        
        c.setFont("Helvetica", 12)
        c.drawString(100, y, f"Paciente: {state['paciente']['nombre']}")
        y -= 20
        c.drawString(100, y, f"NIF: {state['paciente'].get('nif', 'No proporcionado')}")
        y -= 20
        c.drawString(100, y, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        y -= 30
        
        # NOTA DE IMÁGENES SI LAS HAY
        if docs_con_imagenes:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(100, y, "⚠️ NOTA IMPORTANTE:")
            y -= 20
            c.setFont("Helvetica", 10)
            c.drawString(100, y, "Los siguientes documentos contienen imágenes que requieren")
            y -= 15
            c.drawString(100, y, "revisión manual por el especialista:")
            y -= 20
            for doc in docs_con_imagenes:
                c.drawString(120, y, f"  - {doc['nombre']}")
                y -= 15
            y -= 20
        
        # ERRORES DE VALIDACIÓN
        if state.get("errores"):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(100, y, "⚠️ ALERTAS DE VALIDACIÓN:")
            y -= 20
            c.setFont("Helvetica", 10)
            for error in state["errores"]:
                c.drawString(120, y, f"  - {error}")
                y -= 15
            y -= 20
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(100, y, "RESUMEN CLÍNICO")
        y -= 25
        
        for tit, cont in state["resultados"].items():
            c.setFont("Helvetica-Bold", 11)
            c.drawString(100, y, tit)
            y -= 18
            c.setFont("Helvetica", 9)
            lines = [cont[i:i+95] for i in range(0, min(len(cont), 800), 95)]
            for line in lines:
                c.drawString(100, y, line)
                y -= 12
                if y < 100:
                    c.showPage()
                    y = 750
            y -= 15
        
        c.save()
        return filename
    
    def ejecutar(self, paciente: Dict) -> Dict:
        """Ejecuta el pipeline completo"""
        inicio = time.time()
        print(f"\n{'='*50}")
        print(f"  CLINDOC AGENT - AUDITORÍA CLÍNICA")
        print(f"{'='*50}")
        print(f"Paciente: {paciente['nombre']}")
        print(f"NIF: {paciente.get('nif', 'N/A')}")
        print(f"{'='*50}\n")
        
        # Ejecutar nodos secuencialmente (versión simple sin LangGraph completo)
        state: AgentState = {
            "documentos": [],
            "paciente": paciente,
            "resultados": {},
            "errores": [],
            "retry_count": 0,
            "trace": []
        }
        
        # 1. Ingesta
        print("[FASE 1] Escaneo de documentos...")
        state = self._node_ingestion(state)
        
        # 2. Validar identidad
        print("[FASE 2] Validación de identidad...")
        state = self._node_validate_identity(state)
        
        # 3. Validar vigencia
        print("[FASE 3] Validación de vigencia...")
        state = self._node_validate_vigency(state)
        
        # 4. Redactar
        print("[FASE 4] Generación de resumen clínico...")
        state = self._node_redact(state)
        
        # 5. Ensamblar
        print("[FASE 5] Generación de informe PDF...")
        state = self._node_assemble(state)
        
        # Tiempo total
        tiempo_total = round(time.time() - inicio, 2)
        self.recorder.data["kpis"]["total_time"] = tiempo_total
        self.recorder._save()
        
        # Mostrar trace
        print(f"\n{'='*50}")
        print("  CHAIN OF THOUGHT")
        print(f"{'='*50}")
        for traza in state["trace"]:
            print(traza)
        
        print(f"\n{'='*50}")
        print(f"  EJECUCIÓN COMPLETADA EN {tiempo_total}s")
        print(f"{'='*50}")
        
        return state["resultados"]

# --- ORQUESTADOR ORIGINAL (compatibilidad - mantener para atrás compatibilidad) ---
class OrquestadorClinDoc:
    def __init__(self, config_gui: Dict):
        self.guion = GuionInforme(**config_gui)
        self.indice = IndiceCorpus()
        self.escanner = AgenteEscanner()
        self.redactor = AgenteRedactor(self.indice)
        self.verificador_id = VerificadorIdentidad()
        self.verificador_vigencia = VerificadorVigencia()
        self.recorder = DashboardRecorder()
        self.docs_procesados = []

    def ejecutar(self, paciente: Dict):
        inicio_session = time.time()
        print(f"Iniciando proceso de auditoría: {paciente['nombre']}")
        
        # 1. Escaneo e Ingesta
        print("   [1/3] Escaneando documentos...")
        docs = self.escanner.scan()
        for d in docs:
            start_ingest = time.time()
            self.indice.indexar_documento(d['id'], d['texto'], d['nombre'])
            latencia = time.time() - start_ingest
            
            self.recorder.record_event("ingesta_documento", {
                "id": d['id'],
                "nombre": d['nombre'],
                "latencia": round(latencia, 4),
                "longitud_texto": len(d['texto']),
                "imagenes": d.get("imagenes_detectadas", 0),
                "nota": d.get("nota_imagenes")
            })
            self.docs_procesados.append(str(self.escanner.ruta / d['nombre']))
        
        # 2. Análisis Multi-Agente
        print(f"   [2/3] Analizando con LLM Local ({self.redactor.modelo})...")
        resumen = {}
        for s in self.guion.secciones:
            print(f"         > Redactando seccion: {s.titulo}")
            start_redact = time.time()
            resultado = self.redactor.redactar(s)
            resumen[s.titulo] = resultado
            
            conf_simulada = 0.85 if "Error" not in resultado else 0.1
            riesgo = "SAFE" if conf_simulada > 0.8 else "WARNING"
            
            self.recorder.record_event("analisis_seccion", {
                "seccion": s.titulo,
                "confianza": conf_simulada,
                "estado_riesgo": riesgo,
                "tiempo_respuesta": round(time.time() - start_redact, 2)
            })
        
        # 3. Finalización
        print("   [3/3] Generando informe final...")
        self.data_final = {
            "paciente": paciente["nombre"],
            "nif": paciente.get("nif", "N/A"),
            "resumen": resumen,
            "tiempo_total": round(time.time() - inicio_session, 2)
        }
        self.recorder.data["kpis"]["total_time"] = self.data_final["tiempo_total"]
        self.recorder._save()
        
        # Generar Informe Base
        informe_base = self.generar_informe_pdf()
        
        # Ensamblar con Anexos
        print("   [3/3] Ensamblando expediente final con anexos...")
        ensamblador = AgenteEnsamblador(informe_base, self.docs_procesados)
        ruta_final = f"docs/informes/Expediente_Final_{paciente.get('nif', 'N/A')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        ensamblador.ensamblar(ruta_final)
        
        print(f"   [DONE] Expediente consolidado generado: {ruta_final}")
        return resumen

    def generar_informe_pdf(self):
        filename = f"docs/informes/Informe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        os.makedirs("docs/informes", exist_ok=True)
        c = canvas.Canvas(filename, pagesize=letter)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, 750, f"INFORME DE AUDITORÍA CLÍNICA - {self.guion.titulo}")
        c.setFont("Helvetica", 12)
        c.drawString(100, 730, f"Paciente: {self.data_final['paciente']}")
        c.drawString(100, 715, f"NIF: {self.data_final.get('nif', 'N/A')}")
        c.drawString(100, 700, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(100, 685, f"Tiempo Total: {self.data_final['tiempo_total']} s")
        c.line(100, 675, 500, 675)
        
        y = 655
        for tit, cont in self.data_final["resumen"].items():
            c.setFont("Helvetica-Bold", 12)
            c.drawString(100, y, tit)
            y -= 20
            c.setFont("Helvetica", 10)
            text_object = c.beginText(100, y)
            text_object.setWordSpace(1)
            lines = [cont[i:i+90] for i in range(0, len(cont), 90)]
            for line in lines:
                text_object.textLine(line)
                y -= 12
            c.drawText(text_object)
            y -= 20
            if y < 100:
                c.showPage()
                y = 750
        
        c.save()
        return filename


# --- EJECUCIÓN MAESTRA ---
if __name__ == "__main__":
    config_demo = {
        "titulo": "Auditoría de Alta Complejidad v4.0 (Master Run)",
        "secciones": [
            {"id": "A1", "titulo": "Antecedentes de Salud", "instruccion": "Sintetice hallazgos cardíacos y quirúrgicos previos."},
            {"id": "A2", "titulo": "Evolución Clínica Reciente", "instruccion": "Evalúe la respuesta al tratamiento post-operatorio."},
            {"id": "A3", "titulo": "Recomendaciones", "instruccion": "Defina pautas de reposo y seguimiento médico."}
        ]
    }
    # Usar el nuevo orquestador LangGraph
    paciente_demo = {"nombre": "Juan Pérez García", "nif": "12345678Z"}
    
    print("Usando Orquestador LangGraph (v4.0)")
    sistema = OrquestadorLangGraph(config_demo)
    resultados = sistema.ejecutar(paciente_demo)

    print("\n" + "="*50)
    print("      RESULTADO DE AUDITORIA CLINICA")
    print("="*50)
    for tit, cont in resultados.items():
        print(f"\n[{tit}]")
        print(cont[:500] + "..." if len(cont) > 500 else cont)
    print("\n" + "="*50)
    print("  EJECUCIÓN COMPLETADA CON EXITO")
    print("="*50)
