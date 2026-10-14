# Piloto NC/ND — guardar los reclamos en SharePoint

**Cómo funciona:** el distribuidor registra su reclamo en el portal (Streamlit) → la app
envía un correo a tu buzón corporativo con los datos (`reclamo.json`) y el sustento →
un flujo de **Power Automate** creado con tu cuenta lo guarda en una **Lista de SharePoint**
y el sustento en una **carpeta de SharePoint**. No requiere que Sistemas registre nada.

El cliente solo recibe su número de seguimiento (`R-AAAAMMDD-HHMMSS-XXXX`) si el correo salió
bien; si falla, sus datos se quedan en pantalla para reintentar.

---

## Paso 1 — Gmail que envía los reclamos (10 min)

1. Crea un Gmail nuevo solo para esto (ej. `reclamos.ncnd.piloto@gmail.com`).
2. Activa la **verificación en 2 pasos**: Cuenta de Google → Seguridad.
3. En la misma sección, entra a **Contraseñas de aplicaciones**, crea una llamada `NCND` y copia
   el código de 16 letras. Ese código es `SF_SMTP_PASS`, no la contraseña normal del Gmail.

## Paso 2 — Secrets en Streamlit Cloud (5 min)

En share.streamlit.io → tu app → **Settings → Secrets**, pega y completa esto:

```toml
SF_SMTP_HOST = "smtp.gmail.com"
SF_SMTP_PORT = "587"
SF_SMTP_USER = "reclamos.ncnd.piloto@gmail.com"
SF_SMTP_PASS = "abcd efgh ijkl mnop"
SF_BUZON_RECLAMOS = "tu.correo@sanfernando.com.pe"
SF_TOKEN_FLUJO = "elige-una-frase-larga-secreta"

[PILOTO_CLIENTES.CODIGO_SAP_DISTRIBUIDOR_1]
clave = "clave-distribuidor-1"
razon_social = "RAZON SOCIAL DEL DISTRIBUIDOR 1"
ruc = "20XXXXXXXXX"   # opcional: permite entrar también con el RUC

[PILOTO_CLIENTES.CODIGO_SAP_DISTRIBUIDOR_2]
clave = "clave-distribuidor-2"
razon_social = "RAZON SOCIAL DEL DISTRIBUIDOR 2"
```

**Cómo ingresa el cliente:** escribe su **código de cliente (o RUC) + su clave**. El portal
**nunca muestra una lista de empresas**, así nadie ve la relación de clientes de San Fernando.
El error es siempre el mismo ("código/RUC o clave no son correctos"), para no revelar qué códigos
existen, y tras 5 intentos fallidos ese acceso se bloquea 15 minutos.

**El maestro de clientes (`clientes_maestro.csv`) NO va en el repositorio**: es confidencial.
Por eso la razón social de cada distribuidor del piloto se escribe en los Secrets. Entrega a cada
distribuidor **su código y su clave** por un canal privado (WhatsApp o llamada), nunca en un correo masivo.

## Paso 3 — Lista y carpeta (10 min)

Si tu cuenta no puede crear sitios de SharePoint (pasa en muchas empresas), usa **Microsoft Lists**:
9 puntitos → **Lists** → **+ Nueva lista → Lista en blanco** → nombre `Reclamos NCND` →
Guardar en **Mis listas**. Queda en tu OneDrive corporativo y Power Automate la usa igual.

1. Crea estas columnas (la columna **Título** guarda el código del reclamo). En algunas versiones
   el tipo "Elección" se llama **"Opción"**:

| Columna | Tipo |
|---|---|
| Title (renómbrala a **Código**) | Una línea de texto |
| FechaRegistro | Fecha y hora |
| Cliente | Una línea de texto |
| CodigoSAP | Una línea de texto |
| RUC | Una línea de texto |
| Motivo | Una línea de texto |
| Incidencia | Una línea de texto |
| MontoReclamado | Moneda (S/) |
| Detalle | Varias líneas de texto |
| CorreoCliente | Una línea de texto |
| Sustento | Una línea de texto |
| Estado | Elección: Registrado (predeterminado), En revisión SV, Monto fijado, Validado Producción, Pendiente aprobación, Aprobado, NC/ND emitida, Rechazado |
| MontoFinal | Moneda (S/) |
| Observaciones | Varias líneas de texto |

2. Crea la carpeta `Sustentos NCND` en tu **OneDrive** (o en "Documentos" si usas un sitio).

Durante el piloto, el SV y los aprobadores avanzan cada reclamo cambiando **Estado** y
**MontoFinal** directamente en la Lista.

## Paso 4 — Flujo en Power Automate (20–30 min)

En make.powerautomate.com, con tu cuenta corporativa: **Crear → Flujo de nube automatizado**.

> **Importante:** renombra cada paso **exactamente** como se indica (clic en los `...` del paso →
> *Cambiar nombre*) **antes** de escribir expresiones que lo mencionen. Las expresiones usan el
> nombre con guiones bajos: el paso `Buscar JSON` se escribe `Buscar_JSON`. Para escribir una
> expresión: clic en el campo → ícono **fx** (o *Expresión*) → pega el texto → **Agregar**.

