"""
MÓDULO DE MATRIZ DE CONFUSIÓN PARA CLINDOC AGENT
=================================================
Permite al médico validar y corregir las generaciones de la IA,
calculando métricas de falsos positivos/negativos para mejorar el sistema.

Este módulo es CRÍTICO para el Capítulo 6 del TFM:
- Medición de calidad del sistema
- Identificación de sesgos de la IA
- Mejora continua basada en feedback médico
"""

from typing import List, Dict, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import json
import os
from pathlib import Path


class TipoValidacion(str, Enum):
    """Tipos de validación que el médico puede hacer"""
    APROBADO = "aprobado"
    MODIFICADO = "modificado"
    RECHAZADO = "rechazado"
    NUEVOhallazgo = "nuevo_hallazgo"


class CategoriaError(str, Enum):
    """Categorías de errores detectados"""
    FALSO_POSITIVO = "falso_positivo"  # IA detectó algo incorrecto
    FALSO_NEGATIVO = "falso_negativo"  # IA no vio algo importante
    ERROR_FECHA = "error_fecha"
    ERROR_NIF = "error_nif"
    ALUCINACION = "alucinacion"  # Inventó información
    OMISION = "omision"  # No mencionó algo relevante


class ValidacionSeccion(BaseModel):
    """Validación de una sección por el médico"""
    seccion: str
    validacion: TipoValidacion
    texto_original: str
    texto_modificado: Optional[str] = None
    notas_medico: Optional[str] = None
    categoria_error: Optional[CategoriaError] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class InformeAuditado(BaseModel):
    """Informe generado con auditoría del médico"""
    informe_id: str
    paciente_nif: str
    paciente_nombre: str
    fecha_generacion: datetime
    fecha_auditoria: Optional[datetime] = None
    
    # Estado del informe
    estado: Literal["pendiente", "auditado", "aprobado", "modificado"] = "pendiente"
    
    # Validaciones por sección
    validaciones: List[ValidacionSeccion] = []
    
    # Notas generales del médico
    notas_auditoria: Optional[str] = None
    
    # Métricas calculadas
    metricas: Optional[Dict] = None


