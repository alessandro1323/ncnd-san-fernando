"""
db.py
Base de datos central (SQLite) para el flujo de Notas de Crédito / Débito - San Fernando.
Reemplaza el "reclamo por correo" por un ticket único con estado trazable.

Uso típico desde Jupyter:
    from db import *
    init_db()
    ticket_id = crear_ticket(cliente="DISTRIBUIDORA ANTON EIRL", codigo_sap="1100788406",
                              motivo="305 - Descuento especial",
                              incidencia="85 - DE MMPP AAVV - Calidad de Pro",
                              detalle="Reconocimiento por calidad dia 1ero de setiembre",
                              sustento_path="/ruta/al/correo_evidencia.pdf")
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "ncnd.db"

ESTADOS = [
    "REGISTRADO",           # cliente/SV registró el reclamo
    "EN_REVISION_SV",       # SV está evaluando evidencia y fijando el monto
    "MONTO_FIJADO",         # SV ya fijó el monto, pasa a Producción
    "EN_REVISION_PRODUCCION",
    "PENDIENTE_APROBACION", # esperando aprobadores según rango de monto
    "APROBADO",             # todos los aprobadores dieron OK
    "CARGADO_EN_PLATAFORMA",# el RPA ya subió la solicitud
    "RECHAZADO",
]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_creacion TEXT NOT NULL,
            plazo_limite TEXT NOT NULL,
            cliente TEXT NOT NULL,
            codigo_sap TEXT,
            razon_social TEXT,
            ruc TEXT,
            es_cliente_nuevo INTEGER DEFAULT 0,
            motivo TEXT,
            incidencia TEXT,
            detalle_motivo TEXT,
            sustento_path TEXT,
            monto_reclamado REAL,
            monto_fijado_sv REAL,
            porcentaje_reconocido REAL,     -- validado por Producción (0-100)
            monto_final REAL,               -- monto_fijado_sv * porcentaje_reconocido / 100
            moneda TEXT DEFAULT 'PEN',
            estado TEXT NOT NULL DEFAULT 'REGISTRADO',
            aprobador_actual TEXT,
            historial_aprobaciones TEXT DEFAULT '',
            fecha_carga_plataforma TEXT,
            n_solicitud_plataforma TEXT
        )
        """)
        conn.commit()
        # Migración segura para bases de datos creadas antes de agregar ruc/es_cliente_nuevo
        for columna, tipo in [("ruc", "TEXT"), ("es_cliente_nuevo", "INTEGER DEFAULT 0")]:
            try:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {columna} {tipo}")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # la columna ya existe, no hay nada que hacer


def crear_ticket(cliente, codigo_sap=None, razon_social=None, ruc=None, es_cliente_nuevo=False,
                  motivo=None, incidencia=None, detalle=None, sustento_path=None,
                  monto_reclamado=None, plazo_dias_habiles=5):
    now = datetime.now()
    plazo = now + timedelta(days=plazo_dias_habiles)  # simplificado; ajustar con calendario hábil real si se requiere
    estado_inicial = "PENDIENTE_VALIDACION_CLIENTE" if es_cliente_nuevo else "REGISTRADO"
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO tickets (fecha_creacion, plazo_limite, cliente, codigo_sap,
                razon_social, ruc, es_cliente_nuevo, motivo, incidencia, detalle_motivo,
                sustento_path, monto_reclamado, estado)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (now.isoformat(), plazo.isoformat(), cliente, codigo_sap, razon_social, ruc,
              1 if es_cliente_nuevo else 0, motivo, incidencia, detalle, sustento_path,
              monto_reclamado, estado_inicial))
        conn.commit()
        return cur.lastrowid


def validar_cliente_nuevo(ticket_id, codigo_sap_asignado):
    """Lo usa quien administra el maestro de clientes cuando ya le crearon el código SAP
    a un cliente nuevo. El ticket pasa a REGISTRADO y sigue el flujo normal."""
    with _conn() as conn:
        conn.execute("""UPDATE tickets SET codigo_sap=?, es_cliente_nuevo=0, estado='REGISTRADO'
                         WHERE id=?""", (codigo_sap_asignado, ticket_id))
        conn.commit()


def fijar_monto_sv(ticket_id, monto_fijado_sv):
    with _conn() as conn:
        conn.execute("""UPDATE tickets SET monto_fijado_sv=?, estado='MONTO_FIJADO'
                         WHERE id=?""", (monto_fijado_sv, ticket_id))
        conn.commit()


def validar_produccion(ticket_id, porcentaje_reconocido):
    """porcentaje_reconocido: 0-100. Calcula el monto_final automáticamente."""
    with _conn() as conn:
        row = conn.execute("SELECT monto_fijado_sv FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        monto_final = round(row["monto_fijado_sv"] * porcentaje_reconocido / 100, 2)
        conn.execute("""UPDATE tickets SET porcentaje_reconocido=?, monto_final=?,
                         estado='PENDIENTE_APROBACION' WHERE id=?""",
                     (porcentaje_reconocido, monto_final, ticket_id))
        conn.commit()
        return monto_final


def registrar_aprobacion(ticket_id, aprobador, comentario=""):
    with _conn() as conn:
        row = conn.execute("SELECT historial_aprobaciones FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        historial = row["historial_aprobaciones"] or ""
        historial += f"[{datetime.now().isoformat()}] {aprobador}: OK {comentario}\n"
        conn.execute("UPDATE tickets SET historial_aprobaciones=? WHERE id=?", (historial, ticket_id))
        conn.commit()


def marcar_aprobado(ticket_id):
    with _conn() as conn:
        conn.execute("UPDATE tickets SET estado='APROBADO' WHERE id=?", (ticket_id,))
        conn.commit()


def marcar_cargado(ticket_id, n_solicitud_plataforma):
    with _conn() as conn:
        conn.execute("""UPDATE tickets SET estado='CARGADO_EN_PLATAFORMA',
                         fecha_carga_plataforma=?, n_solicitud_plataforma=? WHERE id=?""",
                     (datetime.now().isoformat(), n_solicitud_plataforma, ticket_id))
        conn.commit()


def tickets_por_estado(estado):
    with _conn() as conn:
        return conn.execute("SELECT * FROM tickets WHERE estado=?", (estado,)).fetchall()


def tickets_vencidos():
    """Tickets cuyo plazo_limite ya pasó y no están cerrados."""
    with _conn() as conn:
        return conn.execute("""
            SELECT * FROM tickets
            WHERE plazo_limite < ? AND estado NOT IN ('CARGADO_EN_PLATAFORMA','RECHAZADO')
        """, (datetime.now().isoformat(),)).fetchall()


def get_ticket(ticket_id):
    with _conn() as conn:
        return conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()


if __name__ == "__main__":
    init_db()
    print(f"Base de datos lista en: {DB_PATH}")
