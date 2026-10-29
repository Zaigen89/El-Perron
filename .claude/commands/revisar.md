---
description: Descarga las licitaciones del día y recomienda cuáles mirar
allowed-tools: Bash(.venv/bin/python -m licitaciones:*), Read(salida/resumen.md)
---
1. Ejecuta `.venv/bin/python -m licitaciones actualizar`. Si falla por el ticket, explica en una línea cómo ponerlo en `.env`.
2. Lee `salida/resumen.md` (solo ese archivo).
3. Responde en máximo 12 líneas: las 3-5 más prometedoras para 100 Modos (código, nombre corto, cierre,
   por qué calza en una frase) y las que parecen falsos positivos para descartar
   (`.venv/bin/python -m licitaciones marcar CODIGO descartada`). Termina preguntando cuál preparar con `/oferta CODIGO`.
