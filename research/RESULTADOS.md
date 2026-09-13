# Resultados propios — v0.2

**Resultado: no hay evidencia suficiente para operar dinero real con estas estrategias.**

Son simulaciones sobre datos históricos, no operaciones reales ni previsiones. Universo fijado: BTCUSDT y ETHUSDT. Periodo: enero–marzo de 2025, 25.920 velas 5m por símbolo (51.840 total), descargadas del archivo oficial Binance y verificadas con sus checksums. El trimestre elegido sirve como estudio piloto reproducible, no representa todos los regímenes ni el mercado actual.

Protocolo fijado antes de ver resultados: elegir el mayor PnL de enero entre SMA 5/20, 12/48 con separación 26 bps y 20/60 con separación 26 bps. Validar en febrero y evaluar en marzo sin reselección. Ambos símbolos seleccionaron SMA 20/60. Las ventanas significan barras de cinco minutos (100 y 300 minutos); no es scalping de segundos. El parámetro de separación no es una previsión de beneficio.

Cada evaluación empieza con 1.000 USDT virtuales, una sola posición de hasta 100 USDT, sin apalancamiento ni reinversión proporcional. Máximo 12 entradas por día UTC, pausa de 3 barras tras salida, bloqueo al caer 5% desde máximo y pausa diaria tras caer 2%. Señal calculada antes de apertura, ejecución en apertura siguiente con impacto; cierres por riesgo se realizan en la siguiente observación, no en un stop intrabar.

Costes base hipotéticos: 10 bps de comisión por lado, spread completo 2 bps y slippage 2 bps por lado. No corresponden a una tarifa confirmada de tu cuenta. Paso de cantidad 0,000001 y nominal mínimo 5 USDT son parámetros de laboratorio, no todos los filtros históricos de Binance. Electricidad/impuestos: excluidos.

## Validación de febrero

| Par | PnL neto USDT | Operaciones cerradas | Caída máxima de la cuenta |
|---|---:|---:|---:|
| BTCUSDT | -13.765246 | 49 | 2.414% |
| ETHUSDT | -26.208131 | 67 | 3.135% |

## Evaluación final: marzo, 744 horas

| Par | Estrategia/coste | PnL neto USDT | Comisiones USDT | Operaciones | Caída máxima cuenta |
|---|---|---:|---:|---:|---:|
| BTCUSDT | baseline_5_20 | -43.585497 | 41.3812 | 207 | 5.002% |
| BTCUSDT | selected | -12.801949 | 13.1952 | 66 | 1.978% |
| BTCUSDT | buy_hold_100 | -2.390039 | 0.1978 | 1 | 2.109% |
| BTCUSDT | cash | 0.000000 | 0.0000 | 0 | 0.000% |
| BTCUSDT | selected_cost_zero | 4.350947 | 0.0000 | 66 | 0.961% |
| BTCUSDT | selected_fee_7_5 | -9.503141 | 9.8964 | 66 | 1.723% |
| BTCUSDT | selected_stress | -28.617769 | 19.7785 | 66 | 3.207% |
| ETHUSDT | baseline_5_20 | -39.392721 | 28.1885 | 141 | 5.015% |
| ETHUSDT | selected | 0.002963 | 13.0129 | 65 | 1.328% |
| ETHUSDT | buy_hold_100 | -18.783915 | 0.1814 | 1 | 3.371% |
| ETHUSDT | cash | 0.000000 | 0.0000 | 0 | 0.000% |
| ETHUSDT | selected_cost_zero | 16.924933 | 0.0000 | 65 | 0.887% |
| ETHUSDT | selected_fee_7_5 | 3.256186 | 9.7597 | 65 | 1.159% |
| ETHUSDT | selected_stress | -15.601633 | 19.5056 | 65 | 2.510% |

La baseline 5/20 usa hasta 288 entradas/día y sin cooldown, con los mismos límites de pérdida. Es una adaptación a velas de la idea de v0.1, no su reproducción a intervalos de cinco segundos. `buy_hold_100` compra hasta 100 USDT y conserva el resto en efectivo; no aplica stops ni rebalanceo. `selected_cost_zero` elimina comisión e impacto; `selected_fee_7_5` reduce solo la comisión a 7,5 bps; `selected_stress` usa comisión 15, slippage 5 y spread 10 bps. No reoptimiza los parámetros.

## Ganancias y pérdidas por hora/segundo

| Par, estrategia seleccionada | Media USDT/h | Media aritmética USDT/s | Peor hora USDT | Mejor hora USDT | Aciertos | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | -0.017206921 | -0.000004779700 | -3.8027 | 3.6903 | 25.76% | 0.6018 |
| ETHUSDT | 0.000003982 | 0.000000001106 | -2.2549 | 7.6060 | 32.31% | 1.0001 |

Las horas se agrupan en UTC y contienen cambios de patrimonio, incluyendo posiciones abiertas. Las ganancias de las operaciones cerradas se registran por separado. Al final se liquida todo el inventario pagando salida; así el PnL total concilia con operaciones realizadas. La media por segundo NO es una medición de ejecución ni extremos intrasegundo. Los promedios incluyen todas las 744 horas, también sin exposición.

ETH terminó con solo unas milésimas de USDT de beneficio: es económicamente indistinguible de cero para este uso, y los costes adicionales lo vuelven negativo. BTC pasó de beneficio sin costes a pérdida neta. El estrés pierde en ambos. No interpretamos ganar menos pérdidas que la baseline como haber encontrado ventaja positiva.

## Dos cuentas simultáneas

Capital total virtual: 2.000 USDT. PnL conjunto: -12.798987 USDT. Caída máxima conjunta marcada a cierre: 1.503%. Es agregación de dos cuentas independientes, NO un límite de riesgo global implementado.

## Requerimientos medidos

El benchmark completo consumió 86.15 segundos en el entorno de desarrollo y un máximo de 25.60 MiB de asignaciones Python medido con tracemalloc. Esa cifra NO es RAM total del proceso ni medición del i7 del usuario; la instrumentación añade coste. No permite inferir latencia de trading. No utiliza GPU ni paquetes externos.

## Límites y reproducibilidad

Los CSV y hashes están incluidos. `python3 benchmark.py` reproduce las tablas; `python3 make_report.py` actualiza este informe. No se usó un modelo de IA ni se buscó ajustar parámetros al resultado de marzo. Solo se reservaron periodos históricos, no datos futuros realmente inéditos. Repetir ajustes mirando marzo lo convertiría en entrenamiento.

Faltan profundidad, colas maker, latencia variable, ejecuciones parciales, spread histórico, filtros históricos exactos, delistings, comisiones específicas, otros trimestres y validación demo. El drawdown observado en aperturas/cierres puede subestimar el intrabar; no existe un stop garantizado. Un solo trimestre y dos símbolos no permiten estimar probabilidad de rentabilidad futura.

Los resultados completos están en `results/comparison.csv`, `selection.json` y los directorios con `summary.json`, `trades.csv`, `hourly.csv` y `equity.csv`. El estudio de otros bots y bibliografía están en `research/ANALISIS.md`.

