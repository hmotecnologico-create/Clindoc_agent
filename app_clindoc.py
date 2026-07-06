import streamlit as st
import json
import re
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
from pathlib import Path
import fitz  # PyMuPDF: render del folio + resaltado por coordenadas (Deep Linking forense)

# Importaciones de los nuevos módulos
from historial_clinico_visual import HistorialClinicoVisual
from chat_asistente_medico import ChatAsistenteMedico, TipoMensaje



from utils.ui_helpers import _chunking_folio, render_folio_resaltado, _campos_guion, _validar_campo, _periodo_historia, generar_pdf_historia, registrar_validacion_facultativo

# Configuración de página
st.set_page_config(
    page_title="ClinDoc Agent | Multi-Paciente",
    page_icon="🛡️",
    layout="wide"
)


# --- ESTILO CLÍNICO E INSTITUCIONAL ---
st.markdown("""
    <style>
    /* Estilos Clínicos - Severo y Utililitario */
    .main { background-color: #FFFFFF; font-family: 'Roboto', 'Arial', sans-serif; }
    
    /* Tipografía y métricas (Sobrias) */
    [data-testid="stMetricValue"] { 
        font-size: 28px; 
        color: #1a202c; 
        font-weight: bold;
    }
    [data-testid="stMetricLabel"] {
        color: #4a5568;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 12px;
    }
    
    /* Pestañas estilizadas (Flat Design Institucional) */
    .stTabs [data-baseweb="tab-list"] { 
        gap: 0px; 
        padding-bottom: 0px;
        border-bottom: 2px solid #cbd5e0;
        background-color: #f7fafc;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: transparent;
        border-radius: 0px;
        border-right: 1px solid #e2e8f0;
        padding: 10px 20px;
        font-weight: 600;
        font-size: 14px;
        color: #4a5568;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #edf2f7;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #FFFFFF; 
        border-top: 3px solid #005B96; 
        border-bottom: 2px solid #FFFFFF;
        color: #005B96;
    }
    
    /* Tarjetas de datos (Flat sin sombras exageradas) */
    .premium-card {
        background: #FFFFFF;
        padding: 20px;
        border: 1px solid #cbd5e0;
        border-left: 6px solid #005B96;
        margin-bottom: 15px;
    }
    
    /* Botones principales */
    div.stButton > button {
        border-radius: 4px;
        font-weight: 600;
        border: 1px solid #cbd5e0;
        background-color: #f7fafc;
        color: #2d3748;
    }
    div.stButton > button:hover {
        border-color: #005B96;
        color: #005B96;
    }
    div.stButton > button[kind="primary"] {
        background-color: #005B96;
        color: white;
        border: none;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #003f6b;
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
    perfil = st.radio("Seleccione Perfil:", ["Doctor (Facultativo)", "Tribunal Académico"])
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
    st.header("Chat Asistente")
    if 'chat_asistente' not in st.session_state:
        st.session_state.chat_asistente = ChatAsistenteMedico()
        
    chat = st.session_state.chat_asistente
    if not chat.conversacion_actual or chat.conversacion_actual.paciente_nif != nif_seleccionado:
        _ = chat.iniciar_conversacion(f"inf_{nif_seleccionado}", nif_seleccionado, data["nombre"])
        
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
    
    # --- RELOJ REGRESIVO ---
    if os.path.exists("eta.txt"):
        try:
            target_time = float(open("eta.txt").read().strip())
            import time
            if time.time() < target_time:
                js_code = f"""
                <div id="countdown" style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 16px; font-weight: bold; color: #856404; padding: 12px; background-color: #fff3cd; border-radius: 8px; text-align: center; border: 1px solid #ffeeba; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);"></div>
                <script>
                var targetTime = {target_time} * 1000;
                var x = setInterval(function() {{
                    var now = new Date().getTime();
                    var distance = targetTime - now;
                    if (distance < 0) {{
                        clearInterval(x);
                        document.getElementById("countdown").innerHTML = "✅ Procesamiento finalizado (Estimación). Por favor, haz clic en 'Refrescar Datos'.";
                        document.getElementById("countdown").style.backgroundColor = "#d4edda";
                        document.getElementById("countdown").style.color = "#155724";
                        document.getElementById("countdown").style.borderColor = "#c3e6cb";
                    }} else {{
                        var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                        var seconds = Math.floor((distance % (1000 * 60)) / 1000);
                        document.getElementById("countdown").innerHTML = "⚙️ <b>PROCESANDO EXPEDIENTE:</b> Tiempo estimado restante: " + minutes + "m " + seconds + "s";
                    }}
                }}, 1000);
                </script>
                """
                import streamlit.components.v1 as components
                components.html(js_code, height=70)
        except:
            pass
    
    DEMO_PATIENTS = {
        "25988000R": {"edad": 45, "sexo": "Masculino", "telefono": "654 321 987", "direccion": "Calle Mayor 12, 3ºB, Madrid"},
        "52880483X": {"edad": 38, "sexo": "Femenino", "telefono": "698 765 432", "direccion": "Avenida de la Libertad 45, Barcelona"}
    }
    demo_data = DEMO_PATIENTS.get(data['nif'], {"edad": "N/A", "sexo": "N/A", "telefono": "N/A", "direccion": "N/A"})
    
    # Perfil del Paciente (Datos Personales Básicos - Estilo Premium)
    st.markdown(f"""
    <div class="premium-card">
        <h2 style="margin-top:0; color:#005B96;">{data['nombre']}</h2>
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; color:#2d3748;">
            <div style="flex:1; min-width:200px;">
                <p><b>NIF:</b> <span style="background:#e0f2fe; padding:2px 8px; border-radius:4px; font-family:monospace;">{data['nif']}</span></p>
                <p><b>Edad:</b> {demo_data['edad']} años</p>
            </div>
            <div style="flex:1; min-width:200px;">
                <p><b>Sexo:</b> {demo_data['sexo']}</p>
                <p><b>Estado:</b> <span style="color:#047857; font-weight:bold;">● Activo</span></p>
            </div>
            <div style="flex:1; min-width:200px;">
                <p><b>Teléfono:</b> {demo_data['telefono']}</p>
                <p><b>Dirección:</b> {demo_data['direccion']}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("") # Espacio
    
    # --- ALERTA NIF ---
    eventos_nif = [e for e in data["events"] if e["type"] == "validacion_identidad"]
    if eventos_nif:
        ult_evento = eventos_nif[-1]
        if ult_evento["details"].get("valido", False):
            st.success("✅ **Validación NIF:** Identidad verificada con el documento.")
        else:
            errores = ult_evento["details"].get("errores", [])
            if not errores:
                errores_txt = "No se encontró el NIF en el documento."
            elif len(errores) > 3:
                errores_txt = " | ".join(errores[:3]) + f" ... (y {len(errores) - 3} alertas más ocultas por volumen)"
            else:
                errores_txt = " | ".join(errores)
            
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

# --- KPIs SUPERIORES (Solo para Tribunal) ---
if perfil == "Tribunal Académico":
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("📄 Documentos", data["kpis"]["total_docs"])
    kpi2.metric("⏱️ Tiempo Total", f"{data['kpis']['total_time']}s")
    kpi3.metric("🎯 Confianza", f"{round(data['kpis']['avg_confidence']*100, 1)}%")
    kpi4.metric("🚨 Riesgos", data["kpis"]["critical_risks"], delta_color="inverse")
    st.markdown("---")

# PERFIL DOCTOR
if perfil == "Doctor (Facultativo)":
    # MODAL PARA VER DOCUMENTOS (Pop-ups nativos)
    @st.dialog("Visor de Documento Original", width="large")
    def mostrar_documento(ruta_archivo, fragmento=None):
        if not ruta_archivo.exists():
            matches = list(ruta_archivo.parent.glob(f"{ruta_archivo.stem}.*"))
            if matches:
                ruta_archivo = matches[0]
            else:
                st.warning(f"💡 **Fuente Externa:** El asistente ha citado una guía médica o referencia literaria ('{ruta_archivo.name}') que no forma parte de los documentos físicos del expediente del paciente.")
                return
                
        if ruta_archivo.exists():
            ext = ruta_archivo.suffix.lower()
            if ext == ".pdf":
                st.markdown(f"**Visualizando:** `{ruta_archivo.name}`")
                
                # --- DEEP LINKING FORENSE (Bounding Box) ---
                if fragmento:
                    try:
                        from normalizador_pdf import localizar_en_pdf
                        import fitz
                        pagina, rects = localizar_en_pdf(str(ruta_archivo), fragmento)
                        if pagina >= 0:
                            d = fitz.open(str(ruta_archivo))
                            pg = d[pagina]
                            for r in rects:
                                pg.draw_rect(r, color=(1,0,0), fill=(1,1,0), fill_opacity=0.3)
                            # Renderizar a mayor resolución (zoom 2x) para evitar pixelado o distorsión
                            mat = fitz.Matrix(2, 2)
                            img_bytes = pg.get_pixmap(matrix=mat).tobytes("png")
                            st.image(img_bytes, caption=f"Página {pagina + 1} (Fragmento Resaltado)", use_container_width=True)
                            return
                    except Exception as e:
                        st.warning("No se pudo generar el resaltado (Deep Linking). Mostrando documento original.")
                
                # --- PDF COMPLETO (Fallback si no hay fragmento) ---
                import base64
                with open(ruta_archivo, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#view=FitH" width="100%" height="600" type="application/pdf" style="border: none;"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            elif ext in [".png", ".jpg", ".jpeg"]:
                st.image(str(ruta_archivo), use_container_width=True)
            elif ext == ".docx":
                import docx
                doc = docx.Document(ruta_archivo)
                texto = "\n\n".join([p.text for p in doc.paragraphs])
                st.markdown(f"**Contenido DOCX:**\n\n{texto}")
                # Imagen diagnóstica asociada (p. ej. la radiografía del mismo estudio de radiología).
                # No es analizada por el pipeline semántico; se muestra para verificación visual del facultativo.
                imagen_asociada = ruta_archivo.with_name(f"{ruta_archivo.stem}_img.png")
                if imagen_asociada.exists():
                    st.divider()
                    st.caption("🖼️ Imagen diagnóstica asociada (verificación visual)")
                    st.image(str(imagen_asociada), use_container_width=True)
            else:
                st.text_area("Contenido:", value=ruta_archivo.read_text(encoding="utf-8", errors="ignore"), height=400, disabled=True)
        else:
            st.error("El documento no se encuentra en el servidor.")

    # PESTAÑAS SEPARADAS
    tab_historia, tab_alta, tab_tramite, tab_traz = st.tabs([
        "Historia Clínica", 
        "Informes de Alta", 
        "Trámite Baja Laboral (RD 1060/2022)",
        "Trazabilidad Documental"
    ])
    
    # Procesar y dividir secciones
    resumen_historia = ""
    resumen_alta = ""
    
    for ev in data["events"]:
        if ev["type"] == "analisis_seccion":
            texto_seccion = (ev['details'].get('texto', '') or '').strip()
            if texto_seccion:
                if not texto_seccion.lstrip().startswith("#"):
                    texto_seccion = f"### {ev['details'].get('seccion', 'Sección')}\n{texto_seccion}"
                
                # Clasificar según las fuentes citadas
                if "ALTA_" in texto_seccion:
                    resumen_alta += texto_seccion + "\n\n"
                else:
                    resumen_historia += texto_seccion + "\n\n"
                    
    def renderizar_texto_con_botones(texto, nif, seccion="s"):
        """Renderiza Markdown y agrupa en recuadros los bloques que tienen fuentes, pegando los botones a la línea exacta."""
        ruta_docs = Path(f"datos/expedientes/{nif}")
        bloques = texto.split("\n\n")
        
        for idx_b, bloque in enumerate(bloques):
            if not bloque.strip(): continue
            
            if "[Fuente:" in bloque:
                # Mostrar en un recuadro (container con borde)
                with st.container(border=True):
                    lineas = bloque.split("\n")
                    for idx_l, linea in enumerate(lineas):
                        if not linea.strip(): continue
                        
                        citas_raw = re.findall(r'\[Fuente:\s*([^\]#]+?)\s*(?:#[^\]]+)?\]', linea)
                        fuentes_unicas = list(set(citas_raw))
                        
                        texto_limpio = re.sub(r'\[Fuente:\s*([^\]#]+?)\s*(?:#[^\]]+)?\]', '', linea)
                        
                        # Reemplazar viñetas dobles o markdown roto si ocurre al separar por saltos
                        st.markdown(texto_limpio)
                        
                        if fuentes_unicas:
                            num_cols = min(len(fuentes_unicas), 4)
                            cols = st.columns(num_cols)
                            for i, arch in enumerate(fuentes_unicas):
                                with cols[i % num_cols]:
                                    if st.button(f"📄 {arch}", key=f"btn_{seccion}_{nif}_{idx_b}_{idx_l}_{i}", help="Abrir original", use_container_width=True):
                                        mostrar_documento(ruta_docs / arch, fragmento=linea)
            else:
                st.markdown(bloque)
            
            st.write("") # Espaciador

    with tab_historia:
        st.subheader("Evolución y Diagnósticos Previos")
        if resumen_historia:
            renderizar_texto_con_botones(resumen_historia, nif_seleccionado, seccion="historia")
        else:
            st.info("No hay información clínica general disponible.")
            
    with tab_alta:
        st.subheader("Resumen de Informes de Alta Médica")
        if resumen_alta:
            renderizar_texto_con_botones(resumen_alta, nif_seleccionado, seccion="alta")
        else:
            st.info("El paciente no tiene eventos de alta registrados.")
            
    with tab_tramite:
        st.subheader("Trámite de Incapacidad Temporal (RD 1060/2022)")
        st.info("Esta sección evalúa estrictamente la **Vigencia Regulatoria** de los documentos presentados para justificar la baja actual. Los documentos antiguos siguen en el historial, pero pueden no tener validez administrativa para este trámite.")
        
        eventos_vigencia = [e for e in data.get("events", []) if e["type"] == "validacion_vigencia"]
        
        if not eventos_vigencia:
            st.warning("No se encontraron eventos de validación de vigencia.")
        else:
            # Los errores de vigencia se guardan en el estado (errores) o en los detalles si se registran
            st.markdown("### Análisis de Vigencia Documental")
            doc_vigentes = []
            doc_caducados = []
            
            # Recorrer todos los folios para ver cuáles pasaron la validación de vigencia
            historial_v = HistorialClinicoVisual(f"datos/expedientes/{nif_seleccionado}")
            _ = historial_v.cargar_expediente(nif_seleccionado, data["nombre"])
            
            from datetime import datetime, timedelta
            hoy = datetime.now()
            
            for ev in historial_v.eventos:
                if ev.fecha >= (hoy - timedelta(days=180)):
                    doc_vigentes.append(ev)
                else:
                    doc_caducados.append(ev)
                    
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.success(f"Vigentes para IT (últimos 6 meses): {len(doc_vigentes)} documentos")
                for d in doc_vigentes:
                    st.markdown(f"- `{d.fuente}` ({d.fecha.strftime('%d/%m/%Y')})")
            
            with col_v2:
                st.error(f"SIN VIGENCIA para IT (> 6 meses): {len(doc_caducados)} documentos")
                for d in doc_caducados:
                    st.markdown(f"- `{d.fuente}` ({d.fecha.strftime('%d/%m/%Y')}) - *Válido clínicamente*")
                    
            st.divider()
            st.markdown("#### Resolución Administrativa")
            if doc_vigentes:
                st.success("El paciente ha aportado pruebas médicas recientes válidas para continuar el trámite de IT.")
            else:
                st.error("BLOQUEO ADMINISTRATIVO: El paciente no ha aportado pruebas médicas recientes (menos de 6 meses) que justifiquen la baja actual. Se requiere solicitar informe actualizado.")

    with tab_traz:
        st.subheader("Trazabilidad Cronológica de Folios")
        st.caption("Cada folio del expediente organizado cronológicamente.")
        
        historial_t = HistorialClinicoVisual(f"datos/expedientes/{nif_seleccionado}")
        _ = historial_t.cargar_expediente(nif_seleccionado, data["nombre"])
        if historial_t.eventos:
            filas = [{"Fecha": e.fecha.strftime("%d/%m/%Y"),
                      "_orden": e.fecha,
                      "Tipo": e.tipo.capitalize(),
                      "Documento (Clickable)": e.fuente} for e in historial_t.eventos]
            df_fol = (pd.DataFrame(filas).sort_values("_orden", ascending=False).drop(columns=["_orden"])
                      .drop_duplicates().reset_index(drop=True))
            
            st.dataframe(df_fol, use_container_width=True, hide_index=True)
        else:
            st.info("No hay folios procesados.")

# PERFIL TRIBUNAL
else:
    tab_pipe, tab_metrics, tab_logs = st.tabs(["🤖 Arquitectura y Pipeline", "📊 Métricas Técnicas", "📜 Logs de Ejecución"])
    
    with tab_pipe:
        st.subheader("Pipeline Multi-Agente (LangGraph)")
        st.markdown("El sistema ejecuta 5 agentes especializados en un **grafo de estados (LangGraph)** con ciclo de autocorrección.")
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
