# Validación v0.2

- 21 pruebas automatizadas aprobadas, Python 3.12 en Linux.
- Las pruebas verifican contabilidad de costes, conciliación PnL/hora, ejecución posterior a señal, invariancia del pasado ante cambios futuros, rechazo de velas duplicadas/huecos, saltos que superan stops, tamaños mínimos, aislamiento, reinicios, persistencia de muestras y bloqueo de modo real.
- Dos procesos ejecutados 70 iteraciones y reiniciados otras 10; 80 eventos por libro y 20 muestras recuperadas. Una iteración adicional verificó metadatos y reporte corregido.
- Consulta Capital.com solo probada con respuestas simuladas. No se conectó ninguna cuenta privada.
- Se descargaron seis archivos mensuales Binance; sus checksums SHA256 coinciden con los publicados.
- 51.840 velas OHLCV incluidas; 3 candidatos en entrenamiento por símbolo y 22 evaluaciones de validación/holdout. 28 simulaciones totales.
- Resultados y curvas completos incluidos. No se reoptimizaron parámetros después de observar la evaluación final.
- Reporte paper rechaza capital inicial inconsistente y no muestra tasas temporales en datos sintéticos ni sesiones inferiores a una hora.
- No se enviaron órdenes. No se probó Windows ni el hardware del usuario. No hay pruebas de rentabilidad futura.
