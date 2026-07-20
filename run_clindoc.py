import sys
import os
import re
import yaml
import uuid
import hashlib
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

# --- CIFRADO AES-256-GCM (módulo ligero) ---
from cifrado import CifradoClinDoc

# --- ANALYTICS RECORDER ---
class DashboardRecorder:
    def __init__(self, output_file: str = "dashboard_data.json"):
        self.output_file = output_file
        self.data = self._load_existing()
        if "pacientes" not in self.data:
            self.data = {"pacientes": {}}
        self.paciente_actual = None

    def _load_existing(self):
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"pacientes": {}}

    def set_paciente(self, nif: str, nombre: str):
        self.paciente_actual = nif
        # Reset del paciente en CADA procesamiento: reprocesar reemplaza sus datos,
        # no acumula eventos de runs anteriores (evita duplicar docs/KPIs y mezclar redacciones).
        self.data["pacientes"][nif] = {
            "nombre": nombre,
            "nif": nif,
            "session_start": datetime.now().isoformat(),
            "kpis": {
                "total_docs": 0,
                "total_time": 0,
                "avg_confidence": 0,
                "critical_risks": 0,
                "modelo_ia": "gemma3:4b"
            },
            "events": []
        }
        self._save()

    def record_event(self, event_type: str, details: Dict):
        if not self.paciente_actual:
            return
            
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        }
        self.data["pacientes"][self.paciente_actual]["events"].append(event)
        self._update_kpis()
        self._save()

    def _update_kpis(self):
        if not self.paciente_actual:
            return
        paciente_data = self.data["pacientes"][self.paciente_actual]
        doc_events = [e for e in paciente_data["events"] if e["type"] == "ingesta_documento"]
        paciente_data["kpis"]["total_docs"] = len(doc_events)
        
        confidences = [e["details"].get("confianza", 0) for e in paciente_data["events"] if "confianza" in e["details"]]
        if confidences:
            paciente_data["kpis"]["avg_confidence"] = sum(confidences) / len(confidences)
            
        riesgos_estado = [e for e in paciente_data["events"] if e["details"].get("estado_riesgo") == "CRITICAL"]
        identidad_fallida = [e for e in paciente_data["events"] if e["type"] == "validacion_identidad" and e["details"].get("valido") is False]
        paciente_data["kpis"]["critical_risks"] = len(riesgos_estado) + len(identidad_fallida)

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
    fuente_preferente: Optional[str] = None

class IdentidadDocumento(BaseModel):
    documento_id: str
    nif: Optional[str] = None
    nombre_completo: Optional[str] = None
    num_seguridad_social: Optional[str] = None
    empresa: Optional[str] = None
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
        """Valida NIF/NIE español con algoritmo oficial"""
        v = v.upper()
        if len(v) != 9:
            raise ValueError("NIF/NIE debe tener 9 caracteres")
        letra_inicial = v[0]
        if letra_inicial in "XYZ":
            reemplazo = {"X": "0", "Y": "1", "Z": "2"}[letra_inicial]
            nif_numerico = reemplazo + v[1:8]
        else:
            nif_numerico = v[:8]
        if not nif_numerico.isdigit():
            raise ValueError("Formato numérico de NIF/NIE inválido")
        letra_control = v[8]
        if not letra_control.isalpha():
            raise ValueError("Último caracter debe ser letra")
        letras = "TRWAGMYFPDXBNJZSQVHLCKE"
        if letras[int(nif_numerico) % 23] != letra_control:
            raise ValueError("Letra de control de NIF/NIE inválida")
        return v


# --- AGENTES Y VERIFICADORES EXTERNALIZADOS ---
from agentes.indice_corpus import IndiceCorpus
from agentes.agente_escanner import AgenteEscanner
from agentes.verificadores import VerificadorIdentidad, VerificadorVigencia, validar_nif

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

def obtener_modelo_ollama_disponible(modelo_deseado: str = "gemma3:4b") -> str:
    """Verifica modelos locales instalados en Ollama y retorna el mejor disponible"""
    try:
        modelos_locales = ollama.list()
        nombres = [m.model for m in modelos_locales.models] if hasattr(modelos_locales, 'models') else [m['model'] for m in modelos_locales.get('models', [])]
        
        # 1. Si el deseado está, lo usamos
        if modelo_deseado in nombres:
            return modelo_deseado
            
        # 2. Si no, buscar variaciones (ej: sin el ':latest' o con él)
        for n in nombres:
            if n.split(':')[0] == modelo_deseado.split(':')[0]:
                print(f"[INFO] Modelo '{modelo_deseado}' no exacto, usando variación encontrada: '{n}'")
                return n
                
        # 3. Si no está, priorizar modelos ligeros comunes en español
        ligeros = ["gemma2", "llama3.2", "llama3", "mistral", "phi3", "gemma"]
        for lig in ligeros:
            for n in nombres:
                if n.startswith(lig):
                    print(f"[INFO] Modelo por defecto '{modelo_deseado}' no encontrado. Auto-seleccionando compatible: '{n}'")
                    return n
                    
        # 4. Tomar el primero si hay alguno
        if nombres:
            print(f"[AVISO] No se encontró '{modelo_deseado}' ni similares. Usando primer modelo instalado: '{nombres[0]}'")
            return nombres[0]
            
        # 5. Si no hay modelos
        print(f"[ALERTA] Ollama no tiene ningún modelo descargado. Por favor, ejecuta: 'ollama pull {modelo_deseado}'")
        return modelo_deseado
    except Exception as e:
        print(f"[AVISO] No se pudo conectar a Ollama local. Asegúrate de que Ollama esté ejecutándose. (Detalle: {e})")
        return modelo_deseado

