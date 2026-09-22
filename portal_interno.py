"""
portal_interno.py
Uso exclusivo del personal de San Fernando. Cada rol ve solo lo que le corresponde.

Corre con:
    streamlit run portal_interno.py

IMPORTANTE sobre seguridad: la clave por rol de abajo es un candado simple para
separar vistas mientras el proyecto está en piloto — NO es un login corporativo real.
Antes de usar esto con datos de producción sensibles (montos, aprobaciones reales),
conviene reemplazarlo por el login de la red de San Fernando (Sistemas te puede
orientar si usan Active Directory / SSO) o al menos usuarios y contraseñas propios
por persona en vez de una clave compartida por rol.

Configura las claves como variables de entorno antes de correr streamlit:
    $env:SF_CLAVE_SV = "clave_del_sv"
    $env:SF_CLAVE_PRODUCCION = "clave_de_produccion"
    $env:SF_CLAVE_APROBADORES = "clave_de_aprobadores"
    $env:SF_CLAVE_ADMIN = "clave_de_administracion"
Si no las configuras, usa las claves por defecto de abajo (cámbialas antes de compartir esto con alguien más).
"""

import os
import csv
import base64
import streamlit as st
from pathlib import Path
from db import (
    init_db, get_ticket, tickets_por_estado, fijar_monto_sv,
    validar_produccion, registrar_aprobacion, marcar_aprobado, validar_cliente_nuevo,
)
from aprobadores import siguiente_aprobador, obtener_flujo_aprobadores

MAESTRO_PATH = Path(__file__).parent / "clientes_maestro.csv"

CLAVES = {
    "SV": os.environ.get("SF_CLAVE_SV", "sv2026"),
    "Producción": os.environ.get("SF_CLAVE_PRODUCCION", "prod2026"),
    "Aprobadores": os.environ.get("SF_CLAVE_APROBADORES", "aprob2026"),
    "Administración (maestro de clientes)": os.environ.get("SF_CLAVE_ADMIN", "admin2026"),
}

init_db()

AZUL_SF = "#004B9C"
AZUL_SF_OSCURO = "#002F63"

st.set_page_config(page_title="Portal interno - NC/ND San Fernando", layout="wide",
                    page_icon=str(Path(__file__).parent / "assets" / "logo_san_fernando.png"))

st.markdown(f"""
<style>
.block-container {{ padding-top: 1.2rem; }}
.sf-header {{ background: {AZUL_SF}; padding: 18px 24px; border-radius: 10px;
              display:flex; align-items:center; gap:16px; margin-bottom: 18px; }}
.sf-header h1 {{ color: white; font-size: 20px; margin: 0; }}
.sf-header img {{ height: 46px; border-radius: 6px; }}
div.stButton > button {{ background-color: {AZUL_SF}; color: white; font-weight: 600; }}
div.stButton > button:hover {{ background-color: {AZUL_SF_OSCURO}; }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="sf-header">
    <img src="data:image/png;base64,{base64.b64encode((Path(__file__).parent / 'assets' / 'logo_san_fernando.png').read_bytes()).decode()}" />
    <h1>Portal interno — Notas de Crédito / Débito</h1>
</div>
""", unsafe_allow_html=True)

rol = st.sidebar.selectbox("Ingresa como", list(CLAVES.keys()))
clave_ingresada = st.sidebar.text_input("Clave", type="password")

if clave_ingresada != CLAVES[rol]:
    st.info(f"Ingresa la clave de acceso de {rol} en el panel de la izquierda.")
    st.stop()

st.sidebar.success(f"Conectado como: {rol}")

# ---------------------------------------------------------------------------
if rol == "SV":
    st.subheader("Reclamos por revisar")
    st.caption("Revisa la evidencia en SAP y confirma el monto que corresponde reconocer.")
    pendientes = tickets_por_estado("REGISTRADO")
    if not pendientes:
        st.info("No hay reclamos pendientes.")
    for t in pendientes:
        with st.expander(f"Ticket #{t['id']} — {t['cliente']} — reportado: S/ {t['monto_reclamado'] or '?'}"):
            st.write(f"**Motivo:** {t['motivo']} | **Incidencia:** {t['incidencia']}")
            st.write(f"**Detalle:** {t['detalle_motivo']}")
            st.write(f"**Plazo límite:** {t['plazo_limite']}")
            if t["sustento_path"]:
                st.write(f"**Sustento:** {t['sustento_path']}")
            monto_sv = st.number_input("Monto que corresponde reconocer", min_value=0.0,
                                        step=0.01, key=f"monto_{t['id']}")
            if st.button("Confirmar monto", key=f"btn_{t['id']}"):
                fijar_monto_sv(t["id"], monto_sv)
                st.success(f"Monto fijado: S/ {monto_sv}. Pasa a Producción.")
                st.rerun()

