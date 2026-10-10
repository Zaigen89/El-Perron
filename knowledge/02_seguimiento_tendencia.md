# Seguimiento de tendencia (trend_follow_v4, 4h / diario)

## La naturaleza de la estrategia
- Gana con pocas operaciones grandes y pierde con muchas pequeñas. Un win rate de 30% a 40% es normal y correcto.
  No omitir señales solo porque las últimas perdieron: la racha de pérdidas pequeñas es el costo de estar en la grande.
- Lo que no se puede permitir es perderse la tendencia grande. Omitir una señal es más caro que tomar una mala.

## Cuándo sí tiene sentido reducir
- Cuando el precio ya se extendió mucho desde el nivel de ruptura (más de 2 ATR por encima del máximo roto).
- Cuando la volatilidad es extrema (ATR% en el decil superior histórico): reducir tamaño, no omitir.
- Fin de semana con volumen muy bajo: las rupturas son menos confiables.

## Gestión
- El stop móvil es la salida principal. No cerrar ganadoras por "ya ganó bastante": matar la tendencia es el
  error clásico de esta estrategia.
- No agrandar el stop inicial. Si la ruptura falla, falla rápido y barato.
