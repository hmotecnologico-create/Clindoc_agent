import time
import os
try:
    import PyPDF2
except ImportError:
    os.system("pip install PyPDF2")
    import PyPDF2

def extract_traditional(pdf_path):
    start = time.time()
    text = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text()
    return text, time.time() - start

def run_benchmark():
    pdf_path = "test_clinico.pdf"
    print(f"--- Iniciando Benchmarking de Ingesta: {pdf_path} ---")
    
    # Tradicional
    text_trad, time_trad = extract_traditional(pdf_path)
    print(f"\n[METODO TRADICIONAL (PyPDF2)]")
    print(f"Latencia: {round(time_trad, 4)}s")
    print(f"Muestra de Salida:\n{text_trad[:200]}")
    
    # Docling (Verificar si est listo)
    try:
        from docling.document_converter import DocumentConverter
        start_doc = time.time()
        converter = DocumentConverter()
        result = converter.convert(pdf_path)
        text_doc = result.document.export_to_markdown()
        time_doc = time.time() - start_doc
        print(f"\n[METODO INNOVADOR (Docling)]")
        print(f"Latencia: {round(time_doc, 4)}s")
        print(f"Muestra de Salida (Markdown):\n{text_doc[:200]}")
    except ImportError:
        print("\n[AVISO] Docling an no est disponible en el entorno (Instalacin en curso).")

if __name__ == "__main__":
    run_benchmark()
