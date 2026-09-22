"""
portal_cliente.py
La ÚNICA pantalla que debería ver un cliente externo. No muestra tickets ajenos,
montos internos, ni el estado del flujo de aprobación.

Antes de guardar el reclamo, muestra un resumen para que el cliente confirme que
todo está correcto (evita errores de digitación, sobre todo en el monto).

A propósito NO se muestra el plazo de atención (5 días hábiles) al cliente: es un
SLA interno para dar seguimiento, no una promesa de resultado automático.

Corre con:
    streamlit run portal_cliente.py
"""

import streamlit as st
import csv
import base64
import re
from pathlib import Path
from db import init_db, crear_ticket, get_ticket, tickets_recientes_similares
from consulta_ruc import consultar_razon_social
from notificador import enviar_comprobante_cliente
from generador_pdf import generar_comprobante_pdf

SUSTENTOS_DIR = Path(__file__).parent / "sustentos"
SUSTENTOS_DIR.mkdir(exist_ok=True)
MAESTRO_PATH = Path(__file__).parent / "clientes_maestro.csv"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_san_fernando.png"

AZUL_SF = "#004B9C"
AZUL_SF_OSCURO = "#002F63"
AZUL_SF_CLARO = "#3D7CC9"

init_db()


@st.cache_data
def cargar_maestro_clientes():
    if not MAESTRO_PATH.exists():
        return []
    with open(MAESTRO_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@st.cache_data
def logo_base64():
    if not LOGO_PATH.exists():
        return None
    return base64.b64encode(LOGO_PATH.read_bytes()).decode()


@st.cache_data(ttl=3600)
def buscar_razon_social_cacheada(ruc):
    return consultar_razon_social(ruc)


st.set_page_config(page_title="San Fernando - Registro de reclamos", layout="centered",
                    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "📋")

LOGO_B64 = logo_base64()

st.markdown(f"""
<style>
@keyframes entrada {{ from {{ opacity: 0; transform: translateY(-12px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes brillo {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}
.block-container {{ padding-top: 1rem; max-width: 720px; }}
.sf-banner {{
    background: linear-gradient(120deg, {AZUL_SF_OSCURO}, {AZUL_SF}, {AZUL_SF_CLARO}, {AZUL_SF});
    background-size: 300% 300%; animation: brillo 10s ease infinite, entrada 0.6s ease-out;
    border-radius: 14px; padding: 28px 32px; display: flex; align-items: center; gap: 20px;
    margin-bottom: 22px; box-shadow: 0 6px 18px rgba(0,75,156,0.25);
}}
.sf-banner img {{ height: 64px; border-radius: 8px; }}
.sf-banner h1 {{ color: white; font-size: 26px; margin: 0; font-weight: 700; }}
.sf-banner p {{ color: #DCE9FB; margin: 4px 0 0 0; font-size: 14px; }}
div.stButton > button, div.stFormSubmitButton > button {{
    background-color: {AZUL_SF}; color: white; border: none; font-weight: 600; transition: all 0.15s ease;
}}
div.stButton > button:hover, div.stFormSubmitButton > button:hover {{ background-color: {AZUL_SF_OSCURO}; transform: scale(1.02); }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
.stTabs [aria-selected="true"] {{ color: {AZUL_SF} !important; }}
.sf-resumen {{ border: 2px solid {AZUL_SF}; border-radius: 10px; padding: 18px 20px; background: #F5F9FE; }}
.sf-resumen b {{ color: {AZUL_SF}; }}
</style>
""", unsafe_allow_html=True)

logo_img_tag = f'<img src="data:image/png;base64,{LOGO_B64}" />' if LOGO_B64 else ""
st.markdown(f"""
<div class="sf-banner">
    {logo_img_tag}
    <div>
        <h1>Registro de reclamos</h1>
        <p>Cuéntanos qué pasó y adjunta tu sustento. Un supervisor revisará tu caso y te contactaremos con la respuesta.</p>
    </div>
</div>
""", unsafe_allow_html=True)

tab_nuevo, tab_consulta = st.tabs(["📝 Registrar un reclamo", "🔍 Consultar estado de mi reclamo"])

# ---------------------------------------------------------------------------
with tab_nuevo:

    # --- Paso 2: ya revisó el resumen, confirma o corrige --------------------
    if "borrador" in st.session_state and "ultimo_comprobante" not in st.session_state:
        b = st.session_state["borrador"]
        st.markdown('<div class="sf-resumen">', unsafe_allow_html=True)
        st.markdown("### Revisa antes de enviar")
        st.write(f"**Empresa:** {b['cliente']}")
        if b.get("ruc"):
            st.write(f"**RUC:** {b['ruc']}")
        st.write(f"**Motivo:** {b['motivo']}")
        st.write(f"**Incidencia / referencia:** {b['incidencia'] or '-'}")
        st.write(f"**Monto que consideras correcto:** S/ {b['monto']:,.2f}")
        st.write(f"**Detalle:** {b['detalle']}")
        st.write(f"**Sustento adjunto:** {b['sustento_filename'] or '(ninguno)'}")
        if not b["sustento_filename"]:
            st.warning("No adjuntaste ningún sustento. Puedes enviarlo igual, pero podría demorar más la revisión.")
        if b.get("posible_duplicado"):
            st.warning(f"⚠️ Ya registraste algo muy parecido hace poco (ticket #{b['posible_duplicado']}). Si fue sin querer, no hace falta enviarlo de nuevo.")
        st.caption("⚠️ Revisa sobre todo el monto y el nombre de la empresa — una vez enviado no se puede editar desde aquí.")
        st.markdown('</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Corregir (empezar de nuevo)"):
                del st.session_state["borrador"]
                st.rerun()
        with col2:
            if st.button("✅ Confirmar y enviar definitivamente"):
                sustento_path = None
                if b["sustento_bytes"] is not None:
                    sustento_path = str(SUSTENTOS_DIR / b["sustento_filename"])
                    with open(sustento_path, "wb") as f:
                        f.write(b["sustento_bytes"])

                tid = crear_ticket(
                    cliente=b["cliente"], codigo_sap=b["codigo_sap"], ruc=b["ruc"],
                    es_cliente_nuevo=b["es_cliente_nuevo"], motivo=b["motivo"],
                    incidencia=b["incidencia"] or None, detalle=b["detalle"],
                    sustento_path=sustento_path, monto_reclamado=b["monto"] or None,
                )
                ticket_guardado = get_ticket(tid)
                pdf_bytes = generar_comprobante_pdf(
                    ticket_guardado, logo_path=LOGO_PATH if LOGO_PATH.exists() else None,
                    sustento_path=sustento_path,
                )
                st.session_state["ultimo_comprobante"] = {
                    "tid": tid, "pdf": pdf_bytes, "es_cliente_nuevo": b["es_cliente_nuevo"],
                    "correo": b["correo"], "correo_enviado": False,
                }
                del st.session_state["borrador"]
                st.rerun()

    # --- Resultado final: comprobante listo para descargar --------------------
    elif "ultimo_comprobante" in st.session_state:
        info = st.session_state["ultimo_comprobante"]
        st.success(f"Reclamo recibido. Tu número de seguimiento es #{info['tid']}.")
        if info["es_cliente_nuevo"]:
            st.info("Como no encontramos tu empresa en nuestro sistema, primero validaremos tus datos.")

        st.download_button(
            "⬇️ Descargar comprobante en PDF",
            data=info["pdf"], file_name=f"comprobante_reclamo_{info['tid']}.pdf", mime="application/pdf",
        )

        if info["correo"] and not info["correo_enviado"]:
            enviado_ok = enviar_comprobante_cliente(info["correo"], info["tid"], pdf_bytes=info["pdf"])
            st.session_state["ultimo_comprobante"]["correo_enviado"] = True
            if enviado_ok:
                st.success(f"También te lo enviamos a {info['correo']}.")
            else:
                st.warning("No pudimos enviar el correo automático todavía — usa el botón de descarga por ahora.")

        if st.button("Registrar otro reclamo"):
            del st.session_state["ultimo_comprobante"]
            st.rerun()

    # --- Paso 1: formulario normal --------------------------------------------
    else:
        maestro = cargar_maestro_clientes()
        es_cliente_nuevo = st.checkbox("Soy cliente nuevo / no encuentro mi empresa en la lista")
        cliente = codigo_sap = ruc = None

        if not es_cliente_nuevo and maestro:
            opciones = [f"{c['razon_social']} — {c['codigo_sap']}" for c in maestro]
            busqueda = st.selectbox("Busca tu empresa (escribe parte del nombre)", options=[""] + opciones)
            if busqueda:
                cliente, codigo_sap = busqueda.split(" — ")
        else:
            ruc = st.text_input("RUC (11 dígitos)")
            razon_social_sunat = None
            if ruc and re.fullmatch(r"(10|15|17|20)\d{9}", ruc.strip()):
                razon_social_sunat = buscar_razon_social_cacheada(ruc.strip())
                if razon_social_sunat:
                    st.success(f"Encontrado en SUNAT: {razon_social_sunat}")
            cliente = st.text_input(
                "Razón social de tu empresa",
                value=razon_social_sunat or "",
                help="Se completa sola si el RUC es válido y está registrado en SUNAT. Puedes corregirla si hace falta.",
            )

        with st.form("form_reclamo"):
            motivo = st.selectbox("Motivo", [
                "Calidad de Producto",
                "Venta de pollo de bajo promedio",
                "Mortandad",
                "Merma Elevada",
                "Diferencia de Precio",
                "Descuento Especial / Acción comercial",
                "Otro",
            ], help="Categorías según el historial real de reclamos de San Fernando.")
            incidencia = st.text_input("Incidencia / referencia del pedido")
            monto_reportado_cliente = st.number_input(
                "Monto que consideras correcto (S/) — referencial", min_value=0.0, step=0.01,
                help="Revisa bien este número antes de continuar: es de los datos que más se digita mal.",
            )
            detalle = st.text_area("Cuéntanos qué pasó")
            sustento = st.file_uploader("Adjunta tu sustento (foto, PDF, correo)",
                                         type=["pdf", "png", "jpg", "jpeg", "eml", "msg"])
            correo_cliente = st.text_input("Tu correo (opcional, para recibir el comprobante por email)")

            revisar = st.form_submit_button("Revisar antes de enviar")

            if revisar:
                errores = []
                if not cliente or not detalle:
                    errores.append("Indica tu empresa y cuéntanos qué pasó.")
                if ruc and not re.fullmatch(r"(10|15|17|20)\d{9}", ruc.strip()):
                    errores.append("El RUC debe tener 11 dígitos y empezar con 10, 15, 17 o 20.")
                if correo_cliente and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo_cliente.strip()):
                    errores.append("El correo no tiene un formato válido (ejemplo: nombre@empresa.com).")

                if errores:
                    for e in errores:
                        st.error(e)
                else:
                    duplicados = tickets_recientes_similares(cliente, motivo, monto_reportado_cliente or None)
                    st.session_state["borrador"] = {
                        "cliente": cliente, "codigo_sap": codigo_sap, "ruc": ruc,
                        "es_cliente_nuevo": es_cliente_nuevo, "motivo": motivo,
                        "incidencia": incidencia, "monto": monto_reportado_cliente,
                        "detalle": detalle,
                        "sustento_bytes": sustento.getbuffer().tobytes() if sustento else None,
                        "sustento_filename": sustento.name if sustento else None,
                        "correo": correo_cliente,
                        "posible_duplicado": duplicados[0]["id"] if duplicados else None,
                    }
                    st.rerun()

# ---------------------------------------------------------------------------
with tab_consulta:
    st.caption("Ingresa tu número de ticket y el nombre de tu empresa para verificar el estado.")

    ESTADOS_CLIENTE = {
        "PENDIENTE_VALIDACION_CLIENTE": "Validando tus datos como cliente nuevo",
        "REGISTRADO": "Recibido, pendiente de revisión",
        "MONTO_FIJADO": "En revisión (monto ya evaluado)",
        "EN_REVISION_PRODUCCION": "En validación interna",
        "PENDIENTE_APROBACION": "En proceso de aprobación",
        "APROBADO": "Aprobado, en trámite de emisión",
        "CARGADO_EN_PLATAFORMA": "Nota de crédito/débito emitida",
        "RECHAZADO": "No procede",
    }

    num_ticket = st.number_input("Número de ticket", min_value=1, step=1)
    nombre_verificacion = st.text_input("Nombre de tu empresa (tal como lo registraste)")

    if st.button("Consultar"):
        t = get_ticket(int(num_ticket))
        if t is None or nombre_verificacion.strip().lower() not in (t["cliente"] or "").lower():
            st.error("No se encontró un reclamo con esos datos. Revisa el número de ticket y el nombre de tu empresa.")
        else:
            st.success(f"Ticket #{t['id']} — {ESTADOS_CLIENTE.get(t['estado'], t['estado'])}")
            st.write(f"**Fecha de registro:** {t['fecha_creacion']}")
            if t["monto_final"] is not None:
                st.write(f"**Monto reconocido:** S/ {t['monto_final']}")
