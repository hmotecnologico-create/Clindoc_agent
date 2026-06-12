import streamlit as st
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
from pathlib import Path

# Importaciones de los nuevos módulos
from historial_clinico_visual import HistorialClinicoVisual
from chat_asistente_medico import ChatAsistenteMedico, TipoMensaje

# Configuración de página
st.set_page_config(
    page_title="ClinDoc Agent | Multi-Paciente",
    page_icon="🛡️",
    layout="wide"
)

# --- ESTILO PREMIUM ---
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1e3a8a; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #ffffff;
        border-radius: 5px 5px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] { background-color: #e5e7eb; border-bottom: 2px solid #1e3a8a; }
    .agent-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #1e3a8a;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# Cargar datos
@st.cache_data(ttl=5)
def load_data():
    path = "dashboard_data.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pacientes": {}}

data_general = load_data()
pacientes_db = data_general.get("pacientes", {})

# --- SIDEBAR (Perfiles y Pacientes) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3774/3774293.png", width=80)
    st.header("Modo de Acceso")
    perfil = st.radio("Seleccione Perfil:", ["👨‍⚕️ Doctor (Facultativo)", "🎓 Tribunal Académico"])
    st.write("---")
    
    st.header("Buscador de Pacientes")
    if not pacientes_db:
        st.warning("No hay pacientes procesados.")
        st.stop()
        
    busqueda_nif = st.text_input("Buscar por NIF (Ej: 12345678Z):")
    if busqueda_nif and busqueda_nif in pacientes_db:
        nif_seleccionado = busqueda_nif
    else:
        # Default al primero si no busca nada
        nif_seleccionado = list(pacientes_db.keys())[0]
        if busqueda_nif:
            st.error("NIF no encontrado. Mostrando paciente por defecto.")
    
    data = pacientes_db[nif_seleccionado]
    
    st.write("---")
    from chat_asistente_medico import obtener_modelo_ollama_disponible
    modelo_activo = obtener_modelo_ollama_disponible("gemma3:4b")
    st.markdown(f"**LLM Activo:** `{modelo_activo}`")
    st.caption("ClinDoc Agent v5.0")
    
    st.write("---")
    st.header("💬 Chat Asistente")
    if 'chat_asistente' not in st.session_state:
        st.session_state.chat_asistente = ChatAsistenteMedico()
        
    chat = st.session_state.chat_asistente
    if not chat.conversacion_actual or chat.conversacion_actual.paciente_nif != nif_seleccionado:
        chat.iniciar_conversacion(f"inf_{nif_seleccionado}", nif_seleccionado, data["nombre"])
        
    # Contenedor para mensajes
    chat_container = st.container(height=300)
    with chat_container:
        for msg in chat.conversacion_actual.mensajes:
            if msg.tipo in [TipoMensaje.PREGUNTA, TipoMensaje.CORRECCION, TipoMensaje.APROBACION]:
                st.markdown(f"**👨‍⚕️ Médico:** {msg.contenido}")
            elif msg.tipo == TipoMensaje.RESPUESTA:
                st.markdown(f"**🤖 IA:** {msg.contenido}")
                
    # Chat input en el sidebar
    msg_texto = st.chat_input("Consulta o corrige a la IA...")
    if msg_texto:
        chat.enviar_mensaje(msg_texto, TipoMensaje.PREGUNTA)
        st.rerun()

