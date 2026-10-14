"""
config_piloto.py
Lee la configuración desde los "Secrets" de Streamlit Cloud (o variables de entorno
cuando corres en tu PC). Nada sensible vive en el código ni en el repositorio.

En Streamlit Cloud: App → Settings → Secrets, y pega algo como esto:

    # --- Buzón que ENVÍA los reclamos (un Gmail creado solo para esto) ---
    SF_SMTP_HOST = "smtp.gmail.com"
    SF_SMTP_PORT = "587"
    SF_SMTP_USER = "reclamos.ncnd.piloto@gmail.com"
    SF_SMTP_PASS = "contraseña de aplicación de 16 letras"

    # --- Buzón corporativo que RECIBE y que vigila Power Automate ---
    SF_BUZON_RECLAMOS = "tu.correo@sanfernando.com.pe"

    # --- Palabra secreta que Power Automate verifica (evita correos falsos) ---
    SF_TOKEN_FLUJO = "una-frase-larga-que-solo-tu-conoces"

    # --- Distribuidores del piloto: código SAP = clave de acceso de cada uno ---
    [PILOTO_CLIENTES]
    "1100679218" = "clave-distribuidor-uno"
    "1101229390" = "clave-distribuidor-dos"

Si PILOTO_CLIENTES no está configurado, el portal funciona abierto como antes
(útil para probar en tu PC).
"""

import os

try:
    import streamlit as st
except ImportError:  # permite usar este módulo fuera de Streamlit (Jupyter, pruebas)
    st = None


def leer(nombre, defecto=None):
    """Busca primero en st.secrets y luego en variables de entorno."""
    if st is not None:
        try:
            if nombre in st.secrets:
                return st.secrets[nombre]
        except Exception:
            pass  # no hay secrets.toml (ej. en tu PC): se usan variables de entorno
    return os.environ.get(nombre, defecto)


def clientes_piloto():
    """Devuelve {codigo_sap: clave} de los distribuidores del piloto, o {} si no hay piloto."""
    valor = leer("PILOTO_CLIENTES")
    if not valor:
        return {}
    try:
        return {str(k).strip(): str(v) for k, v in dict(valor).items()}
    except (TypeError, ValueError):
        return {}
