"""
portal_cliente.py
La ÚNICA pantalla que debería ver un cliente externo. No muestra tickets ajenos,
montos internos, ni el estado del flujo de aprobación.

Antes de guardar el reclamo, muestra un resumen para que el cliente confirme que
todo está correcto (evita errores de digitación, sobre todo en el monto).

A propósito NO se muestra el plazo de atención (5 días hábiles) al cliente: es un
SLA interno para dar seguimiento, no una promesa de resultado automático.

MODO PILOTO (Secrets PILOTO_CLIENTES configurado): solo entran los distribuidores
del piloto, cada uno con su clave. Cada reclamo se envía por correo al buzón que vigila
Power Automate, que lo guarda en SharePoint. El reclamo solo se confirma al cliente si
ese envío salió bien — así nunca le damos un número a algo que no quedó registrado.

Corre con:
    streamlit run portal_cliente.py
"""

import streamlit as st
import csv
import base64
import re
import hmac
import time
from pathlib import Path
from db import init_db, crear_ticket, get_ticket, tickets_recientes_similares
from consulta_ruc import consultar_razon_social
from notificador import enviar_comprobante_cliente
from generador_pdf import generar_comprobante_pdf
from config_piloto import clientes_piloto, identificar_cliente
from envio_reclamo import (generar_codigo, enviar_reclamo, envio_configurado,
                           nombre_archivo_seguro, ahora_lima)

SUSTENTOS_DIR = Path(__file__).parent / "sustentos"
SUSTENTOS_DIR.mkdir(exist_ok=True)
MAESTRO_PATH = Path(__file__).parent / "clientes_maestro.csv"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_san_fernando.png"

AZUL_SF = "#004B9C"
AZUL_SF_OSCURO = "#002F63"
AZUL_SF_CLARO = "#3D7CC9"
MAX_SUSTENTO_MB = 15  # el correo de envío acepta hasta ~25 MB; dejamos margen

PILOTO = clientes_piloto()  # {codigo_sap: {clave, ruc, razon_social}}; vacío = portal abierto (pruebas)

# Protección contra quien intente adivinar claves: tras 5 intentos fallidos con el mismo
# código/RUC, ese acceso se bloquea 15 minutos (para todos los navegadores a la vez).
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15

init_db()