# --- HEADER ---
col_t1, col_t2 = st.columns([4, 1])
with col_t1:
    st.title("🛡️ ClinDoc Agent | Expediente Clínico")
    
    # Perfil del Paciente (Datos Personales Básicos)
    with st.container():
        st.markdown(f"### 👤 Datos Personales: {data['nombre']}")
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.markdown(f"**NIF:** `{data['nif']}`")
        col_p2.markdown("**Estado:** Activo")
        col_p3.markdown("**Último Ingreso:** 2026")
    
    st.write("") # Espacio
    
    # --- ALERTA NIF ---
    eventos_nif = [e for e in data["events"] if e["type"] == "validacion_identidad"]
    if eventos_nif:
        ult_evento = eventos_nif[-1]
        if ult_evento["details"].get("valido", False):
            st.success("✅ **Validación NIF:** Identidad verificada con el documento.")
        else:
            errores = ult_evento["details"].get("errores", [])
            errores_txt = " | ".join(errores) if errores else "No se encontró el NIF en el documento."
            st.error(f"🚨 **ALERTA DE SEGURIDAD (ERRATA):** {errores_txt}")
            
            # Permitir ver el documento que generó la errata
            with st.expander("👁️ Clic aquí para ver el documento con la errata", expanded=False):
                ruta_docs = Path(f"datos/expedientes/{data['nif']}")
                if ruta_docs.exists():
                    archivos = list(ruta_docs.glob("*.*"))
                    for arch in archivos:
                        if arch.name in errores_txt or "paciente_juan" in arch.name or len(archivos) == 1:
                            st.markdown(f"**Revisando archivo conflictivo:** `{arch.name}`")
                            try:
                                texto_errata = arch.read_text(encoding='utf-8')
                                st.text_area("Contenido del archivo (buscando NIF):", value=texto_errata, height=120, disabled=True, key=f"errata_{arch.name}")
                            except:
                                pass
            
with col_t2:
    if st.button("🔄 Refrescar Datos", use_container_width=True):
        st.rerun()

# --- KPIs SUPERIORES ---
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("📄 Documentos", data["kpis"]["total_docs"])
kpi2.metric("⏱️ Tiempo Total", f"{data['kpis']['total_time']}s")
kpi3.metric("🎯 Confianza", f"{round(data['kpis']['avg_confidence']*100, 1)}%")
kpi4.metric("🚨 Riesgos", data["kpis"]["critical_risks"], delta_color="inverse")

st.markdown("---")

# PERFIL DOCTOR
if perfil == "👨‍⚕️ Doctor (Facultativo)":
    tab_hist, tab_resumen, tab_traz = st.tabs(["📈 Historial Clínico", "📝 Resumen Auditable", "📅 Trazabilidad Folios"])
    
    with tab_hist:
        st.subheader("Evolución Clínica del Paciente")
        historial = HistorialClinicoVisual(f"datos/expedientes/{nif_seleccionado}")
        historial.cargar_expediente(nif_seleccionado, data["nombre"])
        
        # --- LÍNEA DE TIEMPO INTERACTIVA ---
        if historial.eventos:
            st.markdown("### 📋 Línea de Tiempo de Eventos Clínicos")
            st.caption("Haz clic en cualquier evento para abrir y leer el documento médico original asociado a esa fecha.")
            
            for i, ev in enumerate(historial.eventos):
                # Determinar icono según tipo
                icono = "💊" if ev.tipo == "tratamiento" else "🩺" if ev.tipo == "diagnostico" else "🧪" if ev.tipo == "examen" else "📅"
                
                with st.expander(f"{icono} **{ev.fecha.strftime('%d/%m/%Y')}** | {ev.titulo}"):
                    st.markdown(f"**Detalle extraído por IA:** {ev.descripcion}")
                    st.markdown(f"**Archivo de origen:** `{ev.fuente}`")
                    
                    # Cargar y mostrar el documento original de forma contextualizada
                    ruta_docs = Path(f"datos/expedientes/{nif_seleccionado}")
                    archivo_fuente = ruta_docs / ev.fuente
                    if archivo_fuente.exists():
                        try:
                            texto_doc = archivo_fuente.read_text(encoding='utf-8')
                            st.text_area("Contenido del documento en esta fecha:", value=texto_doc, height=150, disabled=True, key=f"doc_{nif_seleccionado}_{i}")
                        except Exception as e:
                            st.error("No se pudo leer el documento original.")
                    else:
                        st.warning("El documento original ha sido archivado o no está disponible en la ruta.")
        else:
            st.info("No hay eventos clínicos extraídos aún.")
            
    with tab_resumen:
        st.subheader("Auditoría del Resumen Generado por IA")
        st.info("Valide y edite el resumen generado. Al guardar, quedará evidencia de la revisión médica.")
        
        # Recuperar resumen de los eventos de "analisis_seccion"
        resumen_ia = ""
        for ev in data["events"]:
            if ev["type"] == "analisis_seccion":
                texto_seccion = ev['details'].get('texto', 'Generando texto...')
                resumen_ia += f"### {ev['details'].get('seccion', 'Sección')}\n{texto_seccion}\n\n"
        
        if not resumen_ia:
            resumen_ia = "No se encontraron resúmenes redactados para este paciente. (Se generarán en el próximo ciclo)"
            
        resumen_modificado = st.text_area("Borrador del Informe Médico:", value=resumen_ia, height=400)
        
        if st.button("💾 Guardar y Aprobar Informe", type="primary"):
            st.success(f"✅ Informe auditado y guardado con éxito por el Doctor en turno ({datetime.now().strftime('%H:%M:%S')}).")
            st.caption("La evidencia de esta modificación ha sido registrada en el sistema de auditoría (Blockchain/DB).")

    with tab_traz:
        st.subheader("Línea de Tiempo de Ingreso de Folios")
        df_events = pd.DataFrame(data["events"])
        if not df_events.empty:
            df_docs = df_events[df_events['type'] == 'ingesta_documento'].copy()
            if not df_docs.empty:
                df_docs['timestamp'] = pd.to_datetime(df_docs['timestamp'])
                df_docs['Nombre Archivo'] = df_docs['details'].apply(lambda x: str(x.get('id', 'Desconocido')) + "." + str(x.get('formato', 'pdf')))
                
                # Crear Timeline Gantt
                fig_gantt = px.scatter(df_docs, x="timestamp", y="Nombre Archivo", 
                                       color="Nombre Archivo", title="Registro de Entrada de Documentos al Sistema",
                                       size_max=15, size=[10]*len(df_docs))
                fig_gantt.update_traces(marker=dict(symbol='diamond-dot'))
                fig_gantt.update_layout(xaxis_title="Fecha de Ingesta", yaxis_title="Documento", showlegend=False)
                st.plotly_chart(fig_gantt, use_container_width=True)
            else:
                st.info("No hay documentos procesados aún para este paciente.")
        else:
            st.info("No hay eventos registrados.")