1. **Desencadenador:** *Office 365 Outlook → Cuando llega un nuevo correo electrónico (V3)*
   - Carpeta: `Bandeja de entrada`
   - De: el Gmail del Paso 1
   - Filtro de asunto: `[NCND-PILOTO]`
   - Incluir datos adjuntos: **Sí**. Solo con datos adjuntos: **Sí**.

2. **Filtrar matriz** (renómbrala a `Buscar JSON`)
   - De: `Datos adjuntos` (del desencadenador)
   - Condición: `item()?['name']` **es igual a** `reclamo.json`

3. **Redactar** (renómbrala a `Datos`). Expresión:
   ```
   json(base64ToString(first(body('Buscar_JSON'))?['contentBytes']))
   ```

4. **Condición:** `outputs('Datos')?['token']` **es igual a** tu `SF_TOKEN_FLUJO`.
   Todo lo que sigue va en la rama **Sí**. Así, un correo falso con el mismo asunto se ignora.

5. **Filtrar matriz** (renómbrala a `Buscar sustento`)
   - De: `Datos adjuntos`
   - Condición: `item()?['name']` **no es igual a** `reclamo.json`

6. **Aplicar a cada uno** (renómbralo a `Cada sustento`) sobre la expresión `body('Buscar_sustento')`
   → dentro, *OneDrive para la Empresa → Crear archivo* (o *SharePoint → Crear archivo* si usas un sitio):
   - Ruta de la carpeta: usa el **ícono de carpeta** y navega hasta `Sustentos NCND`
     (no la escribas a mano: el nombre interno puede ser distinto)
   - Nombre de archivo: `items('Cada_sustento')?['name']`
   - Contenido: `base64ToBinary(items('Cada_sustento')?['contentBytes'])`

   Si el reclamo no trae sustento, este paso simplemente no hace nada.

7. *SharePoint → Crear elemento* (fuera del "Cada sustento", debajo de él), en la lista `Reclamos NCND`.
   - **Dirección del sitio**, si la lista está en "Mis listas": no aparece en el desplegable. Elige
     **Escribir un valor personalizado** y pega la dirección de tu OneDrive, que es la parte de la URL
     de la lista **hasta** `/personal/tu_usuario` (ej. `https://empresa-my.sharepoint.com/personal/usuario_empresa_com`).
   - **Nombre de la lista**: `Reclamos NCND`.

| Columna | Expresión |
|---|---|
| Código | `outputs('Datos')?['codigo']` |
| FechaRegistro | `outputs('Datos')?['fecha_registro']` |
| Cliente | `outputs('Datos')?['cliente']` |
| CodigoSAP | `outputs('Datos')?['codigo_sap']` |
| RUC | `outputs('Datos')?['ruc']` |
| Motivo | `outputs('Datos')?['motivo']` |
| Incidencia | `outputs('Datos')?['incidencia']` |
| MontoReclamado | `outputs('Datos')?['monto_reclamado']` |
| Detalle | `outputs('Datos')?['detalle']` |
| CorreoCliente | `outputs('Datos')?['correo_cliente']` |
| Sustento | `outputs('Datos')?['sustento_archivo']` |
| Estado | elige `Registrado` en el desplegable |

8. *Office 365 Outlook → Mover correo electrónico (V2)* a una carpeta `NCND procesados`
   (créala antes en Outlook). Así ves de un vistazo qué ya pasó a SharePoint.

9. **Guardar** y probar: registra un reclamo de prueba desde el portal. En 1 o 2 minutos debe
   aparecer en la Lista. Si no, revisa en Power Automate → *Historial de ejecuciones* qué paso falló.

## Antes de dárselo a los distribuidores

- [ ] El correo del Gmail llega a tu bandeja corporativa y no a Correo no deseado o cuarentena.
      Si cae en cuarentena, pide a Sistemas que permitan ese remitente: es un pedido simple.
- [ ] Haz una prueba completa con sustento (foto y PDF) y revisa que el archivo esté en la carpeta.
- [ ] Confirma que `clientes_maestro.csv` **no** está en el repositorio (ya está en `.gitignore`).
      Si más adelante pones el repo como privado, primero autoriza a Streamlit el acceso a repos
      privados (share.streamlit.io → Settings → Linked accounts → GitHub) o la app dejará de cargar.
- [ ] Cambia las claves por defecto del portal interno (o no lo publiques durante el piloto:
      el flujo interno se maneja en la Lista).

## Qué NO cambió

`portal_interno.py`, `aprobadores.py` y `rpa_carga.py` siguen como estaban, para uso local.
En el piloto, la Lista de SharePoint es el registro oficial. La base `ncnd.db` de Streamlit Cloud
es solo una copia de apoyo y puede borrarse en cualquier reinicio.
