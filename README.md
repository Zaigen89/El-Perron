# Licitaciones 100 Modos

Encuentra todos los días las licitaciones de **Mercado Público** que calzan con 100 Modos
(charlas, talleres y capacitaciones para equipos y organizaciones) y ayuda a preparar la oferta con Claude Code.

```
API Mercado Público ──► filtro local (gratis, 0 tokens) ──► salida/resumen.md
                                                              │  /revisar
                                                              ▼
              bases PDF ──► recorte local (-80/90 % de texto) ──► Claude Code redacta (/oferta)
                                                              │
                                                              ▼
                                         para_subir/*.docx ──► ella revisa y sube a mano
```

Python hace todo lo mecánico, como descargar, filtrar, extraer el texto de los PDF y pasar a Word. Claude
solo lee resúmenes cortos y redacta, con la suscripción de Claude que ya tienes, sin pagar API.
**El programa nunca envía nada a Mercado Público.**

## 1. Pedir el ticket (una vez)

La API es la forma oficial y gratuita en que ChileCompra entrega los datos de licitaciones a programas.
Para usarla se necesita un **ticket**, que es un código personal.

1. Entra a https://api.mercadopublico.cl y busca la opción para solicitar ticket.
2. Acepta los términos de uso e inicia sesión con **ClaveÚnica**.
3. El ticket llega por correo, con un formato como `F8537A18-6766-4DEF-9E59-426B4FEE2844`.

El ticket solo sirve para leer información pública. No da acceso a la cuenta de proveedor de la empresa.

## 2. Instalar en el Mac (una vez)

En la app **Terminal**:

```bash
git clone <URL-del-repo> licitaciones-bot
cd licitaciones-bot
bash scripts/instalar_mac.sh --diario 08:40     # instala y programa la revisión diaria a las 08:40
open -e .env                                    # pega el ticket: MP_TICKET=F8537A18-...
```

Si el Mac pide instalar las herramientas de desarrollo (`git`), acepta. Si falta Python: https://www.python.org/downloads/

## 3. Uso diario con Claude Code

Abre Claude Code en la carpeta (`cd licitaciones-bot && claude`) y escribe:

| Comando | Qué hace |
|---|---|
| `/revisar` | Descarga las licitaciones del día y te recomienda 3-5 para mirar |
| `/oferta 1234-56-LE26` | Crea `ofertas/1234-56-LE26/` con la ficha. La primera vez te pide descargar las bases |
| `/oferta 1234-56-LE26` (otra vez) | Con las bases ya descargadas: checklist, propuesta técnica, oferta económica y los Word en `para_subir/` |

Para descargar las bases, abre el enlace de la ficha, baja los PDF y anexos y déjalos en
`ofertas/<CODIGO>/bases/`.

Lo mismo funciona sin Claude, desde la Terminal:

```bash
.venv/bin/python -m licitaciones actualizar            # resumen en salida/resumen.md
.venv/bin/python -m licitaciones resumen               # recalcula tras editar el perfil (sin API)
.venv/bin/python -m licitaciones preparar CODIGO
.venv/bin/python -m licitaciones bases CODIGO          # tras descargar las bases
.venv/bin/python -m licitaciones exportar CODIGO       # borradores/*.md → para_subir/*.docx
.venv/bin/python -m licitaciones marcar CODIGO descartada   # o postulada / ganada / perdida
```

## 4. Ajustar a 100 Modos (lo más importante)

- **`config/perfil.yaml`** decide qué aparece: tipos de servicio, temas, exclusiones, regiones y montos.
  Si salen licitaciones que no corresponden, agrega palabras a `excluir`. Si se pierde alguna buena, agrega su tema.
- **`config/empresa.yaml`** tiene los datos que van en la oferta: RUT, relatores, experiencia,
  metodología y precios. Claude no inventa nada; lo que falte aparece como `[COMPLETAR: ...]`.
  Llenarlo bien es lo que más mejora las ofertas y ahorra idas y vueltas.

## 5. Cómo se ahorran tokens

- Filtrar miles de licitaciones cuesta 0 tokens, porque lo hace Python en el computador.
- `/revisar` lee un solo archivo corto, `salida/resumen.md`.
- `/oferta` lee la ficha, un extracto de las bases (`bases_resumen.md`, normalmente un 10-20 % del original)
  y `empresa.yaml`. Nunca lee los PDF completos.
- Claude Code usa **Sonnet** por defecto (`.claude/settings.json`). Rinde más con el límite de la suscripción.
  Para una oferta importante se puede cambiar a Opus con `/model`.
- Escribe `/clear` entre una licitación y otra, para que no arrastre el contexto anterior.

## 6. Trabajar juntos

Uno desarrolla y sube cambios con `git push`. La otra persona actualiza con `git pull`.
Los datos (`datos/`, `ofertas/`, `salida/`, `.env`) no se suben a GitHub: quedan solo en cada computador.

Tests: `.venv/bin/python -m pytest -q`
