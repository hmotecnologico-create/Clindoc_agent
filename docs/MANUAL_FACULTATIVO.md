# 👨‍⚕️ Manual de Usuario Facultativo (Doctor)

Bienvenido a **ClinDoc Agent**, el asistente de auditoría clínica basado en Inteligencia Artificial. Este manual está diseñado para guiar al médico o facultativo en el uso de la herramienta para validar expedientes y emitir auditorías con total confianza.

## 1. Acceso al Sistema

1. Al abrir la plataforma, diríjase a la barra lateral izquierda.
2. En la sección **"Modo de Acceso"**, seleccione el perfil **"👨‍⚕️ Doctor (Facultativo)"**.
3. En el **"Buscador de Pacientes"**, seleccione el paciente que desea auditar. Puede buscar por NIF o por Nombre.

## 2. Entendiendo el Dashboard Principal

Una vez seleccionado un paciente, visualizará en la parte superior los **KPIs Clave**:
- **Documentos**: Número de documentos analizados en el expediente del paciente.
- **Tiempo Total**: Tiempo que le tomó al sistema procesar y estructurar la información (generalmente unos pocos segundos).
- **Confianza**: El nivel de certeza de la IA al extraer los diagnósticos (si está por debajo de 80%, revise detenidamente).
- **Riesgos**: Indicador de posibles discrepancias en fechas, caducidad documental o fraude de identidad.

## 3. Pestañas de Trabajo

El panel de control se divide en tres herramientas fundamentales para su trabajo:

### A. 📈 Historial Clínico
Esta pestaña muestra la **Evolución Clínica del Paciente**.
- Visualizará una línea de tiempo gráfica (Timeline) que ubica cronológicamente todas las consultas, analíticas, resonancias y tratamientos encontrados en el historial desordenado del paciente.
- **Buscador Semántico:** Puede escribir términos como "diabetes" o "cirugía" para filtrar la línea de tiempo y encontrar rápidamente antecedentes clave.

### B. 💬 Chat Asistente
El sistema incluye un Asistente Médico de IA especializado (Gemma) que ha leído todo el expediente.
- **Aclaraciones:** Escriba preguntas como *"¿En qué página menciona la hipertensión?"* o *"¿Cuál fue el resultado del último ecocardiograma?"*. Seleccione el tipo de mensaje "❓ Pregunta".
- **Correcciones (Crucial para Auditoría):** Si la IA ha deducido algo incorrecto en su resumen, envíe una corrección (Ej. *"El paciente no tiene diabetes, tiene prediabetes"*). Seleccione el tipo **"✏️ Corrección"**. 
  > *Nota Legal: Usted es el responsable final del informe. Toda corrección queda registrada y modifica el informe final emitido.*

### C. 📅 Trazabilidad Folios
Muestra un Diagrama de Gantt indicando **cuándo ingresó cada documento al sistema**. Útil para detectar expedientes añadidos de forma tardía o que sobrepasan el tiempo legal estipulado para bajas médicas (Incapacidad Temporal).

## 4. Validación Final
Recuerde que el informe PDF generado en la carpeta `docs/informes/` incluye las advertencias de riesgo. Si ha realizado correcciones a través del chat, estas quedan registradas como *Chain of Thought* (Trazabilidad de pensamiento) para justificar su decisión clínica final.