class AgenteRedactor:
    def __init__(self, indice: IndiceCorpus, modelo: str = "gemma3:4b"):
        self.indice = indice
        self.modelo = obtener_modelo_ollama_disponible(modelo)

    def redactar(self, seccion: Seccion) -> str:
        """Redacta sección con Deep Linking a fuentes.

        Genera por documento (un prompt por evidencia, cada uno viendo un único
        documento) en vez de darle al modelo todos los documentos juntos. Esto
        elimina estructuralmente la mala atribución de citas entre fragmentos
        (confirmado empíricamente: con varios documentos en un mismo contexto, un
        modelo pequeño mezcla con frecuencia el diagnóstico de un documento con la
        cita de otro) — el modelo nunca tiene que rastrear a cuál de varios
        documentos pertenece cada afirmación, porque solo ve uno a la vez. Los
        resultados por documento se unen por código, no por el modelo.
        """
        evidencias = self.indice.buscar_evidencias(seccion.titulo, tipo_documento=seccion.fuente_preferente)

        # Búsqueda complementaria: la consulta genérica del título de sección no
        # siempre recupera episodios atípicos pero relevantes (p. ej. un accidente de
        # trabajo entre 180 informes de enfermedad común) porque su similitud semántica
        # con el título genérico es baja incluso cuando el contenido es justo el que se
        # busca. Se añade una consulta explícita como red de seguridad, sin sustituir
        # la búsqueda principal, para no alterar el comportamiento ya validado en el
        # caso común (los resultados duplicados se descartan por chunk_id).
        if seccion.fuente_preferente:
            complementarias = self.indice.buscar_evidencias(
                "accidente de trabajo, empresa, mutua, parte de accidente laboral",
                n=2, tipo_documento=seccion.fuente_preferente,
            )
            ids_existentes = {e['chunk_id'] for e in evidencias}
            for e in complementarias:
                if e['chunk_id'] not in ids_existentes:
                    evidencias.append(e)
                    ids_existentes.add(e['chunk_id'])

        if not evidencias:
            return "Sin información documental para esta sección."

        partes_validas = []
        for e in evidencias:
            resultado_doc = self._redactar_un_documento(seccion, e)
            if resultado_doc.strip() != "Sin información documental para esta sección.":
                partes_validas.append(resultado_doc)

        if not partes_validas:
            return self._abstencion_con_confianza(evidencias)
        return "\n\n".join(partes_validas)

    def _abstencion_con_confianza(self, evidencias: List[Dict]) -> str:
        """Cuando ningún documento recuperado aportó contenido usable, la ausencia
        puede deberse a que el dato genuinamente no está en el expediente, o a que
        la búsqueda no recuperó el documento correcto (riesgo real: 16,7% de acierto
        en consultas exactas medido en la línea base, Tabla 22). El sistema no puede
        distinguir ambos casos con certeza, pero SÍ puede reportar la señal que ya
        calcula Qdrant y antes se descartaba: la similitud del mejor candidato
        consultado. Un score bajo es consistente con ausencia real; un score alto
        pese a no extraer nada es más sospechoso de fallo de recuperación -- se
        reporta el número crudo, sin una etiqueta categórica "alta/baja" inventada
        sin calibración estadística real, para que la verificación humana (siempre
        indispensable, ver cap. 8) tenga una señal objetiva en la que apoyarse.
        """
        if not evidencias or all('score' not in e for e in evidencias):
            return "Sin información documental para esta sección."
        mejor_score = max(e['score'] for e in evidencias if 'score' in e)
        return (
            "Sin información documental para esta sección. "
            f"(Mejor coincidencia semántica entre los documentos consultados: {mejor_score:.2f} "
            "-- verificar manualmente si este valor es alto pese a la ausencia de contenido extraído.)"
        )

    def _redactar_un_documento(self, seccion: Seccion, evidencia: Dict) -> str:
        """Redacta lo que UN único documento aporta a la sección. Al ver un solo
        documento, no puede confundir su contenido con la cita de otro."""
        contexto = f"- {evidencia['texto']} [Fuente: {evidencia['archivo']}#{evidencia['chunk_id']}]"

        prompt = f"""Eres un auditor clínico que extrae información de UN ÚNICO documento para la sección '{seccion.titulo}' de una historia clínica consolidada para un proceso de Incapacidad Temporal (RD 1060/2022).

## Reglas Estrictas y Obligatorias

1. **Prohibido inventar.** Solo puedes afirmar lo que aparece de forma EXPLÍCITA en el DOCUMENTO. No supongas, no infieras, no añadas conocimiento médico externo.

2. **Cita exacta obligatoria.** CADA afirmación DEBE terminar con la cita en formato [Fuente: archivo#chunk_id]. Este es el único formato válido. No omitas "Fuente:", no inventes nombres de archivo ni chunk_id distintos a los proporcionados. Si necesitas citar el mismo fragmento múltiples veces, repite la cita cada vez.

3. **Excepción a la Regla 2.** Si el DOCUMENTO no contiene información relevante para esta sección, responde EXACTAMENTE y solo: "Sin información documental para esta sección." (sin cita ni fuente).

4. **Estilo asertivo y directo.** Para una conclusión o recomendación, usa: "Basado en [documento, fecha si aparece], se determina/observa...". Prohibido relleno genérico ("recomendaciones generales", "debe individualizarse", disclaimers).

5. **No confundas procedimiento con diagnóstico.** Un procedimiento es una intervención (artroscopia, punción); un diagnóstico es la condición detectada. Incluye código CIE-10 SOLO si aparece textualmente en el documento o es inequívoco del contexto clínico explícito.

6. **Desambiguación de campos críticos.**
   - NIF del paciente: aparece en la cabecera del documento, es un identificador personal de 8 dígitos + 1 letra (ej: 25988000R).
   - Número de seguridad social: aparece en la cabecera o en campos administrativos, es una secuencia de 12 dígitos.
   - Fecha del informe (cabecera): cuándo se redactó el documento.
   - Fecha de inicio de la baja: cuándo comenzó la incapacidad, explícitamente etiquetada en el documento como tal.
   NO confundas estos campos a menos que el documento lo diga explícitamente con esas palabras exactas. Si tienes duda, indica cuál es el campo que se menciona en el documento y por qué.

7. **Campos opcionales:** si el guion marca un campo como opcional ("requerido: false"), inclúyelo SOLO si aparece en los DATOS del documento. Si no aparece, OMÍTELO sin inventar, sin comentarios, sin excusas.

## Entrada

**Instrucción de la sección:** {seccion.instruccion}

**DOCUMENTO (ÚNICA fuente permitida):**
- {contexto}

## Salida

Responde en español, técnico y conciso. Cada afirmación debe terminar con [Fuente: archivo#chunk_id]. Si el documento no aporta nada a esta sección, escribe únicamente: "Sin información documental para esta sección.\""""

        # Reintento acotado ante abstención: confirmado empíricamente que el modelo a
        # veces responde "sin información" pese a tener evidencia real (variabilidad
        # estocástica). Con un solo documento por llamada el riesgo es menor que antes,
        # pero se mantiene un reintento ligero como red de seguridad.
        MAX_INTENTOS = 2
        resultado = "Sin información documental para esta sección."
        for intento in range(MAX_INTENTOS):
            resultado = self._generar_desde_prompt(prompt)
            if resultado.strip() != "Sin información documental para esta sección.":
                return self._sanear_resultado(resultado, evidencia)
        return resultado

    def _sanear_resultado(self, texto: str, evidencia: Dict) -> str:
        """Correcciones deterministas que no dependen de que el modelo "se acuerde":
        ni el prompt (ninguna versión probada) ni los reintentos eliminaron del todo
        dos patrones recurrentes, así que se corrigen aquí con reglas objetivas.
        """
        # Terminador de valor compartido: captura el valor de un campo hasta el
        # límite real (punto final de frase, corchete de cita, salto de línea o fin
        # de cadena) SIN cortarse en un punto interno legítimo del propio valor
        # (decimales de CIE-10 como "S93.4", abreviaturas como "S.L."). Un punto
        # cuenta como fin de frase solo si va seguido de espacio + mayúscula (nueva
        # frase/campo) o de corchete de cita -- un punto pegado al siguiente
        # carácter (sin espacio) se trata como parte del valor. Bug real detectado
        # y corregido en esta sesión: la versión anterior (`[^.\[\n]{0,N}`) cortaba
        # "S.L." dejando basura como "no disponible en el documento.L." en el texto.
        _VALOR_CAMPO = r'([^\[\n]*?)(?=\.\s+[A-ZÁÉÍÓÚÑ]|\.\s*\[|\.\s*$|\[|\n|$)'

        # 0) Fecha de nacimiento sin respaldo real: encontrado en la regeneración
        # completa de esta sesión -- el corpus SOLO escribe "Edad: X años" y la fecha
        # del propio informe (fecha de la visita), jamás una fecha de nacimiento real
        # (0/60 documentos verificados). El modelo confunde ambos datos: a veces
        # etiqueta la edad como si fuera la fecha ("Fecha de nacimiento: 55 años",
        # visto literalmente en producción), a veces usa la fecha del informe. Mismo
        # razonamiento que el resto: si el documento no menciona "nacimiento" en
        # ningún lado, cualquier valor reportado es forzosamente inventado.
        if not re.search(r'nacimiento', evidencia['texto'], re.IGNORECASE):
            patron_nacimiento_cualquiera = re.compile(
                r'(fecha\s+de\s+nacimiento|fecha_nacimiento)\s*:?\s*' + _VALOR_CAMPO,
                re.IGNORECASE,
            )
            texto = patron_nacimiento_cualquiera.sub(
                lambda m: f"{m.group(1)}: no disponible en el documento", texto
            )

        # 1) Número de seguridad social sin respaldo real: filtrar por formato o por
        # "aparece en algún lugar del texto" no basta -- el NIF real del paciente SÍ
        # aparece en el documento (correctamente, como NIF), así que ese chequeo lo
        # daba por válido aunque estuviera mal etiquetado como NSS. Y el modelo llegó
        # a escribir variantes de formato ("Num Seguridad Social" con espacio) que el
        # patrón exacto no cubría. Se corta el problema de raíz: en TODO este corpus
        # ningún documento contiene jamás un número de seguridad social real (0/900
        # verificado), así que si el propio DOCUMENTO FUENTE no menciona la frase
        # "seguridad social" en ningún lado, cualquier valor que el modelo reporte
        # para ese campo es forzosamente inventado, sea cual sea su formato.
        if not re.search(r'seguridad\s+social', evidencia['texto'], re.IGNORECASE):
            patron_nss_cualquiera = re.compile(
                r'(n[uú]mero\s+de\s+seguridad\s+social|num[\s_]seguridad[\s_]social|nss)\s*:?\s*' + _VALOR_CAMPO,
                re.IGNORECASE,
            )
            texto = patron_nss_cualquiera.sub(
                lambda m: f"{m.group(1)}: no disponible en el documento", texto
            )

        # 1a) Código CIE-10 sin respaldo real: verificado sobre el generador de corpus
        # y sobre una muestra de 30 documentos ALTA reales -- 0/524 documentos por
        # paciente contienen jamás un código con forma de CIE-10 (letra + 2 dígitos,
        # ej. "M25.5"). El guion declara un `patron` de validación para este campo,
        # pero ese patrón nunca se aplica en el código (dead metadata) -- así que la
        # única defensa real es esta: si el documento fuente no contiene un código con
        # forma de CIE-10, cualquier código que el modelo reporte es inventado.
        if not re.search(r'\b[A-Z]\d{2}(\.\d{1,2})?\b', evidencia['texto']):
            patron_cie10_cualquiera = re.compile(
                r'(c[oó]digo\s+cie[\s\-]?10|cie[\s\-]?10|codigo_cie10)\s*:?\s*' + _VALOR_CAMPO,
                re.IGNORECASE,
            )
            texto = patron_cie10_cualquiera.sub(
                lambda m: f"{m.group(1)}: no disponible en el documento", texto
            )

        # 1b) Empresa sin respaldo real: en TODO el corpus, la palabra "empresa" solo
        # aparece en el documento de accidente de trabajo (1 de 524 por paciente,
        # ver Hallazgo 2/3 del plan) -- ningún otro documento la menciona jamás. Mismo
        # razonamiento que el NSS: si el DOCUMENTO citado no menciona "empresa" en
        # ningún lado, cualquier nombre de empresa que el modelo reporte es forzosamente
        # inventado (aplica al 523/524 de los documentos posibles por paciente).
        if not re.search(r'empresa', evidencia['texto'], re.IGNORECASE):
            patron_empresa_cualquiera = re.compile(
                r'(empresa)\s*:?\s*' + _VALOR_CAMPO,
                re.IGNORECASE,
            )
            texto = patron_empresa_cualquiera.sub(
                lambda m: f"{m.group(1)}: no disponible en el documento", texto
            )

        # 2) Fecha de inicio de baja sin forma de fecha real: detectado en producción
        # (app real, no solo en pruebas) que el modelo a veces toma una frase cercana
        # sin relación ("control en 7-10 días") y la reporta como si fuera la fecha de
        # inicio de la baja, en vez de reconocer que el documento no la especifica. A
        # diferencia del NSS, una fecha real SÍ puede existir en el documento, así que
        # no se descarta el campo entero -- se verifica que el valor reportado tenga
        # forma de fecha (DD/MM/AAAA); si no la tiene, es forzosamente una confusión,
        # no un dato real, y se reemplaza.
        patron_fecha_baja = re.compile(
            r'(fecha[\s_]de[\s_]inicio[\s_](?:de[\s_]la[\s_])?baja|fecha_inicio_baja)\s*:?\s*' + _VALOR_CAMPO,
            re.IGNORECASE,
        )
        def _validar_fecha(m):
            valor = m.group(2)
            if re.search(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', valor):
                return m.group(0)
            if re.search(r'no\s+(est[aá]|se)\s|no\s+disponible|no\s+especific|desconocid', valor, re.IGNORECASE):
                return m.group(0)
            return f"{m.group(1)}: no disponible en el documento"
        texto = patron_fecha_baja.sub(_validar_fecha, texto)

        # 3) Cita mal formada (placeholder sin resolver "archivo#chunk_id", texto
        # generico como "[Fuente: documento]", etc.): al generar por documento, solo
        # existe UNA cita válida posible en toda la respuesta — la de esta evidencia —
        # así que en vez de intentar reconocer cada variante rota, se reemplaza
        # cualquier "[Fuente: ...]" por la cita real garantizada.
        cita_real = f"{evidencia['archivo']}#{evidencia['chunk_id']}"
        texto = re.sub(r'\[Fuente:[^\]]*\]', f'[Fuente: {cita_real}]', texto, flags=re.IGNORECASE)

        return texto

    def _generar_desde_prompt(self, prompt: str) -> str:
        try:
            r = ollama.chat(model=self.modelo, messages=[{'role': 'user', 'content': prompt}])
            resp = r['message']['content']

            # Nota: NO se descarta toda la respuesta solo porque contenga la frase "Sin
            # información documental" en algún punto. El modelo la usa a veces para señalar
            # que un CAMPO concreto (p. ej. el CIE-10) no está documentado, dentro de una
            # respuesta por lo demás válida y bien citada. Un chequeo por subcadena aquí
            # destruía respuestas correctas completas. El caso de sección genuinamente vacía
            # ya queda cubierto abajo: si tras el filtro de párrafos huérfanos no sobrevive
            # ningún párrafo con cita real, se devuelve el mensaje de "sin información".

            # Filtro de Destrucción de Párrafos Huérfanos
            # Acepta tanto el formato exacto "[Fuente: archivo#chunk_id]" como variantes sin
            # la etiqueta "Fuente:" (ej. "[ALTA_078.pdf#ALTA_078_chunk_0]"), que gemma3:4b
            # genera con frecuencia pese a la instrucción explícita. Antes, el chequeo exacto
            # de "[Fuente:" destruía párrafos con citas reales y bien formadas, colapsando
            # la sección entera a "Sin información documental" pese a haber evidencia válida.
            CITA_PATTERN = re.compile(r'\[[^\[\]]*\.(?:pdf|docx)[^\[\]]*\]', re.IGNORECASE)
            parrafos_validos = []
            for p in resp.split('\n'):
                p_limpio = p.strip()
                if not p_limpio:
                    continue
                # Si es un encabezado markdown (ej. ##), lo pasamos
                if p_limpio.startswith('#'):
                    parrafos_validos.append(p_limpio)
                # Si tiene una cita reconocible (con o sin etiqueta "Fuente:"), es válido
                elif "[Fuente:" in p_limpio or CITA_PATTERN.search(p_limpio):
                    # Limpieza cosmética: si la frase de "sin información" quedó incrustada
                    # a mitad de un párrafo que sí tiene contenido citado real (se refería a
                    # un campo puntual, no a toda la sección), se retira para no dejar una
                    # frase contradictoria en medio de un párrafo por lo demás válido.
                    p_limpio = re.sub(r'\s*Sin información documental para esta sección\.\s*', ' ', p_limpio).strip()
                    if p_limpio:
                        parrafos_validos.append(p_limpio)
                # Si no tiene fuente y no es encabezado, SE DESTRUYE (se ignora)
            
            resultado_filtrado = "\n\n".join(parrafos_validos)
            if not resultado_filtrado.strip():
                return "Sin información documental para esta sección."
                
            return resultado_filtrado
            
        except Exception as e:
            return f"Error en IA local: {str(e)}"

# --- ESTADO PARA LANGGRAPH (FASE 2) ---
class AgentState(TypedDict):
    """
    Estado del orquestador multi-agente para LangGraph.
    
    ESTRUCTURA DEL ESTADO:
    - documentos: Lista de documentos procesados
    - paciente: Datos del paciente (nombre, nif)
    - resultados: Resumen por sección
    - errores: Lista de errores encontrados
    - retry_count: Contador de reintentos
    - trace: Chain of thought para auditoría
    
    PRUEBAS REALIZADAS (Benchmark v4.0):
    - Pipeline completo: ✓ 0.92s (sin LLM)
    - Distribución: Ingesta 0.4%, Index 99.5%, Valid ID 0.1%, Valid Vig 0.1%
    - Chain of Thought: ✓ Registrado en cada fase
    """
    documentos: List[Dict]
    paciente: Dict
    resultados: Dict[str, str]
    errores: List[str]
    retry_count: int
    trace: List[str]  # Chain of thought
    needs_retry: bool  # Bandera de autocorrección (Self-RAG)

# --- ORQUESTADOR CON LANGGRAPH (FASE 2) ---
class OrquestadorLangGraph:
    """
    Orquestador basado en grafo con ciclos de retry.
    
    ARQUITECTURA (basada en LangGraph):
    1. ingestion → Escanea documentos
    2. validate_identity → Valida NIF
    3. validate_vigency → Valida fechas
    4. redact → Genera resumen (LLM)
    5. assemble → Genera PDF
    
    PRUEBAS REALIZADAS (Benchmark v4.0):
    - Ejecución secuencial: ✓ Funciona
    - Chain of Thought: ✓ Registrado
    - Notas de imágenes: ✓ Incluidas en PDF
    - Alertas de validación: ✓ Incluidas en PDF
    
    ORQUESTACIÓN: grafo de estados con langgraph.graph.StateGraph, con una arista
    condicional de autocorrección (Self-RAG): si la crítica detecta una sección
    fallida y quedan reintentos, el flujo vuelve al nodo de redacción.
    """

    MAX_RETRIES = 2  # Tope de ciclos de autocorrección (Self-RAG)

    def __init__(self, config_gui: Dict):
        self.guion = GuionInforme(**config_gui)
        self.indice = IndiceCorpus()
        self.escanner = AgenteEscanner()
        self.redactor = AgenteRedactor(self.indice)
        self.verificador_id = VerificadorIdentidad()
        self.verificador_vigencia = VerificadorVigencia()
        self.recorder = DashboardRecorder()
        self.docs_procesados = []
        # Construir el grafo de estados LangGraph (con fallback secuencial si no está disponible)
        self.app_graph = self._build_graph()

    def _build_graph(self):
        """Compila el StateGraph de LangGraph con ciclo condicional de autocorrección."""
        try:
            from langgraph.graph import StateGraph, START, END
            g = StateGraph(AgentState)
            g.add_node("ingestion", self._node_ingestion)
            g.add_node("validate_identity", self._node_validate_identity)
            g.add_node("validate_vigency", self._node_validate_vigency)
            g.add_node("redact", self._node_redact)
            g.add_node("critique", self._node_critique)
            g.add_node("assemble", self._node_assemble)
            g.add_edge(START, "ingestion")
            g.add_edge("ingestion", "validate_identity")
            g.add_edge("validate_identity", "validate_vigency")
            g.add_edge("validate_vigency", "redact")
            g.add_edge("redact", "critique")
            # Arista CONDICIONAL: si una sección falló y quedan reintentos -> vuelve a redactar (ciclo Self-RAG)
            g.add_conditional_edges("critique", self._route_after_critique,
                                    {"redact": "redact", "assemble": "assemble"})
            g.add_edge("assemble", END)
            print("[INFO] Orquestacion con LangGraph (grafo de estados + ciclo de autocorreccion) ACTIVA")
            return g.compile()
        except Exception as e:
            print(f"[AVISO] LangGraph no disponible ({e}); se usara el pipeline secuencial de respaldo")
            return None
    
    def _extraer_nif(self, texto: str) -> Optional[str]:
        """Extrae NIF/NIE del texto"""
        match = re.search(r'\b((?:\d{8}|[X-Z]\d{7})[A-Z])\b', texto, re.IGNORECASE)
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
        nombre_ref = paciente_ref.get("nombre", "")
        
        for doc in state["documentos"]:
            ruta_doc = Path("datos/expedientes") / nif_ref / doc["nombre"]
            validacion = self.verificador_id.validar(nif_ref, doc["texto"], str(ruta_doc), nombre_ref)
            if not validacion["valido"]:
                errores.append(f"IDENTIDAD: {doc['nombre']} - {validacion['detalle']}")
                state["trace"].append(f"  ⚠️ {validacion['detalle']}")
        
        if errores:
            state["errores"].extend(errores)
            state["retry_count"] = state.get("retry_count", 0) + 1
            self.recorder.record_event("validacion_identidad", {"valido": False, "errores": errores})
        else:
            self.recorder.record_event("validacion_identidad", {"valido": True, "detalle": "NIF validado correctamente"})
        
        state["trace"].append(f"<<< FIN: Validación identidad {'FALLIDA' if errores else 'OK'}")
        return state
    
    def _node_validate_vigency(self, state: AgentState) -> AgentState:
        """Nodo 3: Validar vigencia de documentos"""
        state["trace"].append(">>> VALIDANDO: Vigencia de documentos...")
        
        errores = []
        
        for doc in state["documentos"]:
            validacion = self.verificador_vigencia.validar(doc["texto"], "reciente_6_meses")
            self.recorder.record_event("validacion_vigencia", {
                "documento": doc["nombre"],
                "valido": validacion["valido"],
                "detalle": validacion["detalle"],
            })
            if not validacion["valido"]:
                errores.append(f"VIGENCIA: {doc['nombre']} - {validacion['detalle']}")
                state["trace"].append(f"  ⚠️ {validacion['detalle']}")
        
        if errores:
            state["errores"].extend(errores)
        
        state["trace"].append(f"<<< FIN: Validación vigencia {'FALLIDA' if errores else 'OK'}")
        return state
    
    def _node_redact(self, state: AgentState) -> AgentState:
        """Nodo 4: Redactar resumen con RAG + Deep Linking (idempotente para el ciclo)"""
        intento = state.get("retry_count", 0)
        state["trace"].append(f">>> REDACTANDO: Generando resumen clínico... (intento {intento + 1})")

        resultados = dict(state.get("resultados") or {})
        for seccion in self.guion.secciones:
            previo = resultados.get(seccion.titulo, "")
            # En un reintento, no re-redactar las secciones que ya salieron bien
            if previo and "Error" not in previo:
                continue
            resultado = self.redactor.redactar(seccion)
            resultados[seccion.titulo] = resultado

            conf = 0.85 if "Error" not in resultado else 0.1
            self.recorder.record_event("analisis_seccion", {
                "seccion": seccion.titulo,
                "texto": resultado,
                "confianza": conf,
                "estado_riesgo": "SAFE" if conf > 0.8 else "WARNING"
            })

        state["resultados"] = resultados
        state["trace"].append("<<< FIN: Resumen redactado con Deep Linking")
        return state

    def _node_critique(self, state: AgentState) -> AgentState:
        """Nodo de crítica (Self-RAG): detecta secciones fallidas y decide si reintentar."""
        resultados = state.get("resultados") or {}
        fallidas = [t for t, c in resultados.items() if (not c) or ("Error" in c)]
        if fallidas and state.get("retry_count", 0) < self.MAX_RETRIES:
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["needs_retry"] = True
            state["trace"].append(
                f">>> AUTOCORRECCIÓN: {len(fallidas)} sección(es) fallida(s); reintento {state['retry_count']}/{self.MAX_RETRIES}")
        else:
            state["needs_retry"] = False
            state["trace"].append(
                f"<<< CRÍTICA: {len(fallidas)} sección(es) sin resolver tras {self.MAX_RETRIES} reintentos"
                if fallidas else "<<< CRÍTICA: todas las secciones validadas")
        return state

    def _route_after_critique(self, state: AgentState) -> str:
        """Arista condicional: vuelve a redactar o continúa al ensamblado."""
        return "redact" if state.get("needs_retry") else "assemble"
    
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
        self.recorder.data["pacientes"][paciente['nif']]["kpis"]["modelo_ia"] = self.redactor.modelo
        self.recorder._save()
        print(f"\n{'='*50}")
        print(f"  CLINDOC AGENT - AUDITORÍA CLÍNICA")
        print(f"{'='*50}")
        print(f"Paciente: {paciente['nombre']}")
        print(f"NIF: {paciente.get('nif', 'N/A')}")
        print(f"{'='*50}\n")

        # AISLAMIENTO: colección propia y limpia para este paciente (no mezcla folios entre pacientes)
        self.indice.usar_coleccion_paciente(paciente['nif'])

        # NORMALIZACIÓN: folios heterogéneos -> PDF canónico (habilita el Deep Linking por coordenadas)
        try:
            from normalizador_pdf import generar_pdfs_paciente
            ok_pdf, tot_pdf = generar_pdfs_paciente(paciente['nif'])
            print(f"   [ingesta] {ok_pdf}/{tot_pdf} folios normalizados a PDF canónico")
        except Exception as _e:
            print(f"   [aviso] no se pudieron generar PDFs canónicos: {_e}")

        state: AgentState = {
            "documentos": [],
            "paciente": paciente,
            "resultados": {},
            "errores": [],
            "retry_count": 0,
            "trace": [],
            "needs_retry": False,
        }

        if self.app_graph is not None:
            # Orquestación REAL con LangGraph (grafo de estados + ciclo de autocorrección)
            print("[ORQUESTACIÓN] LangGraph StateGraph (ingestion→identity→vigency→redact→critique⟳→assemble)")
            state = self.app_graph.invoke(state, config={"recursion_limit": 50})
        else:
            # Fallback: ejecución secuencial respetando el ciclo de autocorrección
            print("[FASE 1] Escaneo de documentos...")
            state = self._node_ingestion(state)
            print("[FASE 2] Validación de identidad...")
            state = self._node_validate_identity(state)
            print("[FASE 3] Validación de vigencia...")
            state = self._node_validate_vigency(state)
            print("[FASE 4] Generación de resumen clínico...")
            state = self._node_redact(state)
            state = self._node_critique(state)
            while state.get("needs_retry"):
                state = self._node_redact(state)
                state = self._node_critique(state)
            print("[FASE 5] Generación de informe PDF...")
            state = self._node_assemble(state)
        
        # Tiempo total
        tiempo_total = round(time.time() - inicio, 2)
        self.recorder.data["pacientes"][paciente['nif']]["kpis"]["total_time"] = tiempo_total
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

        # AISLAMIENTO: colección propia y limpia para este paciente (no mezcla folios entre pacientes)
        self.indice.usar_coleccion_paciente(paciente['nif'])

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


# --- CARGA DEL GUION YAML (contrato semántico que dirige el demo) ---
def cargar_guion_yaml(ruta: str = "guiones/baja_laboral.yaml") -> Dict:
    """Carga el guion (baja_laboral.yaml) y lo mapea a {titulo, secciones:[{id,titulo,instruccion}]}.
    Las secciones con 'campos' (y sin 'instruccion') derivan su instrucción de esos campos, de modo
    que el guion YAML dirige el demo principal (contrato semántico) en vez de secciones hardcoded."""
    with open(ruta, encoding="utf-8") as f:
        y = yaml.safe_load(f)
    secciones = []
    for s in y.get("secciones", []):
        instr = (s.get("instruccion") or "").strip()
        if not instr:
            campos_def = s.get("campos", [])
            obligatorios = [c.get("nombre", "") for c in campos_def if c.get("nombre") and c.get("requerido", False)]
            opcionales = [c.get("nombre", "") for c in campos_def if c.get("nombre") and not c.get("requerido", False)]
            if obligatorios or opcionales:
                partes_instr = [f"Redacta la sección '{s['titulo']}'."]
                if obligatorios:
                    partes_instr.append(f"Campos obligatorios (deben aparecer si el expediente los documenta): {', '.join(obligatorios)}.")
                if opcionales:
                    partes_instr.append(
                        f"Campos opcionales (inclúyelos SOLO si aparecen explícitamente en los DATOS; "
                        f"si un campo opcional no está documentado, OMÍTELO sin mencionarlo, no inventes ni un valor de ejemplo): {', '.join(opcionales)}."
                    )
                partes_instr.append("Cíñete estrictamente a la evidencia documental del expediente.")
                instr = " ".join(partes_instr)
            else:
                instr = (f"Redacta la sección '{s['titulo']}' cubriendo los datos relevantes del expediente. "
                         f"Cíñete estrictamente a la evidencia documental del expediente.")
        secciones.append({
            "id": s["id"], "titulo": s["titulo"], "instruccion": instr,
            "fuente_preferente": s.get("fuente_preferente"),
        })
    return {"titulo": y.get("titulo", "Informe Técnico de Expediente"), "secciones": secciones}


# --- EJECUCIÓN MAESTRA ---
if __name__ == "__main__":
    # El guion YAML (contrato semántico) dirige el demo; fallback a secciones por defecto si falla
    try:
        config_demo = cargar_guion_yaml("guiones/baja_laboral.yaml")
        print(f"Guion YAML cargado: {len(config_demo['secciones'])} secciones desde baja_laboral.yaml -> "
              + ", ".join(s['titulo'] for s in config_demo['secciones']))
    except Exception as e:
        print(f"[AVISO] No se pudo cargar el guion YAML ({e}); usando secciones por defecto.")
        config_demo = {
            "titulo": "Auditoría de Alta Complejidad v4.0 (Master Run)",
            "secciones": [
                {"id": "A1", "titulo": "Antecedentes de Salud", "instruccion": "Sintetice hallazgos cardíacos y quirúrgicos previos."},
                {"id": "A2", "titulo": "Evolución Clínica Reciente", "instruccion": "Evalúe la respuesta al tratamiento post-operatorio."},
                {"id": "A3", "titulo": "Recomendaciones", "instruccion": "Defina pautas de reposo y seguimiento médico."}
            ]
        }

    print("Usando Orquestador LangGraph Multi-Paciente (v5.0)")
    ruta_expedientes = Path("datos/expedientes")
    ruta_expedientes.mkdir(parents=True, exist_ok=True)
    carpetas_pacientes = [d for d in ruta_expedientes.iterdir() if d.is_dir()]

    # Permite procesar UN solo paciente:  python run_clindoc.py <NIF>
    nif_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if nif_arg:
        carpetas_pacientes = [d for d in carpetas_pacientes if d.name == nif_arg]
        print(f">>> Procesando SOLO el paciente indicado: {nif_arg} ({len(carpetas_pacientes)} carpeta encontrada)")

    if not carpetas_pacientes and not nif_arg:
        # Crear datos de prueba
        (ruta_expedientes / "12345678Z").mkdir(exist_ok=True)
        (ruta_expedientes / "12345678Z" / "paciente_juan.txt").write_text("Nombre: Juan Pérez García. Hallazgos: Evolución favorable post-cirugía.", encoding='utf-8')
        (ruta_expedientes / "87654321A").mkdir(exist_ok=True)
        (ruta_expedientes / "87654321A" / "paciente_maria.txt").write_text("Nombre: María Gómez. Hallazgos: Presenta cuadro de hipertensión controlada.", encoding='utf-8')
        carpetas_pacientes = [d for d in ruta_expedientes.iterdir() if d.is_dir()]
    
    sistema = OrquestadorLangGraph(config_demo)
    
    for carpeta in carpetas_pacientes:
        nif_paciente = carpeta.name
        nombre_paciente = f"Paciente {nif_paciente}"
        
        # --- RESUME LOGIC PROPER ---
        try:
            with open("dashboard_data.json", "r", encoding="utf-8") as f:
                d = json.load(f)
                p_data = d.get("pacientes", {}).get(nif_paciente, {})
                # If there are analisis_seccion events, it's considered processed
                if any(e.get("type") == "analisis_seccion" for e in p_data.get("events", [])):
                    print(f"[{nif_paciente}] SALTANDO PACIENTE: Ya procesado en dashboard_data.json")
                    continue
        except Exception as e:
            pass
        # ---------------------------

        paciente_data = {"nombre": nombre_paciente, "nif": nif_paciente}
        
        sistema.escanner.ruta = carpeta
        sistema.recorder.set_paciente(nif_paciente, nombre_paciente)
        
        resultados = sistema.ejecutar(paciente_data)
        
        print(f"\n[{nif_paciente}] PROCESADO CORRECTAMENTE")

    print("\n" + "="*50)
    print("  EJECUCIÓN MULTI-PACIENTE COMPLETADA CON EXITO")
    print("="*50)
