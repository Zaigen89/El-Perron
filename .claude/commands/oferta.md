---
description: Prepara los borradores de la oferta para una licitación (uso /oferta CODIGO)
argument-hint: CODIGO
allowed-tools: Bash(.venv/bin/python -m licitaciones:*), Bash(grep:*), Read, Write, Edit
---
Licitación: $ARGUMENTS

1. Ejecuta `.venv/bin/python -m licitaciones preparar $ARGUMENTS`.
   Si dice que FALTAN LAS BASES, detente: dile que descargue las bases y anexos desde el enlace de la ficha
   a `ofertas/$ARGUMENTS/bases/` y que vuelva a escribir `/oferta $ARGUMENTS`. No sigas sin bases.
2. Lee solo `ofertas/$ARGUMENTS/ficha.md`, `ofertas/$ARGUMENTS/bases_resumen.md`, `config/empresa.yaml`,
   `plantillas/checklist.md` y `plantillas/propuesta_tecnica.md`. Si algo clave no está en el resumen,
   usa grep sobre `ofertas/$ARGUMENTS/bases_texto.txt`.
3. Escribe `ofertas/$ARGUMENTS/borradores/checklist.md` siguiendo la plantilla: requisitos de admisibilidad,
   anexos y documentos exigidos, fechas, criterios de evaluación con ponderación y cómo sacar el máximo
   en cada uno, riesgos (requisitos que 100 Modos quizás no cumple, p. ej. OTEC/SENCE o experiencia mínima).
4. Escribe `ofertas/$ARGUMENTS/borradores/propuesta_tecnica.md` siguiendo la plantilla y respondiendo
   punto por punto a lo que piden las bases, con el lenguaje de los criterios de evaluación.
   Usa solo datos de `config/empresa.yaml`; lo que falte va como `[COMPLETAR: qué falta]`.
5. Si las bases piden oferta económica, escribe `borradores/oferta_economica.md` con una tabla de
   valores usando los precios de referencia de empresa.yaml (o `[COMPLETAR]`), indicando si es neto/exento/con IVA según las bases.
6. Ejecuta `.venv/bin/python -m licitaciones exportar $ARGUMENTS`.
7. Responde en máximo 10 líneas: qué archivos quedaron en `para_subir/`, cuántos `[COMPLETAR]` hay y los
   3 riesgos principales. Recuérdale que revise todo y suba la oferta ella misma antes del cierre.
