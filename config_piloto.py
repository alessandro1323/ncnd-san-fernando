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

    # Opcional: si quieres que también puedan entrar con su RUC, usa esta forma:
    # [PILOTO_CLIENTES.1100679218]
    # clave = "clave-distribuidor-uno"
    # ruc = "20123456789"

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
    """Devuelve {codigo_sap: {"clave": str, "ruc": str, "razon_social": str}} de los
    distribuidores del piloto, o {} si no hay piloto. Acepta dos formas en los Secrets:
        "1100679218" = "clave"                              (solo código)
        [PILOTO_CLIENTES.1100679218] clave = "..." ruc = "..."  (código o RUC)
    """
    valor = leer("PILOTO_CLIENTES")
    if not valor:
        return {}
    try:
        crudo = dict(valor)
    except (TypeError, ValueError):
        return {}
    clientes = {}
    for codigo, datos in crudo.items():
        codigo = str(codigo).strip()
        if isinstance(datos, str) or not hasattr(datos, "get"):
            datos = {"clave": datos}
        clave = str(datos.get("clave", "") or "").strip()
        if not codigo or not clave:
            continue  # un cliente sin clave nunca puede entrar
        clientes[codigo] = {
            "clave": clave,
            "ruc": str(datos.get("ruc", "") or "").strip(),
            "razon_social": str(datos.get("razon_social", "") or "").strip(),
        }
    return clientes


def identificar_cliente(identificador, clientes):
    """Recibe lo que escribió el cliente (código SAP o RUC) y devuelve el código SAP
    del distribuidor del piloto, o None si no corresponde a ninguno."""
    ident = "".join(str(identificador or "").split())
    if not ident:
        return None
    if ident in clientes:
        return ident
    for codigo, datos in clientes.items():
        if datos["ruc"] and datos["ruc"] == ident:
            return codigo
    return None
