"""
rpa_carga.py
Automatiza el llenado de "Crear Nueva Solicitud" a partir de un ticket ya APROBADO
en la base de datos local. El bot hace login, navega y llena todos los campos;
se detiene justo antes de enviar para que tú resuelvas el captcha a mano
(es la única parte que dejamos manual, a propósito).

Requiere:
    pip install playwright
    playwright install chromium

Configura credenciales como variables de entorno (no las pongas en el código):
    export SF_PLATAFORMA_USER="tu_usuario"
    export SF_PLATAFORMA_PASS="tu_contraseña"

Uso desde Jupyter o terminal:
    from rpa_carga import cargar_solicitud
    from db import get_ticket
    ticket = get_ticket(12)
    cargar_solicitud(ticket)
"""

import os
from playwright.sync_api import sync_playwright
from db import marcar_cargado

URL_LOGIN = "https://gestionnc.san-fernando.com.pe/"
URL_NUEVA_SOLICITUD = "https://REEMPLAZAR-CON-LA-URL-REAL/crear-nueva-solicitud"  # AJUSTAR: falta capturar esta

USER = os.environ.get("SF_PLATAFORMA_USER")
PASS = os.environ.get("SF_PLATAFORMA_PASS")


def cargar_solicitud(ticket, headless=False):
    """
    ticket: fila obtenida de db.get_ticket() (o dict equivalente) con los campos ya
    validados y aprobados: cliente, codigo_sap, razon_social, motivo, incidencia,
    detalle_motivo, monto_final, moneda, sustento_path.

    headless=False es intencional: necesitas ver la pantalla para ingresar el captcha.
    """
    if not USER or not PASS:
        raise RuntimeError("Configura SF_PLATAFORMA_USER y SF_PLATAFORMA_PASS como variables de entorno")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=150)
        page = browser.new_page()

        # --- Login ---
        page.goto(URL_LOGIN)
        page.fill("#usuario", USER)
        page.fill("#password", PASS)

        # --- Pausa para captcha ANTES de darle a Ingresar ---
        # El campo del captcha en esta plataforma es id="CaptchaInputText".
        # No lo llenamos por código: tú lo escribes a mano en la ventana del navegador.
        _pausar_para_captcha(page, "login")

        page.click("#btnIngresarLogin")  # dispara ValidarLogin() por JS, no es un submit normal
        page.wait_for_timeout(1500)      # da tiempo a que la página procese el login

        # --- Ir a Crear Nueva Solicitud ---
        page.goto(URL_NUEVA_SOLICITUD)

        # --- Llenar cabecera del formulario ---
        page.select_option("select[name='tipo']", label="Nota de Crédito")   # AJUSTAR
        page.select_option("select[name='area']", label="CANAL DE VENTAS MERCADOS POPULARE")  # AJUSTAR
        page.select_option("select[name='motivo']", label=ticket["motivo"])           # AJUSTAR
        page.select_option("select[name='incidencia']", label=ticket["incidencia"])   # AJUSTAR

        page.fill("input[name='cliente_codigo']", ticket["codigo_sap"])       # AJUSTAR
        page.fill("textarea[name='detalle_motivo']", ticket["detalle_motivo"])  # AJUSTAR

        # --- Adjuntar sustento ---
        if ticket["sustento_path"]:
            page.set_input_files("input[type='file']", ticket["sustento_path"])  # AJUSTAR selector

        # --- Agregar línea de la nota (monto) ---
        page.click("text=Agregar")  # AJUSTAR
        page.fill("input[name='precio_neto']", str(ticket["monto_final"]))  # AJUSTAR

        print(f"Ticket #{ticket['id']}: formulario llenado. Revisa la pantalla.")

        # --- Pausa para captcha final antes de Grabar ---
        _pausar_para_captcha(page, "envío de la solicitud")

        # Descomenta cuando hayas verificado visualmente que todo está correcto:
        # page.click("text=Grabar")
        # n_solicitud = page.inner_text("#numero-solicitud-generado")  # AJUSTAR
        # marcar_cargado(ticket["id"], n_solicitud)

        input("Presiona Enter aquí en la consola cuando termines de revisar/enviar manualmente...")
        browser.close()


def _pausar_para_captcha(page, etapa):
    """
    No resolvemos el captcha por código a propósito: es la verificación humana
    que la plataforma exige. El bot se detiene, tú lo resuelves en la ventana
    que se abrió, y presionas Enter en la consola para continuar.
    """
    input(f"[Captcha - {etapa}] Ingresa el captcha en la ventana del navegador y presiona Enter aquí para continuar...")
