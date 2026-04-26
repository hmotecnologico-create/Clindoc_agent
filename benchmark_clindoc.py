"""
BENCHMARK CLINDOC AGENT v4.0
=============================
Script de benchmarking y pruebas de rendimiento para ClinDoc Agent.
Mide: latencia por fase, eficiencia de extracción, comparación de métodos.

Resultados útiles para:
- Capítulo 5: Métricas de rendimiento (KPIs)
- Capítulo 6: Análisis de resultados del Master Run

Autor: ClinDoc Agent v4.0
Fecha: 2026-04-26
"""

import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path

# Forzar UTF-8
if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# === BENCHMARK 1: Comparación de métodos de extracción ===
def benchmark_extraccion():
    """Compara Docling vs PyPDF2 para extracción de PDFs"""
    print("\n" + "="*60)
    print("BENCHMARK 1: EXTRACCIÓN DE DOCUMENTOS")
    print("="*60)
    
    resultados = {
        "timestamp": datetime.now().isoformat(),
        "docling": {},
        "pypdf2": {},
        "comparacion": {}
    }
    
    # Probar Docling
    print("\n[1.1] Probando Docling...")
    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        
        archivos_pdf = list(Path("datos/expedientes").glob("*.pdf"))
        
        if archivos_pdf:
            start = time.time()
            for f in archivos_pdf:
                result = converter.convert(f)
                texto = result.document.export_to_markdown()
            tiempo_docling = time.time() - start
            resultados["docling"] = {
                "disponible": True,
                "tiempo_total": round(tiempo_docling, 4),
                "archivos": len(archivos_pdf)
            }
            print(f"   ✓ Docling: {tiempo_docling:.4f}s para {len(archivos_pdf)} archivos")
        else:
            resultados["docling"] = {"disponible": True, "archivos": 0, "nota": "No hay PDFs"}
            print("   ⚠ No hay archivos PDF para probar Docling")
    except Exception as e:
        resultados["docling"] = {"disponible": False, "error": str(e)}
        print(f"   ✗ Docling no disponible: {e}")
    
    # Probar PyPDF2 fallback
    print("\n[1.2] Probando PyPDF2...")
    try:
        import pypdf
        
        archivos_pdf = list(Path("datos/expedientes").glob("*.pdf"))
        
        if archivos_pdf:
            start = time.time()
            for f in archivos_pdf:
                reader = pypdf.PdfReader(f)
                texto = ""
                for page in reader.pages:
                    texto += page.extract_text() or ""
            tiempo_pypdf = time.time() - start
            resultados["pypdf2"] = {
                "tiempo_total": round(tiempo_pypdf, 4),
                "archivos": len(archivos_pdf)
            }
            print(f"   ✓ PyPDF2: {tiempo_pypdf:.4f}s para {len(archivos_pdf)} archivos")
        else:
            resultados["pypdf2"] = {"archivos": 0, "nota": "No hay PDFs"}
    except Exception as e:
        resultados["pypdf2"] = {"error": str(e)}
        print(f"   ✗ Error: {e}")
    
    # Comparación
    if resultados["docling"].get("disponible") and resultados["pypdf2"].get("tiempo_total"):
        docling_t = resultados["docling"]["tiempo_total"]
        pypdf_t = resultados["pypdf2"]["tiempo_total"]
        velocidad = (pypdf_t / docling_t) if docling_t > 0 else 1
        
        resultados["comparacion"] = {
            "docling_vs_pypdf": f"Docling es {velocidad:.1f}x {'más rápido' if velocidad > 1 else 'más lento'}",
            "mejor_metodo": "Docling" if velocidad > 1 else "PyPDF2"
        }
        print(f"\n   → Comparación: Docling es {velocidad:.1f}x más rápido")
    
    return resultados


