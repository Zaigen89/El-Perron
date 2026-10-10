# Principios generales que el bot debe respetar (aplican a cualquier estrategia)

## Costo por operación
- Cada operación ida y vuelta cuesta ~0.1% entre comisiones y slippage. En velas de minutos eso es casi todo
  el stop; en 4 horas o diario es irrelevante. Las señales de temporalidades cortas necesitan mucha más calidad.
- Preferir pocas operaciones de calidad a muchas marginales.

## Dirección
- Operar a favor de la tendencia de la temporalidad superior. Las contratendencias son trampas frecuentes.
- Lo que mostraron 180 días de datos reales de BTC en 15 minutos: ninguna señal intradía simple predice el precio.
  La fuente de retorno observable es la deriva de tendencias de días y semanas.

## Volatilidad
- ATR muy bajo = mercado muerto; ATR muy alto = caos. Ante volatilidad extrema, reducir tamaño en vez de agrandar el stop.

## Rachas
- Tras pérdidas seguidas en condiciones parecidas, reducir tamaño. No "vengar" pérdidas aumentando tamaño.