@st.cache_data
def cargar_maestro_clientes():
    if not MAESTRO_PATH.exists():
        return []
    with open(MAESTRO_PATH, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    # El export de SAP trae espacios "duros" (\xa0) y espacios dobles: se normalizan
    for c in filas:
        for k in ("codigo_sap", "razon_social"):
            c[k] = " ".join((c.get(k) or "").replace("\xa0", " ").split())
    return filas


@st.cache_data
def logo_base64():
    if not LOGO_PATH.exists():
        return None
    return base64.b64encode(LOGO_PATH.read_bytes()).decode()


@st.cache_data(ttl=3600)
def buscar_razon_social_cacheada(ruc):
    return consultar_razon_social(ruc)


@st.cache_resource
def _registro_intentos():
    """Compartido por todas las sesiones de la app: {identificador: [tiempos de fallos]}."""
    return {}


def _fallos_recientes(ident):
    limite = time.time() - MINUTOS_BLOQUEO * 60
    registro = _registro_intentos()
    registro[ident] = [t for t in registro.get(ident, []) if t > limite]
    return registro[ident]


def nombre_cliente(codigo):
    """Razón social de un código: primero la de los Secrets, si no la del maestro."""
    datos = PILOTO.get(codigo, {})
    if datos.get("razon_social"):
        return datos["razon_social"]
    for c in cargar_maestro_clientes():
        if c["codigo_sap"] == codigo:
            return c["razon_social"]
    return f"Cliente {codigo}"


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

# ---------------------------------------------------------------------------
# Acceso del piloto: cada distribuidor se identifica con su código (o RUC) y su clave.
# A propósito NO se muestra ninguna lista de empresas: nadie que entre puede ver
# la relación de clientes de San Fernando.
if PILOTO:
    if "cliente_piloto" not in st.session_state:
        st.markdown("#### Ingreso para clientes")
        with st.form("login_piloto"):
            identificador = st.text_input(
                "Código de cliente o RUC",
                help="Tu código de cliente de San Fernando o el RUC de tu empresa.",
            )
            clave = st.text_input("Clave de acceso", type="password",
                                  help="Te la entregó tu ejecutivo de San Fernando.")
            ingresar = st.form_submit_button("Ingresar")
        st.caption("¿No tienes tu código o tu clave? Solicítalos a tu ejecutivo de San Fernando.")

        if ingresar:
            ident = "".join(identificador.split())
            if not ident or not clave.strip():
                st.error("Escribe tu código de cliente (o RUC) y tu clave.")
            elif len(_fallos_recientes(ident)) >= MAX_INTENTOS:
                st.error(f"Demasiados intentos fallidos. Por seguridad, espera {MINUTOS_BLOQUEO} minutos "
                         "o comunícate con tu ejecutivo de San Fernando.")
            else:
                codigo = identificar_cliente(ident, PILOTO)
                clave_esperada = PILOTO[codigo]["clave"] if codigo else ""
                # Se compara siempre (aunque el código no exista) para no dar pistas por el tiempo de respuesta
                clave_ok = hmac.compare_digest(clave.strip().encode(), clave_esperada.encode())
                if codigo and clave_ok:
                    _registro_intentos().pop(ident, None)
                    st.session_state["cliente_piloto"] = {
                        "codigo_sap": codigo, "razon_social": nombre_cliente(codigo),
                        "ruc": PILOTO[codigo]["ruc"],
                    }
                    st.rerun()
                else:
                    _registro_intentos().setdefault(ident, []).append(time.time())
                    # Mensaje genérico a propósito: no revela si el código existe o no
                    st.error("El código/RUC o la clave no son correctos.")
        st.stop()
    else:
        cp = st.session_state["cliente_piloto"]
        col_a, col_b = st.columns([4, 1])
        col_a.caption(f"Conectado como **{cp['razon_social']}**")
        if col_b.button("Salir"):
            st.session_state.clear()
            st.rerun()

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
            st.warning("⚠️ Hace unos minutos registraste un reclamo muy parecido (misma empresa, motivo y monto). Si fue sin querer, no hace falta enviarlo de nuevo.")
        st.caption("⚠️ Revisa sobre todo el monto y el nombre de la empresa — una vez enviado no se puede editar desde aquí.")
        st.markdown('</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Corregir (empezar de nuevo)"):
                del st.session_state["borrador"]
                st.rerun()
        with col2:
            if st.button("✅ Confirmar y enviar definitivamente"):
                # El código se genera una sola vez por borrador: si el envío falla y el
                # cliente reintenta, se reusa y SharePoint no recibe dos códigos distintos.
                codigo = b.setdefault("codigo", generar_codigo())
                fecha = ahora_lima().strftime("%d/%m/%Y %H:%M")
                datos = {
                    "codigo": codigo,
                    "fecha_registro": ahora_lima().isoformat(timespec="seconds"),
                    "cliente": b["cliente"], "codigo_sap": b["codigo_sap"] or "",
                    "ruc": b["ruc"] or "", "cliente_nuevo": bool(b["es_cliente_nuevo"]),
                    "motivo": b["motivo"], "incidencia": b["incidencia"] or "",
                    "monto_reclamado": round(float(b["monto"] or 0), 2),
                    "detalle": b["detalle"], "correo_cliente": b["correo"] or "",
                    "estado": "Pendiente de validación de cliente" if b["es_cliente_nuevo"] else "Registrado",
                }

                if envio_configurado():
                    with st.spinner("Registrando tu reclamo..."):
                        ok, error = enviar_reclamo(datos, b["sustento_bytes"], b["sustento_filename"])
                    if not ok:
                        print(f"[ERROR envío reclamo {codigo}] {error}")  # visible en los logs de Streamlit Cloud
                        st.error("No pudimos registrar tu reclamo en este momento. Tus datos siguen aquí: "
                                 "intenta de nuevo en unos minutos con el mismo botón.")
                        st.stop()
                elif PILOTO:
                    # En el piloto, nunca confirmamos algo que no llegó a SharePoint.
                    print("[ERROR] Piloto activo pero faltan los Secrets de envío (SMTP / buzón).")
                    st.error("El registro de reclamos no está disponible en este momento. "
                             "Por favor, comunícate con tu ejecutivo de San Fernando.")
                    st.stop()

                # Copia local (solo de apoyo: Streamlit Cloud la puede borrar al reiniciar)
                sustento_path = None
                if b["sustento_bytes"] is not None:
                    sustento_path = str(SUSTENTOS_DIR / nombre_archivo_seguro(codigo, b["sustento_filename"]))
                    with open(sustento_path, "wb") as f:
                        f.write(b["sustento_bytes"])
                try:
                    crear_ticket(
                        cliente=b["cliente"], codigo_sap=b["codigo_sap"], ruc=b["ruc"],
                        es_cliente_nuevo=b["es_cliente_nuevo"], motivo=b["motivo"],
                        incidencia=(f"{codigo} | {b['incidencia']}" if b["incidencia"] else codigo),
                        detalle=b["detalle"], sustento_path=sustento_path,
                        monto_reclamado=b["monto"] or None,
                    )
                except Exception as e:
                    print(f"[AVISO] No se guardó la copia local de {codigo}: {e}")

                ticket_pdf = {
                    "id": codigo, "fecha_creacion": fecha, "cliente": b["cliente"],
                    "ruc": b["ruc"], "codigo_sap": b["codigo_sap"], "motivo": b["motivo"],
                    "incidencia": b["incidencia"], "monto_reclamado": f"{float(b['monto'] or 0):,.2f}",
                    "detalle_motivo": b["detalle"],
                }
                pdf_bytes = generar_comprobante_pdf(
                    ticket_pdf, logo_path=LOGO_PATH if LOGO_PATH.exists() else None,
                    sustento_path=sustento_path,
                )
                st.session_state["ultimo_comprobante"] = {
                    "tid": codigo, "pdf": pdf_bytes, "es_cliente_nuevo": b["es_cliente_nuevo"],
                    "correo": b["correo"], "correo_enviado": False,
                    "registrado_remoto": envio_configurado(),
                }
                del st.session_state["borrador"]
                st.rerun()

    # --- Resultado final: comprobante listo para descargar --------------------
    elif "ultimo_comprobante" in st.session_state:
        info = st.session_state["ultimo_comprobante"]
        st.success(f"Reclamo recibido. Tu número de seguimiento es **{info['tid']}**.")
        if not info.get("registrado_remoto"):
            st.caption("(Modo prueba: este reclamo solo se guardó localmente, no se envió a SharePoint.)")
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
        cliente = codigo_sap = ruc = None
        es_cliente_nuevo = False

        if PILOTO:
            # En el piloto la empresa ya quedó identificada al ingresar: no se elige ni se ve ninguna lista.
            cp = st.session_state["cliente_piloto"]
            cliente, codigo_sap, ruc = cp["razon_social"], cp["codigo_sap"], (cp.get("ruc") or None)
        else:
            # Modo abierto (solo para pruebas, sin Secrets): el cliente se identifica escribiendo
            # su código o su RUC. Tampoco se muestra ninguna lista de clientes.
            ident = "".join(st.text_input(
                "Código de cliente San Fernando o RUC",
                help="Si eres cliente nuevo y aún no tienes código, escribe tu RUC.",
            ).split())
            maestro = {c["codigo_sap"]: c["razon_social"] for c in cargar_maestro_clientes()}
            if ident in maestro:
                cliente, codigo_sap = maestro[ident], ident
                st.success(f"Empresa: {cliente}")
            elif re.fullmatch(r"(10|15|17|20)\d{9}", ident):
                ruc, es_cliente_nuevo = ident, True
                razon_social_sunat = buscar_razon_social_cacheada(ruc)
                if razon_social_sunat:
                    st.success(f"Encontrado en SUNAT: {razon_social_sunat}")
                cliente = st.text_input(
                    "Razón social de tu empresa",
                    value=razon_social_sunat or "",
                    help="Se completa sola si el RUC está registrado en SUNAT. Puedes corregirla si hace falta.",
                )
            elif ident:
                st.warning("No reconocemos ese código. Revísalo, o escribe el RUC de tu empresa (11 dígitos).")

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
                if sustento is not None and sustento.size > MAX_SUSTENTO_MB * 1024 * 1024:
                    errores.append(f"El sustento pesa más de {MAX_SUSTENTO_MB} MB. Sube una foto o PDF más liviano.")
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
    if PILOTO:
        st.info("Durante el piloto, tu ejecutivo de San Fernando te informará el avance de cada reclamo. "
                "Ten a la mano tu número de seguimiento (empieza con R-) y el comprobante en PDF.")
    else:
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
            if (t is None or not nombre_verificacion.strip()
                  or nombre_verificacion.strip().lower() != (t["cliente"] or "").strip().lower()):
                st.error("No se encontró un reclamo con esos datos. Revisa el número de ticket y el nombre de tu empresa.")
            else:
                st.success(f"Ticket #{t['id']} — {ESTADOS_CLIENTE.get(t['estado'], t['estado'])}")
                st.write(f"**Fecha de registro:** {t['fecha_creacion']}")
                if t["monto_final"] is not None:
                    st.write(f"**Monto reconocido:** S/ {t['monto_final']}")
