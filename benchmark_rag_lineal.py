# -*- coding: utf-8 -*-
"""Linea base de RAG LINEAL (no agentico) frente al pipeline multiagente (PI-2 / OE-4).

RAG lineal = una sola pasada por seccion: recuperacion semantica top-k sobre TODA la coleccion del
paciente (sin enrutado por tipo de documento), todos los fragmentos concatenados en UN unico prompt,
una generacion con gemma3:4b, sin agentes, sin aislamiento por documento, sin filtros
posteriores y sin ciclo de reintento. Reutiliza las colecciones Qdrant ya construidas de los 5
pacientes (mismo indice y mismo modelo de embeddings que el pipeline).

Metricas DETERMINISTAS, aplicadas identicamente a los informes del pipeline (dashboard_data.json) y
a los de la linea base:
  M1 cobertura de cita   : % de segmentos con contenido que llevan [Fuente: ...]
  M2 cita valida         : % de citas cuyo folio existe en la carpeta del paciente
  M3 sustento lexico     : % de segmentos citados cuyo contenido (numeros y palabras >=5 letras)
                           aparece en >=60 % en el folio citado (proxy de atribucion correcta)
  M4 numeros no respaldados: cifras de >=8 digitos del texto que NO aparecen en el folio citado
  M3b pares frase-folio  : igual que M3 pero por cada par (frase, folio citado), sin tomar el mejor folio
  M5 abstencion          : % de secciones que declaran "Sin informacion documental"
Uso: python benchmark_rag_lineal.py [NIF ...]   (por defecto los 5 pacientes)
"""
import hashlib, json, re, sys, time, unicodedata, urllib.request
from pathlib import Path

MODELO = "gemma3:4b"
TOPK = 5
NUM_PREDICT = 400
EXP = Path("datos/expedientes")
SALIDA = Path("benchmark_rag_lineal_resultado.json")
STOP = set("para como este esta estos estas desde entre sobre segun donde cuando tiene tienen debe puede fecha paciente documento informe".split())
RE_BRACKET = re.compile(r'\[[^\]]*?\.(?:pdf|docx|txt|md)[^\]]*\]', re.I)
RE_FOLIO = re.compile(r'([A-Za-z]{2,6}_\d{2,4}\.(?:pdf|docx|txt|md))', re.I)
_cache = {}


def norm(t):
    return unicodedata.normalize("NFD", t.lower()).encode("ascii", "ignore").decode()


def texto_folio(nif, nombre):
    k = (nif, nombre)
    if k in _cache:
        return _cache[k]
    f = EXP / nif / nombre
    txt = ""
    try:
        if f.suffix.lower() == ".pdf":
            import pypdf
            txt = "".join(p.extract_text() or "" for p in pypdf.PdfReader(str(f)).pages)
        elif f.suffix.lower() == ".docx":
            from docx import Document
            txt = "\n".join(p.text for p in Document(str(f)).paragraphs)
        elif f.exists():
            txt = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        txt = ""
    _cache[k] = norm(txt)
    return _cache[k]


def tokens_contenido(seg):
    s = norm(RE_BRACKET.sub("", seg))
    nums = re.findall(r"\d{2,}", s)
    pals = [w for w in re.findall(r"[a-z]{5,}", s) if w not in STOP]
    return set(nums + pals)


def segmentos(texto):
    out = []
    for linea in texto.split("\n"):
        for seg in re.split(r"(?<=[\.\]])\s+(?=[A-ZÁÉÍÓÚ])", linea.strip()):
            s = seg.strip()
            if len(RE_BRACKET.sub("", s).strip()) >= 25:
                out.append(s)
    return out


