import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="ClinDoc v5 | Opcion 2",
    page_icon="📄",
    layout="wide",
)

st.title("ClinDoc Agent v5 - Opcion 2")
st.caption("Caso de uso acotado: baja laboral + validacion documental + informe guiado")

dash_path = Path("dashboard_data_option2.json")
if not dash_path.exists():
    st.warning("No se encontro 'dashboard_data_option2.json'. Ejecuta primero run_clindoc_option2.py")
    st.stop()

with dash_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Documentos", data.get("kpis", {}).get("total_docs", 0))
k2.metric("Tiempo total", f"{data.get('kpis', {}).get('total_time', 0)} s")
k3.metric("Confianza media", f"{round(data.get('kpis', {}).get('avg_confidence', 0) * 100, 1)}%")
k4.metric("Riesgos criticos", data.get("kpis", {}).get("critical_risks", 0))

events = pd.DataFrame(data.get("events", []))
if events.empty:
    st.info("No hay eventos en la telemetria.")
    st.stop()

events["timestamp"] = pd.to_datetime(events["timestamp"])

tab1, tab2 = st.tabs(["Eventos", "Latencia"])

with tab1:
    st.subheader("Trazabilidad")
    st.dataframe(events.sort_values("timestamp", ascending=False), use_container_width=True)

with tab2:
    ing = events[events["type"] == "ingesta_documento"].copy()
    if not ing.empty:
        ing["latencia"] = ing["details"].apply(lambda x: x.get("latencia", 0))
        fig = px.line(
            ing,
            x="timestamp",
            y="latencia",
            title="Latencia de ingesta por documento",
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay eventos de ingesta para graficar.")

st.markdown("---")
st.write(f"Sesion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
