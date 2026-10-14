"""
envio_reclamo.py
Envía cada reclamo confirmado al buzón corporativo que vigila Power Automate.
Power Automate lo lee y lo guarda en la Lista de SharePoint + carpeta de sustentos.

Por qué así:
- Streamlit Cloud BORRA sus archivos locales (la base SQLite y los sustentos) cada vez
  que la app se reinicia o se actualiza. El correo + SharePoint es el registro oficial.
- No requiere que Sistemas registre ninguna app: el flujo corre con tu cuenta corporativa.

Formato del correo (Power Automate depende de esto, no lo cambies sin ajustar el flujo):
- Asunto:   [NCND-PILOTO] <codigo>
- Adjunto:  reclamo.json   -> todos los datos, en JSON (es lo que lee el flujo)
- Adjunto:  <codigo>_<archivo>  -> el sustento del cliente, si lo subió
- Cuerpo:   los mismos datos en texto legible, por si alguien abre el correo
"""

import json
import re
import secrets
import smtplib
from datetime import datetime
from email.message import EmailMessage
from mimetypes import guess_type
from zoneinfo import ZoneInfo

from config_piloto import leer

PREFIJO_ASUNTO = "[NCND-PILOTO]"
ZONA_LIMA = ZoneInfo("America/Lima")


def ahora_lima():
    return datetime.now(ZONA_LIMA)


def generar_codigo():
    """Código único que no depende de la base local (que Streamlit Cloud puede borrar).
    Ejemplo: R-20261014-153012-7F3A"""
    return ahora_lima().strftime("R-%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2).upper()


def nombre_archivo_seguro(codigo, nombre_original):
    """Antepone el código para que dos clientes con 'foto.jpg' no se pisen,
    y quita caracteres que SharePoint no acepta en nombres de archivo."""
    limpio = re.sub(r'[\\/:*?"<>|#%&{}~]+', "_", nombre_original or "sustento").strip(" .")
    return f"{codigo}_{limpio or 'sustento'}"


def envio_configurado():
    return all(leer(n) for n in ("SF_SMTP_USER", "SF_SMTP_PASS", "SF_BUZON_RECLAMOS"))


def enviar_reclamo(datos, sustento_bytes=None, sustento_nombre=None):
    """datos: dict con los campos del reclamo (debe incluir 'codigo').
    Devuelve (True, None) si el correo salió, o (False, mensaje_de_error).
    Nunca lanza excepciones: el portal decide qué mostrarle al cliente."""
    if not envio_configurado():
        return False, "El envío a SharePoint no está configurado (faltan los Secrets SMTP / buzón)."

    datos = dict(datos)
    datos["token"] = leer("SF_TOKEN_FLUJO", "")
    if sustento_bytes is not None:
        datos["sustento_archivo"] = nombre_archivo_seguro(datos["codigo"], sustento_nombre)
    else:
        datos["sustento_archivo"] = ""

    msg = EmailMessage()
    msg["From"] = leer("SF_SMTP_USER")
    msg["To"] = leer("SF_BUZON_RECLAMOS")
    msg["Subject"] = f"{PREFIJO_ASUNTO} {datos['codigo']}"
    legible = {k: v for k, v in datos.items() if k != "token"}
    msg.set_content(
        "Nuevo reclamo registrado en el portal NC/ND (piloto).\n\n"
        + "\n".join(f"{k}: {v}" for k, v in legible.items())
        + "\n\nEste correo lo procesa Power Automate automáticamente. No lo muevas de la bandeja de entrada."
    )
    msg.add_attachment(json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8"),
                       maintype="application", subtype="json", filename="reclamo.json")
    if sustento_bytes is not None:
        tipo = (guess_type(datos["sustento_archivo"])[0] or "application/octet-stream").split("/", 1)
        msg.add_attachment(sustento_bytes, maintype=tipo[0], subtype=tipo[1],
                           filename=datos["sustento_archivo"])

    try:
        with smtplib.SMTP(leer("SF_SMTP_HOST", "smtp.gmail.com"), int(leer("SF_SMTP_PORT", "587")),
                          timeout=30) as server:
            server.starttls()
            server.login(leer("SF_SMTP_USER"), leer("SF_SMTP_PASS"))
            server.send_message(msg)
        return True, None
    except Exception as e:  # credenciales, red, adjunto muy grande, etc.
        return False, f"{type(e).__name__}: {e}"
