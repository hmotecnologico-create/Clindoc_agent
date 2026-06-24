# -*- coding: utf-8 -*-
"""Generador de corpus clinico sintetico con VOLUMEN REAL (~524 folios/paciente).
100% sintetico (RGPD), contenido VARIADO (no duplicado) via Faker + bancos clinicos.
Distribucion segun la tesis: 150 analiticas + 180 altas/urgencias + 120 radiologia + 74 consentimientos.
Inyecta trampas logicas (identidad cruzada + documentos caducados)."""
import os, random, sys, io
from pathlib import Path
from datetime import date, timedelta
from faker import Faker

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
fake = Faker("es_ES")
Faker.seed(2026); random.seed(2026)

PALABRAS_POR_FOLIO = 300  # convencion pagina clinica

def nif_valido():
    n = random.randint(10000000, 99999999)
    return f"{n}{'TRWAGMYFPDXBNJZSQVHLCKE'[n % 23]}"

# ───────────── BANCOS CLINICOS (para variedad real) ─────────────
CIE10 = [
    ("I10","Hipertension esencial primaria"),("E11.9","Diabetes mellitus tipo 2 sin complicaciones"),
    ("E78.5","Hiperlipidemia no especificada"),("J44.9","EPOC no especificada"),
    ("M54.5","Lumbalgia"),("M17.0","Gonartrosis primaria bilateral"),
    ("I25.10","Cardiopatia isquemica aterosclerotica"),("N18.3","Enfermedad renal cronica estadio 3"),
    ("K21.9","Enfermedad por reflujo gastroesofagico"),("F41.1","Trastorno de ansiedad generalizada"),
    ("J45.909","Asma no especificada no complicada"),("E03.9","Hipotiroidismo no especificado"),
    ("G43.909","Migrana no especificada"),("M75.100","Sindrome del manguito rotador"),
    ("S82.6","Fractura de maleolo lateral"),("C50.911","Neoplasia maligna de mama"),
    ("I48.91","Fibrilacion auricular no especificada"),("N40.0","Hiperplasia benigna de prostata"),
    ("L40.0","Psoriasis vulgar"),("K80.20","Colelitiasis sin colecistitis"),
]
PARAMS_LAB = [
    ("Hemoglobina","g/dL",(11.0,17.5),(13.0,17.0)),("Hematocrito","%",(33,52),(40,50)),
    ("Leucocitos","x10^3/uL",(3.0,18.0),(4.0,11.0)),("Plaquetas","x10^3/uL",(90,520),(150,400)),
    ("Glucosa","mg/dL",(65,260),(70,100)),("Creatinina","mg/dL",(0.5,2.4),(0.7,1.3)),
    ("Urea","mg/dL",(15,90),(15,45)),("Colesterol total","mg/dL",(120,320),(0,200)),
    ("HDL","mg/dL",(25,85),(40,200)),("LDL","mg/dL",(60,220),(0,130)),
    ("Trigliceridos","mg/dL",(40,400),(0,150)),("AST/GOT","U/L",(10,120),(5,40)),
    ("ALT/GPT","U/L",(8,150),(5,41)),("Bilirrubina total","mg/dL",(0.2,3.5),(0.1,1.2)),
    ("TSH","uUI/mL",(0.2,9.0),(0.4,4.0)),("Sodio","mmol/L",(128,148),(135,145)),
    ("Potasio","mmol/L",(3.0,5.8),(3.5,5.1)),("PCR","mg/L",(0.1,90),(0,5)),
    ("Hemoglobina glicada","%",(4.5,11.0),(4.0,5.6)),("Ferritina","ng/mL",(8,400),(30,300)),
]
SERVICIOS = ["Cardiologia","Neumologia","Traumatologia","Neurologia","Digestivo","Nefrologia",
             "Endocrinologia","Medicina Interna","Urgencias","Reumatologia","Oncologia Medica","Urologia"]
