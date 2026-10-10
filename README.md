# El Perrón — bot de scalping BTC (reglas fijas + asesor Claude), solo paper trading

Sistema para **probar ideas de scalping sobre BTCUSDT sin dinero real**. Un motor de reglas detecta señales,
un gestor de riesgo pone límites duros, y un asesor basado en Claude decide si cada señal se ejecuta, se omite
o se ajusta, usando tus ideas de trading y las lecciones que va aprendiendo de su propio historial.

> Nada aquí ejecuta órdenes reales. No hay claves de exchange ni código para enviar órdenes.

## Instalación (en tu PC)

Necesitas Python 3.10 o superior. En macOS el comando es `python3`, no `python`. Si `python3 --version`
no responde, instálalo desde https://www.python.org/downloads/ o con Homebrew (`brew install python`).

```bash
git clone https://github.com/Zaigen89/El-Perron
cd El-Perron
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
```

Para el asesor LLM necesitas una clave de la API de Anthropic:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sk-ant-..."
```

## Flujo de trabajo

```bash
# 1. Datos reales de Binance (público, sin clave). 60 días de velas de 5 minutos:
python -m perron fetch --days 60

#    Sin conexión a Binance puedes probar el flujo con datos sintéticos (NO sirven para validar nada):
python -m perron synth --days 10

# 2. Diagnóstico: ¿hay volatilidad suficiente para pagar comisiones? ¿qué temporalidad conviene?
python -m perron diagnose

# 3. Backtest solo con reglas:
python -m perron backtest
python -m perron backtest --last-days 7 --verbose

# 4. Backtest con el asesor Claude (cada señal se consulta; las decisiones se cachean):
python -m perron backtest --llm

# 5. Revisión: Claude lee el journal, escribe memory/lessons.md y propone parámetros
python -m perron review
python -m perron review --apply          # aplica las propuestas a config.yaml

# 6. Paper trading en vivo con precios de Binance (Ctrl+C para parar; reanuda donde quedó)
python -m perron paper --llm
python -m perron paper --llm --minutes 120
python -m perron review --journal paper_journal.jsonl
```

Si Binance te bloquea por región, cambia `data.base_url` en `config.yaml` a `https://data-api.binance.vision`
o `https://api.binance.us`.

## Cómo está construido

```
perron/
  config.py          lee config.yaml (todo parámetro vive ahí)
  data/binance.py    descarga de velas y precio actual (API pública)
  data/synthetic.py  velas inventadas para probar sin red
  features.py        EMA, RSI, ATR, VWAP de sesión, volumen relativo, tendencia 5m sin mirar al futuro
  strategy/scalping.py  reglas de entrada: pullback a la media + cruce de RSI + vela + volumen + tendencia 5m
  risk.py            tamaño por riesgo fijo, tope de posición, pérdida diaria máxima, enfriamiento
  backtest/engine.py simulador vela a vela con comisiones, slippage, SL/TP intra-vela y salida por tiempo
  backtest/metrics.py PnL, win rate, profit factor, drawdown, Sharpe, desglose por motivo de salida
  llm/advisor.py     Claude decide approve/skip/reduce por señal (JSON validado por esquema, con cache)
  llm/reviewer.py    Claude revisa el historial, reescribe lecciones y propone parámetros acotados
  llm/memory.py      carga knowledge/*.md (tus ideas) y memory/lessons.md (lo aprendido)
  paper/runner.py    paper trading en vivo, con estado persistente para reanudar
  journal.py         registro de cada operación (JSONL) con las features de la señal y la decisión del LLM
```

### Estrategia inicial (`scalping_pullback_v2`)

Temporalidad base de 5 minutos con filtro de tendencia en 15 minutos. Se eligió con `diagnose`: en velas de
1 minuto el ATR de BTC (~0.04% del precio) no alcanza a cubrir las comisiones de ida y vuelta (~0.10%).

Long (short es espejo):
1. Tendencia 15m alcista: precio sobre la EMA50 de 15m y esa EMA subiendo (se usa la vela 15m anterior cerrada, sin mirar al futuro).
2. En 5m, EMA9 > EMA21.
3. Hubo un retroceso en las últimas 5 velas: el RSI(7) bajó de 45 o el precio tocó la EMA9.
4. Gatillo: la vela cierra sobre la EMA9, rompe el máximo de la vela anterior, es alcista con cuerpo >= 40% de su rango,
   el RSI ya está de vuelta sobre 45 y el volumen es >= 1.2x su media de 20.
