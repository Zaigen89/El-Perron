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
# 1. Datos reales de Binance (público, sin clave). 180 días de velas de 15 minutos:
python -m perron fetch --days 180

#    Sin conexión a Binance puedes probar el flujo con datos sintéticos (NO sirven para validar nada):
python -m perron synth --days 10

# 2. Diagnóstico: ¿hay volatilidad suficiente para pagar comisiones? ¿qué temporalidad conviene?
python -m perron diagnose

# 3. Backtest solo con reglas:
python -m perron backtest
python -m perron backtest --last-days 7 --verbose

# 3b. Análisis: ¿hay ventaja real o es ruido + comisiones? Desglose por hora, volumen, volatilidad...
python -m perron analyze
python -m perron analyze --benchmark      # compara contra entradas aleatorias con las mismas salidas

# 4. Backtest con el asesor Claude (cada señal se consulta; las decisiones se cachean):
python -m perron backtest --llm

# 5. Revisión: Claude lee el journal, escribe memory/lessons.md y propone parámetros
python -m perron review
python -m perron review --apply          # aplica las propuestas a config.yaml

# 6. Paper trading en vivo con precios de Binance (Ctrl+C para parar; reanuda donde quedó)
python -m perron --config configs/trend_4h.yaml paper          # la candidata validada
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
  strategy/value_pullback.py  v3: retroceso a valor en tendencia, stop estructural (por defecto)
  strategy/trend_follow.py    v4: Donchian + stop móvil ATR para 4h/1d (configs/trend_*.yaml)
  strategy/scalping.py        v2: ruptura tras retroceso (referencia, sin ventaja en datos reales)
  backtest/validate.py        validación IS/OOS y barrido de parámetros
  diagnose.py / analyze.py    volatilidad vs comisiones; ¿hay ventaja o es ruido?
  risk.py            tamaño por riesgo fijo, tope de posición, pérdida diaria máxima, enfriamiento
  backtest/engine.py simulador vela a vela con comisiones, slippage, SL/TP intra-vela y salida por tiempo
  backtest/metrics.py PnL, win rate, profit factor, drawdown, Sharpe, desglose por motivo de salida
  llm/advisor.py     Claude decide approve/skip/reduce por señal (JSON validado por esquema, con cache)
  llm/reviewer.py    Claude revisa el historial, reescribe lecciones y propone parámetros acotados
  llm/memory.py      carga knowledge/*.md (tus ideas) y memory/lessons.md (lo aprendido)
  paper/runner.py    paper trading en vivo, con estado persistente para reanudar
  journal.py         registro de cada operación (JSONL) con las features de la señal y la decisión del LLM
```

### Estrategias disponibles (`strategy.name` en config.yaml)

**`value_pullback_v3` (por defecto).** Velas de 15 minutos con tendencia en 1 hora. Compra el retroceso a valor
dentro de la tendencia, no la ruptura. Long (short es espejo):
1. Tendencia 1h alcista: precio sobre la EMA50 de 1h y esa EMA subiendo (vela 1h anterior cerrada, sin mirar al futuro).
2. El mínimo de la vela 15m tocó la EMA21 o el VWAP de sesión (tolerancia 0.05%).
3. La vela rechaza el nivel: cierra por encima de la EMA21 y de su apertura.
4. No está extendida: cierre a menos de 0.35% del VWAP y RSI(7) entre 35 y 60.
5. Stop por estructura: debajo del mínimo de las últimas 4 velas menos 0.25 ATR, acotado entre 1 y 3 ATR.
   Si el retroceso fue más profundo que 3 ATR no se opera.
6. Objetivo = 2 veces la distancia del stop, y debe cubrir al menos 2x las comisiones. Salida por tiempo a las 3 horas.

**`scalping_pullback_v2`.** Velas de 5 minutos, entrada por ruptura del máximo previo tras un retroceso con
stop de 1 ATR. Se conserva como referencia: en 60 días de datos reales de BTC se comportó igual que entradas
aleatorias (34.5% de aciertos con objetivo 2:1) y el 45% de sus operaciones murió en la primera vela.
Es el ejemplo de por qué el stop no puede estar dentro del ruido y por qué no se persiguen rupturas.

Entrada siempre en la apertura de la vela siguiente a la señal. Si en una vela se tocan stop y objetivo, se
asume el stop (conservador).

**`trend_follow_v4`.** Seguimiento de tendencia en 4 horas o diario (`configs/trend_4h.yaml`, `configs/trend_1d.yaml`).
Entrada al cerrar sobre el máximo de 20 velas con filtro de régimen (EMA100), solo largos, stop inicial de 2 ATR,
stop móvil a 4 ATR del máximo alcanzado, salida al cerrar bajo el mínimo de 10 velas. Sin objetivo fijo: se deja correr la tendencia.
Motivo: el estudio de eventos sobre 180 días de 15m mostró que a horizontes de minutos a pocas horas ninguna señal
simple predice el precio de BTC; la única fuente de retorno observable es la deriva de tendencias de días y semanas,
donde además las comisiones dejan de importar (ATR de 1% a 3% contra 0.1% de costo). Requiere años de datos:

```bash
python -m perron fetch --interval 4h --days 2000
python -m perron fetch --interval 1d --days 3000
python -m perron --config configs/trend_4h.yaml backtest --oos-days 365
python -m perron --config configs/trend_1d.yaml backtest --oos-days 365
```

**Resultados con años de datos reales de Binance (riesgo 1% por operación, comisiones 0.04% + slippage 0.01% por lado):**

| | Periodo | Operaciones | Retorno | Drawdown máx. | Profit factor | Fuera de muestra (último año) | Comprar y mantener |
|---|---|---|---|---|---|---|---|
| 4h | 2021-04 a 2026-10 | 157 | +106% | -8.2% | 1.82 | +6.9%, PF 1.35 | +44%, drawdown -77% |
| 1d | 2018-07 a 2026-10 | 41 | +87% | -3.7% | 3.87 | -2.7%, 11 operaciones (muestra chica) | +912%, drawdown -77% |

En 4h, 38 de 72 combinaciones del barrido son positivas dentro y fuera de muestra; en diario, 65 de 72.
La ventaja es estructural (seguir tendencias en BTC), no de un parámetro afinado. En 2022, año bajista con
buy&hold en -65%, la versión 4h perdió 4.8%. El retorno escala con `risk_per_trade_pct`; lo que importa es
retorno/drawdown (13x en 4h contra 0.6x de comprar y mantener). Las versiones intradía (v2, v3) no tienen ventaja.

### Validar sin engañarse

```bash
python -m perron backtest --oos-days 30     # reserva los últimos 30 días: solo se miran al final
python -m perron sweep --oos-days 30        # barrido de parámetros; cuenta la columna oos_exp, no is_exp
python -m perron analyze --benchmark        # ¿supera a entradas aleatorias con las mismas salidas?
```

Regla de oro: los parámetros se eligen mirando solo el tramo dentro de muestra (IS). El tramo fuera de muestra
(OOS) se mira una vez al final. Si IS gana y OOS pierde, fue sobreajuste. Si ninguna combinación del barrido es
positiva en ambos tramos, el problema es la idea, no los números.

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
- Un backtest de pocos meses es poca muestra. Mira el `profit_factor` y la expectativa por operación
  después de comisiones, no el PnL bruto.
- Si un parámetro propuesto por el revisor mejora el backtest, pruébalo en un periodo distinto antes de creerlo.
  Lo que mejora el pasado por ajuste fino suele empeorar el futuro.
- Scalping intradía es el terreno donde comisiones y latencia más duelen. El paper trading aquí asume relleno en el
  precio del exchange más 0.01% de slippage; en real puede ser peor.

## Pruebas

```bash
python -m pytest -q
```
