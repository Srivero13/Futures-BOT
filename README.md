# Futures-BOT — Rivero Bots v0.2

**Entrega de investigación y simulación. No envía órdenes reales.**

El nombre del repositorio es Futures-BOT; la versión actual investiga exclusivamente spot sin apalancamiento. El soporte de futuros está pendiente.

Lee primero `research/RESULTADOS.md` y `research/ANALISIS.md`: los costes eliminan el beneficio de las estrategias estudiadas. No hay IA entrenada ni rentabilidad demostrada.

## Qué cambió

- Backtester causal en Decimal con datos oficiales BTC/ETH, cierre de inventario y costes en ambos lados.
- Selección enero 2025 / validación febrero / evaluación marzo; escenarios de costes y referencias pasivas.
- Métricas de PnL neto, comisiones, drawdown, aciertos, profit factor, peor/mejor hora y promedios por hora/segundo.
- Controles del motor histórico: nominal, tamaño mínimo/redondeo, cooldown, entradas diarias, pérdida diaria y drawdown.
- Laboratorio de dos procesos: conserva últimas muestras al reiniciar, rechaza consultas Binance demoradas más de 5 segundos y añade reporte realizado/no realizado.
- Código, datos oficiales normalizados, hashes, pruebas y resultados incluidos para reproducir offline.

## Requisitos

Ubuntu 24.04 LTS recomendado; Python 3.10+ y SSD. Sin pip ni bibliotecas externas.
Windows: sustituye `python3` por `py -3`; no se ha probado Windows en esta entrega.

Clona este repositorio y entra en la carpeta del proyecto:

```bash
git clone -b develop https://github.com/Srivero13/Futures-BOT.git
cd Futures-BOT
```
No sobrescribas tus bases v0.1. Los datos de investigación están en `datasets`; las cuentas virtuales se crean en `data`.

```bash
python3 restore_data.py
python3 -m unittest discover -s tests -v
python3 benchmark.py
python3 make_report.py
```

El benchmark tarda aproximadamente minutos según equipo. Los resultados ya vienen calculados; no necesitas ejecutar nada para leerlos. La descarga es opcional:

```bash
python3 download_data.py
```

No reemplaza datos por sintéticos si falla la red. Verifica los archivos con los checksums publicados por Binance. Los timestamps del archivo spot desde 2025 se normalizan de microsegundos a segundos.

## Prueba de dos bots independientes

```bash
python3 bot.py run --config configs/two-paper.json --ticks 60
```

Solo datos sintéticos, útiles para probar procesos y reinicios. O bien cotizaciones públicas de Binance con operaciones virtuales locales:

```bash
python3 bot.py run --config configs/binance-paper.json --ticks 60
python3 paper_report.py data/binance-paper-a.sqlite3 --initial-capital 1000
```

`bot.py` es el laboratorio concurrente heredado. Su estrategia usa muestras, NO el modelo de velas del backtester, y conserva contabilidad float. Los resultados históricos del motor nuevo no son una promesa de resultados de este comando. No se conectan dos cuentas reales; existen dos libros virtuales independientes.

Cada ID tiene SQLite y bloqueo propios. Omitir `--ticks` ejecuta hasta Ctrl+C. Crear un archivo `PAUSE` en el directorio detiene los procesos en su siguiente iteración y NO liquida posiciones. Eliminarlo permite reiniciar. Las pausas por pérdida persisten. El reporte requiere el capital inicial correcto de la configuración.

## Backtest particular y electricidad

```bash
python3 backtest.py datasets/BTCUSDT-5m-2025Q1.csv --output results/custom --fee-bps 10 --overhead-hour 0.01
```

`0.01` es un EJEMPLO de gasto por hora en moneda cotizada; reemplázalo por tu coste medido convertido. Las tarifas del benchmark también son supuestos; no se consultó tu cuenta privada. El backtest particular usa por defecto SMA5/20 en todo el CSV; no equivale al protocolo de selección de `benchmark.py`.

## Capital.com demo

Se conserva exclusivamente la comprobación de sesión y número de cuentas. En Bash:

```bash
read -r -s -p 'API key: ' CAPITAL_API_KEY
export CAPITAL_API_KEY
read -r -p 'Identificador: ' CAPITAL_IDENTIFIER
export CAPITAL_IDENTIFIER
read -r -s -p 'Contraseña de la API: ' CAPITAL_API_PASSWORD
export CAPITAL_API_PASSWORD
python3 bot.py capital-probe
unset CAPITAL_API_KEY CAPITAL_IDENTIFIER CAPITAL_API_PASSWORD
```

Genera la clave en la web oficial de Capital.com, Configuración > Integraciones API, con 2FA. Usa la contraseña de la clave API. No compartas secretos. La prueba solo usa el host demo. No se verificó autenticación real en esta entrega.

## Alcance pendiente

No hay IA entrenada, ejecución testnet/demo, WebSocket, equivalencia motor histórico/online, reconciliación con bróker, filtros completos ni límites globales. No se simulan forex, CFDs, margen ni futuros. Hapi sigue sin conector oficial identificado. Mantener simulación hasta disponer de estrategia validada y ejecución robusta; no es un producto terminado para inversión real.

## Datos empaquetados

Los CSV completos de históricos y resultados están en `data_bundle/`, comprimidos y divididos para facilitar la transferencia. Ejecuta `python3 restore_data.py` una vez tras clonar. Verifica SHA-256 y reconstruye los mismos CSV; no requiere internet ni sustituye archivos locales diferentes. Los resúmenes JSON e informes se pueden leer directamente.