SINTOMAS = ["dolor toracico opresivo","disnea de moderados esfuerzos","mareo y sensacion de inestabilidad",
            "dolor lumbar irradiado a miembro inferior","palpitaciones","tos productiva persistente",
            "cefalea pulsatil","dolor abdominal en hipocondrio derecho","edemas en miembros inferiores",
            "perdida de fuerza en hemicuerpo derecho","fiebre de 38.5C de 48 horas de evolucion",
            "astenia y perdida de peso no intencionada"]
MEDICAMENTOS = ["Enalapril 10mg/24h","Metformina 850mg/12h","Atorvastatina 40mg/24h","Omeprazol 20mg/24h",
                "Salbutamol inhalado a demanda","Levotiroxina 75mcg/24h","Acido acetilsalicilico 100mg/24h",
                "Bisoprolol 5mg/24h","Furosemida 40mg/24h","Paracetamol 1g/8h","Ibuprofeno 600mg/8h",
                "Insulina glargina 20UI nocturna","Tamsulosina 0.4mg/24h","Sertralina 50mg/24h"]
HALLAZGOS_RX = ["sin condensaciones ni derrame pleural","leve cardiomegalia con indice cardiotoracico aumentado",
                "signos de atrapamiento aereo compatibles con EPOC","fractura costal consolidada en arco posterior",
                "patron intersticial bibasal","sin hallazgos patologicos significativos",
                "pinzamiento del espacio articular femorotibial medial"]
HALLAZGOS_RMN = ["protrusion discal L4-L5 con compromiso radicular","lesion isquemica lacunar en region periventricular",
                 "ausencia de realce patologico tras contraste","atrofia corticosubcortical acorde a la edad",
                 "rotura parcial del tendon supraespinoso","quiste sinovial en region poplitea"]
PROCEDIMIENTOS = ["artroscopia de rodilla","colecistectomia laparoscopica","cateterismo cardiaco diagnostico",
                  "endoscopia digestiva alta","biopsia guiada por ecografia","infiltracion epidural",
                  "implante de marcapasos","reseccion transuretral de prostata"]

def valor_param(p):
    nombre, uni, (lo, hi), (rlo, rhi) = p
    v = round(random.uniform(lo, hi), 2)
    flag = "Normal" if rlo <= v <= rhi else ("ALTO" if v > rhi else "BAJO")
    return nombre, v, uni, f"{rlo} - {rhi}", flag

def parrafo_clinico():
    return (f"{random.choice(['Se objetiva','Se evidencia','El paciente refiere','A la exploracion destaca','Se documenta'])} "
            f"{random.choice(SINTOMAS)}. {random.choice(['Se pauta','Se ajusta tratamiento con','Se mantiene'])} "
            f"{random.choice(MEDICAMENTOS)}. {random.choice(['Evolucion favorable.','Persiste sintomatologia.','Mejoria parcial tras 72h.','Se solicita control en consulta.','Se deriva a especialista.'])}")

# ───────────── GENERADORES POR TIPO ─────────────
def doc_analitica(fnum, pac, fecha):
    nparams = random.randint(8, 18)
    params = random.sample(PARAMS_LAB, nparams)
    filas = "\n".join(f"| {n} | {v} | {u} | {r} | {f} |" for (n,v,u,r,f) in (valor_param(p) for p in params))
    cuerpo = [f"# INFORME DE ANALISIS CLINICOS",
        f"**Hospital:** {fake.company()} | **Servicio:** Laboratorio de Analisis Clinicos",
        f"**Paciente:** {pac['nombre']} | **NIF:** {pac['nif']} | **N.H.C.:** {random.randint(100000,999999)}",
        f"**Fecha de extraccion:** {fecha.strftime('%d/%m/%Y')} | **Medico solicitante:** Dr/a. {fake.last_name()}, {random.choice(SERVICIOS)}",
        "", "## Resultados", "| Parametro | Resultado | Unidad | Valor de Referencia | Flag |",
        "|---|---|---|---|---|", filas, "",
        f"## Interpretacion clinica",
        " ".join(parrafo_clinico() for _ in range(random.randint(4,8)))]
    return "\n".join(cuerpo)

