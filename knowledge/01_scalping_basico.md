# Principios de scalping que el bot debe respetar

## Costo por operación
- Cada operación ida y vuelta cuesta ~0.1% entre comisiones y slippage. Una señal mediocre con objetivo de 0.15% no vale la pena.
- Preferir pocas operaciones de calidad a muchas operaciones marginales.

## Dirección
- Operar solo a favor de la tendencia de 5 minutos. Las contratendencias en 1m son trampas frecuentes.
- Si el precio ya recorrió más de 1.5 ATR en la dirección de la señal en las últimas 5 velas, el movimiento está extendido: omitir o reducir.

## Volatilidad
- ATR muy bajo = mercado muerto: los objetivos no se alcanzan y se sale por tiempo pagando comisiones.
- ATR muy alto = caos: los stops saltan por ruido. Reducir tamaño en vez de agrandar el stop.

## Volumen
- Una ruptura sin volumen es sospechosa. Volumen >= 1.5x la media da más confianza que 1.2x.

## Rachas
- Tras dos pérdidas seguidas en condiciones parecidas, reducir tamaño a la mitad hasta recuperar una ganancia.
- No "vengar" pérdidas aumentando tamaño.

## Distancia a referencias
- Entradas muy lejos del VWAP tienden a revertir hacia él: cuidado con comprar muy por encima o vender muy por debajo.