# === BENCHMARK 2: Ingesta de diferentes formatos ===
def benchmark_formatos():
    """Mide rendimiento procesando diferentes formatos"""
    print("\n" + "="*60)
    print("BENCHMARK 2: PROCESAMIENTO DE FORMATOS HETEROGÉNEOS")
    print("="*60)
    
    # Importar después para no afectar imports anteriores
    sys.path.insert(0, ".")
    from run_clindoc import AgenteEscanner
    
    escanner = AgenteEscanner("datos/expedientes")
    
    resultados = {
        "timestamp": datetime.now().isoformat(),
        "formatos": {}
    }
    
    # Escanear todos los formatos
    print("\n[2.1] Escaneando documentos...")
    start = time.time()
    documentos = escanner.scan()
    tiempo_total = time.time() - start
    
    # Analizar por formato
    por_formato = {}
    for doc in documentos:
        fmt = doc.get("formato", "desconocido")
        if fmt not in por_formato:
            por_formato[fmt] = {"count": 0, "imagenes": 0}
        por_formato[fmt]["count"] += 1
        por_formato[fmt]["imagenes"] += doc.get("imagenes_detectadas", 0)
    
    resultados["formatos"] = por_formato
    resultados["total_documentos"] = len(documentos)
    resultados["tiempo_total"] = round(tiempo_total, 4)
    
    print(f"   ✓ Total: {len(documentos)} documentos en {tiempo_total:.4f}s")
    for fmt, data in por_formato.items():
        print(f"   ✓ {fmt}: {data['count']} documentos, {data['imagenes']} imágenes detectadas")
    
    return resultados


# === BENCHMARK 3: Indexación vectorial ===
def benchmark_indexacion():
    """Mide rendimiento de indexación en Qdrant"""
    print("\n" + "="*60)
    print("BENCHMARK 3: INDEXACIÓN VECTORIAL (Qdrant)")
    print("="*60)
    
    from run_clindoc import IndiceCorpus, AgenteEscanner
    
    resultados = {
        "timestamp": datetime.now().isoformat()
    }
    
    # Escanear documentos
    escanner = AgenteEscanner("datos/expedientes")
    documentos = escanner.scan()
    
    # Indexar
    indice = IndiceCorpus("datos/qdrant_db")
    
    print(f"\n[3.1] Indexando {len(documentos)} documentos...")
    start = time.time()
    
    for doc in documentos:
        indice.indexar_documento(doc['id'], doc['texto'], doc['nombre'])
    
    tiempo_indexacion = time.time() - start
    
    resultados["documentos_indexados"] = len(documentos)
    resultados["tiempo_indexacion"] = round(tiempo_indexacion, 4)
    resultados["tiempo_por_doc"] = round(tiempo_indexacion / len(documentos), 4) if documentos else 0
    
    print(f"   ✓ Indexación completada en {tiempo_indexacion:.4f}s")
    print(f"   ✓ Promedio: {resultados['tiempo_por_doc']:.4f}s por documento")
    
    return resultados


# === BENCHMARK 4: Validación de identidad ===
def benchmark_validacion():
    """Prueba la validación de identidad con NIF"""
    print("\n" + "="*60)
    print("BENCHMARK 4: VALIDACIÓN DE IDENTIDAD (NIF)")
    print("="*60)
    
    from run_clindoc import VerificadorIdentidad
    
    verificador = VerificadorIdentidad()
    
    # Casos de prueba
    casos_prueba = [
        {
            "nombre": "NIF válido que coincide",
            "nif_ref": "12345678Z",
            "texto": "Paciente: Juan Pérez. NIF: 12345678Z. Fecha: 05/04/2026",
            "esperado": True
        },
        {
            "nombre": "NIF válido que NO coincide",
            "nif_ref": "12345678Z",
            "texto": "Paciente: Juana Martínez. NIF: 87654321X. Fecha: 14/02/2026",
            "esperado": False
        },
        {
            "nombre": "NIF inválido (letra incorrecta)",
            "nif_ref": "12345678Z",
            "texto": "Paciente: Test. NIF: 12345678A",
            "esperado": False
        },
        {
            "nombre": "Sin NIF en documento",
            "nif_ref": "12345678Z",
            "texto": "Paciente: Juan Pérez. Fecha: 05/04/2026",
            "esperado": False
        }
    ]
    
    resultados = {
        "timestamp": datetime.now().isoformat(),
        "casos": [],
        "resumen": {"total": 0, "aciertos": 0}
    }
    
    print("\n[4.1] Ejecutando casos de prueba...")
    for caso in casos_prueba:
        resultado = verificador.validar(caso["nif_ref"], caso["texto"])
        
        acierto = resultado["valido"] == caso["esperado"]
        
        resultados["casos"].append({
            "nombre": caso["nombre"],
            "resultado": resultado["valido"],
            "esperado": caso["esperado"],
            "acierto": acierto,
            "detalle": resultado.get("detalle", "")
        })
        
        resultados["resumen"]["total"] += 1
        if acierto:
            resultados["resumen"]["aciertos"] += 1
        
        simbolo = "✓" if acierto else "✗"
        print(f"   {simbolo} {caso['nombre']}: {resultado.get('detalle', '')}")
    
    precision = resultados["resumen"]["aciertos"] / resultados["resumen"]["total"] * 100
    resultados["resumen"]["precision"] = round(precision, 1)
    
    print(f"\n   → Precisión: {precision:.1f}% ({resultados['resumen']['aciertos']}/{resultados['resumen']['total']})")
    
    return resultados


