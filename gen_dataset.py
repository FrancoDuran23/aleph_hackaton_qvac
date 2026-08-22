#!/usr/bin/env python3
"""
Generador de carpetas crediticias sinteticas para el pipeline de riesgo.

Produce, por cada cliente:
  contrato.pdf      texto nativo
  escritura.pdf     a veces "escaneada" (rasterizada, rotada, con ruido) -> exige OCR
  recibos.pdf       tabla de pagos
  correspondencia.txt
  (algunos casos suman tasacion.pdf)

Y un ground_truth.json global con los valores reales, las contradicciones
inyectadas y el ruteo esperado, para medir el pipeline contra algo.

Uso:  python3 gen_dataset.py --n 20 --out ./dataset
"""

import argparse
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

W, H = A4

NOMBRES = [
    ("Juan", "Perez"), ("Maria", "Gonzalez"), ("Carlos", "Rodriguez"),
    ("Ana", "Martinez"), ("Luis", "Lopez"), ("Sofia", "Fernandez"),
    ("Diego", "Sanchez"), ("Valeria", "Romero"), ("Martin", "Diaz"),
    ("Lucia", "Alvarez"), ("Pablo", "Torres"), ("Camila", "Ruiz"),
    ("Jorge", "Ramirez"), ("Elena", "Flores"), ("Ricardo", "Acosta"),
    ("Paula", "Benitez"), ("Hernan", "Medina"), ("Rocio", "Castro"),
    ("Gustavo", "Ortiz"), ("Natalia", "Vega"), ("Federico", "Silva"),
    ("Mariana", "Rojas"), ("Emilio", "Cabrera"), ("Julieta", "Molina"),
]

CIUDADES = ["Salta", "San Salvador de Jujuy", "Tucuman", "Cordoba", "Rosario"]
CALLES = ["Belgrano", "Caseros", "Alvarado", "Mitre", "San Martin", "Balcarce"]

# Distintos formatos de monto, a proposito: el extractor tiene que normalizar.
def fmt_ars(v, estilo=0):
    if estilo == 0:
        return f"$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if estilo == 1:
        return f"ARS {v:,.0f}".replace(",", ".")
    if estilo == 2:
        return f"$ {v/1_000_000:.2f} millones".replace(".", ",")
    return f"$ {v}"


def fecha(d, m, y):
    return f"{d:02d}/{m:02d}/{y}"


# ---------------------------------------------------------------- documentos

def pdf_contrato(path, c):
    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2.5 * cm, rightMargin=2.5 * cm)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5,
                          leading=14, spaceAfter=6)
    st = []
    st.append(Paragraph("<b>CONTRATO DE MUTUO CON GARANTIA REAL</b>", ss["Title"]))
    st.append(Spacer(1, 10))
    st.append(Paragraph(
        f"En la ciudad de {c['sucursal']}, a los {c['contrato_dia']} dias del mes de "
        f"{c['contrato_mes_txt']} de {c['contrato_anio']}, entre BANCO REGIONAL S.A., "
        f"en adelante EL BANCO, y <b>{c['nombre']} {c['apellido']}</b>, DNI "
        f"{c['dni']}, con domicilio en {c['domicilio_contrato']}, en adelante EL DEUDOR, "
        "se conviene lo siguiente:", body))
    st.append(Spacer(1, 6))
    st.append(Paragraph(
        f"<b>PRIMERA - Objeto.</b> EL BANCO otorga a EL DEUDOR un prestamo por la suma "
        f"de {fmt_ars(c['capital_original'], c['estilo_monto'])} "
        f"(capital original).", body))
    st.append(Paragraph(
        f"<b>SEGUNDA - Plazo.</b> El prestamo se cancelara en "
        f"<b>{c['cuotas_contrato']} cuotas</b> mensuales, iguales y consecutivas, "
        f"venciendo la primera el {c['primer_venc']}.", body))
    st.append(Paragraph(
        f"<b>TERCERA - Tasa.</b> Se aplicara una tasa nominal anual del "
        f"{c['tna']}%, sobre saldos.", body))
    st.append(Paragraph(
        f"<b>CUARTA - Garantia.</b> En garantia del cumplimiento, EL DEUDOR "
        f"constituye hipoteca en primer grado sobre el inmueble matricula "
        f"<b>{c['matricula']}</b>, sito en {c['inmueble_dir']}, "
        f"segun escritura que se adjunta como Anexo I.", body))
    st.append(Paragraph(
        "<b>QUINTA - Mora.</b> La mora se producira de pleno derecho por el mero "
        "vencimiento de los plazos, sin necesidad de interpelacion judicial o "
        "extrajudicial alguna.", body))
    st.append(Paragraph(
        f"<b>SEXTA - Saldo.</b> Al {c['fecha_corte']}, el capital adeudado asciende "
        f"a {fmt_ars(c['capital_adeudado'], c['estilo_monto'])}.", body))
    st.append(Spacer(1, 24))
    st.append(Paragraph(
        f"____________________<br/>{c['nombre']} {c['apellido']}<br/>"
        f"DNI {c['dni']}", body))
    doc.build(st)


