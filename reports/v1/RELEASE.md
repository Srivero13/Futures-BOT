# Informe 1.0 — 13 de septiembre de 2026

## Decisión

Se entrega un motor de investigación/paper con mayor precisión contable y controles compartidos. No se habilitan entradas con los modelos incluidos: no hay evidencia de ventaja neta. No se puede elegir honestamente el timing óptimo para la PC ENTEL sin medir allí ni validar ejecución subminuto con datos de libro.

## Respuesta medida

Entorno de desarrollo, no PC del usuario. Dos series de 30 solicitudes REST públicas:

| Endpoint | Éxitos / intentos | Fallos | p50 de éxitos | p95/p99 de éxitos |
|---|---:|---:|---:|---:|
| Hora de Binance | 5 / 30 | 25 | 1831,89 ms | 3295,17 ms |
| Mejor bid/ask BTC | 3 / 30 | 27 | 3407,80 ms | 3506,67 ms |

Los percentiles con tres o cinco éxitos no son estimaciones fiables de las colas; además excluyen solicitudes fallidas. La decisión del perfil es **rechazado**, no ampliar tolerancias hasta aceptar una red mala. El timeout de urllib es por operación de socket: no garantiza una duración total máxima de dos segundos. No se midieron confirmaciones ni fills de órdenes.

La observación WebSocket recibió 2230 mensajes en 30,00 s, con una reconexión por `WebSocketProxyException`. El p95 entre recepciones fue 53,39 ms: es interarribo, **no RTT ni latencia de ejecución**. No hubo medida válida de desfase de eventos ni de cómputo de órdenes en esa observación. Datos crudos: `latency-development.json` y `stream-development.json`.

Reglas elegidas: perfil local vigente, ≥30 éxitos por endpoint, fallos ≤5%, p99 ≤1000 ms y reloj con incertidumbre ≤250 ms; espaciar decisiones al menos `max(100, 2 p95)` ms, edad máxima de recepción `min(1000, max(250, 3 p99))` ms y horizonte al menos `max(60000, 20 p99)` ms. No son parámetros optimizados para beneficio. Se bloquean nuevas entradas al caducar el perfil durante una sesión.

Binance spot bookTicker publica mejores precios/cantidades en tiempo real, pero no incluye timestamp de evento E: la edad local de recepción no prueba frescura en origen. El stream de velas permite comprobar cierre y desfase; se exige calentamiento tras huecos. La librería gestiona ping/pong y el cliente reconecta. Referencia: [documentación oficial de WebSocket](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md).