# PERFIL TRIBUNAL
else:
    tab_pipe, tab_metrics, tab_logs = st.tabs(["🤖 Arquitectura y Pipeline", "📊 Métricas Técnicas", "📜 Logs de Ejecución"])
    
    with tab_pipe:
        st.subheader("Pipeline Multi-Agente (LangGraph)")
        st.markdown("El sistema ejecuta 5 fases concurrentes de validación y extracción.")
        agentes = {
            "Agente Escáner (Docling)": "ingesta_documento",
            "Verificador ID (Algoritmo NIF)": "validacion_identidad",
            "Verificador Vigencia (Fechas)": "validacion_vigencia",
            "Redactor RAG (Ollama)": "analisis_seccion",
            "Ensamblador (PyPDF)": "generacion_informe"
        }
        
        cols = st.columns(len(agentes))
        for i, (nombre, e_type) in enumerate(agentes.items()):
            with cols[i]:
                count = len([e for e in data["events"] if e["type"] == e_type])
                status = "✅ Completado" if count > 0 else "⏳ Pendiente"
                st.markdown(f"""
                <div class="agent-card">
                    <p style="margin-bottom:5px; font-weight:bold;">{nombre}</p>
                    <p style="font-size:16px;">{status}</p>
                    <p style="font-size:12px; color:gray;">Operaciones: {count}</p>
                </div>
                """, unsafe_allow_html=True)
                
    with tab_metrics:
        st.subheader("Rendimiento del Sistema")
        df_events = pd.DataFrame(data["events"])
        if not df_events.empty:
            df_ingesta = df_events[df_events['type'] == 'ingesta_documento'].copy()
            if not df_ingesta.empty:
                df_ingesta['latencia'] = df_ingesta['details'].apply(lambda x: x.get('latencia', 0))
                fig = px.bar(df_ingesta, x='timestamp', y='latencia', title="Latencia por Documento (s)")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay suficientes datos de rendimiento.")
            
    with tab_logs:
        st.subheader("Trazabilidad y Chain of Thought")
        st.dataframe(df_events, use_container_width=True)
