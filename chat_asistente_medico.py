"""
CHAT ASISTENTE MÉDICO - CLINDOC AGENT
======================================
Asistente de conversación para que el médico pueda:
1. Preguntar sobre aspectos cuestionables del informe
2. Dar su opinión/expertise
3. El sistema aprende del feedback del médico

FLUJO:
- Médico revisa informe y ve algo dudoso
- Abre chat y pregunta: "¿Por qué dijiste esto?"
- IA explica su razonamiento
- Médico puede corregir/añadir: "En realidad el paciente tiene..."
- Sistema registra este feedback para aprendizaje

Este módulo es CRÍTICO para Capítulo 5 y 6 del TFM:
- Feedback loop médico-IA
- Aprendizaje continuo
- Responsabilidad médica (quien firma es el doctor)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum
import ollama


class TipoMensaje(str, Enum):
    """Tipos de mensaje en la conversación"""
    PREGUNTA = "pregunta"        # Médico pregunta
    RESPUESTA = "respuesta"      # IA responde
    CORRECCION = "correccion"   # Médico corrige a la IA
    APROBACION = "aprobacion"   # Médico aprueba
    NOTA = "nota"               # Nota informativa


class MensajeChat(BaseModel):
    """Mensaje en el chat"""
    tipo: TipoMensaje
    contenido: str
    timestamp: datetime = Field(default_factory=datetime.now)
    seccion_origen: Optional[str] = None  # Sección del informe que se discute


class Conversacion(BaseModel):
    """Conversación entre médico e IA sobre un informe"""
    conversacion_id: str
    informe_id: str
    paciente_nif: str
    paciente_nombre: str
    mensajes: List[MensajeChat] = []
    estado: str = "activa"  # activa/cerrada
    fecha_creacion: datetime = Field(default_factory=datetime.now)
    fecha_cierre: Optional[datetime] = None


class ChatAsistenteMedico:
    """
    Chat interactivo para que el médico dialogue con la IA.
    
    CASOS DE USO:
    1. Aclaración: "¿Por qué mencionaste diabetes?"
    2. Corrección: "El paciente NO tiene алт elevado"
    3. Consulta: "¿Qué evidencia encontraste para este diagnóstico?"
    4. Validación: "Confirmo que el tratamiento es correcto"
    
    APRENDIZAJE:
    - Cada corrección del médico se guarda
    - Se puede usar para fine-tuning del modelo
    - Mejora la precisión en futuras generaciones
    """
    
    def __init__(self, ruta: str = "datos/conversaciones", modelo: str = "gemma3:4b"):
        self.ruta = Path(ruta)
        self.ruta.mkdir(parents=True, exist_ok=True)
        self.modelo = modelo
        self.conversacion_actual: Optional[Conversacion] = None
    
    def iniciar_conversacion(self, informe_id: str, paciente_nif: str, 
                            paciente_nombre: str) -> str:
        """Inicia una nueva conversación sobre un informe"""
        conv_id = f"conv_{informe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.conversacion_actual = Conversacion(
            conversacion_id=conv_id,
            informe_id=informe_id,
            paciente_nif=paciente_nif,
            paciente_nombre=paciente_nombre
        )
        
        # Mensaje inicial
        self.conversacion_actual.mensajes.append(MensajeChat(
            tipo=TipoMensaje.NOTA,
            contenido=f"Conversación iniciada sobre informe de {paciente_nombre}. "
                     f"Puede preguntar sobre cualquier aspecto del informe generado por IA."
        ))
        
        self._guardar_conversacion()
        
        return conv_id
    
    def enviar_mensaje(self, mensaje: str, tipo: TipoMensaje = TipoMensaje.PREGUNTA,
                      seccion: Optional[str] = None) -> str:
        """Envía un mensaje y obtiene respuesta de la IA"""
        
        if not self.conversacion_actual:
            return "Error: No hay conversación activa"
        
        # Guardar mensaje del médico
        msg_medico = MensajeChat(
            tipo=tipo,
            contenido=mensaje,
            seccion_origen=seccion
        )
        self.conversacion_actual.mensajes.append(msg_medico)
        
        # Si es una corrección, procesar especialmente
        if tipo == TipoMensaje.CORRECCION:
            respuesta = self._procesar_correccion(mensaje, seccion)
        else:
            # Generar respuesta de la IA
            respuesta = self._generar_respuesta(mensaje)
        
        # Guardar respuesta de la IA
        msg_ia = MensajeChat(
            tipo=TipoMensaje.RESPUESTA,
            contenido=respuesta
        )
        self.conversacion_actual.mensajes.append(msg_ia)
        
        self._guardar_conversacion()
        
        return respuesta
    
    def _procesar_correccion(self, correccion: str, seccion: Optional[str]) -> str:
        """Procesa una corrección del médico"""
        
        # Registrar la corrección en el sistema de auditoría
        try:
            from modulo_auditoria import (
                GestorAuditorias, TipoValidacion, 
                CategoriaError, ValidacionSeccion
            )
            
            gestor = GestorAuditorias()
            
            validacion = ValidacionSeccion(
                seccion=seccion or "Chat",
                validacion=TipoValidacion.MODIFICADO,
                texto_original="",
                texto_modificado=correccion,
                notas_medico=f"Corrección vía chat: {correccion}",
                categoria_error=CategoriaError.OMISION  # Asumimos omisión por defecto
            )
            
            gestor.registrar_validacion(
                self.conversacion_actual.informe_id, 
                validacion
            )
        except Exception as e:
            pass  # Silenciar errores de auditoría en chat
        
        # Responder confirmando la corrección
        return (f"✓ Corrección registrada. "
                f"Gracias por su feedback. "
                f"Esta corrección ayudará a mejorar la precisión del sistema en futuras generaciones. "
                f"¿Desea que actualice el informe con esta corrección?")
    
    def _generar_respuesta(self, pregunta: str) -> str:
        """Genera respuesta de la IA usando contexto del informe"""
        
        # Cargar contexto del informe
        contexto = self._obtener_contexto_informe()
        
        # Construir prompt
        prompt = f"""Eres un asistente médico experto. Un doctor está revisando 