def doc_alta(fnum, pac, fecha):
    dx = random.sample(CIE10, random.randint(1,3))
    serv = random.choice(SERVICIOS)
    secciones = [f"# INFORME DE ALTA - {serv.upper()}",
        f"**Hospital:** {fake.company()} | **Servicio:** {serv}",
        f"**Paciente:** {pac['nombre']} | **NIF:** {pac['nif']} | **Episodio:** {random.randint(2000000,9999999)}",
        f"**Fecha ingreso:** {(fecha-timedelta(days=random.randint(1,12))).strftime('%d/%m/%Y')} | **Fecha alta:** {fecha.strftime('%d/%m/%Y')}",
        "", "## Motivo de consulta", random.choice(SINTOMAS).capitalize()+".",
        "## Antecedentes personales", " ".join(parrafo_clinico() for _ in range(random.randint(3,6))),
        "## Enfermedad actual", " ".join(parrafo_clinico() for _ in range(random.randint(6,12))),
        "## Exploracion fisica y pruebas complementarias", " ".join(parrafo_clinico() for _ in range(random.randint(5,9))),
        "## Evolucion y tratamiento", " ".join(parrafo_clinico() for _ in range(random.randint(6,12))),
        "## Diagnosticos (CIE-10)"] + [f"- **{c}**: {d}" for c,d in dx] + [
        "## Recomendaciones al alta", " ".join(parrafo_clinico() for _ in range(random.randint(3,6)))]
    return "\n".join(secciones)

def doc_radiologia(fnum, pac, fecha):
    mod = random.choice(["Radiografia","TC","RMN","Ecografia"])
    region = random.choice(["torax","columna lumbar","craneal","abdomen","rodilla derecha","hombro izquierdo"])
    hall = HALLAZGOS_RMN if mod in ("RMN","TC") else HALLAZGOS_RX
    cuerpo = [f"# INFORME RADIOLOGICO - {mod.upper()} DE {region.upper()}",
        f"**Hospital:** {fake.company()} | **Servicio:** Radiodiagnostico",
        f"**Paciente:** {pac['nombre']} | **NIF:** {pac['nif']}",
        f"**Fecha del estudio:** {fecha.strftime('%d/%m/%Y')} | **Radiologo:** Dr/a. {fake.last_name()}",
        f"**Resolucion de adquisicion:** {random.choice([150,200,300])} DPI",
        "", "## Tecnica", f"Se realiza {mod} de {region} {random.choice(['sin contraste','con contraste intravenoso','en proyecciones estandar'])}.",
        "## Hallazgos", " ".join(random.sample(hall, min(len(hall), random.randint(2,4)))) + ". " +
        " ".join(parrafo_clinico() for _ in range(random.randint(3,6))),
        "## Conclusion", random.choice(hall).capitalize()+"."]
    return "\n".join(cuerpo)

def doc_consentimiento(fnum, pac, fecha):
    proc = random.choice(PROCEDIMIENTOS)
    cuerpo = [f"# CONSENTIMIENTO INFORMADO - {proc.upper()}",
        f"**Centro:** {fake.company()} | **Paciente:** {pac['nombre']} | **NIF:** {pac['nif']}",
        f"**Fecha:** {fecha.strftime('%d/%m/%Y')}",
        "", "## Informacion del procedimiento",
        f"Se informa al paciente sobre la realizacion de {proc}. " + " ".join(parrafo_clinico() for _ in range(random.randint(3,5))),
        "## Riesgos y alternativas",
        "Se explican los riesgos generales (infeccion, hemorragia, reaccion anestesica) y especificos. " +
        " ".join(parrafo_clinico() for _ in range(random.randint(2,4))),
        "## Declaracion de consentimiento",
        f"D/Dna. {pac['nombre']} declara haber comprendido la informacion y otorga su consentimiento. "
        f"Firma del paciente y del facultativo Dr/a. {fake.last_name()}."]
    return "\n".join(cuerpo)