class MatrizConfusion:
    """
    Calcula y guarda la matriz de confusión del sistema.
    
    MATRIZ DE CONFUSIÓN:
                        Predicho: Sí         Predicho: No
    Real: Sí        Verdadero Positivo    Falso Negativo
    Real: No        Falso Positivo        Verdadero Negativo
    
    Para ClinDoc Agent:
    - VP: La IA detectó algo correcto y el médico lo aprobó
    - FP: La IA detectó algo pero el médico lo corrigió/rechazó
    - VN: La IA no mencionó algo irrelevante
    - FN: La IA no vio algo que el médico añadió como nuevo hallazgo
    """
    
    def __init__(self, ruta: str = "datos/auditorias"):
        self.ruta = Path(ruta)
        self.ruta.mkdir(parents=True, exist_ok=True)
        self.archivo_matriz = self.ruta / "matriz_confusion.json"
        self._cargar_matriz()
    
    def _cargar_matriz(self):
        """Carga la matriz existente o crea una nueva"""
        if self.archivo_matriz.exists():
            with open(self.archivo_matriz, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.vp = data.get("vp", 0)
                self.fp = data.get("fp", 0)
                self.vn = data.get("vn", 0)
                self.fn = data.get("fn", 0)
        else:
            self.vp = 0
            self.fp = 0
            self.vn = 0
            self.fn = 0
    
    def _guardar_matriz(self):
        """Guarda la matriz actualizada"""
        with open(self.archivo_matriz, "w", encoding="utf-8") as f:
            json.dump({
                "vp": self.vp,
                "fp": self.fp,
                "vn": self.vn,
                "fn": self.fn,
                "ultima_actualizacion": datetime.now().isoformat()
            }, f, indent=2)
    
    def registrar_validacion(self, validacion: ValidacionSeccion):
        """Registra una validación y actualiza la matriz"""
        
        if validacion.validacion == TipoValidacion.APROBADO:
            # La IA detectó bien
            self.vp += 1
        elif validacion.validacion == TipoValidacion.MODIFICADO:
            # La IA detectó pero había error
            if validacion.categoria_error == CategoriaError.FALSO_POSITIVO:
                self.fp += 1
            else:
                self.fp += 1  # Cualquier modificación cuenta como FP
        elif validacion.validacion == TipoValidacion.RECHAZADO:
            # La IA detectó completamente mal
            self.fp += 1
        elif validacion.validacion == TipoValidacion.NUEVOhallazgo:
            # La IA no vio algo que el médico añadió
            self.fn += 1
        
        self._guardar_matriz()
    
    def calcular_metricas(self) -> Dict:
        """Calcula métricas de rendimiento"""
        total = self.vp + self.fp + self.vn + self.fn
        
        precision = self.vp / (self.vp + self.fp) if (self.vp + self.fp) > 0 else 0
        exhaustividad = self.vp / (self.vp + self.fn) if (self.vp + self.fn) > 0 else 0
        f1 = 2 * (precision * exhaustividad) / (precision + exhaustividad) if (precision + exhaustividad) > 0 else 0
        exactitud = (self.vp + self.vn) / total if total > 0 else 0
        
        return {
            "matriz": {
                "vp": self.vp,
                "fp": self.fp,
                "vn": self.vn,
                "fn": self.fn
            },
            "metricas": {
                "precision": round(precision * 100, 2),
                "exhaustividad": round(exhaustividad * 100, 2),
                "f1": round(f1 * 100, 2),
                "exactitud": round(exactitud * 100, 2),
                "total_validaciones": total
            }
        }


class GestorAuditorias:
    """
    Gestor de auditorías de informes generados.
    
    FLUJO DE TRABAJO:
    1. Sistema genera informe → guarda como "pendiente"
    2. Médico abre informe → ve lo generado por IA
    3. Médico revisa cada sección:
       - Aprueba (VP)
       - Modifica con corrección (FP)
       - Añade nuevo hallazgo (FN)
    4. Sistema actualiza matriz de confusión
    5. Informe queda como "auditado" o "aprobado"
    """
    
    def __init__(self, ruta: str = "datos/auditorias"):
        self.ruta = Path(ruta)
        self.ruta.mkdir(parents=True, exist_ok=True)
        self.matriz = MatrizConfusion(ruta)
    
    def guardar_informe_pendiente(self, informe: Dict) -> str:
        """Guarda un nuevo informe generado por la IA"""
        informe_id = f"inf_{informe.get('paciente_nif', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        datos = {
            "informe_id": informe_id,
            "paciente_nif": informe.get("paciente_nif", ""),
            "paciente_nombre": informe.get("paciente_nombre", ""),
            "fecha_generacion": datetime.now().isoformat(),
            "estado": "pendiente",
            "secciones": informe.get("resumen", {}),
            "validaciones": []
        }
        
        archivo = self.ruta / f"{informe_id}.json"
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2)
        
        return informe_id
    
    def cargar_informe(self, informe_id: str) -> Optional[InformeAuditado]:
        """Carga un informe para auditoría"""
        archivo = self.ruta / f"{informe_id}.json"
        
        if not archivo.exists():
            return None
        
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return InformeAuditado(**data)
    
    def registrar_validacion(self, informe_id: str, validacion: ValidacionSeccion):
        """Registra una validación de sección"""
        archivo = self.ruta / f"{informe_id}.json"
        
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Añadir validación
        validacion_dict = validacion.model_dump()
        validacion_dict["timestamp"] = validacion.timestamp.isoformat()
        data["validaciones"].append(validacion_dict)
        
        # Actualizar matriz de confusión
        self.matriz.registrar_validacion(validacion)
        
        # Actualizar estado
        data["estado"] = "auditado"
        data["fecha_auditoria"] = datetime.now().isoformat()
        
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def aprobar_informe(self, informe_id: str, notas: str = ""):
        """Aprueba un informe completo"""
        archivo = self.ruta / f"{informe_id}.json"
        
        if archivo.exists():
            with open(archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            data["estado"] = "aprobado"
            data["fecha_auditoria"] = datetime.now().isoformat()
            data["notas_auditoria"] = notas
            
            with open(archivo, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    
    def listar_informes_pendientes(self) -> List[Dict]:
        """Lista todos los informes pendientes de auditoría"""
        informes = []
        
        for archivo in self.ruta.glob("inf_*.json"):
            with open(archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("estado") == "pendiente":
                    informes.append({
                        "informe_id": data["informe_id"],
                        "paciente": data.get("paciente_nombre", "Unknown"),
                        "nif": data.get("paciente_nif", "Unknown"),
                        "fecha": data.get("fecha_generacion", "")
                    })
        
        return informes
    
    def obtener_estadisticas(self) -> Dict:
        """Obtiene estadísticas de auditorías"""
        informes_pendientes = len(self.listar_informes_pendientes())
        metricas_matriz = self.matriz.calcular_metricas()
        
        return {
            "informes_pendientes": informes_pendientes,
            "matriz_confusion": metricas_matriz
        }


# === EJEMPLO DE USO ===
if __name__ == "__main__":
    # Ejemplo de flujo de trabajo
    
    print("="*60)
    print("  EJEMPLO: FLUJO DE AUDITORÍA MÉDICA")
    print("="*60)
    
    gestor = GestorAuditorias()
    
    # 1. Simular informe generado por IA
    print("\n[1] Sistema genera informe...")
    informe_demo = {
        "paciente_nif": "12345678Z",
        "paciente_nombre": "Juan Pérez",
        "resumen": {
            "Antecedentes": "Hipertensión arterial diagnosticada en 2020...",
            "Tratamiento": "Enalapril 5mg diario..."
        }
    }
    informe_id = gestor.guardar_informe_pendiente(informe_demo)
    print(f"   ✓ Informe guardado: {informe_id}")
    
    # 2. Médico aprueba una sección
    print("\n[2] Médico aprueba sección 'Antecedentes'...")
    validacion1 = ValidacionSeccion(
        seccion="Antecedentes",
        validacion=TipoValidacion.APROBADO,
        texto_original="Hipertensión arterial diagnosticada en 2020..."
    )
    gestor.registrar_validacion(informe_id, validacion1)
    print("   ✓ Aprobado (VP)")
    
    # 3. Médico detecta falso positivo
    print("\n[3] Médico detecta error en 'Tratamiento'...")
    validacion2 = ValidacionSeccion(
        seccion="Tratamiento",
        validacion=TipoValidacion.MODIFICADO,
        texto_original="Enalapril 5mg diario...",
        texto_modificado="Losartán 50mg diario (cambiado por tolerancia)",
        notas_medico="El paciente no toleraba Enalapril",
        categoria_error=CategoriaError.FALSO_POSITIVO
    )
    gestor.registrar_validacion(informe_id, validacion2)
    print("   ✓ Modificado (FP)")
    
    # 4. Médico añade hallazgo nuevo
    print("\n[4] Médico añade hallazgo que la IA no vio...")
    validacion3 = ValidacionSeccion(
        seccion="Alergias",
        validacion=TipoValidacion.NUEVOhallazgo,
        texto_original="",
        notas_medico="Alergia a penicilina no registrada",
        categoria_error=CategoriaError.OMISION
    )
    gestor.registrar_validacion(informe_id, validacion3)
    print("   ✓ Nuevo hallazgo (FN)")
    
    # 5. Aprobar informe
    print("\n[5] Médico aprueba informe final...")
    gestor.aprobar_informe(informe_id, "Informe revisado y aprobado con modificaciones")
    print("   ✓ Aprobado")
    
    # 6. Ver matriz de confusión
    print("\n[6] Matriz de Confusión:")
    estadisticas = gestor.obtener_estadisticas()
    matriz = estadisticas["matriz_confusion"]["matriz"]
    metricas = estadisticas["matriz_confusion"]["metricas"]
    
    print(f"""
    ┌─────────────────────┬──────────────────┬─────────────────┐
    │                     │   Predicho: Sí   │  Predicho: No   │
    ├─────────────────────┼──────────────────┼─────────────────┤
    │   Real: Sí (Enfermo)│       VP: {matriz['vp']}       │       FN: {matriz['fn']}      │
    │   Real: No (Sano)   │       FP: {matriz['fp']}       │       VN: {matriz['vn']}      │
    └─────────────────────┴──────────────────┴─────────────────┘
    
    MÉTRICAS:
    • Precisión: {metricas['precision']}%
    • Exhaustividad: {metricas['exhaustividad']}%
    • F1: {metricas['f1']}%
    • Exactitud: {metricas['exactitud']}%
    """)
    
    print("="*60)
    print("  FLUJO DE AUDITORÍA COMPLETADO")
    print("="*60)