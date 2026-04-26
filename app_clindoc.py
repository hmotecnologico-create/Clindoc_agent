import streamlit as st
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import os

# Configuración de página
st.set_page_config(page_title="ClinDoc Agent | Dashboard Auditoría", layout="wide")

# Estilo personalizado
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# Cargar datos del Auditor
def load_data():
    path = "dashboard_data.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

data = load_data()

st.title("🏥 ClinDoc Agent | Auditoría Soberana")
st.subheader("Dashboard de Control de Calidad y Trazabilidad")

if data:
    # --- FILA 1: KPIs ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Documentos Auditados", data["kpis"]["total_docs"])
    with col2:
        st.metric("Tiempo Total (s)", f"{data['kpis']['total_time']}s")
    with col3:
        st.metric("Confianza Media", f"{round(data['kpis']['avg_confidence']*100, 1)}%")
    with col4:
        st.metric("Riesgos Críticos", data["kpis"]["critical_risks"], delta_color="inverse")

    # --- FILA 2: Gráficas y Eventos ---
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.write("### Historial de Eventos del Agente")
        df_events = pd.DataFrame(data["events"])
        if not df_events.empty:
            df_events['timestamp'] = pd.to_datetime(df_events['timestamp'])
            st.dataframe(df_events, use_container_width=True)
            
            # Gráfica de Latencia
            fig = px.line(df_events[df_events['type'] == 'ingesta_documento'], 
                         x='timestamp', y=lambda x: [d.get('latencia', 0) for d in df_events['details'] if 'latencia' in d],
                         title="Latencia de Ingesta (Segundos)",
                         line_shape="spline", render_mode="svg")
            # st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay eventos registrados aún.")

    with c2:
        st.write("### Estado de Riesgo")
        risks = [e["details"].get("estado_riesgo", "SAFE") for e in data["events"] if "estado_riesgo" in e["details"]]
        if risks:
            risk_counts = pd.Series(risks).value_counts()
            fig_pie = px.pie(values=risk_counts.values, names=risk_counts.index, 
                            color_discrete_sequence=["#2ecc71", "#e74c3c", "#f1c40f"])
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.write("Esperando datos de análisis...")

else:
    st.warning("No se encontró el archivo 'dashboard_data.json'. Ejecuta 'run_clindoc.py' primero para generar datos.")

# Sidebar para control
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3774/3774293.png", width=100)
    st.write("### Panel de Control")
    st.button("Actualizar Dashboard")
    st.write("---")
    st.write("**Modelo:** Llama 3.2 (4-bit)")
    st.write("**Motor:** LangGraph + Docling")
    st.write("**Estado:** Conectado a Qdrant Local")