# === BENCHMARK 5: Validación de vigencia ===
def benchmark_vigencia():
    """Prueba la validación de vigencia de documentos"""
    print("\n" + "="*60)
    print("BENCHMARK 5: VALIDACIÓN DE VIGENCIA")
    print("="*60)
    
    from run_clindoc import VerificadorVigencia
    
    verificador = VerificadorVigencia()
    
    casos_prueba = [
        {
            "nombre": "Documento reciente (< 6 meses)",
            "texto": "Fecha: 15/03/2026. Paciente: Juan Pérez.",
            "regla": "reciente_6_meses",
            "esperado": True
        },
        {
            "nombre": "Documento antiguo (> 6 meses)",
            "texto": "Fecha: 15/08/2024. Paciente: Juan Pérez.",
            "regla": "reciente_6_meses",
            "esperado": False
        },
        {
            "nombre": "Documento expirado (fecha futura)",
            "texto": "Fecha: 15/04/2027. Paciente: Juan Pérez.",
            "regla": "no_vencido",
            "esperado": False
        }
    ]
    
    resultados = {
        "timestamp": datetime.now().isoformat(),
        "casos": [],
        "resumen": {"total": 0, "aciertos": 0}
    }
    
    print("\n[5.1] Ejecutando casos de prueba...")
    for caso in casos_prueba:
        resultado = verificador.validar(caso["texto"], caso["regla"])
        
        acierto = resultado["valido"] == caso["esperado"]
        
        resultados["casos"].append({
            "nombre": caso["nombre"],
            "resultado": resultado["valido"],
            "esperado": caso["esperado"],
            "acierto": acierto,
            "detalle": resultado.get("detalle", "")
        })
        
        resultados["resumen"]["total"] += 1
        if acierto:
            resultados["resumen"]["aciertos"] += 1
        
        simbolo = "✓" if acierto else "✗"
        print(f"   {simbolo} {caso['nombre']}: {resultado.get('detalle', '')}")
    
    precision = resultados["resumen"]["aciertos"] / resultados["resumen"]["total"] * 100
    resultados["resumen"]["precision"] = round(precision, 1)
    
    print(f"\n   → Precisión: {precision:.1f}% ({resultados['resumen']['aciertos']}/{resultados['resumen']['total']})")
    
    return resultados