5. ATR entre 0.05% y 0.60% del precio.
6. El objetivo (2 ATR) debe ser al menos 2x el costo ida y vuelta. Sin este filtro, las operaciones que llegan al
   objetivo pierden dinero en neto.
7. Precio por encima del VWAP de la sesión.

Entrada en la apertura de la vela siguiente. Stop = 1 ATR, objetivo = 2 ATR, salida por tiempo a las 12 velas (1 hora).
Si en una vela se tocan stop y objetivo, se asume el stop (conservador).

### Dónde entra el LLM y dónde no

| Decide el LLM | Nunca decide el LLM |
|---|---|
| Ejecutar, omitir o reducir una señal que las reglas ya produjeron | Abrir operaciones sin señal |
| Multiplicador de tamaño (acotado 0 a 1.5x) | Saltarse la pérdida diaria máxima o el tope de posición |
| Ajuste de stop (0.7 a 1.5x) y objetivo (0.7 a 2x) | Cambiar la dirección de la señal |
| Lecciones y propuestas de parámetros en la revisión | Aplicar parámetros fuera de los rangos permitidos |

Si la API falla o se agota el presupuesto de llamadas, el bot sigue solo con reglas. Las decisiones se cachean en
`memory/llm_cache.json` por contexto, así que repetir un backtest con los mismos datos y conocimiento no cuesta.
Las llamadas usan `fallbacks: "default"` del lado del servidor: si el modelo principal rechaza una solicitud por
política, la API la reintenta en un modelo alternativo dentro de la misma llamada.

## Qué información darle al bot para que mejore

El bot aprende por dos canales. Uno lo alimentas tú, el otro se alimenta solo.

### 1. Tu conocimiento: `knowledge/*.md`

Todo archivo `.md` en `knowledge/` (excepto `00_plantilla.md`) se envía al asesor en cada decisión y al revisor.
Lo que más le sirve, en orden de utilidad:

- **Reglas de invalidación.** "No operar si..." vale más que "operar cuando...". Las reglas ya generan señales;
  el LLM aporta filtrándolas. Ejemplos: después de una vela de rango > 3 ATR, en los 15 minutos previos a datos
  macro de EE. UU., cuando el precio está a más de 0.5% del VWAP.
- **Contexto de sesión.** Qué horas (UTC) sueles ver buenas para scalping en BTC y cuáles no (apertura de EE. UU.,
  cierre de Asia, fines de semana con poco volumen).
- **Cómo gestionar rachas.** Cuándo reducir tamaño, cuándo parar el día.
- **Patrones de precio que reconoces.** Descríbelos con números medibles sobre las features que el bot ve:
  `rsi`, `atr_pct`, `vol_ratio`, `body_ratio`, `ret_5`, `dist_vwap_pct`, `dist_ema_fast_pct`, `trend_slope`.
  "Rechazo de nivel" no es medible; "vela con mecha superior > 60% del rango tras ret_5 > 0.4%" sí.
- **Tus errores pasados.** Lo que te ha costado dinero es lo que más vale que evite.

Lo que NO ayuda: teoría genérica larga (el prompt se trunca a 20k caracteres), opiniones sobre dónde irá BTC, y
reglas contradictorias entre archivos.

### 2. Su propia experiencia: `memory/`

- `backtest_journal.jsonl` / `paper_journal.jsonl`: cada operación con sus features, motivo de salida y lo que
  dijo el LLM. Es la fuente de verdad.
- `lessons.md`: lo que el revisor concluye del journal. Se inyecta en cada decisión futura. Puedes editarlo a mano.
- `proposals.json`: cambios de parámetros propuestos (acotados a rangos seguros definidos en `llm/prompts.py`).

Ciclo recomendado: backtest con reglas → ajustar reglas hasta que la expectativa sea positiva sin LLM →
backtest con `--llm` y comparar → `review` → repetir. Si el LLM no mejora el resultado de las reglas solas, el
problema está en el conocimiento que recibe, no en el modelo.

## Advertencias honestas

- Los datos sintéticos son ruido con regímenes; cualquier resultado sobre ellos es irrelevante. Usa `fetch`.
- Un backtest de 60 días de 5 minutos es poca muestra. Mira el `profit_factor` y la expectativa por operación
  después de comisiones, no el PnL bruto.
- Si un parámetro propuesto por el revisor mejora el backtest, pruébalo en un periodo distinto antes de creerlo.
  Lo que mejora el pasado por ajuste fino suele empeorar el futuro.
- Scalping intradía es el terreno donde comisiones y latencia más duelen. El paper trading aquí asume relleno en el
  precio del exchange más 0.01% de slippage; en real puede ser peor.

## Pruebas

```bash
python -m pytest -q
```
