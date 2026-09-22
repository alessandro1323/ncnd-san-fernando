"""
aprobadores.py
El flujo de aprobación depende SOLO del monto final del ticket, no del motivo
(confirmado). Esta es la única matriz de aprobadores que existe hoy; si en el
futuro hay una matriz distinta por otra razón, se agrega como una nueva entrada
en MATRIZ_APROBADORES sin tocar el resto del código.
"""

# Cada tupla: (monto_maximo_del_rango o None si es "más de", lista de roles en orden de liberación)
MATRIZ_APROBADORES = {
    "por_monto": [
        (1000, ["Jefatura de la Unidad Organizativa", "Coordinador de Cuentas por Cobrar"]),
        (20000, ["Jefatura de la Unidad Organizativa", "Gerente Comercial Commodity",
                  "Coordinador de Cuentas por Cobrar"]),
        (None, ["Jefatura de la Unidad Organizativa", "Gerente Comercial Commodity",
                 "Gerencia de Administración y Finanzas", "Coordinador de Cuentas por Cobrar"]),
    ],
}

# Mapea cada rol a su correo real. Complétalo con los correos de San Fernando.
CORREOS_ROLES = {
    "Jefatura de la Unidad Organizativa": "jefatura.unidad@sanfernando.com.pe",
    "Coordinador de Cuentas por Cobrar": "cxc.coordinador@sanfernando.com.pe",
    "Gerente Comercial Commodity": "gerente.commodity@sanfernando.com.pe",
    "Gerencia de Administración y Finanzas": "gerencia.finanzas@sanfernando.com.pe",
}


def obtener_flujo_aprobadores(monto_final, matriz="por_monto"):
    """Devuelve la lista ordenada de roles que deben aprobar, según el monto."""
    for tope, roles in MATRIZ_APROBADORES[matriz]:
        if tope is None or monto_final <= tope:
            return roles
    raise ValueError("No se encontró rango para el monto dado")


def siguiente_aprobador(monto_final, ya_aprobaron, matriz="por_monto"):
    """ya_aprobaron: lista de roles que ya dieron OK. Devuelve el siguiente rol o None si ya completó el flujo."""
    flujo = obtener_flujo_aprobadores(monto_final, matriz)
    for rol in flujo:
        if rol not in ya_aprobaron:
            return rol
    return None
