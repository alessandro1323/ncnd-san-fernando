"""
notificador.py
Envía correos de notificación en cada etapa (registro, SV, Producción, aprobadores).
Usa SMTP normal - funciona con el servidor de correo corporativo de San Fernando
(pídele a sistemas el host/puerto si usan Exchange/Office365, o usa smtp.office365.com
si tienes Microsoft 365).

Configura las credenciales como variables de entorno, NUNCA hardcodeadas en el código:
    export SF_SMTP_HOST="smtp.office365.com"
    export SF_SMTP_PORT="587"
    export SF_SMTP_USER="tu.usuario@sanfernando.com.pe"
    export SF_SMTP_PASS="tu_contraseña_o_app_password"
"""

import os
import smtplib
from email.message import EmailMessage
from aprobadores import CORREOS_ROLES, siguiente_aprobador

SMTP_HOST = os.environ.get("SF_SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SF_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SF_SMTP_USER")
SMTP_PASS = os.environ.get("SF_SMTP_PASS")


def _enviar(destinatario, asunto, cuerpo):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[SIMULADO - falta configurar SMTP] Para: {destinatario} | Asunto: {asunto}\n{cuerpo}\n")
        return
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def notificar_sv(ticket, correo_sv):
    _enviar(
        correo_sv,
        f"[NC/ND] Ticket #{ticket['id']} pendiente de fijar monto",
        f"Cliente: {ticket['cliente']}\n"
        f"Monto reclamado: {ticket['monto_reclamado']}\n"
        f"Plazo límite: {ticket['plazo_limite']}\n"
        f"Sustento: {ticket['sustento_path']}\n\n"
        f"Responde con el monto que corresponde reconocer."
    )


def notificar_produccion(ticket, correo_produccion):
    _enviar(
        correo_produccion,
        f"[NC/ND] Ticket #{ticket['id']} pendiente de validar %",
        f"Cliente: {ticket['cliente']}\n"
        f"Monto fijado por SV: {ticket['monto_fijado_sv']}\n\n"
        f"Confirma el porcentaje a reconocer (0-100)."
    )


def notificar_siguiente_aprobador(ticket, ya_aprobaron):
    rol = siguiente_aprobador(ticket["monto_final"], ya_aprobaron)
    if rol is None:
        return None  # flujo de aprobación completo
    correo = CORREOS_ROLES.get(rol)
    _enviar(
        correo,
        f"[NC/ND] Ticket #{ticket['id']} requiere tu aprobación",
        f"Cliente: {ticket['cliente']}\n"
        f"Monto final: {ticket['monto_final']} {ticket['moneda']}\n"
        f"Motivo: {ticket['motivo']}\n"
        f"Detalle: {ticket['detalle_motivo']}\n\n"
        f"Rol requerido: {rol}"
    )
    return rol


def enviar_comprobante_cliente(correo_destino, ticket_id, pdf_bytes=None, html_comprobante=None):
    """Envía el comprobante al correo del cliente, con el PDF adjunto (preferido) o el
    HTML como respaldo. Devuelve True si se envió de verdad, False si el buzón de envío
    (SF_SMTP_USER/PASS) todavía no está configurado — en ese caso el cliente igual tiene
    el botón de descarga."""
    if not SMTP_USER or not SMTP_PASS:
        return False
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = correo_destino
    msg["Subject"] = f"San Fernando - Comprobante de tu reclamo #{ticket_id}"
    msg.set_content(
        f"Adjuntamos el comprobante de tu reclamo #{ticket_id}.\n\n"
        f"Conserva este número para cualquier consulta sobre su estado."
    )
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                            filename=f"comprobante_reclamo_{ticket_id}.pdf")
    elif html_comprobante:
        msg.add_alternative(html_comprobante, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception:
        return False
