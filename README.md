# Automatización NC/ND — San Fernando

Todo en Python puro, pensado para correr desde tus notebooks de Jupyter. Cuatro módulos:

- `db.py` — base de datos SQLite (`ncnd.db`, se crea sola) con el estado de cada ticket.
- `aprobadores.py` — matriz de aprobadores según rango de monto (la de tu imagen 3).
- `notificador.py` — envía los correos de cada etapa por SMTP.
- `rpa_carga.py` — bot Playwright que llena "Crear Nueva Solicitud" y pausa en el captcha.

## Flujo de uso en Jupyter

```python
from db import init_db, crear_ticket, fijar_monto_sv, validar_produccion, marcar_aprobado, get_ticket
from notificador import notificar_sv, notificar_produccion, notificar_siguiente_aprobador
from aprobadores import obtener_flujo_aprobadores

init_db()

# 1. Se registra el reclamo (esto reemplaza el correo del cliente al SV)
tid = crear_ticket(
    cliente="DISTRIBUIDORA ANTON EIRL",
    codigo_sap="1100788406",
    motivo="305 - Descuento especial",
    incidencia="85 - DE MMPP AAVV - Calidad de Pro",
    detalle="Reconocimiento por calidad dia 1ero de setiembre",
    sustento_path="/ruta/evidencia_cliente.pdf",
    monto_reclamado=150.00,
)
notificar_sv(get_ticket(tid), "sv.correo@sanfernando.com.pe")

# 2. El SV fija el monto (esto puede venir de leer su respuesta de correo, o de un formulario)
fijar_monto_sv(tid, 102.71)
notificar_produccion(get_ticket(tid), "produccion.correo@sanfernando.com.pe")

# 3. Producción valida el porcentaje
monto_final = validar_produccion(tid, porcentaje_reconocido=100)

# 4. Se dispara el flujo de aprobadores según el monto
print(obtener_flujo_aprobadores(monto_final))
notificar_siguiente_aprobador(get_ticket(tid), ya_aprobaron=[])
# ... cuando cada aprobador confirma, se llama registrar_aprobacion() y
#     notificar_siguiente_aprobador() de nuevo con la lista actualizada.

marcar_aprobado(tid)

# 5. RPA sube la solicitud (requiere que ajustes los selectores y URLs reales)
from rpa_carga import cargar_solicitud
cargar_solicitud(get_ticket(tid))
```

## Lo que falta ajustar antes de usarlo en serio

1. **Selectores reales de la plataforma** en `rpa_carga.py` (los marcados con `# AJUSTAR`).
   Ábrela con el inspector del navegador (clic derecho → Inspeccionar) y copia los
   `id`/`name` reales de cada campo.
2. **URLs reales** de login y de "Crear Nueva Solicitud".
3. **Correos reales** de los aprobadores en `aprobadores.py` (`CORREOS_ROLES`).
4. **Credenciales** como variables de entorno, nunca en el código:
   ```bash
   export SF_PLATAFORMA_USER="tu_usuario"
   export SF_PLATAFORMA_PASS="tu_contraseña"
   export SF_SMTP_USER="tu.correo@sanfernando.com.pe"
   export SF_SMTP_PASS="tu_password_o_app_password"
   ```
5. **El captcha se resuelve a mano**, a propósito — el bot hace todo lo demás y
   se detiene justo ahí. No intenta leerlo ni resolverlo automáticamente.
6. Instalar Playwright una sola vez:
   ```bash
   pip install playwright
   playwright install chromium
   ```

## Ideas para siguientes iteraciones

- Reemplazar la captura manual del monto del SV/Producción por un mini-formulario
  (Streamlit, `pip install streamlit`, corre local en minutos) en vez de leer correos.
- Programar `notificador.py` con un cron/Task Scheduler para que revise
  `db.tickets_vencidos()` cada mañana y avise si algo se está por vencer (plazo de 5 días hábiles).
- Si consigues que sistemas te den un usuario "de servicio" sin captcha (algunos
  ERPs lo permiten para integraciones), ahí sí se puede automatizar el envío al 100%.
