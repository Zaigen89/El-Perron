# Licitaciones 100 Modos

Herramienta para encontrar licitaciones de Mercado Público (Chile) que calzan con 100 Modos
(charlas, talleres y capacitaciones para equipos y organizaciones) y preparar ofertas.

## Reglas para ahorrar tokens (importante)
- El trabajo mecánico lo hace Python: `.venv/bin/python -m licitaciones <comando>`. No lo repliques a mano.
- No leas `datos/`, `bases_texto.txt` ni código fuente salvo que se pida arreglar el programa.
  Si falta un dato de las bases, búscalo con grep en `bases_texto.txt`, no lo leas entero.
- Para una oferta lee solo: `ofertas/<CODIGO>/ficha.md`, `ofertas/<CODIGO>/bases_resumen.md`,
  `config/empresa.yaml` y la plantilla que corresponda en `plantillas/`.
- Respuestas breves en el chat; el contenido largo va a archivos.
- Nunca inventes datos de la empresa (experiencia, RUT, relatores, precios): usa `[COMPLETAR: ...]`.
- Nunca envíes ni subas nada a Mercado Público; ella revisa y sube la oferta a mano.

## Comandos
- `/revisar`: actualiza y muestra las licitaciones que calzan.
- `/oferta CODIGO`: prepara la carpeta y los borradores de la oferta.