def _render_escritura_texto(c):
    """Devuelve las lineas de la escritura (se usa nativo o rasterizado)."""
    return [
        ("ESCRITURA NUMERO " + str(c["escritura_nro"]), True),
        ("", False),
        (f"En {c['sucursal']}, Republica Argentina, a {c['escritura_fecha']},", False),
        ("ante mi, Escribano Publico Titular del Registro N " + str(c["registro"]) + ",", False),
        ("COMPARECE:", False),
        ("", False),
        (f"{c['titular_escritura']}, DNI {c['dni_escritura']},", True),
        (f"con domicilio en {c['domicilio_escritura']},", False),
        ("", False),
        ("quien acredita ser titular de dominio del inmueble", False),
        (f"identificado bajo MATRICULA {c['matricula_escritura']},", True),
        (f"con superficie de {c['superficie']} m2, ubicado en", False),
        (f"{c['inmueble_dir']}.", False),
        ("", False),
        (f"VALUACION FISCAL: {fmt_ars(c['garantia_valor'], 1)}", True),
        (f"FECHA DE TASACION: {c['tasacion_fecha']}", True),
        ("", False),
        ("Se constituye HIPOTECA EN PRIMER GRADO a favor de", False),
        ("BANCO REGIONAL S.A. por la suma consignada.", False),
        ("", False),
        ("Leida y ratificada, firman ante mi. DOY FE.", False),
    ]


def pdf_escritura_nativa(path, c):
    cv = rl_canvas.Canvas(str(path), pagesize=A4)
    y = H - 3 * cm
    for txt, bold in _render_escritura_texto(c):
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        cv.drawString(2.5 * cm, y, txt)
        y -= 0.62 * cm
    cv.save()


def pdf_escritura_escaneada(path, c, seed):
    """Rasteriza, rota, ensucia. Fuerza OCR de verdad."""
    rnd = random.Random(seed)
    scale = 2
    iw, ih = int(W * scale / 2), int(H * scale / 2)
    img = Image.new("L", (iw, ih), 250)
    dr = ImageDraw.Draw(img)
    try:
        f_reg = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        f_bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
    except OSError:
        f_reg = f_bold = ImageFont.load_default()

    y = 90
    for txt, bold in _render_escritura_texto(c):
        dr.text((70, y), txt, fill=rnd.randint(25, 65),
                font=f_bold if bold else f_reg)
        y += 26

    # manchas y grano de fotocopia
    for _ in range(int(iw * ih * 0.004)):
        x0, y0 = rnd.randrange(iw), rnd.randrange(ih)
        img.putpixel((x0, y0), rnd.randint(150, 245))
    for _ in range(6):
        x0, y0 = rnd.randrange(iw - 120), rnd.randrange(ih - 120)
        r = rnd.randint(15, 55)
        dr.ellipse([x0, y0, x0 + r, y0 + r], fill=rnd.randint(228, 244))

    # inclinacion tipica de escaneo
    img = img.rotate(rnd.uniform(-2.2, 2.2), resample=Image.BICUBIC,
                     fillcolor=248, expand=False)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=58)
    buf.seek(0)

    cv = rl_canvas.Canvas(str(path), pagesize=A4)
    cv.drawImage(__import__("reportlab.lib.utils", fromlist=["ImageReader"])
                 .ImageReader(buf), 0, 0, width=W, height=H)
    cv.save()


def pdf_recibos(path, c):
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=2 * cm)
    ss = getSampleStyleSheet()
    st = [Paragraph("<b>DETALLE DE PAGOS RECIBIDOS</b>", ss["Title"]),
          Spacer(1, 6),
          Paragraph(f"Cliente: {c['nombre']} {c['apellido']} — Legajo "
                    f"{c['cliente_id']}", ss["Normal"]),
          Spacer(1, 12)]
    data = [["Cuota", "Vencimiento", "Fecha de pago", "Importe", "Estado"]]
    for r in c["recibos"]:
        data.append([str(r["cuota"]), r["venc"], r["pago"],
                     fmt_ars(r["importe"], 0), r["estado"]])
    t = Table(data, colWidths=[1.7 * cm, 3.4 * cm, 3.4 * cm, 4.2 * cm, 3 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, "#888888"),
        ("BACKGROUND", (0, 0), (-1, 0), "#dddddd"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))
    st.append(t)
    doc.build(st)


