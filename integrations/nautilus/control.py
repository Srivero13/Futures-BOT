"""Offline engine migration control; no exchange clients or credentials."""
import argparse
import json
from decimal import Decimal as D
from importlib.metadata import version
from pathlib import Path

from engine_v1.core import Portfolio, Quote, dec


def run_account(name, exit_bid):
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
    from nautilus_trader.model.currencies import ETH, USDT
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    instrument = CurrencyPair(
        instrument_id=InstrumentId.from_str('ETHUSDT.SIM'), raw_symbol=Symbol('ETHUSDT'),
        base_currency=ETH, quote_currency=USDT, price_precision=2, size_precision=6,
        price_increment=Price.from_str('0.01'), size_increment=Quantity.from_str('0.000001'),
        maker_fee=D('0.001'), taker_fee=D('0.001'), ts_event=0, ts_init=0)

    class RoundTrip(Strategy):
        def __init__(self):
            super().__init__()
            self.ticks = 0
            self.fills = []

        def on_start(self):
            self.subscribe_quote_ticks(instrument.id)

        def on_quote_tick(self, tick):
            self.ticks += 1
            if self.ticks in (1, 3):
                order = self.order_factory.market(
                    instrument_id=instrument.id,
                    order_side=OrderSide.BUY if self.ticks == 1 else OrderSide.SELL,
                    quantity=Quantity.from_str('1.000000'))
                self.submit_order(order)

        def on_order_filled(self, event):
            self.fills.append(dict(side=event.order_side.name, price=str(event.last_px),
                                   quantity=str(event.last_qty),
                                   fee=str(event.commission.as_decimal()),
                                   fee_currency=str(event.commission.currency)))

    venue = Venue('SIM')
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(log_level='ERROR')))
    strategy = RoundTrip()
    quotes = [('100.00', '100.10'), ('100.00', '100.10'),
              (exit_bid, str(D(exit_bid) + D('0.10'))),
              (exit_bid, str(D(exit_bid) + D('0.10')))]
    try:
        engine.add_venue(venue=venue, oms_type=OmsType.NETTING,
                         account_type=AccountType.CASH, base_currency=None,
                         starting_balances=[Money(1000, USDT)])
        engine.add_instrument(instrument)
        engine.add_data([QuoteTick(instrument.id, Price.from_str(b), Price.from_str(a),
                         Quantity.from_str('100.000000'), Quantity.from_str('100.000000'),
                         (i+1)*1_000_000_000, (i+1)*1_000_000_000)
                         for i, (b, a) in enumerate(quotes)])
        engine.add_strategy(strategy)
        engine.run()
        balance = engine.cache.account_for_venue(venue).balance_total(USDT).as_decimal()
        open_positions = len(engine.cache.positions_open())
    finally:
        engine.dispose()

    ledger = Portfolio(':memory:', [dict(id=name, symbol='ETHUSDT', capital='1000',
                                        notional='100.10')], slip_bps='0')
    try:
        for i in (0, 2):
            b, a = quotes[i]
            q = Quote('ETHUSDT', dec(b), dec(a), dec('100'), dec('100'), (i+1)*1000, i)
            ledger.process({'ETHUSDT': q}, {name: {'enter': i == 0, 'exit': i == 2}},
                           q.timestamp_ms, event_id=str(i))
        state = ledger.states()[0]
    finally:
        ledger.close()
    expected_fees = (D('100.10') + D(exit_bid)) * D('0.001')
    expected_cash = D('1000') - D('100.10') + D(exit_bid) - expected_fees
    checks = dict(two_fills=len(strategy.fills) == 2,
                  exact_sides=[f['side'] for f in strategy.fills] == ['BUY', 'SELL'],
                  prices=[D(f['price']) for f in strategy.fills] == [D('100.10'), D(exit_bid)],
                  quantities=all(D(f['quantity']) == 1 for f in strategy.fills),
                  quote_fees=all(f['fee_currency'] == 'USDT' for f in strategy.fills),
                  fees=sum((D(f['fee']) for f in strategy.fills), D(0)) == expected_fees,
                  flat=open_positions == 0 and D(state['qty']) == 0,
                  cash_reconciled=balance == D(state['cash']) == expected_cash,
                  ledger_fees=D(state['fees']) == expected_fees)
    if not all(checks.values()):
        raise ValueError(f'{name}: reconciliation failed: {checks}; fills={strategy.fills}; cash={balance}')
    return dict(account=name, checks=checks, fills=strategy.fills, ending_cash=str(balance),
                ledger_cash=state['cash'], net_pnl=str(balance-D('1000')))


def run():
    installed = version('nautilus_trader')
    if installed != '1.231.0':
        raise ValueError(f'Expected NautilusTrader 1.231.0, found {installed}')
    return dict(approved=False, real_orders=False, synthetic=True,
                status='offline_accounting_control_passed', nautilus_version=installed,
                accounts=[run_account('account-a', '101.00'), run_account('account-b', '99.00')],
                limitations=['Two isolated simulated engines, not live multi-account routing.',
                             'Synthetic spot quotes, zero latency/extra slippage, 10 bps hypothetical fees.',
                             'No strategy, real fills, futures margin, funding or profitability validation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output exists; use a new output path.')
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
