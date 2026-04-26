import sys
import os
import re
import yaml
import uuid
import time
import ollama
import qdrant_client
from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from pathlib import Path
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from qdrant_client.http import models
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import json
from datetime import datetime
import pypdf

# Forzar salida en UTF-8 para evitar errores de codificación en consola Windows
if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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


# --- MODELOS DE DATOS (Pydantic) ---
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

# --- MOTOR SEMÁNTICO (Qdrant) ---
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

    def indexar_documento(self, doc_id: str, texto: str, nombre_original: str):
        fragmentos = [texto[i:i+1000] for i in range(0, len(texto), 800)]
        points = []
        for i, frag in enumerate(fragmentos):
            vector = self.modelo_emb.encode(frag).tolist()
            points.append(models.PointStruct(
                id=str(uuid.uuid4()), 
                vector=vector, 
                payload={"texto": frag, "nombre_archivo": nombre_original, "doc_id": doc_id}
            ))
        self.cliente.upsert(collection_name=self.nombre_coleccion, points=points)

    def buscar_evidencias(self, consulta: str, n: int = 3) -> List[Dict]:
        vector = self.modelo_emb.encode(consulta).tolist()
        res = self.cliente.query_points(collection_name=self.nombre_coleccion, query=vector, limit=n).points
        return [{"texto": r.payload["texto"], "archivo": r.payload["nombre_archivo"]} for r in res]

# --- AGENTES ---
class AgenteEscanner:
    def __init__(self, ruta: str = "datos/expedientes_sinteticos"):
        self.ruta = Path(ruta)
        if not self.ruta.exists():
            self.ruta.mkdir(parents=True, exist_ok=True)

    def scan(self) -> List[Dict]:
        if not list(self.ruta.glob("*")):
            test_file = self.ruta / "paciente_juan.txt"
            test_file.write_text("Hallazgos clínicos en paciente Juan Pérez García: El paciente presenta una evolución favorable tras cirugía cardiovascular. Se recomienda reposo por 15 días.", encoding='utf-8')

        documentos = []
        for f in self.ruta.glob("*"):
            documentos.append({
                "id": f.stem, "nombre": f.name, 
                "texto": f.read_text(encoding='utf-8')
            })
        return documentos

class VerificadorIdentidad:
    def validar(self, nombre_ref, nombre_doc):
        ref = re.sub(r'[^a-zA-Z]', '', nombre_ref).lower()
        doc = re.sub(r'[^a-zA-Z]', '', nombre_doc).lower()
        return ref in doc or doc in ref

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
            # Tomamos la última fecha mencionada como la más relevante (ej: fecha de fin o firma)
            fecha_doc_str = fechas[-1].replace('-', '/')
            partes = fecha_doc_str.split('/')
            if len(partes[2]) == 2: partes[2] = "20" + partes[2] # Arreglar años de 2 dígitos
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
        evidencias = self.indice.buscar_evidencias(seccion.titulo)
        contexto = "\n".join([f"- {e['texto']} (Ref: {e['archivo']})" for e in evidencias])
        
        prompt = f"Eres un auditor clínico profesional. Redacta la sección '{seccion.titulo}'. Instrucción: {seccion.instruccion}. Datos: {contexto}. Responde de forma técnica y concisa en español."
        
        try:
            r = ollama.chat(model=self.modelo, messages=[{'role': 'user', 'content': prompt}])
            return r['message']['content']
        except Exception as e:
            return f"Error en IA local: {str(e)}"

# --- ORQUESTADOR ---
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
            
            # Log Analytics: "Injesta Agresiva" metadata
            self.recorder.record_event("ingesta_documento", {
                "id": d['id'],
                "nombre": d['nombre'],
                "latencia": round(latencia, 4),
                "longitud_texto": len(d['texto'])
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
            
            # Simulamos cálculo de riesgo y confianza (en versión real vendría del LLM)
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
            "resumen": resumen,
            "tiempo_total": round(time.time() - inicio_session, 2)
        }
        self.recorder.data["kpis"]["total_time"] = self.data_final["tiempo_total"]
        self.recorder._save()
        
        # Generar Informe Base
        informe_base = self.generar_informe_pdf()
        
        # Ensamblar con Anexos (OE7)
        print("   [3/3] Ensamblando expediente final con anexos...")
        ensamblador = AgenteEnsamblador(informe_base, self.docs_procesados)
        ruta_final = f"docs/informes/Expediente_Final_{paciente['nif']}_{datetime.now().strftime('%Y%m%d')}.pdf"
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
        c.drawString(100, 715, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(100, 700, f"Tiempo Total: {self.data_final['tiempo_total']} s")
        c.line(100, 690, 500, 690)
        
        y = 670
        for tit, cont in self.data_final["resumen"].items():
            c.setFont("Helvetica-Bold", 12)
            c.drawString(100, y, tit)
            y -= 20
            c.setFont("Helvetica", 10)
            text_object = c.beginText(100, y)
            text_object.setWordSpace(1)
            # Simple wrapping logic
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
        "titulo": "Auditoría de Alta Complejidad v3.0 (Master Run)",
        "secciones": [
            {"id": "A1", "titulo": "Antecedentes de Salud", "instruccion": "Sintetice hallazgos cardíacos y quirúrgicos previos."},
            {"id": "A2", "titulo": "Evolución Clínica Reciente", "instruccion": "Evalúe la respuesta al tratamiento post-operatorio."},
            {"id": "A3", "titulo": "Recomendaciones", "instruccion": "Defina pautas de reposo y seguimiento médico."}
        ]
    }
    paciente_demo = {"nombre": "Juan Pérez García", "nif": "12345678X"}

    sistema = OrquestadorClinDoc(config_demo)
    resultados = sistema.ejecutar(paciente_demo)

    print("\n" + "="*40)
    print("      RESULTADO DE AUDITORIA CLINICA")
    print("="*40)
    for tit, cont in resultados.items():
        print(f"\nSeccion: {tit}:\n{cont}")
    print("\n" + "="*40)
    print("  EJECUCIÓN COMPLETADA CON EXITO")
    print("="*40)
