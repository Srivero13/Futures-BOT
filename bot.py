"""Rivero Bots 0.2: local paper engine. No broker order endpoints."""
import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import sqlite3
import statistics
import time
from urllib import request, parse, error

ROOT = Path(__file__).resolve().parent


def http_json(url, method='GET', headers=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = request.Request(url, data=data, method=method,
                          headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with request.urlopen(req, timeout=15) as response:
            return json.load(response), response.headers
    except error.HTTPError as exc:
        # Do not log headers, response bodies, or credentials.
        raise RuntimeError(f'HTTP {exc.code}; consulta permisos, límites o disponibilidad regional') from None
    except (error.URLError, TimeoutError):
        raise RuntimeError('Conexión no disponible; no se generó ninguna orden') from None


def binance_quote(symbol):
    started = time.monotonic()
    payload, _ = http_json('https://api.binance.com/api/v3/ticker/bookTicker?' +
                           parse.urlencode({'symbol': symbol}))
    if time.monotonic() - started > 5:
        raise RuntimeError('Cotización recibida con más de 5 segundos de demora')
    return float(payload['bidPrice']), float(payload['askPrice'])


def capital_probe():
    """Authenticate DEMO only and read accounts. Never places orders."""
    names = ['CAPITAL_API_KEY', 'CAPITAL_IDENTIFIER', 'CAPITAL_API_PASSWORD']
    values = {name: os.environ.get(name) for name in names}
    if not all(values.values()):
        raise ValueError('Configura CAPITAL_API_KEY, CAPITAL_IDENTIFIER y CAPITAL_API_PASSWORD localmente')
    base = 'https://demo-api-capital.backend-capital.com/api/v1'
    _, headers = http_json(base + '/session', 'POST',
        {'X-CAP-API-KEY': values['CAPITAL_API_KEY']},
        {'identifier': values['CAPITAL_IDENTIFIER'],
         'password': values['CAPITAL_API_PASSWORD'], 'encryptedPassword': False})
    accounts, _ = http_json(base + '/accounts', headers={
        'CST': headers['CST'], 'X-SECURITY-TOKEN': headers['X-SECURITY-TOKEN']})
    # Counts only: do not print identifiers, balances or session tokens.
    print(json.dumps({'platform': 'capital-demo', 'connected': True,
                      'account_count': len(accounts.get('accounts', []))}))


def validate(c):
    if c.get('mode') != 'paper':
        raise ValueError('Esta versión solo permite mode=paper')
    if c.get('source') not in ('synthetic', 'binance_public'):
        raise ValueError('Fuente no implementada')
    if not isinstance(c.get('id'), str) or not c['id'].replace('-', '').replace('_', '').isalnum():
        raise ValueError('ID inválido')
    if not isinstance(c.get('symbol'), str) or not c['symbol'].isalnum():
        raise ValueError('Símbolo inválido')
    for key in ('initial_cash', 'order_notional', 'max_spread_bps', 'poll_seconds'):
        if not isinstance(c.get(key), (int, float)) or not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError('Parámetro positivo requerido: ' + key)
    for key in ('fee_bps', 'slippage_bps'):
        if not isinstance(c.get(key), (int, float)) or not math.isfinite(c[key]) or not 0 <= c[key] < 10000:
            raise ValueError('Coste inválido: ' + key)
    if not 0 < c.get('max_loss_fraction', 0) < 1:
        raise ValueError('Límite de pérdida inválido')
    if c['order_notional'] > c['initial_cash']:
        raise ValueError('Importe mayor al capital simulado')
    return c


class Ledger:
    def __init__(self, path, config):
        self.c = validate(config)
        self.db = sqlite3.connect(path, timeout=1)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY, config TEXT);
        CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, mid REAL);
        CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), cash REAL,
          qty REAL, halted INTEGER, step INTEGER, fingerprint TEXT);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp REAL,
          step INTEGER, kind TEXT, price REAL, qty REAL, fee REAL, equity REAL);
        ''')
        fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        row = self.db.execute('SELECT fingerprint FROM state WHERE id=1').fetchone()
        if row and row[0] != fingerprint:
            self.db.close()
            raise ValueError('Configuración cambiada: usa un ID nuevo para una simulación distinta')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES(1,?)', (json.dumps(config, sort_keys=True),))
            self.db.execute('INSERT OR IGNORE INTO state VALUES(1, ?, 0, 0, 0, ?)',
                            (config['initial_cash'], fingerprint))

    def state(self):
        return self.db.execute('SELECT cash,qty,halted,step FROM state WHERE id=1').fetchone()

    def tick(self, bid, ask, signal):
        if signal not in ('BUY', 'SELL', 'HOLD'):
            raise ValueError('Señal inválida')
        if not all(math.isfinite(x) and x > 0 for x in (bid, ask)) or ask < bid:
            raise ValueError('Cotización inválida')
        c = self.c
        with self.db:
            cash, qty, halted, step = self.state()
            equity = cash + qty * bid
            stop = equity <= c['initial_cash'] * (1 - c['max_loss_fraction'])
            forced_exit = bool(halted or stop)
            if stop:
                halted = 1  # Persists across restarts; a loss limit is not a guaranteed loss cap.
            if forced_exit:
                signal = 'SELL' if qty else 'HOLD'
            spread = (ask - bid) / ((ask + bid) / 2) * 10000
            kind, size, fee, price = 'HOLD', 0., 0., (bid + ask) / 2
            rate = c['fee_bps'] / 10000
            slip = c['slippage_bps'] / 10000
            if signal == 'BUY' and not halted and qty == 0 and spread <= c['max_spread_bps']:
                price = ask * (1 + slip)
                budget = min(c['order_notional'], cash / (1 + rate))
                size, fee = budget / price, budget * rate
                cash -= budget + fee
                qty = size
                kind = 'BUY'
            elif signal == 'SELL' and qty > 0:
                price = bid * (1 - slip)
                size = qty
                fee = size * price * rate
                cash += size * price - fee
                qty = 0
                kind = 'STOP' if forced_exit else 'SELL'
            equity = cash + qty * bid
            if equity <= c['initial_cash'] * (1 - c['max_loss_fraction']):
                halted = 1
            self.db.execute('INSERT INTO samples VALUES(NULL,?)', ((bid+ask)/2,))
            self.db.execute('DELETE FROM samples WHERE id NOT IN (SELECT id FROM samples ORDER BY id DESC LIMIT 20)')
            self.db.execute('UPDATE state SET cash=?,qty=?,halted=?,step=? WHERE id=1',
                            (cash, qty, halted, step + 1))
            self.db.execute('INSERT INTO events VALUES(NULL,?,?,?,?,?,?,?)',
                            (time.time(), step, kind, price, size, fee, equity))
        return {'bot': c['id'], 'mode': 'PAPER', 'source': c['source'], 'event': kind,
                'equity': round(equity, 4), 'position': qty, 'halted': bool(halted)}


def run_one(config, ticks):
    c = validate(config)
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    # OS lock auto-releases on crash (Linux and Windows).
    lock = open(data / (c['id'] + '.lock'), 'a+b')
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        if lock.read(1) == b'':
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    book = Ledger(data / (c['id'] + '.sqlite3'), c)
    history = [r[0] for r in reversed(book.db.execute('SELECT mid FROM samples ORDER BY id DESC LIMIT 20').fetchall())]
    failures = 0
    try:
        for _ in range(ticks) if ticks else iter(int, 1):
            if (ROOT / 'PAUSE').exists():
                print(c['id'] + ': PAUSE presente; saliendo sin liquidar posiciones simuladas', flush=True)
                break
            try:
                if c['source'] == 'synthetic':
                    step = book.state()[3]
                    mid = 100 + 2 * math.sin(step / 5)
                    bid, ask = mid - .01, mid + .01
                else:
                    bid, ask = binance_quote(c['symbol'])
                candidate_history = (history + [(bid + ask) / 2])[-20:]
                signal = 'HOLD'
                if len(candidate_history) == 20:
                    signal = 'BUY' if statistics.mean(candidate_history[-5:]) > statistics.mean(candidate_history) else 'SELL'
                print(json.dumps(book.tick(bid, ask, signal)), flush=True)
                history = candidate_history
                failures = 0
            except (RuntimeError, ValueError, KeyError) as exc:
                failures += 1
                print(json.dumps({'bot': c['id'], 'error_type': type(exc).__name__,
                                  'status': 'sin operación; reintento con espera'}), flush=True)
                if failures >= 5:
                    raise RuntimeError('Cinco fallos consecutivos; proceso detenido') from None
            time.sleep(min(60, c['poll_seconds'] * 2 ** failures))
    finally:
        book.db.close()
        lock.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--config', default='configs/two-paper.json')
    run.add_argument('--ticks', type=int, default=0, help='0 ejecuta hasta Ctrl+C')
    sub.add_parser('capital-probe')
    sub.add_parser('binance-probe')
    args = p.parse_args()
    if args.command == 'capital-probe':
        capital_probe(); return
    if args.command == 'binance-probe':
        bid, ask = binance_quote('BTCUSDT')
        print(json.dumps({'source': 'binance_public', 'symbol': 'BTCUSDT', 'bid': bid, 'ask': ask})); return
    if args.ticks < 0:
        p.error('--ticks debe ser >= 0')
    configs = json.loads(Path(args.config).read_text())['bots']
    if not configs or len({c['id'] for c in configs}) != len(configs):
        raise ValueError('Debe haber bots con IDs únicos')
    for c in configs:
        validate(c)
    workers = [mp.Process(target=run_one, args=(c, args.ticks), name=c['id']) for c in configs]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    except KeyboardInterrupt:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
        for worker in workers:
            worker.join()
    if any(w.exitcode for w in workers):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