# ---------------------------------------------------------------------------
elif rol == "Producción":
    st.subheader("Reclamos por validar (%)")
    pendientes = tickets_por_estado("MONTO_FIJADO")
    if not pendientes:
        st.info("No hay reclamos pendientes.")
    for t in pendientes:
        with st.expander(f"Ticket #{t['id']} — {t['cliente']} — monto SV: S/ {t['monto_fijado_sv']}"):
            st.write(f"**Detalle:** {t['detalle_motivo']}")
            porcentaje = st.slider("% a reconocer", 0, 100, 100, key=f"pct_{t['id']}")
            if st.button("Confirmar validación", key=f"btnp_{t['id']}"):
                monto_final = validar_produccion(t["id"], porcentaje)
                st.success(f"Validado. Monto final: S/ {monto_final}. Pasa a aprobaciones.")
                st.rerun()

# ---------------------------------------------------------------------------
elif rol == "Aprobadores":
    st.subheader("Pendientes de tu aprobación")
    pendientes = tickets_por_estado("PENDIENTE_APROBACION")
    if not pendientes:
        st.info("No hay reclamos pendientes de aprobación.")
    for t in pendientes:
        aprobados_previos = [linea.split(": ")[0].split("] ")[1] for linea in
                              (t["historial_aprobaciones"] or "").splitlines() if linea]
        rol_pendiente = siguiente_aprobador(t["monto_final"], aprobados_previos)
        with st.expander(f"Ticket #{t['id']} — {t['cliente']} — S/ {t['monto_final']} — falta: {rol_pendiente}"):
            st.write(f"**Motivo:** {t['motivo']} | **Detalle:** {t['detalle_motivo']}")
            st.write(f"**Flujo completo para este monto:** {obtener_flujo_aprobadores(t['monto_final'])}")
            aprobador_que_firma = st.selectbox("Firmas como", obtener_flujo_aprobadores(t["monto_final"]),
                                                key=f"firma_{t['id']}")
            if st.button("Aprobar", key=f"btna_{t['id']}"):
                registrar_aprobacion(t["id"], aprobador_que_firma)
                actualizado = get_ticket(t["id"])
                aprobados = [linea.split(": ")[0].split("] ")[1] for linea in
                             (actualizado["historial_aprobaciones"] or "").splitlines() if linea]
                if siguiente_aprobador(actualizado["monto_final"], aprobados) is None:
                    marcar_aprobado(t["id"])
                    st.success("Última aprobación registrada. Ticket queda APROBADO, listo para el RPA.")
                else:
                    st.success("Aprobación registrada, falta el siguiente nivel.")
                st.rerun()

# ---------------------------------------------------------------------------
elif rol == "Administración (maestro de clientes)":
    st.subheader("Clientes nuevos por validar")
    st.caption("Asigna aquí el código SAP una vez que lo hayan creado, para que el ticket siga su flujo.")
    pendientes = tickets_por_estado("PENDIENTE_VALIDACION_CLIENTE")
    if not pendientes:
        st.info("No hay clientes nuevos pendientes de validar.")
    for t in pendientes:
        with st.expander(f"Ticket #{t['id']} — {t['cliente']} — RUC: {t['ruc'] or '(no indicado)'}"):
            codigo_nuevo = st.text_input("Código SAP asignado", key=f"cod_{t['id']}")
            if st.button("Validar cliente y continuar", key=f"btnc_{t['id']}"):
                if not codigo_nuevo:
                    st.error("Ingresa el código SAP antes de continuar.")
                else:
                    validar_cliente_nuevo(t["id"], codigo_nuevo)
                    # Se agrega también al maestro para que la próxima vez el cliente lo encuentre solo
                    with open(MAESTRO_PATH, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow([codigo_nuevo, t["cliente"]])
                    st.cache_data.clear()
                    st.success(f"Cliente validado con código {codigo_nuevo}. Ticket pasa a revisión del SV.")
                    st.rerun()

    st.divider()
    st.subheader("Maestro de clientes actual")
    if MAESTRO_PATH.exists():
        with open(MAESTRO_PATH, encoding="utf-8") as f:
            filas = list(csv.reader(f))
        st.write(f"Total de clientes en el maestro: {len(filas) - 1}")
        st.caption("Reemplaza clientes_maestro.csv por una exportación fresca de SAP cuando la consigas, para mantenerlo al día.")
