"""Build the reproducible Spanish results report from exported backtests."""
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load(symbol,case,phase='holdout'):
    return json.loads((ROOT/'results'/f'{symbol}_{phase}_{case}'/'summary.json').read_text())

def main():
    lines=['# Resultados propios — v0.2\n',
    '**Resultado: no hay evidencia suficiente para operar dinero real con estas estrategias.**\n',
    'Son simulaciones sobre datos históricos, no operaciones reales ni previsiones. Universo fijado: BTCUSDT y ETHUSDT. Periodo: enero–marzo de 2025, 25.920 velas 5m por símbolo (51.840 total), descargadas del archivo oficial Binance y verificadas con sus checksums. El trimestre elegido sirve como estudio piloto reproducible, no representa todos los regímenes ni el mercado actual.\n',
    'Protocolo fijado antes de ver resultados: elegir el mayor PnL de enero entre SMA 5/20, 12/48 con separación 26 bps y 20/60 con separación 26 bps. Validar en febrero y evaluar en marzo sin reselección. Ambos símbolos seleccionaron SMA 20/60. Las ventanas significan barras de cinco minutos (100 y 300 minutos); no es scalping de segundos. El parámetro de separación no es una previsión de beneficio.\n',
    'Cada evaluación empieza con 1.000 USDT virtuales, una sola posición de hasta 100 USDT, sin apalancamiento ni reinversión proporcional. Máximo 12 entradas por día UTC, pausa de 3 barras tras salida, bloqueo al caer 5% desde máximo y pausa diaria tras caer 2%. Señal calculada antes de apertura, ejecución en apertura siguiente con impacto; cierres por riesgo se realizan en la siguiente observación, no en un stop intrabar.\n',
    'Costes base hipotéticos: 10 bps de comisión por lado, spread completo 2 bps y slippage 2 bps por lado. No corresponden a una tarifa confirmada de tu cuenta. Paso de cantidad 0,000001 y nominal mínimo 5 USDT son parámetros de laboratorio, no todos los filtros históricos de Binance. Electricidad/impuestos: excluidos.\n',
    '## Validación de febrero\n',
    '| Par | PnL neto USDT | Operaciones cerradas | Caída máxima de la cuenta |',
    '|---|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        r=load(symbol,'selected','validation')
        lines.append(f"| {symbol} | {r['net_pnl']:.6f} | {r['closed_trades']} | {r['max_drawdown_pct']:.3f}% |")
    lines+=['\n## Evaluación final: marzo, 744 horas\n',
    '| Par | Estrategia/coste | PnL neto USDT | Comisiones USDT | Operaciones | Caída máxima cuenta |',
    '|---|---|---:|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        for case in ('baseline_5_20','selected','buy_hold_100','cash','selected_cost_zero','selected_fee_7_5','selected_stress'):
            r=load(symbol,case)
            lines.append(f"| {symbol} | {case} | {r['net_pnl']:.6f} | {r['fees']:.4f} | {r['closed_trades']} | {r['max_drawdown_pct']:.3f}% |")
    lines+=['\nLa baseline 5/20 usa hasta 288 entradas/día y sin cooldown, con los mismos límites de pérdida. Es una adaptación a velas de la idea de v0.1, no su reproducción a intervalos de cinco segundos. `buy_hold_100` compra hasta 100 USDT y conserva el resto en efectivo; no aplica stops ni rebalanceo. `selected_cost_zero` elimina comisión e impacto; `selected_fee_7_5` reduce solo la comisión a 7,5 bps; `selected_stress` usa comisión 15, slippage 5 y spread 10 bps. No reoptimiza los parámetros.\n',
    '## Ganancias y pérdidas por hora/segundo\n',
    '| Par, estrategia seleccionada | Media USDT/h | Media aritmética USDT/s | Peor hora USDT | Mejor hora USDT | Aciertos | Profit factor |',
    '|---|---:|---:|---:|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        r=load(symbol,'selected')
        lines.append(f"| {symbol} | {r['average_pnl_per_hour']:.9f} | {r['average_pnl_per_second']:.12f} | {r['worst_hour_pnl']:.4f} | {r['best_hour_pnl']:.4f} | {r['win_rate_pct']:.2f}% | {r['profit_factor']:.4f} |")
    lines+=['\nLas horas se agrupan en UTC y contienen cambios de patrimonio, incluyendo posiciones abiertas. Las ganancias de las operaciones cerradas se registran por separado. Al final se liquida todo el inventario pagando salida; así el PnL total concilia con operaciones realizadas. La media por segundo NO es una medición de ejecución ni extremos intrasegundo. Los promedios incluyen todas las 744 horas, también sin exposición.\n',
    'ETH terminó con solo unas milésimas de USDT de beneficio: es económicamente indistinguible de cero para este uso, y los costes adicionales lo vuelven negativo. BTC pasó de beneficio sin costes a pérdida neta. El estrés pierde en ambos. No interpretamos ganar menos pérdidas que la baseline como haber encontrado ventaja positiva.\n',
    '## Dos cuentas simultáneas\n']
    curves=[]
    for symbol in ('BTCUSDT','ETHUSDT'):
        with (ROOT/'results'/f'{symbol}_holdout_selected'/'equity.csv').open() as f:
            curves.append(list(csv.DictReader(f)))
    peak=2000.;dd=0;out=[]
    for a,b in zip(*curves):
        assert a['timestamp']==b['timestamp']
        eq=float(a['equity'])+float(b['equity']);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak*100)
        out.append({'timestamp':a['timestamp'],'equity_combined':eq})
    with (ROOT/'results'/'combined_equity.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys());w.writeheader();w.writerows(out)
    lines.append(f"Capital total virtual: 2.000 USDT. PnL conjunto: {out[-1]['equity_combined']-2000:.6f} USDT. Caída máxima conjunta marcada a cierre: {dd:.3f}%. Es agregación de dos cuentas independientes, NO un límite de riesgo global implementado.\n")
    runtime=json.loads((ROOT/'results'/'runtime.json').read_text())
    lines+=['## Requerimientos medidos\n',f"El benchmark completo consumió {runtime['wall_seconds']:.2f} segundos en el entorno de desarrollo y un máximo de {runtime['python_peak_allocated_mib']:.2f} MiB de asignaciones Python medido con tracemalloc. Esa cifra NO es RAM total del proceso ni medición del i7 del usuario; la instrumentación añade coste. No permite inferir latencia de trading. No utiliza GPU ni paquetes externos.\n",
    '## Límites y reproducibilidad\n',
    'Los CSV y hashes están incluidos. `python3 benchmark.py` reproduce las tablas; `python3 make_report.py` actualiza este informe. No se usó un modelo de IA ni se buscó ajustar parámetros al resultado de marzo. Solo se reservaron periodos históricos, no datos futuros realmente inéditos. Repetir ajustes mirando marzo lo convertiría en entrenamiento.\n',
    'Faltan profundidad, colas maker, latencia variable, ejecuciones parciales, spread histórico, filtros históricos exactos, delistings, comisiones específicas, otros trimestres y validación demo. El drawdown observado en aperturas/cierres puede subestimar el intrabar; no existe un stop garantizado. Un solo trimestre y dos símbolos no permiten estimar probabilidad de rentabilidad futura.\n',
    'Los resultados completos están en `results/comparison.csv`, `selection.json` y los directorios con `summary.json`, `trades.csv`, `hourly.csv` y `equity.csv`. El estudio de otros bots y bibliografía están en `research/ANALISIS.md`.\n']
    (ROOT/'research'/'RESULTADOS.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
