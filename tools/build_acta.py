"""Genera el acta en PDF que el tablero entrega al aceptar la propuesta.

El PDF es un archivo estático servido desde el mismo origen que la app: el QR
del tablero apunta a él, así que el celular que lo escanea abre su visor nativo
sin pasar por la red de nadie más.

Los números salen del paquete real del lote (frontend/mock/package-nar-001.json)
y no se recalculan aquí: este script sólo los redacta. La versión humanizada de
cada tecnicismo vive en HUMANIZADO, que es la parte que el asistente reescribe.

    python tools/build_acta.py

Requiere reportlab. No entra en requirements.txt porque el despliegue no genera
el PDF: lo lee ya construido del repositorio.
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "frontend" / "mock" / "package-nar-001.json"
OUT = ROOT / "frontend" / "informes" / "acta-plan-el-rosal.pdf"

BRAND = HexColor("#00aedb")
BRAND_DEEP = HexColor("#00718f")
BRAND_SOFT = HexColor("#e2f6fc")
INK = HexColor("#1f2a30")
MUTED = HexColor("#626d76")
LINE = HexColor("#dfe4e6")
LOW = HexColor("#c0392b")
MID = HexColor("#e8a33d")
HIGH = HexColor("#2e8b57")
PAPER = HexColor("#ffffff")

W, H = A4
MARGIN = 44
COL = W - MARGIN * 2

NIVEL_COLOR = {"critico": LOW, "bajo": MID, "adecuado": HIGH}
NIVEL_TEXTO = {"critico": "muy por debajo", "bajo": "por debajo", "adecuado": "alcanza"}

# Lo que el sistema escribe a la izquierda y lo que una persona entiende a la
# derecha. Es la tabla que hace visible el trabajo del asistente.
HUMANIZADO = [
    ("Proceso gaussiano Matérn por nutriente",
     "Con 18 mediciones el sistema dibuja el resto del lote, y además dice dónde\n"
     "está adivinando más."),
    ("Balance de masa sobre la capa muestreada",
     "Convierte el porcentaje del sensor en kilos por hectárea, contando 20 cm de\n"
     "profundidad. No se resta del porcentaje del bulto."),
    ("Factor de disponibilidad 0,001",
     "De todo el nutriente que hay en el suelo, la planta sólo alcanza una milésima.\n"
     "Es un supuesto conservador de la demo, no una medición."),
    ("Óptimo lexicográfico entre combinaciones enteras factibles",
     "Se probaron todas las mezclas posibles con bultos enteros y ganó la que menos\n"
     "deja faltando; a igual faltante, la que menos desperdicia."),
    ("Incertidumbre predictiva sobre el umbral",
     "Las franjas rayadas del mapa: ahí el sistema no sabe y hace falta ir a medir."),
    ("validation_status: requires_technical_validation",
     "Nadie aplica esto hasta que un técnico lo firme. Este documento es esa firma."),
]


def load():
    pkg = json.loads(PACKAGE.read_text(encoding="utf-8"))
    zonas = []
    for rec in pkg["proposal"]["recommendations"]:
        assessment = rec["agronomic_assessment"]
        plan = rec["integer_plan"]
        need = assessment["crop_requirement"]
        have = assessment["estimated_crop_available"]
        niveles = {}
        for n in ("N", "P", "K"):
            ratio = have[n] / need[n] if need[n] else 1
            niveles[n] = "critico" if ratio < 0.5 else ("bajo" if ratio < 1 else "adecuado")
        zonas.append({
            "id": rec["zone_id"].replace("zone-", ""),
            "area": assessment["zone_area"]["value"],
            "bultos": [(f["label"], f["bags"], f["bag_weight"]["value"]) for f in plan["formulations"]],
            "total_bultos": plan["total_bags"],
            "total_kg": plan["total_weight"]["value"],
            "falta": assessment["calculated_deficit"],
            "niveles": niveles,
        })
    return pkg, zonas


class Sheet:
    """Envoltura fina sobre el canvas: la página se escribe de arriba hacia abajo."""

    def __init__(self, pdf: canvas.Canvas):
        self.pdf = pdf
        self.y = H - MARGIN

    def space(self, amount):
        self.y -= amount

    def text(self, string, size=9.5, font="Helvetica", color=INK, x=MARGIN, leading=None):
        leading = leading or size + 3.2
        self.pdf.setFont(font, size)
        self.pdf.setFillColor(color)
        for line in string.split("\n"):
            for wrapped in simpleSplit(line, font, size, COL - (x - MARGIN)):
                self.pdf.drawString(x, self.y, wrapped)
                self.y -= leading
        return self.y

    def rule(self, color=LINE, gap=9):
        self.y -= gap
        self.pdf.setStrokeColor(color)
        self.pdf.setLineWidth(0.6)
        self.pdf.line(MARGIN, self.y, W - MARGIN, self.y)
        self.y -= gap

    def heading(self, number, title):
        self.pdf.setFillColor(BRAND)
        self.pdf.circle(MARGIN + 6, self.y + 3, 7.5, stroke=0, fill=1)
        self.pdf.setFillColor(PAPER)
        self.pdf.setFont("Helvetica-Bold", 8)
        self.pdf.drawCentredString(MARGIN + 6, self.y + 0.6, number)
        self.pdf.setFillColor(BRAND_DEEP)
        self.pdf.setFont("Helvetica-Bold", 11.5)
        self.pdf.drawString(MARGIN + 20, self.y, title)
        self.y -= 18


def header(sheet, pkg, folio):
    pdf = sheet.pdf
    pdf.setFillColor(BRAND)
    pdf.rect(0, H - 8, W, 8, stroke=0, fill=1)

    pdf.setFillColor(BRAND_DEEP)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(MARGIN, sheet.y - 12, "IOmido")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(MARGIN + 74, sheet.y - 12, "Inteligencia operativa para el acopio")

    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(W - MARGIN, sheet.y - 6, f"Folio {folio}")
    pdf.drawRightString(W - MARGIN, sheet.y - 17, "Acopio Pasto · Pasto, Nariño")
    sheet.y -= 32
    sheet.rule(gap=7)


def portada(sheet, pkg, zonas, decidido_en):
    pdf = sheet.pdf
    plot = pkg["plot"]
    perfil = pkg["crop_profile"]

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(MARGIN, sheet.y, "Plan de fertilización aceptado")
    sheet.y -= 20
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        MARGIN, sheet.y,
        f"{plot['name']} · {plot['municipality']} · {plot['area']['value']:.2f} ha"
        f" · {perfil['crop']} {perfil['variety']}",
    )
    sheet.y -= 22

    total_bultos = sum(z["total_bultos"] for z in zonas)
    total_kg = sum(z["total_kg"] for z in zonas)
    caja_alto = 46
    pdf.setFillColor(BRAND_SOFT)
    pdf.roundRect(MARGIN, sheet.y - caja_alto, COL, caja_alto, 6, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DEEP)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(MARGIN + 14, sheet.y - 18, "En una frase")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        MARGIN + 14, sheet.y - 33,
        f"Lleve {total_bultos} bultos ({total_kg:.0f} kg) al lote y repártalos en tres zonas: "
        "la de abajo pide casi todo.",
    )
    sheet.y -= caja_alto + 16


def tabla_zonas(sheet, zonas):
    pdf = sheet.pdf
    sheet.heading("1", "Qué hay que llevar y dónde va")

    cols = [MARGIN, MARGIN + 54, MARGIN + 104, MARGIN + 250, MARGIN + 330]
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 7.6)
    for x, label in zip(cols, ("ZONA", "SUPERFICIE", "QUÉ COMPRAR", "CUÁNTO", "LO QUE MÁS FALTA")):
        pdf.drawString(x, sheet.y, label)
    sheet.y -= 6
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.6)
    pdf.line(MARGIN, sheet.y, W - MARGIN, sheet.y)
    sheet.y -= 14

    for zona in zonas:
        alto = 13 * len(zona["bultos"]) + 8
        top = sheet.y + 9
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(cols[0], sheet.y, f"Zona {zona['id']}")
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(cols[1], sheet.y, f"{zona['area']:.2f} ha")

        y_row = sheet.y
        for label, bags, peso in zona["bultos"]:
            pdf.setFont("Helvetica-Bold", 9.5)
            pdf.setFillColor(BRAND_DEEP)
            pdf.drawString(cols[2], y_row, label)
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica", 9.5)
            unidad = "bulto" if bags == 1 else "bultos"
            pdf.drawString(cols[3], y_row, f"{bags} {unidad} de {peso:.0f} kg")
            y_row -= 13

        peor = min(zona["niveles"].items(), key=lambda kv: zona["falta"][kv[0]] * -1)
        nutriente, nivel = peor
        pdf.setFillColor(NIVEL_COLOR[nivel])
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(cols[4], sheet.y, nutriente)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8.3)
        pdf.drawString(cols[4] + 12, sheet.y, f"{NIVEL_TEXTO[nivel]}, faltan {zona['falta'][nutriente]:.0f} kg/ha")

        sheet.y = min(y_row, sheet.y - 13) - 4
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(0.4)
        pdf.line(MARGIN, sheet.y + 6, W - MARGIN, sheet.y + 6)
        sheet.y -= 6

    total_bultos = sum(z["total_bultos"] for z in zonas)
    total_kg = sum(z["total_kg"] for z in zonas)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(cols[2], sheet.y, "Total del lote")
    pdf.drawString(cols[3], sheet.y, f"{total_bultos} bultos · {total_kg:.0f} kg")
    sheet.y -= 16
    sheet.text(
        "Un grado 30-30-40 quiere decir que el bulto es 30 % nitrógeno, 30 % fósforo y 40 % potasio\n"
        "de su propio peso. No hace falta convertir nada: los bultos ya vienen contados.",
        size=8.4, color=MUTED,
    )
    sheet.space(8)


def antes_de_aplicar(sheet, pkg):
    sheet.heading("2", "Antes de aplicar, mire el clima")
    pdf = sheet.pdf
    riesgos = pkg["climate"]["risks"][:3]
    textos = {
        "frost": ("Helada", "Puede bajar la temperatura de noche. Proteja las zonas expuestas antes de la mínima."),
        "drought": ("Falta de agua", "Si el suelo está seco, el abono no se disuelve: aplace la aplicación."),
        "late_blight": ("Gota", "Revise las hojas de abajo y consulte al técnico antes de cualquier preventivo."),
    }
    for riesgo in riesgos:
        titulo, detalle = textos.get(riesgo["type"], (riesgo["type"], ""))
        ventana = riesgo["window"]
        confianza = int(riesgo["confidence"]["value"] * 100)
        pdf.setFillColor(MID)
        pdf.circle(MARGIN + 3, sheet.y + 3, 3, stroke=0, fill=1)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(MARGIN + 12, sheet.y, titulo)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8.4)
        pdf.drawString(MARGIN + 12 + pdf.stringWidth(titulo, "Helvetica-Bold", 9.5) + 8, sheet.y,
                       f"del {ventana['start']} al {ventana['end']} · el modelo le da {confianza} % de confianza")
        sheet.y -= 12
        sheet.text(detalle, size=9, x=MARGIN + 12)
        sheet.space(3)
    sheet.text(
        "El clima de este documento viene de un archivo guardado, no de una consulta en vivo.\n"
        "Refresque las fuentes antes de salir a campo.",
        size=8.4, color=LOW,
    )
    sheet.space(6)


def por_que(sheet, pkg, zonas):
    sheet.heading("3", "Por qué esta mezcla y no otra")
    plan = pkg["proposal"]["recommendations"][0]["integer_plan"]
    evaluadas = plan["optimizer"]["evaluated_combinations"]
    factibles = plan["optimizer"]["feasible_combinations"]
    sheet.text(
        f"El sistema probó {evaluadas:,} combinaciones de bultos enteros y {factibles} cumplían los "
        "límites de seguridad.".replace(",", "."),
        size=9.5,
    )
    sheet.text(
        "Entre esas eligió, en este orden: la que menos nutriente deja faltando, la que menos "
        "desperdicia, la que usa menos bultos y la que mezcla menos productos distintos. "
        "Ninguna zona queda con faltante.",
        size=9.5,
    )
    sheet.space(4)


def firma(sheet, pkg, decidido_en, decision_id):
    pdf = sheet.pdf
    alto = 58
    pdf.setFillColor(HexColor("#f7fbfc"))
    pdf.setStrokeColor(HexColor("#a8e2f2"))
    pdf.setLineWidth(0.8)
    pdf.roundRect(MARGIN, sheet.y - alto, COL, alto, 6, stroke=1, fill=1)

    pdf.setFillColor(HIGH)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(MARGIN + 14, sheet.y - 18, "ACEPTADO POR UN TÉCNICO")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 9.2)
    pdf.drawString(MARGIN + 14, sheet.y - 32, "Juan Morales · técnico del Acopio Pasto")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.3)
    pdf.drawString(MARGIN + 14, sheet.y - 45, f"{decidido_en} · decisión {decision_id}")
    pdf.drawRightString(W - MARGIN - 14, sheet.y - 45, f"propuesta {pkg['proposal']['id']}")
    sheet.y -= alto + 10


def pie(pdf, numero, total):
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.4)
    pdf.drawString(MARGIN, 28, "IOmido NPK 4.0 · documento generado por el tablero del acopio")
    pdf.drawRightString(W - MARGIN, 28, f"{numero} de {total}")
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.5)
    pdf.line(MARGIN, 38, W - MARGIN, 38)


def pagina_dos(sheet, pkg):
    pdf = sheet.pdf
    sheet.heading("4", "Del tecnicismo al castellano")
    sheet.text(
        "El sistema calcula en su idioma. Esta columna es la traducción que hace el asistente de "
        "IOmido para que el acta se lea sin diccionario.",
        size=9, color=MUTED,
    )
    sheet.space(8)

    for tecnico, humano in HUMANIZADO:
        top = sheet.y + 9
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Oblique", 8.4)
        for line in simpleSplit(tecnico, "Helvetica-Oblique", 8.4, 168):
            pdf.drawString(MARGIN + 6, sheet.y, line)
            sheet.y -= 11
        y_tecnico = sheet.y
        sheet.y = top
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 9.2)
        for parrafo in humano.split("\n"):
            for line in simpleSplit(parrafo, "Helvetica", 9.2, COL - 196):
                pdf.drawString(MARGIN + 190, sheet.y, line)
                sheet.y -= 12
        sheet.y = min(sheet.y, y_tecnico) - 4

        pdf.setStrokeColor(BRAND)
        pdf.setLineWidth(1.2)
        pdf.line(MARGIN, sheet.y + 12, MARGIN, top + 4)
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(0.4)
        pdf.line(MARGIN, sheet.y + 4, W - MARGIN, sheet.y + 4)
        sheet.y -= 8

    sheet.space(6)
    sheet.heading("5", "Lo que el sistema no sabe")
    for unknown in pkg["proposal"]["explanation"]["unknowns"]:
        pdf.setFillColor(LOW)
        pdf.circle(MARGIN + 3, sheet.y + 3, 2.4, stroke=0, fill=1)
        sheet.text(unknown, size=9.2, x=MARGIN + 12)
        sheet.space(1)
    sheet.space(8)

    sheet.heading("6", "De dónde salen los números")
    modelo = pkg["model_run"]
    evidencia = pkg["proposal"]["explanation"]["evidence"]
    filas = [
        ("Mediciones usadas", f"{pkg['measurements']['valid_for_model']} de {pkg['measurements']['count']} lecturas dentro del lote"),
        ("Modelo espacial", f"{modelo['model_name']} {modelo['model_version']}"),
        ("Error medio del modelo", f"{modelo['metrics']['mean_rmse']['gp']:.2f} puntos de porcentaje (validación dejando uno fuera)"),
        ("Fuentes de clima", ", ".join(evidencia["source_names"][:3])),
        ("Huella de las entradas", evidencia["input_hash"][:32] + "…"),
        ("Perfil de cultivo", f"{pkg['crop_profile']['id']} · sin validar por agrónomo local"),
    ]
    for etiqueta, valor in filas:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawString(MARGIN, sheet.y, etiqueta)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 8.6)
        for line in simpleSplit(valor, "Helvetica", 8.6, COL - 150):
            pdf.drawString(MARGIN + 148, sheet.y, line)
            sheet.y -= 11
        sheet.y -= 2

    sheet.space(10)
    alto = 40
    pdf.setFillColor(BRAND_SOFT)
    pdf.roundRect(MARGIN, sheet.y - alto, COL, alto, 6, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DEEP)
    pdf.setFont("Helvetica-Bold", 8.6)
    pdf.drawString(MARGIN + 14, sheet.y - 15, "Sobre el uso de inteligencia artificial")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 8.3)
    pdf.drawString(
        MARGIN + 14, sheet.y - 28,
        "Los cálculos los hacen modelos deterministas y auditables. La IA sólo redactó este acta: "
        "tradujo los tecnicismos, no tocó un solo número.",
    )
    sheet.y -= alto


def build():
    pkg, zonas = load()
    decidido_en = "16 de agosto de 2026, 09:14"
    decision_id = "decision-7c41a9e0b3f2"
    folio = "AC-2026-0816-001"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUT), pagesize=A4)
    pdf.setTitle("Acta de fertilización · Lote El Rosal")
    pdf.setAuthor("IOmido · Acopio Pasto")
    pdf.setSubject("Plan de fertilización por zonas aceptado por un técnico")

    sheet = Sheet(pdf)
    header(sheet, pkg, folio)
    portada(sheet, pkg, zonas, decidido_en)
    tabla_zonas(sheet, zonas)
    antes_de_aplicar(sheet, pkg)
    por_que(sheet, pkg, zonas)
    firma(sheet, pkg, decidido_en, decision_id)
    pie(pdf, 1, 2)

    pdf.showPage()
    sheet = Sheet(pdf)
    header(sheet, pkg, folio)
    pagina_dos(sheet, pkg)
    pie(pdf, 2, 2)

    pdf.save()
    print(f"escrito {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.1f} kB)")


if __name__ == "__main__":
    build()
