"""
MÓDULO DE HISTORIAL CLÍNICO VISUAL
=====================================
Genera línea de tiempo visual de la evolución del paciente:
- Citas médicas
- Exámenes/Pruebas diagnósticas
- Diagnósticos
- Tratamientos
- Eventos de salud

Permite búsqueda de términos/enfermedades en todo el historial.

Este módulo es CRÍTICO para el dashboard del médico.
"""

import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from collections import defaultdict
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class EventoClinico:
    """Representa un evento en la historia clínica del paciente"""
    def __init__(self, fecha: datetime, tipo: str, titulo: str, 
                 descripcion: str = "", fuente: str = "", importancia: int = 1):
        self.fecha = fecha
        self.tipo = tipo  # cita, examen, diagnostico, tratamiento, evento
        self.titulo = titulo
        self.descripcion = descripcion
        self.fuente = fuente
        self.importancia = importancia  # 1=baja, 2=media, 3=alta
    
    def to_dict(self) -> dict:
        return {
            "fecha": self.fecha.isoformat(),
            "tipo": self.tipo,
            "titulo": self.titulo,
            "descripcion": self.descripcion,
            "fuente": self.fuente,
            "importancia": self.importancia
        }


class HistorialClinicoVisual:
    """
    Genera visualización de la evolución temporal del paciente.
    
    FUNCIONALIDADES:
    1. Extraer eventos de documentos clínicos
    2. Generar línea de tiempo interactiva
    3. Búsqueda de términos/enfermedades
    4. Estadísticas del historial
    """
    
    def __init__(self, ruta_expedientes: str = "datos/expedientes"):
        self.ruta = Path(ruta_expedientes)
        self.eventos: List[EventoClinico] = []
        self.paciente_actual: Optional[Dict] = None
        
        # Patrones para extraer eventos
        self.patrones_eventos = {
            "cita": [
                r'Fecha de consulta[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'Fecha[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'consulta del\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
            ],
            "examen": [
                r'anal[ií]tic[oa][:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'radiograf[ií]a[:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'ecocardiograma[:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'rmn[:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'tac[:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'anal[ií]tica[:?\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ],
            "diagnostico": [
                r'diagn[oó]stico[:?\s]+([^.]+)',
                r'juicio cl[ií]nico[:?\s]+([^.]+)',
                r'patolog[ií]a[:?\s]+([^.]+)',
                r'afecci[óo]n[:?\s]+([^.]+)',
            ],
            "tratamiento": [
                r'tratamiento[:?\s]+([^.]+)',
                r'medicaci[óo]n[:?\s]+([^.]+)',
                r'posolog[ií]a[:?\s]+([^.]+)',
                r'dosis[:?\s]+(\d+\s*mg)',
                r'([a-z]+(?:pril|statina|sartan|mf))',  # principios activos comunes
            ],
        }
        
        # Palabras clave por tipo de evento
        self.palabras_clave = {
            "examen": ["analítica", "análisis", "radiografía", "resonancia", "ecocardiograma", 
                      "tac", "rmn", "ecografía", "electrocardiograma", "prueba", "test"],
            "diagnostico": ["diagnóstico", "diagnosticado", "patología", "enfermedad", 
                           "afección", "trastorno", "síndrome", "juicio clínico"],
            "tratamiento": ["tratamiento", "medicación", "fármaco", "medicamento", "dosis",
                           "toma", "prescrito", "recetado", "adayuvante"],
            "cita": ["consulta", "visita", "revisión", "cita", "atención", "urgencias"],
        }
    
    def _parsear_fecha(self, texto_fecha: str) -> Optional[datetime]:
        """Convierte texto de fecha a datetime"""
        formatos = [
            "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
            "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d de %B de %Y"
        ]
        
        texto_fecha = texto_fecha.strip()
        
        # Limpiar el texto
        texto_fecha = texto_fecha.replace('de ', '').replace('Del ', '')
        
        for fmt in formatos:
            try:
                return datetime.strptime(texto_fecha, fmt)
            except:
                continue
        
        # Intentar con regex flexible
        match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', texto_fecha)
        if match:
            dia, mes, año = match.groups()
            if len(año) == 2:
                año = "20" + año if int(año) < 50 else "19" + año
            try:
                return datetime(int(año), int(mes), int(dia))
            except:
                pass
        
        return None
    
    def _extraer_eventos_de_documento(self, doc_id: str, texto: str, 
                                      nombre_archivo: str) -> List[EventoClinico]:
        """Extrae eventos clínicos de un documento"""
        eventos = []
        
        # Buscar fechas y asociar con contenido
        fechas_encontradas = re.findall(
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', texto
        )
        
        for fecha_str in fechas_encontradas:
            fecha = self._parsear_fecha(fecha_str)
            if fecha and fecha.year >= 2000 and fecha <= datetime.now():
                
                # Determinar tipo de evento por contexto
                tipo, titulo, importancia = self._detectar_tipo_evento(texto, fecha_str)
                
                evento = EventoClinico(
                    fecha=fecha,
                    tipo=tipo,
                    titulo=titulo,
                    descripcion=self._extraer_contexto_cercano(texto, fecha_str),
                    fuente=nombre_archivo,
                    importancia=importancia
                )
                eventos.append(evento)
        
        # Si no hay fechas claras, buscar palabras clave
        if not eventos:
            eventos.extend(self._buscar_por_palabras_clave(texto, nombre_archivo))
        
        return eventos
    
    def _detectar_tipo_evento(self, texto: str, fecha_str: str) -> Tuple[str, str, int]:
        """Detecta el tipo de evento basado en el contexto"""
        texto_lower = texto.lower()
        
        for palabra in self.palabras_clave.get("examen", []):
            if palabra in texto_lower:
                return "examen", f"Examen médico - {palabra.title()}", 2
        
        for palabra in self.palabras_clave.get("diagnostico", []):
            if palabra in texto_lower:
                # Extraer diagnóstico
                match = re.search(rf'{palabra}[:\s]+([^.]+)', texto_lower)
                if match:
                    return "diagnostico", f"Diagnóstico: {match.group(1)[:50]}", 3
        
        for palabra in self.palabras_clave.get("tratamiento", []):
            if palabra in texto_lower:
                return "tratamiento", "Tratamiento/Medicação", 2
        
        for palabra in self.palabras_clave.get("cita", []):
            if palabra in texto_lower:
                return "cita", f"Consulta médica - {palabra.title()}", 1
        
        # Por defecto, evento general
        return "evento", f"Evento clínico - {fecha_str}", 1
    
    def _buscar_por_palabras_clave(self, texto: str, fuente: str) -> List[EventoClinico]:
        """Busca eventos por palabras clave cuando no hay fechas claras"""
        eventos = []
        texto_lower = texto.lower()
        
        lineas = texto.split('\n')
        
        for tipo, palabras in self.palabras_clave.items():
            for palabra in palabras:
                if palabra in texto_lower:
                    for linea in lineas:
                        if palabra in linea.lower():
                            # Buscar fecha en la línea o cerca
                            match = re.search(r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', linea)
                            if match:
                                fecha = self._parsear_fecha(match.group(1))
                                if fecha:
                                    evento = EventoClinico(
                                        fecha=fecha,
                                        tipo=tipo,
                                        titulo=palabra.title(),
                                        descripcion=linea[:100],
                                        fuente=fuente,
                                        importancia=2 if tipo in ["diagnostico", "examen"] else 1
                                    )
                                    eventos.append(evento)
        
        return eventos
    
    def _extraer_contexto_cercano(self, texto: str, fecha_str: str, 
                                  contexto_chars: int = 100) -> str:
        """Extrae el texto cercano a una fecha"""
        pos = texto.find(fecha_str)
        if pos == -1:
            return ""
        
        inicio = max(0, pos - 20)
        fin = min(len(texto), pos + contexto_chars)
        
        return texto[inicio:fin].strip()
    
    def cargar_expediente(self, paciente_nif: str, paciente_nombre: str):
        """Carga todos los documentos de un paciente"""
        self.paciente_actual = {
            "nif": paciente_nif,
            "nombre": paciente_nombre
        }
        self.eventos = []
        
        # Cargar desde carpeta de auditorías
        carpeta = Path("datos/auditorias")
        if carpeta.exists():
            for archivo in carpeta.glob(f"inf_{paciente_nif}_*.json"):
                try:
                    with open(archivo, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Buscar en secciones
                    secciones = data.get("secciones", {})
                    for seccion, contenido in secciones.items():
                        eventos = self._extraer_eventos_de_documento(
                            data.get("informe_id", ""),
                            contenido,
                            f"sección: {seccion}"
                        )
                        self.eventos.extend(eventos)
                except:
                    pass
        
        # Cargar también desde carpeta de expedientes
        if self.ruta.exists():
            for archivo in self.ruta.glob("*"):
                try:
                    contenido = archivo.read_text(encoding="utf-8")
                    eventos = self._extraer_eventos_de_documento(
                        archivo.stem,
                        contenido,
                        archivo.name
                    )
                    self.eventos.extend(eventos)
                except:
                    pass
        
        # Ordenar por fecha
        self.eventos.sort(key=lambda e: e.fecha)
    
    def buscar_termino(self, termino: str) -> List[EventoClinico]:
        """Busca un término/enfermedad en todo el historial"""
        termino_lower = termino.lower()
        resultados = []
        
        for evento in self.eventos:
            if (termino_lower in evento.titulo.lower() or 
                termino_lower in evento.descripcion.lower() or
                termino_lower in evento.tipo.lower()):
                resultados.append(evento)
        
        return resultados
    
    def obtener_estadisticas(self) -> Dict:
        """Obtiene estadísticas del historial"""
        if not self.eventos:
            return {"total_eventos": 0}
        
        # Conteo por tipo
        por_tipo = defaultdict(int)
        por_año = defaultdict(int)
        por_mes = defaultdict(int)
        
        for evento in self.eventos:
            por_tipo[evento.tipo] += 1
            por_año[evento.fecha.year] += 1
            por_mes[f"{evento.fecha.year}-{evento.fecha.month:02d}"] += 1
        
        # Última cita
        ultima_fecha = max(e.fecha for e in self.eventos)
        primera_fecha = min(e.fecha for e in self.eventos)
        
        # Tiempo de seguimiento
        dias_seguimiento = (ultima_fecha - primera_fecha).days
        
        return {
            "total_eventos": len(self.eventos),
            "por_tipo": dict(por_tipo),
            "por_año": dict(por_año),
            "primera_fecha": primera_fecha.isoformat(),
            "ultima_fecha": ultima_fecha.isoformat(),
            "dias_seguimiento": dias_seguimiento,
            "eventos_importantes": len([e for e in self.eventos if e.importancia >= 3])
        }
    
    def generar_grafico_timeline(self) -> go.Figure:
        """Genera gráfico de línea de tiempo interactivo"""
        
        if not self.eventos:
            fig = go.Figure()
            fig.add_annotation(text="No hay eventos clínicos registrados",
                             xref="paper", yref="paper", x=0.5, y=0.5)
            return fig
        
        # Preparar datos
        fechas = [e.fecha for e in self.eventos]
        titulos = [e.titulo for e in self.eventos]
        descripciones = [e.descripcion for e in self.eventos]
        tipos = [e.tipo for e in self.eventos]
        importancia = [e.importancia for e in self.eventos]
        
        # Colores por tipo
        colores = {
            "examen": "#3b82f6",      # azul
            "diagnostico": "#ef4444", # rojo
            "tratamiento": "#22c55e", # verde
            "cita": "#f59e0b",        # amarillo
            "evento": "#6b7280"       # gris
        }
        
        color_tipo = [colores.get(t, "#6b7280") for t in tipos]
        
        # Tamaño por importancia
        tamaños = [i * 8 + 8 for i in importancia]
        
        # Crear figura
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=("Línea de Tiempo - Evolución Clínica", "Eventos por Año"),
            vertical_spacing=0.15
        )
        
        # Gráfico de dispersión (timeline)
        fig.add_trace(
            go.Scatter(
                x=fechas,
                y=[1] * len(fechas),
                mode='markers+text',
                marker=dict(
                    size=tamaños,
                    color=color_tipo,
                    line=dict(color='white', width=1)
                ),
                text=titulos,
                textposition="top center",
                textfont=dict(size=8),
                hovertemplate=
                "<b>%{text}</b><br>" +
                "Fecha: %{x}<br>" +
                "Tipo: %{customdata}<br>" +
                "Descripción: %{customdata2}<extra></extra>",
                customdata=tipos,
                customdata2=descripciones
            ),
            row=1, col=1
        )
        
        # Eventos por año
        stats = self.obtener_estadisticas()
        años = sorted(stats["por_año"].keys())
        conteos = [stats["por_año"][a] for a in años]
        
        fig.add_trace(
            go.Bar(
                x=años,
                y=conteos,
                marker_color="#3b82f6",
                text=conteos,
                textposition="outside"
            ),
            row=2, col=1
        )
        
        # Actualizar layout
        fig.update_layout(
            title=f"Historial Clínico - {self.paciente_actual.get('nombre', 'Paciente')}",
            showlegend=False,
            height=600,
            xaxis=dict(showgrid=True, gridcolor='lightgray'),
            yaxis=dict(showgrid=False, showticklabels=False, range=[0.5, 1.5]),
            xaxis2=dict(title="Año"),
            yaxis2=dict(title="Número de Eventos")
        )
        
        # Añadir leyenda manual
        for tipo, color in colores.items():
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=10, color=color),
                name=tipo.capitalize(),
                showlegend=True
            ))
        
        return fig
    
    def generar_tabla_eventos(self) -> List[Dict]:
        """Genera tabla de eventos para mostrar"""
        return [
            {
                "fecha": e.fecha.strftime("%d/%m/%Y"),
                "tipo": e.tipo.capitalize(),
                "titulo": e.titulo[:50],
                "descripcion": e.descripcion[:100] + "..." if len(e.descripcion) > 100 else e.descripcion,
                "importancia": "Alta" if e.importancia == 3 else ("Media" if e.importancia == 2 else "Baja")
            }
            for e in self.eventos
        ]


# === INTERFAZ PARA DASHBOARD ===
def mostrar_historial_clinico(paciente_nif: str, paciente_nombre: str):
    """Muestra el historial clínico visual en Streamlit"""
    
    import streamlit as st
    
    st.markdown("## 📈 Historial Clínico - Evolución del Paciente")
    
    historial = HistorialClinicoVisual()
    historial.cargar_expediente(paciente_nif, paciente_nombre)
    
    if not historial.eventos:
        st.warning("No se encontró información clínica para este paciente")
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
    busqueda = st.text_input("Buscar en historial:", placeholder="diabetes, tensión, tratamiento...")
    
    if busqueda:
        resultados = historial.buscar_termino(busqueda)
        st.markdown(f"**{len(resultados)} resultados encontrados** para '{busqueda}'")
        
        for e in resultados:
            with st.expander(f"📅 {e.fecha.strftime('%d/%m/%Y')} - {e.titulo}"):
                st.markdown(f"**Tipo:** {e.tipo.capitalize()}")
                st.markdown(f"**Descripción:** {e.descripcion}")
                st.markdown(f"**Fuente:** {e.fuente}")
    
    # Gráfico de timeline
    st.markdown("### 📊 Línea de Tiempo - Evolución Clínica")
    
    fig = historial.generar_grafico_timeline()
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabla de eventos
    st.markdown("### 📋 Lista de Eventos")
    
    eventos_tabla = historial.generar_tabla_eventos()
    if eventos_tabla:
        import pandas as pd
        df = pd.DataFrame(eventos_tabla)
        st.dataframe(df, use_container_width=True)


# === EJEMPLO DE USO ===
if __name__ == "__main__":
    print("="*60)
    print("  HISTORIAL CLÍNICO VISUAL - CLINDOC AGENT")
    print("="*60)
    
    historial = HistorialClinicoVisual()
    
    # Simular carga de expediente
    print("\n[1] Cargando expediente del paciente...")
    historial.cargar_expediente("12345678Z", "Juan Pérez García")
    print(f"    → {len(historial.eventos)} eventos extraídos")
    
    # Estadísticas
    print("\n[2] Estadísticas del historial:")
    stats = historial.obtener_estadisticas()
    for k, v in stats.items():
        if k not in ["por_tipo", "por_año"]:
            print(f"    {k}: {v}")
    
    # Buscar término
    print("\n[3] Buscando 'diabetes':")
    resultados = historial.buscar_termino("diabetes")
    print(f"    → {len(resultados)} resultados")
    
    # Generar gráfico
    print("\n[4] Generando gráfico de timeline...")
    fig = historial.generar_grafico_timeline()
    fig.write_html("historial_clinico.html")
    print("    → Guardado en: historial_clinico.html")
    
    print("\n" + "="*60)
    print("  EJEMPLO COMPLETADO")
    print("="*60)