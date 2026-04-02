import streamlit as st
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import os

# Configuración de página
st.set_page_config(
    page_title="ClinDoc Agent | Control de Auditoría",
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
def load_data():
    path = "dashboard_data.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

data = load_data()

# --- HEADER ---
col_t1, col_t2 = st.columns([4, 1])
with col_t1:
    st.title("🛡️ ClinDoc Agent | Centro de Control de Auditoría")
    st.markdown("*Plataforma Multi-Agente para la Validación de Expedientes Clínicos*")
with col_t2:
    if st.button("🔄 Refrescar Datos", use_container_width=True):
        st.rerun()

if not data:
    st.warning("⚠️ No se detectan datos de ejecución. Inicia el orquestador `run_clindoc.py` para comenzar.")
    st.stop()

# --- KPIs SUPERIORES ---
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("📄 Documentos", data["kpis"]["total_docs"])
kpi2.metric("⏱️ Tiempo Total", f"{data['kpis']['total_time']}s")
kpi3.metric("🎯 Confianza", f"{round(data['kpis']['avg_confidence']*100, 1)}%")
kpi4.metric("🚨 Riesgos", data["kpis"]["critical_risks"], delta_color="inverse")

st.markdown("---")

# --- TABS PRINCIPALES ---
tab1, tab2, tab3 = st.tabs(["🕒 Trazabilidad en Vivo", "🤖 Pipeline de Agentes", "📊 Análisis Técnico"])

with tab1:
    col_a, col_b = st.columns([2, 1])
    
    with col_a:
        st.subheader("📜 Historial de Eventos")
        df_events = pd.DataFrame(data["events"])
        if not df_events.empty:
            df_events['timestamp'] = pd.to_datetime(df_events['timestamp'])
            
            # Extraer información útil de los detalles para la tabla
            def extract_info(row):
                details = row['details']
                if row['type'] == 'ingesta_documento':
                    return f"📄 {details.get('formato', '?').upper()} | {details.get('id', 'N/A')}"
                elif row['type'] == 'analisys_seccion' or row['type'] == 'analisis_seccion':
                    return f"🧠 Sección: {details.get('seccion', 'N/A')} (Conf: {details.get('confianza', 0)})"
                return str(details)[:50]

            df_display = df_events.copy()
            df_display['Resumen'] = df_display.apply(extract_info, axis=1)
            
            # Reordenar y mostrar
            st.dataframe(
                df_display[['timestamp', 'type', 'Resumen']].sort_values('timestamp', ascending=False), 
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Sin eventos registrados.")

    with col_b:
        st.subheader("⚠️ Estado de Riesgo")
        risks = [e["details"].get("estado_riesgo", "SAFE") for e in data["events"] if "estado_riesgo" in e["details"]]
        if risks:
            risk_counts = pd.Series(risks).value_counts()
            fig_pie = px.pie(values=risk_counts.values, names=risk_counts.index, 
                            color_discrete_sequence=["#10b981", "#ef4444", "#f59e0b"],
                            hole=0.4)
            fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Esperando análisis de riesgos...")

with tab2:
    st.subheader("⚙️ Estado de los Agentes en el Pipeline")
    
    # Simulación de estados por agente basado en eventos
    agentes = {
        "Agente Escáner": "ingesta_documento",
        "Agente Verificador ID": "validacion_identidad",
        "Agente de Vigencia": "validacion_vigencia",
        "Agente Redactor (RAG)": "analisis_seccion",
        "Agente Ensamblador": "generacion_informe"
    }
    
    cols = st.columns(len(agentes))
    for i, (nombre, e_type) in enumerate(agentes.items()):
        with cols[i]:
            count = len([e for e in data["events"] if e["type"] == e_type])
            status = "✅ Activo" if count > 0 else "💤 Esperando"
            st.markdown(f"""
            <div class="agent-card">
                <p style="margin-bottom:5px; font-weight:bold;">{nombre}</p>
                <p style="font-size:20px;">{status}</p>
                <p style="font-size:12px; color:gray;">Tareas: {count}</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("### 🔍 Detalle por Agente")
    sel_agent = st.selectbox("Selecciona un agente para ver sus logs:", list(agentes.keys()))
    agent_events = df_events[df_events['type'] == agentes[sel_agent]]
    if not agent_events.empty:
        st.table(agent_events[['timestamp', 'details']].tail(5))
    else:
        st.info("No hay logs recientes para este agente.")

with tab3:
    st.subheader("📈 Rendimiento y Latencia")
    df_ingesta = df_events[df_events['type'] == 'ingesta_documento'].copy()
    if not df_ingesta.empty:
        df_ingesta['latencia'] = df_ingesta['details'].apply(lambda x: x.get('latencia', 0))
        fig = px.area(df_ingesta, 
                     x='timestamp', y='latencia',
                     title="Latencia de Procesamiento (Segundos)",
                     line_shape="spline", color_discrete_sequence=["#1e3a8a"])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de latencia disponibles.")

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3774/3774293.png", width=80)
    st.header("Soberanía del Dato")
    st.info("🛡️ Todos los procesos se ejecutan en hardware local para garantizar cumplimiento RGPD.")
    st.write("---")
    st.markdown(f"""
    **Configuración Actual:**
    - **LLM:** Llama 3.2 (Local)
    - **Embedding:** all-MiniLM-L6-v2
    - **DB Vectorial:** Qdrant
    - **Sesión:** {datetime.now().strftime('%H:%M:%S')}
    """)
    st.write("---")
    st.caption("ClinDoc Agent v4.0 - TFM 2026")

