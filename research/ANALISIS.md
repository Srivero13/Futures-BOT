# Auditoría y evidencia — Rivero Bots v0.2

Preparado para Santiago Rivero. Consulta de fuentes: 12 de septiembre de 2026.

## Dictamen sobre la v0.1

La v0.1 era una prueba de infraestructura. No había evidencia para llamarla bot rentable, IA ni scalper validado. Haber aprobado diez pruebas no demuestra ventaja de mercado. Una serie sinusoidal permite comprobar compras y ventas, pero no representa la incertidumbre del mercado. El funcionamiento local tampoco demuestra conexión a dos cuentas reales.

| Hallazgo | Consecuencia | Cambio de v0.2 |
|---|---|---|
| Medias de observaciones, no de velas cerradas | Dependen de la frecuencia de consulta | Nuevo motor histórico causal con velas 5m |
| Señal y ejecución sobre la misma observación | Ejecución demasiado optimista | Señal previa; apertura de vela siguiente más costes |
| Sin históricos ni periodo reservado | Imposible evaluar generalización | Enero selección, febrero validación, marzo evaluación final |
| Sin referencia pasiva | Ganar puede deberse solamente al mercado | Efectivo y buy-and-hold con igual asignación inicial |
| Pérdida desde capital inicial, sin día ni máximo | No cubre pérdidas desde una ganancia previa | Motor histórico incorpora pérdida diaria y drawdown desde máximo |
| Historia de muestras perdida al reiniciar | Señales distintas tras un reinicio | Persistencia atómica de últimas 20 muestras en motor paper |
| Sin métricas horarias ni realizadas/no realizadas | PnL incompleto o difícil de interpretar | Exportaciones históricas y reporte del libro paper |
| Contabilidad float | Insuficiente como base de ejecución financiera | Nuevo backtester usa Decimal; motor paper heredado sigue float |
| Respuestas lentas de cotizaciones aceptadas | Puede simular con datos retrasados | Rechazo tras >5 segundos; aún no verifica edad del dato en exchange |
| Simulador no reproduce CFD ni forex | Trasladar resultados sería incorrecto | Alcance económico explícito: Binance Spot, largo, sin apalancamiento |

El programa `bot.py` conserva el laboratorio concurrente de v0.1 con las correcciones de persistencia y demora. `backtest.py` es un motor distinto para investigación: sus nuevas reglas de riesgo no se presentan como ya integradas en el motor online. No se ha demostrado equivalencia entre ambos. Capital demo continúa siendo consulta de cuentas, no ejecución.

## Otros bots: qué evidencia existe

### Hummingbot en Binance: resultados publicados, no auditados por nosotros

La fundación publicó una competición de 48 horas en septiembre de 2023 con cinco participantes elegibles y menos de 100 USDT iniciales por participante. La tabla reporta estos PnL; las dos últimas columnas son nuestras divisiones aritméticas:

| Participante | Mercado | PnL reportado (USDT/48h) | Media USDT/h | Media USDT/s |
|---|---|---:|---:|---:|
| doi_doi | Binance perpetuos | +134,72 | +2,806667 | +0,00077963 |
| WeGotGame | Binance perpetuos | +11,24 | +0,234167 | +0,00006505 |
| nikita7970 | Binance perpetuos | −5,40 | −0,112500 | −0,00003125 |
| fengtality | Binance spot | −1,00 | −0,020833 | −0,00000579 |
| cgambit | Binance spot | −3,61 | −0,075208 | −0,00002089 |

