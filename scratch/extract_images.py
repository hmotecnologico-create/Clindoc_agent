import zipfile
import os

docx_path = r"f:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\DOC_TFM\TFM_V1.docx"
out_dir = r"f:\HMO\TFM_DATA\2026\TFM\PROYECTO_CLINDOC\DOC_TFM\Graficas_TFM\Patron_Original"

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

if os.path.exists(docx_path):
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        for file in zip_ref.namelist():
            if file.startswith('word/media/'):
                zip_ref.extract(file, out_dir)
                print(f"Extraída: {file}")
else:
    print("Archivo no encontrado.")