`recvWindow` determina validez temporal de solicitudes firmadas; no es un objetivo de latencia ni una razón para sondear cada 5000 ms. No se firman solicitudes en esta versión. [REST oficial](https://developers.binance.com/en/docs/products/spot/rest-api).

## Modelo matemático

La contabilidad acepta cadenas decimales, rechaza float/NaN/infinito y usa precisión 50. Cantidad redondeada hacia abajo al paso permitido; comisión y deslizamiento en entrada y salida. [Decimal de Python](https://docs.python.org/3/library/decimal.html). Más dígitos no mejoran la capacidad de anticipar el mercado.

Con ask A, bid B, comisión proporcional f y deslizamiento s, el crecimiento mínimo del bid para recuperar costes es:

`c = A (1+s) (1+f) / [B (1-s) (1-f)] - 1`.

La etiqueta es retorno logarítmico, desde apertura posterior a la vela de señal hasta apertura h minutos después: `y = 10000 ln(P_salida / P_entrada)`. Se compara el pronóstico menos un margen de error con `10000 ln(1+c) + 2` bps logarítmicos; no se mezclan retorno simple y logarítmico. Las etiquetas futuras nunca entran al cálculo de indicadores.

Ridge utiliza retorno de un minuto, momentum 5/20, volatilidad 20, volumen relativo y rango de vela. Se normaliza solo con ajuste; coeficientes mediante mínimos cuadrados aumentados con regularización L2 (alpha 10) resueltos por SVD, sin invertir X'X. [Definición oficial de Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html). Estadística float64; dinero Decimal.

La calibración estima percentil unilateral 90% del error de sobrepredicción, tomando muestras separadas h minutos. No es probabilidad de beneficio ni garantía de cobertura con dependencia temporal. Datos a más de ocho desviaciones del entrenamiento se rechazan. Escalado, horizonte y validación temporal quedan separados; se purgan etiquetas que cruzan límites. [Separación temporal con gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## Protocolo y resultados

Datos oficiales spot BTC/ETH, 131.040 velas de un minuto por símbolo, abril–junio 2025. Abril: 80% ajuste y 20% calibración. Mayo: comparar horizontes 1, 3 y 5 minutos. Junio: evaluación posterior sin volver a ajustar. Manifiesto de archivos y SHA-256 en `datasets/manifest-v1.json`; descarga mediante `download_v1_data.py`.

Los tres horizontes empataron en mayo sin operaciones. El artefacto conserva 1 minuto por orden de desempate, **no porque sea el mejor timing**. Promoción exige mayo con beneficio neto, al menos 30 cierres y RMSE de calibración menor que pronóstico cero; no se cumple. Los modelos históricos también caducan para paper actual.

En junio los modelos no operan en escenarios de 50, 250 y 1000 ms, ni con costes aumentados. Resultado neto y comisiones: cero. Es abstención, no prueba de rentabilidad ni mejora predictiva frente a la versión anterior. La referencia momentum, con los mismos límites, pierde aproximadamente 50,18 USDT en BTC y 50,14 en ETH por cada 1000 virtuales; queda bloqueada por drawdown. No es una comparación directa con la estrategia v0.2, que empleaba otro periodo/frecuencia.

Las comisiones base supuestas son 10 bps por lado, deslizamiento 2 bps y spread 2 bps; estrés 15/5/10. Un término de volatilidad previa por raíz del tiempo aumenta el spread en escenarios de latencia: es sensibilidad sintética, no reconstrucción de ejecución real. Fills completos, liquidez abundante sintética y ausencia de cola limitan el estudio. No incluye electricidad, impuestos, funding ni costes de futuros. No se puede extraer PnL observado por segundo a partir de velas de un minuto; se entrega exclusivamente promedio normalizado por segundo, junto a PnL horario agregado.

En el escenario base, el p99 del cálculo de señal fue 0,03194 ms para BTC y 0,04282 ms para ETH. Mide solo inferencia, no lectura de red, SQLite, envío ni ejecución de órdenes. Los RMSE de calibración (BTC 4,52961 y ETH 8,05565 bps logarítmicos) fueron ligeramente peores que predecir cero (4,52302 y 8,04770).

Consulta `evaluation.json` para cifras exactas, métricas por caso, RMSE y tiempos de cómputo medidos en este entorno. Los registros detallados se regeneran con `train_v1.py`. Los datos son históricos, no un diagnóstico del mercado de septiembre de 2026.

## Validación y alcance

43 pruebas automatizadas, incluyendo 21 anteriores y 22 nuevas: contabilidad exacta, coste de equilibrio, cuantización, reinicio/idempotencia, límite global, bloqueo de segunda cuenta al incurrir en costes, rechazo de quotes atrasadas/futuras, rollback, drawdown persistente, horizonte por cuenta, modelos íntegros, causalidad y separación del holdout. La prueba de autenticación demo de la suite anterior utiliza mocks; no demuestra conexión a una cuenta privada.

Se verificó conexión pública WebSocket de corta duración. No se validó funcionamiento continuo, ni PC i7, ni Windows, ni red ENTEL. Dos libros virtuales no equivalen a dos cuentas de exchange autenticadas. No hay ruta para enviar órdenes reales. Antes de desarrollar ejecución financiera hace falta una estrategia validada, datos subminuto, pruebas testnet y reconciliación robusta. La etiqueta 1.0 identifica esta entrega de software; no certifica aptitud para capital real.
