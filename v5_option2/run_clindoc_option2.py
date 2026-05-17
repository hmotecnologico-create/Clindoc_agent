import os
import sys
import shutil
from pathlib import Path

import yaml


def _load_config() -> dict:
    cfg_path = Path(__file__).with_name("config_option2.yaml")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_guion(guion_path: Path) -> dict:
    with guion_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    secciones = []
    for idx, sec in enumerate(data.get("secciones", []), start=1):
        instruccion = sec.get("instruccion")
        if not instruccion:
            campos = sec.get("campos", [])
            nombres = [c.get("nombre", "campo") for c in campos]
            instruccion = (
                f"Redacta la seccion '{sec.get('titulo', f'S{idx}')}' con base en evidencias del corpus. "
                f"Prioriza los campos: {', '.join(nombres)}. "
                "Incluye solo informacion sustentada por evidencias."
            )
        secciones.append(
            {
                "id": sec.get("id", f"S{idx}"),
                "titulo": sec.get("titulo", f"Seccion {idx}"),
                "instruccion": instruccion,
            }
        )

    return {"titulo": data.get("titulo", "Informe de Baja Laboral"), "secciones": secciones}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    cfg = _load_config()

    if cfg.get("perfil") != "baja_laboral":
        raise ValueError("Esta version solo permite el perfil 'baja_laboral'.")

    # Imports tardios para no romper carga de config
    from run_clindoc import OrquestadorLangGraph

    runtime = cfg.get("runtime", {})
    dashboard_output = runtime.get("dashboard_output", "dashboard_data_option2.json")
    os.environ["CLINDOC_DASHBOARD_FILE"] = dashboard_output

    guion_rel = cfg.get("guion", {}).get("ruta", "guiones/baja_laboral.yaml")
    guion_path = root / guion_rel
    config_gui = _load_guion(guion_path)

    paciente = cfg.get("paciente_demo", {"nombre": "Paciente Demo", "nif": "12345678Z"})

    print("=" * 60)
    print("ClinDoc Agent v5 - Opcion 2 (alcance acotado)")
    print(f"Perfil: {cfg.get('perfil')}")
    print(f"Guion: {guion_path}")
    print(f"Paciente demo: {paciente.get('nombre')} ({paciente.get('nif')})")
    print("=" * 60)

    sistema = OrquestadorLangGraph(config_gui)
    resultados = sistema.ejecutar(paciente)

    # El motor actual guarda por defecto en dashboard_data.json.
    # Para la variante opcion 2 dejamos una copia dedicada.
    default_dash = root / "dashboard_data.json"
    if default_dash.exists() and dashboard_output:
        shutil.copy2(default_dash, root / dashboard_output)
        print(f"Telemetria copiada en: {root / dashboard_output}")

    print("\nResumen generado por secciones:")
    for titulo, contenido in resultados.items():
        print(f"\n[{titulo}]")
        print((contenido[:400] + "...") if len(contenido) > 400 else contenido)


if __name__ == "__main__":
    main()