def pdf_tasacion(path, c):
    cv = rl_canvas.Canvas(str(path), pagesize=A4)
    cv.setFont("Helvetica-Bold", 14)
    cv.drawString(2.5 * cm, H - 3 * cm, "INFORME DE TASACION")
    cv.setFont("Helvetica", 10)
    lines = [
        f"Inmueble: {c['inmueble_dir']}",
        f"Matricula: {c['matricula_escritura']}",
        f"Superficie: {c['superficie']} m2",
        f"Fecha del informe: {c['tasacion_fecha']}",
        "",
        f"VALOR DE MERCADO ESTIMADO: {fmt_ars(c['garantia_valor'], 0)}",
        "",
        "El presente informe tiene una validez de 180 dias corridos",
        "desde la fecha de emision.",
    ]
    y = H - 4.2 * cm
    for l in lines:
        cv.drawString(2.5 * cm, y, l)
        y -= 0.6 * cm
    cv.save()


def txt_correspondencia(path, c):
    if c["aviso_previo"]:
        cuerpo = (
            f"De: {c['nombre'].lower()}.{c['apellido'].lower()}@mail.com\n"
            f"Para: cobranzas@bancoregional.com.ar\n"
            f"Fecha: {c['aviso_fecha']}\n"
            f"Asunto: Legajo {c['cliente_id']} - demora en el pago\n\n"
            f"Estimados,\n\n"
            f"Les escribo para informar que voy a demorarme con la cuota de este "
            f"mes por una demora en cobranzas de mi actividad. Estimo regularizar "
            f"dentro de los proximos 45 dias.\n\n"
            f"Quedo a disposicion para acordar un plan.\n\n"
            f"Saludos,\n{c['nombre']} {c['apellido']}\nDNI {c['dni']}\n"
        )
    else:
        cuerpo = (
            f"De: cobranzas@bancoregional.com.ar\n"
            f"Para: {c['nombre'].lower()}.{c['apellido'].lower()}@mail.com\n"
            f"Fecha: {c['aviso_fecha']}\n"
            f"Asunto: Legajo {c['cliente_id']} - intimacion\n\n"
            f"Sr./Sra. {c['apellido']},\n\n"
            f"Registramos un atraso de {c['dias_atraso']} dias en su obligacion. "
            f"Intimamos a regularizar en 10 dias habiles bajo apercibimiento de "
            f"iniciar las acciones que correspondan.\n\n"
            f"Departamento de Cobranzas\n"
        )
    path.write_text(cuerpo, encoding="utf-8")


# ------------------------------------------------------------------ armado

