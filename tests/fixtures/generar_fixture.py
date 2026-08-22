"""Genera un PDF sintético de prueba (datos inventados, sin relación con
ningún dominio real) para poder correr el flujo completo end-to-end sin
cargar información real. Herramienta de desarrollo, no es parte de la app:
necesita `pip install fpdf2` (no está en requirements.txt a propósito).

Correr: python tests/fixtures/generar_fixture.py
"""
from pathlib import Path

from fpdf import FPDF

SECCIONES = [
    ("Registro de usuarios", """
Para registrarse en BiciPresta hace falta completar el formulario de alta
con nombre, DNI y un medio de contacto. El registro es gratuito y da
acceso a la primera media hora de uso sin cargo en cualquier viaje. Los
usuarios menores de 18 años necesitan autorización de un adulto responsable
firmada en la sede central.
"""),
    ("Mantenimiento de bicicletas", """
Cada bicicleta pasa una revisión de frenos, cadena y presión de neumáticos
cada 15 días. Si una unidad vuelve con daño visible, se retira de
circulación hasta que el sector de mantenimiento la revise. Las bicicletas
eléctricas tienen un chequeo adicional de batería cada semana.
"""),
    ("Turnos del personal", """
El personal de las estaciones trabaja en turnos rotativos de 6 horas,
de lunes a domingo. Hay al menos dos personas por estación en el turno de
la mañana (7 a 13) y una sola persona en el turno de la tarde (13 a 19).
Los feriados se cubren con guardias voluntarias pagas doble.
"""),
    ("Política de devoluciones tardías", """
Si una bicicleta se devuelve más de 2 horas tarde sin aviso previo, se
cobra un recargo por hora excedida. Si además la unidad vuelve dañada, el
recargo se suma al costo de reparación estimado por el sector de
mantenimiento antes de habilitar nuevos préstamos a ese usuario.
"""),
    ("Tarifas y membresías", """
La membresía mensual cuesta un valor fijo e incluye viajes ilimitados de
hasta 45 minutos. Superado ese tiempo se cobra por minuto adicional. Los
estudiantes con credencial vigente tienen 30% de descuento en la
membresía mensual.
"""),
]


def generar(destino: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, "Manual de Operaciones - BiciPresta (datos ficticios de prueba)")
    pdf.ln(4)

    for titulo, cuerpo in SECCIONES:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 8, titulo, new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, cuerpo.strip(), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    pdf.output(str(destino))
    print(f"generado: {destino}")


if __name__ == "__main__":
    generar(Path(__file__).parent / "manual_bicipresta.pdf")