def contar_palabras(s): return len(s.split())

def generar_categoria(carpeta, prefijo, generador, pac, folios_objetivo, fmin, fmax):
    """Genera docs hasta alcanzar el objetivo de folios (palabras/300)."""
    pal_objetivo = folios_objetivo * PALABRAS_POR_FOLIO
    pal_acum, idx = 0, 1
    while pal_acum < pal_objetivo:
        fecha = fake.date_between(start_date=date(2015,1,1), end_date=date(2026,5,1))
        # concatenar varios sub-informes para que el archivo tenga varios folios
        nfolios_doc = random.randint(fmin, fmax)
        partes = []
        for _ in range(nfolios_doc):
            partes.append(generador(idx, pac, fake.date_between(start_date=date(2015,1,1), end_date=date(2026,5,1))))
        contenido = "\n\n---\n\n".join(partes)
        (carpeta / f"{prefijo}_{idx:03d}.md").write_text(contenido, encoding="utf-8")
        pal_acum += contar_palabras(contenido); idx += 1
    return idx-1, pal_acum

def generar_paciente(pac, base):
    carpeta = base / pac['nif']
    carpeta.mkdir(parents=True, exist_ok=True)
    tot_pal = 0
    plan = [("LAB", doc_analitica, 150, 2, 4), ("ALTA", doc_alta, 180, 1, 2),
            ("RAD", doc_radiologia, 120, 3, 5), ("CONS", doc_consentimiento, 74, 2, 3)]
    for pref, gen, fol, fmin, fmax in plan:
        n, pal = generar_categoria(carpeta, pref, gen, pac, fol, fmin, fmax)
        tot_pal += pal
        print(f"  {pref}: {n} archivos, ~{pal//PALABRAS_POR_FOLIO} folios ({pal:,} palabras)")
    return carpeta, tot_pal

# ───────────── EJECUCION ─────────────
BASE = Path("datos/expedientes_524")
if BASE.exists():
    import shutil; shutil.rmtree(BASE)
BASE.mkdir(parents=True)

pac1 = {"nombre": fake.name(), "nif": nif_valido()}
pac2 = {"nombre": fake.name(), "nif": nif_valido()}
print(f"PACIENTE 1: {pac1['nombre']} ({pac1['nif']})")
c1, p1 = generar_paciente(pac1, BASE)
print(f"  TOTAL P1: ~{p1//PALABRAS_POR_FOLIO} folios ({p1:,} palabras)\n")
print(f"PACIENTE 2: {pac2['nombre']} ({pac2['nif']})")
c2, p2 = generar_paciente(pac2, BASE)
print(f"  TOTAL P2: ~{p2//PALABRAS_POR_FOLIO} folios ({p2:,} palabras)\n")

# ───────────── TRAMPAS LOGICAS ─────────────
# Trampa identidad: doc del paciente 2 colado en carpeta del paciente 1
trampa_id = doc_alta(999, pac2, fake.date_between(start_date=date(2023,1,1), end_date=date(2026,1,1)))
(c1 / "TRAMPA_Identidad_Equivocada.md").write_text(trampa_id, encoding="utf-8")
# Trampa caducidad: doc muy antiguo (1998)
trampa_cad = doc_alta(998, pac1, date(1998,6,15))
(c1 / "TRAMPA_Documento_Caducado_1998.md").write_text(trampa_cad, encoding="utf-8")
print(f"Trampas inyectadas en {c1.name}: identidad ({pac2['nif']}) + caducado (1998)")

print(f"\n=== CORPUS GENERADO EN {BASE} ===")
print(f"Paciente 1: {pac1['nif']} (~{p1//PALABRAS_POR_FOLIO} folios)")
print(f"Paciente 2: {pac2['nif']} (~{p2//PALABRAS_POR_FOLIO} folios)")