def construir_caso(i, rnd):
    nombre, apellido = NOMBRES[i % len(NOMBRES)]
    cliente_id = 4400 + i * 7

    capital_original = rnd.choice([1_500_000, 2_400_000, 4_000_000,
                                   6_500_000, 9_000_000, 12_000_000])
    pagado_ratio = rnd.uniform(0.15, 0.55)
    capital_adeudado = round(capital_original * (1 - pagado_ratio), -3)

    cobertura = rnd.choice([0.25, 0.45, 0.62, 0.71, 0.9, 1.15])
    garantia_valor = round(capital_adeudado * cobertura, -3)

    cuotas = rnd.choice([12, 24, 36, 48])
    cant_recibos = cuotas
    puntuales = 0
    recibos = []
    n_emitidos = rnd.randint(max(4, cuotas // 3), cuotas)
    for k in range(1, n_emitidos + 1):
        m = (k - 1) % 12 + 1
        y = 2024 + (k - 1) // 12
        venc = fecha(10, m, y)
        atraso_dias = rnd.choices([0, 0, 0, 0, 2, 5, 18, 40],
                                  weights=[45, 15, 10, 8, 8, 6, 5, 3])[0]
        if atraso_dias <= 5:
            puntuales += 1
            estado = "PAGADO"
        elif atraso_dias <= 30:
            estado = "PAGADO C/MORA"
        else:
            estado = "PAGADO C/MORA"
        dia_pago = min(28, 10 + atraso_dias)
        recibos.append({
            "cuota": k, "venc": venc,
            "pago": fecha(dia_pago, m, y),
            "importe": round(capital_original / cuotas, 2),
            "estado": estado,
        })
    puntualidad = puntuales / max(1, n_emitidos)

    aviso_previo = rnd.random() < 0.45
    dias_atraso = rnd.randint(31, 95)

    ciudad = rnd.choice(CIUDADES)
    matricula = f"{rnd.randint(10,99)}-{rnd.randint(10000,99999)}"
    dni = rnd.randint(20_000_000, 44_999_999)
    dom = f"{rnd.choice(CALLES)} {rnd.randint(100,1900)}, {ciudad}"

    c = {
        "cliente_id": cliente_id,
        "nombre": nombre, "apellido": apellido, "dni": dni,
        "sucursal": ciudad,
        "domicilio_contrato": dom,
        "domicilio_escritura": dom,
        "inmueble_dir": f"{rnd.choice(CALLES)} {rnd.randint(100,1900)}, {ciudad}",
        "capital_original": capital_original,
        "capital_adeudado": capital_adeudado,
        "garantia_valor": garantia_valor,
        "cuotas_contrato": cuotas,
        "tna": rnd.choice([48, 62, 75, 88, 96]),
        "matricula": matricula,
        "matricula_escritura": matricula,
        "titular_escritura": f"{nombre} {apellido}",
        "dni_escritura": dni,
        "escritura_nro": rnd.randint(100, 999),
        "registro": rnd.randint(1, 40),
        "superficie": rnd.randint(180, 900),
        "escritura_fecha": fecha(rnd.randint(1, 28), rnd.randint(1, 12), 2024),
        "tasacion_fecha": fecha(rnd.randint(1, 28), rnd.randint(1, 12), 2024),
        "contrato_dia": rnd.randint(1, 28),
        "contrato_mes_txt": rnd.choice(
            ["enero", "marzo", "mayo", "julio", "septiembre", "noviembre"]),
        "contrato_anio": 2024,
        "primer_venc": fecha(10, rnd.randint(1, 12), 2024),
        "fecha_corte": fecha(31, 7, 2026),
        "aviso_fecha": fecha(rnd.randint(1, 28), rnd.randint(4, 7), 2026),
        "estilo_monto": rnd.randint(0, 2),
        "recibos": recibos,
        "puntualidad": round(puntualidad, 3),
        "aviso_previo": aviso_previo,
        "dias_atraso": dias_atraso,
        "escaneada": rnd.random() < 0.5,
        "con_tasacion": rnd.random() < 0.6,
    }

    # ---- contradicciones inyectadas (esto es lo que hay que detectar)
    contradicciones = []
    posibles = ["titular_garantia", "cuotas_no_coinciden",
                "tasacion_vencida", "domicilio_distinto", "matricula_distinta"]
    n_contra = rnd.choices([0, 1, 2], weights=[45, 40, 15])[0]
    for tipo in rnd.sample(posibles, n_contra):
        if tipo == "titular_garantia":
            otro = rnd.choice([n for n in NOMBRES if n[1] != apellido])
            c["titular_escritura"] = f"{otro[0]} {apellido}"
            c["dni_escritura"] = rnd.randint(20_000_000, 44_999_999)
            contradicciones.append({
                "tipo": "titular_garantia",
                "detalle": "El titular de la escritura no coincide con el "
                           "titular del prestamo; la garantia puede no ser ejecutable.",
                "docs": ["escritura.pdf", "contrato.pdf"]})
        elif tipo == "cuotas_no_coinciden":
            c["cuotas_contrato"] = cuotas - rnd.randint(2, 6)
            contradicciones.append({
                "tipo": "cuotas_no_coinciden",
                "detalle": f"El contrato estipula {c['cuotas_contrato']} cuotas "
                           f"pero existen {n_emitidos} recibos emitidos.",
                "docs": ["contrato.pdf", "recibos.pdf"]})
        elif tipo == "tasacion_vencida":
            c["tasacion_fecha"] = fecha(rnd.randint(1, 28), rnd.randint(1, 12),
                                        rnd.choice([2018, 2019, 2020]))
            contradicciones.append({
                "tipo": "tasacion_vencida",
                "detalle": "La tasacion de la garantia tiene mas de 5 anios; "
                           "el valor consignado puede estar desactualizado.",
                "docs": ["escritura.pdf"]})
        elif tipo == "domicilio_distinto":
            c["domicilio_escritura"] = (
                f"{rnd.choice(CALLES)} {rnd.randint(100,1900)}, "
                f"{rnd.choice([x for x in CIUDADES if x != ciudad])}")
            contradicciones.append({
                "tipo": "domicilio_distinto",
                "detalle": "El domicilio declarado en el contrato difiere del "
                           "de la escritura.",
                "docs": ["contrato.pdf", "escritura.pdf"]})
        elif tipo == "matricula_distinta":
            c["matricula_escritura"] = f"{rnd.randint(10,99)}-{rnd.randint(10000,99999)}"
            contradicciones.append({
                "tipo": "matricula_distinta",
                "detalle": "La matricula del inmueble en el contrato no coincide "
                           "con la de la escritura.",
                "docs": ["contrato.pdf", "escritura.pdf"]})
    c["contradicciones"] = contradicciones

    # ---- ruteo esperado (reglas deterministas, el modelo NO decide esto)
    descubierto = max(0, capital_adeudado - garantia_valor)
    cobertura_real = garantia_valor / capital_adeudado if capital_adeudado else 0
    if any(x["tipo"] in ("titular_garantia", "matricula_distinta")
           for x in contradicciones):
        ruteo = "LEGALES"
        motivo = "garantia con defecto formal: no ejecutable con seguridad"
    elif descubierto > 1_000_000 or puntualidad < 0.5:
        ruteo = "LEGALES"
        motivo = "descubierto alto o historial de pago deficiente"
    elif cobertura_real >= 0.6 and aviso_previo:
        ruteo = "REFINANCIACION"
        motivo = "garantia suficiente y notificacion previa del deudor"
    else:
        ruteo = "COBRANZAS"
        motivo = "caso estandar de gestion de mora"

    c["descubierto"] = descubierto
    c["cobertura"] = round(cobertura_real, 3)
    c["ruteo_esperado"] = ruteo
    c["motivo_ruteo"] = motivo
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="./dataset")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    gt = []
    for i in range(a.n):
        c = construir_caso(i, rnd)
        d = out / f"cliente_{c['cliente_id']}"
        d.mkdir(exist_ok=True)

        pdf_contrato(d / "contrato.pdf", c)
        if c["escaneada"]:
            pdf_escritura_escaneada(d / "escritura.pdf", c, a.seed * 1000 + i)
        else:
            pdf_escritura_nativa(d / "escritura.pdf", c)
        pdf_recibos(d / "recibos.pdf", c)
        if c["con_tasacion"]:
            pdf_tasacion(d / "tasacion.pdf", c)
        txt_correspondencia(d / "correspondencia.txt", c)

        (d / "trigger.json").write_text(json.dumps({
            "cliente_id": c["cliente_id"],
            "dias_atraso": c["dias_atraso"],
            "fecha_corte": c["fecha_corte"],
        }, indent=2), encoding="utf-8")

        gt.append({
            "cliente_id": c["cliente_id"],
            "nombre": f"{c['nombre']} {c['apellido']}",
            "carpeta": d.name,
            "escritura_escaneada": c["escaneada"],
            "campos": {
                "capital_original": c["capital_original"],
                "capital_adeudado": c["capital_adeudado"],
                "garantia_valor": c["garantia_valor"],
                "cuotas_contrato": c["cuotas_contrato"],
                "matricula_contrato": c["matricula"],
                "matricula_escritura": c["matricula_escritura"],
                "titular_escritura": c["titular_escritura"],
                "tasacion_fecha": c["tasacion_fecha"],
                "pagos_emitidos": len(c["recibos"]),
                "puntualidad": c["puntualidad"],
                "aviso_previo": c["aviso_previo"],
                "dias_atraso": c["dias_atraso"],
            },
            "derivados": {
                "descubierto": c["descubierto"],
                "cobertura": c["cobertura"],
            },
            "contradicciones": c["contradicciones"],
            "ruteo_esperado": c["ruteo_esperado"],
            "motivo_ruteo": c["motivo_ruteo"],
        })

    (out / "ground_truth.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")

    n_scan = sum(1 for g in gt if g["escritura_escaneada"])
    n_contra = sum(1 for g in gt if g["contradicciones"])
    print(f"{a.n} carpetas en {out}/")
    print(f"  escrituras escaneadas (exigen OCR): {n_scan}")
    print(f"  casos con contradiccion:            {n_contra}")
    for r in ("LEGALES", "REFINANCIACION", "COBRANZAS"):
        print(f"  ruteo {r:15s}: {sum(1 for g in gt if g['ruteo_esperado']==r)}")


if __name__ == "__main__":
    main()
