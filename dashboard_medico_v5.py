"""
DASHBOARD MÉDICO INTEGRADO - CLINDOC AGENT v5.0
=================================================
Dashboard completo que integra:
1. Revisión de informes generados por IA
2. Chat asistente para dudas
3. Matriz de confusión
4. Feedback loop médico-IA
5. Historial clínico visual

Este dashboard representa el FLUJO REAL del médico:
- Se sienta → Busca paciente → Ve informe IA
- Puede chatear con la IA sobre dudas
- Revisa historial clínico visual
- Aprueba/Modifica/Añade
- Firma el informe (responsabilidad médica)

Módulo CRÍTICO para Capítulo 5 y 6 del TFM.
"""

import streamlit as st
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Configuración de página
st.set_page_config(
    page_title="ClinDoc Agent | Dashboard Médico v5.0",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton > button { border-radius: 5px; }
    .seccion-auditar {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; }
    .badge-aprobado { background-color: #28a745; color: white; }
    .badge-pendiente { background-color: #ffc107; color: black; }
    .badge-modificado { background-color: #dc3545; color: white; }
    .chat-message { padding: 10px; margin: 5px 0; border-radius: 10px; }
    .chat-medico { background-color: #e3f2fd; text-align: right; }
    .chat-ia { background-color: #f5f5f5; text-align: left; }
    </style>
""", unsafe_allow_html=True)

# Imports
import sys
sys.path.insert(0, ".")
from chat_asistente_medico import ChatAsistenteMedico, TipoMensaje
from modulo_auditoria import GestorAuditorias, TipoValidacion, CategoriaError, ValidacionSeccion
from run_clindoc import AgenteEscanner, IndiceCorpus
from historial_clinico_visual import HistorialClinicoVisual


class DashboardMedicov5:
    """
    Dashboard médico integrado v5.0
    
    FLUJO DEL MÉDICO:
    1. Buscar/Seleccionar paciente
    2. Ver informe generado por IA
    3. Revisar cada sección
    4. Si tiene dudas → Chat con IA
    5. Aprobar/Modificar/Añadir
    6. Firmar (responsabilidad médica)
    """
    
    def __init__(self):
        self.gestor = GestorAuditorias()
        self.chat = ChatAsistenteMedico()
        self._inicializar_estado()
    
    def _inicializar_estado(self):
        """Inicializa el estado de la sesión"""
        if 'vista_actual' not in st.session_state:
            st.session_state.vista_actual = "inicio"
        if 'informe_seleccionado' not in st.session_state:
            st.session_state.informe_seleccionado = None
        if 'mostrar_chat' not in st.session_state:
            st.session_state.mostrar_chat = False
    
    def mostrar_sidebar(self):
        """Barra lateral de navegación"""
        with st.sidebar:
            st.title("🏥 ClinDoc Agent")
            st.markdown("**v5.0 - Dashboard Integrado**")
            st.markdown("---")
            
            # Menú principal
            st.markdown("### 📋 Menú")
            opcion = st.radio("Navegación", [
                "🏠 Inicio",
                "🔍 Buscar Paciente",
                "📋 Informes Pendientes",
                "📈 Historial Clínico",
                "💬 Chat Asistente",
                "📊 Métricas de Calidad"
            ], label_visibility="collapsed")
            
            st.markdown("---")
            
            # Estado del sistema
            st.markdown("### ℹ️ Estado del Sistema")
            col1, col2 = st.columns(2)
            with col1:
                st.success("● Activo")
            with col2:
                st.info("● Local")
            
            st.markdown("---")
            
            # Guía rápida
            st.markdown("""
            ### 📖 Guía Rápida
            
            1. **Buscar** paciente por NIF
            2. **Revisar** informe generado por IA
            3. **Chat** si tiene dudas
            4. **Aprobar/Modificar** secciones
            5. **Firmar** informe (usted responde)
            """)
            
            return opcion
    
    def vista_inicio(self):
        """Pantalla de inicio"""
        st.title("🏥 ClinDoc Agent v5.0")
        st.markdown("## Dashboard del Médico")
        
        # Stats rápidos
        stats = self.gestor.obtener_estadisticas()
        chat_stats = self.chat.obtener_estadisticas_feedback()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Informes Pendientes", stats.get("informes_pendientes", 0))
        with col2:
            st.metric("Total Auditados", stats.get("matriz_confusion", {}).get("metricas", {}).get("total_validaciones", 0))
        with col3:
            st.metric("Correcciones IA", chat_stats.get("correcciones_medicas", 0))
        with col4:
            st.metric("Precisión IA", f"{stats.get('matriz_confusion', {}).get('metricas', {}).get('precision', 0)}%")
        
        st.markdown("---")
        
        # Acciones rápidas
        st.markdown("### 🚀 Acciones Rápidas")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Buscar Paciente", use_container_width=True):
                st.session_state.vista_actual = "buscar"
                st.rerun()
        with col2:
            if st.button("📋 Ver Pendientes", use_container_width=True):
                st.session_state.vista_actual = "pendientes"
                st.rerun()
        
        # Últimos informes
        st.markdown("### 📄 Informes Recientes")
        pendientes = self.gestor.listar_informes_pendientes()[:5]
        
        if pendientes:
            for p in pendientes:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.markdown(f"**{p['paciente']}**")
                    with col2:
                        st.caption(p['nif'])
                    with col3:
                        if st.button("Revisar", key=f"btn_{p['informe_id']}"):
                            st.session_state.informe_seleccionado = p['informe_id']
                            st.session_state.vista_actual = "revisar"
                            st.rerun()
        else:
            st.success("✓ No hay informes pendientes")
    
    def vista_buscar(self):
        """Buscar paciente"""
        st.title("🔍 Buscar Paciente")
        
        busqueda = st.text_input("Buscar por NIF o Nombre:", placeholder="12345678Z o Juan Pérez")
        
        if busqueda:
            # Buscar en auditorias
            pacientes = []
            for archivo in Path("datos/auditorias").glob("inf_*.json"):
                try:
                    with open(archivo, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if (busqueda.upper() in data.get("paciente_nif", "").upper() or 
                            busqueda.upper() in data.get("paciente_nombre", "").upper()):
                            pacientes.append({
                                "informe_id": data["informe_id"],
                                "nif": data["paciente_nif"],
                                "nombre": data["paciente_nombre"],
                                "estado": data["estado"],
                                "fecha": data["fecha_generacion"]
                            })
                except:
                    pass
            
            if pacientes:
                for p in pacientes:
                    with st.container():
                        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                        with col1:
                            st.markdown(f"**{p['nombre']}**")
                        with col2:
                            st.caption(f"NIF: {p['nif']}")
                        with col3:
                            badge = f"badge-{p['estado']}"
                            st.markdown(f"<span class='badge {badge}'>{p['estado']}</span>", 
                                       unsafe_allow_html=True)
                        with col4:
                            if st.button("Revisar", key=f"bus_{p['informe_id']}"):
                                st.session_state.informe_seleccionado = p['informe_id']
                                st.session_state.vista_actual = "revisar"
                                st.rerun()
            else:
                st.warning("No se encontraron pacientes")
        
        if st.button("← Volver"):
            st.session_state.vista_actual = "inicio"
            st.rerun()
    
    def vista_revisar(self):
        """Revisar un informe específico"""
        if not st.session_state.informe_seleccionado:
            st.error("No hay informe seleccionado")
            return
        
        informe = self.gestor.cargar_informe(st.session_state.informe_seleccionado)
        
        if not informe:
            st.error("Informe no encontrado")
            return
        
        # Header
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.title(f"📋 {informe.paciente_nombre}")
        with col2:
            if st.button("💬 Chat"):
                st.session_state.mostrar_chat = not st.session_state.mostrar_chat
        with col3:
            if st.button("← Volver"):
                st.session_state.vista_actual = "inicio"
                st.rerun()
        
        # Info paciente
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("NIF", informe.paciente_nif)
        with col2:
            st.metric("Generado", informe.fecha_generacion[:10])
        with col3:
            estado = informe.estado
            if estado == "pendiente":
                st.warning("⏳ Pendiente")
            elif estado == "auditado":
                st.info("✏️ Auditado")
            else:
                st.success("✓ Aprobado")
        
        st.markdown("---")
        
        # Layout: Revisión + Chat
        col_rev, col_chat = st.columns([3, 1]) if st.session_state.mostrar_chat else [1, 0]
        
        with col_rev:
            # Secciones del informe
            st.markdown("### 📄 Secciones del Informe")
            
            secciones = getattr(informe, 'secciones', {}) or {}
            
            if not secciones:
                st.warning("No hay secciones disponibles")
                return
            
            # Formulario de auditoría
            with st.form(f"auditoria_{informe.informe_id}"):
                validaciones = []
                
                for titulo, contenido in secciones.items():
                    with st.container():
                        st.markdown(f"""
                        <div class="seccion-auditar">
                            <h4>{titulo}</h4>
                            <p>{contenido[:500]}{'...' if len(contenido) > 500 else ''}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Opciones
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            aprobar = st.checkbox("✓ Aprobar", key=f"apr_{titulo}")
                        with col_b:
                            modificar = st.checkbox("✗ Modificar", key=f"mod_{titulo}")
                        with col_c:
                            nuevo = st.checkbox("+ Nuevo Hallazgo", key=f"nue_{titulo}")
                        
                        texto_modificado = ""
                        notas = ""
                        
                        if modificar:
                            texto_modificado = st.text_area(
                                "Texto corregido:", value=contenido, 
                                key=f"txt_{titulo}"
                            )
                            notas = st.text_area("Notas:", key=f"not_{titulo}")
                        elif nuevo:
                            notas = st.text_area(
                                "Nuevo hallazgo (lo que la IA no vio):",
                                key=f"new_{titulo}"
                            )
                        
                        validaciones.append({
                            "seccion": titulo,
                            "aprobar": aprobar,
                            "modificar": modificar,
                            "nuevo": nuevo,
                            "texto_modificado": texto_modificado,
                            "notas": notas
                        })
                        
                        st.markdown("---")
                
                # Botones
                col1, col2 = st.columns(2)
                with col1:
                    guardar = st.form_submit_button("💾 Guardar Auditoría", type="primary")
                with col2:
                    aprobar_todo = st.form_submit_button("✓ Firmar/Aprobar Informe")
        
        # Procesar auditoría
        if guardar:
            for val in validaciones:
                if val["aprobar"]:
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.APROBADO,
                        texto_original=secciones.get(val["seccion"], "")
                    )
                    self.gestor.registrar_validacion(informe.informe_id, v)
                
                if val["modificar"]:
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.MODIFICADO,
                        texto_original=secciones.get(val["seccion"], ""),
                        texto_modificado=val["texto_modificado"],
                        notas_medico=val["notas"],
                        categoria_error=CategoriaError.FALSO_POSITIVO
                    )
                    self.gestor.registrar_validacion(informe.informe_id, v)
                
                if val["nuevo"]:
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.NUEVOhallazgo,
                        texto_original="",
                        notas_medico=val["notas"],
                        categoria_error=CategoriaError.OMISION
                    )
                    self.gestor.registrar_validacion(informe.informe_id, v)
            
            st.success("✓ Auditoría guardada")
            st.rerun()
        
        if aprobar_todo:
            self.gestor.aprobar_informe(
                informe.informe_id, 
                "Aprobado y firmado por el médico"
            )
            st.success("✓ Informe firmado y aprobado")
            st.rerun()
        
        # Panel de chat
        if st.session_state.mostrar_chat:
            with col_chat:
                self._mostrar_panel_chat(informe)
    
    def _mostrar_panel_chat(self, informe):
        """Muestra el panel de chat"""
        st.markdown("### 💬 Chat con IA")
        
        # Iniciar conversación si no existe
        if not self.chat.conversacion_actual:
            self.chat.iniciar_conversacion(
                informe.informe_id,
                informe.paciente_nif,
                informe.paciente_nombre
            )
        
        # Mostrar mensajes
        mensajes = self.chat.conversacion_actual.mensajes[-8:] if self.chat.conversacion_actual else []
        
        for msg in mensajes:
            if msg.tipo == TipoMensaje.PREGUNTA or msg.tipo == TipoMensaje.CORRECCION:
                st.markdown(f"**👨‍⚕️:** {msg.contenido[:100]}...")
            elif msg.tipo == TipoMensaje.RESPUESTA:
                st.markdown(f"**🤖:** {msg.contenido[:100]}...")
        
        # Input
        with st.form("chat_form"):
            mensaje = st.text_input("Preguntar:", key="chat_input")
            tipo = st.selectbox("Tipo", ["pregunta", "correccion", "aprobacion"])
            enviar = st.form_submit_button("Enviar")
        
        if enviar and mensaje:
            self.chat.enviar_mensaje(mensaje, TipoMensaje(tipo))
            st.rerun()
    
    def vista_pendientes(self):
        """Ver informes pendientes"""
        st.title("📋 Informes Pendientes")
        
        pendientes = self.gestor.listar_informes_pendientes()
        
        if pendientes:
            for p in pendientes:
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    with col1:
                        st.markdown(f"**{p['paciente']}**")
                    with col2:
                        st.caption(p['nif'])
                    with col3:
                        st.caption(p['fecha'][:10])
                    with col4:
                        if st.button("Revisar", key=f"pen_{p['informe_id']}"):
                            st.session_state.informe_seleccionado = p['informe_id']
                            st.session_state.vista_actual = "revisar"
                            st.rerun()
                    st.markdown("---")
        else:
            st.success("✓ No hay informes pendientes")
        
        if st.button("← Volver"):
            st.session_state.vista_actual = "inicio"
            st.rerun()
    
    def vista_historial(self):
        """Ver historial clínico visual del paciente"""
        st.title("📈 Historial Clínico - Evolución del Paciente")
        
        # Selector de paciente
        col1, col2 = st.columns([2, 1])
        with col1:
            paciente_seleccionado = st.selectbox(
                "Seleccionar Paciente:",
                options=self._listar_pacientes(),
                format_func=lambda x: f"{x['nombre']} ({x['nif']})" if x else "Seleccionar..."
            )
        
        if not paciente_seleccionado:
            st.info("Seleccione un paciente para ver su historial clínico")
            return
        
        # Mostrar historial
        historial = HistorialClinicoVisual()
        historial.cargar_expediente(
            paciente_seleccionado["nif"], 
            paciente_seleccionado["nombre"]
        )
        
        if not historial.eventos:
            st.warning(f"No se encontró información clínica para {paciente_seleccionado['nombre']}")
            return
        
        # Estadísticas
        stats = historial.obtener_estadisticas()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Eventos", stats["total_eventos"])
        with col2:
            st.metric("Días de Seguimiento", stats["dias_seguimiento"])
        with col3:
            st.metric("Eventos Importantes", stats["eventos_importantes"])
        with col4:
            st.metric("Período", f"{stats['primera_fecha'][:4]} - {stats['ultima_fecha'][:4]}")
        
        # Buscador
        st.markdown("### 🔍 Buscar Término o Enfermedad")
        busqueda = st.text_input("Buscar en historial:", 
                                placeholder="diabetes, tensión, tratamiento, análisis...")
        
        if busqueda:
            resultados = historial.buscar_termino(busqueda)
            st.markdown(f"**{len(resultados)} resultados encontrados** para '{busqueda}'")
            
            for e in resultados:
                with st.expander(f"📅 {e.fecha.strftime('%d/%m/%Y')} - {e.titulo}"):
                    st.markdown(f"**Tipo:** {e.tipo.capitalize()}")
                    st.markdown(f"**Descripción:** {e.descripcion}")
                    st.markdown(f"**Fuente:** {e.fuente}")
        
        # Gráfico timeline
        st.markdown("### 📊 Línea de Tiempo - Evolución Clínica")
        fig = historial.generar_grafico_timeline()
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabla de eventos
        st.markdown("### 📋 Lista de Eventos")
        eventos = historial.generar_tabla_eventos()
        if eventos:
            import pandas as pd
            df = pd.DataFrame(eventos)
            st.dataframe(df, use_container_width=True)
        
        if st.button("← Volver"):
            st.session_state.vista_actual = "inicio"
            st.rerun()
    
    def _listar_pacientes(self) -> List[Dict]:
        """Lista todos los pacientes con datos"""
        pacientes = []
        
        # De auditorías
        for archivo in Path("datos/auditorias").glob("inf_*.json"):
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pacientes.append({
                        "nif": data.get("paciente_nif", ""),
                        "nombre": data.get("paciente_nombre", "")
                    })
            except:
                pass
        
        return pacientes
    
    def vista_chat(self):
        """Ver historial de chat"""
        st.title("💬 Chat Asistente")
        
        historial = self.chat.obtener_historial()
        
        if historial:
            for h in historial[:10]:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.markdown(f"**{h['paciente']}**")
                    with col2:
                        st.caption(f"{h['mensajes']} mensajes")
                    with col3:
                        st.caption(h['estado'])
        else:
            st.info("No hay conversaciones")
        
        if st.button("← Volver"):
            st.session_state.vista_actual = "inicio"
            st.rerun()
    
    def vista_metricas(self):
        """Ver métricas de calidad"""
        st.title("📊 Métricas de Calidad")
        
        stats = self.gestor.obtener_estadisticas()
        matriz = stats.get("matriz_confusion", {}).get("matriz", {})
        metricas = stats.get("matriz_confusion", {}).get("metricas", {})
        
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Precisión", f"{metricas.get('precision', 0)}%")
        with col2:
            st.metric("Exhaustividad", f"{metricas.get('exhaustividad', 0)}%")
        with col3:
            st.metric("F1-Score", f"{metricas.get('f1', 0)}%")
        with col4:
            st.metric("Exactitud", f"{metricas.get('exactitud', 0)}%")
        
        # Matriz visual
        st.markdown("### Matriz de Confusión")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <table style="width:100%; text-align:center; border: 1px solid #ddd;">
                <tr>
                    <th></th>
                    <th>Predicho: Sí</th>
                    <th>Predicho: No</th>
                </tr>
                <tr>
                    <td><b>Real: Sí</b></td>
                    <td style="background-color:#d4edda;"><b>VP: {matriz.get('vp', 0)}</b></td>
                    <td style="background-color:#f8d7da;"><b>FN: {matriz.get('fn', 0)}</b></td>
                </tr>
                <tr>
                    <td><b>Real: No</b></td>
                    <td style="background-color:#f8d7da;"><b>FP: {matriz.get('fp', 0)}</b></td>
                    <td style="background-color:#d4edda;"><b>VN: {matriz.get('vn', 0)}</b></td>
                </tr>
            </table>
            """, unsafe_allow_html=True)
        
        st.markdown("""
        - **VP:** IA detectó bien → Médico aprobó
        - **FP:** IA detectó mal → Médico corrigió
        - **FN:** IA no vio → Médico añadió
        - **VN:** IA no mencionó → Correcto
        """)
        
        # Chat stats
        chat_stats = self.chat.obtener_estadisticas_feedback()
        st.markdown("### Feedback del Chat")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Correcciones", chat_stats["correcciones_medicas"])
        with col2:
            st.metric("Preguntas", chat_stats["preguntas"])
        with col3:
            st.metric("Ratio Aprobación", f"{chat_stats['ratio_aprobacion']}%")
        
        if st.button("← Volver"):
            st.session_state.vista_actual = "inicio"
            st.rerun()
    
    def run(self):
        """Ejecuta el dashboard"""
        opcion = self.mostrar_sidebar()
        
        if opcion == "🏠 Inicio":
            self.vista_inicio()
        elif opcion == "🔍 Buscar Paciente":
            self.vista_buscar()
        elif opcion == "📋 Informes Pendientes":
            self.vista_pendientes()
        elif opcion == "📈 Historial Clínico":
            self.vista_historial()
        elif opcion == "💬 Chat Asistente":
            self.vista_chat()
        elif opcion == "📊 Métricas de Calidad":
            self.vista_metricas()
        elif st.session_state.vista_actual == "revisar":
            self.vista_revisar()


# === ENTRADA PRINCIPAL ===
if __name__ == "__main__":
    dashboard = DashboardMedicov5()
    dashboard.run()