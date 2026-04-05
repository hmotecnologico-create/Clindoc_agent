"""
DASHBOARD DEL MÉDICO - REVISIÓN DE HISTORIAS CLÍNICAS
=======================================================
Interfaz para que el médico revise, valide y modifique
los informes generados por la IA.

Este es el flujo real de trabajo del médico:
1. Buscar paciente
2. Ver informe generado por IA
3. Revisar cada sección
4. Aprobar / Modificar / Añadir hallazgos
5. Finalizar auditoría

Módulo crítica para Capítulo 5 y 6 del TFM.
"""

import streamlit as st
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import sys

# Imports del sistema
from modulo_auditoria import GestorAuditorias, TipoValidacion, CategoriaError, ValidacionSeccion
from run_clindoc import OrquestadorLangGraph, GuionInforme

# Configuración
st.set_page_config(
    page_title="ClinDoc Agent | Dashboard Médico",
    page_icon="🏥",
    layout="wide"
)

# Estilos CSS
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton > button {
        width: 100%;
        border-radius: 5px;
    }
    .seccion-auditar {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .badge-aprobado {
        background-color: #28a745;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
    }
    .badge-pendiente {
        background-color: #ffc107;
        color: black;
        padding: 5px 10px;
        border-radius: 5px;
    }
    .badge-modificado {
        background-color: #dc3545;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)


class DashboardMedico:
    """
    Dashboard para revisión de informes clínicos.
    
    FLUJO DEL MÉDICO:
    1. Seleccionar/Buscar paciente
    2. Ver informe IA (historia clínica generada)
    3. Revisar cada sección:
       - ✓ Aprobar si está correcto
       - ✗ Modificar si hay errores
       - + Añadir si la IA omitió algo
    4. Ver métricas de calidad (matriz de confusión)
    """
    
    def __init__(self):
        self.gestor = GestorAuditorias()
        self.informe_actual = None
    
    def cargar_datos(self):
        """Carga datos iniciales"""
        if 'pacientes' not in st.session_state:
            st.session_state.pacientes = self._cargar_pacientes()
        if 'informe_actual' not in st.session_state:
            st.session_state.informe_actual = None
    
    def _cargar_pacientes(self) -> List[Dict]:
        """Carga lista de pacientes con informes"""
        pacientes = []
        gestor = GestorAuditorias("datos/auditorias")
        
        for archivo in Path("datos/auditorias").glob("inf_*.json"):
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pacientes.append({
                        "informe_id": data.get("informe_id", ""),
                        "nif": data.get("paciente_nif", ""),
                        "nombre": data.get("paciente_nombre", ""),
                        "fecha": data.get("fecha_generacion", ""),
                        "estado": data.get("estado", "pendiente")
                    })
            except:
                pass
        
        return pacientes
    
    def mostrar_sidebar(self):
        """Muestra el menú lateral"""
        with st.sidebar:
            st.title("🏥 ClinDoc Agent")
            st.markdown("---")
            
            st.markdown("### 📋 Menú Principal")
            opcion = st.radio("Navegación", [
                "🔍 Buscar Paciente",
                "📋 Informes Pendientes",
                "📊 Métricas de Calidad",
                "⚙️ Configuración"
            ])
            
            st.markdown("---")
            st.markdown("### ℹ️ Estado del Sistema")
            st.success("● Sistema Activo")
            st.info(f"● Ollama: gemma3:4b")
            st.info(f"● Qdrant: Local")
            
            return opcion
    
    def buscar_paciente(self):
        """Buscar paciente por NIF o nombre"""
        st.header("🔍 Buscar Paciente")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            busqueda = st.text_input("Buscar por NIF o Nombre:", placeholder="12345678Z o Juan Pérez")
        with col2:
            st.write("")  # Espaciador
            st.write("")  # Espaciador
            tipo_busqueda = st.radio("Tipo", ["NIF", "Nombre"], horizontal=True)
        
        # Filtrar pacientes
        if busqueda:
            pacientes_filtrados = [
                p for p in st.session_state.pacientes
                if (tipo_busqueda == "NIF" and busqueda.upper() in p["nif"].upper()) or
                   (tipo_busqueda == "Nombre" and busqueda.upper() in p["nombre"].upper())
            ]
        else:
            pacientes_filtrados = st.session_state.pacientes
        
        # Mostrar resultados
        st.markdown("### Resultados")
        
        if pacientes_filtrados:
            for p in pacientes_filtrados:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.markdown(f"**{p['nombre']}**")
                        st.caption(f"NIF: {p['nif']}")
                    with col2:
                        st.caption(f"Fecha: {p['fecha'][:10] if p['fecha'] else 'N/A'}")
                    with col3:
                        estado = p.get("estado", "pendiente")
                        badge = {
                            "pendiente": "badge-pendiente",
                            "auditado": "badge-modificado",
                            "aprobado": "badge-aprobado"
                        }.get(estado, "badge-pendiente")
                        st.markdown(f"<span class='{badge}'>{estado.upper()}</span>", 
                                   unsafe_allow_html=True)
                    
                    if st.button(f"📝 Revisar Informe", key=p["informe_id"]):
                        st.session_state.informe_actual = p["informe_id"]
                        st.rerun()
                    
                    st.markdown("---")
        else:
            st.info("No se encontraron pacientes")
    
    def mostrar_informe(self, informe_id: str):
        """Muestra el informe para revisión"""
        
        # Cargar informe
        informe = self.gestor.cargar_informe(informe_id)
        
        if not informe:
            st.error("Informe no encontrado")
            return
        
        # Header
        st.header(f"📋 Historia Clínica: {informe.paciente_nombre}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("NIF", informe.paciente_nif)
        with col2:
            st.metric("Fecha Generación", informe.fecha_generacion[:10])
        with col3:
            estado = informe.estado
            if estado == "pendiente":
                st.warning("⏳ Pendiente de Auditoría")
            elif estado == "auditado":
                st.info("✏️ Auditado (con modificaciones)")
            else:
                st.success("✓ Aprobado")
        
        st.markdown("---")
        
        # Secciones del informe
        st.markdown("### 📄 Secciones del Informe")
        
        # Obtener secciones
        secciones = informe.secciones if hasattr(informe, 'secciones') else {}
        
        if not secciones:
            st.warning("No hay secciones disponibles")
            return
        
        # Formulario de auditoría
        with st.form(f"auditoria_{informe_id}"):
            validaciones = []
            
            for titulo, contenido in secciones.items():
                with st.container():
                    st.markdown(f"""
                    <div class="seccion-auditar">
                        <h4>{titulo}</h4>
                        <p>{contenido[:500]}{'...' if len(contenido) > 500 else ''}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Opciones de validación
                    opcion = st.radio(
                        f"Validar: {titulo}",
                        ["✓ Aprobar", "✗ Modificar", "+ Añadir Hallazgo"],
                        key=f"val_{titulo}",
                        horizontal=True
                    )
                    
                    notas = ""
                    texto_modificado = ""
                    
                    if opcion == "✗ Modificar":
                        texto_modificado = st.text_area(
                            "Texto corregido:",
                            value=contenido,
                            key=f"mod_{titulo}"
                        )
                        categoria = st.selectbox(
                            "Tipo de error:",
                            ["Falso Positivo", "Error Fecha", "Error NIF", "Alucinación", "Otro"],
                            key=f"cat_{titulo}"
                        )
                    elif opcion == "+ Añadir Hallazgo":
                        notas = st.text_area(
                            "Nuevo hallazgo (lo que la IA no vio):",
                            key=f"nuevo_{titulo}"
                        )
                    
                    validaciones.append({
                        "seccion": titulo,
                        "opcion": opcion,
                        "texto_modificado": texto_modificado,
                        "notas": notas
                    })
                    
                    st.markdown("---")
            
            # Botones de acción
            col1, col2 = st.columns(2)
            with col1:
                submit_auditar = st.form_submit_button("💾 Guardar Auditoría", type="primary")
            with col2:
                submit_aprobar = st.form_submit_button("✓ Aprobar Informe Completo")
        
        # Procesar envío
        if submit_auditar:
            for val in validaciones:
                if val["opcion"] == "✓ Aprobar":
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.APROBADO,
                        texto_original=secciones.get(val["seccion"], "")
                    )
                elif val["opcion"] == "✗ Modificar":
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.MODIFICADO,
                        texto_original=secciones.get(val["seccion"], ""),
                        texto_modificado=val["texto_modificado"],
                        notas_medico=val["notas"],
                        categoria_error=CategoriaError.FALSO_POSITIVO
                    )
                else:  # Añadir
                    v = ValidacionSeccion(
                        seccion=val["seccion"],
                        validacion=TipoValidacion.NUEVOhallazgo,
                        texto_original="",
                        notas_medico=val["notas"],
                        categoria_error=CategoriaError.OMISION
                    )
                
                self.gestor.registrar_validacion(informe_id, v)
            
            st.success("✓ Auditoría guardada")
            st.rerun()
        
        if submit_aprobar:
            self.gestor.aprobar_informe(informe_id, "Aprobado por el médico")
            st.success("✓ Informe aprobado")
            st.rerun()
    
    def mostrar_informes_pendientes(self):
        """Muestra lista de informes pendientes"""
        st.header("📋 Informes Pendientes de Auditoría")
        
        pendientes = self.gestor.listar_informes_pendientes()
        
        if pendientes:
            for p in pendientes:
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    with col1:
                        st.markdown(f"**{p['paciente']}**")
                        st.caption(f"NIF: {p['nif']}")
                    with col2:
                        st.caption(f"Fecha: {p['fecha'][:10] if p['fecha'] else 'N/A'}")
                    with col3:
                        st.caption("Estado: Pendiente")
                    with col4:
                        if st.button("Revisar", key=f"pen_{p['informe_id']}"):
                            st.session_state.informe_actual = p["informe_id"]
                            st.rerun()
                    st.markdown("---")
        else:
            st.success("✓ No hay informes pendientes")
            st.info("Todos los informes han sido auditados")
    
    def mostrar_metricas(self):
        """Muestra métricas de calidad (matriz de confusión)"""
        st.header("📊 Métricas de Calidad del Sistema")
        
        stats = self.gestor.obtener_estadisticas()
        matriz = stats["matriz_confusion"]["matriz"]
        metricas = stats["matriz_confusion"]["metricas"]
        
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Informes Pendientes", stats["informes_pendientes"])
        with col2:
            st.metric("Precisión", f"{metricas['precision']}%")
        with col3:
            st.metric("Exhaustividad", f"{metricas['exhaustividad']}%")
        with col4:
            st.metric("F1-Score", f"{metricas['f1']}%")
        
        # Matriz de confusión visual
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
                    <td style="background-color:#d4edda; padding:15px; font-size:20px;"><b>VP: {matriz['vp']}</b></td>
                    <td style="background-color:#f8d7da; padding:15px; font-size:20px;"><b>FN: {matriz['fn']}</b></td>
                </tr>
                <tr>
                    <td><b>Real: No</b></td>
                    <td style="background-color:#f8d7da; padding:15px; font-size:20px;"><b>FP: {matriz['fp']}</b></td>
                    <td style="background-color:#d4edda; padding:15px; font-size:20px;"><b>VN: {matriz['vn']}</b></td>
                </tr>
            </table>
            """, unsafe_allow_html=True)
        
        # Explicación
        st.markdown("""
        ### 📖 Guía de Métricas
        
        - **Verdadero Positivo (VP):** La IA detectó correctamente algo que el médico aprobó
        - **Falso Positivo (FP):** La IA detectó algo que el médico tuvo que corregir
        - **Verdadero Negativo (VN):** La IA no mencionó algo irrelevante (correcto)
        - **Falso Negativo (FN):** La IA no vio algo importante que el médico añadió
        
        ### 📈 Interpretación
        
        - **Precisión:** De lo que la IA detecta, ¿cuánto es correcto?
        - **Exhaustividad:** De todo lo correcto, ¿cuánto detecta la IA?
        - **F1:** Balance entre precisión y exhaustividad
        """)
    
    def generar_informe_nuevo(self):
        """Genera un nuevo informe para un paciente"""
        st.header("🆕 Generar Nuevo Informe")
        
        # Formulario
        with st.form("generar_informe"):
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Nombre del Paciente")
            with col2:
                nif = st.text_input("NIF", max_length=9)
            
            st.markdown("### Configuración del Informe")
            
            titulo = st.text_input("Título del Informe", 
                                  value="Auditoría de Historia Clínica")
            
            secciones_input = st.text_area(
                "Secciones (formato JSON)",
                value='[{"id":"A1","titulo":"Antecedentes","instruccion":"Sintetice antecedentes médicos"},{"id":"A2","titulo":"Evolución","instruccion":"Evalúe evolución clínica"}]',
                height=100
            )
            
            generar = st.form_submit_button("🔬 Generar Informe con IA", type="primary")
        
        if generar and nombre and nif:
            try:
                import yaml
                secciones = json.loads(secciones_input)
                
                config = {
                    "titulo": titulo,
                    "secciones": secciones
                }
                
                st.info("⏳ Generando informe con IA... (puede tardar 1-3 minutos)")
                
                # Ejecutar
                paciente = {"nombre": nombre, "nif": nif}
                sistema = OrquestadorLangGraph(config)
                resultados = sistema.ejecutar(paciente)
                
                # Guardar para auditoría
                informe_data = {
                    "paciente_nif": nif,
                    "paciente_nombre": nombre,
                    "resumen": resultados
                }
                
                informe_id = self.gestor.guardar_informe_pendiente(informe_data)
                
                st.success(f"✓ Informe generado: {informe_id}")
                st.session_state.informe_actual = informe_id
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al generar: {str(e)}")
    
    def run(self):
        """Ejecuta el dashboard"""
        self.cargar_datos()
        
        # Ver si hay informe seleccionado
        if st.session_state.get("informe_actual"):
            self.mostrar_informe(st.session_state.informe_actual)
            
            if st.button("← Volver"):
                st.session_state.informe_actual = None
                st.rerun()
        else:
            opcion = self.mostrar_sidebar()
            
            if opcion == "🔍 Buscar Paciente":
                self.buscar_paciente()
            elif opcion == "📋 Informes Pendientes":
                self.mostrar_informes_pendientes()
            elif opcion == "📊 Métricas de Calidad":
                self.mostrar_metricas()
            elif opcion == "⚙️ Configuración":
                self.generar_informe_nuevo()


# === ENTRADA PRINCIPAL ===
if __name__ == "__main__":
    dashboard = DashboardMedico()
    dashboard.run()