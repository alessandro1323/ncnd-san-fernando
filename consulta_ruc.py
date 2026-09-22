"""
consulta_ruc.py
Busca la razón social de una empresa a partir de su RUC, usando la API pública
de apis.net.pe (consume datos de SUNAT). No es un servicio oficial de SUNAT,
pero es el estándar que se usa en Perú para esto sin pelearse con el captcha
del portal de SUNAT.

CONFIGURACIÓN NECESARIA (una sola vez, gratis):
    1. Entra a https://apis.net.pe y crea una cuenta gratuita.
    2. Te da un token (una cadena larga de texto).
    3. Configúralo como variable de entorno antes de correr streamlit:
        $env:SF_APIS_NET_PE_TOKEN = "tu_token_aquí"
    Sin el token, esta función simplemente no hace nada (el cliente escribe
    su razón social a mano, como hasta ahora) — no rompe el resto del formulario.
"""

import os
import requests

TOKEN = os.environ.get("SF_APIS_NET_PE_TOKEN")
URL = "https://api.apis.net.pe/v2/sunat/ruc"


def consultar_razon_social(ruc):
    """Devuelve la razón social si la encuentra, o None si no se pudo
    (sin token configurado, RUC no existe, o falla la conexión).
    Nunca lanza una excepción hacia afuera — si algo falla, el cliente
    simplemente escribe su razón social a mano, como plan B."""
    if not TOKEN or not ruc:
        return None
    try:
        resp = requests.get(
            URL, params={"numero": ruc},
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("razonSocial") or data.get("nombre")
        return None
    except requests.RequestException:
        return None
