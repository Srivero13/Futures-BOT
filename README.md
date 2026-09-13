# Futures-BOT 1.0 — investigación y paper trading

Motor compartido para simulación histórica y dos cuentas virtuales BTC/USDT y ETH/USDT, con contabilidad Decimal, modelo Ridge calibrado y controles de latencia. **No envía órdenes reales. No hay rentabilidad demostrada.**

El resultado de esta entrega es una mejora de ingeniería, no una estrategia lista para invertir: los modelos entrenados no superaron la promoción y permanecen bloqueados. El nombre del repositorio no implica soporte de futuros; esta versión estudia Binance spot, sin apalancamiento. Capital.com, Hapi, forex y acciones no se incorporan al motor 1.0.

Lee [el informe 1.0](reports/v1/RELEASE.md), [los resultados reproducibles](reports/v1/evaluation.json) y [la medición de respuesta](reports/v1/latency-development.json).

## Instalación

Python 3.10+; probado con Python 3.12 en Linux. Linux es la opción inicial para el servicio. Tu i7-9700F y 16 GB son suficientes para este modelo CPU; no requiere GPU. Esto no constituye un benchmark de tu PC ni de su conexión ENTEL.

```bash
git clone -b develop https://github.com/Srivero13/Futures-BOT.git
cd Futures-BOT
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

En Windows, activa `.venv\Scripts\Activate.ps1` desde PowerShell. Windows no fue validado en esta entrega.

## Medir desde tu PC

Observación pública por WebSocket, sin claves ni operaciones:

```bash
python -m engine_v1.stream --seconds 60 --output data/stream-local.json
python -m engine_v1.latency --samples 100 --location user-pc --output data/latency-local.json
```

El segundo comando mide respuesta REST, incluidos DNS/TLS, y estima incertidumbre del reloj. No mide confirmación de órdenes. El perfil caduca a las 24 horas. No reutilices el perfil de desarrollo como medición de ENTEL.

La cadencia se calcula de los percentiles locales: separación mínima entre decisiones `max(100, 2 × p95)` ms; antigüedad máxima de cotización `min(1000, max(250, 3 × p99))` ms. Son reglas conservadoras de ingeniería. El perfil exige al menos 30 respuestas válidas por endpoint, como máximo 5% de fallos y p99 ≤ 1000 ms; incertidumbre del reloj ≤ 250 ms. Los horizontes investigados son 1, 3 y 5 minutos. No se ha demostrado un horizonte rentable ni un timing óptimo.

## Reproducir entrenamiento y evaluación

```bash
python download_v1_data.py
python train_v1.py
```

Descarga 262.080 velas oficiales de un minuto, BTC/ETH de abril a junio de 2025, verifica SHA-256 y genera modelos y resultados. Los CSV 1.0 no están empaquetados: requieren acceso a los archivos públicos de Binance. El manifiesto permite verificar los mismos datos. Abril se divide en ajuste y calibración; mayo selecciona horizonte; junio queda fuera de selección. No se debe retocar la estrategia usando junio como nueva validación.

Los resultados incluyen PnL, comisiones, drawdown, peor/mejor hora y promedios por hora/segundo. Esos promedios no son ingresos regulares ni pronósticos. No incluyen electricidad ni impuestos.

## Dos cuentas virtuales

```bash
python -m engine_v1.stream --paper --profile data/latency-local.json --seconds 3600
```

Este comando exige perfil local válido. Para entradas también exige modelos aprobados, con calibración de antigüedad máxima de siete días, y 21 velas cerradas consecutivas de calentamiento. **Los modelos incluidos son históricos y no están aprobados: no abrirán operaciones.** `train_v1.py` reproduce el experimento histórico; no es un servicio de reentrenamiento actual. No cambies `approved` ni fechas a mano para habilitarlo.

Un coordinador maneja dos libros de 1.000 USDT virtuales, nominal máximo de 100 por entrada y exposición conjunta de 200, con SQLite transaccional y controles por cuenta y cartera. Valores predeterminados: 10 bps de comisión por lado, 2 bps de deslizamiento, 20 bps de spread máximo, 12 entradas diarias, cooldown de 60 s, pérdida diaria de 2% y drawdown de 5%. No son tarifas verificadas de tu cuenta. El drawdown bloquea persistentemente entradas; la pérdida diaria se reinicia al cambiar el día UTC. Los límites no garantizan pérdidas máximas ante saltos de precio o desconexiones.

La base `data/v1-paper.sqlite3` conserva saldos y eventos; cambiar configuración requiere una base separada. No borres una base con posiciones virtuales sin conservarla. Ctrl+C detiene el proceso; no liquida al detenerse. Cotizaciones obsoletas bloquean decisiones; las salidas esperan una cotización válida. El archivo `PAUSE` pertenece al laboratorio anterior y no controla este motor.

## Cambios principales y límites

- Aritmética monetaria Decimal de 50 dígitos; cuantización por paso, costes de ida y vuelta y contabilidad persistente sin convertir dinero a float.
- Pronóstico estadístico float64 separado del dinero: Ridge mediante mínimos cuadrados SVD, normalización solo con entrenamiento, calibración posterior y descarte de entradas fuera de distribución.
- WebSocket de libro y velas cerradas; reconexión y descarte de secuencias repetidas, velas incompletas y huecos de datos.
- Un mismo motor contable para replay y paper, límites compartidos e idempotencia transaccional.
- Pruebas de causalidad, integridad de modelos, reinicio, riesgo, precisión y temporización.

No hay ejecución real/testnet, reconciliación con exchange, simulación de cola, funding, liquidaciones, ventas en corto ni órdenes protectoras remotas. Los fills paper son supuestos; velas de un minuto no validan scalping subsegundo. La observación del WebSocket durante 30 segundos no valida servicio 24/7. Falta monitorización operativa y política de retención de eventos antes de dejarlo funcionando permanentemente.

La documentación y comandos anteriores se conservan en [v0.2](docs/V0.2.md). `bot.py`, `benchmark.py` y `backtest.py` pertenecen a esa versión; el nuevo modelo se usa mediante `engine_v1` y `train_v1.py`.