Fuente primaria: [Hummingbot, resultados](https://hummingbot.org/blog/-beta-bot-battle-results-and-roundup/).

No conocemos desde esa tabla la distribución por segundo, el drawdown completo ni un historial prolongado. Hay sesgo de participación y datos excluidos. El resultado de futuros no es comparable con nuestro spot sin apalancamiento. No anualizamos los ganadores ni extrapolamos al capital del usuario. No son un rendimiento esperado de Hummingbot.

### Binance Spot Grid

Binance distingue beneficio de operaciones emparejadas e inventario no realizado: un grid puede mostrar ganancias en ciclos cerrados y perder en total. Por eso v0.2 conserva la valoración de inventario y fuerza el cierre final del backtest con costes. No encontramos un rendimiento poblacional auditado que permita asignar una ganancia por hora al producto. [Parámetros oficiales](https://www.binance.com/en/support/faq/detail/688ff6ff08734848915de76a07b953dd).

### Freqtrade

Es infraestructura para estrategias propias, no una tasa de retorno. Su documentación recomienda como mínimo 2 vCPU, 2 GB RAM y 1 GB de disco, y reloj sincronizado. El i7/16 GB supera ese mínimo para trabajo modesto, aunque históricos y búsquedas intensivas requieren más recursos. [Repositorio oficial](https://github.com/freqtrade/freqtrade).

Sus herramientas advierten del sesgo de mirar velas futuras y de diferencias entre backtest y ejecución. Adoptamos separación temporal y una prueba que modifica el futuro y comprueba que no cambia el pasado. No hemos ejecutado Freqtrade ni Hummingbot, ni replicado sus estrategias: los rendimientos propios pertenecen exclusivamente a nuestro motor. [Lookahead](https://www.freqtrade.io/en/stable/lookahead-analysis/) · [Backtesting](https://www.freqtrade.io/en/stable/backtesting/).

## Estudios de mercado

**Hudson y Urquhart, Technical trading and cryptocurrencies, Annals of Operations Research.** Examina 14.919 reglas con datos diarios y ajustes por pruebas múltiples. Encuentra resultados favorables en parte del análisis, pero Bitcoin no conserva predictibilidad fuera de muestra. Esto respalda reservar datos y controlar selección; no prueba scalping rentable en Binance. [Artículo](https://link.springer.com/article/10.1007/s10479-019-03357-1).

**Bysik y Ślepaczuk, preprint 2026, Machine Learning-Based Bitcoin Trading Under Transaction Costs.** El resumen describe unas 70.000 observaciones horarias y 27 ventanas de validación. Las estrategias ingenuas fallan con costes de diez puntos básicos; algunas configuraciones filtradas mejoran, y una XGBoost supera 65% anualizado en su experimento. No es historial de dinero real, no lo replicamos y no trasladamos esa cifra a este bot. La lectura se limita al resumen del preprint. [arXiv](https://arxiv.org/abs/2606.00060).

**Inferencia para nuestro diseño:** antes de añadir una red neuronal, debemos comprobar si la señal supera costes y sobrevive a datos reservados. No hay evidencia aquí para comprar GPU ni afirmar que IA compleja superará un modelo pequeño. El filtro de separación de medias de v0.2 NO predice un retorno ni garantiza superar costes; es una hipótesis que se somete a prueba.

## Cuánto puede ganar o perder por segundo y hora

No existe una renta fija. Se necesitan capital, importe por operación, operaciones completadas, ganancia/pérdida media, comisiones y distribución temporal. Un promedio por segundo es PnL dividido por segundos: no significa una operación cada segundo ni flujo estable. Nuestras velas 5m no permiten medir extremos intrasegundo.

Ejemplo puramente hipotético: importe 100 USDT; comisión 0,10% en cada lado; spread completo 0,02%; slippage 0,02% por lado. Coste de ida/vuelta aproximado: 0,26 USDT. No son tarifas confirmadas de tu cuenta. El coste exacto cambia con el precio de salida.

| Cambio favorable bruto por ciclo | PnL neto aproximado/ciclo | Si se completaran 10 ciclos iguales/h |
|---|---:|---:|
| 0,10% | −0,16 USDT | −1,60 USDT/h |
| 0,30% | +0,04 USDT | +0,40 USDT/h |
| −0,30% | −0,56 USDT | −5,60 USDT/h |

Estas filas NO son predicciones ni probabilidades. Presuponen los mismos movimientos en todos los ciclos. El punto de equilibrio debe calcularse incluyendo ambas ejecuciones; cuantos más ciclos sin ventaja, más pérdida por costes.

Para electricidad: coste/h = potencia medida en W / 1000 × tarifa por kWh. Convierte a la moneda del backtest antes de usar `--overhead-hour`. No conocemos potencia real, tarifa marginal ni conversión aplicable. Los resultados entregados excluyen electricidad, impuestos y depósitos/retiros; incluyen los costes de negociación simulados.

## Problemas pendientes y prioridades

| Riesgo | Efecto | Tratamiento |
|---|---|---|
| Comisiones/promociones por cuenta | Estrategia bruta rentable puede perder | Escenarios de costes; confirmar tarifa de cuenta antes de operar |
| Spread/slippage variables | Destruyen márgenes pequeños | Estrés incorporado; pendiente libro de órdenes histórico |
| Ejecuciones parciales/cola maker | Una señal no equivale a una orden llenada | Aún no modelado; no enviar reales |
| Selección de pares y periodo | BTC/ETH Q1 no representan todo el mercado | Ampliar a periodos y regímenes distintos antes de aprobar estrategia |
| Dos bots correlacionados | Duplicación de exposición a cripto | Mostrar capital por cuenta; límite global aún pendiente |
| Corte de luz/internet y reinicios | Posiciones sin supervisión | Persistencia local; falta reconciliación real y supervisor |
| Saltos de precio | Pérdida supera stop | Prueba explícita; límite no garantizado |
| Límites API y filtros por símbolo | Rechazos, bloqueos o tamaños inválidos | Redondeo/min_notional de laboratorio; falta cargar filtros reales |
| Sobreajuste | Parámetros ganadores del pasado fallan después | Tres candidatos prefijados y periodo reservado |
| Confundir spot con futuros/CFD | Riesgos de margen, financiación y liquidación | Excluidos del benchmark; se implementarán con modelos propios |

Los filtros oficiales incluyen límites de precio, cantidad y nominal: [Binance filters](https://developers.binance.com/docs/binance-spot-api-docs/filters). Un paso decimal genérico en un backtest no sustituye todos esos filtros. Las API también tienen límites: [Binance REST](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/limits).

## Decisión técnica

Mantener Ubuntu y Python, dos procesos pequeños y almacenamiento SSD. Para el alcance actual no se justifica más hardware sin medir. La v0.2 debe juzgarse por la capacidad de detectar y documentar estrategias malas, no por forzar un resultado positivo. No incorpora IA entrenada ni ejecución real. La integración operativa posterior deberá compartir el mismo motor de decisión validado y añadir reconciliación, límites globales, estado de órdenes y pruebas demo prolongadas.