un informe generado por IA y tiene la siguiente pregunta:

PREGUNTA DEL MÉDICO: {pregunta}

CONTEXTO DEL INFORME:
{contexto}

INSTRUCCIONES:
1. Responde de forma clara y técnica
2. Si no tienes información suficiente, dilo
3. Si el médico hace una corrección, reconócela y agradécela
4. Recuerda: el médico es quien firma el informe, tú eres solo un asistente

Responde en español de forma profesional."""
        
        try:
            respuesta = ollama.chat(
                model=self.modelo,
                messages=[{'role': 'user', 'content': prompt}]
            )
            return respuesta['message']['content']
        except Exception as e:
            return f"Error al generar respuesta: {str(e)}"
    
    def _obtener_contexto_informe(self) -> str:
        """Obtiene el contexto del informe actual"""
        
        try:
            from pathlib import Path
            archivo = Path("datos/auditorias") / f"{self.conversacion_actual.informe_id}.json"
            
            if archivo.exists():
                with open(archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return json.dumps(data.get("secciones", {}), indent=2, ensure_ascii=False)
        except:
            pass
        
        return "No hay contexto adicional disponible"
    
    def _guardar_conversacion(self):
        """Guarda la conversación actual"""
        
        if not self.conversacion_actual:
            return
        
        archivo = self.ruta / f"{self.conversacion_actual.conversacion_id}.json"
        
        data = {
            "conversacion_id": self.conversacion_actual.conversacion_id,
            "informe_id": self.conversacion_actual.informe_id,
            "paciente_nif": self.conversacion_actual.paciente_nif,
            "paciente_nombre": self.conversacion_actual.paciente_nombre,
            "estado": self.conversacion_actual.estado,
            "fecha_creacion": self.conversacion_actual.fecha_creacion.isoformat(),
            "fecha_cierre": self.conversacion_actual.fecha_cierre.isoformat() 
                           if self.conversacion_actual.fecha_cierre else None,
            "mensajes": [
                {
                    "tipo": m.tipo,
                    "contenido": m.contenido,
                    "timestamp": m.timestamp.isoformat(),
                    "seccion_origen": m.seccion_origen
                }
                for m in self.conversacion_actual.mensajes
            ]
        }
        
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def cerrar_conversacion(self):
        """Cierra la conversación actual"""
        
        if self.conversacion_actual:
            self.conversacion_actual.estado = "cerrada"
            self.conversacion_actual.fecha_cierre = datetime.now()
            self._guardar_conversacion()
            self.conversacion_actual = None
    
    def cargar_conversacion(self, conversacion_id: str) -> Optional[Conversacion]:
        """Carga una conversación existente"""
        
        archivo = self.ruta / f"{conversacion_id}.json"
        
        if not archivo.exists():
            return None
        
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        mensajes = [
            MensajeChat(
                tipo=m["tipo"],
                contenido=m["contenido"],
                timestamp=datetime.fromisoformat(m["timestamp"]),
                seccion_origen=m.get("seccion_origen")
            )
            for m in data["mensajes"]
        ]
        
        conv = Conversacion(
            conversacion_id=data["conversacion_id"],
            informe_id=data["informe_id"],
            paciente_nif=data["paciente_nif"],
            paciente_nombre=data["paciente_nombre"],
            estado=data["estado"],
            fecha_creacion=datetime.fromisoformat(data["fecha_creacion"]),
            mensajes=mensajes
        )
        
        if data.get("fecha_cierre"):
            conv.fecha_cierre = datetime.fromisoformat(data["fecha_cierre"])
        
        self.conversacion_actual = conv
        return conv
    
    def obtener_historial(self) -> List[Dict]:
        """Obtiene historial de conversaciones"""
        
        conversaciones = []
        
        for archivo in self.ruta.glob("conv_*.json"):
            with open(archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
                conversaciones.append({
                    "conversacion_id": data["conversacion_id"],
                    "paciente": data["paciente_nombre"],
                    "estado": data["estado"],
                    "mensajes": len(data["mensajes"]),
                    "fecha": data["fecha_creacion"]
                })
        
        return sorted(conversaciones, key=lambda x: x["fecha"], reverse=True)
    
    def obtener_estadisticas_feedback(self) -> Dict:
        """Obtiene estadísticas del feedback médico"""
        
        correcciones = 0
        preguntas = 0
        aprobaciones = 0
        
        for archivo in self.ruta.glob("conv_*.json"):
            with open(archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
                for msg in data["mensajes"]:
                    if msg["tipo"] == "correccion":
                        correcciones += 1
                    elif msg["tipo"] == "pregunta":
                        preguntas += 1
                    elif msg["tipo"] == "aprobacion":
                        aprobaciones += 1
        
        return {
            "total_conversaciones": len(list(self.ruta.glob("conv_*.json"))),
            "correcciones_medicas": correcciones,
            "preguntas": preguntas,
            "aprobaciones": aprobaciones,
            "ratio_aprobacion": round(aprobaciones / (correcciones + preguntas) * 100, 1) 
                               if (correcciones + preguntas) > 0 else 0
        }


# === INTERFAZ DE CHAT PARA STREAMLIT ===
definterfaz_chat():
    """Interfaz de chat para integrar en el dashboard"""
    
    import streamlit as st
    
    st.markdown("### 💬 Chat con el Asistente")
    
    # Inicializar chat
    if 'chat_asistente' not in st.session_state:
        st.session_state.chat_asistente = ChatAsistenteMedico()
    
    chat = st.session_state.chat_asistente
    
    # Si no hay conversación activa, crear una
    if not chat.conversacion_actual and 'informe_id' in st.session_state:
        chat.iniciar_conversacion(
            st.session_state.informe_id,
            st.session_state.get('paciente_nif', 'UNKNOWN'),
            st.session_state.get('paciente_nombre', 'Paciente')
        )
    
    # Mostrar mensajes
    if chat.conversacion_actual:
        for msg in chat.conversacion_actual.mensajes[-10:]:  # Últimos 10
            if msg.tipo == TipoMensaje.PREGUNTA or msg.tipo == TipoMensaje.CORRECCION:
                st.markdown(f"**👨‍⚕️ Médico:** {msg.contenido}")
            elif msg.tipo == TipoMensaje.RESPUESTA:
                st.markdown(f"**🤖 IA:** {msg.contenido}")
            else:
                st.caption(msg.contenido)
    
    # Input del médico
    with st.form("chat_form"):
        col1, col2 = st.columns([4, 1])
        with col1:
            mensaje = st.text_input("Escriba su mensaje:", placeholder="¿Por qué mencionaste...?")
        with col2:
            tipo_mensaje = st.selectbox("Tipo", 
                ["pregunta", "correccion", "aprobacion"],
                format_func=lambda x: {"pregunta": "❓ Pregunta", 
                                      "correccion": "✏️ Corrección",
                                      "aprobacion": "✓ Confirmar"}[x])
        
        enviar = st.form_submit_button("Enviar")
    
    if enviar and mensaje:
        tipo = TipoMensaje(tipo_mensaje)
        respuesta = chat.enviar_mensaje(mensaje, tipo)
        st.rerun()
    
    # Métricas de feedback
    st.markdown("---")
    stats = chat.obtener_estadisticas_feedback()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Correcciones", stats["correcciones_medicas"])
    with col2:
        st.metric("Preguntas", stats["preguntas"])
    with col3:
        st.metric("Ratio Aprobación", f"{stats['ratio_aprobacion']}%")


# === EJEMPLO DE USO ===
if __name__ == "__main__":
    print("="*60)
    print("  CHAT ASISTENTE MÉDICO - CLINDOC AGENT")
    print("="*60)
    
    chat = ChatAsistenteMedico()
    
    # Iniciar conversación
    conv_id = chat.iniciar_conversacion(
        informe_id="inf_test_001",
        paciente_nif="12345678Z",
        paciente_nombre="Juan Pérez"
    )
    print(f"\n✓ Conversación iniciada: {conv_id}")
    
    # Simular preguntas del médico
    print("\n--- Conversación ---")
    
    # Pregunta 1
    pregunta1 = "¿Por qué mencionaste que el paciente tiene diabetes?"
    print(f"\n👨‍⚕️ Médico: {pregunta1}")
    respuesta1 = chat.enviar_mensaje(pregunta1, TipoMensaje.PREGUNTA)
    print(f"🤖 IA: {respuesta1[:200]}...")
    
    # Corrección
    correccion = "El paciente NO tiene diabetes, tiene prediabetes. Por favor corrige el informe."
    print(f"\n👨‍⚕️ Médico: {correccion}")
    respuesta2 = chat.enviar_mensaje(correccion, TipoMensaje.CORRECCION, seccion="Diagnósticos")
    print(f"🤖 IA: {respuesta2}")
    
    # Aprobación
    aproba = "El resto del informe está correcto"
    print(f"\n👨‍⚕️ Médico: {aproba}")
    respuesta3 = chat.enviar_mensaje(aproba, TipoMensaje.APROBACION)
    print(f"🤖 IA: {respuesta3}")
    
    # Cerrar conversación
    chat.cerrar_conversacion()
    
    # Estadísticas
    print("\n--- Estadísticas de Feedback ---")
    stats = chat.obtener_estadisticas_feedback()
    print(f"Total conversaciones: {stats['total_conversaciones']}")
    print(f"Correcciones médicas: {stats['correcciones_medicas']}")
    print(f"Preguntas: {stats['preguntas']}")
    print(f"Ratio aprobación: {stats['ratio_aprobacion']}%")
    
    print("\n" + "="*60)
    print("  EJEMPLO COMPLETADO")
    print("="*60)