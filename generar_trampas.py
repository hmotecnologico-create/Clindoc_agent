import os
import random
from pathlib import Path
from datetime import date, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def generar_pdf(ruta, titulo, cabecera, texto):
    doc = SimpleDocTemplate(str(ruta), pagesize=A4)
    elementos = []
    styles = getSampleStyleSheet()
    
    elementos.append(Paragraph(titulo, styles['Title']))
    elementos.append(Paragraph(cabecera, styles['Normal']))
    elementos.append(Spacer(1, 12))
    
    for p in texto.split("\n"):
        if p.strip():
            elementos.append(Paragraph(p, styles['Normal']))
            elementos.append(Spacer(1, 6))
            
    doc.build(elementos)

if __name__ == "__main__":
    BASE_TRAMPAS = Path("datos/trampas_eval")
    BASE_TRAMPAS.mkdir(parents=True, exist_ok=True)
    
    # NIF base para las pruebas
    nif_real = "25988000R"
    nombre_real = "Carlos Valderrama"
    
    # Trampas de Identidad (20)
    for i in range(1, 21):
        # 10 con NIF inventado y 10 con nombre distinto
        if i <= 10:
            nif_trampa = f"000000{i:02d}X"
            nombre_trampa = nombre_real
        else:
            nif_trampa = nif_real
            nombre_trampa = "Feliciano Valverde Vigil" # Trampa de nombre
            
        ruta = BASE_TRAMPAS / f"TRAMPA_ID_{i:02d}.pdf"
        titulo = "INFORME MEDICO"
        cabecera = f"Paciente: {nombre_trampa} | NIF: {nif_trampa} | Fecha: 2026-05-10"
        texto = f"El paciente acude a consulta por cuadro clínico general.\n\nSe realiza exploración y se pauta tratamiento conservador.\n\nFdo: Dr. Falso."
        
        generar_pdf(ruta, titulo, cabecera, texto)
        
    # Trampas de Vigencia (20)
    for i in range(1, 21):
        # Fechas antiguas (ej. 2010 a 2015)
        fecha_trampa = date(2010 + (i%6), 5, 10).strftime("%d/%m/%Y")
        
        ruta = BASE_TRAMPAS / f"TRAMPA_VIG_{i:02d}.pdf"
        titulo = "INFORME CLINICO"
        cabecera = f"Paciente: {nombre_real} | NIF: {nif_real} | Fecha: {fecha_trampa}"
        texto = f"Informe emitido en fecha {fecha_trampa} detallando estado clínico anterior.\n\nEsta es una trampa de vigencia para el validador.\n\nFdo: Dr. Antiguo."
        
        generar_pdf(ruta, titulo, cabecera, texto)
        
    print(f"Generadas 40 trampas en {BASE_TRAMPAS}")