# === BENCHMARK 6: Latencia del pipeline completo ===
def benchmark_pipeline():
    """Mide latencia total del pipeline (sin LLM)"""
    print("\n" + "="*60)
    print("BENCHMARK 6: LATENCIA DEL PIPELINE")
    print("="*60)
    
    from run_clindoc import AgenteEscanner, IndiceCorpus, VerificadorIdentidad, VerificadorVigencia
    
    resultados = {
        "timestamp": datetime.now().isoformat(),
        "fases": {}
    }
    
    paciente = {"nombre": "Juan Pérez García", "nif": "12345678Z"}
    
    # Fase 1: Ingesta
    print("\n[6.1] Fase 1: Ingesta...")
    escanner = AgenteEscanner("datos/expedientes")
    start = time.time()
    documentos = escanner.scan()
    resultados["fases"]["ingesta"] = round(time.time() - start, 4)
    print(f"   ✓ {resultados['fases']['ingesta']}s")
    
    # Fase 2: Indexación
    print("[6.2] Fase 2: Indexación...")
    indice = IndiceCorpus("datos/qdrant_db")
    start = time.time()
    for doc in documentos:
        indice.indexar_documento(doc['id'], doc['texto'], doc['nombre'])
    resultados["fases"]["indexacion"] = round(time.time() - start, 4)
    print(f"   ✓ {resultados['fases']['indexacion']}s")
    
    # Fase 3: Validación identidad
    print("[6.3] Fase 3: Validación identidad...")
    verificador_id = VerificadorIdentidad()
    start = time.time()
    for doc in documentos:
        verificador_id.validar(paciente["nif"], doc["texto"])
    resultados["fases"]["validacion_identidad"] = round(time.time() - start, 4)
    print(f"   ✓ {resultados['fases']['validacion_identidad']}s")
    
    # Fase 4: Validación vigencia
    print("[6.4] Fase 4: Validación vigencia...")
    verificador_vig = VerificadorVigencia()
    start = time.time()
    for doc in documentos:
        verificador_vig.validar(doc["texto"], "reciente_6_meses")
    resultados["fases"]["validacion_vigencia"] = round(time.time() - start, 4)
    print(f"   ✓ {resultados['fases']['validacion_vigencia']}s")
    
    # Total
    total = sum(resultados["fases"].values())
    resultados["total"] = round(total, 4)
    resultados["porcentajes"] = {
        fase: round((tiempo / total) * 100, 1) 
        for fase, tiempo in resultados["fases"].items()
    }
    
    print(f"\n   → TOTAL: {total:.4f}s")
    print(f"   → Distribución: {resultados['porcentajes']}")
    
    return resultados


# === EJECUTAR TODOS LOS BENCHMARKS ===
def ejecutar_todos_benchmarks():
    """Ejecuta todos los benchmarks y genera informe"""
    print("\n" + "="*70)
    print("  CLINDOC AGENT v4.0 - SUITE DE BENCHMARKING COMPLETO")
    print("  Generado: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)
    
    resultados = {
        "info": {
            "version": "v4.0",
            "fecha": datetime.now().isoformat(),
            "objetivo": "Validación experimental del sistema ClinDoc Agent"
        }
    }
    
    # Ejecutar benchmarks
    try:
        resultados["extraccion"] = benchmark_extraccion()
    except Exception as e:
        resultados["extraccion"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de extracción: {e}")
    
    try:
        resultados["formatos"] = benchmark_formatos()
    except Exception as e:
        resultados["formatos"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de formatos: {e}")
    
    try:
        resultados["indexacion"] = benchmark_indexacion()
    except Exception as e:
        resultados["indexacion"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de indexación: {e}")
    
    try:
        resultados["validacion_identidad"] = benchmark_validacion()
    except Exception as e:
        resultados["validacion_identidad"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de identidad: {e}")
    
    try:
        resultados["validacion_vigencia"] = benchmark_vigencia()
    except Exception as e:
        resultados["validacion_vigencia"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de vigencia: {e}")
    
    try:
        resultados["pipeline"] = benchmark_pipeline()
    except Exception as e:
        resultados["pipeline"] = {"error": str(e)}
        print(f"\n✗ Error en benchmark de pipeline: {e}")
    
    # Guardar resultados
    output_file = "benchmark_resultados.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*70)
    print("  RESUMEN DE RESULTADOS")
    print("="*70)
    
    # Mostrar KPIs clave
    if "pipeline" in resultados and "total" in resultados["pipeline"]:
        print(f"\n📊 LATENCIA TOTAL DEL PIPELINE (sin LLM):")
        print(f"   → {resultados['pipeline']['total']:.4f} segundos")
    
    if "validacion_identidad" in resultados:
        prec = resultados["validacion_identidad"]["resumen"]["precision"]
        print(f"\n📊 VALIDACIÓN DE IDENTIDAD:")
        print(f"   → Precisión: {prec:.1f}%")
    
    if "validacion_vigencia" in resultados:
        prec = resultados["validacion_vigencia"]["resumen"]["precision"]
        print(f"\n📊 VALIDACIÓN DE VIGENCIA:")
        print(f"   → Precisión: {prec:.1f}%")
    
    if "formatos" in resultados:
        print(f"\n📊 FORMATOS PROCESADOS:")
        for fmt, data in resultados["formatos"].get("formatos", {}).items():
            print(f"   → {fmt}: {data['count']} documentos")
    
    print(f"\n✅ Resultados guardados en: {output_file}")
    
    return resultados


# === ENTRADA PRINCIPAL ===
if __name__ == "__main__":
    resultados = ejecutar_todos_benchmarks()