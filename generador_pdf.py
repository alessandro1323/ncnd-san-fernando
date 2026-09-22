"""
generador_pdf.py
Genera el comprobante del reclamo como PDF: a la izquierda los datos del ticket,
a la derecha el detalle redactado por el cliente y, si el sustento es una imagen,
la evidencia se ve directamente ahí. Si el sustento es un PDF/correo, se menciona
el nombre del archivo (no se puede "incrustar" un PDF dentro de otro PDF como imagen
sin convertirlo antes, así que por ahora solo queda referenciado).

No se muestra el plazo de atención aquí a propósito: es un SLA interno para dar
seguimiento, no una promesa de resultado automático al cliente.
"""

from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)
from reportlab.lib.enums import TA_LEFT

AZUL_SF = colors.HexColor("#004B9C")
GRIS_TEXTO = colors.HexColor("#333333")

EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg"}


def generar_comprobante_pdf(ticket, logo_path=None, sustento_path=None):
    """ticket: fila de db.get_ticket() (o dict equivalente).
    Devuelve los bytes del PDF, listos para descargar o adjuntar a un correo."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    estilo_normal = ParagraphStyle("normal_sf", parent=styles["Normal"], fontSize=10,
                                   leading=14, textColor=GRIS_TEXTO, alignment=TA_LEFT)
    estilo_label = ParagraphStyle("label_sf", parent=estilo_normal, textColor=colors.HexColor("#666666"),
                                   fontSize=8.5, spaceAfter=1)
    estilo_valor = ParagraphStyle("valor_sf", parent=estilo_normal, fontSize=10.5,
                                   spaceAfter=8, textColor=colors.HexColor("#0A1F3D"))
    estilo_titulo_col = ParagraphStyle("titulo_col", parent=estilo_normal, fontSize=11,
                                        textColor=AZUL_SF, spaceAfter=8, fontName="Helvetica-Bold")

    story = []

    # --- Encabezado ---
    if logo_path and Path(logo_path).exists():
        logo = RLImage(str(logo_path), width=26 * mm, height=26 * mm)
        header_tbl = Table(
            [[logo, Paragraph(f"<b>San Fernando</b><br/>Comprobante de recepción de reclamo",
                               ParagraphStyle("h1", parent=estilo_normal, fontSize=14, textColor=colors.white))]],
            colWidths=[30 * mm, None],
        )
        header_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AZUL_SF),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(header_tbl)
    else:
        story.append(Paragraph("San Fernando — Comprobante de recepción de reclamo",
                                ParagraphStyle("h1b", parent=estilo_normal, fontSize=14, textColor=AZUL_SF)))
    story.append(Spacer(1, 14))

    # --- Columna izquierda: datos del ticket ---
    def campo(label, valor):
        return [Paragraph(label, estilo_label), Paragraph(str(valor) if valor not in (None, "") else "-", estilo_valor)]

    columna_izquierda = [Paragraph("Datos del ticket", estilo_titulo_col)]
    for label, valor in [
        ("N° de ticket", f"#{ticket['id']}"),
        ("Fecha y hora de registro", ticket["fecha_creacion"]),
        ("Cliente", ticket["cliente"]),
        ("RUC", ticket["ruc"] or "(vía código SAP)"),
        ("Código SAP", ticket["codigo_sap"] or "(pendiente de validar)"),
        ("Motivo", ticket["motivo"]),
        ("Incidencia / referencia", ticket["incidencia"]),
        ("Monto referencial informado", f"S/ {ticket['monto_reclamado'] or '0.00'}"),
    ]:
        columna_izquierda += campo(label, valor)

    # --- Columna derecha: detalle redactado + evidencia ---
    columna_derecha = [Paragraph("Detalle del reclamo", estilo_titulo_col),
                        Paragraph(ticket["detalle_motivo"] or "-", estilo_valor),
                        Spacer(1, 8)]

    if sustento_path and Path(sustento_path).exists():
        ext = Path(sustento_path).suffix.lower()
        if ext in EXTENSIONES_IMAGEN:
            columna_derecha.append(Paragraph("Evidencia adjunta:", estilo_label))
            try:
                img = RLImage(str(sustento_path), width=75 * mm, height=None)
                img._restrictSize(75 * mm, 90 * mm)
                columna_derecha.append(img)
            except Exception:
                columna_derecha.append(Paragraph(f"(no se pudo mostrar la imagen: {Path(sustento_path).name})", estilo_valor))
        else:
            columna_derecha.append(Paragraph("Evidencia adjunta:", estilo_label))
            columna_derecha.append(Paragraph(f"📎 {Path(sustento_path).name} (archivo adjunto por separado)", estilo_valor))
    else:
        columna_derecha.append(Paragraph("(No se adjuntó sustento)", estilo_valor))

    tabla_principal = Table([[columna_izquierda, columna_derecha]], colWidths=[80 * mm, 80 * mm])
    tabla_principal.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 14),
        ("LEFTPADDING", (1, 0), (1, 0), 14),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, colors.HexColor("#DDDDDD")),
    ]))
    story.append(tabla_principal)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Este documento certifica que San Fernando recibió tu reclamo en la fecha indicada. "
        "Conserva el número de ticket para cualquier consulta sobre su estado.",
        ParagraphStyle("footer", parent=estilo_normal, fontSize=8, textColor=colors.HexColor("#888888")),
    ))

    doc.build(story)
    return buffer.getvalue()