def metricas(nif, textos):
    seg_tot = seg_cit = cit_tot = cit_ok = sust_tot = sust_ok = num_no = abst = par_tot = par_ok = 0
    for t in textos:
        if "sin informaci" in norm(t) and len(t) < 160:
            abst += 1
            continue
        for s in segmentos(t):
            seg_tot += 1
            citas = sorted(set(RE_FOLIO.findall(" ".join(RE_BRACKET.findall(s)))))
            if not citas:
                continue
            seg_cit += 1
            tk = tokens_contenido(s)
            mejor = 0.0
            for c in citas:
                cit_tot += 1
                existe = (EXP / nif / c.strip()).exists()
                cit_ok += existe
                if existe and tk:
                    ft = texto_folio(nif, c.strip())
                    frac = sum(1 for w in tk if w in ft) / len(tk)
                    mejor = max(mejor, frac)
                    par_tot += 1
                    par_ok += frac >= 0.6
                    for n in re.findall(r"\d{8,}", RE_BRACKET.sub("", s)):
                        if n not in ft:
                            num_no += 1
            if tk:
                sust_tot += 1
                sust_ok += mejor >= 0.6
    return {"secciones": len(textos), "abstenciones": abst, "segmentos": seg_tot, "segmentos_citados": seg_cit,
            "citas": cit_tot, "citas_validas": cit_ok, "segmentos_evaluables": sust_tot, "segmentos_sustentados": sust_ok,
            "numeros_no_respaldados": num_no, "pares_frase_folio": par_tot, "pares_sustentados": par_ok}


def generar(prompt):
    body = json.dumps({"model": MODELO, "prompt": prompt, "stream": False,
                       "options": {"num_predict": NUM_PREDICT, "temperature": 0.2, "seed": 42}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=1800).read())["response"].strip()


def prompt_lineal(titulo, instruccion, contexto):
    return (f"Eres un asistente que redacta la seccion '{titulo}' de un informe de incapacidad temporal a partir del contexto recuperado.\n"
            f"{instruccion or ''}\nUsa solo la informacion del contexto. Cita la fuente de cada afirmacion con el formato [Fuente: archivo#chunk_id]. "
            f"Si el contexto no aporta nada, responde: Sin informacion documental para esta seccion.\n\nCONTEXTO:\n{contexto}\n\nSECCION '{titulo}':")


def main():
    import yaml
    from agentes.indice_corpus import IndiceCorpus
    data = json.load(open("dashboard_data.json", encoding="utf-8"))["pacientes"]
    guion = yaml.safe_load(open("guiones/baja_laboral.yaml", encoding="utf-8"))["secciones"]
    nifs = sys.argv[1:] or list(data)
    res = json.load(open(SALIDA, encoding="utf-8")) if SALIDA.exists() else {}
    recalcular = "--recalcular" in sys.argv
    nifs = [n for n in nifs if not n.startswith("--")]
    if recalcular:
        for nif, r in res.items():
            if nif.startswith("_"): continue
            finales = {}
            for e in data[nif]["events"]:
                if e["type"] == "analisis_seccion":
                    finales[e["details"]["seccion"]] = e["details"]["texto"]
            r["pipeline"] = metricas(nif, list(finales.values()))
            r["lineal"] = metricas(nif, list(r["textos_lineal"].values()))
        nifs = []
    ic = IndiceCorpus() if nifs else None
    for nif in nifs:
        if nif in res and "lineal" in res[nif]:
            print("ya medido", nif); continue
        ic.patient_hash = hashlib.sha256(nif.encode()).hexdigest()
        ic.nombre_coleccion = f"expediente_{ic.patient_hash}"
        finales = {}
        for e in data[nif]["events"]:
            if e["type"] == "analisis_seccion":
                finales[e["details"]["seccion"]] = e["details"]["texto"]
        lineal, tiempos = {}, {}
        for s in guion:
            t0 = time.time()
            ev = ic.buscar_evidencias(s["titulo"], n=TOPK)
            ctx = "\n".join(f"- {x['texto']} [Fuente: {x['archivo']}#{x['chunk_id']}]" for x in ev)
            lineal[s["titulo"]] = generar(prompt_lineal(s["titulo"], s.get("instruccion"), ctx))
            tiempos[s["titulo"]] = round(time.time() - t0, 1)
            print(nif, s["id"], tiempos[s["titulo"]], "s", flush=True)
        res[nif] = {"pipeline": metricas(nif, list(finales.values())), "lineal": metricas(nif, list(lineal.values())),
                    "tiempo_lineal_s": tiempos, "textos_lineal": lineal}
        SALIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    tot = {"pipeline": {}, "lineal": {}}
    for nif, r in res.items():
        if nif.startswith("_"):
            continue
        for k in tot:
            for m, v in r[k].items():
                tot[k][m] = tot[k].get(m, 0) + v
    res["_total"] = tot
    SALIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(tot, indent=2))


if __name__ == "__main__":
    main()
